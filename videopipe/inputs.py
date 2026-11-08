import json
import shutil
from pathlib import Path

import yaml

from .models import AssetBinding, PipelineConfig, ScriptPackage
from .prompts import load_prompt
from .records import write_json
from .subtitles import subtitle_font


RESERVED_PARAMETERS = {
    "prompt", "negative_prompt", "h3_prompt", "feedback", "seed", "attempt",
    "reference_image", "reference_images", "reference_video", "filename_prefix",
    "width", "height", "fps", "frames", "duration",
}


def load_package(path: Path) -> ScriptPackage:
    path = path.resolve()
    package = ScriptPackage.model_validate(json.loads(path.read_text(encoding="utf-8")))
    ids = [shot.id for shot in package.shots]
    if len(ids) != len(set(ids)):
        raise ValueError("Shot IDs must be unique")
    package.script = _file(path.parent, package.script)
    for shot in package.shots:
        shot.reference_images = [_file(path.parent, ref) for ref in shot.reference_images]
        for asset in shot.asset_bindings:
            asset.path = _file(path.parent, asset.path)
    return package


def load_config(path: Path) -> PipelineConfig:
    path = path.resolve()
    config = PipelineConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    for name in ("workflow", "upscale_workflow"):
        value = getattr(config.comfyui, name)
        if value is not None:
            setattr(config.comfyui, name, _file(path.parent, value))
    if config.subtitles.font_file is not None:
        # Checked when a run is planned; script export also reads this configuration on machines without the font.
        config.subtitles.font_file = (path.parent / config.subtitles.font_file).resolve()
    if config.generator == "comfyui" and config.workers > len(config.comfyui.urls):
        raise ValueError("workers must not exceed the number of ComfyUI service URLs")
    return config


def validate_plan(package: ScriptPackage, config: PipelineConfig) -> None:
    for parameters in [config.comfyui.parameters, *(shot.parameters for shot in package.shots)]:
        reserved = {key for key in parameters if key in RESERVED_PARAMETERS or key.startswith("reference_image_")}
        if reserved:
            raise ValueError(f"Use the package fields instead of parameter overrides: {', '.join(sorted(reserved))}")
    for shot in package.shots:
        if sum(asset.role == "first_frame" for asset in shot.asset_bindings) > 1:
            raise ValueError(f"Shot {shot.id}: the built-in I2VA workflow accepts one first_frame")
        ids = [asset.asset_id for asset in shot.asset_bindings]
        if len(ids) != len(set(ids)):
            raise ValueError(f"Shot {shot.id}: asset IDs must be unique")
    if config.subtitles.burn:
        if not config.subtitles.font_path.is_file():
            raise ValueError(f"Subtitle font file does not exist: {config.subtitles.font_path}")
        subtitle_font(config.subtitles)
    classes = []
    for path in (config.comfyui.workflow, config.comfyui.upscale_workflow):
        if path is not None:
            graph = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(graph, dict) or not graph or any(
                not isinstance(node, dict) or not isinstance(node.get("class_type"), str)
                or not isinstance(node.get("inputs"), dict) for node in graph.values()
            ):
                raise ValueError(f"Workflow must use ComfyUI API format (class_type and inputs per node): {path}")
            if path == config.comfyui.workflow:
                classes = [node["class_type"] for node in graph.values()]
    if config.generator != "comfyui":
        return
    for shot in package.shots:
        duration = config.comfyui.frame_count(shot.duration, shot.fps) / shot.fps
        if duration > config.comfyui.maximum_duration_seconds:
            raise ValueError(f"Shot {shot.id}: rounded duration {duration:g}s exceeds configured maximum_duration_seconds={config.comfyui.maximum_duration_seconds:g}")
    workflow = config.comfyui.workflow
    native_h3 = workflow is None or any(name.startswith("MiniMaxH3") for name in classes)
    if native_h3:
        for shot in package.shots:
            if shot.fps != 24 or shot.width % 32 or shot.height % 32:
                raise ValueError(f"H3 shot {shot.id} requires 24 fps and dimensions divisible by 32")


def snapshot_inputs(root: Path, package: ScriptPackage, config: PipelineConfig) -> None:
    write_json(root / "input-package.json", package.model_dump(mode="json"))
    package = package.model_copy(deep=True)
    config = config.model_copy(deep=True)
    inputs = root / "inputs"
    inputs.mkdir()
    shutil.copy2(package.script, inputs / "script.md")
    package.script = Path("inputs/script.md")
    for shot in package.shots:
        if shot.negative_prompt:
            # Legacy packages supplied two fields; freeze their combined text once at input.
            shot.prompt += "\n\n" + load_prompt("videopipe/videopipe_legacy_negative.txt", negative_prompt=shot.negative_prompt)
            shot.negative_prompt = ""
        if not shot.asset_bindings:
            shot.asset_bindings = [AssetBinding(
                asset_id=f"ref-{index + 1}", path=ref,
                role="first_frame" if index == 0 else "review_only",
                prompt_ref="<Picture 1>" if index == 0 else "",
            ) for index, ref in enumerate(shot.reference_images)]
        shot.asset_bindings.sort(key=lambda asset: asset.role != "first_frame")
        for index, asset in enumerate(shot.asset_bindings):
            destination = Path("inputs") / f"{shot.id}-{index}{asset.path.suffix}"
            shutil.copy2(asset.path, root / destination)
            asset.path = destination
        shot.reference_images = [asset.path for asset in shot.asset_bindings]
    for name in ("workflow", "upscale_workflow"):
        source = getattr(config.comfyui, name)
        if source is not None:
            destination = Path("inputs") / f"{name}.json"
            shutil.copy2(source, root / destination)
            setattr(config.comfyui, name, destination)
    write_json(root / "package.json", package.model_dump(mode="json"))
    write_json(root / "config.json", config.model_dump(mode="json"))


def _file(base: Path, value: Path) -> Path:
    result = (base / value).resolve()
    if not result.is_file():
        raise ValueError(f"Input file does not exist: {result}")
    return result
