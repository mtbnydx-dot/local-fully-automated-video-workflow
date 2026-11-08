import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from videopipe.inputs import load_package
from videopipe.media import inspect_video, run_ffmpeg
from videopipe.models import PipelineConfig, SubtitleConfig
from videopipe.pipeline import Production


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "script.md").write_text("# Two shots of a blue cup\nWide shot, then close-up.")
        Image.new("RGB", (160, 96), "teal").save(self.root / "reference.png")
        self.manifest = self.root / "package.json"
        self.data = {"title": "Test film", "script": "script.md", "shots": [
            {"id": name, "prompt": f"A blue cup, {name}", "reference_images": ["reference.png"],
             "width": 160, "height": 96, "duration": 0.25, "fps": 24}
            for name in ("wide", "close")
        ]}
        self.manifest.write_text(json.dumps(self.data))
        self.package = load_package(self.manifest)
        self.config = PipelineConfig.model_validate({
            "generator": "cpu", "workers": 2, "human_approval": False, "review": {"sample_frames": 2},
            "media": {"width": 160, "height": 96, "upscale": "lanczos", "upscale_factor": 2},
        })
        self.run_dir = self.root / "run"

    def test_full_run_repairs_only_rejected_shots_then_upscales_before_assembly(self):
        self.config.review.reject_once = ["wide"]
        state = Production.create(self.package, self.config, self.run_dir).run()
        self.assertEqual(state["status"], "complete")
        self.assertEqual([state["shots"][key]["attempts"] for key in ("wide", "close")], [2, 1])
        self.assertEqual(state["assembly_version"], 1)
        info = inspect_video(self.run_dir / state["final"])
        self.assertEqual((info.width, info.height), (320, 192))
        self.assertAlmostEqual(info.duration, 0.5, delta=0.1)
        run_ffmpeg(["-v", "error", "-i", str(self.run_dir / state["final"]), "-f", "null", "-"])
        events = [json.loads(line) for line in (self.run_dir / "events.jsonl").read_text().splitlines()]
        self.assertTrue(any(event["event"] == "run_completed" for event in events))
        stages = [event for event in events if event["event"] == "stage_finished"]
        self.assertEqual({event["stage"] for event in stages},
                         {"generate", "upscale", "shot_review", "assemble", "asr", "finalize"})
        self.assertTrue(all(event["status"] == "complete" and event["elapsed"] >= 0 for event in stages))
        self.assertTrue((self.run_dir / "shots/wide/attempt-001/review/result.json").is_file())
        self.assertLess(max(i for i, e in enumerate(events) if e["event"] == "stage_finished" and e["stage"] == "upscale"),
                        next(i for i, e in enumerate(events) if e["event"] == "stage_started" and e["stage"] == "assemble"))
        self.assertEqual(Production(self.run_dir).run()["shots"], state["shots"])

    def test_approval_and_targeted_retry_preserve_previous_delivery(self):
        self.config.human_approval = True
        state = Production.create(self.package, self.config, self.run_dir).run()
        self.assertEqual(state["status"], "awaiting_approval")
        self.assertNotIn("final", state)
        state = Production(self.run_dir).approve()
        old_final = self.run_dir / state["final"]
        old_bytes = old_final.read_bytes()
        production = Production(self.run_dir)
        production.retry(["close"], feedback="Please make another take")
        state = production.run(auto_approve=True)
        self.assertEqual(state["shots"]["wide"]["attempts"], 1)
        self.assertEqual(state["shots"]["close"]["attempts"], 2)
        self.assertNotEqual(old_final, self.run_dir / state["final"])
        self.assertEqual(old_bytes, old_final.read_bytes())
        params = json.loads((self.run_dir / "shots/close/attempt-002/shot.json").read_text())
        self.assertEqual(params["prompt"], "A blue cup, close")
        self.assertEqual(state["shots"]["close"]["budget_used"], 2)

    def test_budget_selects_a_take_and_only_explicit_new_round_resets_allowance(self):
        self.config.max_attempts = 1
        self.config.review.reject_once = ["wide"]
        state = Production.create(self.package, self.config, self.run_dir).run()
        self.assertEqual(state["status"], "complete")
        self.assertEqual(state["shots"]["wide"]["selection"]["reason"], "budget_exhausted")
        production = Production(self.run_dir)
        with self.assertRaisesRegex(ValueError, "budget exhausted"):
            production.retry(["wide"])
        production.retry(["wide"], feedback="Try again", new_round=True)
        state = production.run()
        self.assertEqual(state["status"], "complete")
        self.assertEqual(state["shots"]["close"]["attempts"], 1)
        self.assertEqual(state["shots"]["wide"]["round"], 1)
        self.assertEqual(state["shots"]["wide"]["budget_used"], 1)
        self.assertEqual(state["shots"]["wide"]["attempts"], 2)

    def test_negative_prompt_is_combined_once_at_input_and_never_on_resume(self):
        self.package.shots[0].negative_prompt = "No red cup"
        production = Production.create(self.package, self.config, self.run_dir)
        self.addCleanup(production.events.close)
        expected = "A blue cup, wide\n\nAvoid: No red cup"
        self.assertEqual(production.package.shots[0].prompt, expected)
        resumed = Production(self.run_dir)
        self.addCleanup(resumed.events.close)
        self.assertEqual(resumed.package.shots[0].prompt, expected)
        source = json.loads((self.run_dir / "input-package.json").read_text())
        self.assertEqual(source["shots"][0]["prompt"], "A blue cup, wide")
        self.assertEqual(source["shots"][0]["negative_prompt"], "No red cup")

    def test_parameter_overrides_cannot_change_prompt_or_seed(self):
        for key in ("prompt", "h3_prompt", "seed", "reference_image_0"):
            with self.subTest(key=key):
                self.package.shots[0].parameters = {key: "replacement"}
                with self.assertRaisesRegex(ValueError, "parameter overrides"):
                    Production.create(self.package, self.config, self.run_dir)
        self.assertFalse(self.run_dir.exists())

    def test_optional_asr_process_failure_does_not_block_video_delivery(self):
        self.config.asr.enabled = True
        self.config.asr.model = str(self.root / "missing-local-model")
        self.package.shots[0].prompt += " <d>[Chinese] 等一下。</d>"
        state = Production.create(self.package, self.config, self.run_dir).run()
        self.assertEqual(state["status"], "complete")
        self.assertEqual(state["audio"]["transcript"]["status"], "unavailable")
        self.assertEqual(state["audio"]["subtitles"]["status"], "complete")
        self.assertEqual(state["audio"]["subtitles"]["timing"], "script")
        self.assertFalse(state["audio"]["consistency"]["available"])
        self.assertIn("等一下。", (self.run_dir / state["final"]).with_name("episode.srt").read_text())
        self.assertEqual([s["attempts"] for s in state["shots"].values()], [1, 1])

    def test_burned_subtitles_stay_within_three_lines_inside_the_lower_third(self):
        for shot in self.package.shots:
            shot.width, shot.height, shot.duration = 144, 256, 1
        self.package.shots[0].prompt += (" <d>[Chinese] 我告诉你，这份合同上的每一个字都是我亲手写的，"
                                         "你以为改掉一个数字就没人发现吗？董事会明天上午九点开会，你最好想清楚该怎么解释。</d>")
        self.config.media.width, self.config.media.height = 144, 256
        self.config.subtitles = SubtitleConfig(burn=True)
        state = Production.create(self.package, self.config, self.run_dir).run()
        final = self.run_dir / state["final"]
        self.assertTrue(state["delivery"]["burned_subtitles"])
        cues = [line.split(",", 9)[9] for line in final.with_name("episode.ass").read_text(encoding="utf-8").splitlines()
                if line.startswith("Dialogue:")]
        self.assertGreater(len(cues), 1)
        self.assertTrue(all(len(cue.split(r"\N")) <= 3 and cue.endswith(("，", "？", "。")) for cue in cues))
        for second, subtitled in ((0.2, True), (1.5, False)):
            frame = self.root / f"frame-{second}.png"
            run_ffmpeg(["-v", "error", "-ss", str(second), "-i", str(final), "-frames:v", "1", str(frame)])
            with Image.open(frame) as image:
                gray = image.convert("L")
            # White subtitle pixels below the CPU preview label.
            rows = [y for y in range(gray.height // 5, gray.height)
                    if any(gray.getpixel((x, y)) > 235 for x in range(gray.width))]
            self.assertEqual(bool(rows), subtitled)
            self.assertTrue(all(y >= gray.height * 2 / 3 for y in rows))

    def test_package_files_are_snapshotted_and_paths_resolve_from_manifest(self):
        production = Production.create(self.package, self.config, self.run_dir)
        (self.root / "reference.png").unlink()
        (self.root / "script.md").unlink()
        self.assertEqual(production.run()["status"], "complete")

    def test_cli_validation_rejects_bad_inputs_and_yaml_without_traceback(self):
        self.data["shots"][1]["id"] = "wide"
        self.manifest.write_text(json.dumps(self.data))
        config_path = self.root / "config.yaml"
        config_path.write_text("generator: cpu\n")
        command = [sys.executable, "-m", "videopipe", "validate", str(self.manifest),
                   "--config", str(config_path)]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("unique", result.stderr)
        self.data["shots"][1]["id"] = "close"
        self.manifest.write_text(json.dumps(self.data))
        config_path.write_text("generator: [not yaml\n")
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("Traceback", result.stderr)

    def test_h3_constraints_are_checked_before_creating_run(self):
        self.config.generator = "comfyui"
        self.package.shots[0].fps = 12
        with self.assertRaisesRegex(ValueError, "24 fps"):
            Production.create(self.package, self.config, self.run_dir)
        self.assertFalse(self.run_dir.exists())

    def test_ui_workflow_is_rejected_at_entry_with_export_guidance(self):
        path = self.root / "ui-workflow.json"
        path.write_text(json.dumps({"nodes": [], "links": []}))
        self.config.comfyui.workflow = path
        with self.assertRaisesRegex(ValueError, "API format"):
            Production.create(self.package, self.config, self.run_dir)
        self.assertFalse(self.run_dir.exists())


if __name__ == "__main__":
    unittest.main()
