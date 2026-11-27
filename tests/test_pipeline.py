import json
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


if __name__ == "__main__":
    unittest.main()
