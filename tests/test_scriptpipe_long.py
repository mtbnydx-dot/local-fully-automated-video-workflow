import asyncio
import contextlib
import io
import re
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from imagepipe.models import ImageConfig
from imagepipe.pipeline import run as run_images
from imagepipe.plan import compile_plan
from scriptpipe.long_pipeline import run_long
from videopipe.inputs import load_config, load_package, validate_plan
from videopipe.subtitles import extract_dialogue


class LongScriptTests(unittest.TestCase):
    def test_applied_prompt_examples_connect_to_images_and_video_with_music_and_voiceover(self):
        prompt_root = Path(__file__).resolve().parents[1] / "prompt/script"
        examples = []
        for name in ("season_plan", "episode_opening", "episode_plan", "scene_write"):
            content = (prompt_root / f"scriptpipe_long_{name}_zh.txt").read_text()
            examples.append(json.loads(re.search(r"```json\s*\n(.*?)\n```", content, re.S).group(1)))
        season, opening, body, scene = examples
        opening["events"][1]["voiceover"] = True

        class ExampleClient:
            key = "local-test-key"
            model = "fixture"
            endpoint = "local"
            reasoning_effort = "high"

            def event(self, *args, **kwargs):
                pass

            async def complete(self, name, system, payload, **kwargs):
                responses = {
                    "long_season": season, "ep01_opening_v0": opening,
                    "ep01_plan_v0": body, "ep01_ep01_scene01_v0": scene,
                    "ep01_review_0": {"issues": []}, "season_review_0": {"issues": []},
                }
                return responses[name]

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "novel.txt"
            source.write_text("讨薪。\n辞退威胁。\n录音。", encoding="utf-8")
            production = root / "production.yaml"
            production.write_text("generator: comfyui\n", encoding="utf-8")
            result = asyncio.run(run_long(source, root / "run", ExampleClient(), episode_count=1,
                                         production_config=production))
            self.assertEqual(result["status"], "text_ready")
            asyncio.run(run_long(source, root / "run", ExampleClient(), episode_count=1,
                                 production_config=production, long_review="report", stop_after="review"))
            quality = json.loads((root / "run/quality.json").read_text())
            self.assertEqual(quality["llm_review"], "reported")
            delivery = root / "handoff"
            (root / "run/delivery").rename(delivery)
            # Downstream stages must work with only the delivered package, without authoring caches.
            shutil.rmtree(root / "run")
            storyboard = json.loads((delivery / "episodes/ep01/storyboard.json").read_text())
            self.assertEqual(storyboard["shots"][0]["story_events"], opening["events"])
            env = root / "test.env"
            env.write_text("SCRIPT_HANDOFF_TEST_KEY=local-test-key\n")
            image_config = ImageConfig.model_validate({"api": {
                "env_file": str(env), "key_name": "SCRIPT_HANDOFF_TEST_KEY",
                "base_url": "http://127.0.0.1:1", "request_timeout_seconds": 1,
            }, "scheduler": {"max_attempts": 1}})
            image_plan = compile_plan(delivery, image_config)
            frames = [task for task in image_plan.tasks if task.asset_id.startswith("first-frame-")]
            self.assertEqual(len(frames), len(storyboard["shots"]))
            # Fixture images exercise actual image delivery/copy and video loading without inference.
            for task in image_plan.tasks:
                target = Path(task.target_path)
                target.parent.mkdir(parents=True, exist_ok=True)
                Image.new("RGB", (18, 32), "navy").save(target)
            with contextlib.redirect_stdout(io.StringIO()):
                report = asyncio.run(run_images(image_plan, image_config, root / "image-run"))
            self.assertTrue(report["success"])
            self.assertEqual(report["generated"], 0)
            package = load_package(delivery / "episodes/ep01/package.json")
            validate_plan(package, load_config(delivery / "episodes/ep01/production.yaml"))
            expected = [event["text_zh"] for event in opening["events"] + body["scenes"][0]["events"] if "text_zh" in event]
            self.assertEqual([line["text"] for line in extract_dialogue(package.shots)], expected)
            self.assertIn("says in an off-screen voiceover", package.shots[0].prompt)
            self.assertIn("lips remain closed", package.shots[0].prompt)
            for raw, shot in zip(scene["shots"], package.shots):
                self.assertIn("non_diegetic_music: " + raw["non_diegetic_music_en"], shot.prompt)
                self.assertEqual(sum(asset.role == "first_frame" for asset in shot.asset_bindings), 1)
                self.assertTrue(all(asset.path.is_file() for asset in shot.asset_bindings))


if __name__ == "__main__":
    unittest.main()
