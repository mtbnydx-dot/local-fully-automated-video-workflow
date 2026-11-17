"""Exchange native image-tool requests and completed local images."""

import json
import threading
from contextlib import ExitStack
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .delivery import copy_asset


class ReferenceSheetCache:
    """Reuse identical, labelled full-resolution reference panels within a run."""

    def __init__(self, directory: Path):
        self.directory = directory
        self.index_path = directory / "index.json"
        self.index = json.loads(self.index_path.read_text()) if self.index_path.exists() else {}
        self.lock = threading.Lock()

    def render(self, group: list[Path], start: int) -> Path:
        sources = [(str(path.resolve()), path.stat().st_size, path.stat().st_mtime_ns) for path in group]
        key = json.dumps([start, sources], ensure_ascii=False)
        with self.lock:
            name = self.index.get(key, f"sheet_{len(self.index) + 1:05d}.png")
            path = self.directory / name
            if key in self.index and path.is_file():
                return path
            self.directory.mkdir(parents=True, exist_ok=True)
            _render_reference_sheet(group, start, path)
            self.index[key] = name
            pending = self.index_path.with_suffix(".json.tmp")
            pending.write_text(json.dumps(self.index, ensure_ascii=False, indent=2) + "\n")
            pending.replace(self.index_path)
            return path


def prepare_tool_args(prompt: str, references: list[Path], sheets_dir: Path, *,
                      sheet_cache: ReferenceSheetCache | None = None) -> dict:
    arguments = {"prompt": prompt, "transparent_background": False}
    if len(references) <= 5:
        if references:
            arguments["referenced_image_paths"] = [str(path) for path in references]
        return arguments

    sheets_dir.mkdir(parents=True, exist_ok=True)
    sheet_count = min(5, (len(references) + 1) // 2)
    group_size, extra = divmod(len(references), sheet_count)
    paths, mapping = [], []
    cursor = 0
    for sheet_index in range(sheet_count):
        count = group_size + (sheet_index < extra)
        group = references[cursor:cursor + count]
        path = sheets_dir / f"sheet_{sheet_index + 1:02d}.png"
        if sheet_cache is None:
            _render_reference_sheet(group, cursor, path)
        else:
            copy_asset(sheet_cache.render(group, cursor), path, hardlink=True)
        labels = []
        for panel_index in range(count):
            position = ("left" if panel_index == 0 else "right") if count == 2 else f"panel {panel_index + 1} from left"
            labels.append(f"original reference {cursor + panel_index + 1} ({position})")
        paths.append(str(path))
        mapping.append(f"Attached image {sheet_index + 1}: " + ", ".join(labels) + ".")
        cursor += count
    arguments["referenced_image_paths"] = paths
    arguments["prompt"] = (
        "Reference transport mapping: the attached images are reference sheets. Use their labelled panels "
        "as separate original references when following the original prompt below. Produce the single requested "
        "image; the sheet labels and layout are input metadata.\n" + "\n".join(mapping)
        + "\n\nOriginal system image prompt:\n" + prompt
    )
    return arguments


def _render_reference_sheet(group: list[Path], start: int, path: Path) -> None:
    with ExitStack() as stack:
        images = [stack.enter_context(Image.open(source)) for source in group]
        mode = "RGBA" if any("A" in source.getbands() or "transparency" in source.info for source in images) else "RGB"
        sheet = Image.new(mode, (sum(source.width for source in images), max(source.height for source in images) + 64), "white")
        draw = ImageDraw.Draw(sheet)
        font = ImageFont.load_default(size=24)
        offset = 0
        for index, source in enumerate(images):
            sheet.paste(source, (offset, 64))
            draw.text((offset + 8, 16), f"Reference {start + index + 1}", fill="black", font=font)
            offset += source.width
        sheet.save(path, compress_level=6)


def pending_requests(run_dir: Path) -> list[dict]:
    requests = []
    for path in sorted((run_dir / "requests").glob("*.json")):
        request = json.loads(path.read_text())
        if not (run_dir / "responses" / path.name).exists() and not Path(request["target_path"]).is_file():
            requests.append(request)
    return requests


def accept_image(run_dir: Path, asset_id: str, image_path: Path) -> dict:
    plan = json.loads((run_dir / "tasks.json").read_text())
    if plan["config"]["provider"] != "codex":
        raise ValueError("accept requires a codex image run")
    if asset_id not in {task["asset_id"] for task in plan["tasks"]}:
        raise ValueError(f"Unknown image asset: {asset_id}")
    image_path = image_path.resolve()
    if not image_path.is_file():
        raise ValueError(f"Generated image not found: {image_path}")
    response = {"asset_id": asset_id, "image_path": str(image_path)}
    path = run_dir / "responses" / f"{asset_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(".json.tmp")
    pending.write_text(json.dumps(response, ensure_ascii=False, indent=2) + "\n")
    pending.replace(path)
    return response
