"""Compile episode or season image slots into one dependency-driven plan."""

import json
from graphlib import TopologicalSorter
from pathlib import Path

from videopipe.prompts import load_prompt

from .models import CopyTask, ImageConfig, ImagePlan, ImageTask


def compile_plan(package_dir: Path, config: ImageConfig, episode_ids: list[str] | None = None) -> ImagePlan:
    root = Path(package_dir).resolve()
    selected, catalogue, copies, style = _load_inputs(root, episode_ids)
    references, masters = _dependencies(selected, catalogue, config.continuity, config.api.max_reference_images)
    canonical_indices = {asset_id: index for index, asset_id in enumerate(catalogue)}
    tasks = []
    for index, asset_id in enumerate(selected):
        slot = catalogue[asset_id]
        reference_ids = references[asset_id]
        template, mode = _generation_kind(slot, masters, reference_ids)
        slot_style = slot.get("style_en", style).strip()
        prompt = load_prompt(
            f"image/imagepipe_{template}.txt",
            style=slot_style,
            description=(_frame_description(slot, catalogue, slot_style)
                         if slot.get("purpose") == "first_frame" else _description(slot, slot_style)),
            reference_guide=_reference_guide(reference_ids, catalogue),
            width=(config.generation.native_width if config.provider != "qwen" else config.generation.width),
            height=(config.generation.native_height if config.provider != "qwen" else config.generation.height),
        )
        tasks.append(ImageTask(
            asset_id=asset_id,
            mode=mode,
            prompt=prompt,
            reference_ids=reference_ids,
            target_path=slot["_target"],
            seed=config.generation.seed_base + (canonical_indices[asset_id] if episode_ids is not None else index),
        ))
    return ImagePlan(package_root=str(root), tasks=tasks, copies=copies)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_inputs(root: Path, episode_ids: list[str] | None = None
                 ) -> tuple[list[str], dict[str, dict], list[CopyTask], str]:
    manifest = _read_json(root / "image_slots.json")
    if episode_ids is not None:
        if "shared_assets" not in manifest:
            raise ValueError("Episode selection requires a season package")
        available = {slot["episode_id"] for slot in manifest.get("first_frames", [])}
        missing = set(episode_ids) - available
        if missing:
            raise ValueError(f"Episodes not found in package: {', '.join(sorted(missing))}")
    season_path = next((p / "season.json" for p in (root, *root.parents)
                        if (p / "season.json").exists()), None)
    season = _read_json(season_path) if season_path else {}
    style = season.get("render_style_en", season.get("style_en", ""))
    catalogue = {}
    selected = []
    copies = []

    if "shared_assets" in manifest:
        slots = manifest["shared_assets"] + manifest.get("first_frames", [])
        for slot in slots:
            asset_id = slot["asset_id"]
            if asset_id in catalogue:
                raise ValueError(f"Duplicate image asset ID: {asset_id}")
            catalogue[asset_id] = {**slot, "_target": str((root / slot["path"]).resolve())}
            if episode_ids is None or slot.get("episode_id") in episode_ids:
                selected.append(asset_id)
        for path in sorted(root.rglob("image_slots.json")):
            if path.parent == root:
                continue
            if episode_ids is not None and path.parent.name not in episode_ids:
                continue
            for slot in _read_json(path).get("slots", []):
                if "source_path" in slot:
                    source_id = slot.get("source_asset_id", slot["asset_id"])
                    copies.append(CopyTask(
                        asset_id=source_id,
                        source_path=str((path.parent / slot["source_path"]).resolve()),
                        target_path=str((path.parent / slot["path"]).resolve()),
                    ))
                    if source_id not in selected:
                        selected.append(source_id)
    else:
        # A standalone episode can still depend on the season's canonical mother images.
        for parent in root.parents:
            path = parent / "image_slots.json"
            if path.exists():
                parent_manifest = _read_json(path)
                shared = parent_manifest.get("shared_assets", [])
                if shared:
                    catalogue.update({slot["asset_id"]: {
                        **slot, "_target": str((parent / slot["path"]).resolve()),
                    } for slot in shared + parent_manifest.get("first_frames", [])})
                    break
        for slot in manifest["slots"]:
            asset_id = slot["asset_id"]
            if asset_id in selected:
                raise ValueError(f"Duplicate image asset ID: {asset_id}")
            selected.append(asset_id)
            if "source_path" in slot:
                source_path = str((root / slot["source_path"]).resolve())
                source = catalogue.get(slot.get("source_asset_id", asset_id),
                                       {**slot, "purpose": slot.get("reference_purpose", slot.get("purpose"))})
                catalogue[asset_id] = {**source, "asset_id": asset_id, "_target": source_path}
                copies.append(CopyTask(
                    asset_id=asset_id,
                    source_path=source_path,
                    target_path=str((root / slot["path"]).resolve()),
                ))
            else:
                catalogue[asset_id] = {**slot, "_target": str((root / slot["path"]).resolve())}
    # Older exported slots keep scene metadata in storyboard.json.
    contexts = {}
    for path in sorted(root.rglob("storyboard.json")):
        episode = _read_json(path)
        for shot in episode["shots"]:
            contexts[(episode["id"], shot["id"])] = shot
    for slot in catalogue.values():
        if slot.get("purpose") == "first_frame":
            shot = contexts.get((slot.get("episode_id"), slot.get("shot_id")), {})
            for field in ("scene_id", "location_id", "time_of_day", "continuity_en", "scene_anchor_shot_id"):
                if field in shot:
                    slot.setdefault(field, shot[field])
    return selected, catalogue, copies, style


def _dependencies(selected: list[str], catalogue: dict[str, dict], continuity: dict, max_references: int
                  ) -> tuple[dict[str, list[str]], dict[str, str]]:
    masters = {}
    for asset_id, slot in catalogue.items():
        character_id = slot.get("character_id")
        if character_id:
            if character_id not in masters or slot.get("purpose") == "character_identity":
                masters[character_id] = asset_id
    anchors = _frame_anchors(catalogue, continuity.get("sets", []),
                             auto=continuity.get("auto_scene_anchors", True))
    additional = continuity.get("additional_reference_assets", {})
    priorities = continuity.get("reference_priority", {})
    references = {}
    # Appending dependencies here also brings missing season masters into an episode run.
    for asset_id in selected:
        slot = catalogue[asset_id]
        refs = list(slot.get("reference_asset_ids", []))
        character_id = slot.get("character_id")
        if character_id and masters[character_id] != asset_id:
            refs.insert(0, masters[character_id])
        refs.extend(additional.get(asset_id, []))
        if asset_id in anchors:
            refs.append(anchors[asset_id])
        refs = list(dict.fromkeys(refs))
        missing = [ref for ref in refs if ref not in catalogue]
        if missing:
            raise ValueError(f"{asset_id} references missing asset {missing[0]}")
        priority = {ref: index for index, ref in enumerate(priorities.get(asset_id, []))}
        refs.sort(key=lambda ref: priority.get(ref, len(priority)))
        refs = refs[:max_references]
        for reference_id in refs:
            if reference_id not in selected:
                selected.append(reference_id)
        references[asset_id] = refs
    TopologicalSorter(references).prepare()
    return references, masters


def _frame_anchors(catalogue: dict[str, dict], sets: list[dict], *, auto: bool = True) -> dict[str, str]:
    aliases: dict[str, list[str]] = {}
    scene_groups, anchors = {}, {}
    for asset_id, slot in catalogue.items():
        if slot.get("purpose") != "first_frame":
            continue
        labels = {asset_id, slot["shot_id"]}
        if slot.get("episode_id"):
            labels.add(f"{slot['episode_id']}/{slot['shot_id']}")
        for label in labels:
            aliases.setdefault(label, []).append(asset_id)
        if auto and slot.get("scene_id"):
            key = (slot.get("episode_id"), slot["scene_id"], slot.get("location_id"), slot.get("time_of_day"))
            scene_groups.setdefault(key, []).append(asset_id)
    for members in scene_groups.values():
        planned = catalogue[members[0]].get("scene_anchor_shot_id")
        if planned:
            matches = [member for member in members if catalogue[member]["shot_id"] == planned]
            # A script scene can span location/time groups, each needing its own anchor.
            anchor = matches[0] if matches else members[0]
        else:
            anchor = members[0]
        anchors.update((member, anchor) for member in members if member != anchor)
    for group in sets:
        shots = group.get("shot_ids", group.get("shots", []))
        anchor_label = group.get("anchor_shot", shots[0] if shots else "")
        resolved = []
        for label in [anchor_label, *shots]:
            matches = aliases.get(label, [])
            if len(matches) != 1:
                raise ValueError(f"Set {group.get('set_id', '')}: shot {label!r} is missing or ambiguous")
            resolved.append(matches[0])
        anchor = resolved[0]
        anchors.pop(anchor, None)
        for member in resolved[1:]:
            if member != anchor:
                anchors[member] = anchor
    return anchors


def _generation_kind(slot: dict, masters: dict[str, str], references: list[str]) -> tuple[str, str]:
    if slot.get("purpose") == "first_frame":
        template = "first_frame"
    elif slot.get("purpose") == "character_identity":
        template = "character_identity"
    elif slot.get("character_id"):
        template = ("character_master" if masters[slot["character_id"]] == slot["asset_id"]
                    else "wardrobe_edit")
    elif slot.get("location_id"):
        template = "location_reference"
    else:
        template = "prop_edit" if references else "prop_reference"
    mode = "text"
    if references:
        mode = "edit" if len(references) == 1 and template in {"wardrobe_edit", "prop_edit"} else "reference"
    return template, mode


def _description(slot: dict, style: str) -> str:
    description = slot["prompt_en"].strip()
    if style and description.startswith(style):
        description = description[len(style):].strip()
    return description


def _frame_description(slot: dict, catalogue: dict[str, dict], style: str) -> str:
    cast = []
    for ref in slot.get("reference_asset_ids", []):
        reference = catalogue[ref]
        if reference.get("wardrobe_id"):
            costume = reference.get("wardrobe_description_en") or _description(reference, style)
            cast.append(f"{reference['character_id']} wears {costume.rstrip('.')}")
    parts = [_description(slot, style)]
    if cast:
        parts.append("Featured character wardrobe: " + "; ".join(cast) + ".")
    if slot.get("continuity_en"):
        parts.append("Scene geography: " + slot["continuity_en"])
    return " ".join(parts)


def _reference_guide(references: list[str], catalogue: dict[str, dict]) -> str:
    lines = []
    for index, asset_id in enumerate(references, start=1):
        slot = catalogue[asset_id]
        if slot.get("purpose") == "first_frame":
            role = "the same scene's geography and lighting, reframed from the target camera position"
        elif slot.get("purpose") == "character_identity":
            role = f"facial identity and hairline of {slot['character_id']}"
        elif slot.get("character_id"):
            role = f"clothing design for {slot['character_id']}, outfit {slot.get('wardrobe_id', '')}"
        elif slot.get("location_id"):
            role = f"architecture and fixed furnishings of {slot['location_id']}"
        else:
            role = f"appearance of {slot.get('prop_id', asset_id)}; quantity and placement come from the target scene"
        label = "the reference image" if len(references) == 1 else f"<image{index}>"
        lines.append(f"{label}: {role}.")
    return "\n".join(lines)
