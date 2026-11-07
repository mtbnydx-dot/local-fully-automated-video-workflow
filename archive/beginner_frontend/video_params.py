"""视频工作流可调参数的声明式注册表。

平台要接入的视频工作流来源很杂（本地模型、ComfyUI 原生节点和外部工作流），所以
"某个模型支持哪些参数、输入和输出"必须是数据而不是代码分支：

  * ``PARAM_SPECS``  描述参数本身：类型、范围、默认值、给用户看的中文说明。
  * ``MODE_PARAMS``  描述某个 mode 用到哪些参数，以及该 mode 下的默认值/选项覆盖。

新增一个引擎 = 往这两张表里加条目 + 写一个 builder。不需要改 ``/api/generate`` 的签名，
不需要在 ``index.html`` 里加输入框，也不需要改 ``app.js`` —— 前端是照着
``param_schema()`` 吐出来的 schema 动态渲染的。

写 help / recommend 文案的约定（面向没调过参的用户）：
  * ``help``      说清楚"这是什么、调它会发生什么"，别只写节点名。
  * ``recommend`` 说清楚"什么时候该动它、往哪个方向动"，没有明确建议就留空。
"""

from __future__ import annotations

import json
from typing import Any

# ComfyUI 内置采样器/调度器里适合视频的子集。这里保持保守：提交前
# graph_node_schema_errors() 还会拿真实的 /object_info 再校验一次，
# 所以这份列表只负责"别给用户列一堆不该用的"，不负责当唯一真相。
KSAMPLER_SAMPLERS = [
    "euler",
    "euler_ancestral",
    "dpmpp_2m",
    "dpmpp_2m_sde",
    "dpmpp_sde",
    "uni_pc",
    "uni_pc_bh2",
    "ddim",
    "lcm",
    "res_multistep",
]
SCHEDULERS = [
    "simple",
    "normal",
    "karras",
    "exponential",
    "sgm_uniform",
    "beta",
    "ddim_uniform",
]
LTX_SAMPLERS = [
    "euler_ancestral_cfg_pp",
    "euler_cfg_pp",
    "euler",
    "euler_ancestral",
    "res_multistep",
    "dpmpp_2m",
]
# VideoHelperSuite 的 h264-mp4 预设里 pix_fmt 只有这两个取值（见
# custom_nodes/ComfyUI-VideoHelperSuite/video_formats/h264-mp4.json）。
VHS_PIX_FMTS = ["yuv420p", "yuv420p10le"]

GROUP_LABELS = {
    "cloud": "云端服务",
    "optimization": "社区优化档位",
    "h3_creative": "H3 创作控制（实验）",
    "reference": "参考素材",
    "sampling": "采样与调度",
    "stage": "分段与阶段",
    "lora": "LoRA 强度",
    "memory": "显存与解码",
    "restoration": "视频修复",
    "output": "输出与编码",
}

# Keep each distilled checkpoint and its trained schedule together.
# Source: https://github.com/ModelTC/Minimax-H3-Turbo#1-model-specs
H3_RUNTIME_PROFILES: dict[str, dict[str, Any]] = {
    "spectrum_balanced": {
        "label": "Spectrum 均衡（20 步）", "steps": 20,
        "sampler": "res_multistep", "scheduler": "simple",
        "shift_video": 12.0, "shift_audio": 3.0,
        "required_node": "SpectrumApplyMiniMaxH3", "spectrum": True,
    },
    "lightx8_v10": {
        "label": "LightX 8 步 v1.0（旧版 544P）", "steps": 8,
        "sampler": "euler", "scheduler": "simple",
        "shift_video": 12.0, "shift_audio": 3.0,
        "asset_id": "minimax_h3_lightx8_v10",
        "lora_name": "minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors",
    },
    "lightx8_v10_768p": {
        "label": "LightX 8 步 v1.0（768P）", "steps": 8,
        "sampler": "euler", "scheduler": "simple",
        "shift_video": 6.0, "shift_audio": 3.0,
        "asset_id": "minimax_h3_lightx8_v10_768p",
        "lora_name": "minimax_h3_fl2v_turbo_8step_v1.0_768p_comfyui_bf16.safetensors",
    },
    "lightx4_v11_768p": {
        "label": "LightX 4 步 v1.1（768P，保留版）", "steps": 4,
        "sampler": "euler", "scheduler": "simple",
        "shift_video": 6.0, "shift_audio": 3.0,
        "asset_id": "minimax_h3_lightx4_v11_768p",
        "lora_name": "minimax_h3_fl2v_turbo_4step_v1.1_768p_comfyui_bf16.safetensors",
    },
    "lightx4_v12_768p": {
        "label": "LightX 4 步 v1.2（768P）", "steps": 4,
        "sampler": "euler", "scheduler": "simple",
        "shift_video": 6.0, "shift_audio": 3.0,
        "asset_id": "minimax_h3_lightx4_v12_768p",
        "lora_name": "minimax_h3_fl2v_turbo_4step_v1.2_768p_comfyui_bf16.safetensors",
    },
    "lightx_ref4_v01": {
        "label": "LightX Reference 4 步 v0.1（544P，实验）", "steps": 4,
        "sampler": "euler", "scheduler": "simple",
        "shift_video": 12.0, "shift_audio": 3.0,
        "asset_id": "minimax_h3_ref_lightx4_v01",
        "lora_name": "minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors",
    },
}

# 模型能力是前端联动和后端校验的共同事实来源。接入新引擎时，在这里声明
# 输入类型、音频、帧率和帧数约束，前端无需再按具体模型 ID 写判断。
_DEFAULT_MODE_CAPABILITIES: dict[str, Any] = {
    "kind": "other",
    "engine": "generic",
    "engine_label": "通用",
    "text_to_video": False,
    "image_to_video": False,
    "image_input": "none",
    "first_frame": False,
    "last_frame": False,
    "native_audio": False,
    "fixed_fps": None,
    "frame_rule": "",
    "frame_step": 1,
    "frame_offset": 0,
    "min_frames": 1,
    "max_frames": 481,
    "max_dimension": 1536,
    "resolution_presets": [],
    "reference_images": 0,
    "reference_videos": 0,
    "reference_audios": 0,
    "smoke_test": False,
}


def _generation_capabilities(
    *,
    engine: str,
    engine_label: str,
    text: bool = False,
    image: bool = False,
    image_input: str = "none",
    last_frame: bool = False,
    native_audio: bool = False,
    fixed_fps: int | None = None,
    frame_rule: str = "4n+1",
    frame_step: int = 4,
    frame_offset: int = 1,
    min_frames: int = 17,
    max_frames: int = 481,
    max_dimension: int = 1536,
    resolution_presets: list[dict[str, Any]] | None = None,
    reference_images: int = 0,
    reference_videos: int = 0,
    reference_audios: int = 0,
    smoke_test: bool | None = None,
) -> dict[str, Any]:
    return {
        "kind": "generation",
        "engine": engine,
        "engine_label": engine_label,
        "text_to_video": text,
        "image_to_video": image,
        "image_input": image_input,
        "first_frame": image,
        "last_frame": last_frame,
        "native_audio": native_audio,
        "fixed_fps": fixed_fps,
        "frame_rule": frame_rule,
        "frame_step": frame_step,
        "frame_offset": frame_offset,
        "min_frames": min_frames,
        "max_frames": max_frames,
        "max_dimension": max_dimension,
        "resolution_presets": resolution_presets or [],
        "reference_images": max(0, int(reference_images)),
        "reference_videos": max(0, int(reference_videos)),
        "reference_audios": max(0, int(reference_audios)),
        "smoke_test": text if smoke_test is None else smoke_test,
    }


MODE_CAPABILITIES: dict[str, dict[str, Any]] = {
    "ti2v_5b": _generation_capabilities(
        engine="wan22",
        engine_label="Wan2.2",
        text=True,
        image=True,
        image_input="optional",
        resolution_presets=[
            {"label": "480P 横屏", "width": 832, "height": 480},
            {"label": "720P 横屏", "width": 1280, "height": 704},
            {"label": "720P 竖屏", "width": 704, "height": 1280},
        ],
    ),
    "i2v_a14b": _generation_capabilities(
        engine="wan22",
        engine_label="Wan2.2",
        image=True,
        image_input="required",
        last_frame=True,
        resolution_presets=[
            {"label": "480P 横屏", "width": 832, "height": 480},
            {"label": "720P 横屏", "width": 1280, "height": 704},
            {"label": "720P 竖屏", "width": 704, "height": 1280},
        ],
    ),
    "t2v_a14b": _generation_capabilities(
        engine="wan22",
        engine_label="Wan2.2",
        text=True,
        resolution_presets=[
            {"label": "480P 横屏", "width": 832, "height": 480},
            {"label": "720P 横屏", "width": 1280, "height": 704},
            {"label": "720P 竖屏", "width": 704, "height": 1280},
        ],
    ),
    "ltx_i2v": _generation_capabilities(
        engine="ltx098",
        engine_label="LTXV 0.9.8",
        image=True,
        image_input="required",
        frame_rule="8n+1",
        frame_step=8,
        min_frames=9,
        resolution_presets=[
            {"label": "低负载横屏", "width": 512, "height": 320},
            {"label": "480P 横屏", "width": 832, "height": 480},
            {"label": "480P 竖屏", "width": 480, "height": 832},
        ],
    ),
    "ltx_t2v": _generation_capabilities(
        engine="ltx098",
        engine_label="LTXV 0.9.8",
        text=True,
        frame_rule="8n+1",
        frame_step=8,
        min_frames=9,
        resolution_presets=[
            {"label": "低负载横屏", "width": 512, "height": 320},
            {"label": "480P 横屏", "width": 832, "height": 480},
            {"label": "480P 竖屏", "width": 480, "height": 832},
        ],
    ),
    "ltx23_i2v": _generation_capabilities(
        engine="ltx23",
        engine_label="LTX-Video 2.3",
        image=True,
        image_input="required",
        native_audio=True,
        frame_rule="8n+1",
        frame_step=8,
        min_frames=9,
        resolution_presets=[
            {"label": "试镜横屏", "width": 512, "height": 320},
            {"label": "质量横屏", "width": 768, "height": 512},
            {"label": "质量竖屏", "width": 512, "height": 768},
        ],
    ),
    "ltx23_t2v": _generation_capabilities(
        engine="ltx23",
        engine_label="LTX-Video 2.3",
        text=True,
        native_audio=True,
        frame_rule="8n+1",
        frame_step=8,
        min_frames=9,
        resolution_presets=[
            {"label": "试镜横屏", "width": 512, "height": 320},
            {"label": "质量横屏", "width": 768, "height": 512},
            {"label": "质量竖屏", "width": 512, "height": 768},
        ],
    ),
    "ltx25_i2v": _generation_capabilities(
        engine="ltx25",
        engine_label="LTX-Video 2.5",
        image=True,
        image_input="required",
        last_frame=True,
        native_audio=True,
        frame_rule="8n+1",
        frame_step=8,
        min_frames=9,
        max_dimension=2048,
        resolution_presets=[
            {"label": "低负载试镜", "width": 640, "height": 352},
            {"label": "720P 横屏", "width": 1280, "height": 704},
            {"label": "720P 竖屏", "width": 704, "height": 1280},
            {"label": "1080P 画布（实验）", "width": 1920, "height": 1088},
        ],
    ),
    "ltx25_t2v": _generation_capabilities(
        engine="ltx25",
        engine_label="LTX-Video 2.5",
        text=True,
        native_audio=True,
        frame_rule="8n+1",
        frame_step=8,
        min_frames=9,
        max_dimension=2048,
        resolution_presets=[
            {"label": "低负载试镜", "width": 640, "height": 352},
            {"label": "720P 横屏", "width": 1280, "height": 704},
            {"label": "720P 竖屏", "width": 704, "height": 1280},
            {"label": "1080P 画布（实验）", "width": 1920, "height": 1088},
        ],
    ),
    "hunyuan15_i2v": _generation_capabilities(
        engine="hunyuan15",
        engine_label="HunyuanVideo 1.5",
        image=True,
        image_input="required",
        resolution_presets=[
            {"label": "480P 横屏", "width": 832, "height": 480},
            {"label": "720P 横屏", "width": 1280, "height": 704},
            {"label": "720P 竖屏", "width": 704, "height": 1280},
        ],
    ),
    "hunyuan15_t2v": _generation_capabilities(
        engine="hunyuan15",
        engine_label="HunyuanVideo 1.5",
        text=True,
        resolution_presets=[
            {"label": "480P 横屏", "width": 832, "height": 480},
            {"label": "720P 横屏", "width": 1280, "height": 704},
            {"label": "720P 竖屏", "width": 704, "height": 1280},
        ],
    ),
    "minimax_h3_i2v": _generation_capabilities(
        engine="minimax_h3",
        engine_label="MiniMax H3",
        image=True,
        image_input="required",
        last_frame=True,
        native_audio=True,
        fixed_fps=24,
        frame_rule="17n+5",
        frame_step=17,
        frame_offset=5,
        min_frames=22,
        max_frames=362,
        max_dimension=2048,
        resolution_presets=[
            {"label": "试镜横屏", "width": 864, "height": 480},
            {"label": "质量横屏", "width": 1344, "height": 768},
            {"label": "质量竖屏", "width": 768, "height": 1344},
            {"label": "1080P 实验横屏", "width": 1920, "height": 1088},
        ],
    ),
    "minimax_h3_t2v": _generation_capabilities(
        engine="minimax_h3",
        engine_label="MiniMax H3",
        text=True,
        native_audio=True,
        fixed_fps=24,
        frame_rule="17n+5",
        frame_step=17,
        frame_offset=5,
        min_frames=22,
        max_frames=362,
        max_dimension=2048,
        resolution_presets=[
            {"label": "试镜横屏", "width": 864, "height": 480},
            {"label": "质量横屏", "width": 1344, "height": 768},
            {"label": "质量竖屏", "width": 768, "height": 1344},
            {"label": "1080P 实验横屏", "width": 1920, "height": 1088},
        ],
    ),
    "minimax_h3_r2v": _generation_capabilities(
        engine="minimax_h3",
        engine_label="MiniMax H3",
        text=True,
        native_audio=True,
        fixed_fps=24,
        frame_rule="17n+5",
        frame_step=17,
        frame_offset=5,
        min_frames=22,
        max_frames=362,
        max_dimension=2048,
        reference_images=9,
        reference_videos=3,
        reference_audios=3,
        resolution_presets=[
            {"label": "试镜横屏", "width": 864, "height": 480},
            {"label": "质量横屏", "width": 1344, "height": 768},
            {"label": "质量竖屏", "width": 768, "height": 1344},
            {"label": "1080P 实验横屏", "width": 1920, "height": 1088},
        ],
    ),
    "fal_h3_max_i2v": _generation_capabilities(
        engine="fal_h3_max",
        engine_label="H3 Max（fal 云端）",
        image=True,
        image_input="required",
        last_frame=True,
        native_audio=True,
        fixed_fps=24,
        frame_rule="",
        frame_step=1,
        min_frames=120,
        max_frames=360,
        max_dimension=1344,
        smoke_test=False,
        resolution_presets=[
            {"label": "480P 横屏", "width": 832, "height": 480},
            {"label": "768P 横屏", "width": 1344, "height": 768},
            {"label": "768P 竖屏", "width": 768, "height": 1344},
        ],
    ),
    "fal_h3_max_t2v": _generation_capabilities(
        engine="fal_h3_max",
        engine_label="H3 Max（fal 云端）",
        text=True,
        native_audio=True,
        fixed_fps=24,
        frame_rule="",
        frame_step=1,
        min_frames=120,
        max_frames=360,
        max_dimension=1344,
        smoke_test=False,
        resolution_presets=[
            {"label": "480P 横屏", "width": 832, "height": 480},
            {"label": "768P 横屏", "width": 1344, "height": 768},
            {"label": "768P 竖屏", "width": 768, "height": 1344},
        ],
    ),
    "deflicker": {"kind": "postprocess", "engine": "ffmpeg", "engine_label": "FFmpeg"},
    "rife_2x": {"kind": "postprocess", "engine": "rife", "engine_label": "RIFE"},
    "upscale_2x": {"kind": "postprocess", "engine": "upscale", "engine_label": "视频超分"},
    "upscale_seedvr2": {"kind": "postprocess", "engine": "seedvr2", "engine_label": "SeedVR2 时序超分"},
}


def mode_capabilities(mode: str) -> dict[str, Any]:
    capabilities = dict(_DEFAULT_MODE_CAPABILITIES)
    capabilities.update(MODE_CAPABILITIES.get(mode) or {})
    capabilities["mode"] = mode
    return capabilities


def capability_labels(mode: str) -> list[str]:
    capabilities = mode_capabilities(mode)
    labels: list[str] = []
    if capabilities["text_to_video"] and capabilities["image_to_video"]:
        labels.append("文字 / 图片输入")
    elif capabilities["text_to_video"]:
        labels.append("文字生视频")
    elif capabilities["image_to_video"]:
        labels.append("图生视频")
    if capabilities["last_frame"]:
        labels.append("支持首尾帧")
    if capabilities["native_audio"]:
        labels.append("原生音频")
    reference_count = (
        int(capabilities.get("reference_images") or 0)
        + int(capabilities.get("reference_videos") or 0)
        + int(capabilities.get("reference_audios") or 0)
    )
    if reference_count:
        labels.append("多参考素材")
    if capabilities["fixed_fps"]:
        labels.append(f"固定 {capabilities['fixed_fps']} FPS")
    if capabilities["frame_rule"]:
        labels.append(f"帧数 {capabilities['frame_rule']}")
    return labels


def generation_modes() -> set[str]:
    return {mode for mode in MODE_CAPABILITIES if mode_capabilities(mode)["kind"] == "generation"}


def required_image_modes() -> set[str]:
    return {mode for mode in generation_modes() if mode_capabilities(mode)["image_input"] == "required"}


def smoke_test_modes() -> set[str]:
    return {mode for mode in generation_modes() if mode_capabilities(mode)["smoke_test"]}


END_IMAGE_MODES = frozenset(mode for mode in generation_modes() if mode_capabilities(mode)["last_frame"])


def supports_end_image(mode: str) -> bool:
    return bool(mode_capabilities(mode)["last_frame"])

# ---------------------------------------------------------------------------
# 参数目录
# ---------------------------------------------------------------------------

PARAM_SPECS: dict[str, dict[str, Any]] = {
    "fal_prompt_expansion_mode": {
        "type": "select",
        "label": "fal 提示词扩写",
        "group": "cloud",
        "default": "balanced",
        "choices": ["disabled", "balanced", "quality"],
        "choice_labels": {
            "disabled": "关闭（原样发送）",
            "balanced": "均衡（推荐，约 1 秒）",
            "quality": "质量优先（最多约 30 秒）",
        },
        "help": "由 fal 在云端整理提示词，不会调用本机文本模型，也不会占用本机显存。",
        "recommend": "日常使用 balanced；已经写好精细分镜提示词时选 disabled。",
    },
    "fal_safety_checker": {
        "type": "bool",
        "label": "fal 安全检查",
        "group": "cloud",
        "default": True,
        "help": "使用 fal 端点的内容安全检查。服务商策略独立于本地工作台设置。",
        "recommend": "保持开启。",
    },
    # ---- 社区优化档位 -----------------------------------------------------
    "h3_acceleration_profile": {
        "type": "select",
        "label": "H3 运行档位",
        "group": "optimization",
        "default": "native",
        "choices": ["native", "spectrum_balanced", "lightx8_v10_768p", "lightx4_v12_768p", "lightx4_v11_768p", "lightx8_v10"],
        "choice_labels": {
            "native": "原生保真（沿用当前参数）",
            **{key: value["label"] for key, value in H3_RUNTIME_PROFILES.items()},
        },
        "help": "原生档使用手动参数；其他档位锁定配套步数、采样器、调度器、音视频 shift 和完整去噪。544P 与 768P LoRA 是不同文件，不能互换。",
        "recommend": "正式镜头先用原生或 768P 8 步；4 步用于试镜。已安装不代表效果已验证，缺文件时先在下载中心安装对应 LoRA。",
    },
    "h3_turbo_strength": {
        "type": "number",
        "label": "LightX Turbo 强度",
        "group": "optimization",
        "default": 1.0,
        "min": 0.5,
        "max": 1.5,
        "step": 0.05,
        "help": "只在 LightX 蒸馏档生效。强度越高，模型越贴近少步蒸馏轨迹，也可能带来更重的对比度、鬼影或音频瑕疵。",
        "recommend": "先用作者基准 1.0。画面明显发虚时可小步试到 1.1~1.2，每次固定同一提示词和种子比较。",
    },
    "h3_prompt_format": {
        "type": "select",
        "label": "H3 提示词结构",
        "group": "optimization",
        "default": "original",
        "choices": ["original", "official_three_part"],
        "choice_labels": {
            "original": "保持原文",
            "official_three_part": "自动整理为官方三段式",
        },
        "help": "把普通描述整理为画面时间线、环境声、非剧情配乐三个字段。已经写好 integrated_multimodal_description 等字段时不会重复包装。",
        "recommend": "提示词经常漏掉声音或镜头结构时开启；已有精细 H3 提示词保持原文。自动整理不会调用云端模型。",
    },
    "h3_tiled_decode": {
        "type": "bool",
        "label": "H3 分块 VAE 解码",
        "group": "memory",
        "default": False,
        "help": "把视频 VAE 按空间与时间小块解码，显著降低解码峰值显存，但会增加解码时间，极端参数下可能出现块边界。",
        "recommend": "96GB 默认关闭。48GB 或长片在采样完成后解码爆显存时开启；它不会降低 H3 主模型采样显存。",
    },
    "h3_reference_size": {
        "type": "select",
        "label": "参考图解析精度",
        "group": "reference",
        "default": "match",
        "choices": ["match", "max"],
        "choice_labels": {
            "match": "匹配生成画布（推荐）",
            "max": "最高身份保真（更慢）",
        },
        "help": "R2V 专用。match 会把参考图按生成画布面积缩小；max 最多保留 2048px 短边，身份细节更强，但参考 token 会贯穿全部采样步骤。",
        "recommend": "先用 match。只有人物脸部或服装标识保持不住时再用 max，并先跑 2-3 秒短镜头。",
    },
    # ---- 采样与调度 -------------------------------------------------------
    "sampler_name": {
        "type": "select",
        "label": "采样器 Sampler",
        "group": "sampling",
        "default": "euler",
        "choices": KSAMPLER_SAMPLERS,
        "help": "决定每一步怎么从噪声里「猜」出画面。不同采样器的质感差别很明显：euler 最稳最可预测，dpmpp 系列细节更多但更吃步数。",
        "recommend": "4~8 步的加速档必须用 euler，换别的会糊。步数提到 20 以上再考虑 dpmpp_2m。",
    },
    "scheduler": {
        "type": "select",
        "label": "调度器 Scheduler",
        "group": "sampling",
        "default": "simple",
        "choices": SCHEDULERS,
        "help": "控制噪声按什么曲线往下降。simple 是均匀下降，karras 在后段留更多步数给细节。",
        "recommend": "低步数保持 simple。步数 25 以上、想要更多皮肤/布料细节时可以试 karras 或 beta。",
    },
    "shift": {
        "type": "number",
        "label": "时间偏移 Shift",
        "group": "sampling",
        "default": 5.0,
        "min": 0.0,
        "max": 15.0,
        "step": 0.1,
        "help": "Wan 系最重要的动态旋钮，控制模型把多少注意力放在「时间」上。调低画面更稳、动作更小、更容易保持人物一致；调高动作幅度更大，但也更容易糊、更容易出现人物漂移。",
        "recommend": "人物镜头 3~5，风景/运镜类 5~8。画面太死板往上加 1，人脸开始变形就往下减 1。填 0 表示用模型自带推荐值。",
    },
    "h3_attention_backend": {
        "type": "select", "label": "H3 Attention 后端", "group": "optimization", "default": "native",
        "choices": ["native", "pytorch", "kitchen_int8"],
        "choice_labels": {"native": "跟随 ComfyUI（不打补丁）", "pytorch": "PyTorch 质量对照", "kitchen_int8": "INT8 Attention（实验）"},
        "help": "只切换 H3 扩散模型的注意力计算，不改文本编码器或原始权重。INT8 可能降低计算开销，也可能影响细节。",
        "recommend": "先保留同一种子做对照；所需内核不可用会阻止提交，不自动降级。",
    },
    "h3_task": {
        "type": "select", "label": "创作任务", "group": "h3_creative", "surface": "h3_tools", "default": "generate",
        "choices": ["generate", "control", "inpaint"],
        "choice_labels": {"generate": "普通生成", "control": "动作 / 结构控制", "inpaint": "局部重绘"},
        "help": "控制视频引导动作与轮廓；局部重绘只替换白色遮罩区域。两者均需要独立 Fun ControlNet 权重。",
    },
    "h3_control_type": {
        "type": "select", "label": "控制素材类型", "group": "h3_creative", "default": "canny",
        "choices": ["canny", "pose", "depth", "hed", "mlsd"],
        "choice_labels": {"canny": "普通视频 → Canny 边缘", "pose": "已处理的姿态视频", "depth": "已处理的深度视频", "hed": "已处理的软边缘视频", "mlsd": "已处理的直线视频"},
        "help": "只有 Canny 自动从普通视频提取。其余类型请上传已处理的控制图视频；不会自动估计骨骼或深度。",
    },
    "h3_control_strength": {
        "type": "number", "label": "控制强度", "group": "h3_creative", "default": 0.7, "min": 0.1, "max": 1.5, "step": 0.05,
        "help": "越高越贴近控制轮廓，越低越自由。先试 0.7，动作偏离再小幅增加。",
    },
    "h3_control_start": {
        "type": "number", "label": "控制开始比例", "group": "h3_creative", "default": 0.0, "min": 0.0, "max": 0.95, "step": 0.05,
        "help": "0 表示从采样第一步开始约束，不是视频的起始时间。",
    },
    "h3_control_end": {
        "type": "number", "label": "控制结束比例", "group": "h3_creative", "default": 0.8, "min": 0.05, "max": 1.0, "step": 0.05,
        "help": "0.8 表示最后两成采样放开约束，给细节更多自由；必须大于开始比例。",
    },
    "h3_preserve_source_audio": {
        "type": "bool", "label": "重绘保留原音轨", "group": "h3_creative", "default": True,
        "help": "局部重绘使用原片音轨；原片无声时保持无声。关闭后使用 H3 原生音频设置。",
    },
    "h3_latent_upscale": {
        "type": "bool", "label": "H3 潜空间超分", "group": "h3_creative", "surface": "h3_tools", "default": False,
        "help": "先低分辨率生成，再放大潜变量并精修到所选目标分辨率。原音轨保留；不是对现成 MP4 直接超分。",
    },
    "h3_upscale_factor": {
        "type": "number", "label": "潜空间放大倍率", "group": "h3_creative", "default": 1.5, "min": 1.5, "max": 2.0, "step": 0.5,
        "help": "目标尺寸不变，倍率越大第一段尺寸越小。1.5 更保守，2 倍更依赖精修；不能保证节省峰值显存。",
    },
    "h3_refine_steps": {
        "type": "int", "label": "超分精修步数", "group": "h3_creative", "default": 8, "min": 4, "max": 20, "step": 1,
        "help": "高分辨率阶段的实际采样步数，越多越慢，不保证画质线性提升。",
    },
    "h3_refine_denoise": {
        "type": "number", "label": "超分精修强度", "group": "h3_creative", "default": 0.35, "min": 0.1, "max": 0.6, "step": 0.05,
        "help": "低值保留原构图，高值重新生成更多细节，也可能改变脸和文字。建议从 0.35 开始。",
    },
    "h3_shift_video": {
        "type": "number",
        "label": "H3 视频流偏移",
        "group": "sampling",
        "default": 12.0,
        "min": 0.01,
        "max": 30.0,
        "step": 0.1,
        "help": "MiniMax H3 视频潜变量的流匹配偏移。数值越高，前段更强调大结构和运动；数值过高可能增加形体漂移与闪烁。",
        "recommend": "官方默认 12.0。人物不稳定时可试 10~11；动作太弱时只小幅提高，不建议一次跨越 2。",
    },
    "h3_shift_audio": {
        "type": "number",
        "label": "H3 音频流偏移",
        "group": "sampling",
        "default": 3.0,
        "min": 0.01,
        "max": 12.0,
        "step": 0.1,
        "help": "控制 H3 原生音频流的去噪节奏。它会影响对白、环境声、音乐与画面同步收敛的方式。",
        "recommend": "官方默认 3.0，通常不要改。出现音频破碎或节奏漂移时先恢复为 3.0，再检查提示词和时长。",
    },
    "denoise": {
        "type": "number",
        "label": "重绘强度 Denoise",
        "group": "sampling",
        "default": 1.0,
        "min": 0.05,
        "max": 1.0,
        "step": 0.05,
        "help": "1.0 = 完全从零生成。小于 1.0 会保留一部分输入的潜变量，相当于「在已有结果上改一点」。",
        "recommend": "常规生成保持 1.0。想微调已有画面而不推翻重来时用 0.4~0.7。",
    },
    # ---- 分段与阶段 -------------------------------------------------------
    "boundary_ratio": {
        "type": "number",
        "label": "高噪专家占比",
        "group": "stage",
        "default": 0.5,
        "min": 0.1,
        "max": 0.9,
        "step": 0.05,
        "help": "Wan2.2 A14B 是「高噪 + 低噪」两个专家模型接力跑。这个值决定前面多少比例的步数交给高噪专家。高噪负责构图和大动作，低噪负责细节和收敛。",
        "recommend": "默认 0.5 适合大多数镜头。动作太小、构图太平就加到 0.6~0.7；画面糊、细节不够就降到 0.3~0.4。",
    },
    "cfg_high": {
        "type": "number",
        "label": "高噪段 CFG",
        "group": "stage",
        "default": 0.0,
        "min": 0.0,
        "max": 20.0,
        "step": 0.1,
        "help": "只作用在高噪那一段的提示词强度。填 0 表示跟随上面的主 CFG。",
        "recommend": "想让构图更听 prompt 又不想让细节段变僵硬时，把这里调到 3~5，低噪段留 1。",
    },
    "cfg_low": {
        "type": "number",
        "label": "低噪段 CFG",
        "group": "stage",
        "default": 0.0,
        "min": 0.0,
        "max": 20.0,
        "step": 0.1,
        "help": "只作用在低噪那一段的提示词强度。填 0 表示跟随主 CFG。",
        "recommend": "细节段通常越低越自然，配合加速 LoRA 时建议留 1.0。",
    },
    "first_stage_ratio": {
        "type": "number",
        "label": "第一阶段步数占比",
        "group": "stage",
        "default": 0.727,
        "min": 0.3,
        "max": 0.9,
        "step": 0.01,
        "help": "LTX 两段式先在一半分辨率生成，再做潜变量超分精修。这个值决定低分辨率阶段占多少步数，剩下的留给精修。",
        "recommend": "默认 0.73 是官方比例。想要更锐的细节可以降到 0.6 给精修段更多步数。",
    },
    "spatial_upscale": {
        "type": "bool",
        "label": "启用两段式空间超分",
        "group": "stage",
        "default": True,
        "help": "开启（推荐）：先用一半分辨率生成再超分精修，显存占用低，是官方推荐路径。关闭：直接按目标分辨率一段跑完，时间大约省一半，但显存占用会高很多，容易爆显存。",
        "recommend": "24G 以下显存保持开启。只是想快速看构图对不对时可以临时关掉。",
    },
    # ---- LoRA 强度 --------------------------------------------------------
    "lightx2v_strength": {
        "type": "number",
        "label": "加速 LoRA 强度",
        "group": "lora",
        "default": 1.0,
        "min": 0.0,
        "max": 1.5,
        "step": 0.05,
        "help": "lightx2v 4 步加速 LoRA 的权重。它能让 4 步就出片，但官方模板自己也标注了「会损失视频动态」——画面容易变得死板、动作幅度变小。",
        "recommend": "画面太静就降到 0.6~0.8。设为 0 会完全不加载它（不是以 0 强度加载），此时必须把采样步数提到 20 以上，否则出不来东西。",
    },
    "motion_lora_strength": {
        "type": "number",
        "label": "动作 LoRA 强度",
        "group": "lora",
        "default": 1.0,
        "min": 0.0,
        "max": 1.5,
        "step": 0.05,
        "help": "作用于上面选中的动作 LoRA 包。只有选了动作 LoRA 包时才生效。",
        "recommend": "动作过头、肢体开始变形就降到 0.6~0.8。",
    },
    "distill_lora_strength": {
        "type": "number",
        "label": "蒸馏 LoRA 强度",
        "group": "lora",
        "default": 0.5,
        "min": 0.0,
        "max": 1.5,
        "step": 0.05,
        "help": "LTX 2.3 的少步蒸馏 LoRA。调高出图更快更稳但动态变弱，调低动态更强但需要更多采样步数才收敛。",
        "recommend": "默认 0.5 已经是折中值。想要更大动作就降到 0.3 并把步数加到 20 以上。",
    },
    # ---- 显存与解码 -------------------------------------------------------
    "batch_size": {
        "type": "int",
        "label": "同批条数 Batch",
        "group": "memory",
        "default": 1,
        "min": 1,
        "max": 4,
        "step": 1,
        "help": "一次采样同时出几条视频。显存占用接近成倍增长。",
        "recommend": "24G 以下保持 1。只有在显存充裕、想一次挑几个随机结果时才调大。",
    },
    "vae_tile_size": {
        "type": "int",
        "label": "VAE 解码分块",
        "group": "memory",
        "default": 512,
        "min": 128,
        "max": 1536,
        "step": 64,
        "help": "解码阶段把画面切成多大的块逐块处理。这是「采样跑完了、最后一步爆显存」时最有效的一根杠杆。",
        "recommend": "解码时爆显存就往下调到 256 甚至 192。调小只会变慢，基本不影响画质。",
    },
    "vae_tile_overlap": {
        "type": "int",
        "label": "VAE 分块重叠",
        "group": "memory",
        "default": 64,
        "min": 16,
        "max": 256,
        "step": 16,
        "help": "相邻分块之间重叠多少像素，用来消除拼接痕迹。",
        "recommend": "画面上出现规则的方格接缝时往上调到 96~128。",
    },
    "vae_temporal_size": {
        "type": "int",
        "label": "VAE 时间分块",
        "group": "memory",
        "default": 16,
        "min": 4,
        "max": 4096,
        "step": 4,
        "help": "解码时一次处理多少帧。长片段爆显存主要靠这个。",
        "recommend": "长镜头解码爆显存就降到 8。",
    },
    "vae_temporal_overlap": {
        "type": "int",
        "label": "VAE 时间重叠",
        "group": "memory",
        "default": 4,
        "min": 2,
        "max": 64,
        "step": 2,
        "help": "相邻时间分块之间重叠多少帧。",
        "recommend": "LTX 2.5 默认 32；出现周期性接缝时可试 48 或 64，显存不足时再降低。",
    },
    # ---- 视频修复 ---------------------------------------------------------
    "seedvr_temporal_overlap": {
        "type": "int",
        "label": "片段衔接重叠帧",
        "group": "restoration",
        "default": 0,
        "min": 0,
        "max": 16,
        "step": 1,
        "help": "长视频会被分段修复。这里控制相邻片段重复计算多少帧，再把重叠区域融合，主要用于减轻分段接缝和瞬间跳变。",
        "recommend": "先用官方默认 0；片段交界处有跳变时试 4~8。数值越大越慢，也会增加显存和重复计算。",
    },
    "seedvr_color_correction": {
        "type": "select",
        "label": "色彩回贴方式",
        "group": "restoration",
        "default": "none",
        "choices": ["none", "wavelet", "lab", "adain"],
        "choice_labels": {
            "none": "关闭（保留 SeedVR2 输出）",
            "wavelet": "Wavelet（自然、推荐修偏色）",
            "lab": "LAB（较强地贴近原片颜色）",
            "adain": "AdaIN（统一整体色调）",
        },
        "help": "把修复后的色彩向原视频靠拢。关闭时锐度和细节最自由；其他方式可减少偏色，但过强时可能压低对比度。",
        "recommend": "默认关闭。发现肤色或品牌色明显漂移时先试 Wavelet；LAB 更强，AdaIN 适合整体色调统一。",
    },
    # ---- 输出与编码 -------------------------------------------------------
    "ltx_audio": {
        "type": "bool",
        "label": "输出附带生成的音频",
        "group": "output",
        "default": True,
        "help": "LTX 会跟着画面一起生成一条音轨。关掉后输出的是纯静音视频。采样阶段仍会计算音频潜变量，关闭只省下音频解码和封装，不会明显加快生成。",
        "recommend": "要拿去自己配音配乐的话就关掉，省得后期还要抽掉原声。",
    },
    "ltx_audio_cfg": {
        "type": "number",
        "label": "音频提示词强度",
        "group": "sampling",
        "default": 1.0,
        "min": 0.0,
        "max": 10.0,
        "step": 0.1,
        "help": "控制 LTX 2.5 音轨对提示词的服从程度，不影响视频提示词强度。过高可能让声音生硬或失真。",
        "recommend": "Distilled 模型按官方工作流保持 1.0。声音和画面不匹配时先小幅调到 1.2~1.5。",
    },
    "ltx25_image_strength": {
        "type": "number",
        "label": "关键帧约束强度",
        "group": "stage",
        "default": 0.7,
        "min": 0.0,
        "max": 1.0,
        "step": 0.05,
        "help": "决定首帧或尾帧对生成视频的约束强度。数值高会更贴近参考图，但动作空间会变小。",
        "recommend": "人物一致性优先用 0.7~0.85；希望动作更自由可降到 0.5~0.65。",
    },
    "ltx25_pipeline_profile": {
        "type": "select",
        "label": "LTX 一键运行档位",
        "group": "optimization",
        "default": "balanced",
        "choices": ["preview", "balanced", "quality", "custom"],
        "choice_labels": {
            "preview": "快速试镜（单阶段 + ConvVAE）",
            "balanced": "均衡成片（两阶段 + ConvVAE）",
            "quality": "正式高质量（两阶段 + DiffVAE）",
            "custom": "自定义（使用下方单独设置）",
        },
        "help": "把最容易混淆的单/双阶段和解码器组合成三档。只有选择“自定义”时，下方的两阶段超分和视频解码器开关才直接决定实际链路。",
        "recommend": "构图和动作测试选快速；大多数交付选均衡；脸部、纹理和屏幕细节重要时选正式高质量；明确知道参数含义时再选自定义。",
    },
    "ltx25_decoder": {
        "type": "select",
        "label": "视频解码器",
        "group": "memory",
        "default": "diffusion",
        "choices": ["diffusion", "conv"],
        "choice_labels": {
            "diffusion": "DiffVAE（质量优先）",
            "conv": "Conv VAE（速度/显存优先）",
        },
        "help": "DiffVAE 是 LTX 2.5 的高质量扩散解码器，细节更好但更慢；Conv VAE 更快、占用更低。此项仅在“一键运行档位”选择自定义时生效。",
        "recommend": "96GB 显存正式出片选 DiffVAE；48GB 或快速试镜先选 Conv VAE。",
    },
    "ltx25_auto_duration": {
        "type": "bool",
        "label": "让模型自动决定时长",
        "group": "stage",
        "default": False,
        "help": "启用官方 Duration Head，根据提示词在设定区间内预测镜头时长，并自动输出满足 8n+1 的帧数。",
        "recommend": "普通分镜先关闭，手动控制成本更可预测；动作复杂、对白镜头可开启。",
    },
    "ltx25_min_seconds": {
        "type": "number",
        "label": "自动时长下限（秒）",
        "group": "stage",
        "default": 2.0,
        "min": 1.0,
        "max": 20.0,
        "step": 0.5,
        "help": "只在开启自动时长时生效，模型不会生成比这个值更短的镜头。",
        "recommend": "试镜用 2 秒，正式单镜头可设 3~5 秒。",
    },
    "ltx25_max_seconds": {
        "type": "number",
        "label": "自动时长上限（秒）",
        "group": "stage",
        "default": 5.0,
        "min": 1.0,
        "max": 20.0,
        "step": 0.5,
        "help": "只在开启自动时长时生效。上限越高，显存和生成时间增长越明显。",
        "recommend": "先保持 5 秒。长叙事建议仍拆成多个短镜头，角色和构图更稳定。",
    },
    "h3_audio": {
        "type": "bool",
        "label": "输出 H3 原生立体声音频",
        "group": "output",
        "default": True,
        "help": "开启后把 H3 同步生成的 32kHz 立体声音频解码并封装进 MP4。关闭只跳过音频解码和封装，音频潜变量仍会参与联合采样。",
        "recommend": "需要对白、环境声或配乐联动时保持开启；准备完全后期配音时可以关闭，节省一点解码时间和显存。",
    },
    "crf": {
        "type": "int",
        "label": "输出画质 CRF",
        "group": "output",
        "default": 19,
        "min": 0,
        "max": 51,
        "step": 1,
        "help": "H.264 的质量参数，数值越小画质越好、文件越大。0 是无损，通常 18 已经接近肉眼无损。",
        "recommend": "交付母版用 16~18，日常预览用 22~25 可以显著缩小文件。",
    },
    "pix_fmt": {
        "type": "select",
        "label": "像素格式",
        "group": "output",
        "default": "yuv420p",
        "choices": VHS_PIX_FMTS,
        "help": "yuv420p 是 8bit，兼容性最好，任何播放器和平台都能放。yuv420p10le 是 10bit，调色空间更大但部分老设备放不了。",
        "recommend": "要进达芬奇/PR 调色再选 10bit，直接发平台就用 yuv420p。",
    },
    # ---- RIFE 专有 --------------------------------------------------------
    "rife_fast_mode": {
        "type": "bool",
        "label": "RIFE 快速模式",
        "group": "sampling",
        "default": True,
        "help": "开启后跳过一部分精细化计算，插帧速度明显更快。",
        "recommend": "快速运动或复杂遮挡下出现拖影、鬼影时关掉它。",
    },
    "rife_ensemble": {
        "type": "bool",
        "label": "RIFE 集成推理",
        "group": "sampling",
        "default": True,
        "help": "同时正向和反向各算一遍再融合，中间帧更准，代价是慢一些。",
        "recommend": "保持开启。只有在追求最快速度时才关。",
    },
}

# ---------------------------------------------------------------------------
# 每个 mode 支持的参数（值是该 mode 下的覆盖项）
# ---------------------------------------------------------------------------

_WAN_A14B_PARAMS: dict[str, dict[str, Any]] = {
    "boundary_ratio": {},
    "cfg_high": {},
    "cfg_low": {},
    "shift": {"default": 5.0, "min": 1.0},
    "lightx2v_strength": {},
    "motion_lora_strength": {},
    "sampler_name": {},
    "scheduler": {},
    "batch_size": {},
    "vae_tile_size": {},
    "vae_tile_overlap": {},
    "vae_temporal_size": {},
    "vae_temporal_overlap": {},
}

_WAN_TI2V_PARAMS: dict[str, dict[str, Any]] = {
    "shift": {"default": 5.0, "min": 1.0},
    "sampler_name": {},
    "scheduler": {},
    "denoise": {},
    "batch_size": {},
    "vae_tile_size": {},
    "vae_tile_overlap": {},
    "vae_temporal_size": {},
    "vae_temporal_overlap": {},
}

_HUNYUAN15_PARAMS: dict[str, dict[str, Any]] = {
    "shift": {
        "default": 0.0,
        "help": "控制模型对时间维度的关注程度，影响动作幅度和画面稳定性。",
        "recommend": "填 0 表示按分辨率自动选择（480P 用 5.0，720P 用 7.0~9.0）。想固定风格再手动填。",
    },
    "sampler_name": {},
    "scheduler": {},
    "denoise": {},
    "batch_size": {},
}

_MINIMAX_H3_PARAMS: dict[str, dict[str, Any]] = {
    **{key: {} for key in (
        "h3_attention_backend", "h3_task", "h3_control_type", "h3_control_strength", "h3_control_start",
        "h3_control_end", "h3_preserve_source_audio", "h3_latent_upscale", "h3_upscale_factor",
        "h3_refine_steps", "h3_refine_denoise",
    )},
    "h3_acceleration_profile": {},
    "h3_turbo_strength": {},
    "h3_prompt_format": {},
    "h3_shift_video": {},
    "h3_shift_audio": {},
    "sampler_name": {
        "default": "res_multistep",
        "choices": ["res_multistep", "euler", "dpmpp_2m"],
        "recommend": "官方模板使用 res_multistep；首次运行和正式出片都建议保持不变。",
    },
    "scheduler": {
        "default": "simple",
        "choices": ["simple", "normal", "beta"],
        "recommend": "FL2VA/T2V 默认 simple。参考条件很重时才尝试 beta；切换后应先跑 3 秒试镜。",
    },
    "denoise": {
        "default": 1.0,
        "min": 0.5,
        "recommend": "H3 正常生成保持 1.0。降低会留下更多初始潜变量，不等于更忠于关键帧。",
    },
    "h3_tiled_decode": {},
    "h3_audio": {},
}

_MINIMAX_H3_REFERENCE_PARAMS: dict[str, dict[str, Any]] = {
    **_MINIMAX_H3_PARAMS,
    "h3_acceleration_profile": {
        "default": "native",
        "choices": ["native", "lightx_ref4_v01"],
        "choice_labels": {
            "native": "原生参考保真",
            "lightx_ref4_v01": H3_RUNTIME_PROFILES["lightx_ref4_v01"]["label"],
        },
        "help": "R2V 使用独立 ref2va 权重，不能套用 FL2VA 的 4/8 步 LoRA。Reference 4 步是对应 ref2va 的专用社区加速。",
        "recommend": "多人、声音或多视频参考先用原生。只在短片批量试镜时尝试 Reference 4 步。",
    },
    "scheduler": {
        "default": "beta",
        "choices": ["beta", "normal", "simple"],
        "recommend": "官方 R2V 模板指出参考条件较重时 beta/normal 通常优于 simple，默认 beta。",
    },
    "h3_reference_size": {},
}

_FAL_H3_MAX_PARAMS: dict[str, dict[str, Any]] = {
    "fal_prompt_expansion_mode": {},
    "fal_safety_checker": {},
}

_LTX23_PARAMS: dict[str, dict[str, Any]] = {
    "spatial_upscale": {},
    "first_stage_ratio": {},
    "distill_lora_strength": {},
    "sampler_name": {
        "default": "euler_ancestral_cfg_pp",
        "choices": LTX_SAMPLERS,
        "recommend": "LTX 2.3 的低分辨率段依赖 cfg_pp 系列采样器，不要随便换成普通 euler。",
    },
    "sampler_name_refine": {
        "type": "select",
        "label": "精修段采样器",
        "group": "sampling",
        "default": "euler_cfg_pp",
        "choices": LTX_SAMPLERS,
        "help": "两段式里第二段（超分精修）用的采样器。",
        "recommend": "只在开启两段式超分时生效，一般不需要改。",
    },
    "ltx_audio": {},
    "batch_size": {},
    "vae_tile_size": {"default": 768},
    "vae_tile_overlap": {"default": 64},
    "vae_temporal_size": {"default": 4096},
    "vae_temporal_overlap": {"default": 4},
}

_LTX25_PARAMS: dict[str, dict[str, Any]] = {
    "ltx25_pipeline_profile": {},
    "spatial_upscale": {},
    "first_stage_ratio": {},
    "sampler_name": {
        "default": "euler_ancestral",
        "choices": LTX_SAMPLERS,
        "recommend": "LTX 2.5 Distilled 官方工作流使用 euler_ancestral；首次运行保持不变。",
    },
    "sampler_name_refine": {
        "type": "select",
        "label": "精修段采样器",
        "group": "sampling",
        "default": "euler_ancestral",
        "choices": LTX_SAMPLERS,
        "help": "潜变量 2x 超分后的第二阶段采样器。",
        "recommend": "官方配方使用 euler_ancestral，除非在做对照测试，否则保持默认。",
    },
    "ltx_audio": {},
    "ltx_audio_cfg": {},
    "ltx25_decoder": {},
    "ltx25_auto_duration": {},
    "ltx25_min_seconds": {},
    "ltx25_max_seconds": {},
    "batch_size": {},
    "vae_tile_size": {"default": 768},
    "vae_tile_overlap": {"default": 64},
    "vae_temporal_size": {"default": 4096},
    "vae_temporal_overlap": {"default": 32},
}

_LTX25_I2V_PARAMS: dict[str, dict[str, Any]] = {
    **_LTX25_PARAMS,
    "ltx25_image_strength": {},
}

_LTX098_T2V_PARAMS: dict[str, dict[str, Any]] = {
    "sampler_name": {"default": "res_multistep", "choices": LTX_SAMPLERS},
    "ltx_max_shift": {
        "type": "number",
        "label": "LTX max_shift",
        "group": "sampling",
        "default": 2.05,
        "min": 0.5,
        "max": 8.0,
        "step": 0.05,
        "help": "LTXVScheduler 噪声曲线的上界，值越大前期下降越陡。",
        "recommend": "一般不用动。画面过于平淡时可以试 2.5~3.0。",
    },
    "ltx_base_shift": {
        "type": "number",
        "label": "LTX base_shift",
        "group": "sampling",
        "default": 0.95,
        "min": 0.1,
        "max": 4.0,
        "step": 0.05,
        "help": "LTXVScheduler 噪声曲线的基准偏移。",
        "recommend": "一般不用动。",
    },
    "ltx_terminal": {
        "type": "number",
        "label": "LTX terminal",
        "group": "sampling",
        "default": 0.1,
        "min": 0.0,
        "max": 0.5,
        "step": 0.01,
        "help": "噪声曲线的终点值。设为 0 会跑满整条曲线。",
        "recommend": "保持 0.1。设为 0 通常更慢且容易过曝。",
    },
    "ltx_stretch": {
        "type": "bool",
        "label": "LTX 拉伸调度曲线",
        "group": "sampling",
        "default": True,
        "help": "把 sigma 曲线拉伸到完整区间，让每一步都用上。",
        "recommend": "保持开启。",
    },
    "batch_size": {},
}

_LTX098_I2V_PARAMS: dict[str, dict[str, Any]] = {
    **_LTX098_T2V_PARAMS,
    "sampler_name": {"default": "euler", "choices": LTX_SAMPLERS},
}

# 后期处理这两条走 VideoHelperSuite 的 VHS_VideoCombine，能调的是封装质量。
_RIFE_PARAMS: dict[str, dict[str, Any]] = {
    "rife_fast_mode": {},
    "rife_ensemble": {},
    "crf": {"default": 19},
    "pix_fmt": {},
}

_UPSCALE_PARAMS: dict[str, dict[str, Any]] = {
    "crf": {"default": 18},
    "pix_fmt": {},
}

_SEEDVR2_UPSCALE_PARAMS: dict[str, dict[str, Any]] = {
    "denoise": {"default": 1.0, "min": 0.05, "max": 1.0},
    "seedvr_temporal_overlap": {},
    "seedvr_color_correction": {},
    "vae_tile_size": {"default": 512},
    "vae_tile_overlap": {"default": 128},
    "vae_temporal_size": {"default": 64},
    "vae_temporal_overlap": {"default": 8},
    "crf": {"default": 18},
    "pix_fmt": {},
}

MODE_PARAMS: dict[str, dict[str, dict[str, Any]]] = {
    "i2v_a14b": _WAN_A14B_PARAMS,
    "t2v_a14b": _WAN_A14B_PARAMS,
    "ti2v_5b": _WAN_TI2V_PARAMS,
    "hunyuan15_t2v": _HUNYUAN15_PARAMS,
    "hunyuan15_i2v": _HUNYUAN15_PARAMS,
    "minimax_h3_t2v": _MINIMAX_H3_PARAMS,
    "minimax_h3_i2v": _MINIMAX_H3_PARAMS,
    "minimax_h3_r2v": _MINIMAX_H3_REFERENCE_PARAMS,
    "fal_h3_max_t2v": _FAL_H3_MAX_PARAMS,
    "fal_h3_max_i2v": _FAL_H3_MAX_PARAMS,
    "ltx23_t2v": _LTX23_PARAMS,
    "ltx23_i2v": _LTX23_PARAMS,
    "ltx25_t2v": _LTX25_PARAMS,
    "ltx25_i2v": _LTX25_I2V_PARAMS,
    "ltx_t2v": _LTX098_T2V_PARAMS,
    "ltx_i2v": _LTX098_I2V_PARAMS,
    "rife_2x": _RIFE_PARAMS,
    "upscale_2x": _UPSCALE_PARAMS,
    "upscale_seedvr2": _SEEDVR2_UPSCALE_PARAMS,
}


def _merged_spec(param_id: str, override: dict[str, Any]) -> dict[str, Any]:
    """合并全局定义和 mode 级覆盖。

    覆盖项里允许出现全局目录中没有的参数（例如只有 LTX 才有的 ltx_terminal），
    这样"某个引擎独有的旋钮"不用污染公共目录。
    """
    base = PARAM_SPECS.get(param_id)
    if base is None and not override:
        return {}
    spec = dict(base or {})
    spec.update(override or {})
    if "type" not in spec or "default" not in spec:
        return {}
    spec["id"] = param_id
    spec.setdefault("help", "")
    spec.setdefault("recommend", "")
    spec["group_label"] = GROUP_LABELS.get(str(spec.get("group")), "其他")
    return spec


def supported_params(mode: str) -> dict[str, dict[str, Any]]:
    """返回某个 mode 支持的全部参数（已合并 mode 级覆盖）。"""
    merged = {
        param_id: _merged_spec(param_id, override)
        for param_id, override in (MODE_PARAMS.get(mode) or {}).items()
    }
    return {param_id: spec for param_id, spec in merged.items() if spec}


def param_schema(mode: str) -> list[dict[str, Any]]:
    """给前端渲染用的 schema，按分组顺序排列。"""
    specs = supported_params(mode)
    if "h3_acceleration_profile" in specs:
        spec = specs["h3_acceleration_profile"]
        spec["choice_details"] = {
            key: dict(H3_RUNTIME_PROFILES[key])
            for key in spec["choices"] if key in H3_RUNTIME_PROFILES
        }
    order = list(GROUP_LABELS)
    return sorted(
        specs.values(),
        key=lambda item: (order.index(item["group"]) if item["group"] in order else len(order), item["id"]),
    )


def defaults_for(mode: str) -> dict[str, Any]:
    return {param_id: spec["default"] for param_id, spec in supported_params(mode).items()}


def _coerce(spec: dict[str, Any], value: Any) -> Any:
    kind = spec.get("type")
    if kind == "bool":
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)
    if kind == "select":
        choices = [str(item) for item in (spec.get("choices") or [])]
        text = str(value).strip()
        return text if text in choices else spec["default"]
    number = float(value)
    low = float(spec.get("min", number))
    high = float(spec.get("max", number))
    number = max(low, min(high, number))
    return int(round(number)) if kind == "int" else number


class AdvancedParams(dict):
    """已经过校验的高级参数。取不到的键回落到全局默认值，builder 不用到处写 or。"""

    def __missing__(self, key: str) -> Any:
        spec = PARAM_SPECS.get(key)
        if spec is None:
            raise KeyError(key)
        return spec["default"]

    def enabled(self, key: str) -> bool:
        return bool(self[key])


def resolve(mode: str, raw: Any) -> AdvancedParams:
    """把前端提交的 JSON 串解析成该 mode 的完整参数表。

    任何解析失败、越界、不认识的键都会被安静地丢掉并回落到默认值 —— 高级参数
    不该成为提交失败的理由，真正的图错误由 validate_graph 那一层负责报。
    """
    specs = supported_params(mode)
    resolved = AdvancedParams({param_id: spec["default"] for param_id, spec in specs.items()})
    if not raw:
        return resolved
    payload = raw
    if isinstance(payload, (str, bytes)):
        try:
            payload = json.loads(payload)
        except (ValueError, TypeError):
            return resolved
    if not isinstance(payload, dict):
        return resolved
    for param_id, value in payload.items():
        spec = specs.get(str(param_id))
        if not spec or value is None or value == "":
            continue
        try:
            resolved[str(param_id)] = _coerce(spec, value)
        except (TypeError, ValueError):
            continue
    return resolved


def non_default_items(mode: str, resolved: dict[str, Any]) -> dict[str, Any]:
    """只保留和默认值不同的项，用于任务记录里标注"这条是改过参数跑出来的"。"""
    specs = supported_params(mode)
    return {
        param_id: value
        for param_id, value in resolved.items()
        if param_id in specs and value != specs[param_id]["default"]
    }
