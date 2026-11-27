import asyncio
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import yaml
from PIL import Image

from imagepipe.models import ImageConfig
from imagepipe.pipeline import run as run_images
from imagepipe.plan import compile_plan
from scriptpipe.batch import export_batch
from scriptpipe.export import export_season
from scriptpipe.checks import check_episode
from videopipe.inputs import load_package, validate_plan
from videopipe.models import PipelineConfig, ScriptPackage
from videopipe.subtitles import extract_dialogue


def season_fixture():
    season = {
        "title": "连续剧测试", "logline": "同一人物跨集进入新场景。", "style_en": "Naturalistic drama.",
        "characters": [{
            "id": character, "name": name, "appearance_en": "An adult with short black hair.",
            "voice_en": "A calm Mandarin voice.",
            "wardrobes": [{"id": "work", "description_en": "A navy cotton shirt and black trousers."}],
        } for character, name in [("hero", "主角"), ("later_guest", "后续人物")]],
        "locations": [{"id": location, "name": name, "description_en": description} for location, name, description in [
            ("office", "办公室", "An empty office with a desk beside the west window."),
            ("garden", "花园", "An empty garden with a stone path leading north."),
        ]],
        "props": [], "episodes": [],
    }
    episodes = []
    for number in range(1, 4):
        episode_id = f"ep{number:02}"
        episode = {"id": episode_id, "title": f"第{number}集", "synopsis": "主角观察环境。",
                   "start_state": "来到现场", "end_state": "看清环境"}
        season["episodes"].append({**episode, "summary": episode["synopsis"]})
        episode["shots"] = [{
            "id": f"{episode_id}_s001", "scene_id": f"{episode_id}_scene",
            "location_id": "garden" if number == 3 else "office", "time_of_day": "day",
            "characters": [{"id": character, "wardrobe_id": "work"}
                           for character in (["hero", "later_guest"] if number == 3 else ["hero"])],
            "prop_ids": [], "duration": 5.875, "dialogue": [],
            "story_events": [{"id": "ev001", "action_zh": "主角抬头，目光停住。"}],
            "visual_en": "The adult looks around and settles their gaze.", "camera_en": "Locked wide shot.",
            "soundscape_en": "Quiet ambient sound.", "first_frame_prompt_en": "The adult stands still before looking up.",
            "acceptance_en": ["The adult completes the glance."],
        }]
        episodes.append(episode)
    return season, episodes


class ScriptBatchTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.canonical = self.root / "full-season"
        config_path = self.root / "production.yaml"
        config_path.write_text("generator: cpu\n", encoding="utf-8")
        self.season, episodes = season_fixture()
        export_season(self.season, episodes, self.canonical, config_path)
        env_path = self.root / ".env"
        env_path.write_text("SCRIPT_BATCH_TEST_KEY=local-test-key\n", encoding="utf-8")
        self.image_config = ImageConfig.model_validate({
            "api": {"base_url": "http://127.0.0.1:1", "env_file": str(env_path),
                    "key_name": "SCRIPT_BATCH_TEST_KEY", "request_timeout_seconds": 1},
            "scheduler": {"max_attempts": 1},
        })

    def supply_images_and_export(self, episode_ids, output):
        plan = compile_plan(self.canonical, self.image_config, episode_ids)
        for task in plan.tasks:
            target = Path(task.target_path)
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                Image.new("RGB", (18, 32), (task.seed % 255, 80, 120)).save(target)
        with contextlib.redirect_stdout(io.StringIO()):
            report = asyncio.run(run_images(plan, self.image_config, self.root / f"images-{episode_ids[0]}"))
        self.assertTrue(report["success"])
        self.assertEqual(report["generated"], 0)
        self.assertEqual(report["reused"], len(plan.tasks))
        result = export_batch(self.canonical, output, episode_ids, [task.asset_id for task in plan.tasks],
                              hardlink_images=self.image_config.asset_copy_mode == "hardlink")
        return plan, result

    def test_first_batch_is_portable_and_preserves_canonical_ids_seeds_and_images(self):
        output = self.root / "delivery-ep01-ep02"
        plan, summary = self.supply_images_and_export(["ep01", "ep02"], output)
        self.assertEqual([episode["id"] for episode in summary["episodes"]], ["ep01", "ep02"])
        self.assertTrue(summary["render_ready"])
        self.assertFalse((output / "episodes/ep03").exists())
        manifest = json.loads((output / "image_slots.json").read_text(encoding="utf-8"))
        self.assertEqual({slot["asset_id"] for slot in manifest["shared_assets"]}, {
            "identity-hero", "character-hero-work", "location-office",
        })
        self.assertFalse((self.canonical / "assets/review/characters/identity-later_guest.png").exists())
        self.assertEqual((output / "season.json").read_bytes(), (self.canonical / "season.json").read_bytes())
        self.assertEqual(len(json.loads((output / "season.json").read_text())["episodes"]), 3)
        full_plan = compile_plan(self.canonical, self.image_config)
        full_tasks = {task.asset_id: task for task in full_plan.tasks}
        for task in plan.tasks:
            self.assertEqual(task.seed, full_tasks[task.asset_id].seed)
            self.assertEqual(task.prompt, full_tasks[task.asset_id].prompt)
        for episode in summary["episodes"]:
            relative = Path(episode["package"])
            self.assertEqual((output / relative).read_bytes(), (self.canonical / relative).read_bytes())
            package = load_package(output / relative)
            for shot in package.shots:
                for asset in shot.asset_bindings:
                    self.assertTrue(asset.path.is_relative_to(output))
                    self.assertEqual(asset.path.read_bytes(), (self.canonical / asset.path.relative_to(output)).read_bytes())
        for slot in manifest["shared_assets"] + manifest["first_frames"]:
            self.assertEqual((output / slot["path"]).read_bytes(), (self.canonical / slot["path"]).read_bytes())

    def test_export_preserves_configured_canvas_multilingual_turns_and_reference_priority(self):
        season, episodes = season_fixture()
        shot = episodes[2]["shots"][0]
        shot.update(duration=11.5, acceptance_en=[], reference_priority=["garden", "later_guest"], dialogue=[
            {"speaker_id": "hero", "text_zh": "<d>这件事<cutoff>还没结束</d>", "voiceover": True, "delivery_en": "An urgent inner thought."},
            {"speaker_id": "later_guest", "text_zh": "2 > 1. OK?", "language": "English", "voiceover": False, "delivery_en": "Quickly."},
            {"speaker_id": "hero", "text_zh": "别走，我还有事要问你！", "voiceover": False, "delivery_en": "Interrupting."},
        ])
        shot["story_events"].extend(
            {"id": f"ev{index:03}", "speaker_id": line["speaker_id"], "text_zh": line["text_zh"],
             "voiceover": line["voiceover"]}
            for index, line in enumerate(shot["dialogue"], 2)
        )
        config = PipelineConfig(comfyui={"maximum_duration_seconds": 12}, max_attempts=5,
                                media={"width": 1024, "height": 576, "upscale_factor": 6},
                                script={"non_diegetic_music": "Tense strings.", "on_screen_text": "Include the message on the phone."})
        self.assertEqual(check_episode(episodes[2], season, config=config), [])
        output = self.root / "configured-export"
        export_season(season, episodes, output, config)
        package = ScriptPackage.model_validate(json.loads((output / "episodes/ep03/package.json").read_text()))
        exported = package.shots[0]
        self.assertEqual((exported.width, exported.height, exported.fps), (1024, 576, 24))
        self.assertEqual([(line["language"], line["text"]) for line in extract_dialogue(package.shots)], [
            ("Chinese", "这件事还没结束"), ("English", "2 > 1. OK?"), ("Chinese", "别走，我还有事要问你！"),
        ])
        self.assertNotIn("all visible characters keep their lips closed", exported.prompt)
        self.assertNotIn("other visible characters listen silently", exported.prompt)
        self.assertIn("non_diegetic_music: Tense strings.", exported.prompt)
        self.assertIn("Include the message on the phone.", exported.prompt)
        self.assertEqual(exported.acceptance, [])
        validate_plan(package, config)
        with self.assertRaisesRegex(ValueError, "maximum_duration_seconds"):
            validate_plan(package, PipelineConfig())
        slots = json.loads((output / "episodes/ep03/image_slots.json").read_text())["slots"]
        frame = next(slot for slot in slots if slot["purpose"] == "first_frame")
        self.assertEqual(frame["reference_asset_ids"][:3], ["location-garden", "identity-later_guest", "character-later_guest-work"])
        saved = PipelineConfig.model_validate(yaml.safe_load((output / "episodes/ep03/production.yaml").read_text()))
        self.assertEqual(saved.media, config.media)
        self.assertEqual(saved.script, config.script)


if __name__ == "__main__":
    unittest.main()
