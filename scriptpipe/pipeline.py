"""Plan once, write episodes concurrently, review, repair, and export text packages."""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from videopipe.inputs import load_config
from videopipe.models import PipelineConfig

from .checks import check_episode
from .export import export_season
from .llm import GLMClient, write_json

ROOT = Path(__file__).resolve().parent.parent


def prompt(name: str) -> str:
    return (ROOT / "prompt" / "script" / f"scriptpipe_{name}.txt").read_text(encoding="utf-8")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def compact_episode(episode: dict) -> dict:
    """Keep the actual shot evidence needed for story and production review."""
    fields = ("id", "scene_id", "location_id", "time_of_day", "characters", "prop_ids",
              "duration", "beat_zh", "action_start_zh", "action_end_zh", "action_complete",
              "cut_reason_zh", "visual_en", "camera_en", "soundscape_en",
              "first_frame_prompt_en", "acceptance_en", "dialogue", "reference_priority", "non_diegetic_music_en",
              "story_events", "event_refs")
    return {**{k: v for k, v in episode.items() if k != "shots"},
            "shots": [{k: s[k] for k in fields if k in s} for s in episode.get("shots", [])]}


def production_brief(config: PipelineConfig) -> dict:
    return {
        "maximum_duration_seconds": config.comfyui.maximum_duration_seconds,
        "maximum_requested_duration_seconds": (config.comfyui.maximum_requested_duration(config.media.fps)
                                               if config.generator == "comfyui" else config.comfyui.maximum_duration_seconds),
        "width": config.media.width, "height": config.media.height, "fps": config.media.fps,
        "duration_rule": "Choose duration from the scene's dialogue, action and pacing within the configured workflow limit.",
        "dialogue_language": config.script.language,
        "language": "Chinese narrative fields; dialogue in the project's language or the specified line language; English production descriptions.",
        "non_diegetic_music": config.script.non_diegetic_music,
        "on_screen_text": config.script.on_screen_text,
    }


def structural_issues(episodes: list[dict], season: dict, config: PipelineConfig) -> list[dict]:
    return [{**issue, "episode_id": ep.get("id")}
            for ep in episodes for issue in check_episode(ep, season, config=config)]


def merge_episode_repair(episode: dict, patch: dict) -> dict:
    """Replace only explicitly repaired shots; preserve every unaffected shot."""
    if patch.get("id") != episode["id"]:
        raise ValueError(f"Repair changed episode ID: {episode['id']}")
    by_id = {shot["id"]: shot for shot in episode["shots"]}
    replacements = patch.get("shots", [])
    replacement_ids = [shot["id"] for shot in replacements]
    if len(replacement_ids) != len(set(replacement_ids)) or not set(replacement_ids) <= by_id.keys():
        raise ValueError("A local repair must reference unique existing shot IDs")
    by_id.update((shot["id"], shot) for shot in replacements)
    order = patch.get("shot_order", [shot["id"] for shot in episode["shots"]])
    if len(order) != len(by_id) or set(order) != by_id.keys():
        raise ValueError("shot_order must contain every existing shot exactly once")
    result = {**episode, "shots": [by_id[shot_id] for shot_id in order]}
    for field in ("title", "synopsis", "start_state", "end_state"):
        if field in patch:
            result[field] = patch[field]
    return result


async def run(source_path: Path, out: Path, client: GLMClient, *, episode_count: int = 12,
              repair_rounds: int = 2, production_config: Path | None = None,
              notes_path: Path | None = None, review_reasoning_effort: str | None = None) -> dict:
    review_reasoning_effort = review_reasoning_effort or client.reasoning_effort
    config = load_config(production_config or Path("configs/b200.yaml"))
    out.mkdir(parents=True, exist_ok=True)
    state_file = out / "run.json"
    state = {"source": str(source_path.resolve()), "model": client.model,
             "endpoint": client.endpoint, "episode_count": episode_count,
             "planning_effort": client.reasoning_effort, "writing_effort": client.reasoning_effort,
             "review_effort": review_reasoning_effort,
             "status": "running", "started_at": datetime.now(timezone.utc).isoformat()}
    if state_file.exists():
        previous = read_json(state_file)
        if previous.get("source") != state["source"] or previous.get("episode_count") != episode_count:
            raise ValueError("This output directory contains a different experiment; choose a new output directory")
        state["started_at"] = previous.get("started_at", state["started_at"])
    write_json(state_file, state)
    original = source_path.read_text(encoding="utf-8")
    source = re.sub(r"\.mw-parser-output[^{}]*\{[^{}]*\}", "", original)
    (out / "source.cleaned.txt").write_text(source, encoding="utf-8")
    if source != original:
        client.event("source_cleaned", removed_characters=len(original) - len(source),
                     reason="Remove embedded MediaWiki CSS; keep original source file unchanged")
    notes = notes_path.read_text(encoding="utf-8") if notes_path else ""
    brief = {
        **production_brief(config),
        "episode_count": episode_count,
        "shot_count_policy": "Choose the number of shots from the story and its dialogue.",
        "format": "Live-action short drama; setting and complete story follow the supplied source and editor notes",
        "action_rule": "Describe the action, dialogue turns and state at each cut so adjacent shots form a coherent scene.",
        "scope": "Write text and image-slot descriptions.",
        "adaptation_decisions": [
            "Preserve the source's complete causal chain and ending; follow explicit adaptation decisions in editor notes.",
            "Develop the story through dialogue, inner monologue, conflict and action; track what each character knows.",
        ],
    }
    try:
        season_file = out / "season.json"
        if season_file.exists():
            season = read_json(season_file)
            client.event("stage_resumed", stage="season")
        else:
            season = await client.complete("season", prompt("short_season_plan"), {
                "brief": brief, "source_text": source, "editor_notes": notes,
            })
            write_json(season_file, season)
        plans = season.get("episodes", [])
        if len(plans) != episode_count or len({p["id"] for p in plans}) != episode_count:
            raise ValueError("Season plan must contain the requested number of uniquely identified episodes")

        async def write_episode(plan: dict) -> dict:
            destination = out / "drafts" / f"{plan['id']}.json"
            if destination.exists():
                client.event("stage_resumed", stage="episode", episode_id=plan["id"])
                return read_json(destination)
            episode = await client.complete(plan["id"], prompt("short_episode_write"), {
                "brief": brief, "source_text": source, "editor_notes": notes,
                "season": season, "episode_plan": plan,
            })
            if episode.get("id") != plan["id"]:
                raise ValueError(f"Episode ID differs from requested plan: {plan['id']}")
            write_json(destination, episode)
            return episode

        episodes = list(await asyncio.gather(*(write_episode(plan) for plan in plans)))
        reviews: list[dict] = []
        for cycle in range(repair_rounds + 1):
            issues = structural_issues(episodes, season, config)
            review = await client.complete(f"review_{cycle}", prompt("short_season_review"), {
                "brief": brief, "source_text": source, "editor_notes": notes,
                "season": season, "episodes": [compact_episode(ep) for ep in episodes],
                "structural_issues": issues,
            }, temperature=0.3, reasoning_effort=review_reasoning_effort)
            write_json(out / "reviews" / f"review_{cycle}.json", review)
            reviews.append(review)
            combined = issues + review.get("issues", [])
            errors = [x for x in combined if x.get("severity") == "error"]
            client.event("review_finished", cycle=cycle, errors=len(errors),
                         warnings=sum(x.get("severity") == "warning" for x in combined))
            if not errors or cycle == repair_rounds:
                break
            global_errors = [x for x in errors if not x.get("episode_id")]

            async def repair_episode(episode: dict) -> dict:
                relevant = [x for x in errors if x.get("episode_id") == episode["id"]] + global_errors
                if not relevant:
                    return episode
                patch = await client.complete(f"{episode['id']}_repair_{cycle}", prompt("short_shot_repair"), {
                    "brief": brief, "source_text": source, "editor_notes": notes,
                    "season": season, "episode": episode, "issues": relevant,
                    "adjacent_episode_summaries": [
                        {"id": ep["id"], "start_state": ep.get("start_state"),
                         "end_state": ep.get("end_state"), "synopsis": ep.get("synopsis")}
                        for ep in episodes],
                })
                repaired = merge_episode_repair(episode, patch)
                write_json(out / "drafts" / f"{episode['id']}.before_repair_{cycle}.json", episode)
                write_json(out / "drafts" / f"{episode['id']}.json", repaired)
                return repaired

            episodes = list(await asyncio.gather(*(repair_episode(ep) for ep in episodes)))

        checks = structural_issues(episodes, season, config)
        final_review = reviews[-1]
        summary = export_season(season, episodes, out / "delivery",
                                config)
        quality = {"structural_issues": checks, "model_review": final_review,
                   "review_rounds": len(reviews),
                   "open_errors": [x for x in checks + final_review.get("issues", [])
                                   if x.get("severity") == "error"],
                   "scope": "Text/package checks only. No images, audio or videos were generated or assessed."}
        write_json(out / "quality.json", quality)
        write_json(out / "delivery" / "quality.json", quality)
        if quality["open_errors"]:
            summary["status"] = "needs_text_revision_images_pending"
            write_json(out / "delivery" / "overview.json", summary)
        state.update(status="text_ready" if not quality["open_errors"] else "needs_text_revision",
                     finished_at=datetime.now(timezone.utc).isoformat(), summary=summary)
        write_json(state_file, state)
        client.event("export_finished", status=state["status"], output=str(out / "delivery"))
        return state
    except Exception as exc:
        state.update(status="failed", error=str(exc).replace(client.key, "[REDACTED]"))
        write_json(state_file, state)
        raise
