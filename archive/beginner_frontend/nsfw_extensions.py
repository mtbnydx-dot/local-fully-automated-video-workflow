"""NSFW playbook graph extensions — no imports from app.py (avoid circular deps)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable


KEYFRAME_CONSISTENCY_NEGATIVE: tuple[str, ...] = (
    "inconsistent identity",
    "face morphing",
    "flickering face",
    "temporal inconsistency",
    "frame-to-frame drift",
    "identity shift",
    "changing facial features",
    "身份漂移",
    "面部闪烁",
    "前后帧不一致",
    "人物换脸感",
)

EDIT_STRENGTH_PRESETS: dict[str, float] = {
    "soft": 0.25,
    "medium": 0.4,
    "strong": 0.65,
}


def append_consistency_negative(negative: str, *, enabled: bool = True) -> str:
    if not enabled:
        return str(negative or "").strip()
    base = str(negative or "").strip()
    extras = ", ".join(KEYFRAME_CONSISTENCY_NEGATIVE)
    if not base:
        return extras
    lowered = base.lower()
    missing = [term for term in KEYFRAME_CONSISTENCY_NEGATIVE if term.lower() not in lowered and term not in base]
    if not missing:
        return base
    return f"{base}, {', '.join(missing)}"


def _node(class_type: str, inputs: dict[str, Any]) -> dict[str, Any]:
    return {"class_type": class_type, "inputs": inputs}


def _has_node(object_info: dict[str, Any] | None, *names: str) -> bool:
    if not object_info:
        return False
    return any(name in object_info for name in names)


def _option_values(object_info: dict[str, Any] | None, node_name: str, input_name: str) -> list[Any]:
    if not object_info or node_name not in object_info:
        return []
    node_info = object_info.get(node_name) or {}
    required = node_info.get("input", {}).get("required") or {}
    optional = node_info.get("input", {}).get("optional") or {}
    spec = required.get(input_name) or optional.get(input_name)
    if not spec:
        return []
    if isinstance(spec, (list, tuple)) and spec and isinstance(spec[0], (list, tuple)):
        return list(spec[0])
    return []


def _pick_option(options: list[Any], preferred: tuple[str, ...] = (), fallback: Any = "") -> Any:
    normalized = [item for item in options if str(item).strip()]
    if not normalized:
        return fallback
    lowered = {str(item).lower(): item for item in normalized}
    for token in preferred:
        match = lowered.get(str(token).lower())
        if match is not None:
            return match
    return normalized[0]


def capability_payload(object_info: dict[str, Any] | None, base_dir: Path | str | None = None) -> dict[str, Any]:
    root = Path(base_dir) if base_dir else None
    controlnet_apply = _has_node(object_info, "ControlNetApplyAdvanced", "ControlNetApply")
    controlnet_loader = _has_node(object_info, "ControlNetLoader")
    controlnet_models: list[str] = []
    if controlnet_loader and object_info:
        controlnet_models = [str(item) for item in _option_values(object_info, "ControlNetLoader", "control_net_name")]
    controlnet_dir = root / "models" / "controlnet" if root else None
    if root and controlnet_dir and controlnet_dir.is_dir() and not controlnet_models:
        controlnet_models = sorted(
            path.name
            for path in controlnet_dir.iterdir()
            if path.is_file() and path.suffix.lower() in {".safetensors", ".pt", ".pth", ".bin"}
        )

    openpose_preprocessor = _has_node(object_info, "OpenposePreprocessor", "DWPreprocessor")
    detailer = _has_node(object_info, "FaceDetailer", "ReActorRestoreFace")
    regional = _has_node(object_info, "ConditioningSetArea", "ConditioningCombine")
    video_face_swap = (
        _has_node(object_info, "ReActorFaceSwap")
        and _has_node(object_info, "VHS_LoadVideo")
        and _has_node(object_info, "VHS_VideoCombine")
    )

    return {
        "controlnet": {
            "ready": bool(controlnet_loader and controlnet_apply),
            "loader": controlnet_loader,
            "apply": controlnet_apply,
            "models": controlnet_models,
            "note": "需上传 OpenPose 姿态图；无预处理器时直接使用姿态图作为 ControlNet 输入。",
        },
        "openpose_preprocessor": {
            "ready": openpose_preprocessor,
            "nodes": [name for name in ("OpenposePreprocessor", "DWPreprocessor") if _has_node(object_info, name)],
            "note": "可选；未安装时请上传已渲染的 OpenPose 姿态图。",
        },
        "detailer": {
            "ready": detailer,
            "nodes": [name for name in ("FaceDetailer", "ReActorRestoreFace") if _has_node(object_info, name)],
            "note": "Impact FaceDetailer 或 ReActorRestoreFace 可用时启用。",
        },
        "regional": {
            "ready": regional,
            "note": "使用 ConditioningSetArea + ConditioningCombine 分区提示词。",
        },
        "video_face_swap": {
            "ready": video_face_swap,
            "install_profile": "face-swap-reactor",
            "note": "VHS_LoadVideo → ReActorFaceSwap → VHS_VideoCombine。",
        },
        "secondary_lora": {
            "ready": True,
            "note": "图片工作流支持第二 LoRA 槽位（LoraLoaderModelOnly）。",
        },
    }


def build_video_face_swap_prompt(
    video_name: str,
    identity_image_name: str,
    object_info: dict[str, Any],
    *,
    faceswap_weight: float | str = 0.85,
    fps: int = 24,
    filename_prefix: str = "VideoFaceSwap",
    swap_model: str = "",
    detector: str = "",
    restore_model: str = "none",
    pick_option: Callable[..., Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """VHS_LoadVideo → ReActorFaceSwap → VHS_VideoCombine."""
    picker = pick_option or _pick_option
    missing = [
        name
        for name in ("VHS_LoadVideo", "ReActorFaceSwap", "VHS_VideoCombine")
        if name not in object_info
    ]
    if missing:
        raise ValueError(f"ComfyUI 缺少视频换脸节点：{', '.join(missing)}")

    swap_options = [
        item
        for item in _option_values(object_info, "ReActorFaceSwap", "swap_model")
        if str(item).strip().lower() not in {"", "none"}
    ]
    if not swap_options:
        raise ValueError("ReActor 没有识别到可用换脸模型")
    selected_swap = swap_model if swap_model in [str(item) for item in swap_options] else picker(
        swap_options, ("inswapper_128.onnx", "inswapper_128_fp16.onnx")
    )

    detector_options = _option_values(object_info, "ReActorFaceSwap", "facedetection")
    selected_detector = detector if detector in [str(item) for item in detector_options] else picker(
        detector_options, ("retinaface_resnet50", "retinaface_mobile0.25")
    )

    restore_options = _option_values(object_info, "ReActorFaceSwap", "face_restore_model")
    selected_restore = restore_model if restore_model in [str(item) for item in restore_options] else picker(
        restore_options, ("none",), "none"
    )

    weight_options = [str(item) for item in _option_values(object_info, "ReActorSetWeight", "faceswap_weight")]
    selected_weight: Any = "75%"
    if weight_options:
        if isinstance(faceswap_weight, str) and faceswap_weight in weight_options:
            selected_weight = faceswap_weight
        else:
            try:
                numeric = float(str(faceswap_weight).replace("%", "").strip())
                if numeric <= 1.0:
                    numeric *= 100.0
            except (TypeError, ValueError):
                numeric = 75.0

            def _weight_distance(item: str) -> float:
                try:
                    return abs(float(str(item).replace("%", "").strip()) - numeric)
                except (TypeError, ValueError):
                    return 999.0

            selected_weight = min(weight_options, key=_weight_distance)
    elif isinstance(faceswap_weight, str) and faceswap_weight.strip():
        selected_weight = faceswap_weight

    swap_inputs: dict[str, Any] = {
        "enabled": True,
        "input_image": ["1", 0],
        "swap_model": selected_swap,
        "facedetection": selected_detector,
        "face_restore_model": selected_restore,
        "face_restore_visibility": 0.85,
        "codeformer_weight": 0.5,
        "detect_gender_input": "no",
        "detect_gender_source": "no",
        "input_faces_index": "0",
        "source_faces_index": "0",
        "console_log_level": picker(_option_values(object_info, "ReActorFaceSwap", "console_log_level"), ("1",), 1),
    }
    nsfw_detection_options = _option_values(object_info, "ReActorFaceSwap", "nsfw_detection")
    if nsfw_detection_options:
        swap_inputs["nsfw_detection"] = picker(nsfw_detection_options, ("false", "False", "disable", "no", "off", False))

    graph: dict[str, Any] = {
        "1": _node(
            "VHS_LoadVideo",
            {
                "video": video_name,
                "force_rate": int(fps),
                "custom_width": 0,
                "custom_height": 0,
                "frame_load_cap": 0,
                "skip_first_frames": 0,
                "select_every_nth": 1,
            },
        ),
        "2": _node("LoadImage", {"image": identity_image_name}),
    }
    if "ReActorSetWeight" in object_info:
        graph["4"] = _node(
            "ReActorSetWeight",
            {
                "input_image": ["2", 0],
                "source_image": ["2", 0],
                "faceswap_weight": selected_weight,
            },
        )
        swap_inputs["face_model"] = ["4", 1]
    else:
        swap_inputs["source_image"] = ["2", 0]
    graph["3"] = _node("ReActorFaceSwap", swap_inputs)
    graph["5"] = _node(
        "VHS_VideoCombine",
        {
            "images": ["3", 0],
            "audio": ["1", 2],
            "frame_rate": int(fps),
            "loop_count": 0,
            "filename_prefix": filename_prefix,
            "format": "video/h264-mp4",
            "pix_fmt": "yuv420p",
            "crf": 19,
            "save_metadata": True,
            "trim_to_audio": False,
            "pingpong": False,
            "save_output": True,
        },
    )
    resolved = {
        "swap_model": str(selected_swap),
        "detector": str(selected_detector),
        "restore_model": str(selected_restore),
        "faceswap_weight": str(selected_weight),
    }
    return graph, resolved


def apply_face_detailer(
    graph: dict[str, Any],
    object_info: dict[str, Any] | None,
    *,
    image_node: str,
    save_node: str,
    base_node_id: int = 300,
) -> dict[str, Any]:
    """Insert ReActorRestoreFace between decoded image and SaveImage when available."""
    if not object_info or "ReActorRestoreFace" not in object_info:
        return graph
    if image_node not in graph or save_node not in graph:
        return graph
    detector = _pick_option(
        _option_values(object_info, "ReActorRestoreFace", "facedetection"),
        ("retinaface_resnet50", "retinaface_mobile0.25"),
    )
    model = _pick_option(
        _option_values(object_info, "ReActorRestoreFace", "model"),
        ("GFPGANv1.4.onnx",),
        "GFPGANv1.4.onnx",
    )
    if str(model).lower() in {"", "none"}:
        return graph
    detail_id = str(base_node_id)
    graph[detail_id] = _node(
        "ReActorRestoreFace",
        {
            "image": [image_node, 0],
            "facedetection": detector,
            "model": model,
            "visibility": 0.75,
            "codeformer_weight": 0.5,
        },
    )
    save_inputs = graph[save_node].get("inputs") or {}
    if save_inputs.get("images") == [image_node, 0]:
        save_inputs["images"] = [detail_id, 0]
    return graph


def _rewire_positive_references(graph: dict[str, Any], old_positive: str, new_positive: str) -> None:
    old_ref: list[Any] = [old_positive, 0]
    new_ref: list[Any] = [new_positive, 0]
    for node in graph.values():
        inputs = node.get("inputs") or {}
        for key, value in list(inputs.items()):
            if value == old_ref:
                inputs[key] = new_ref
            elif isinstance(value, list) and len(value) == 2 and value[0] == old_positive and value[1] == 0:
                inputs[key] = new_ref


def apply_regional_conditioning(
    graph: dict[str, Any],
    *,
    positive_node: str,
    clip_node: list[Any],
    face_prompt: str,
    body_prompt: str,
    width: int,
    height: int,
    base_node_id: int = 200,
) -> dict[str, Any]:
    face = str(face_prompt or "").strip()
    body = str(body_prompt or "").strip()
    if not face and not body:
        return graph
    if not face or not body:
        target = face or body
        if positive_node in graph:
            graph[positive_node]["inputs"]["text"] = target
        return graph

    area_height = max(64, int(int(height) * 0.4))
    body_id = str(base_node_id)
    face_id = str(base_node_id + 1)
    area_id = str(base_node_id + 2)
    combine_id = str(base_node_id + 3)

    graph[body_id] = _node("CLIPTextEncode", {"clip": clip_node, "text": body})
    graph[face_id] = _node("CLIPTextEncode", {"clip": clip_node, "text": face})
    graph[area_id] = _node(
        "ConditioningSetArea",
        {
            "conditioning": [face_id, 0],
            "width": int(width),
            "height": area_height,
            "x": 0,
            "y": 0,
            "strength": 1.0,
        },
    )
    graph[combine_id] = _node(
        "ConditioningCombine",
        {
            "conditioning_1": [body_id, 0],
            "conditioning_2": [area_id, 0],
        },
    )
    _rewire_positive_references(graph, positive_node, combine_id)
    graph.pop(positive_node, None)
    return graph


def apply_secondary_lora(
    graph: dict[str, Any],
    model_source: list[Any],
    lora_name: str,
    strength: float,
    node_id: str,
) -> list[Any]:
    name = str(lora_name or "").strip()
    if not name:
        return model_source
    graph[node_id] = _node(
        "LoraLoaderModelOnly",
        {
            "model": model_source,
            "lora_name": name,
            "strength_model": max(0.0, min(2.0, float(strength))),
        },
    )
    return [node_id, 0]


def apply_controlnet_pose(
    graph: dict[str, Any],
    *,
    image_node: str,
    positive: str,
    negative: str,
    controlnet_name: str,
    strength: float = 0.7,
    base_node_id: int = 210,
) -> dict[str, Any]:
    """Apply ControlNet using a user-supplied OpenPose map (no preprocessor).

    Without OpenposePreprocessor/DWPreprocessor the caller must upload a pose map image.
    """
    name = str(controlnet_name or "").strip()
    if not name or image_node not in graph:
        return graph
    apply_class = "ControlNetApplyAdvanced"
    loader_id = str(base_node_id)
    apply_id = str(base_node_id + 1)
    graph[loader_id] = _node("ControlNetLoader", {"control_net_name": name})
    apply_inputs: dict[str, Any] = {
        "positive": [positive, 0],
        "negative": [negative, 0],
        "control_net": [loader_id, 0],
        "image": [image_node, 0],
        "strength": max(0.0, min(2.0, float(strength))),
    }
    for optional_key, default in (("start_percent", 0.0), ("end_percent", 1.0)):
        apply_inputs.setdefault(optional_key, default)
    graph[apply_id] = _node(apply_class, apply_inputs)
    _rewire_positive_references(graph, positive, apply_id)
    return graph


def expand_prompt_from_style(prompt: str, style_preset: str, *, style_map: dict[str, dict[str, Any]] | None = None) -> str:
    """Soft template enrichment — no external LLM."""
    from beginner_frontend.image_studio import STYLE_PRESET_MAP, clean_prompt_text

    presets = style_map or STYLE_PRESET_MAP
    style = presets.get(style_preset) or presets.get("photo") or {}
    language = "en" if not any("\u4e00" <= ch <= "\u9fff" for ch in prompt) else "zh"
    clause = str((style.get("prompt_en") if language == "en" else style.get("prompt")) or "").strip()
    if not clause:
        if language == "en":
            clause = "balanced composition, natural lighting, coherent depth, polished detail"
        else:
            clause = "构图均衡，光影自然，景深合理，细节完整"
    base = clean_prompt_text(prompt)
    if clause in base:
        return base
    if language == "en":
        return f"{base}, {clause}" if base else clause
    return f"{base}。{clause.rstrip('。')}" if base else clause
