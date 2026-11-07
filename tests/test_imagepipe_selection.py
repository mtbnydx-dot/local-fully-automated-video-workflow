import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml
from PIL import Image

from imagepipe.models import ImageConfig
from imagepipe.plan import compile_plan


class ImageEpisodeSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.package = self.root / "season"
        self.package.mkdir()
        shared = [
            {"asset_id": "identity-hero", "purpose": "character_identity", "character_id": "hero"},
            {"asset_id": "outfit-hero", "purpose": "character_reference", "character_id": "hero",
             "wardrobe_id": "office", "reference_asset_ids": ["identity-hero"]},
            {"asset_id": "room", "purpose": "location_reference", "location_id": "room"},
            {"asset_id": "box", "purpose": "prop_reference", "prop_id": "box"},
            {"asset_id": "open-box", "purpose": "prop_reference", "prop_id": "open-box",
             "reference_asset_ids": ["box"]},
            {"asset_id": "future-room", "purpose": "location_reference", "location_id": "future-room"},
        ]
        for slot in shared:
            slot.update(path=f"assets/review/{slot['asset_id']}.png", prompt_en="A reference image.")
        frames = []
        for episode_id in ("ep01", "ep02"):
            folder = self.package / "episodes" / episode_id
            folder.mkdir(parents=True)
            refs = ["identity-hero", "outfit-hero", "room", "open-box"]
            episode_slots = []
            for index in (1, 2):
                shot_id = f"{episode_id}_s{index:03}"
                slot = {
                    "asset_id": f"first-frame-{shot_id}", "purpose": "first_frame",
                    "path": f"assets/first_frames/{shot_id}.png", "prompt_en": "A person holds a box.",
                    "episode_id": episode_id, "shot_id": shot_id, "scene_id": f"{episode_id}_scene1",
                    "location_id": "room", "time_of_day": "day", "reference_asset_ids": refs,
                    "scene_anchor_shot_id": f"{episode_id}_s001",
                }
                episode_slots.append(slot)
                frames.append({**slot, "path": f"episodes/{episode_id}/{slot['path']}"})
            episode_slots.extend({**slot, "source_path": f"../../{slot['path']}"}
                                 for slot in shared if slot["asset_id"] in refs)
            (folder / "image_slots.json").write_text(json.dumps({"slots": episode_slots}))
        (self.package / "season.json").write_text(json.dumps({"style_en": "Cinematic."}))
        (self.package / "image_slots.json").write_text(json.dumps({"shared_assets": shared, "first_frames": frames}))

    def test_selection_keeps_reference_closure_scene_anchors_and_canonical_seeds(self):
        config = ImageConfig()
        all_tasks = {task.asset_id: task for task in compile_plan(self.package, config).tasks}
        plan = compile_plan(self.package, config, ["ep01"])
        tasks = {task.asset_id: task for task in plan.tasks}
        self.assertEqual(set(tasks), {
            "first-frame-ep01_s001", "first-frame-ep01_s002",
            "identity-hero", "outfit-hero", "room", "open-box", "box",
        })
        self.assertIn("first-frame-ep01_s001", tasks["first-frame-ep01_s002"].reference_ids)
        self.assertEqual(tasks["open-box"].reference_ids, ["box"])
        self.assertEqual(len(plan.copies), 4)
        self.assertTrue(all("episodes/ep01/" in item.target_path for item in plan.copies))
        for asset_id, task in tasks.items():
            self.assertEqual(task.target_path, all_tasks[asset_id].target_path)
            self.assertEqual(task.seed, all_tasks[asset_id].seed)
        later = {task.asset_id: task for task in compile_plan(self.package, config, ["ep02"]).tasks}
        self.assertEqual(tasks["identity-hero"].target_path, later["identity-hero"].target_path)
        self.assertEqual(tasks["identity-hero"].seed, later["identity-hero"].seed)

    def test_selection_rejects_missing_episode_and_standalone_package(self):
        with self.assertRaisesRegex(ValueError, "ep03"):
            compile_plan(self.package, ImageConfig(), ["ep03"])
        with self.assertRaisesRegex(ValueError, "season package"):
            compile_plan(self.package / "episodes/ep01", ImageConfig(), ["ep01"])

    def test_scene_anchor_stays_within_location_and_time_group(self):
        manifest_path = self.package / "image_slots.json"
        manifest = json.loads(manifest_path.read_text())
        frame = manifest["first_frames"][1]
        frame.update(location_id="future-room", time_of_day="night")
        manifest_path.write_text(json.dumps(manifest))
        tasks = {task.asset_id: task for task in compile_plan(self.package, ImageConfig(), ["ep01"]).tasks}
        self.assertNotIn("first-frame-ep01_s001", tasks["first-frame-ep01_s002"].reference_ids)

    def test_reference_budget_uses_configured_priority_without_restricting_cast(self):
        config = ImageConfig(api={"max_reference_images": 2}, continuity={
            "auto_scene_anchors": False,
            "reference_priority": {"first-frame-ep01_s001": ["open-box", "outfit-hero"]},
        })
        tasks = {task.asset_id: task for task in compile_plan(self.package, config, ["ep01"]).tasks}
        frame = tasks["first-frame-ep01_s001"]
        self.assertEqual(frame.reference_ids, ["open-box", "outfit-hero"])
        self.assertIn("<image1>: appearance of open-box", frame.prompt)
        self.assertIn("<image2>: clothing design for hero", frame.prompt)
        self.assertNotIn("Exactly", frame.prompt)
        self.assertTrue(all(len(task.reference_ids) <= 2 for task in tasks.values()))
        config.api.max_reference_images = 12
        frames = {task.asset_id: task for task in compile_plan(self.package, config, ["ep01"]).tasks}
        self.assertEqual(len(frames["first-frame-ep01_s001"].reference_ids), 4)

    def test_cli_persists_selection_resumes_and_rejects_different_selection(self):
        from imagepipe.cli import main

        env = self.root / ".env"
        env.write_text("SELECTION_TEST_KEY=local-test-key\n")
        config = ImageConfig.model_validate({"api": {"env_file": str(env), "key_name": "SELECTION_TEST_KEY"}})
        config_path = self.root / "image.yaml"
        config_path.write_text(yaml.safe_dump(config.model_dump()))
        selected = compile_plan(self.package, config, ["ep01"])
        for task in selected.tasks:
            target = Path(task.target_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (18, 32), "teal").save(target)
        output = self.root / "run"

        def invoke(*args):
            with patch.object(sys, "argv", ["imagepipe", *map(str, args)]), \
                    contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                return main()

        self.assertEqual(invoke("run", self.package, "--config", config_path,
                                "--output", output, "--episodes", "1-1"), 0)
        self.assertEqual(json.loads((output / "batch.json").read_text()), {"episode_ids": ["ep01"]})
        self.assertEqual(invoke("resume", output), 0)
        report = json.loads((output / "report.json").read_text())
        self.assertEqual(report["reused"], len(selected.tasks))
        self.assertTrue(report["success"])
        self.assertEqual(invoke("run", self.package, "--provider", "qwen",
                                "--output", output, "--episodes", "1-1"), 1)
        self.assertEqual(invoke("run", self.package, "--config", config_path,
                                "--output", output, "--episodes", "2-2"), 1)
        self.assertFalse((self.package / "episodes/ep02/assets/first_frames/ep02_s001.png").exists())
        self.assertFalse((self.package / "assets/review/future-room.png").exists())


if __name__ == "__main__":
    unittest.main()
