"""Copy a rendered-image episode batch from the canonical full-season package."""

import argparse
import json
import re
import shutil
from pathlib import Path

from imagepipe.delivery import copy_asset
from videopipe.inputs import load_package

from .llm import write_json


def parse_episode_range(value: str) -> list[str]:
    match = re.fullmatch(r"(?:ep)?(\d+)(?:-(?:ep)?(\d+))?", value.strip())
    if not match:
        raise argparse.ArgumentTypeError("Use an episode or inclusive range, e.g. ep01-ep10 or 11-20")
    start, end = int(match[1]), int(match[2] or match[1])
    if start < 1 or end < start:
        raise argparse.ArgumentTypeError("Episode numbers must be positive and the range ascending")
    return [f"ep{number:02}" for number in range(start, end + 1)]


def export_batch(package: Path, output: Path, episode_ids: list[str], asset_ids: list[str], *,
                 hardlink_images: bool = False) -> dict:
    """Keep IDs, prompts, seeds and image bytes identical to the canonical package."""
    package, output = package.resolve(), output.resolve()
    overview = json.loads((package / "overview.json").read_text(encoding="utf-8"))
    manifest = json.loads((package / "image_slots.json").read_text(encoding="utf-8"))
    episodes = _batch_inputs(package, output, overview, episode_ids)
    assets = set(asset_ids)
    shared = [slot for slot in manifest["shared_assets"] if slot["asset_id"] in assets]
    frames = [slot for slot in manifest["first_frames"] if slot["asset_id"] in assets]
    for slot in shared + frames:
        if not (package / slot["path"]).is_file():
            raise ValueError(f"Batch image is missing: {slot['path']}")

    output.mkdir(parents=True, exist_ok=True)
    def copy_file(source, target):
        if Path(source).suffix.lower() == ".png":
            return copy_asset(source, target, hardlink=hardlink_images)
        return shutil.copy2(source, target)

    for name in ("season.json", "season_bible.md", "quality.json"):
        if (package / name).is_file():
            shutil.copy2(package / name, output / name)
    scripts = [f"# {overview['title']} · {episode_ids[0]}–{episode_ids[-1]}", ""]
    for episode in episodes:
        relative_dir = Path(episode["package"]).parent
        shutil.copytree(package / relative_dir, output / relative_dir, dirs_exist_ok=True, copy_function=copy_file)
        scripts.append((output / relative_dir / "script.md").read_text(encoding="utf-8"))
        slots_path = output / relative_dir / "image_slots.json"
        episode_slots = json.loads(slots_path.read_text(encoding="utf-8"))
        episode_slots["status"] = "images_ready"
        for slot in episode_slots["slots"]:
            slot["status"] = "ready"
        write_json(slots_path, episode_slots)
    for slot in shared + frames:
        destination = output / slot["path"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        copy_asset(package / slot["path"], destination, hardlink=hardlink_images)
    write_json(output / "image_slots.json", {
        "status": "images_ready",
        "shared_assets": [{**slot, "status": "ready"} for slot in shared],
        "first_frames": [{**slot, "status": "ready"} for slot in frames],
    })
    summary = {
        **overview, "status": "images_ready", "render_ready": True,
        "episode_count": len(episodes), "episodes": episodes,
        "shot_count": sum(episode["shot_count"] for episode in episodes),
        "planned_duration_seconds": round(sum(episode["planned_duration_seconds"] for episode in episodes), 3),
        "shared_image_slot_count": len(shared), "image_slot_count": len(shared) + len(frames),
        "episode_range": [episode_ids[0], episode_ids[-1]],
    }
    if overview["status"].startswith("needs_text_revision"):
        summary.update(status="needs_text_revision_images_ready", render_ready=False)
    write_json(output / "overview.json", summary)
    (output / "screenplay.md").write_text("\n\n---\n\n".join(scripts), encoding="utf-8")
    (output / "README.md").write_text(
        f"# {overview['title']} · {episode_ids[0]}–{episode_ids[-1]} 剧本包\n\n"
        f"包含 {len(episodes)} 集剧本、镜头首帧及所需人物、服装、场景和道具参考图。\n"
        "season.json / season_bible.md 保留全剧设定；overview.json 仅列本批次。\n"
        "quality.json（如有）保留整季文字审阅结果。所有图片均复制自全剧资产目录。\n\n"
        "使用 `videopipe run-season <本包目录> --output <视频运行目录>` 生成本批视频。\n",
        encoding="utf-8",
    )
    return {"delivery": str(output), **summary}


def _batch_inputs(package: Path, output: Path, overview: dict, episode_ids: list[str]) -> list[dict]:
    if output == package or output in package.parents or package in output.parents:
        raise ValueError("Batch delivery and canonical package must be separate directories")
    by_id = {episode["id"]: episode for episode in overview["episodes"]}
    missing = set(episode_ids) - by_id.keys()
    if missing:
        raise ValueError(f"Unknown episodes: {', '.join(sorted(missing))}")
    previous = output / "overview.json"
    if previous.exists():
        saved = json.loads(previous.read_text(encoding="utf-8"))
        if [episode["id"] for episode in saved["episodes"]] != episode_ids:
            raise ValueError("Batch delivery already contains a different episode range; choose a new directory")
    episodes = [by_id[episode_id] for episode_id in episode_ids]
    for episode in episodes:
        load_package(package / episode["package"])
    return episodes
