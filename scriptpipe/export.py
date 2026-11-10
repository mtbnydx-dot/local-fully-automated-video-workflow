"""Compile structured writing into text-only videopipe episode packages."""

import json
import re
from pathlib import Path

import yaml

from videopipe.inputs import load_config
from videopipe.models import PipelineConfig, ScriptConfig

_PROMPT = Path(__file__).resolve().parent.parent / "prompt" / "script" / "scriptpipe_export_h3_i2va.txt"
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _text(value: object) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)


def _identifier(value: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError(f"Expected an ASCII identifier for an asset or episode path: {value!r}")
    return value


def _asset_id(kind: str, *identifiers: str) -> str:
    return "-".join([kind, *(_identifier(value) for value in identifiers)])


def _shared_slots(season: dict) -> dict[str, dict]:
    slots = {}
    style = season.get("render_style_en", season["style_en"]).strip()
    for character in season["characters"]:
        identity_id = _asset_id("identity", character["id"])
        slots[identity_id] = {
            "asset_id": identity_id,
            "path": f"assets/review/characters/{identity_id}.png",
            "purpose": "character_identity",
            "character_id": character["id"],
            "prompt_en": "\n".join((style, character["appearance_en"])),
            "consistency_source": {"character_id": character["id"]},
            "status": "pending_image",
        }
        for wardrobe in character["wardrobes"]:
            asset_id = _asset_id("character", character["id"], wardrobe["id"])
            slots[asset_id] = {
                "asset_id": asset_id,
                "path": f"assets/review/characters/{asset_id}.png",
                "purpose": "character_identity_and_wardrobe",
                "character_id": character["id"],
                "wardrobe_id": wardrobe["id"],
                "wardrobe_description_en": wardrobe["description_en"],
                "reference_asset_ids": [identity_id],
                "prompt_en": "\n".join((style, wardrobe["description_en"])),
                "consistency_source": {"character_id": character["id"], "wardrobe_id": wardrobe["id"]},
                "status": "pending_image",
            }
    for kind, plural in (("location", "locations"), ("prop", "props")):
        for item in season.get(plural, []):
            asset_id = _asset_id(kind, item["id"])
            slots[asset_id] = {
                "asset_id": asset_id,
                "path": f"assets/review/{plural}/{asset_id}.png",
                "purpose": f"{kind}_continuity_reference",
                f"{kind}_id": item["id"],
                "prompt_en": f"{style}\n{item['description_en']}",
                "consistency_source": {f"{kind}_id": item["id"]},
                "status": "pending_image",
            }
            if kind == "prop" and item.get("reference_prop_ids"):
                slots[asset_id]["reference_asset_ids"] = [
                    _asset_id("prop", prop_id) for prop_id in item["reference_prop_ids"]
                ]
    return slots


def _shot_references(shot: dict) -> list[str]:
    references = [
        (member["id"], asset_id)
        for member in shot["characters"]
        for asset_id in (_asset_id("identity", member["id"]),
                         _asset_id("character", member["id"], member["wardrobe_id"]))
    ]
    references.append((shot["location_id"], _asset_id("location", shot["location_id"])))
    references.extend((prop_id, _asset_id("prop", prop_id)) for prop_id in shot.get("prop_ids", []))
    priority = {entity_id: index for index, entity_id in enumerate(shot.get("reference_priority", []))}
    references.sort(key=lambda item: priority.get(item[0], len(priority)))
    return list(dict.fromkeys(asset_id for _, asset_id in references))


def _compile_prompt(shot: dict, season: dict, template: str, config: ScriptConfig) -> str:
    characters = {item["id"]: item for item in season["characters"]}
    speaker_labels = {item["id"]: f"S{index}" for index, item in enumerate(season["characters"], start=1)}
    speaking = {line["speaker_id"] for line in shot.get("dialogue", [])}
    subject_lines = []
    for member in shot["characters"]:
        character = characters[member["id"]]
        wardrobe = next(item for item in character["wardrobes"] if item["id"] == member["wardrobe_id"])
        label = f" ({speaker_labels[member['id']]})" if member["id"] in speaking else ""
        subject_lines.append(f"{member['id']}{label}, wearing {wardrobe['description_en']}")
    dialogue_lines = []
    for turn, line in enumerate(shot.get("dialogue", []), 1):
        character = characters[line["speaker_id"]]
        speaker = speaker_labels[line["speaker_id"]]
        identity = f"{character['id']}, {character['voice_en']}, {line['delivery_en']} ({speaker})"
        text = re.sub(r"</?(?:d|scenetrans|cutoff)>", "", line["text_zh"], flags=re.IGNORECASE)
        language = line.get("language") or config.language
        if line.get("voiceover") is True:
            dialogue_lines.append(
                f"Turn {turn}: {identity} says in an off-screen voiceover: <d>[{language}]{text}</d> "
                f"If visible, {character['id']}'s lips remain closed during this voiceover turn."
            )
        else:
            dialogue_lines.append(
                f"Turn {turn}: {identity} says: <d>[{language}]{text}</d> with natural synchronized lip movement during this turn."
            )
    if dialogue_lines:
        dialogue_lines.insert(0, "Perform the following dialogue turns in order, with the timing and interactions described in the scene.")
    return template.format(
        style=season.get("render_style_en", season["style_en"]).strip(),
        subjects="\n".join(subject_lines) or "The visual description determines the composition and background cast.",
        visual=shot["visual_en"].strip(),
        camera=shot["camera_en"].strip(),
        dialogue="\n".join(dialogue_lines) or "No speech.",
        soundscape=shot["soundscape_en"].strip(),
        music=shot.get("non_diegetic_music_en", config.non_diegetic_music),
        on_screen_text=config.on_screen_text,
    ).strip()


def _episode_script(episode: dict, season: dict) -> str:
    names = {item["id"]: item["name"] for item in season["characters"]}
    lines = [f"# {episode['title']}", "", episode.get("synopsis", ""), "", "## 本集开始状态", "", _text(episode.get("start_state", "")), "", "## 分镜剧本", ""]
    elapsed = 0.0
    for shot in episode["shots"]:
        cast = "、".join(f"{names[member['id']]}（{member['wardrobe_id']}）" for member in shot["characters"]) or "无人"
        end = elapsed + shot["duration"]
        lines.extend([
            f"### {shot['id']} · {elapsed:.3f}–{end:.3f} 秒",
            "", f"场景：{shot['scene_id']} / {shot['location_id']} / {shot['time_of_day']}；出场：{cast}",
            "",
        ])
        if "story_events" in shot:
            for event in shot["story_events"]:
                if "action_zh" in event:
                    lines.extend([event["action_zh"], ""])
                else:
                    mode = "画外音" if event["voiceover"] else "对白"
                    lines.extend([f"{names[event['speaker_id']]}（{mode}）：{event['text_zh']}", ""])
        else:
            lines.extend([f"剧情：{shot['beat_zh']}", "", f"动作开始：{shot['action_start_zh']}", "",
                          f"动作结束：{shot['action_end_zh']}", ""])
            for dialogue in shot.get("dialogue", []):
                mode = "画外音" if dialogue.get("voiceover") is True else "对白"
                lines.extend([f"{names[dialogue['speaker_id']]}（{mode}）：{dialogue['text_zh']}", ""])
            if not shot.get("dialogue"):
                lines.extend(["对白：无。", ""])
            lines.extend([f"切镜理由：{shot['cut_reason_zh']}", ""])
        elapsed = end
    lines.extend(["## 本集结束状态", "", _text(episode.get("end_state", "")), ""])
    return "\n".join(lines)


def _season_bible(season: dict) -> str:
    lines = [f"# {season['title']} · 整季设定", "", season.get("logline", ""), "", "## 统一视觉风格", "", season["style_en"], "", "## 固定人物与服装", ""]
    for index, character in enumerate(season["characters"], start=1):
        lines.extend([f"### {character['name']} · {character['id']} · S{index}", "", character["appearance_en"], "", f"声音目标：{character['voice_en']}", ""])
        if character.get("dramatic_profile_zh"):
            lines.extend([f"人物与说话方式：{character['dramatic_profile_zh']}", ""])
        for wardrobe in character["wardrobes"]:
            lines.extend([f"- {wardrobe['id']}：{wardrobe['description_en']}", ""])
    for title, key in (("固定场景", "locations"), ("关键道具", "props")):
        lines.extend([f"## {title}", ""])
        for item in season.get(key, []):
            lines.extend([f"### {item['name']} · {item['id']}", "", item["description_en"], ""])
    lines.extend(["## 分集与连续性", ""])
    for episode in season["episodes"]:
        lines.extend([f"### {episode['id']} · {episode['title']}", "", f"开场钩子：{episode.get('hook', '')}", "", _text(episode.get("summary", "")), "", f"结尾：{episode.get('cliffhanger', '')}", "", f"进入状态：{_text(episode.get('start_state', ''))}", "", f"离开状态：{_text(episode.get('end_state', ''))}", ""])
    return "\n".join(lines)


def export_season(season: dict, episodes: list[dict], out_dir: Path, config_path: Path | PipelineConfig) -> dict:
    """Write packages with explicit missing image bindings; return delivery counts.

    No placeholder image is fabricated. package.json matches ScriptPackage, but
    videopipe cannot load it until every path listed in image_slots.json exists.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    template = _PROMPT.read_text(encoding="utf-8")
    production = config_path if isinstance(config_path, PipelineConfig) else load_config(config_path)
    config = production.model_dump(mode="json")
    media = production.media
    _write_json(out_dir / "season.json", season)
    (out_dir / "season_bible.md").write_text(_season_bible(season), encoding="utf-8")
    shared_slots = _shared_slots(season)
    for slot in shared_slots.values():
        (out_dir / slot["path"]).parent.mkdir(parents=True, exist_ok=True)

    overview = {
        "title": season["title"], "status": "text_complete_images_pending", "render_ready": False,
        "episode_count": len(episodes), "shot_count": 0, "planned_duration_seconds": 0.0,
        "shared_image_slot_count": len(shared_slots), "image_slot_count": len(shared_slots),
        "episodes": [],
    }
    all_first_frames = []
    scripts = [f"# {season['title']} · 全季剧本", "", season.get("logline", ""), ""]
    for episode_index, episode in enumerate(episodes, start=1):
        episode_id = _identifier(episode["id"])
        episode_dir = out_dir / "episodes" / episode_id
        episode_dir.mkdir(parents=True, exist_ok=True)
        package = {"title": episode["title"], "script": "script.md", "shots": []}
        episode_slots: dict[str, dict] = {}
        duration = 0.0
        for shot_index, shot in enumerate(episode["shots"], start=1):
            shot_id = _identifier(shot["id"])
            first_frame_id = _asset_id("first-frame", episode_id, shot_id)
            first_frame_path = f"assets/first_frames/{shot_id}.png"
            references = _shot_references(shot)
            first_frame = {
                "asset_id": first_frame_id, "path": first_frame_path, "purpose": "first_frame",
                "episode_id": episode_id, "shot_id": shot_id,
                "scene_id": shot["scene_id"],
                "location_id": shot["location_id"],
                "time_of_day": shot["time_of_day"],
                "continuity_en": shot.get("continuity_en", ""),
                "scene_anchor_shot_id": shot.get("scene_anchor_shot_id", ""),
                "prompt_en": shot["first_frame_prompt_en"],
                "style_en": season.get("render_style_en", season["style_en"]),
                "reference_asset_ids": references,
                "consistency_source": {
                    "characters": shot["characters"], "location_id": shot["location_id"],
                    "prop_ids": shot.get("prop_ids", []), "time_of_day": shot["time_of_day"],
                },
                "status": "pending_image",
            }
            episode_slots[first_frame_id] = first_frame
            all_first_frames.append({**first_frame, "path": f"episodes/{episode_id}/{first_frame_path}"})
            bindings = [{"asset_id": first_frame_id, "path": first_frame_path, "role": "first_frame", "prompt_ref": "<Picture 1>"}]
            for reference_id in references:
                reference = shared_slots[reference_id]
                episode_slots[reference_id] = {
                    **reference, "purpose": "review_only", "source_asset_id": reference_id,
                    "reference_purpose": reference["purpose"],
                    "source_path": f"../../{reference['path']}",
                }
                bindings.append({"asset_id": reference_id, "path": reference["path"], "role": "review_only", "prompt_ref": ""})
            package["shots"].append({
                "id": shot_id, "prompt": _compile_prompt(shot, season, template, production.script),
                "duration": shot["duration"], "width": media.width, "height": media.height, "fps": media.fps,
                "seed": episode_index * 1000 + shot_index,
                "asset_bindings": bindings, "acceptance": shot.get("acceptance_en", []),
            })
            duration += shot["duration"]
        for slot in episode_slots.values():
            (episode_dir / slot["path"]).parent.mkdir(parents=True, exist_ok=True)
        script = _episode_script(episode, season)
        _write_json(episode_dir / "package.json", package)
        _write_json(episode_dir / "storyboard.json", episode)
        _write_json(episode_dir / "image_slots.json", {"status": "pending_images", "slots": list(episode_slots.values())})
        (episode_dir / "script.md").write_text(script, encoding="utf-8")
        (episode_dir / "production.yaml").write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8")
        scripts.extend([script, "---", ""])
        overview["shot_count"] += len(episode["shots"])
        overview["planned_duration_seconds"] += duration
        overview["image_slot_count"] += len(episode["shots"])
        overview["episodes"].append({
            "id": episode_id, "title": episode["title"], "path": f"episodes/{episode_id}",
            "package": f"episodes/{episode_id}/package.json", "shot_count": len(episode["shots"]),
            "planned_duration_seconds": round(duration, 3), "image_slot_count": len(episode_slots),
        })
    overview["planned_duration_seconds"] = round(overview["planned_duration_seconds"], 3)
    _write_json(out_dir / "image_slots.json", {"status": "pending_images", "shared_assets": list(shared_slots.values()), "first_frames": all_first_frames})
    _write_json(out_dir / "overview.json", overview)
    (out_dir / "screenplay.md").write_text("\n".join(scripts), encoding="utf-8")
    readme = f"""# {season['title']}：文字剧本包

本包包含 {overview['episode_count']} 集、{overview['shot_count']} 个分镜，计划时长 {overview['planned_duration_seconds']:.3f} 秒。
仅完成文字与图片槽位；未生成图片、配音或视频。最终文字检查结果见 `quality.json`。

## 阅读顺序

1. `screenplay.md`：全季中文剧情、逐字对白与正式动作。
2. `season_bible.md` / `season.json`：固定人物、服装、声音目标、场景、道具及分集状态。
3. `episodes/<集ID>/script.md`：单集可读剧本。
4. `episodes/<集ID>/storyboard.json`：结构化分镜，包含首帧、动态画面、声音与逐字对白；长链路保留正式事件引用。
5. `episodes/<集ID>/package.json`：当前 videopipe 格式，含英文 H3 prompt 与中文对白。
6. `image_slots.json`：全季共享参考槽位和逐镜首帧槽位；单集同名文件说明本集目标路径。

长链路的开场已作为每集第一镜合入上述剧本、分镜、镜头包和图片槽位。图片与视频阶段直接读取本交付目录；`openings/` 是 scriptpipe 运行目录中的内部创作缓存。

## 补图后交接

- 全季有 {overview['shared_image_slot_count']} 个共享参考槽位和 {overview['shot_count']} 个首帧槽位，按 `image_slots.json` 填入实际图片。
- 先按季设定生成固定人物/服装、场景、道具参考，同一人物的不同服装沿用同一身份。
- 使用 `imagepipe run <本包目录> --config configs/imagepipe.yaml`，按每个首帧的 `reference_asset_ids` 和英文说明制作开场构图；图片尺寸由生图配置决定。
- 单集 `review_only` 槽位的 `source_path` 指向全季参考，补图时复制到槽位的本集 `path`；每集包由此可独立运行。
- 首帧呈现镜头开始时的实际场面，镜头时长由对白、动作和节奏决定。
- 图片齐备后可用 `videopipe run-season <本包目录> --output <运行目录>` 逐集生成视频；各集读取自身 `production.yaml`。
- 视频画布为 {media.width}×{media.height}、{media.fps}fps；服务、步数、超分、ASR 和批准设置由导出时选定的配置保存在各集 `production.yaml` 中。

声音描述属于制作目标，实际对白和口型表现由成片提供依据。
"""
    (out_dir / "README.md").write_text(readme, encoding="utf-8")
    return overview
