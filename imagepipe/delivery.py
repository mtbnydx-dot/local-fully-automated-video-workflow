"""Write generated images into the package's existing asset paths."""

from __future__ import annotations

import errno
import os
import shutil
import time
from pathlib import Path

from PIL import Image


def deliver_image(original: Path, target: Path, width: int, height: int, resize_mode: str = "crop") -> dict:
    with Image.open(original) as source:
        source_size = source.size
        image = source.convert("RGB")
    source_width, source_height = source_size
    resized = source_size != (width, height)
    scale = (min if resize_mode == "pad" else max)(width / source_width, height / source_height)
    crop_width, crop_height = width / scale, height / scale
    left = (source_width - crop_width) / 2
    top = (source_height - crop_height) / 2
    crop_box = (left, top, left + crop_width, top + crop_height)
    if resize_mode == "pad":
        crop_box = (0, 0, source_width, source_height)
        size = (max(1, round(source_width * scale)), max(1, round(source_height * scale)))
        content = image.resize(size, Image.Resampling.LANCZOS) if resized else image
        image = Image.new("RGB", (width, height), "black")
        image.paste(content, ((width - size[0]) // 2, (height - size[1]) // 2))
    elif resized:
        image = image.resize((width, height), Image.Resampling.LANCZOS, box=crop_box)
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target, format="PNG")
    return {
        "source_size": list(source_size),
        "output_size": [width, height],
        "crop_box": [round(value, 3) for value in crop_box],
        "resized": resized,
        "mode": "RGB",
        "resize_mode": resize_mode,
    }


def copy_asset(original: Path, target: Path, *, hardlink: bool = False) -> str:
    original, target = Path(original), Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and original.samefile(target):
        return str(target)
    if not hardlink:
        return shutil.copy2(original, target)
    # Replace the directory entry so an existing shared inode is never overwritten.
    pending = target.with_name(f".{target.name}.{time.time_ns()}.tmp")
    try:
        os.link(original, pending)
    except OSError as error:
        if error.errno != errno.EXDEV:
            raise
        shutil.copy2(original, pending)
    pending.replace(target)
    return str(target)


def deliver_original(original: Path, target: Path, *, hardlink: bool = False) -> dict:
    with Image.open(original) as source:
        width, height = source.size
        mode = source.mode
    copy_asset(original, target, hardlink=hardlink)
    return {
        "source_size": [width, height], "output_size": [width, height],
        "crop_box": [0, 0, width, height], "resized": False,
        "mode": mode, "resize_mode": "original",
    }
