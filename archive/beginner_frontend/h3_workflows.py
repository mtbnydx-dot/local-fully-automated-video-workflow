"""CPU-only H3 graph extensions. No runtime/model imports or implicit fallbacks."""

from copy import deepcopy
from typing import Any

H3_MODES = {"minimax_h3_t2v", "minimax_h3_i2v", "minimax_h3_r2v"}
CONTROL_MODEL = "minimax_h3_fun_controlnet_union_pruned_int8_convrot.safetensors"
UPSCALE_MODEL = "minimax_h3_latent_upscaler_3d_conv_v1_bf16.safetensors"


def requirement_errors(mode: str, adv: dict, *, control=False, source=False, mask=False) -> list[str]:
    if mode not in H3_MODES:
        return []
    task = adv.get("h3_task", "generate")
    upscale = adv.get("h3_latent_upscale", False)
    errors = []
    if (task != "generate" or upscale) and adv.get("h3_acceleration_profile", "native") != "native":
        errors.append("动作控制、局部重绘和潜空间超分目前只支持原生档；请先切回原生，不叠加 LightX / Spectrum。")
    if task != "generate" and mode == "minimax_h3_r2v":
        errors.append("Fun ControlNet 仅适用于 FL2VA；请切换 H3 文字或首帧生视频。")
    if task != "generate" and upscale:
        errors.append("控制 / 重绘暂不与潜空间超分叠加；请关闭潜空间超分，生成后可在清晰度增强步骤处理。")
    if task == "control" and not control:
        errors.append("动作控制需要上传控制视频；Canny 可直接用普通视频，姿态 / 深度模式需要预处理后的控制图视频。")
    if task == "inpaint" and not (source and mask):
        errors.append("局部重绘需要原视频和黑白遮罩；白色重绘、黑色保留，遮罩可以是图片或逐帧视频。")
    if task != "generate" and adv.get("h3_control_start", 0) >= adv.get("h3_control_end", 1):
        errors.append("控制开始比例必须小于结束比例。")
    return errors


def runtime_errors(graph: dict, object_info: dict | None) -> list[str]:
    errors = []
    for item in graph.values():
        if item.get("class_type") != "ModelAttentionBackend" or not object_info:
            continue
        descriptor = object_info.get("ModelAttentionBackend", {}).get("input", {}).get("required", {}).get("attention", [])
        choices = descriptor[0] if descriptor and isinstance(descriptor[0], list) else (
            descriptor[1].get("options", []) if len(descriptor) > 1 else []
        )
        if item["inputs"]["attention"] not in choices:
            errors.append("当前 ComfyUI 未提供所选 Attention 后端；INT8 需要可用的 Comfy Kitchen 内核。请切回原生或 PyTorch，不会静默降级。")
    return errors


def dimensions(width: int, height: int, factor: float) -> dict[str, list[int]]:
    low = [max(32, int(value / factor / 32 + 0.5) * 32) for value in (width, height)]
    delivery = [1920, 1080] if (width, height) == (1920, 1088) else (
        [1080, 1920] if (width, height) == (1088, 1920) else [width, height]
    )
    return {"base": low, "target": [width, height], "delivery": delivery}


def apply_extensions(graph: dict, mode: str, adv: dict, *, control_name="", source_name="",
                     mask_name="", mask_is_video=False, source_has_audio=False) -> dict[str, Any]:
    if mode not in H3_MODES:
        return graph
    graph = deepcopy(graph)
    task = adv.get("h3_task", "generate")
    errors = requirement_errors(mode, adv, control=bool(control_name), source=bool(source_name), mask=bool(mask_name))
    if errors:
        raise ValueError("\n".join(errors))
    width, height, length = (graph["5"]["inputs"][key] for key in ("width", "height", "length"))

    def add(key, kind, **inputs):
        graph[str(key)] = {"class_type": kind, "inputs": inputs}
        return [str(key), 0]

    def video(key, name):
        return add(key, "VHS_LoadVideo", video=name, force_rate=24, custom_width=width,
                   custom_height=height, frame_load_cap=length, skip_first_frames=0,
                   select_every_nth=1, format="None")

    model = graph["9"]["inputs"]["model"]
    attention = adv.get("h3_attention_backend", "native")
    if attention != "native":
        model = add(180, "ModelAttentionBackend", model=model,
                    attention="comfy kitchen attention" if attention == "kitchen_int8" else "pytorch attention")

    if task in {"control", "inpaint"}:
        patch = add(181, "ModelPatchLoader", name=CONTROL_MODEL)
        control_inputs = {}
        if task == "control":
            images = video(182, control_name)
            if adv.get("h3_control_type", "canny") == "canny":
                images = add(183, "Canny", image=images, low_threshold=0.4, high_threshold=0.8)
            control_inputs["control_video"] = images
        else:
            original = video(182, source_name)
            mask_images = video(183, mask_name) if mask_is_video else add(183, "LoadImage", image=mask_name)
            mask_images = add(184, "ImageScale", image=mask_images, upscale_method="nearest-exact",
                              width=width, height=height, crop="center")
            mask = add(185, "ImageToMask", image=mask_images, channel="red")
            control_inputs.update(source_video=original, mask=mask)
            # Re-composite to keep untouched pixels, not just a soft model suggestion.
            composite = add(187, "ImageCompositeMasked", destination=original, source=["11", 0],
                            x=0, y=0, resize_source=False, mask=mask)
            if "16" in graph:
                graph["16"]["inputs"]["image"] = composite
            else:
                graph["12"]["inputs"]["images"] = composite
            if adv.get("h3_preserve_source_audio", True):
                graph["12"]["inputs"].pop("audio", None)
                if source_has_audio:
                    graph["12"]["inputs"]["audio"] = ["182", 2]
        model = add(186, "MiniMaxH3FunControlNetApply", model=model, model_patch=patch, vae=["3", 0],
                    strength=adv["h3_control_strength"], start_percent=adv["h3_control_start"],
                    end_percent=adv["h3_control_end"], **control_inputs)

    graph["8"]["inputs"]["model"] = model
    graph["9"]["inputs"]["model"] = model
    if adv.get("h3_latent_upscale", False):
        size = dimensions(width, height, adv["h3_upscale_factor"])
        graph["195"] = deepcopy(graph["5"])
        graph["5"]["inputs"].update(zip(("width", "height"), size["base"]))
        video_latent = add(190, "LTXVSeparateAVLatent", av_latent=["10", 1])
        upscaled = add(191, "MinimaxH3LatentUpscaler3D", latent=video_latent, model_name=UPSCALE_MODEL,
                       mode="target dimensions", **{"mode.width": width, "mode.height": height},
                       align=32, enable_temporal_chunking=True, force_unload=True, device="cuda", precision="bf16")
        zero_mask = add(192, "SolidMask", value=0.0, width=32, height=32)
        audio = add(193, "SetLatentNoiseMask", samples=["190", 1], mask=zero_mask)
        av = add(194, "LTXVConcatAVLatent", video_latent=upscaled, audio_latent=audio)
        sigmas = add(196, "BasicScheduler", model=model, scheduler=graph["8"]["inputs"]["scheduler"],
                     steps=adv["h3_refine_steps"], denoise=adv["h3_refine_denoise"])
        guider = add(197, "BasicGuider", model=model, conditioning=["195", 0])
        refined = add(198, "SamplerCustomAdvanced", noise=["6", 0], guider=guider, sampler=["7", 0],
                      sigmas=sigmas, latent_image=av)
        graph["11"]["inputs"]["samples"] = refined
        # Audio output stays on node 15 / first pass; never re-synthesized for delivery.
    suffix = {"control": "_Control", "inpaint": "_Inpaint"}.get(task, "")
    if adv.get("h3_latent_upscale"):
        suffix += "_LatentUpscale"
    graph["13"]["inputs"]["filename_prefix"] += suffix
    return graph
