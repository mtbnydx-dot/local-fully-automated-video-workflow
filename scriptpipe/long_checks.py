"""Deterministic checks for scene-by-scene long-form script production."""

from .checks import check_episode


def _issue(issues, code, message, episode_id="", shot_id="", suggested_fix="", severity="error"):
    issues.append({
        "severity": severity, "code": code, "message": message,
        "episode_id": episode_id, "shot_id": shot_id, "suggested_fix": suggested_fix,
    })


def _references(scene, season, episode_id, issues):
    """Check planned references before generating the full scene."""
    scene_id = scene.get("id", "")
    characters = {x["id"]: x for x in season.get("characters", []) if isinstance(x, dict) and isinstance(x.get("id"), str)}
    locations = {x.get("id") for x in season.get("locations", []) if isinstance(x, dict) and isinstance(x.get("id"), str)}
    props = {x.get("id") for x in season.get("props", []) if isinstance(x, dict) and isinstance(x.get("id"), str)}
    location_id = scene.get("location_id")
    if not isinstance(location_id, str) or location_id not in locations:
        _issue(issues, "unknown_location", f"Scene {scene_id}: unknown location_id {location_id!r}.", episode_id,
               suggested_fix="Use a location id registered in season.locations.")
    cast = scene.get("characters")
    if not isinstance(cast, list):
        _issue(issues, "cast_type", f"Scene {scene_id}: characters must be a list.", episode_id,
               suggested_fix="Use a list of {id, wardrobe_id} objects.")
        cast = []
    for member in cast:
        if not isinstance(member, dict):
            _issue(issues, "cast_type", f"Scene {scene_id}: each character must be an object.", episode_id,
                   suggested_fix="Use {id, wardrobe_id} for each character.")
            continue
        character_id = member.get("id")
        character = characters.get(character_id) if isinstance(character_id, str) else None
        if character is None:
            _issue(issues, "unknown_character", f"Scene {scene_id}: unknown character {character_id!r}.", episode_id,
                   suggested_fix="Use a character id registered in season.characters.")
            continue
        wardrobes = [x.get("id") for x in character.get("wardrobes", []) if isinstance(x, dict)]
        if member.get("wardrobe_id") not in wardrobes:
            _issue(issues, "unknown_wardrobe", f"Scene {scene_id}: unknown wardrobe {member.get('wardrobe_id')!r} for {character_id}.", episode_id,
                   suggested_fix="Use a wardrobe registered under this character.")
    prop_ids = scene.get("prop_ids")
    if not isinstance(prop_ids, list):
        _issue(issues, "props_type", f"Scene {scene_id}: prop_ids must be a list.", episode_id,
               suggested_fix="Use a list of registered prop ids, or an empty list.")
    else:
        for prop_id in prop_ids:
            if not isinstance(prop_id, str) or prop_id not in props:
                _issue(issues, "unknown_prop", f"Scene {scene_id}: unknown prop_id {prop_id!r}.", episode_id,
                       suggested_fix="Use a prop id registered in season.props.")


def _episode_content(episode, season, config):
    """Attach episode context to the shared field and reference checks."""
    episode_id = episode.get("id", "")
    try:
        issues = check_episode(episode, season, config=config)
    except (TypeError, AttributeError) as exc:
        return [{
            "severity": "error", "code": "shot_structure", "episode_id": episode_id,
            "shot_id": "", "message": f"Episode content has malformed fields: {exc}.",
            "suggested_fix": "Use string ids, lists for characters/props/dialogue, and objects for shots and cast members.",
        }]
    return [{
        **issue, "episode_id": episode_id,
        "suggested_fix": issue.get("suggested_fix", "Correct the reported shot field using the canonical season references and the planned action."),
    } for issue in issues]


def _shot_layout(shots, episode_id, first_number, issues, scene_id=None):
    for offset, shot in enumerate(shots):
        if not isinstance(shot, dict):
            continue  # check_episode reports the malformed shot.
        shot_id = shot.get("id", "")
        expected_id = f"{episode_id}_s{first_number + offset:03d}" if first_number is not None else None
        if expected_id is not None and shot_id != expected_id:
            _issue(issues, "shot_number", f"Expected shot id {expected_id}, got {shot_id!r}.", episode_id, str(shot_id),
                   f"Set this shot id to {expected_id}; preserve chronological list order.")
        if scene_id is not None and shot.get("scene_id") != scene_id:
            _issue(issues, "shot_scene_id", f"Shot scene_id must be {scene_id!r}.", episode_id, str(shot_id),
                   "Use the enclosing scene_plan.id for every shot in this scene.")


def check_opening(opening: dict, season: dict, episode_plan: dict) -> list[dict]:
    """Validate opening drama with the same event and asset contract as the body."""
    if not isinstance(opening, dict):
        issues = []
        _issue(issues, "opening_type", "Return an opening object with episode_id and events.", episode_plan["id"])
        return issues
    scene = {**opening, "id": f"{episode_plan['id']}_scene01"}
    issues = check_long_plan({"id": opening.get("episode_id"), "scenes": [scene]}, season, episode_plan)
    if not issues and any(not event["id"].startswith("opening_ev") for event in opening["events"]):
        _issue(issues, "opening_event_id", "Use opening_ev001, opening_ev002, etc. for opening events.", episode_plan["id"])
    return issues


def check_long_plan(plan: dict, season: dict, episode_plan: dict, *, opening: dict | None = None) -> list[dict]:
    """Check formal drama at its authoring boundary, including an optional continuation."""
    issues = []
    episode_id = episode_plan["id"]
    if not isinstance(plan, dict):
        _issue(issues, "plan_type", "Return an object with id and scenes.", episode_id)
        return issues
    if plan.get("id") != episode_id:
        _issue(issues, "plan_episode_id", f"Plan id must be {episode_id!r}.", episode_id)
    scenes = plan.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        _issue(issues, "scenes_type", "scenes must be a nonempty list.", episode_id)
        return issues
    characters = {item["id"] for item in season["characters"]}
    seen = set()
    for scene in scenes:
        if not isinstance(scene, dict):
            _issue(issues, "scene_type", "Each scene must be an object.", episode_id)
            continue
        scene_id = scene.get("id")
        if not isinstance(scene_id, str) or not scene_id.strip():
            _issue(issues, "scene_id", "Each scene needs a nonempty id.", episode_id)
        elif scene_id in seen:
            _issue(issues, "duplicate_scene_id", f"Scene {scene_id!r} is duplicated.", episode_id)
        else:
            seen.add(scene_id)
        if not isinstance(scene.get("time_of_day"), str) or not scene["time_of_day"].strip():
            _issue(issues, "time_of_day", f"Scene {scene_id}: supply time_of_day.", episode_id)
        _references(scene, season, episode_id, issues)
        cast = scene.get("characters", [])
        visible = {member["id"] for member in cast
                   if isinstance(member, dict) and isinstance(member.get("id"), str)} if isinstance(cast, list) else set()
        events = scene.get("events")
        if not isinstance(events, list) or not events:
            _issue(issues, "scene_events", f"Scene {scene_id}: events must be a nonempty list.", episode_id)
            continue
        event_ids = set()
        for event in events:
            if not isinstance(event, dict):
                _issue(issues, "event_type", f"Scene {scene_id}: each event must be an object.", episode_id)
                continue
            event_id = event.get("id")
            if not isinstance(event_id, str) or not event_id.strip() or event_id in event_ids:
                _issue(issues, "event_id", f"Scene {scene_id}: event IDs must be nonempty and unique.", episode_id)
            else:
                event_ids.add(event_id)
                if opening is not None and event_id.startswith("opening_"):
                    _issue(issues, "opening_event_rewritten", "Write only the continuation using ev001, ev002, etc.; opening events are inserted by the program.", episode_id)
            action, dialogue = "action_zh" in event, "text_zh" in event
            if action == dialogue:
                _issue(issues, "event_content", f"Event {event_id}: supply either action_zh or dialogue text_zh.", episode_id)
                continue
            field = "action_zh" if action else "text_zh"
            if not isinstance(event[field], str) or not event[field].strip():
                _issue(issues, "event_content", f"Event {event_id}: {field} must contain the formal text.", episode_id)
            if dialogue:
                speaker = event.get("speaker_id")
                if not isinstance(speaker, str) or speaker not in characters:
                    _issue(issues, "unknown_speaker", f"Event {event_id}: use a registered speaker_id.", episode_id)
                if not isinstance(event.get("voiceover"), bool):
                    _issue(issues, "voiceover_type", f"Event {event_id}: voiceover must be a boolean.", episode_id)
                elif event["voiceover"] is False and isinstance(speaker, str) and speaker not in visible:
                    _issue(issues, "speaker_not_visible", f"Event {event_id}: include the speaking character in this scene's cast.", episode_id)
    if opening is not None and not issues:
        opening_scene_id = f"{episode_id}_scene01"
        for index, scene in enumerate(scenes):
            if scene["id"] != opening_scene_id:
                continue
            if index != 0:
                _issue(issues, "opening_scene_order", f"Continue {opening_scene_id} as the first body scene; use a new id for later scenes.", episode_id)
            for field in ("location_id", "time_of_day"):
                if scene[field] != opening[field]:
                    _issue(issues, "opening_scene_changed", f"The opening scene's {field} is {opening[field]!r}; use scene02 for a new location or time.", episode_id)
            if any(member not in scene["characters"] for member in opening["characters"]):
                _issue(issues, "opening_cast_changed", "Keep the opening's characters and wardrobes in the continued scene; add other cast as needed.", episode_id)
            if not set(opening["prop_ids"]) <= set(scene["prop_ids"]):
                _issue(issues, "opening_props_changed", "Keep the opening's props in the continued scene; add other props as needed.", episode_id)
    return issues


def resolve_scene(scene: dict, scene_plan: dict, *, language: str) -> dict:
    """Resolve P3 references into formal drama and the existing production shot shape."""
    if not isinstance(scene, dict) or not isinstance(scene.get("shots"), list) or not scene["shots"]:
        raise ValueError("Return a scene object with a nonempty shots list")
    events = {event["id"]: event for event in scene_plan["events"]}
    wardrobes = {member["id"]: member["wardrobe_id"] for member in scene_plan["characters"]}
    resolved, event_ids = [], []
    for raw in scene["shots"]:
        if not isinstance(raw, dict):
            raise ValueError("Each shot must be an object")
        refs = raw.get("event_refs")
        if not isinstance(refs, list) or not refs:
            raise ValueError(f"{raw.get('id')}: event_refs must contain the scene events used by this shot")
        cast = raw.get("character_ids")
        if not isinstance(cast, list) or any(not isinstance(cid, str) or cid not in wardrobes for cid in cast):
            raise ValueError(f"{raw.get('id')}: character_ids must reference this scene's visible characters")
        props = raw.get("prop_ids", [])
        if not isinstance(props, list) or any(not isinstance(pid, str) or pid not in scene_plan["prop_ids"] for pid in props):
            raise ValueError(f"{raw.get('id')}: prop_ids must reference this scene's props")
        if "non_diegetic_music_en" not in raw:
            raise ValueError(f"{raw.get('id')}: supply non_diegetic_music_en, using N/A for no score")
        story, dialogue = [], []
        for ref in refs:
            if not isinstance(ref, dict) or not isinstance(ref.get("event_id"), str) or ref["event_id"] not in events:
                raise ValueError(f"{raw.get('id')}: each event_ref must point to an existing scene event")
            event = events[ref["event_id"]]
            event_ids.append(event["id"])
            story.append(event)
            if "text_zh" in event:
                dialogue.append({"speaker_id": event["speaker_id"], "text_zh": event["text_zh"],
                                 "voiceover": event["voiceover"], "language": language,
                                 "delivery_en": ref.get("delivery_en", "")})
        fields = ("id", "event_refs", "reference_priority", "duration", "first_frame_prompt_en",
                  "visual_en", "camera_en", "soundscape_en", "non_diegetic_music_en")
        resolved.append({**{key: raw[key] for key in fields if key in raw}, "prop_ids": props,
                         "scene_id": scene_plan["id"], "location_id": scene_plan["location_id"],
                         "time_of_day": scene_plan["time_of_day"],
                         "characters": [{"id": cid, "wardrobe_id": wardrobes[cid]} for cid in cast],
                         "story_events": story, "dialogue": dialogue})
    if event_ids != [event["id"] for event in scene_plan["events"]]:
        raise ValueError("Across shots, event_refs must use every scene event exactly once in its original order")
    if opening := scene_plan.get("opening"):
        if [event["id"] for event in resolved[0]["story_events"]] != opening["event_ids"]:
            raise ValueError("The first shot must contain exactly opening.event_ids, in order, as one complete clip")
        low, high = opening["duration_range_seconds"]
        duration = resolved[0].get("duration")
        if not isinstance(duration, (int, float)) or not low <= duration <= high:
            raise ValueError(f"The opening shot duration must be within {low:g}–{high:g} seconds")
    return {**scene, "shots": resolved}


def check_scene(scene: dict, scene_plan: dict, episode_plan: dict, season: dict, *, config=None) -> list[dict]:
    """Check one generated scene against its plan and the existing shot contract."""
    issues = []
    episode_id = episode_plan.get("id", "")
    scene_id = scene_plan.get("id", "")
    if not isinstance(scene, dict):
        _issue(issues, "scene_type", "Generated scene must be an object.", episode_id,
               suggested_fix="Return {episode_id, scene_id, shots}.")
        return issues
    if scene.get("episode_id") != episode_id:
        _issue(issues, "scene_episode_id", f"Scene episode_id must be {episode_id!r}.", episode_id,
               suggested_fix="Use the enclosing episode_plan.id.")
    if scene.get("scene_id") != scene_id:
        _issue(issues, "scene_id", f"Scene id must be {scene_id!r}.", episode_id,
               suggested_fix="Copy scene_plan.id to scene_id.")
    shots = scene.get("shots")
    if not isinstance(shots, list):
        _issue(issues, "shots_type", "Scene shots must be a list.", episode_id,
               suggested_fix="Return the scene's shot objects in viewing order.")
        return issues
    if scene.get("anchor_shot_id") not in [shot.get("id") for shot in shots if isinstance(shot, dict)]:
        _issue(issues, "scene_anchor", "anchor_shot_id must refer to a shot in this scene.", episode_id,
               suggested_fix="Select one of the returned shots as the spatial reference.")
    episode = {"id": episode_id, "title": episode_plan.get("title", episode_id), "shots": shots}
    issues.extend(_episode_content(episode, season, config))
    _shot_layout(shots, episode_id, None, issues, scene_id)
    return issues


def check_long_season(episodes: list[dict], season: dict, *, config=None) -> list[dict]:
    """Check final episode order, global ids and consecutive shot numbering."""
    issues = []
    if not isinstance(episodes, list):
        _issue(issues, "episodes_type", "Episodes must be a list.", suggested_fix="Supply the completed episodes in season order.")
        return issues
    if not episodes:
        _issue(issues, "season_episode_count", "Season must contain at least one episode.",
               suggested_fix="Deliver the completed episodes from the season plan.")
    expected_ids = [e.get("id") for e in season.get("episodes", []) if isinstance(e, dict)]
    actual_ids = [e.get("id") if isinstance(e, dict) else None for e in episodes]
    if actual_ids != expected_ids:
        _issue(issues, "season_episode_order", f"Episode ids/order {actual_ids!r} do not match the season outline {expected_ids!r}.",
               suggested_fix="Deliver every planned episode exactly once, in season.episodes order.")
    seen_episode_ids, seen_shot_ids, scene_owners = set(), set(), {}
    for episode in episodes:
        if not isinstance(episode, dict):
            _issue(issues, "episode_type", "Each episode must be an object.", suggested_fix="Supply a complete episode object.")
            continue
        episode_id = str(episode.get("id", ""))
        if episode_id in seen_episode_ids:
            _issue(issues, "duplicate_episode_id", f"Episode id {episode_id!r} is duplicated.", episode_id,
                   suggested_fix="Use each planned episode id exactly once.")
        seen_episode_ids.add(episode_id)
        issues.extend(_episode_content(episode, season, config))
        shots = episode.get("shots", [])
        if not isinstance(shots, list):
            continue
        _shot_layout(shots, episode_id, 1, issues)
        for shot in shots:
            if not isinstance(shot, dict):
                continue
            shot_id = str(shot.get("id", ""))
            if shot_id in seen_shot_ids:
                _issue(issues, "duplicate_global_shot_id", f"Shot id {shot_id!r} occurs more than once in the season.", episode_id, shot_id,
                       "Keep every epXX_sNNN id unique across the season.")
            seen_shot_ids.add(shot_id)
            scene_id = shot.get("scene_id")
            if isinstance(scene_id, str):
                owner = scene_owners.setdefault(scene_id, episode_id)
                if owner != episode_id:
                    _issue(issues, "duplicate_global_scene_id", f"Scene {scene_id!r} is also used by {owner}.", episode_id, shot_id,
                           "Use distinct scene ids across episodes; reuse location_id for the same physical set.")
    return issues
