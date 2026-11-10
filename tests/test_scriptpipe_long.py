import asyncio
import copy
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
from scriptpipe.checks import check_episode
from scriptpipe.long_checks import check_long_plan, check_long_season, check_opening, check_scene, resolve_scene
from scriptpipe.long_pipeline import merge_opening, run_long, source_excerpt
from videopipe.inputs import load_config, load_package, validate_plan
from videopipe.models import PipelineConfig
from videopipe.subtitles import extract_dialogue


def episode_fixture(episode_id, scene_shot_counts=(2, 3)):
    shots = []
    for scene_number, count in enumerate(scene_shot_counts, 1):
        for _ in range(count):
            number = len(shots) + 1
            shots.append({
                "id": f"{episode_id}_s{number:03}", "scene_id": f"{episode_id}_scene{scene_number:02}",
                "location_id": "room", "time_of_day": "day", "duration": (4, 6.5, 9.4)[(number - 1) % 3],
                "characters": [], "prop_ids": [], "dialogue": [],
                "visual_en": "An empty room.", "camera_en": "Locked wide shot.",
                "soundscape_en": "Quiet room tone.", "first_frame_prompt_en": "An empty room in daylight.",
                "acceptance_en": ["The room remains empty."], "beat_zh": "光线落入室内",
                "action_start_zh": "光线移动", "action_end_zh": "光线停住", "cut_reason_zh": "转入下一时刻",
                "action_complete": True,
            })
    return {
        "id": episode_id, "title": "测试", "synopsis": "发现线索", "start_state": "等待", "end_state": "知情",
        "shots": shots,
    }


def plan_fixture(episode):
    scenes = []
    for shot in episode["shots"]:
        if not scenes or scenes[-1]["id"] != shot["scene_id"]:
            scenes.append({"id": shot["scene_id"], "location_id": "room", "time_of_day": "day",
                           "characters": [], "prop_ids": [],
                           "events": [{"id": f"ev{i:03}", "action_zh": f"室内光线变化，第{i}步。"}
                                      for i in range(1, 7)]})
    return {"id": episode["id"], "scenes": scenes}


def season_fixture(episodes):
    return {"title": "测试剧集", "logline": "发现线索", "style_en": "Naturalistic drama.", "characters": [],
            "locations": [{"id": "room", "name": "房间", "description_en": "A room in daylight."}], "props": [],
            "episodes": [{"id": episode["id"], "title": "测试", "summary": "发现线索",
                          "start_state": "等待", "end_state": "知情", "required_events": ["发现线索"],
                          "source_ranges": [[1, 1]]} for episode in episodes]}


def opening_fixture(episode_id):
    return {"episode_id": episode_id, "location_id": "room", "time_of_day": "day",
            "characters": [], "prop_ids": [], "events": [
                {"id": "opening_ev001", "action_zh": "房间突然暗下来。"},
                {"id": "opening_ev002", "action_zh": "一道强光照进窗内。"},
            ]}


class ScriptClient:
    """Replace remote model responses while exercising actual orchestration and export."""

    key = "test-key"
    model = "deepseek-v4.1-flash"
    endpoint = "https://example.invalid"
    reasoning_effort = "high"

    def __init__(self, scene_shot_counts=(2, 3)):
        self.calls = []
        self.payloads = {}
        self.scene_shot_counts = scene_shot_counts

    def event(self, *args, **kwargs):
        pass

    async def complete(self, name, system, payload, **kwargs):
        self.calls.append((name, kwargs))
        self.payloads[name] = copy.deepcopy(payload)
        if name == "long_season":
            return season_fixture([{"id": f"ep{index:02}"} for index in range(1, payload["brief"]["episode_count"] + 1)])
        if name.endswith("_opening_v0"):
            return opening_fixture(payload["episode_plan"]["id"])
        if name.endswith("_plan_v0"):
            return plan_fixture(episode_fixture(payload["episode_plan"]["id"]))
        if "scene" in payload:
            scene = payload["scene"]
            body = [event for event in scene["events"] if not event["id"].startswith("opening_")]
            count = self.scene_shot_counts[int(scene["id"][-2:]) - 1]
            groups = [(body[index * len(body) // count:(index + 1) * len(body) // count],
                       (4, 6.5, 9.4)[index % 3]) for index in range(count)] if body else []
            if "opening" in scene:
                groups.insert(0, (opening_fixture(payload["episode_id"])["events"], 7.5))
            shots = [{
                "id": f"s{index + 1:03}", "event_refs": [{"event_id": event["id"]} for event in events],
                "character_ids": [], "prop_ids": [], "duration": duration,
                "first_frame_prompt_en": "An empty room in daylight.", "visual_en": "Light moves across the room.",
                "camera_en": "Locked wide shot.", "soundscape_en": "Quiet room tone.", "non_diegetic_music_en": "N/A",
            } for index, (events, duration) in enumerate(groups)]
            return {"episode_id": payload["episode_id"], "scene_id": scene["id"],
                    "anchor_shot_id": shots[-1]["id"], "shots": shots}
        if name == "ep01_review_0":
            return {"issues": [{"severity": "error", "code": "story_clarity", "message": "Clarify the first event."}]}
        if name == "season_review_0":
            return {"issues": []}
        raise AssertionError(f"Unexpected model call: {name}")


class LongScriptTests(unittest.TestCase):
    def test_episode_runtime_is_a_target_without_scene_or_shot_quotas(self):
        for count, minutes in [(64, 5), (1, 1), (48, 10)]:
            with self.subTest(count=count, minutes=minutes), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source = root / "novel.txt"
                source.write_text("测试原文", encoding="utf-8")
                result = asyncio.run(run_long(source, root / "run", ScriptClient(), episode_count=count,
                                             episode_minutes=minutes, stop_after="season"))
                brief = result["brief"]
                self.assertEqual(brief["episode_count"], count)
                self.assertEqual(brief["target_episode_duration_seconds"], minutes * 60)
                self.assertEqual(brief["target_season_duration_seconds"], count * minutes * 60)
                self.assertNotIn("preferred_duration_seconds", brief)
                self.assertEqual(brief["maximum_requested_duration_seconds"], 9.4)
                self.assertEqual(brief["opening_duration_range_seconds"], [5, 9.4])
                self.assertEqual(brief["maximum_duration_seconds"], 10)
                for key in ("scenes_per_episode", "shots_per_scene", "shots_per_episode", "duration_per_shot"):
                    self.assertNotIn(key, brief)
                self.assertEqual(result["review_effort"], "high")

    def test_plan_checks_formal_events_without_estimated_shot_ranges(self):
        episode = episode_fixture("ep01")
        season = season_fixture([episode])
        plan = plan_fixture(episode)
        self.assertEqual(check_long_plan(plan, season, season["episodes"][0]), [])
        for field, value, code in [
            ("events", [], "scene_events"),
            ("time_of_day", "", "time_of_day"),
        ]:
            changed = copy.deepcopy(plan)
            changed["scenes"][1][field] = value
            self.assertIn(code, [issue["code"] for issue in check_long_plan(changed, season, season["episodes"][0])])
        plan["scenes"][0]["events"][1]["id"] = "ev001"
        self.assertIn("event_id", [issue["code"] for issue in check_long_plan(plan, season, season["episodes"][0])])

    def test_source_ranges_select_original_text_and_reject_out_of_bounds(self):
        paragraphs = [{"id": i, "text": text} for i, text in enumerate(("前情", "本集原句", "后文"), 1)]
        self.assertEqual(source_excerpt({"id": "ep01", "source_ranges": [[2, 2]]}, paragraphs), [paragraphs[1]])
        with self.assertRaisesRegex(ValueError, "within the numbered source"):
            source_excerpt({"id": "ep01", "source_ranges": [[2, 4]]}, paragraphs)

    def test_long_season_allows_different_scene_counts_and_shot_counts(self):
        episodes = [episode_fixture("ep01", (2, 3)), episode_fixture("ep02", (1,)),
                    episode_fixture("ep03", (4, 1, 2))]
        season = season_fixture(episodes)
        self.assertEqual(check_long_season(episodes, season), [])
        episodes[0]["shots"][2]["id"] = "ep01_s004"
        self.assertIn("shot_number", [issue["code"] for issue in check_long_season(episodes, season)])
        self.assertIn("season_episode_order", [issue["code"] for issue in check_long_season(episodes[:-1], season)])

    def test_h3_rounding_limit_applies_to_flexible_shot_durations(self):
        episode = episode_fixture("ep01", (1,))
        season = season_fixture([episode])
        plan = plan_fixture(episode)
        scene = {"episode_id": "ep01", "scene_id": "ep01_scene01", "anchor_shot_id": "ep01_s001", "shots": episode["shots"]}
        episode["shots"][0]["duration"] = 9.4
        self.assertEqual(check_scene(scene, plan["scenes"][0], plan, season), [])
        episode["shots"][0]["duration"] = 9.5
        self.assertIn("h3_duration_limit", [issue["code"] for issue in check_scene(scene, plan["scenes"][0], plan, season)])
        episode["shots"][0]["duration"] = 6
        config = PipelineConfig(comfyui={"maximum_duration_seconds": 6})
        self.assertIn("h3_duration_limit", [issue["code"] for issue in check_episode(episode, season, config=config)])
        config.comfyui.maximum_duration_seconds = 12
        episode["shots"][0]["duration"] = 11.5
        self.assertEqual(check_scene(scene, plan["scenes"][0], plan, season, config=config), [])

    def test_dialogue_and_ongoing_actions_have_no_creative_quotas(self):
        episode = episode_fixture("ep01", (1,))
        season = season_fixture([episode])
        season["characters"] = [{"id": name, "wardrobes": [{"id": "outfit"}]} for name in ("speaker", "listener")]
        shot = episode["shots"][0]
        shot.update(duration=2, characters=[{"id": name, "wardrobe_id": "outfit"} for name in ("speaker", "listener")], dialogue=[{
            "speaker_id": "speaker", "voiceover": False, "delivery_en": "Natural measured Mandarin.",
            "text_zh": "我们已经核对了所有资料，明天上午一起去办公室确认最后的合同。",
        }, {"speaker_id": "listener", "voiceover": False, "delivery_en": "A quick reply.", "text_zh": "OK, 2 > 1."}],
            acceptance_en=[], action_complete=False, action_end_zh="手伸到一半", visual_en='The sign reads “合同”.')
        self.assertEqual(check_long_season([episode], season), [])
        self.assertEqual(check_episode(episode, season), [])
        shot["dialogue"][1]["speaker_id"] = "missing"
        self.assertIn("unknown_speaker", [issue["code"] for issue in check_episode(episode, season)])

    def test_variable_scene_counts_survive_assembly_export_and_image_planning(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "novel.txt"
            source.write_text("测试原文", encoding="utf-8")
            client = ScriptClient(scene_shot_counts=(4, 1))
            result = asyncio.run(run_long(source, root / "run", client, episode_count=1))
            self.assertEqual(result["status"], "text_ready")
            episode = json.loads((root / "run/drafts/ep01.json").read_text())
            self.assertEqual([shot["id"] for shot in episode["shots"]], [f"ep01_s{i:03}" for i in range(1, 7)])
            self.assertEqual(episode["shots"][0]["duration"], 7.5)
            self.assertEqual(episode["shots"][0]["story_events"], opening_fixture("ep01")["events"])
            self.assertNotIn("beat_zh", episode["shots"][0])
            self.assertEqual(json.loads((root / "run/quality.json").read_text())["llm_review"], "skipped")
            self.assertEqual(len(client.calls), 5)
            self.assertEqual(client.payloads["ep01_plan_v0"]["opening"], opening_fixture("ep01"))
            opening_payload = client.payloads["ep01_opening_v0"]
            self.assertNotIn("season", opening_payload)
            self.assertNotIn("source_paragraphs", opening_payload)
            self.assertEqual(opening_payload["source_excerpt"], [{"id": 1, "text": "测试原文"}])
            self.assertNotIn("season", client.payloads["ep01_plan_v0"])
            self.assertNotIn("source_text", client.payloads["ep01_plan_v0"])
            scene_payload = client.payloads["ep01_ep01_scene01_v0"]
            self.assertNotIn("episode_plan", scene_payload)
            self.assertNotIn("source_excerpt", scene_payload)
            self.assertNotIn("source_paragraphs", scene_payload)
            self.assertEqual([shot["scene_anchor_shot_id"] for shot in episode["shots"]], ["ep01_s005"] * 5 + ["ep01_s006"])
            plan = json.loads((root / "run/assembled_plans/ep01.json").read_text())
            self.assertEqual([(s["first_shot_number"], s["last_shot_number"]) for s in plan["scenes"]], [(1, 5), (6, 6)])
            body = json.loads((root / "run/plans/ep01.json").read_text())
            self.assertFalse(any(event["id"].startswith("opening_") for event in body["scenes"][0]["events"]))
            image_plan = compile_plan(root / "run/delivery", ImageConfig())
            frames = [task for task in image_plan.tasks if task.asset_id.startswith("first-frame-")]
            self.assertEqual(len(frames), 6)
            anchor = "first-frame-ep01-ep01_s005"
            self.assertIn(anchor, next(task for task in frames if task.asset_id.endswith("s001")).reference_ids)
            self.assertNotIn(anchor, next(task for task in frames if task.asset_id == anchor).reference_ids)

            client.calls.clear()
            asyncio.run(run_long(source, root / "run", client, episode_count=1))
            self.assertEqual(client.calls, [])

    def test_report_mode_runs_each_review_once_without_rewriting(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "novel.txt"
            source.write_text("测试原文", encoding="utf-8")
            client = ScriptClient()
            result = asyncio.run(run_long(source, root / "run", client, episode_count=1,
                                         episode_minutes=1, long_review="report"))
            self.assertEqual(result["status"], "needs_text_revision")
            self.assertTrue((root / "run/delivery/episodes/ep01/package.json").exists())
            self.assertEqual([name for name, _ in client.calls], [
                "long_season", "ep01_opening_v0", "ep01_plan_v0", "ep01_ep01_scene01_v0", "ep01_ep01_scene02_v0",
                "ep01_review_0", "season_review_0",
            ])
            evidence = client.payloads["season_review_0"]["episodes"][0]["shots"][0]
            self.assertIn("story_events", evidence)
            self.assertNotIn("first_frame_prompt_en", evidence)
            client.calls.clear()
            asyncio.run(run_long(source, root / "run", client, episode_count=1,
                                 episode_minutes=1, long_review="report"))
            self.assertEqual(client.calls, [])
            (root / "run/reviews/ep01_0.json").unlink()
            asyncio.run(run_long(source, root / "run", client, episode_count=1,
                                 episode_minutes=1, long_review="report"))
            self.assertEqual([name for name, _ in client.calls], ["ep01_review_0"])

    def test_applied_prompt_examples_connect_to_images_and_video_with_music_and_voiceover(self):
        prompt_root = Path(__file__).resolve().parents[1] / "prompt/script"
        examples = []
        for name in ("season_plan", "episode_opening", "episode_plan", "scene_write"):
            content = (prompt_root / f"scriptpipe_long_{name}_zh.txt").read_text()
            examples.append(json.loads(re.search(r"```json\s*\n(.*?)\n```", content, re.S).group(1)))
        season, opening, body, scene = examples
        self.assertEqual(check_opening(opening, season, season["episodes"][0]), [])
        self.assertEqual(check_long_plan(body, season, season["episodes"][0], opening=opening), [])
        # The same voiceover flag must survive event resolution and H3 compilation.
        opening["events"][1]["voiceover"] = True
        plan = merge_opening(body, opening, [5, 9.4])
        scene["shots"][0]["dialogue"] = [{"text_zh": "P3 should not replace the formal dialogue."}]
        resolved = resolve_scene(scene, plan["scenes"][0], language="Chinese")
        self.assertEqual(resolved["shots"][0]["dialogue"][0]["text_zh"], "签了。钱今天就到。")
        self.assertEqual(check_scene(resolved, plan["scenes"][0], plan, season), [])
        invalid = copy.deepcopy(scene)
        invalid["shots"][0]["event_refs"].reverse()
        with self.assertRaisesRegex(ValueError, "original order"):
            resolve_scene(invalid, plan["scenes"][0], language="Chinese")
        for split in (True, False):
            invalid = copy.deepcopy(scene)
            if split:
                invalid["shots"][1]["event_refs"].insert(0, invalid["shots"][0]["event_refs"].pop())
            else:
                invalid["shots"][0]["event_refs"].append(invalid["shots"][1]["event_refs"].pop(0))
                invalid["shots"].pop(1)
            with self.assertRaisesRegex(ValueError, "one complete clip"):
                resolve_scene(invalid, plan["scenes"][0], language="Chinese")
        for duration in (4, 9.5):
            invalid = copy.deepcopy(scene)
            invalid["shots"][0]["duration"] = duration
            with self.assertRaisesRegex(ValueError, "opening shot duration"):
                resolve_scene(invalid, plan["scenes"][0], language="Chinese")

        class ExampleClient(ScriptClient):
            async def complete(self, name, system, payload, **kwargs):
                if name == "long_season":
                    return copy.deepcopy(season)
                if name == "ep01_opening_v0":
                    return copy.deepcopy(opening)
                if name == "ep01_plan_v0":
                    return copy.deepcopy(body)
                if name == "ep01_ep01_scene01_v0":
                    return copy.deepcopy(scene)
                raise AssertionError(f"Unexpected model call: {name}")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "novel.txt"
            source.write_text("讨薪。\n辞退威胁。\n录音。", encoding="utf-8")
            production = root / "production.yaml"
            production.write_text("generator: comfyui\n", encoding="utf-8")
            result = asyncio.run(run_long(source, root / "run", ExampleClient(), episode_count=1,
                                         production_config=production))
            self.assertEqual(result["status"], "text_ready")
            delivery = root / "handoff"
            (root / "run/delivery").rename(delivery)
            # Downstream stages must work with only the delivered package, without authoring caches.
            shutil.rmtree(root / "run")
            storyboard = json.loads((delivery / "episodes/ep01/storyboard.json").read_text())
            self.assertEqual(storyboard["shots"][0]["story_events"], opening["events"])
            self.assertEqual([event for shot in storyboard["shots"] for event in shot["story_events"]],
                             plan["scenes"][0]["events"])
            env = root / "test.env"
            env.write_text("SCRIPT_HANDOFF_TEST_KEY=local-test-key\n")
            image_config = ImageConfig.model_validate({"api": {
                "env_file": str(env), "key_name": "SCRIPT_HANDOFF_TEST_KEY",
                "base_url": "http://127.0.0.1:1", "request_timeout_seconds": 1,
            }, "scheduler": {"max_attempts": 1}})
            image_plan = compile_plan(delivery, image_config)
            frames = [task for task in image_plan.tasks if task.asset_id.startswith("first-frame-")]
            self.assertEqual(len(frames), 4)
            self.assertIn("identity-zhou_mei", frames[0].reference_ids)
            self.assertIn("character-zhou_mei-blue_work_uniform", frames[0].reference_ids)
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
            expected = [event["text_zh"] for event in plan["scenes"][0]["events"] if "text_zh" in event]
            self.assertEqual([line["text"] for line in extract_dialogue(package.shots)], expected)
            self.assertEqual(package.shots[0].duration, 9.0)
            self.assertEqual([line["text"] for line in extract_dialogue(package.shots[:1])],
                             [event["text_zh"] for event in opening["events"] if "text_zh" in event])
            self.assertIn("says in an off-screen voiceover", package.shots[0].prompt)
            self.assertIn("lips remain closed", package.shots[0].prompt)
            for raw, shot in zip(scene["shots"], package.shots):
                self.assertIn("non_diegetic_music: " + raw["non_diegetic_music_en"], shot.prompt)
                self.assertEqual(sum(asset.role == "first_frame" for asset in shot.asset_bindings), 1)
                self.assertTrue(all(asset.path.is_file() for asset in shot.asset_bindings))
            script = package.script.read_text()
            first_shot_script = script.split(f"### {storyboard['shots'][1]['id']}", 1)[0]
            for event in opening["events"]:
                text = event["action_zh"] if "action_zh" in event else event["text_zh"]
                self.assertIn(text, first_shot_script)
                self.assertEqual(script.count(text), 1)
            self.assertNotIn("P3 should not replace", script)

    def test_openings_can_be_inspected_and_resumed_for_every_episode(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "novel.txt"
            source.write_text("测试原文", encoding="utf-8")
            client = ScriptClient()
            result = asyncio.run(run_long(source, root / "run", client, episode_count=2, stop_after="openings"))
            self.assertEqual(result["status"], "openings_complete")
            self.assertEqual([name for name, _ in client.calls], ["long_season", "ep01_opening_v0", "ep02_opening_v0"])
            self.assertFalse((root / "run/plans").exists())
            for episode_id in ("ep01", "ep02"):
                self.assertEqual(json.loads((root / f"run/openings/{episode_id}.json").read_text()),
                                 opening_fixture(episode_id))
            client.calls.clear()
            result = asyncio.run(run_long(source, root / "run", client, episode_count=2))
            self.assertEqual(result["status"], "text_ready")
            self.assertFalse(any("opening" in name for name, _ in client.calls))
            for episode_id in ("ep01", "ep02"):
                episode = json.loads((root / f"run/drafts/{episode_id}.json").read_text())
                self.assertEqual(episode["shots"][0]["story_events"], opening_fixture(episode_id)["events"])

    def test_body_can_start_in_a_new_scene_without_rewriting_the_opening(self):
        class NewSceneClient(ScriptClient):
            async def complete(self, name, system, payload, **kwargs):
                result = await super().complete(name, system, payload, **kwargs)
                if name == "ep01_plan_v0":
                    result["scenes"] = result["scenes"][1:]
                    result["scenes"][0]["time_of_day"] = "night"
                return result

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "novel.txt"
            source.write_text("测试原文", encoding="utf-8")
            client = NewSceneClient()
            result = asyncio.run(run_long(source, root / "run", client, episode_count=1))
            self.assertEqual(result["status"], "text_ready")
            episode = json.loads((root / "run/drafts/ep01.json").read_text())
            self.assertEqual([shot["scene_id"] for shot in episode["shots"]], ["ep01_scene01"] + ["ep01_scene02"] * 3)
            self.assertEqual(episode["shots"][0]["time_of_day"], "day")
            self.assertEqual(episode["shots"][1]["time_of_day"], "night")
            self.assertEqual(episode["shots"][0]["scene_anchor_shot_id"], "ep01_s001")

        opening = opening_fixture("ep01")
        season = season_fixture([{"id": "ep01"}])
        body = plan_fixture(episode_fixture("ep01"))
        body["scenes"][0]["events"][0] = {"id": "opening_ev001", "action_zh": "篡改开场。"}
        self.assertIn("opening_event_rewritten", [issue["code"] for issue in
                                                 check_long_plan(body, season, season["episodes"][0], opening=opening)])
        body = plan_fixture(episode_fixture("ep01"))
        body["scenes"][0]["time_of_day"] = "night"
        self.assertIn("opening_scene_changed", [issue["code"] for issue in
                                               check_long_plan(body, season, season["episodes"][0], opening=opening)])


if __name__ == "__main__":
    unittest.main()
