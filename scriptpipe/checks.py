"""Small, deterministic checks for a text-only episode before handoff."""

import math
import re

from videopipe.models import PipelineConfig

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


def check_episode(episode: dict, season: dict, *, config: PipelineConfig | None = None) -> list[dict]:
    """Check fields, references and configured workflow limits."""
    config = config or PipelineConfig()
    issues: list[dict] = []

    def issue(code: str, message: str, shot_id: str = "", severity: str = "error") -> None:
        issues.append({"severity": severity, "shot_id": shot_id, "code": code, "message": message})

    def english(value: object, field: str, shot_id: str) -> None:
        if not isinstance(value, str) or not value.strip():
            issue("missing_english", f"{field} must contain an English description.", shot_id)

    characters = {item["id"]: item for item in season.get("characters", []) if isinstance(item, dict) and "id" in item}
    locations = {item["id"] for item in season.get("locations", []) if isinstance(item, dict) and "id" in item}
    props = {item["id"] for item in season.get("props", []) if isinstance(item, dict) and "id" in item}
    episode_id = episode.get("id", "")
    if not isinstance(episode_id, str) or not _ID.fullmatch(episode_id):
        issue("episode_id", "Episode id must be a nonempty ASCII identifier.")
    if not episode.get("title"):
        issue("episode_title", "Episode title is missing.")
    shots = episode.get("shots")
    if not isinstance(shots, list) or not shots:
        issue("missing_shots", "Episode must contain shots.")
        return issues

    seen: set[str] = set()
    for index, shot in enumerate(shots):
        if not isinstance(shot, dict):
            issue("shot_type", f"Shot {index + 1} is not an object.")
            continue
        shot_id = shot.get("id", "")
        if not isinstance(shot_id, str) or not _ID.fullmatch(shot_id):
            issue("shot_id", "Shot id must be a nonempty ASCII identifier.", str(shot_id))
            shot_id = str(shot_id)
        if shot_id in seen:
            issue("duplicate_shot_id", "Shot id is duplicated in this episode.", shot_id)
        seen.add(shot_id)
        if not shot.get("scene_id"):
            issue("scene_id", "A scene_id is required to track continuous scenes.", shot_id)
        if shot.get("location_id") not in locations:
            issue("unknown_location", f"Unknown location_id: {shot.get('location_id')!r}.", shot_id)
        if not shot.get("time_of_day"):
            issue("time_of_day", "Time of day is missing.", shot_id)

        duration = shot.get("duration")
        valid_duration = isinstance(duration, (int, float)) and not isinstance(duration, bool) and math.isfinite(duration) and duration > 0
        if not valid_duration:
            issue("duration", "Duration must be a positive finite number.", shot_id)
        elif config.generator == "comfyui":
            maximum_duration_seconds = config.comfyui.maximum_duration_seconds
            if duration > maximum_duration_seconds:
                issue("duration_limit", f"Planned duration {duration:g}s exceeds the {maximum_duration_seconds:g}s limit.", shot_id)
            rendered_duration = config.comfyui.frame_count(duration, config.media.fps) / config.media.fps
            if rendered_duration > maximum_duration_seconds:
                issue("h3_duration_limit", f"The workflow rounds {duration:g}s to {rendered_duration:.3f}s; the configured limit is {maximum_duration_seconds:g}s.", shot_id)

        cast = shot.get("characters", [])
        if not isinstance(cast, list):
            issue("cast_type", "characters must be a list.", shot_id)
            cast = []
        cast_ids: set[str] = set()
        for member in cast:
            if not isinstance(member, dict):
                issue("cast_type", "Each character reference must be an object.", shot_id)
                continue
            character_id = member.get("id")
            if character_id in cast_ids:
                issue("duplicate_character", f"Character {character_id!r} occurs twice in the shot cast.", shot_id)
            cast_ids.add(str(character_id))
            character = characters.get(character_id)
            if character is None:
                issue("unknown_character", f"Unknown character: {character_id!r}.", shot_id)
                continue
            wardrobes = {item.get("id") for item in character.get("wardrobes", []) if isinstance(item, dict)}
            if member.get("wardrobe_id") not in wardrobes:
                issue("unknown_wardrobe", f"Unknown wardrobe {member.get('wardrobe_id')!r} for {character_id}.", shot_id)
        prop_ids = shot.get("prop_ids", [])
        if not isinstance(prop_ids, list):
            issue("props_type", "prop_ids must be a list.", shot_id)
        else:
            for prop_id in prop_ids:
                if prop_id not in props:
                    issue("unknown_prop", f"Unknown prop_id: {prop_id!r}.", shot_id)

        for field in ("visual_en", "camera_en", "soundscape_en", "first_frame_prompt_en"):
            english(shot.get(field), field, shot_id)
        if "non_diegetic_music_en" in shot:
            english(shot["non_diegetic_music_en"], "non_diegetic_music_en", shot_id)
        priority = shot.get("reference_priority", [])
        if not isinstance(priority, list) or any(not isinstance(item, str) for item in priority):
            issue("reference_priority_type", "reference_priority must be a list of entity IDs.", shot_id)
        acceptance = shot.get("acceptance_en", [])
        if not isinstance(acceptance, list):
            issue("acceptance", "acceptance_en must be a list of observable requirements, or an empty list.", shot_id)
        else:
            for criterion in acceptance:
                english(criterion, "acceptance_en", shot_id)
        if "story_events" not in shot:
            for field in ("beat_zh", "action_start_zh", "action_end_zh", "cut_reason_zh"):
                if not isinstance(shot.get(field), str) or not shot[field].strip():
                    issue("missing_story_field", f"{field} is missing.", shot_id)
            if not isinstance(shot.get("action_complete"), bool):
                issue("action_complete_type", "action_complete must be a JSON boolean describing the action at the cut.", shot_id)

        dialogue = shot.get("dialogue", [])
        if not isinstance(dialogue, list):
            issue("dialogue_type", "dialogue must be a list.", shot_id)
            dialogue = []
        for line in dialogue:
            if not isinstance(line, dict):
                issue("dialogue_type", "Each dialogue line must be an object.", shot_id)
                continue
            speaker = line.get("speaker_id")
            if not isinstance(line.get("voiceover"), bool):
                issue("voiceover_type", "voiceover must be a JSON boolean.", shot_id)
            if "language" in line and (not isinstance(line["language"], str) or not line["language"].strip()):
                issue("dialogue_language_type", "language must be a language name string.", shot_id)
            if speaker not in characters:
                issue("unknown_speaker", f"Unknown speaker_id: {speaker!r}.", shot_id)
            if line.get("voiceover") is not True and speaker not in cast_ids:
                issue("speaker_not_visible", f"On-screen speaker {speaker!r} is missing from the shot cast.", shot_id)
            english(line.get("delivery_en"), "dialogue.delivery_en", shot_id)
            text = line.get("text_zh", "")
            if not isinstance(text, str) or not text.strip():
                issue("empty_dialogue", "Dialogue text is empty.", shot_id)
                continue
    return issues
