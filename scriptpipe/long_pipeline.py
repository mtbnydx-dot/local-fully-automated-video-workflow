"""Write drama once, design each scene, and compile the image/video handoff."""

from __future__ import annotations

import asyncio
import math
import re
from datetime import datetime, timezone
from pathlib import Path

from videopipe.inputs import load_config

from .export import export_season
from .llm import GLMClient, write_json
from .pipeline import compact_episode, production_brief, prompt, read_json
from .long_checks import check_long_plan, check_long_season, check_opening, check_scene, resolve_scene


async def collect(tasks):
    """Let independent calls save their work even when another call fails."""
    results = await asyncio.gather(*tasks, return_exceptions=True)
    errors = [result for result in results if isinstance(result, BaseException)]
    if errors:
        raise RuntimeError("; ".join(str(error) for error in errors))
    return results


def story_evidence(episode: dict) -> dict:
    """Keep the actual ordered drama, without repeating art direction or dialogue."""
    fields = ("id", "scene_id", "location_id", "story_events")
    return {**{key: value for key, value in episode.items() if key != "shots"},
            "shots": [{key: shot[key] for key in fields} for shot in episode["shots"]]}


async def run_long(source_path: Path, out: Path, client: GLMClient, *,
                   episode_count: int = 8, episode_minutes: float = 5,
                   production_config: Path | None = None, notes_path: Path | None = None,
                   delivery: Path | None = None, stop_after: str | None = None,
                   review_reasoning_effort: str | None = None, long_review: str = "off") -> dict:
    if episode_count < 1:
        raise ValueError("episode_count must be positive")
    if not math.isfinite(episode_minutes) or episode_minutes <= 0:
        raise ValueError("episode_minutes must be positive and finite")
    if long_review not in ("off", "report"):
        raise ValueError("long_review must be off or report")
    review_reasoning_effort = review_reasoning_effort or client.reasoning_effort
    config = load_config(production_config or Path("configs/b200.yaml"))
    out.mkdir(parents=True, exist_ok=True)
    delivery = delivery or out / "delivery"
    brief = {
        **production_brief(config),
        "episode_count": episode_count,
        "target_episode_duration_seconds": episode_minutes * 60,
        "target_season_duration_seconds": episode_count * episode_minutes * 60,
    }
    brief["opening_duration_range_seconds"] = [5, min(10, brief["maximum_requested_duration_seconds"])]
    if brief["opening_duration_range_seconds"][1] < 5:
        raise ValueError("Long-form openings require a workflow that supports a clip of at least 5 seconds")
    state_file = out / "run.json"
    state = {"source": str(source_path.resolve()), "model": client.model,
             "endpoint": client.endpoint, "mode": "long_form", "brief": brief,
             "planning_effort": client.reasoning_effort, "writing_effort": client.reasoning_effort,
             "review_effort": review_reasoning_effort, "long_review": long_review,
             "delivery": str(delivery.resolve()), "status": "running",
             "started_at": datetime.now(timezone.utc).isoformat()}
    if state_file.exists():
        previous = read_json(state_file)
        if previous.get("source") != state["source"] or previous.get("brief") != brief:
            raise ValueError("Use a new output directory for a different source, prompt schema or duration plan")
        state["started_at"] = previous["started_at"]
    write_json(state_file, state)
    original = source_path.read_text(encoding="utf-8")
    source = re.sub(r"\.mw-parser-output[^{}]*\{[^{}]*\}", "", original)
    (out / "source.cleaned.txt").write_text(source, encoding="utf-8")
    paragraphs = [{"id": index, "text": text} for index, text in enumerate(
        (line for line in source.splitlines() if line.strip()), 1)]
    write_json(out / "source.paragraphs.json", paragraphs)
    notes = notes_path.read_text(encoding="utf-8") if notes_path else ""
    write_json(out / "creative_brief.json", brief)

    def pause(stage):
        if stop_after != stage:
            return False
        state.update(status=f"{stage}_complete", stage=stage)
        write_json(state_file, state)
        client.event("stage_complete", stage=stage)
        return True

    async def checked(name, template, payload, destination, validate):
        if destination.exists():
            cached = read_json(destination)
            if not any(issue["severity"] == "error" for issue in validate(cached)):
                return cached
        feedback = []
        candidate = None
        for attempt in range(3):
            data = {**payload}
            if feedback:
                data.update(previous_invalid_result=candidate, required_corrections=feedback)
            candidate = await client.complete(f"{name}_v{attempt}", prompt(template), data)
            issues = validate(candidate)
            write_json(out / "checks" / f"{name}_v{attempt}.json", issues)
            feedback = [issue for issue in issues if issue["severity"] == "error"]
            if not feedback:
                write_json(destination, candidate)
                return candidate
            write_json(out / "rejected" / f"{name}_v{attempt}.json", candidate)
        raise ValueError(f"{name} still has {len(feedback)} concrete structural errors")

    async def reviewed(name, template, payload, destination):
        input_path = out / "review_inputs" / destination.name
        if destination.exists() and input_path.exists() and read_json(input_path) == payload:
            return read_json(destination)
        review = await client.complete(name, prompt(template), payload,
                                       temperature=0.3, reasoning_effort=review_reasoning_effort)
        write_json(destination, review)
        write_json(input_path, payload)
        return review

    try:
        season_path = out / "season.json"
        if season_path.exists():
            season = read_json(season_path)
        else:
            season = await client.complete("long_season", prompt("long_season_plan_zh"), {
                "brief": {key: brief[key] for key in ("episode_count", "target_episode_duration_seconds",
                                                       "target_season_duration_seconds", "dialogue_language")},
                "source_paragraphs": paragraphs, "editor_notes": notes,
            })
            write_json(season_path, season)
        plans = season["episodes"]
        if [item["id"] for item in plans] != [f"ep{i:02}" for i in range(1, episode_count + 1)]:
            raise ValueError("Season must contain exactly the requested ordered episode IDs")
        excerpts = {plan["id"]: source_excerpt(plan, paragraphs) for plan in plans}
        if pause("season"):
            return state

        catalog = asset_catalog(season)

        async def plan_episode(plan):
            opening = await checked(f"{plan['id']}_opening", "long_episode_opening_zh", {
                "episode_plan": plan, "source_excerpt": excerpts[plan["id"]], "asset_catalog": catalog,
                "brief": {key: brief[key] for key in ("opening_duration_range_seconds", "dialogue_language",
                                                       "maximum_requested_duration_seconds")},
                "editor_notes": notes,
            }, out / "openings" / f"{plan['id']}.json",
                lambda candidate: check_opening(candidate, season, plan))
            if stop_after == "openings":
                return
            destination = out / "plans" / f"{plan['id']}.json"
            result = await checked(f"{plan['id']}_plan", "long_episode_plan_zh", {
                "episode_plan": plan, "source_excerpt": excerpts[plan["id"]], "asset_catalog": catalog,
                "opening": opening,
                "brief": {key: brief[key] for key in ("target_episode_duration_seconds", "dialogue_language",
                                                       "maximum_requested_duration_seconds", "opening_duration_range_seconds")},
                "editor_notes": notes,
            }, destination, lambda candidate: check_long_plan(candidate, season, plan, opening=opening))
            result = merge_opening(result, opening, brief["opening_duration_range_seconds"])
            result.update({key: plan[key] for key in ("title", "start_state", "end_state")}, synopsis=plan["summary"])
            return result

        detailed_plans = await collect([plan_episode(plan) for plan in plans])
        if pause("openings"):
            return state
        if pause("plans"):
            return state

        async def write_scene(plan, scene_plan):
            resolved = None

            def validate(candidate):
                nonlocal resolved
                try:
                    resolved = resolve_scene(candidate, scene_plan, language=config.script.language)
                except (ValueError, KeyError, TypeError) as exc:
                    return [{"severity": "error", "code": "scene_event_reference",
                             "episode_id": plan["id"], "shot_id": "", "message": str(exc),
                             "suggested_fix": "Use the scene's event IDs once in order, its registered cast, and the P3 field format."}]
                return check_scene(resolved, scene_plan, plan, season, config=config)

            await checked(f"{plan['id']}_{scene_plan['id']}", "long_scene_write_zh", {
                "episode_id": plan["id"], "scene": scene_plan, "assets": scene_assets(season, scene_plan),
                "brief": {key: brief[key] for key in ("width", "height", "dialogue_language",
                                                       "maximum_requested_duration_seconds",
                                                       "non_diegetic_music", "on_screen_text")},
                "editor_notes": notes,
            }, out / "scenes" / plan["id"] / f"{scene_plan['id']}.json", validate)
            return resolved

        scenes = await collect([write_scene(plan, scene) for plan in detailed_plans for scene in plan["scenes"]])
        by_scene = {(scene["episode_id"], scene["scene_id"]): scene for scene in scenes}
        episodes = []
        for plan in detailed_plans:
            episode = assemble_episode(plan, [by_scene[plan["id"], scene["id"]] for scene in plan["scenes"]])
            sync_scene_plan(episode, plan)
            write_json(out / "drafts" / f"{plan['id']}.json", episode)
            write_json(out / "assembled_plans" / f"{plan['id']}.json", plan)
            episodes.append(episode)
        checks = check_long_season(episodes, season, config=config)
        write_json(out / "checks" / "assembled.json", checks)
        if pause("drafts"):
            return state

        local_reviews, season_review = [], {}
        if long_review == "report":
            async def review_episode(episode):
                outline = next(plan for plan in plans if plan["id"] == episode["id"])
                review = await reviewed(f"{episode['id']}_review_0", "long_episode_review_zh", {
                    "episode_plan": outline, "episode": compact_episode(episode), "editor_notes": notes,
                }, out / "reviews" / f"{episode['id']}_0.json")
                return {"episode_id": episode["id"], "review": review,
                        "issues": [{**issue, "episode_id": episode["id"]} for issue in review.get("issues", [])]}

            local_reviews = await collect([review_episode(episode) for episode in episodes])
            season_review = await reviewed("season_review_0", "long_season_review_zh", {
                "season_plan": {"title": season["title"], "logline": season.get("logline", ""), "episodes": plans},
                "episodes": [story_evidence(episode) for episode in episodes], "editor_notes": notes,
            }, out / "reviews" / "season_0.json")
        write_json(out / "episode_reviews.json", local_reviews)
        quality = {"status": "text_complete_images_pending", "structural_issues": checks,
                   "llm_review": "skipped" if long_review == "off" else "reported",
                   "episode_reviews": local_reviews, "model_review": season_review,
                   "open_errors": [issue for issue in checks + season_review.get("issues", [])
                                   + [issue for review in local_reviews for issue in review["issues"]]
                                   if issue["severity"] == "error"],
                   "scope": "Actual text/package checks only; no images, audio or video generated."}
        write_json(out / "quality.json", quality)
        if pause("review"):
            return state
        summary = export_season(season, episodes, delivery, config)
        write_json(delivery / "quality.json", quality)
        if quality["open_errors"]:
            summary["status"] = "needs_text_revision_images_pending"
            write_json(delivery / "overview.json", summary)
        state.update(status="needs_text_revision" if quality["open_errors"] else "text_ready",
                     finished_at=datetime.now(timezone.utc).isoformat(), summary=summary)
        write_json(state_file, state)
        client.event("export_finished", status=state["status"], output=str(delivery))
        return state
    except Exception as exc:
        state.update(status="failed", error=str(exc).replace(client.key, "[REDACTED]"))
        write_json(state_file, state)
        raise


def source_excerpt(plan: dict, paragraphs: list[dict]) -> list[dict]:
    """Resolve the P1 source selection at the input boundary, keeping original text."""
    ranges = plan.get("source_ranges")
    if not isinstance(ranges, list) or not ranges:
        raise ValueError(f"{plan['id']}: source_ranges must contain paragraph ranges")
    result, previous_end = [], 0
    for bounds in ranges:
        if (not isinstance(bounds, list) or len(bounds) != 2
                or any(type(number) is not int for number in bounds)):
            raise ValueError(f"{plan['id']}: source_ranges entries must be [start, end] integers")
        start, end = bounds
        if not previous_end < start <= end <= len(paragraphs):
            raise ValueError(f"{plan['id']}: source_ranges must be ordered, nonoverlapping and within the numbered source")
        result.extend(paragraphs[start - 1:end])
        previous_end = end
    return result


def asset_catalog(season: dict) -> dict:
    """Give the dramatist an inventory without repeated visual descriptions."""
    return {
        "characters": [{"id": item["id"], "name": item["name"],
                        "dramatic_profile_zh": item["dramatic_profile_zh"],
                        "wardrobe_ids": [wardrobe["id"] for wardrobe in item["wardrobes"]]}
                       for item in season["characters"]],
        **{key: [{"id": item["id"], "name": item["name"]} for item in season[key]]
           for key in ("locations", "props")},
    }


def scene_assets(season: dict, scene: dict) -> dict:
    """Include the scene's visual assets and voices, including off-screen speakers."""
    wardrobes = {member["id"]: member["wardrobe_id"] for member in scene["characters"]}
    speakers = {event["speaker_id"] for event in scene["events"] if "speaker_id" in event}
    characters = [{**item, "wardrobes": [wardrobe for wardrobe in item["wardrobes"]
                                         if wardrobe["id"] == wardrobes.get(item["id"])]}
                  for item in season["characters"] if item["id"] in wardrobes or item["id"] in speakers]
    return {"style_en": season["style_en"], "characters": characters,
            "locations": [item for item in season["locations"] if item["id"] == scene["location_id"]],
            "props": [item for item in season["props"] if item["id"] in scene["prop_ids"]]}


def merge_opening(plan: dict, opening: dict, duration_range: list[float]) -> dict:
    """Join the two authors' events while preserving one continuous physical scene."""
    first_scene = {key: opening[key] for key in ("location_id", "time_of_day", "characters", "prop_ids", "events")}
    first_scene.update(id=f"{plan['id']}_scene01", opening={
        "event_ids": [event["id"] for event in opening["events"]],
        "duration_range_seconds": duration_range,
    })
    remaining = plan["scenes"]
    if remaining[0]["id"] == first_scene["id"]:
        continuation = remaining[0]
        first_scene.update(characters=continuation["characters"], prop_ids=continuation["prop_ids"],
                           events=opening["events"] + continuation["events"])
        remaining = remaining[1:]
    return {**plan, "scenes": [first_scene, *remaining]}


def assemble_episode(plan: dict, scenes: list[dict]) -> dict:
    """Assign final episode IDs after writers choose each scene's shot count."""
    episode = {key: plan[key] for key in ("id", "title", "synopsis", "start_state", "end_state")}
    episode["shots"] = []
    for scene in scenes:
        first = len(episode["shots"]) + 1
        ids = {shot["id"]: f"{plan['id']}_s{first + index:03}" for index, shot in enumerate(scene["shots"])}
        anchor = ids[scene["anchor_shot_id"]]
        episode["shots"].extend({**shot, "id": ids[shot["id"]], "scene_anchor_shot_id": anchor}
                                for shot in scene["shots"])
    return episode


def sync_scene_plan(episode: dict, plan: dict) -> None:
    """Record actual shot ranges after scene assembly."""
    for scene in plan["scenes"]:
        members = [(index, shot) for index, shot in enumerate(episode["shots"], 1) if shot["scene_id"] == scene["id"]]
        ids = {shot["id"]: index for index, shot in members}
        anchor = members[0][1]["scene_anchor_shot_id"]
        scene.update(first_shot_number=members[0][0], last_shot_number=members[-1][0], anchor_shot_number=ids[anchor])
