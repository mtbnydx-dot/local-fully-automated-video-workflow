from __future__ import annotations

import re
from typing import Any

from beginner_frontend import qwen21_updates


QWEN_IMAGE_MODEL = "qwen_image_2512_fp8_e4m3fn.safetensors"
QWEN_IMAGE_TEXT_ENCODER = "qwen_2.5_vl_7b_fp8_scaled.safetensors"
QWEN_IMAGE_VAE = "qwen_image_vae.safetensors"
QWEN_IMAGE_LIGHTNING_LORA = "Qwen-Image-Lightning-4steps-V1.0.safetensors"
QWEN_IMAGE_NSFW_LORA = "qwen_image_nsfw.safetensors"
QWEN_IMAGE_INSTALL_PROFILE = "qwen-image-2512-fp8"
QWEN_IMAGE_ASSET_IDS = (
    "qwen_image_2512_fp8",
    "qwen_image_text_encoder_fp8",
    "qwen_image_vae",
    "qwen_image_lightning_lora",
)

QWEN_IMAGE_21_MODEL = "qwen_image_2.1_int8_convrot.safetensors"
QWEN_IMAGE_21_TEXT_ENCODER = "qwen3vl_8b_int8_convrot.safetensors"
QWEN_IMAGE_21_VAE = "qwen_image_2.1_vae_bf16.safetensors"
QWEN_IMAGE_21_INSTALL_PROFILE = "qwen-image-2.1-int8"
QWEN_IMAGE_21_Q8_MODEL = "Qwen-Image-2.1-Uncensored/qwen-image-2.1-Q8_0.gguf"
QWEN_IMAGE_21_MAX_REFERENCES = 10
QWEN_IMAGE_21_ASSET_IDS = (
    "qwen_image_21_int8",
    "qwen_image_21_text_encoder_int8",
    "qwen_image_21_vae_bf16",
)

DEFAULT_IMAGE_PROMPT = "雨后的上海街头，一家灯光温暖的独立书店，行人撑着透明雨伞，电影感纪实摄影"
DEFAULT_IMAGE_NEGATIVE = (
    "低分辨率，低画质，模糊，肢体畸形，手指畸形，重复人物，过度饱和，"
    "蜡像感，塑料质感，人脸无细节，构图混乱，水印，签名，文字乱码"
)

ASPECT_PRESETS: list[dict[str, Any]] = [
    {"id": "qwen21-square-2k", "group": "Qwen 2.1 原生 2K", "name": "原生 2K 方形", "label": "1:1", "width": 2048, "height": 2048, "profiles": ["qwen_image_21_int8"]},
    {"id": "qwen21-classic-landscape-2k", "group": "Qwen 2.1 原生 2K", "name": "原生 2K 横幅", "label": "4:3", "width": 2400, "height": 1792, "profiles": ["qwen_image_21_int8"]},
    {"id": "qwen21-classic-portrait-2k", "group": "Qwen 2.1 原生 2K", "name": "原生 2K 竖幅", "label": "3:4", "width": 1792, "height": 2400, "profiles": ["qwen_image_21_int8"]},
    {"id": "qwen21-photo-landscape-2k", "group": "Qwen 2.1 原生 2K", "name": "原生 2K 摄影横幅", "label": "3:2", "width": 2528, "height": 1696, "profiles": ["qwen_image_21_int8"]},
    {"id": "qwen21-photo-portrait-2k", "group": "Qwen 2.1 原生 2K", "name": "原生 2K 摄影竖幅", "label": "2:3", "width": 1696, "height": 2528, "profiles": ["qwen_image_21_int8"]},
    {"id": "qwen21-landscape-2k", "group": "Qwen 2.1 原生 2K", "name": "原生 2K 横屏", "label": "16:9", "width": 2752, "height": 1536, "profiles": ["qwen_image_21_int8"]},
    {"id": "qwen21-portrait-2k", "group": "Qwen 2.1 原生 2K", "name": "原生 2K 竖屏", "label": "9:16", "width": 1536, "height": 2752, "profiles": ["qwen_image_21_int8"]},
    {"id": "square", "group": "模型推荐", "name": "方形", "label": "1:1", "width": 1328, "height": 1328},
    {"id": "landscape", "group": "模型推荐", "name": "横屏", "label": "16:9", "width": 1664, "height": 928},
    {"id": "portrait", "group": "模型推荐", "name": "竖屏", "label": "9:16", "width": 928, "height": 1664},
    {"id": "classic-landscape", "group": "模型推荐", "name": "经典横幅", "label": "4:3", "width": 1472, "height": 1104},
    {"id": "classic-portrait", "group": "模型推荐", "name": "经典竖幅", "label": "3:4", "width": 1104, "height": 1472},
    {"id": "photo-landscape", "group": "模型推荐", "name": "摄影横幅", "label": "3:2", "width": 1584, "height": 1056},
    {"id": "photo-portrait", "group": "模型推荐", "name": "摄影竖幅", "label": "2:3", "width": 1056, "height": 1584},
    {"id": "hd-landscape", "group": "常用输出", "name": "HD 横屏", "label": "16:9", "width": 1280, "height": 720},
    {"id": "hd-portrait", "group": "常用输出", "name": "HD 竖屏", "label": "9:16", "width": 720, "height": 1280},
    {"id": "fullhd-landscape", "group": "常用输出", "name": "Full HD 横屏", "label": "16:9", "width": 1920, "height": 1088},
    {"id": "fullhd-portrait", "group": "常用输出", "name": "Full HD 竖屏", "label": "9:16", "width": 1088, "height": 1920},
    {"id": "2k-landscape", "group": "常用输出", "name": "2K 横屏", "label": "16:9", "width": 2560, "height": 1440},
    {"id": "2k-portrait", "group": "常用输出", "name": "2K 竖屏", "label": "9:16", "width": 1440, "height": 2560},
    {"id": "3k-square", "group": "常用输出", "name": "3K 方形", "label": "1:1", "width": 3072, "height": 3072},
    {"id": "4k-landscape", "group": "常用输出", "name": "4K 横屏", "label": "16:9", "width": 3840, "height": 2160},
    {"id": "4k-portrait", "group": "常用输出", "name": "4K 竖屏", "label": "9:16", "width": 2160, "height": 3840},
    {"id": "ultrawide-landscape", "group": "扩展画幅", "name": "超宽银幕", "label": "21:9", "width": 2016, "height": 864},
    {"id": "ultrawide-portrait", "group": "扩展画幅", "name": "超长竖屏", "label": "9:21", "width": 864, "height": 2016},
    {"id": "double-landscape", "group": "扩展画幅", "name": "双倍横幅", "label": "2:1", "width": 1792, "height": 896},
    {"id": "double-portrait", "group": "扩展画幅", "name": "双倍竖幅", "label": "1:2", "width": 896, "height": 1792},
    {"id": "desktop-landscape", "group": "扩展画幅", "name": "桌面横屏", "label": "16:10", "width": 1536, "height": 960},
    {"id": "desktop-portrait", "group": "扩展画幅", "name": "桌面竖屏", "label": "10:16", "width": 960, "height": 1536},
    {"id": "social-portrait", "group": "扩展画幅", "name": "社媒竖图", "label": "4:5", "width": 1152, "height": 1440},
    {"id": "print-landscape", "group": "扩展画幅", "name": "印刷横图", "label": "5:4", "width": 1440, "height": 1152},
]
ASPECT_PRESET_MAP = {item["id"]: item for item in ASPECT_PRESETS}

STYLE_PRESETS: list[dict[str, str]] = [
    {"id": "none", "label": "不追加", "prompt": "", "prompt_en": ""},
    {
        "id": "photo",
        "label": "写实摄影",
        "prompt": "写实摄影，真实材质与自然光影，细节清楚",
        "prompt_en": "realistic photography, authentic materials, natural lighting, clear details",
    },
    {
        "id": "cinematic",
        "label": "电影画面",
        "prompt": "电影感画面，叙事构图，层次丰富的光影与色彩",
        "prompt_en": "cinematic frame, narrative composition, layered lighting and color",
    },
    {
        "id": "poster",
        "label": "品牌海报",
        "prompt": "专业品牌海报，明确视觉焦点，留白克制，版式整洁",
        "prompt_en": "professional brand poster, clear visual focus, restrained negative space, clean layout",
    },
    {
        "id": "product",
        "label": "产品摄影",
        "prompt": "高端商业产品摄影，主体轮廓准确，材质细节真实",
        "prompt_en": "premium commercial product photography, accurate silhouette, realistic material details",
    },
    {
        "id": "illustration",
        "label": "编辑插画",
        "prompt": "精致编辑插画，造型准确，色彩关系统一",
        "prompt_en": "refined editorial illustration, accurate forms, cohesive color relationships",
    },
    {
        "id": "anime",
        "label": "动画插画",
        "prompt": "高完成度动画插画，线条干净，角色结构准确",
        "prompt_en": "high-fidelity anime illustration, clean linework, accurate character structure",
    },
]
STYLE_PRESET_MAP = {item["id"]: item for item in STYLE_PRESETS}

PROMPT_MODES: list[dict[str, str]] = [
    {"id": "native", "label": "原文直输", "description": "中文或英文保持原文，并按输入语言追加所选风格。"},
    {"id": "structured", "label": "结构化增强", "description": "自动识别中文或英文，并用同一种语言整理画面要求。"},
    {"id": "mixed", "label": "双语增强", "description": "保留原始语言，并追加少量英文视觉质量词。"},
]
PROMPT_MODE_IDS = {item["id"] for item in PROMPT_MODES}


def _nsfw_unverified(note: str) -> dict[str, Any]:
    return {
        "status": "unverified",
        "label": "暂无已验证无限制方案",
        "toggle_enabled": False,
        "note": note,
    }


QWEN21_NSFW = {
    "status": "community_addon",
    "label": "Qwen 2.1 社区 Q8_0 扩散模型",
    "model_label": "Qwen-Image-2.1 Uncensored GGUF Q8_0",
    "toggle_enabled": True,
    "addon_profile": "qwen-image-2.1-uncensored-q8-addon",
    "asset_id": "qwen_image_21_uncensored_q8",
    "model_override": QWEN_IMAGE_21_Q8_MODEL,
    "required_nodes": ["UnetLoaderGGUF"],
    "source": "https://huggingface.co/abenzerps/Qwen-Image-2.1-Uncensored-GGUF",
    "note": "开启后使用社区 Q8_0 GGUF，关闭后恢复官方 INT8；复用原编码器和 VAE。Uncensored 为作者标注，生成效果未实测。",
    "trigger": "",
}
QWEN_NSFW = {
    "status": "community_addon",
    "label": "有社区无限制 LoRA",
    "toggle_enabled": True,
    "addon_profile": "qwen-image-2512-nsfw-addon",
    "asset_id": "qwen_image_nsfw_lora",
    "lora_name": QWEN_IMAGE_NSFW_LORA,
    "source": "https://huggingface.co/aiunivers/qwen-image-nsfw-lora-v2",
    "note": "可选社区无限制扩展，与标准模式分开安装。",
    "trigger": "",
    "strength_default": 0.85,
    "strength_min": 0.0,
    "strength_max": 1.4,
    "strength_step": 0.05,
    "strength_recommended": "0.65-1.00",
    "strength_help": "0.65-1.00 通常兼顾基础画质与扩展效果；超过 1.00 更强，但更容易出现构图漂移、纹理过锐或肢体错误。0 表示不加载效果。",
}
Z_IMAGE_NSFW = {
    "status": "community_addon",
    "label": "有社区无限制 LoRA",
    "toggle_enabled": True,
    "addon_profile": "z-image-nsfw-addon",
    "asset_id": "z_image_nsfw_lora",
    "lora_name": "z_image_nsfw_community.safetensors",
    "source": "https://huggingface.co/qqnyanddld/nsfw-z-image-lora",
    "note": "可选社区无限制扩展，来源与训练质量由社区维护。",
    "trigger": "",
    "strength_default": 0.8,
    "strength_min": 0.0,
    "strength_max": 1.3,
    "strength_step": 0.05,
    "strength_recommended": "0.55-0.95",
    "strength_help": "0.55-0.95 是平台建议区间；较低值更保留原模型构图，较高值会加强 LoRA 特征，也可能增加伪影。0 表示不加载效果。",
}
FLUX_NSFW = {
    "status": "community_addon",
    "label": "有社区破限文本编码器",
    "toggle_enabled": True,
    "addon_profile": "flux2-uncensored-te-addon",
    "asset_id": "flux2_uncensored_te_fp8",
    "text_encoder": "mistral_small_3_abliterated_v2_fp8mixed.safetensors",
    "source": "https://huggingface.co/silveroxides/FLUX.2-dev-fp8_scaled",
    "note": "开启后改用社区 abliterated Mistral 文本编码器，降低提示词拒绝；不注入视觉 LoRA。",
    "trigger": "",
}
KLEIN_NSFW_DISTILLED = {
    "status": "community_addon",
    "label": "有社区破限文本编码器",
    "toggle_enabled": True,
    "addon_profile": "flux2-klein-uncensored-te-addon",
    "asset_id": "flux2_klein_uncensored_te_nvfp4",
    "text_encoder": "qwen3-4b-heretic_nvfp4.safetensors",
    "source": "https://huggingface.co/DreamFast/qwen3-4b-heretic",
    "note": "开启后改用社区 heretic/abliterated Qwen3-4B 文本编码器；只降低文本拒绝，成人视觉知识仍有限。",
    "trigger": "",
}
KLEIN_NSFW_BASE = {
    "status": "community_addon",
    "label": "有社区破限文本编码器",
    "toggle_enabled": True,
    "addon_profile": "flux2-klein-uncensored-te-addon",
    "asset_id": "flux2_klein_uncensored_te_fp8",
    "text_encoder": "qwen3-4b-heretic_fp8_e4m3fn.safetensors",
    "source": "https://huggingface.co/DreamFast/qwen3-4b-heretic",
    "note": "开启后改用社区 heretic/abliterated Qwen3-4B 文本编码器；只降低文本拒绝，成人视觉知识仍有限。",
    "trigger": "",
}
ERNIE_NSFW = {
    "status": "experimental_community",
    "label": "有实验性文本破限方案（暂无 ComfyUI 单文件）",
    "toggle_enabled": False,
    "source": "https://huggingface.co/ponpoke/ERNIE-Image-Abliterated",
    "note": "社区已有 abliterated Ministral/增强器，但目前只有 HF 多文件或 GGUF，缺少可直接放入 text_encoders 的 ComfyUI 单文件，因此暂不开放一键开关。",
}


def _native_unaligned(label: str, note: str) -> dict[str, Any]:
    return {
        "status": "native_unaligned",
        "label": label,
        "toggle_enabled": True,
        "note": note,
        "trigger": "",
    }


IMAGE_PROFILES: list[dict[str, Any]] = [
    {
        "id": "qwen2512_lightning_fp8",
        "family": "Qwen-Image-2512",
        "label": "Qwen-Image-2512 FP8 极速",
        "short_label": "Qwen 极速 4 步",
        "description": "原生中文与画面文字主力，官方 Lightning 4 步，适合预览和批量探索。",
        "builder": "qwen",
        "install_profile": QWEN_IMAGE_INSTALL_PROFILE,
        "uses_lora": True,
        "required_asset_ids": list(QWEN_IMAGE_ASSET_IDS),
        "model": QWEN_IMAGE_MODEL,
        "text_encoder": QWEN_IMAGE_TEXT_ENCODER,
        "vae": QWEN_IMAGE_VAE,
        "lora": QWEN_IMAGE_LIGHTNING_LORA,
        "fixed_steps": 4,
        "fixed_cfg": 1.0,
        "default_steps": 4,
        "default_cfg": 1.0,
        "default_sampler": "euler",
        "default_scheduler": "simple",
        "max_dimension": 3104,
        "max_batch": 4,
        "quantization": "FP8 e4m3fn",
        "released": "2025-12",
        "vram_hint": "24GB 可尝试；48GB 更稳",
        "capabilities": ["中文", "海报文字", "批量", "视频关键帧"],
        "official_workflow": "https://docs.comfy.org/tutorials/image/qwen/qwen-image-2512",
        "nsfw": dict(QWEN_NSFW),
        "recommended": True,
    },
    {
        "id": "qwen_image_21_int8",
        "family": "Qwen-Image-2.1",
        "label": "Qwen-Image-2.1 INT8 ConvRot",
        "short_label": "Qwen 2.1 原生 2K",
        "description": "统一文生图与原生多参考编辑，支持透明图、中文文字和官方 2K 画幅。",
        "builder": "qwen21",
        "install_profile": QWEN_IMAGE_21_INSTALL_PROFILE,
        "uses_lora": False,
        "required_asset_ids": list(QWEN_IMAGE_21_ASSET_IDS),
        "optional_asset_ids": ["qwen_image_21_uncensored_q8"],
        "model": QWEN_IMAGE_21_MODEL,
        "text_encoder": QWEN_IMAGE_21_TEXT_ENCODER,
        "vae": QWEN_IMAGE_21_VAE,
        "default_steps": 25,
        "min_steps": 20,
        "max_steps": 50,
        "fixed_cfg": 1.0,
        "default_cfg": 1.0,
        "default_sampler": "euler",
        "default_scheduler": "simple",
        "max_dimension": 2752,
        "max_pixels": 4_301_000,
        "dimension_multiple": 32,
        "max_batch": 2,
        "quantization": "INT8 ConvRot + BF16 VAE",
        "released": "2026-09",
        "vram_hint": "24GB 可尝试；32GB+ 更稳；原生 2K 建议 48GB+",
        "capabilities": ["中文与画面文字", "原生 2K", "透明 RGBA", "最多 10 张参考图"],
        "official_workflow": "https://github.com/Comfy-Org/workflow_templates/blob/main/templates/image_qwen_image_2_1_t2i.json",
        "official_edit_workflow": "https://github.com/Comfy-Org/workflow_templates/blob/main/templates/image_qwen_image_2_1_image_edit.json",
        "license": "Qwen Research License",
        "nsfw": dict(QWEN21_NSFW),
        "recommended": True,
    },
    {
        "id": "hidream_o1_dev2604_fp8",
        "family": "HiDream-O1-Image",
        "label": "HiDream-O1-Image Dev-2604 FP8",
        "short_label": "HiDream Dev-2604",
        "description": "综合画质主力，28 步，擅长复杂构图、长文字和故事板。",
        "builder": "hidream_dev",
        "install_profile": "hidream-o1-dev2604-fp8",
        "uses_lora": False,
        "required_asset_ids": ["hidream_o1_dev2604_fp8"],
        "optional_asset_ids": ["hidream_gemma4_prompt_fp8"],
        "model": "hidream_o1_image_dev_fp8_scaled.safetensors",
        "fixed_steps": 28,
        "fixed_cfg": 1.0,
        "default_steps": 28,
        "default_cfg": 1.0,
        "default_sampler": "lcm",
        "default_scheduler": "normal",
        "max_dimension": 3104,
        "max_batch": 4,
        "quantization": "FP8 scaled",
        "released": "2026-05",
        "vram_hint": "24GB 可尝试；48GB 推荐",
        "capabilities": ["综合画质", "长文字", "故事板", "图像编辑模板"],
        "official_workflow": "https://docs.comfy.org/tutorials/image/hidream/hidream-o1",
        "nsfw": _nsfw_unverified("未找到可稳定复现的 O1 专用社区破限 LoRA。"),
        "recommended": True,
    },
    {
        "id": "qwen2512_quality_fp8",
        "family": "Qwen-Image-2512",
        "label": "Qwen-Image-2512 FP8 质量",
        "short_label": "Qwen 质量 50 步",
        "description": "不加载 Lightning LoRA，适合中文文字和最终大图。",
        "builder": "qwen",
        "install_profile": QWEN_IMAGE_INSTALL_PROFILE,
        "uses_lora": False,
        "required_asset_ids": list(QWEN_IMAGE_ASSET_IDS[:3]),
        "model": QWEN_IMAGE_MODEL,
        "text_encoder": QWEN_IMAGE_TEXT_ENCODER,
        "vae": QWEN_IMAGE_VAE,
        "default_steps": 50,
        "min_steps": 20,
        "max_steps": 80,
        "default_cfg": 4.0,
        "default_sampler": "euler",
        "default_scheduler": "simple",
        "max_dimension": 2048,
        "max_batch": 4,
        "quantization": "FP8 e4m3fn",
        "released": "2025-12",
        "vram_hint": "24GB 可尝试；48GB 推荐",
        "capabilities": ["中文", "海报文字", "质量优先", "视频关键帧"],
        "official_workflow": "https://docs.comfy.org/tutorials/image/qwen/qwen-image-2512",
        "nsfw": dict(QWEN_NSFW),
        "recommended": False,
    },
    {
        "id": "qwen_edit_2511_lightning_fp8",
        "family": "Qwen-Image-Edit-2511",
        "label": "Qwen-Image-Edit-2511 FP8 极速编辑",
        "short_label": "Qwen Edit 4 步",
        "description": "仅用于已有图片微调；4 步 Lightning，适合中文改图、画面文字和快速迭代。",
        "builder": "qwen_edit_2511",
        "install_profile": "qwen-image-edit-2511-fp8",
        "uses_lora": True,
        "generation_supported": False,
        "required_asset_ids": [
            "qwen_image_edit_2511_fp8mixed",
            "qwen_image_text_encoder_fp8",
            "qwen_image_vae",
            "qwen_image_edit_2511_lightning_lora",
        ],
        "model": "qwen_image_edit_2511_fp8mixed.safetensors",
        "text_encoder": QWEN_IMAGE_TEXT_ENCODER,
        "vae": QWEN_IMAGE_VAE,
        "lora": "Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors",
        "fixed_steps": 4,
        "fixed_cfg": 1.0,
        "default_steps": 4,
        "default_cfg": 1.0,
        "default_sampler": "euler",
        "default_scheduler": "simple",
        "max_dimension": 2048,
        "max_batch": 4,
        "quantization": "FP8 mixed + BF16 LoRA",
        "released": "2025-12",
        "vram_hint": "24GB 可尝试；48GB 更稳",
        "capabilities": ["仅图片微调", "中文指令", "多人一致性", "画面文字"],
        "official_workflow": "https://docs.comfy.org/tutorials/image/qwen/qwen-image-edit-2511",
        "nsfw": _nsfw_unverified("未找到可稳定复现的 Edit-2511 专用社区破限附件。"),
        "recommended": True,
    },
    {
        "id": "qwen_edit_2511_quality_fp8",
        "family": "Qwen-Image-Edit-2511",
        "label": "Qwen-Image-Edit-2511 FP8 质量编辑",
        "short_label": "Qwen Edit 质量",
        "description": "仅用于已有图片微调；20-50 步自由调整，质量和原图一致性优先。",
        "builder": "qwen_edit_2511",
        "install_profile": "qwen-image-edit-2511-fp8",
        "uses_lora": False,
        "generation_supported": False,
        "required_asset_ids": [
            "qwen_image_edit_2511_fp8mixed",
            "qwen_image_text_encoder_fp8",
            "qwen_image_vae",
        ],
        "optional_asset_ids": ["qwen_image_edit_2511_lightning_lora"],
        "model": "qwen_image_edit_2511_fp8mixed.safetensors",
        "text_encoder": QWEN_IMAGE_TEXT_ENCODER,
        "vae": QWEN_IMAGE_VAE,
        "default_steps": 40,
        "min_steps": 20,
        "max_steps": 50,
        "default_cfg": 4.0,
        "default_sampler": "euler",
        "default_scheduler": "simple",
        "max_dimension": 2048,
        "max_batch": 4,
        "quantization": "FP8 mixed",
        "released": "2025-12",
        "vram_hint": "24GB 可尝试；48GB 推荐",
        "capabilities": ["仅图片微调", "中文指令", "多人一致性", "质量优先"],
        "official_workflow": "https://docs.comfy.org/tutorials/image/qwen/qwen-image-edit-2511",
        "nsfw": _nsfw_unverified("未找到可稳定复现的 Edit-2511 专用社区破限附件。"),
        "recommended": False,
    },
    {
        "id": "hidream_i1_fast_fp8",
        "family": "HiDream-I1",
        "label": "HiDream-I1 Fast FP8",
        "short_label": "HiDream-I1 Fast",
        "description": "2025 年 MIT 通用模型，四文本编码器增强中英指令理解，16 步快速出图。",
        "builder": "hidream_i1",
        "install_profile": "hidream-i1-fast-fp8",
        "uses_lora": False,
        "required_asset_ids": [
            "hidream_i1_fast_fp8",
            "hidream_i1_clip_l",
            "hidream_i1_clip_g",
            "chroma_t5xxl_fp8",
            "hidream_i1_llama_fp8",
            "z_image_vae",
        ],
        "model": "hidream_i1_fast_fp8.safetensors",
        "clip_name1": "clip_l_hidream.safetensors",
        "clip_name2": "clip_g_hidream.safetensors",
        "clip_name3": "t5xxl_fp8_e4m3fn_scaled.safetensors",
        "clip_name4": "llama_3.1_8b_instruct_fp8_scaled.safetensors",
        "vae": "ae.safetensors",
        "shift": 3.0,
        "fixed_steps": 16,
        "fixed_cfg": 1.0,
        "default_steps": 16,
        "default_cfg": 1.0,
        "default_sampler": "lcm",
        "default_scheduler": "normal",
        "max_dimension": 2048,
        "max_batch": 4,
        "quantization": "FP8 scaled",
        "released": "2025-04",
        "vram_hint": "16GB+；24GB 更稳",
        "capabilities": ["中英提示词", "复杂语义", "16 步快速", "MIT"],
        "official_workflow": "https://docs.comfy.org/tutorials/image/hidream/hidream-i1",
        "nsfw": _nsfw_unverified("未找到可稳定复现的 HiDream-I1 专用社区破限附件。"),
        "recommended": True,
    },
    {
        "id": "hidream_i1_dev_fp8",
        "family": "HiDream-I1",
        "label": "HiDream-I1 Dev FP8",
        "short_label": "HiDream-I1 Dev",
        "description": "28 步均衡档，四文本编码器，适合复杂构图、人物、产品和中文提示词。",
        "builder": "hidream_i1",
        "install_profile": "hidream-i1-dev-fp8",
        "uses_lora": False,
        "required_asset_ids": [
            "hidream_i1_dev_fp8",
            "hidream_i1_clip_l",
            "hidream_i1_clip_g",
            "chroma_t5xxl_fp8",
            "hidream_i1_llama_fp8",
            "z_image_vae",
        ],
        "model": "hidream_i1_dev_fp8.safetensors",
        "clip_name1": "clip_l_hidream.safetensors",
        "clip_name2": "clip_g_hidream.safetensors",
        "clip_name3": "t5xxl_fp8_e4m3fn_scaled.safetensors",
        "clip_name4": "llama_3.1_8b_instruct_fp8_scaled.safetensors",
        "vae": "ae.safetensors",
        "shift": 6.0,
        "fixed_steps": 28,
        "fixed_cfg": 1.0,
        "default_steps": 28,
        "default_cfg": 1.0,
        "default_sampler": "lcm",
        "default_scheduler": "normal",
        "max_dimension": 2048,
        "max_batch": 4,
        "quantization": "FP8 scaled",
        "released": "2025-04",
        "vram_hint": "16GB+；24GB 更稳",
        "capabilities": ["中英提示词", "复杂构图", "质量均衡", "MIT"],
        "official_workflow": "https://docs.comfy.org/tutorials/image/hidream/hidream-i1",
        "nsfw": _nsfw_unverified("未找到可稳定复现的 HiDream-I1 专用社区破限附件。"),
        "recommended": False,
    },
    {
        "id": "hidream_i1_full_fp8",
        "family": "HiDream-I1",
        "label": "HiDream-I1 Full FP8",
        "short_label": "HiDream-I1 Full",
        "description": "未蒸馏质量档，30-60 步可自由选择，适合最终大图和复杂细节。",
        "builder": "hidream_i1",
        "install_profile": "hidream-i1-full-fp8",
        "uses_lora": False,
        "required_asset_ids": [
            "hidream_i1_full_fp8",
            "hidream_i1_clip_l",
            "hidream_i1_clip_g",
            "chroma_t5xxl_fp8",
            "hidream_i1_llama_fp8",
            "z_image_vae",
        ],
        "model": "hidream_i1_full_fp8.safetensors",
        "clip_name1": "clip_l_hidream.safetensors",
        "clip_name2": "clip_g_hidream.safetensors",
        "clip_name3": "t5xxl_fp8_e4m3fn_scaled.safetensors",
        "clip_name4": "llama_3.1_8b_instruct_fp8_scaled.safetensors",
        "vae": "ae.safetensors",
        "shift": 3.0,
        "default_steps": 50,
        "min_steps": 30,
        "max_steps": 60,
        "default_cfg": 5.0,
        "default_sampler": "lcm",
        "default_scheduler": "normal",
        "max_dimension": 2048,
        "max_batch": 4,
        "quantization": "FP8 scaled",
        "released": "2025-04",
        "vram_hint": "16GB+；24GB-32GB 推荐",
        "capabilities": ["中英提示词", "最高质量", "自由步数", "MIT"],
        "official_workflow": "https://docs.comfy.org/tutorials/image/hidream/hidream-i1",
        "nsfw": _nsfw_unverified("未找到可稳定复现的 HiDream-I1 专用社区破限附件。"),
        "recommended": False,
    },
    {
        "id": "hidream_o1_full_fp8",
        "family": "HiDream-O1-Image",
        "label": "HiDream-O1-Image Full FP8",
        "short_label": "HiDream Full",
        "description": "未蒸馏质量档，支持接缝平滑，适合最终大图和复杂细节。",
        "builder": "hidream_full",
        "install_profile": "hidream-o1-full-fp8",
        "uses_lora": False,
        "required_asset_ids": ["hidream_o1_full_fp8"],
        "optional_asset_ids": ["hidream_gemma4_prompt_fp8"],
        "model": "hidream_o1_image_fp8_scaled.safetensors",
        "default_steps": 50,
        "min_steps": 30,
        "max_steps": 60,
        "default_cfg": 5.0,
        "default_sampler": "dpmpp_2m_sde_gpu",
        "default_scheduler": "normal",
        "max_dimension": 2048,
        "max_batch": 4,
        "quantization": "FP8 scaled",
        "released": "2026-05",
        "vram_hint": "32GB+；48GB 推荐",
        "capabilities": ["最高质量", "长文字", "图像编辑模板", "主体一致性"],
        "official_workflow": "https://docs.comfy.org/tutorials/image/hidream/hidream-o1",
        "nsfw": _nsfw_unverified("未找到可稳定复现的 O1 专用社区破限 LoRA。"),
        "recommended": False,
    },
    {
        "id": "flux2_klein_4b_fp8",
        "family": "FLUX.2 Klein",
        "label": "FLUX.2 Klein 4B Distilled FP8",
        "short_label": "Klein 4B 极速",
        "description": "Apache 2.0 小模型，4 步快速出图，适合实时预览、产品草图和后续参考图编辑。",
        "builder": "flux2_klein_distilled",
        "install_profile": "flux2-klein-4b-fp8",
        "uses_lora": False,
        "required_asset_ids": ["flux2_klein_4b_fp8", "flux2_klein_qwen3_4b_fp4", "flux2_vae"],
        "model": "flux-2-klein-4b-fp8.safetensors",
        "text_encoder": "qwen_3_4b_fp4_flux2.safetensors",
        "vae": "flux2-vae.safetensors",
        "fixed_steps": 4,
        "fixed_cfg": 1.0,
        "default_steps": 4,
        "default_cfg": 1.0,
        "default_sampler": "euler",
        "default_scheduler": "flux2",
        "max_dimension": 2048,
        "max_batch": 8,
        "quantization": "FP8 + FP4 encoder",
        "released": "2026",
        "vram_hint": "官方约 8.4GB；16GB+ 更稳",
        "capabilities": ["4 步极速", "产品草图", "参考图编辑基座", "Apache 2.0"],
        "official_workflow": "https://docs.comfy.org/tutorials/flux/flux-2-klein",
        "nsfw": dict(KLEIN_NSFW_DISTILLED),
        "recommended": True,
    },
    {
        "id": "flux2_klein_base_4b_fp8",
        "family": "FLUX.2 Klein",
        "label": "FLUX.2 Klein Base 4B FP8",
        "short_label": "Klein Base 4B",
        "description": "未蒸馏 4B 基础档，约 20 步，适合质量优先、LoRA 微调和可控编辑。",
        "builder": "flux2_klein_base",
        "install_profile": "flux2-klein-base-4b-fp8",
        "uses_lora": False,
        "required_asset_ids": ["flux2_klein_base_4b_fp8", "flux2_klein_qwen3_4b", "flux2_vae"],
        "model": "flux-2-klein-base-4b-fp8.safetensors",
        "text_encoder": "qwen_3_4b.safetensors",
        "vae": "flux2-vae.safetensors",
        "default_steps": 20,
        "min_steps": 12,
        "max_steps": 40,
        "default_cfg": 4.0,
        "default_sampler": "euler",
        "default_scheduler": "flux2",
        "max_dimension": 2048,
        "max_batch": 4,
        "quantization": "Base FP8",
        "released": "2026",
        "vram_hint": "官方约 9.2GB；16GB+ 更稳",
        "capabilities": ["质量小模型", "LoRA 基座", "产品图", "参考图编辑基座"],
        "official_workflow": "https://docs.comfy.org/tutorials/flux/flux-2-klein",
        "nsfw": dict(KLEIN_NSFW_BASE),
        "recommended": False,
    },
    {
        "id": "chroma1_hd_bf16",
        "family": "Chroma",
        "label": "Chroma1-HD BF16",
        "short_label": "Chroma1-HD",
        "description": "Apache 2.0 开放权重高质量模型，原生未对齐特定安全过滤器，适合风格探索和通用创作。",
        "builder": "chroma",
        "install_profile": "chroma1-hd-bf16",
        "uses_lora": False,
        "required_asset_ids": ["chroma1_hd_bf16", "chroma_t5xxl_fp8", "z_image_vae"],
        "model": "Chroma1-HD.safetensors",
        "text_encoder": "t5xxl_fp8_e4m3fn_scaled.safetensors",
        "vae": "ae.safetensors",
        "default_steps": 28,
        "min_steps": 16,
        "max_steps": 50,
        "default_cfg": 4.0,
        "default_sampler": "euler",
        "default_scheduler": "beta",
        "max_dimension": 2048,
        "max_batch": 4,
        "quantization": "BF16 + FP8 encoder",
        "released": "2025",
        "vram_hint": "24GB 可尝试；32GB+ 更稳",
        "capabilities": ["开放创作", "高质量通用图", "风格探索", "批量"],
        "official_workflow": "https://huggingface.co/lodestones/Chroma1-HD",
        "nsfw": _native_unaligned(
            "原生未对齐特定安全过滤器",
            "模型卡明确说明可能生成露骨或冒犯内容；无需附加 LoRA。",
        ),
        "recommended": False,
    },
    {
        "id": "noobai_xl_11",
        "family": "NoobAI XL",
        "label": "NoobAI XL 1.1",
        "short_label": "NoobAI XL 1.1",
        "description": "2025 年 SDXL 动漫主力，现成 LoRA 与标签生态成熟，适合角色、插画和批量生产。",
        "builder": "sdxl",
        "install_profile": "noobai-xl-11",
        "uses_lora": False,
        "required_asset_ids": ["noobai_xl_11"],
        "model": "NoobAI-XL-v1.1.safetensors",
        "default_steps": 28,
        "min_steps": 20,
        "max_steps": 50,
        "default_cfg": 5.5,
        "default_sampler": "euler_ancestral",
        "default_scheduler": "normal",
        "max_dimension": 2048,
        "max_batch": 4,
        "quantization": "SDXL checkpoint",
        "released": "2025",
        "vram_hint": "8GB-12GB 可用；16GB+ 更稳",
        "capabilities": ["动漫角色", "成熟 LoRA 生态", "标签提示词", "批量"],
        "official_workflow": "https://huggingface.co/Laxhar/noobai-XL-1.1",
        "nsfw": _native_unaligned(
            "原生成人内容生态",
            "仓库标注 Not-For-All-Audiences，通常无需破限 LoRA。",
        ),
        "recommended": False,
    },
    {
        "id": "illustrious_xl_v20",
        "family": "Illustrious XL",
        "label": "Illustrious XL v2.0 Stable",
        "short_label": "Illustrious XL 2.0",
        "description": "2025 年稳定版 SDXL 动漫基础模型，适合角色插画、标签提示词、LoRA 微调与批量生产。",
        "builder": "sdxl",
        "install_profile": "illustrious-xl-v20",
        "uses_lora": False,
        "required_asset_ids": ["illustrious_xl_v20"],
        "model": "Illustrious-XL-v2.0.safetensors",
        "prompt_prefix": "masterpiece, best quality, amazing quality, very aesthetic",
        "default_steps": 28,
        "min_steps": 18,
        "max_steps": 50,
        "default_cfg": 6.0,
        "default_sampler": "dpmpp_2m_sde_gpu",
        "default_scheduler": "normal",
        "max_dimension": 2048,
        "max_batch": 4,
        "quantization": "SDXL FP16 checkpoint",
        "released": "2025-04",
        "vram_hint": "10GB-12GB 可用；16GB+ 更稳",
        "capabilities": ["动漫基础模型", "标签提示词", "LoRA 生态", "批量"],
        "official_workflow": "https://huggingface.co/OnomaAIResearch/Illustrious-XL-v2.0",
        "nsfw": _native_unaligned(
            "原生开放权重",
            "基础 checkpoint 没有平台侧文本过滤；并非专用成人微调，效果取决于提示词与配套 LoRA。",
        ),
        "recommended": False,
    },
    {
        "id": "wai_nsfw_illustrious_v90",
        "family": "WAI Illustrious",
        "label": "WAI NSFW Illustrious v9.0",
        "short_label": "WAI Illustrious v9",
        "description": "2025 年 Illustrious SDXL 社区微调，动漫成人内容与标签生态成熟，可直接使用原生 checkpoint 工作流。",
        "builder": "sdxl",
        "install_profile": "wai-nsfw-illustrious-v90",
        "uses_lora": False,
        "required_asset_ids": ["wai_nsfw_illustrious_v90"],
        "model": "waiNSFWIllustrious_v90.safetensors",
        "prompt_prefix": "masterpiece, best quality, amazing quality, very aesthetic, absurdres",
        "default_steps": 28,
        "min_steps": 18,
        "max_steps": 50,
        "default_cfg": 5.5,
        "default_sampler": "euler_ancestral",
        "default_scheduler": "normal",
        "max_dimension": 2048,
        "max_batch": 4,
        "quantization": "SDXL FP16 checkpoint",
        "released": "2025-01",
        "vram_hint": "10GB-12GB 可用；16GB+ 更稳",
        "capabilities": ["动漫成人生态", "Illustrious LoRA", "标签提示词", "批量"],
        "official_workflow": "https://huggingface.co/jzli/WAI-NSFW-illustrious-SDXL",
        "nsfw": _native_unaligned(
            "原生成人内容微调",
            "仓库标注 Not-For-All-Audiences；无需额外破限 LoRA，标签式英文提示词通常更稳定。",
        ),
        "recommended": False,
    },
    {
        "id": "cyberrealistic_pony_v18",
        "family": "CyberRealistic Pony",
        "label": "CyberRealistic Pony v18 FP16",
        "short_label": "CyberRealistic Pony 18",
        "description": "2026 年 Pony SDXL 写实档，适合人物摄影、写实角色、成人生态和高吞吐素材生产。",
        "builder": "sdxl",
        "install_profile": "cyberrealistic-pony-v18",
        "uses_lora": False,
        "required_asset_ids": ["cyberrealistic_pony_v18"],
        "model": "CyberRealisticPony_V18.0_F16.safetensors",
        "prompt_prefix": "score_9, score_8_up, score_7_up, photorealistic",
        "default_steps": 28,
        "min_steps": 18,
        "max_steps": 50,
        "default_cfg": 5.0,
        "default_sampler": "dpmpp_2m_sde_gpu",
        "default_scheduler": "normal",
        "max_dimension": 2048,
        "max_batch": 4,
        "quantization": "SDXL FP16 checkpoint",
        "released": "2026-05",
        "vram_hint": "10GB-12GB 可用；16GB+ 更稳",
        "capabilities": ["写实人物", "Pony LoRA 生态", "成人内容", "批量"],
        "official_workflow": "https://huggingface.co/cyberdelia/CyberRealisticPony",
        "nsfw": _native_unaligned(
            "原生 Pony 成人生态",
            "模型面向写实 Pony SDXL 生态，通常无需额外破限 LoRA；建议使用 score 标签和匹配的 Pony LoRA。",
        ),
        "recommended": False,
    },
    {
        "id": "lustify_sdxl_v40",
        "family": "LUSTIFY SDXL",
        "label": "LUSTIFY SDXL v4.0",
        "short_label": "LUSTIFY v4",
        "description": "2025 年社区 SDXL NSFW/SFW checkpoint，偏写实人物与成人内容，使用原生 checkpoint 工作流。",
        "builder": "sdxl",
        "install_profile": "lustify-sdxl-v40",
        "uses_lora": False,
        "required_asset_ids": ["lustify_sdxl_v40"],
        "model": "lustifySDXLNSFWSFW_v40.safetensors",
        "prompt_prefix": "masterpiece, best quality, photorealistic, highly detailed",
        "default_steps": 28,
        "min_steps": 18,
        "max_steps": 50,
        "default_cfg": 5.5,
        "default_sampler": "dpmpp_2m_sde_gpu",
        "default_scheduler": "normal",
        "max_dimension": 2048,
        "max_batch": 4,
        "quantization": "SDXL FP16 checkpoint",
        "released": "2025-03",
        "vram_hint": "10GB-12GB 可用；16GB+ 更稳",
        "capabilities": ["写实人物", "原生成人内容", "SFW/NSFW", "批量"],
        "official_workflow": "https://huggingface.co/MishGUN1/LUSTIFY",
        "nsfw": _native_unaligned(
            "原生成人内容 checkpoint",
            "仓库提供独立 NSFW/SFW checkpoint；模型卡未标注许可证，商用前需要自行核对授权。",
        ),
        "recommended": False,
    },
    {
        "id": "flux2_dev_fp8",
        "family": "FLUX.2",
        "label": "FLUX.2-dev FP8",
        "short_label": "FLUX.2 FP8",
        "description": "产品图、材质、品牌色和参考图编辑主力；平台内先接入 T2I。",
        "builder": "flux2",
        "install_profile": "flux2-dev-fp8",
        "uses_lora": False,
        "required_asset_ids": ["flux2_dev_fp8", "flux2_text_encoder_fp8", "flux2_vae"],
        "model": "flux2_dev_fp8mixed.safetensors",
        "text_encoder": "mistral_3_small_flux2_fp8.safetensors",
        "vae": "flux2-vae.safetensors",
        "default_steps": 20,
        "min_steps": 8,
        "max_steps": 50,
        "default_cfg": 4.0,
        "default_sampler": "euler",
        "default_scheduler": "flux2",
        "max_dimension": 4096,
        "max_batch": 4,
        "quantization": "FP8 mixed",
        "released": "2025-11",
        "vram_hint": "32GB+；48GB 推荐",
        "capabilities": ["产品图", "多参考图模板", "编辑模板", "品牌色"],
        "official_workflow": "https://docs.comfy.org/tutorials/flux/flux-2-dev",
        "nsfw": dict(FLUX_NSFW),
        "recommended": False,
    },
    {
        "id": "flux2_dev_nvfp4",
        "family": "FLUX.2",
        "label": "FLUX.2-dev NVFP4",
        "short_label": "FLUX.2 NVFP4",
        "description": "Blackwell 优化量化，功能与 FP8 档一致，模型和文本编码器更小。",
        "builder": "flux2",
        "install_profile": "flux2-dev-nvfp4",
        "uses_lora": False,
        "required_asset_ids": ["flux2_dev_nvfp4", "flux2_text_encoder_fp4", "flux2_vae"],
        "model": "flux2-dev-nvfp4-mixed.safetensors",
        "text_encoder": "mistral_3_small_flux2_fp4_mixed.safetensors",
        "vae": "flux2-vae.safetensors",
        "default_steps": 20,
        "min_steps": 8,
        "max_steps": 50,
        "default_cfg": 4.0,
        "default_sampler": "euler",
        "default_scheduler": "flux2",
        "max_dimension": 4096,
        "max_batch": 4,
        "quantization": "NVFP4 mixed",
        "released": "2025-12",
        "vram_hint": "Blackwell + PyTorch cu130",
        "capabilities": ["产品图", "多参考图模板", "编辑模板", "Blackwell 优化"],
        "official_workflow": "https://docs.comfy.org/tutorials/flux/flux-2-dev",
        "nsfw": dict(FLUX_NSFW),
        "recommended": False,
    },
    {
        "id": "z_image_base_bf16",
        "family": "Z-Image",
        "label": "Z-Image Base BF16",
        "short_label": "Z-Image Base",
        "description": "非蒸馏基础模型，适合 LoRA 训练、微调和定制生产。",
        "builder": "z_image",
        "install_profile": "z-image-base-bf16",
        "uses_lora": False,
        "required_asset_ids": ["z_image_base_bf16", "z_image_text_encoder_fp8", "z_image_vae"],
        "model": "z_image_bf16.safetensors",
        "text_encoder": "qwen_3_4b_fp8_mixed.safetensors",
        "vae": "ae.safetensors",
        "default_steps": 35,
        "min_steps": 25,
        "max_steps": 60,
        "default_cfg": 4.0,
        "default_sampler": "res_multistep",
        "default_scheduler": "simple",
        "max_dimension": 2048,
        "max_batch": 4,
        "quantization": "BF16 + FP8 encoder",
        "released": "2025-11",
        "vram_hint": "16GB+ 推理",
        "capabilities": ["LoRA 训练基座", "中英文字", "微调", "批量"],
        "official_workflow": "https://docs.comfy.org/tutorials/image/z-image/z-image",
        "nsfw": dict(Z_IMAGE_NSFW),
        "recommended": False,
    },
    {
        "id": "z_image_turbo_nvfp4",
        "family": "Z-Image",
        "label": "Z-Image Turbo NVFP4",
        "short_label": "Z-Image Turbo",
        "description": "8 步高吞吐档，适合素材探索和批量生产。",
        "builder": "z_image_turbo",
        "install_profile": "z-image-turbo-nvfp4",
        "uses_lora": False,
        "required_asset_ids": ["z_image_turbo_nvfp4", "z_image_text_encoder_fp4", "z_image_vae"],
        "model": "z_image_turbo_nvfp4.safetensors",
        "text_encoder": "qwen_3_4b_fp4_mixed.safetensors",
        "vae": "ae.safetensors",
        "fixed_steps": 8,
        "fixed_cfg": 1.0,
        "default_steps": 8,
        "default_cfg": 1.0,
        "default_sampler": "res_multistep",
        "default_scheduler": "simple",
        "max_dimension": 2048,
        "max_batch": 4,
        "quantization": "NVFP4 + FP4 encoder",
        "released": "2025-11",
        "vram_hint": "12GB-16GB；Blackwell 最佳",
        "capabilities": ["高速批量", "中英文字", "ControlNet 模板", "姿态/深度模板"],
        "official_workflow": "https://docs.comfy.org/tutorials/image/z-image/z-image-turbo",
        "nsfw": dict(Z_IMAGE_NSFW),
        "recommended": False,
    },
    {
        "id": "ernie_image_standard",
        "family": "ERNIE-Image",
        "label": "ERNIE-Image 标准版",
        "short_label": "ERNIE 标准",
        "description": "质量和指令遵循优先，适合中文视觉设计与复杂版式。",
        "builder": "ernie",
        "install_profile": "ernie-image-standard",
        "uses_lora": False,
        "required_asset_ids": ["ernie_image_standard", "ernie_ministral_text_encoder", "flux2_vae"],
        "optional_asset_ids": ["ernie_prompt_enhancer"],
        "model": "ernie-image.safetensors",
        "text_encoder": "ministral-3-3b.safetensors",
        "vae": "flux2-vae.safetensors",
        "default_steps": 50,
        "min_steps": 20,
        "max_steps": 70,
        "default_cfg": 4.0,
        "default_sampler": "euler",
        "default_scheduler": "simple",
        "max_dimension": 2048,
        "max_batch": 4,
        "quantization": "BF16 repack",
        "released": "2026-04",
        "vram_hint": "24GB+；48GB 推荐",
        "capabilities": ["中文", "复杂指令", "版式", "质量优先"],
        "official_workflow": "https://docs.comfy.org/tutorials/image/ernie-image/ernie-image",
        "nsfw": dict(ERNIE_NSFW),
        "recommended": False,
    },
    {
        "id": "ernie_image_turbo",
        "family": "ERNIE-Image",
        "label": "ERNIE-Image Turbo",
        "short_label": "ERNIE Turbo",
        "description": "DMD/RL 8 步快速档，适合中文海报草案和批量探索。",
        "builder": "ernie_turbo",
        "install_profile": "ernie-image-turbo",
        "uses_lora": False,
        "required_asset_ids": ["ernie_image_turbo", "ernie_ministral_text_encoder", "flux2_vae"],
        "optional_asset_ids": ["ernie_prompt_enhancer"],
        "model": "ernie-image-turbo.safetensors",
        "text_encoder": "ministral-3-3b.safetensors",
        "vae": "flux2-vae.safetensors",
        "fixed_steps": 8,
        "fixed_cfg": 1.0,
        "default_steps": 8,
        "default_cfg": 1.0,
        "default_sampler": "euler",
        "default_scheduler": "simple",
        "max_dimension": 2048,
        "max_batch": 4,
        "quantization": "Turbo BF16 repack",
        "released": "2026-04",
        "vram_hint": "24GB+；48GB 推荐",
        "capabilities": ["中文", "8 步快速", "版式", "批量"],
        "official_workflow": "https://docs.comfy.org/tutorials/image/ernie-image/ernie-image",
        "nsfw": dict(ERNIE_NSFW),
        "recommended": False,
    },
]

_LATENT_IMAGE_EDIT = {
    "supported": True,
    "method": "latent_img2img",
    "label": "潜空间重绘",
    "description": "把原图编码到模型潜空间，再按可调重绘强度重新采样。",
    "strength_supported": True,
    "strength_default": 0.35,
    "strength_min": 0.05,
    "strength_max": 0.95,
    "strength_step": 0.01,
    "strength_recommended": "0.20-0.60",
    "strength_help": "数值越低越接近原图，越高改动越大；0.20-0.40 适合修细节，0.45-0.70 适合换风格或较大调整。",
    "adherence_mode": "numeric_inverse_denoise",
    "adherence_label": "数值遵循",
    "adherence_default": 0.65,
    "adherence_min": 0.05,
    "adherence_max": 0.95,
    "adherence_step": 0.01,
    "adherence_help": "这是数值控制：原图遵循度 = 1 - 重绘强度（denoise）。数值越高，主体、构图和纹理越接近原图。",
    "resize_supported": True,
}
_REFERENCE_IMAGE_EDIT = {
    "supported": True,
    "method": "reference_instruction",
    "label": "原生指令编辑",
    "description": "使用模型原生参考图条件执行语义编辑，保留未要求修改的主体和构图。",
    "strength_supported": False,
    "strength_default": 1.0,
    "strength_min": 1.0,
    "strength_max": 1.0,
    "strength_step": 1.0,
    "strength_recommended": "由编辑指令控制",
    "strength_help": "当前模型的原生编辑节点没有重绘强度参数，请在编辑要求中明确哪些内容需要修改、哪些内容保持不变。",
    "adherence_mode": "semantic_reference",
    "adherence_label": "语义遵循",
    "adherence_default": 0.80,
    "adherence_min": 0.50,
    "adherence_max": 0.95,
    "adherence_step": 0.05,
    "adherence_help": "模型使用原生参考图条件，没有可验证的像素级 denoise 参数；该数值只调整提交给模型的保留约束强度。",
    "resize_supported": False,
}
_QWEN21_REFERENCE_EDIT = {
    **_REFERENCE_IMAGE_EDIT,
    "method": "qwen21_reference",
    "label": "原生多参考编辑",
    "description": "第一张图是要修改的目标图，可再添加最多 9 张人物、产品、风格或构图参考图。",
    "adherence_help": "Qwen-Image-2.1 使用原生参考条件；请在提示词中用 <image1> 指目标图，<image2> 起指附加参考图，并明确哪些内容保持不变。",
    "max_reference_images": QWEN_IMAGE_21_MAX_REFERENCES,
    "reference_prompt_hint": "目标图为 <image1>；附加参考图依次为 <image2> 到 <image10>。",
}
IMAGE_EDIT_CAPABILITIES = {
    "qwen": _LATENT_IMAGE_EDIT,
    "qwen21": _QWEN21_REFERENCE_EDIT,
    "qwen_edit_2511": _REFERENCE_IMAGE_EDIT,
    "z_image": _LATENT_IMAGE_EDIT,
    "z_image_turbo": _LATENT_IMAGE_EDIT,
    "chroma": _LATENT_IMAGE_EDIT,
    "sdxl": _LATENT_IMAGE_EDIT,
    "ernie": _LATENT_IMAGE_EDIT,
    "ernie_turbo": _LATENT_IMAGE_EDIT,
    "flux2": _REFERENCE_IMAGE_EDIT,
    "flux2_klein_distilled": _REFERENCE_IMAGE_EDIT,
    "flux2_klein_base": _REFERENCE_IMAGE_EDIT,
    "hidream_dev": _REFERENCE_IMAGE_EDIT,
    "hidream_full": _REFERENCE_IMAGE_EDIT,
    "hidream_i1": _LATENT_IMAGE_EDIT,
}
_qwen21_base = next(item for item in IMAGE_PROFILES if item["id"] == "qwen_image_21_int8")
_qwen21_additions = qwen21_updates.image_profiles(_qwen21_base)
IMAGE_PROFILES[IMAGE_PROFILES.index(_qwen21_base) + 1:IMAGE_PROFILES.index(_qwen21_base) + 1] = _qwen21_additions
for _preset in ASPECT_PRESETS:
    if _preset.get("profiles") == ["qwen_image_21_int8"]:
        _preset["profiles"] = ["qwen_image_21_int8", *[item["id"] for item in _qwen21_additions]]
IMAGE_PROFILE_MAP = {item["id"]: item for item in IMAGE_PROFILES}
IMAGE_ASSET_IDS = tuple(
    dict.fromkeys(
        asset_id
        for profile in IMAGE_PROFILES
        for asset_id in [*(profile.get("required_asset_ids") or []), *(profile.get("optional_asset_ids") or [])]
    )
)

ALLOWED_SAMPLERS = {
    "euler",
    "euler_cfg_pp",
    "euler_ancestral",
    "dpmpp_2m",
    "dpmpp_2m_sde",
    "dpmpp_2m_sde_gpu",
    "heun",
    "lcm",
    "res_multistep",
}
ALLOWED_SCHEDULERS = {"simple", "beta", "normal", "sgm_uniform", "flux2"}


def image_profile(profile_id: str | None) -> dict[str, Any]:
    return IMAGE_PROFILE_MAP.get((profile_id or "").strip(), IMAGE_PROFILES[0])


def image_edit_capability(profile_id: str | None) -> dict[str, Any]:
    profile = image_profile(profile_id)
    capability = dict(
        IMAGE_EDIT_CAPABILITIES.get(
            str(profile.get("builder") or ""),
            {
                "supported": False,
                "method": "unsupported",
                "label": "暂不支持",
                "description": "当前模型还没有接入可验证的图片编辑工作流。",
                "strength_supported": False,
                "resize_supported": False,
            },
        )
    )
    if capability.get("method") == "latent_img2img" and profile.get("fixed_steps") is not None:
        capability.update(
            {
                "strength_default": 0.65,
                "strength_recommended": "0.50-0.85",
                "strength_help": "当前是少步数蒸馏档；重绘强度过低时有效采样步数不足，建议从 0.65 开始。",
                "adherence_default": 0.35,
                "adherence_help": "这是数值控制：当前少步数蒸馏档需要较高 denoise 才能完成修改，因此默认原图遵循度为 35%；提高遵循度可能导致改动不明显。",
            }
        )
    return capability


def normalize_image_edit_controls(
    profile_id: str | None,
    *,
    source_adherence: float | None = None,
    edit_strength: float | None = None,
) -> dict[str, Any]:
    capability = image_edit_capability(profile_id)
    minimum = float(capability.get("adherence_min", 0.05))
    maximum = float(capability.get("adherence_max", 0.95))
    requested = float(source_adherence) if source_adherence is not None else -1.0
    if requested < 0:
        if capability.get("adherence_mode") == "numeric_inverse_denoise" and edit_strength is not None:
            requested = 1.0 - float(edit_strength)
        else:
            requested = float(capability.get("adherence_default", 0.65))
    adherence = max(minimum, min(maximum, requested))
    if capability.get("adherence_mode") == "numeric_inverse_denoise":
        strength = 1.0 - adherence
        strength = max(
            float(capability.get("strength_min", 0.05)),
            min(float(capability.get("strength_max", 0.95)), strength),
        )
        adherence = 1.0 - strength
    else:
        strength = float(capability.get("strength_default", 1.0))
    return {
        "source_adherence": round(adherence, 4),
        "edit_strength": round(strength, 4),
        "adherence_mode": str(capability.get("adherence_mode") or "unsupported"),
        "adherence_label": str(capability.get("adherence_label") or "原图遵循"),
        "numeric": capability.get("adherence_mode") == "numeric_inverse_denoise",
    }


def clean_prompt_text(value: str | None, *, limit: int = 5000) -> str:
    text = re.sub(r"[\t\r ]+", " ", (value or "").strip())
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text[:limit]


def normalize_image_dimensions(
    width: int,
    height: int,
    aspect: str = "",
    profile_id: str | None = None,
) -> tuple[int, int, str]:
    preset = ASPECT_PRESET_MAP.get((aspect or "").strip())
    if preset:
        width = int(preset["width"])
        height = int(preset["height"])

    profile = image_profile(profile_id)
    maximum = int(profile.get("max_dimension") or 2048)
    maximum_pixels = int(profile.get("max_pixels") or 0)
    multiple = max(1, int(profile.get("dimension_multiple") or 16))

    requested_width = max(1, int(width))
    requested_height = max(1, int(height))
    scale = min(1.0, maximum / requested_width, maximum / requested_height)
    if maximum_pixels > 0 and requested_width * requested_height > maximum_pixels:
        scale = min(scale, (maximum_pixels / (requested_width * requested_height)) ** 0.5)

    def normalize(value: float) -> int:
        return max(512, min(maximum, round(value / multiple) * multiple))

    normalized_width = normalize(requested_width * scale)
    normalized_height = normalize(requested_height * scale)
    if maximum_pixels > 0 and normalized_width * normalized_height > maximum_pixels:
        pixel_scale = (maximum_pixels / (normalized_width * normalized_height)) ** 0.5
        normalized_width = max(512, min(maximum, int(normalized_width * pixel_scale / multiple) * multiple))
        normalized_height = max(512, min(maximum, int(normalized_height * pixel_scale / multiple) * multiple))
    preset_id = (
        str(preset["id"])
        if preset and normalized_width == requested_width and normalized_height == requested_height
        else "custom"
    )
    return normalized_width, normalized_height, preset_id


def prompt_language(value: str) -> str:
    text = clean_prompt_text(value, limit=10_000)
    cjk_count = len(re.findall(r"[\u3400-\u9fff]", text))
    latin_count = len(re.findall(r"[A-Za-z]", text))
    return "en" if latin_count and (not cjk_count or latin_count >= cjk_count * 3) else "zh"


def _join_prompt_clauses(clauses: list[str], language: str) -> str:
    cleaned = [clause.strip() for clause in clauses if clause and clause.strip()]
    if language == "en":
        return " ".join(
            clause if clause.endswith((".", "!", "?")) else f"{clause}."
            for clause in cleaned
        )
    return "。".join(clause.rstrip("。") for clause in cleaned).strip() + "。"


def source_adherence_clause(language: str, value: float) -> str:
    adherence = max(0.0, min(1.0, float(value)))
    if language == "en":
        if adherence >= 0.85:
            return "Preservation: strictly change only the explicitly requested area; keep all other pixels, identity traits, objects, composition, camera angle, lighting, and spatial relationships as close to the source as possible"
        if adherence >= 0.65:
            return "Preservation: keep every unmentioned subject feature, object, composition, camera angle, and spatial relationship unchanged"
        return "Preservation: retain the main identity, subject layout, and composition while allowing coherent local reconstruction required by the edit"
    if adherence >= 0.85:
        return "保留要求：严格只修改明确指定的区域，其余像素、身份特征、物体、构图、机位、光影和空间关系尽可能贴近原图"
    if adherence >= 0.65:
        return "保留要求：未明确要求修改的主体特征、物体、构图、机位和空间关系保持不变"
    return "保留要求：保留主要身份、主体布局和构图，允许为完成编辑进行必要且连贯的局部重构"


def build_effective_prompt(
    prompt: str,
    *,
    prompt_mode: str = "structured",
    style_preset: str = "photo",
    exact_text: str = "",
    profile_id: str | None = None,
    nsfw: bool = False,
    edit_mode: bool = False,
    source_adherence: float = 0.65,
    auto_inject_trigger: bool = True,
    trigger_override: str = "",
    style_presets: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    from beginner_frontend.nsfw_playbook import inject_trigger

    source = clean_prompt_text(prompt) or DEFAULT_IMAGE_PROMPT
    mode = prompt_mode if prompt_mode in PROMPT_MODE_IDS else "structured"
    style_map = {item["id"]: item for item in (style_presets or STYLE_PRESETS)}
    style = style_map.get(style_preset) or STYLE_PRESET_MAP.get(style_preset) or STYLE_PRESET_MAP["none"]
    exact = clean_prompt_text(exact_text, limit=500)
    profile = image_profile(profile_id)
    nsfw_config = profile.get("nsfw") or {}
    unrestricted_mode = bool(nsfw and nsfw_config.get("toggle_enabled"))
    language = prompt_language(source)
    style_prompt = str((style.get("prompt_en") if language == "en" else style.get("prompt")) or "")

    clauses: list[str] = []
    if mode == "native":
        clauses.append(source)
        if style_prompt:
            clauses.append(style_prompt)
        if edit_mode:
            clauses.append(source_adherence_clause(language, source_adherence))
    elif language == "en":
        clauses.append(f"Edit instruction: {source}" if edit_mode else f"Subject and scene: {source}")
        if style_prompt:
            clauses.append(f"Visual style: {style_prompt}")
        if edit_mode:
            clauses.append(source_adherence_clause(language, source_adherence))
            clauses.append("Quality: make the requested edit coherent with the original lighting, texture, perspective, and image detail")
        else:
            clauses.append(
                "Composition: a clear subject, accurate count and placement, coherent spatial relationships, "
                "complete framing, and readable visual hierarchy"
            )
            clauses.append(
                "Quality: accurate forms, natural textures, consistent lighting, and no unnecessary repeated elements"
            )
        if mode == "mixed":
            clauses.append("highly detailed, coherent composition, natural lighting, accurate anatomy")
    else:
        clauses.append(f"编辑要求：{source}" if edit_mode else f"画面主题：{source}")
        if style_prompt:
            clauses.append(f"视觉风格：{style_prompt}")
        if edit_mode:
            clauses.append(source_adherence_clause(language, source_adherence))
            clauses.append("质量要求：修改内容与原图的光影、纹理、透视和细节自然衔接")
        else:
            clauses.append("构图要求：主体明确，数量和方位准确，空间关系合理，画面边缘完整，视觉层次清晰")
            clauses.append("质量要求：形体结构准确，纹理自然，光影统一，避免不必要的重复元素")
        if mode == "mixed":
            clauses.append("highly detailed, coherent composition, natural lighting, accurate anatomy")

    if exact:
        if language == "en":
            clauses.append(
                f'Clearly and exactly render this text in the image: "{exact}". '
                "Preserve its order and punctuation without rewriting, translating, or adding text"
            )
        else:
            clauses.append(
                f"画面中必须清晰、准确、逐字呈现以下文字：\"{exact}\"。"
                "保持文字顺序和标点一致，不得改写、翻译或添加其他文字"
            )
    effective = _join_prompt_clauses(clauses, language)
    trigger = str(trigger_override or nsfw_config.get("trigger") or "").strip()
    if unrestricted_mode and auto_inject_trigger and trigger:
        effective = inject_trigger(effective, trigger, enabled=True)
    return {
        "source": source,
        "effective": effective,
        "mode": mode,
        "language": language,
        "style_preset": str(style.get("id") or style_preset or "none"),
        "style_label": str(style.get("label") or ""),
        "exact_text": exact,
        "profile": profile["id"],
        "nsfw": unrestricted_mode,
        "nsfw_status": nsfw_config.get("status", "unverified"),
        "trigger": trigger if unrestricted_mode else "",
        "auto_inject_trigger": bool(auto_inject_trigger and unrestricted_mode),
        "edit_mode": bool(edit_mode),
        "source_adherence": round(max(0.0, min(1.0, float(source_adherence))), 4) if edit_mode else None,
    }


def normalized_generation_settings(
    profile_id: str,
    *,
    steps: int,
    cfg: float,
    sampler: str,
    scheduler: str,
    batch_size: int,
) -> dict[str, Any]:
    profile = image_profile(profile_id)
    if profile.get("fixed_steps") is not None:
        normalized_steps = int(profile["fixed_steps"])
    else:
        normalized_steps = max(
            int(profile.get("min_steps") or 1),
            min(int(profile.get("max_steps") or 100), int(steps or profile["default_steps"])),
        )
    if profile.get("fixed_cfg") is not None:
        normalized_cfg = float(profile["fixed_cfg"])
    else:
        normalized_cfg = max(0.0, min(20.0, float(cfg if cfg is not None else profile["default_cfg"])))
    normalized_sampler = profile.get("fixed_sampler") or (sampler if sampler in ALLOWED_SAMPLERS else str(profile["default_sampler"]))
    normalized_scheduler = profile.get("fixed_scheduler") or (scheduler if scheduler in ALLOWED_SCHEDULERS else str(profile["default_scheduler"]))
    return {
        "profile": profile,
        "steps": normalized_steps,
        "cfg": normalized_cfg,
        "sampler": normalized_sampler,
        "scheduler": normalized_scheduler,
        "batch_size": max(1, min(int(profile.get("max_batch") or 4), int(batch_size))),
    }


def _node(class_type: str, inputs: dict[str, Any]) -> dict[str, Any]:
    return {"class_type": class_type, "inputs": inputs}


def _apply_adult_lora(
    graph: dict[str, Any],
    *,
    model_source: list[Any],
    profile: dict[str, Any],
    nsfw: bool,
    node_id: str,
    strength: float,
    secondary_lora_name: str = "",
    secondary_lora_strength: float = 0.8,
    secondary_node_id: str = "98",
) -> list[Any]:
    config = profile.get("nsfw") or {}
    if nsfw and config.get("toggle_enabled") and config.get("lora_name"):
        minimum = float(config.get("strength_min", 0.0))
        maximum = float(config.get("strength_max", 2.0))
        graph[node_id] = _node(
            "LoraLoaderModelOnly",
            {
                "model": model_source,
                "lora_name": str(config["lora_name"]),
                "strength_model": max(minimum, min(maximum, float(strength))),
            },
        )
        model_source = [node_id, 0]
    secondary = str(secondary_lora_name or "").strip()
    if secondary:
        from beginner_frontend.nsfw_extensions import apply_secondary_lora

        model_source = apply_secondary_lora(
            graph,
            model_source,
            secondary,
            secondary_lora_strength,
            secondary_node_id,
        )
    return model_source


def _resolve_text_encoder(profile: dict[str, Any], *, nsfw: bool = False) -> str:
    config = profile.get("nsfw") or {}
    override = str(config.get("text_encoder") or "").strip()
    if nsfw and config.get("toggle_enabled") and override:
        return override
    return str(profile["text_encoder"])


def _apply_image_edit(
    graph: dict[str, Any],
    *,
    settings: dict[str, Any],
    source_image: str,
    width: int,
    height: int,
    edit_strength: float,
    edit_resize_mode: str,
) -> dict[str, Any]:
    profile = settings["profile"]
    capability = image_edit_capability(str(profile["id"]))
    if not capability.get("supported"):
        raise ValueError(f"{profile['label']} 暂未接入图片微调工作流")

    source_name = str(source_image or "").strip()
    if not source_name:
        raise ValueError("图片微调需要源图片")

    method = str(capability.get("method") or "")
    graph["90"] = _node("LoadImage", {"image": source_name})
    if method == "latent_img2img":
        graph["91"] = _node(
            "ImageScale",
            {
                "image": ["90", 0],
                "upscale_method": "lanczos",
                "width": int(width),
                "height": int(height),
                "crop": "disabled" if edit_resize_mode == "stretch" else "center",
            },
        )
        layout = {
            "qwen": (["3", 0], "9", "10"),
            "z_image": (["3", 0], "8", "9"),
            "z_image_turbo": (["3", 0], "8", "9"),
            "chroma": (["3", 0], "12", "13"),
            "sdxl": (["1", 2], "4", "5"),
            "ernie": (["3", 0], "6", "7"),
            "ernie_turbo": (["3", 0], "6", "7"),
            "hidream_i1": (["3", 0], "7", "8"),
        }.get(str(profile["builder"]))
        if layout is None:
            raise ValueError(f"{profile['label']} 缺少潜空间重绘布局")
        vae_source, empty_node_id, sampler_node_id = layout
        graph["92"] = _node("VAEEncode", {"pixels": ["91", 0], "vae": vae_source})
        latent_source: list[Any] = ["92", 0]
        if int(settings["batch_size"]) > 1:
            graph["93"] = _node("RepeatLatentBatch", {"samples": latent_source, "amount": int(settings["batch_size"])})
            latent_source = ["93", 0]
        graph.pop(empty_node_id, None)
        sampler_inputs = graph[sampler_node_id]["inputs"]
        sampler_inputs["latent_image"] = latent_source
        strength = max(
            float(capability.get("strength_min", 0.05)),
            min(float(capability.get("strength_max", 0.95)), float(edit_strength)),
        )
        if str(profile["builder"]) == "chroma":
            graph["94"] = _node("SplitSigmasDenoise", {"sigmas": ["11", 0], "denoise": strength})
            sampler_inputs["sigmas"] = ["94", 1]
        else:
            sampler_inputs["denoise"] = strength
        return graph

    if method != "reference_instruction":
        raise ValueError(f"{profile['label']} 的图片微调方式无效")

    target_megapixels = max(0.25, (int(width) * int(height)) / 1_000_000)
    reference_megapixels = min(4.0 if str(profile["builder"]).startswith("hidream") else 1.0, target_megapixels)
    graph["91"] = _node(
        "ImageScaleToTotalPixels",
        {
            "image": ["90", 0],
            "upscale_method": "lanczos",
            "megapixels": round(reference_megapixels, 2),
            "resolution_steps": 1,
        },
    )
    builder = str(profile["builder"])
    if builder.startswith("hidream"):
        graph["92"] = _node(
            "HiDreamO1ReferenceImages",
            {
                "positive": ["3", 0],
                "negative": ["4", 0],
                "images.image_1": ["91", 0],
            },
        )
        graph["9"]["inputs"]["positive"] = ["92", 0]
        graph["9"]["inputs"]["negative"] = ["92", 1]
        return graph

    graph["92"] = _node("VAEEncode", {"pixels": ["91", 0], "vae": ["3", 0]})
    if builder == "flux2":
        graph["93"] = _node("ReferenceLatent", {"conditioning": ["5", 0], "latent": ["92", 0]})
        graph["6"]["inputs"]["conditioning"] = ["93", 0]
        return graph
    if builder in {"flux2_klein_distilled", "flux2_klein_base"}:
        graph["93"] = _node("ReferenceLatent", {"conditioning": ["4", 0], "latent": ["92", 0]})
        graph["94"] = _node("ReferenceLatent", {"conditioning": ["5", 0], "latent": ["92", 0]})
        graph["6"]["inputs"]["positive"] = ["93", 0]
        graph["6"]["inputs"]["negative"] = ["94", 0]
        return graph
    raise ValueError(f"{profile['label']} 缺少原生参考图编辑布局")


def _build_qwen_prompt(
    *,
    settings: dict[str, Any],
    prompt: str,
    negative: str,
    width: int,
    height: int,
    seed: int,
    filename_prefix: str,
    nsfw: bool,
    nsfw_lora_strength: float,
    secondary_lora_name: str = "",
    secondary_lora_strength: float = 0.8,
) -> dict[str, Any]:
    profile = settings["profile"]
    graph: dict[str, Any] = {
        "1": _node("UNETLoader", {"unet_name": profile["model"], "weight_dtype": "default"}),
        "2": _node("CLIPLoader", {"clip_name": profile["text_encoder"], "type": "qwen_image", "device": "default"}),
        "3": _node("VAELoader", {"vae_name": profile["vae"]}),
    }
    model_source: list[Any] = ["1", 0]
    if profile.get("uses_lora"):
        graph["4"] = _node(
            "LoraLoaderModelOnly",
            {"model": model_source, "lora_name": profile["lora"], "strength_model": 1.0},
        )
        model_source = ["4", 0]
    model_source = _apply_adult_lora(
        graph,
        model_source=model_source,
        profile=profile,
        nsfw=nsfw,
        node_id="5",
        strength=nsfw_lora_strength,
        secondary_lora_name=secondary_lora_name,
        secondary_lora_strength=secondary_lora_strength,
    )
    graph.update(
        {
            "6": _node("ModelSamplingAuraFlow", {"model": model_source, "shift": 3.1}),
            "7": _node("CLIPTextEncode", {"clip": ["2", 0], "text": clean_prompt_text(prompt)}),
            "8": _node("CLIPTextEncode", {"clip": ["2", 0], "text": clean_prompt_text(negative) or DEFAULT_IMAGE_NEGATIVE}),
            "9": _node("EmptySD3LatentImage", {"width": width, "height": height, "batch_size": settings["batch_size"]}),
            "10": _node(
                "KSampler",
                {
                    "model": ["6", 0],
                    "seed": seed,
                    "steps": settings["steps"],
                    "cfg": settings["cfg"],
                    "sampler_name": settings["sampler"],
                    "scheduler": settings["scheduler"],
                    "positive": ["7", 0],
                    "negative": ["8", 0],
                    "latent_image": ["9", 0],
                    "denoise": 1.0,
                },
            ),
            "11": _node("VAEDecode", {"samples": ["10", 0], "vae": ["3", 0]}),
            "12": _node("SaveImage", {"images": ["11", 0], "filename_prefix": filename_prefix}),
        }
    )
    return graph


def _build_qwen21_prompt(
    *,
    settings: dict[str, Any],
    prompt: str,
    negative: str,
    width: int,
    height: int,
    seed: int,
    filename_prefix: str,
    nsfw: bool = False,
    nsfw_lora_strength: float = 0.8,
    source_image: str = "",
    reference_images: list[str] | None = None,
) -> dict[str, Any]:
    profile = settings["profile"]
    source_name = str(source_image or "").strip()
    if profile.get("generation_supported") is False and not source_name:
        raise ValueError("此 Qwen 2.1 档位仅支持图片微调，请先上传源图片")
    extra_references = [str(item or "").strip() for item in (reference_images or []) if str(item or "").strip()]
    if len(extra_references) > QWEN_IMAGE_21_MAX_REFERENCES - 1:
        raise ValueError(f"Qwen-Image-2.1 最多支持 {QWEN_IMAGE_21_MAX_REFERENCES} 张参考图（含目标图）")

    nsfw_config = profile.get("nsfw") or {}
    override = nsfw_config.get("model_override") if nsfw and nsfw_config.get("toggle_enabled") else None
    model_name = str(override or profile["model"])
    use_gguf = model_name.lower().endswith(".gguf")
    graph: dict[str, Any] = {
        "1": (
            _node("UnetLoaderGGUF", {"unet_name": model_name})
            if use_gguf
            else _node("UNETLoader", {"unet_name": model_name, "weight_dtype": "default"})
        ),
        "2": _node("CLIPLoader", {"clip_name": profile["text_encoder"], "type": "qwen_image", "device": "default"}),
        "3": _node("VAELoader", {"vae_name": profile["vae"]}),
    }
    model_source: list[Any] = ["1", 0]
    if profile.get("uses_lora"):
        graph["15"] = _node("LoraLoaderModelOnly", {
            "model": model_source, "lora_name": profile["lora"],
            "strength_model": float(profile.get("lora_strength", 1.0)),
        })
        model_source = ["15", 0]
    if nsfw and nsfw_config.get("lora_name") and float(nsfw_lora_strength) > 0:
        model_source = _apply_adult_lora(graph, model_source=model_source, profile=profile,
                                       nsfw=True, node_id="16", strength=nsfw_lora_strength)
    conditioning_inputs: dict[str, Any] = {
        "clip": ["2", 0],
        "prompt": clean_prompt_text(prompt),
        "negative_prompt": clean_prompt_text(negative) or DEFAULT_IMAGE_NEGATIVE,
        "resolution": 1024,
    }

    if source_name:
        graph["4"] = _node("QwenImage21Cache", {"model": model_source, "device": "auto", "dtype": "default"})
        model_source = ["4", 0]
        edit_resolution = max(32, round(((int(width) * int(height)) ** 0.5) / 32) * 32)
        conditioning_inputs.update({"vae": ["3", 0], "resolution": edit_resolution})
        for index, image_name in enumerate([source_name, *extra_references], start=1):
            node_id = str(20 + index)
            graph[node_id] = _node("LoadImage", {"image": image_name})
            conditioning_inputs[f"images.image_{index}"] = [node_id, 0]
        graph["5"] = _node("TextEncodeQwenImage21", conditioning_inputs)
        latent_source: list[Any] = ["5", 2]
        if int(settings["batch_size"]) > 1:
            graph["6"] = _node(
                "RepeatLatentBatch",
                {"samples": latent_source, "amount": int(settings["batch_size"])},
            )
            latent_source = ["6", 0]
        positive_source = ["5", 0]
        negative_source = ["5", 1]
    else:
        if extra_references:
            raise ValueError("附加参考图只能在图片微调模式中使用")
        graph["4"] = _node("TextEncodeQwenImage21", conditioning_inputs)
        graph["5"] = _node(
            "EmptyLatentImage",
            {"width": int(width), "height": int(height), "batch_size": int(settings["batch_size"])},
        )
        latent_source = ["5", 0]
        positive_source = ["4", 0]
        negative_source = ["4", 1]

    graph["7"] = _node(
        "KSampler",
        {
            "model": model_source,
            "seed": int(seed),
            "steps": int(settings["steps"]),
            "cfg": float(settings["cfg"]),
            "sampler_name": str(settings["sampler"]),
            "scheduler": str(settings["scheduler"]),
            "positive": positive_source,
            "negative": negative_source,
            "latent_image": latent_source,
            "denoise": 1.0,
        },
    )
    graph["8"] = _node("VAEDecode", {"samples": ["7", 0], "vae": ["3", 0]})
    graph["9"] = _node("SaveImage", {"images": ["8", 0], "filename_prefix": filename_prefix})
    return graph


def _build_qwen_edit_2511_prompt(
    *,
    settings: dict[str, Any],
    prompt: str,
    negative: str,
    source_image: str,
    seed: int,
    filename_prefix: str,
) -> dict[str, Any]:
    profile = settings["profile"]
    source_name = str(source_image or "").strip()
    if not source_name:
        raise ValueError("Qwen-Image-Edit-2511 需要先导入一张源图片")
    graph: dict[str, Any] = {
        "1": _node("UNETLoader", {"unet_name": profile["model"], "weight_dtype": "default"}),
        "2": _node("CLIPLoader", {"clip_name": profile["text_encoder"], "type": "qwen_image", "device": "default"}),
        "3": _node("VAELoader", {"vae_name": profile["vae"]}),
        "4": _node("LoadImage", {"image": source_name}),
        "5": _node("FluxKontextImageScale", {"image": ["4", 0]}),
        "6": _node(
            "TextEncodeQwenImageEditPlus",
            {"clip": ["2", 0], "vae": ["3", 0], "image1": ["5", 0], "prompt": clean_prompt_text(prompt)},
        ),
        "7": _node(
            "TextEncodeQwenImageEditPlus",
            {
                "clip": ["2", 0],
                "vae": ["3", 0],
                "image1": ["5", 0],
                "prompt": clean_prompt_text(negative) or DEFAULT_IMAGE_NEGATIVE,
            },
        ),
    }
    model_source: list[Any] = ["1", 0]
    if profile.get("uses_lora"):
        graph["15"] = _node(
            "LoraLoaderModelOnly",
            {"model": model_source, "lora_name": profile["lora"], "strength_model": 1.0},
        )
        model_source = ["15", 0]
    graph["8"] = _node("ModelSamplingAuraFlow", {"model": model_source, "shift": 3.1})
    graph["9"] = _node("CFGNorm", {"model": ["8", 0], "strength": 1.0})
    graph["10"] = _node("VAEEncode", {"pixels": ["5", 0], "vae": ["3", 0]})
    latent_source: list[Any] = ["10", 0]
    if int(settings["batch_size"]) > 1:
        graph["11"] = _node("RepeatLatentBatch", {"samples": latent_source, "amount": int(settings["batch_size"])})
        latent_source = ["11", 0]
    graph["12"] = _node(
        "KSampler",
        {
            "model": ["9", 0],
            "seed": seed,
            "steps": settings["steps"],
            "cfg": settings["cfg"],
            "sampler_name": settings["sampler"],
            "scheduler": settings["scheduler"],
            "positive": ["6", 0],
            "negative": ["7", 0],
            "latent_image": latent_source,
            "denoise": 1.0,
        },
    )
    graph["13"] = _node("VAEDecode", {"samples": ["12", 0], "vae": ["3", 0]})
    graph["14"] = _node("SaveImage", {"images": ["13", 0], "filename_prefix": filename_prefix})
    return graph


def _build_z_image_prompt(
    *,
    settings: dict[str, Any],
    prompt: str,
    negative: str,
    width: int,
    height: int,
    seed: int,
    filename_prefix: str,
    nsfw: bool,
    nsfw_lora_strength: float,
    secondary_lora_name: str = "",
    secondary_lora_strength: float = 0.8,
) -> dict[str, Any]:
    profile = settings["profile"]
    graph: dict[str, Any] = {
        "1": _node("UNETLoader", {"unet_name": profile["model"], "weight_dtype": "default"}),
        "2": _node("CLIPLoader", {"clip_name": profile["text_encoder"], "type": "lumina2", "device": "default"}),
        "3": _node("VAELoader", {"vae_name": profile["vae"]}),
    }
    model_source = _apply_adult_lora(
        graph,
        model_source=["1", 0],
        profile=profile,
        nsfw=nsfw,
        node_id="4",
        strength=nsfw_lora_strength,
        secondary_lora_name=secondary_lora_name,
        secondary_lora_strength=secondary_lora_strength,
    )
    graph["5"] = _node("ModelSamplingAuraFlow", {"model": model_source, "shift": 3.0})
    graph["6"] = _node("CLIPTextEncode", {"clip": ["2", 0], "text": clean_prompt_text(prompt)})
    if profile["builder"] == "z_image_turbo":
        graph["7"] = _node("ConditioningZeroOut", {"conditioning": ["6", 0]})
    else:
        graph["7"] = _node("CLIPTextEncode", {"clip": ["2", 0], "text": clean_prompt_text(negative) or DEFAULT_IMAGE_NEGATIVE})
    graph.update(
        {
            "8": _node("EmptySD3LatentImage", {"width": width, "height": height, "batch_size": settings["batch_size"]}),
            "9": _node(
                "KSampler",
                {
                    "model": ["5", 0],
                    "seed": seed,
                    "steps": settings["steps"],
                    "cfg": settings["cfg"],
                    "sampler_name": settings["sampler"],
                    "scheduler": "simple" if settings["scheduler"] == "flux2" else settings["scheduler"],
                    "positive": ["6", 0],
                    "negative": ["7", 0],
                    "latent_image": ["8", 0],
                    "denoise": 1.0,
                },
            ),
            "10": _node("VAEDecode", {"samples": ["9", 0], "vae": ["3", 0]}),
            "11": _node("SaveImage", {"images": ["10", 0], "filename_prefix": filename_prefix}),
        }
    )
    return graph


def _build_flux2_prompt(
    *,
    settings: dict[str, Any],
    prompt: str,
    width: int,
    height: int,
    seed: int,
    filename_prefix: str,
    nsfw: bool = False,
) -> dict[str, Any]:
    profile = settings["profile"]
    return {
        "1": _node("UNETLoader", {"unet_name": profile["model"], "weight_dtype": "default"}),
        "2": _node(
            "CLIPLoader",
            {
                "clip_name": _resolve_text_encoder(profile, nsfw=nsfw),
                "type": "flux2",
                "device": "default",
            },
        ),
        "3": _node("VAELoader", {"vae_name": profile["vae"]}),
        "4": _node("CLIPTextEncode", {"clip": ["2", 0], "text": clean_prompt_text(prompt)}),
        "5": _node("FluxGuidance", {"conditioning": ["4", 0], "guidance": settings["cfg"]}),
        "6": _node("BasicGuider", {"model": ["1", 0], "conditioning": ["5", 0]}),
        "7": _node("RandomNoise", {"noise_seed": seed}),
        "8": _node("KSamplerSelect", {"sampler_name": settings["sampler"]}),
        "9": _node("Flux2Scheduler", {"steps": settings["steps"], "width": width, "height": height}),
        "10": _node("EmptyFlux2LatentImage", {"width": width, "height": height, "batch_size": settings["batch_size"]}),
        "11": _node(
            "SamplerCustomAdvanced",
            {"noise": ["7", 0], "guider": ["6", 0], "sampler": ["8", 0], "sigmas": ["9", 0], "latent_image": ["10", 0]},
        ),
        "12": _node("VAEDecode", {"samples": ["11", 0], "vae": ["3", 0]}),
        "13": _node("SaveImage", {"images": ["12", 0], "filename_prefix": filename_prefix}),
    }


def _build_flux2_klein_prompt(
    *,
    settings: dict[str, Any],
    prompt: str,
    negative: str,
    width: int,
    height: int,
    seed: int,
    filename_prefix: str,
    nsfw: bool = False,
) -> dict[str, Any]:
    profile = settings["profile"]
    distilled = profile["builder"] == "flux2_klein_distilled"
    graph: dict[str, Any] = {
        "1": _node("UNETLoader", {"unet_name": profile["model"], "weight_dtype": "default"}),
        "2": _node(
            "CLIPLoader",
            {
                "clip_name": _resolve_text_encoder(profile, nsfw=nsfw),
                "type": "flux2",
                "device": "default",
            },
        ),
        "3": _node("VAELoader", {"vae_name": profile["vae"]}),
        "4": _node("CLIPTextEncode", {"clip": ["2", 0], "text": clean_prompt_text(prompt)}),
    }
    if distilled:
        graph["5"] = _node("ConditioningZeroOut", {"conditioning": ["4", 0]})
    else:
        graph["5"] = _node("CLIPTextEncode", {"clip": ["2", 0], "text": clean_prompt_text(negative) or DEFAULT_IMAGE_NEGATIVE})
    graph.update(
        {
            "6": _node(
                "CFGGuider",
                {"model": ["1", 0], "positive": ["4", 0], "negative": ["5", 0], "cfg": settings["cfg"]},
            ),
            "7": _node("RandomNoise", {"noise_seed": seed}),
            "8": _node("KSamplerSelect", {"sampler_name": settings["sampler"]}),
            "9": _node("Flux2Scheduler", {"steps": settings["steps"], "width": width, "height": height}),
            "10": _node("EmptyFlux2LatentImage", {"width": width, "height": height, "batch_size": settings["batch_size"]}),
            "11": _node(
                "SamplerCustomAdvanced",
                {"noise": ["7", 0], "guider": ["6", 0], "sampler": ["8", 0], "sigmas": ["9", 0], "latent_image": ["10", 0]},
            ),
            "12": _node("VAEDecode", {"samples": ["11", 0], "vae": ["3", 0]}),
            "13": _node("SaveImage", {"images": ["12", 0], "filename_prefix": filename_prefix}),
        }
    )
    return graph


def _build_chroma_prompt(
    *,
    settings: dict[str, Any],
    prompt: str,
    negative: str,
    width: int,
    height: int,
    seed: int,
    filename_prefix: str,
) -> dict[str, Any]:
    profile = settings["profile"]
    return {
        "1": _node("UNETLoader", {"unet_name": profile["model"], "weight_dtype": "default"}),
        "2": _node("CLIPLoader", {"clip_name": profile["text_encoder"], "type": "chroma", "device": "default"}),
        "3": _node("VAELoader", {"vae_name": profile["vae"]}),
        "4": _node("T5TokenizerOptions", {"clip": ["2", 0], "min_padding": 0, "min_length": 0}),
        "5": _node("CLIPTextEncode", {"clip": ["4", 0], "text": clean_prompt_text(prompt)}),
        "6": _node("CLIPTextEncode", {"clip": ["4", 0], "text": clean_prompt_text(negative) or DEFAULT_IMAGE_NEGATIVE}),
        "7": _node("ModelSamplingAuraFlow", {"model": ["1", 0], "shift": 1.0}),
        "8": _node("CFGGuider", {"model": ["7", 0], "positive": ["5", 0], "negative": ["6", 0], "cfg": settings["cfg"]}),
        "9": _node("RandomNoise", {"noise_seed": seed}),
        "10": _node("KSamplerSelect", {"sampler_name": settings["sampler"]}),
        "11": _node("BetaSamplingScheduler", {"model": ["7", 0], "steps": settings["steps"], "alpha": 0.6, "beta": 0.6}),
        "12": _node("EmptySD3LatentImage", {"width": width, "height": height, "batch_size": settings["batch_size"]}),
        "13": _node(
            "SamplerCustomAdvanced",
            {"noise": ["9", 0], "guider": ["8", 0], "sampler": ["10", 0], "sigmas": ["11", 0], "latent_image": ["12", 0]},
        ),
        "14": _node("VAEDecode", {"samples": ["13", 0], "vae": ["3", 0]}),
        "15": _node("SaveImage", {"images": ["14", 0], "filename_prefix": filename_prefix}),
    }


def _build_sdxl_prompt(
    *,
    settings: dict[str, Any],
    prompt: str,
    negative: str,
    width: int,
    height: int,
    seed: int,
    filename_prefix: str,
) -> dict[str, Any]:
    profile = settings["profile"]
    positive = ", ".join(
        item for item in (str(profile.get("prompt_prefix") or "").strip(" ,"), clean_prompt_text(prompt)) if item
    )
    negative_text = ", ".join(
        item
        for item in (str(profile.get("negative_prefix") or "").strip(" ,"), clean_prompt_text(negative) or DEFAULT_IMAGE_NEGATIVE)
        if item
    )
    return {
        "1": _node("CheckpointLoaderSimple", {"ckpt_name": profile["model"]}),
        "2": _node("CLIPTextEncode", {"clip": ["1", 1], "text": positive}),
        "3": _node("CLIPTextEncode", {"clip": ["1", 1], "text": negative_text}),
        "4": _node("EmptyLatentImage", {"width": width, "height": height, "batch_size": settings["batch_size"]}),
        "5": _node(
            "KSampler",
            {
                "model": ["1", 0],
                "seed": seed,
                "steps": settings["steps"],
                "cfg": settings["cfg"],
                "sampler_name": settings["sampler"],
                "scheduler": settings["scheduler"],
                "positive": ["2", 0],
                "negative": ["3", 0],
                "latent_image": ["4", 0],
                "denoise": 1.0,
            },
        ),
        "6": _node("VAEDecode", {"samples": ["5", 0], "vae": ["1", 2]}),
        "7": _node("SaveImage", {"images": ["6", 0], "filename_prefix": filename_prefix}),
    }


def _build_ernie_prompt(
    *,
    settings: dict[str, Any],
    prompt: str,
    negative: str,
    width: int,
    height: int,
    seed: int,
    filename_prefix: str,
) -> dict[str, Any]:
    profile = settings["profile"]
    graph: dict[str, Any] = {
        "1": _node("UNETLoader", {"unet_name": profile["model"], "weight_dtype": "default"}),
        "2": _node("CLIPLoader", {"clip_name": profile["text_encoder"], "type": "flux2", "device": "default"}),
        "3": _node("VAELoader", {"vae_name": profile["vae"]}),
        "4": _node("CLIPTextEncode", {"clip": ["2", 0], "text": clean_prompt_text(prompt)}),
    }
    if profile["builder"] == "ernie_turbo":
        graph["5"] = _node("ConditioningZeroOut", {"conditioning": ["4", 0]})
    else:
        graph["5"] = _node("CLIPTextEncode", {"clip": ["2", 0], "text": clean_prompt_text(negative) or DEFAULT_IMAGE_NEGATIVE})
    graph.update(
        {
            "6": _node("EmptyFlux2LatentImage", {"width": width, "height": height, "batch_size": settings["batch_size"]}),
            "7": _node(
                "KSampler",
                {
                    "model": ["1", 0],
                    "seed": seed,
                    "steps": settings["steps"],
                    "cfg": settings["cfg"],
                    "sampler_name": settings["sampler"],
                    "scheduler": "simple" if settings["scheduler"] == "flux2" else settings["scheduler"],
                    "positive": ["4", 0],
                    "negative": ["5", 0],
                    "latent_image": ["6", 0],
                    "denoise": 1.0,
                },
            ),
            "8": _node("VAEDecode", {"samples": ["7", 0], "vae": ["3", 0]}),
            "9": _node("SaveImage", {"images": ["8", 0], "filename_prefix": filename_prefix}),
        }
    )
    return graph


def _build_hidream_i1_prompt(
    *,
    settings: dict[str, Any],
    prompt: str,
    negative: str,
    width: int,
    height: int,
    seed: int,
    filename_prefix: str,
) -> dict[str, Any]:
    profile = settings["profile"]
    negative_text = clean_prompt_text(negative) if float(settings["cfg"]) > 1.0 else ""
    return {
        "1": _node("UNETLoader", {"unet_name": profile["model"], "weight_dtype": "default"}),
        "2": _node(
            "QuadrupleCLIPLoader",
            {
                "clip_name1": profile["clip_name1"],
                "clip_name2": profile["clip_name2"],
                "clip_name3": profile["clip_name3"],
                "clip_name4": profile["clip_name4"],
            },
        ),
        "3": _node("VAELoader", {"vae_name": profile["vae"]}),
        "4": _node("ModelSamplingSD3", {"model": ["1", 0], "shift": float(profile["shift"])}),
        "5": _node("CLIPTextEncode", {"clip": ["2", 0], "text": clean_prompt_text(prompt)}),
        "6": _node("CLIPTextEncode", {"clip": ["2", 0], "text": negative_text}),
        "7": _node("EmptySD3LatentImage", {"width": width, "height": height, "batch_size": settings["batch_size"]}),
        "8": _node(
            "KSampler",
            {
                "model": ["4", 0],
                "seed": seed,
                "steps": settings["steps"],
                "cfg": settings["cfg"],
                "sampler_name": settings["sampler"],
                "scheduler": settings["scheduler"],
                "positive": ["5", 0],
                "negative": ["6", 0],
                "latent_image": ["7", 0],
                "denoise": 1.0,
            },
        ),
        "9": _node("VAEDecode", {"samples": ["8", 0], "vae": ["3", 0]}),
        "10": _node("SaveImage", {"images": ["9", 0], "filename_prefix": filename_prefix}),
    }


def _build_hidream_prompt(
    *,
    settings: dict[str, Any],
    prompt: str,
    negative: str,
    width: int,
    height: int,
    seed: int,
    filename_prefix: str,
) -> dict[str, Any]:
    profile = settings["profile"]
    is_dev = profile["builder"] == "hidream_dev"
    graph: dict[str, Any] = {
        "1": _node("CheckpointLoaderSimple", {"ckpt_name": profile["model"]}),
        "2": _node("ModelNoiseScale", {"model": ["1", 0], "noise_scale": 7.6 if is_dev else 8.0}),
        "3": _node("CLIPTextEncode", {"clip": ["1", 1], "text": clean_prompt_text(prompt)}),
        "4": _node("CLIPTextEncode", {"clip": ["1", 1], "text": "" if is_dev else clean_prompt_text(negative)}),
        "5": _node("EmptyHiDreamO1LatentImage", {"width": width, "height": height, "batch_size": settings["batch_size"]}),
        "6": _node("BasicScheduler", {"model": ["2", 0], "scheduler": "normal", "steps": settings["steps"], "denoise": 1.0}),
    }
    model_source: list[Any] = ["2", 0]
    if is_dev:
        graph["7"] = _node("SamplerLCM", {"s_noise": 1.0, "s_noise_end": 1.0, "noise_clip_std": 2.5})
    else:
        graph["7"] = _node("KSamplerSelect", {"sampler_name": settings["sampler"]})
        graph["8"] = _node(
            "HiDreamO1PatchSeamSmoothing",
            {
                "model": ["2", 0],
                "start_percent": 0.8,
                "end_percent": 1.0,
                "pattern": "single_shift",
                "passes": "ramp_2_4",
                "blend": "median",
                "strength": 1.0,
            },
        )
        model_source = ["8", 0]
    graph["9"] = _node(
        "SamplerCustom",
        {
            "model": model_source,
            "add_noise": True,
            "noise_seed": seed,
            "cfg": settings["cfg"],
            "positive": ["3", 0],
            "negative": ["4", 0],
            "sampler": ["7", 0],
            "sigmas": ["6", 0],
            "latent_image": ["5", 0],
        },
    )
    graph["10"] = _node("VAEDecode", {"samples": ["9", 0], "vae": ["1", 2]})
    graph["11"] = _node("SaveImage", {"images": ["10", 0], "filename_prefix": filename_prefix})
    return graph


def _builder_regional_layout(builder: str) -> tuple[str, list[Any]] | None:
    layouts = {
        "qwen": ("7", ["2", 0]),
        "z_image": ("6", ["2", 0]),
        "z_image_turbo": ("6", ["2", 0]),
        "sdxl": ("2", ["1", 1]),
        "chroma": ("5", ["4", 0]),
        "ernie": ("4", ["2", 0]),
        "ernie_turbo": ("4", ["2", 0]),
    }
    return layouts.get(builder)


def _builder_controlnet_layout(builder: str) -> tuple[str, str] | None:
    layouts = {
        "qwen": ("7", "8"),
        "z_image": ("6", "7"),
        "z_image_turbo": ("6", "7"),
        "sdxl": ("2", "3"),
        "chroma": ("5", "6"),
        "ernie": ("4", "5"),
        "ernie_turbo": ("4", "5"),
    }
    return layouts.get(builder)


def build_image_prompt(
    *,
    prompt: str,
    negative: str,
    width: int,
    height: int,
    seed: int,
    profile_id: str = "qwen2512_lightning_fp8",
    steps: int = 4,
    cfg: float = 1.0,
    sampler: str = "euler",
    scheduler: str = "simple",
    batch_size: int = 1,
    filename_prefix: str = "image_studio/Image",
    nsfw: bool = False,
    nsfw_lora_strength: float = 1.0,
    secondary_lora_name: str = "",
    secondary_lora_strength: float = 0.8,
    regional_face_prompt: str = "",
    regional_body_prompt: str = "",
    pose_map_filename: str = "",
    controlnet_name: str = "",
    controlnet_strength: float = 0.7,
    source_image: str = "",
    reference_images: list[str] | None = None,
    edit_strength: float = 0.35,
    edit_resize_mode: str = "crop",
) -> dict[str, Any]:
    settings = normalized_generation_settings(
        profile_id,
        steps=steps,
        cfg=cfg,
        sampler=sampler,
        scheduler=scheduler,
        batch_size=batch_size,
    )
    builder = settings["profile"]["builder"]
    common = {
        "settings": settings,
        "prompt": prompt,
        "width": int(width),
        "height": int(height),
        "seed": int(seed),
        "filename_prefix": filename_prefix,
    }
    graph: dict[str, Any]
    lora_kwargs = {
        "secondary_lora_name": secondary_lora_name,
        "secondary_lora_strength": secondary_lora_strength,
    }
    if builder == "qwen_edit_2511":
        graph = _build_qwen_edit_2511_prompt(
            settings=settings,
            prompt=prompt,
            negative=negative,
            source_image=source_image,
            seed=int(seed),
            filename_prefix=filename_prefix,
        )
    elif builder == "qwen21":
        graph = _build_qwen21_prompt(
            **common,
            negative=negative,
            nsfw=nsfw,
            nsfw_lora_strength=nsfw_lora_strength,
            source_image=source_image,
            reference_images=reference_images,
        )
    elif builder == "qwen":
        graph = _build_qwen_prompt(
            **common,
            negative=negative,
            nsfw=nsfw,
            nsfw_lora_strength=nsfw_lora_strength,
            **lora_kwargs,
        )
    elif builder in {"z_image", "z_image_turbo"}:
        graph = _build_z_image_prompt(
            **common,
            negative=negative,
            nsfw=nsfw,
            nsfw_lora_strength=nsfw_lora_strength,
            **lora_kwargs,
        )
    elif builder == "flux2":
        graph = _build_flux2_prompt(**common, nsfw=nsfw)
    elif builder in {"flux2_klein_distilled", "flux2_klein_base"}:
        graph = _build_flux2_klein_prompt(**common, negative=negative, nsfw=nsfw)
    elif builder == "chroma":
        graph = _build_chroma_prompt(**common, negative=negative)
    elif builder == "sdxl":
        graph = _build_sdxl_prompt(**common, negative=negative)
    elif builder in {"ernie", "ernie_turbo"}:
        graph = _build_ernie_prompt(**common, negative=negative)
    elif builder == "hidream_i1":
        graph = _build_hidream_i1_prompt(**common, negative=negative)
    elif builder in {"hidream_dev", "hidream_full"}:
        graph = _build_hidream_prompt(**common, negative=negative)
    else:
        raise ValueError(f"unsupported image workflow builder: {builder}")
    if source_image and builder not in {"qwen_edit_2511", "qwen21"}:
        graph = _apply_image_edit(
            graph,
            settings=settings,
            source_image=source_image,
            width=int(width),
            height=int(height),
            edit_strength=float(edit_strength),
            edit_resize_mode="stretch" if edit_resize_mode == "stretch" else "crop",
        )
    face_prompt = str(regional_face_prompt or "").strip()
    body_prompt = str(regional_body_prompt or "").strip()
    pose_map = str(pose_map_filename or "").strip()
    controlnet = str(controlnet_name or "").strip()
    if builder in {"sdxl", "z_image", "z_image_turbo", "qwen", "chroma", "ernie", "ernie_turbo"}:
        from beginner_frontend.nsfw_extensions import apply_controlnet_pose, apply_regional_conditioning

        regional_layout = _builder_regional_layout(builder)
        if regional_layout and (face_prompt or body_prompt):
            positive_node, clip_node = regional_layout
            graph = apply_regional_conditioning(
                graph,
                positive_node=positive_node,
                clip_node=clip_node,
                face_prompt=face_prompt or prompt,
                body_prompt=body_prompt or prompt,
                width=int(width),
                height=int(height),
            )
        controlnet_layout = _builder_controlnet_layout(builder)
        if pose_map and controlnet and controlnet_layout:
            graph["95"] = _node("LoadImage", {"image": pose_map})
            positive_node, negative_node = controlnet_layout
            if face_prompt or body_prompt:
                positive_node = "203"
            graph = apply_controlnet_pose(
                graph,
                image_node="95",
                positive=positive_node,
                negative=negative_node,
                controlnet_name=controlnet,
                strength=float(controlnet_strength),
            )
    return graph


def build_qwen_image_prompt(**kwargs: Any) -> dict[str, Any]:
    return build_image_prompt(**kwargs)


def image_studio_static_payload() -> dict[str, Any]:
    from beginner_frontend.nsfw_playbook import default_playbook

    families = list(dict.fromkeys(str(item["family"]) for item in IMAGE_PROFILES))
    playbook = default_playbook()
    styles = [dict(item) for item in STYLE_PRESETS] + [dict(item) for item in playbook["nsfw_styles"]]
    return {
        "install_profile": QWEN_IMAGE_INSTALL_PROFILE,
        "profiles": [{**item, "image_edit": image_edit_capability(str(item["id"]))} for item in IMAGE_PROFILES],
        "families": families,
        "aspect_presets": [dict(item) for item in ASPECT_PRESETS],
        "style_presets": styles,
        "prompt_modes": [dict(item) for item in PROMPT_MODES],
        "samplers": sorted(ALLOWED_SAMPLERS),
        "schedulers": sorted(ALLOWED_SCHEDULERS),
        "nsfw_playbook": playbook,
        "defaults": {
            "prompt": DEFAULT_IMAGE_PROMPT,
            "negative": DEFAULT_IMAGE_NEGATIVE,
            "profile": IMAGE_PROFILES[0]["id"],
            "aspect": "landscape",
            "style_preset": "photo",
            "prompt_mode": "structured",
            "batch_size": 1,
            "seed": -1,
            "nsfw": False,
            "edit_mode": False,
            "edit_strength": 0.35,
            "source_adherence": 0.65,
            "edit_resize_mode": "crop",
            "nsfw_intensity": "medium",
            "nsfw_scene": "",
            "auto_inject_trigger": True,
            "auto_strip_negative": True,
            "custom_trigger": "",
        },
    }
