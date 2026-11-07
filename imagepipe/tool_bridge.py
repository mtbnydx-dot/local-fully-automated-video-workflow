"""Exchange native image-tool requests and completed local images."""

import json
from contextlib import ExitStack
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def prepare_tool_args(prompt: str, references: list[Path], sheets_dir: Path) -> dict:
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
        with ExitStack() as stack:
            images = [stack.enter_context(Image.open(source)) for source in group]
            mode = "RGBA" if any("A" in source.getbands() or "transparency" in source.info for source in images) else "RGB"
            sheet = Image.new(mode, (sum(source.width for source in images), max(source.height for source in images) + 64), "white")
            draw = ImageDraw.Draw(sheet)
            font = ImageFont.load_default(size=24)
            offset = 0
            labels = []
            for panel_index, source in enumerate(images):
                reference_number = cursor + panel_index + 1
                sheet.paste(source, (offset, 64))
                draw.text((offset + 8, 16), f"Reference {reference_number}", fill="black", font=font)
                position = ("left" if panel_index == 0 else "right") if count == 2 else f"panel {panel_index + 1} from left"
                labels.append(f"original reference {reference_number} ({position})")
                offset += source.width
            sheet.save(path, compress_level=1)
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
