"""Social publishing targets and model-native generation recipes.

The platform deliberately separates the *generation canvas* from the final
publishing canvas. Video diffusion models are usually more stable at their
native multiples of 32 and frame-count rules; post-processing can then deliver
the exact 1080p shape expected by a social platform.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


QUALITY_TIERS: list[dict[str, Any]] = [
    {
        "id": "preview",
        "label": "快速试镜",
        "description": "先看主体、动作和运镜，尺寸与时长最保守。",
        "seconds": 2.0,
    },
    {
        "id": "balanced",
        "label": "均衡成片",
        "description": "默认推荐，兼顾稳定性、细节和生成时间。",
        "seconds": 5.0,
    },
    {
        "id": "quality",
        "label": "正式高质量",
        "description": "更大的生成画布，并建议接时序修复与目标分辨率输出。",
        "seconds": 6.0,
    },
]


SOCIAL_TARGETS: list[dict[str, Any]] = [
    {
        "id": "tiktok",
        "label": "TikTok",
        "group": "竖屏短视频",
        "format": "vertical_9_16",
        "aspect_ratio": "9:16",
        "target_width": 1080,
        "target_height": 1920,
        "target_fps": 30,
        "safe_zone": {"top": 8, "right": 14, "bottom": 20, "left": 6},
        "note": "全屏竖屏；主体和字幕避开右侧操作栏与底部文案区。",
        "source": "https://ads.tiktok.com/business/library/Top_Tips_One_Pager_SMB.pdf",
    },
    {
        "id": "instagram_reels",
        "label": "Instagram Reels",
        "group": "竖屏短视频",
        "format": "vertical_9_16",
        "aspect_ratio": "9:16",
        "target_width": 1080,
        "target_height": 1920,
        "target_fps": 30,
        "safe_zone": {"top": 13, "right": 8, "bottom": 18, "left": 8},
        "note": "9:16 带声音；重要主体、品牌和字幕放在中央安全区。",
        "source": "https://www.facebook.com/business/ads/facebook-instagram-reels-ads",
    },
    {
        "id": "youtube_shorts",
        "label": "YouTube Shorts",
        "group": "竖屏短视频",
        "format": "vertical_9_16",
        "aspect_ratio": "9:16",
        "target_width": 1080,
        "target_height": 1920,
        "target_fps": 30,
        "safe_zone": {"top": 9, "right": 15, "bottom": 18, "left": 6},
        "note": "竖屏或方形均可归类 Shorts；此处使用通用 1080p 竖屏交付。",
        "source": "https://support.google.com/youtube/answer/10059070",
    },
    {
        "id": "douyin",
        "label": "抖音",
        "group": "竖屏短视频",
        "format": "vertical_9_16",
        "aspect_ratio": "9:16",
        "target_width": 1080,
        "target_height": 1920,
        "target_fps": 30,
        "safe_zone": {"top": 9, "right": 15, "bottom": 21, "left": 6},
        "note": "采用保守竖屏安全区；发布前仍以客户端实时预览为准。",
        "source": "https://creator.douyin.com/",
    },
    {
        "id": "xiaohongshu",
        "label": "小红书",
        "group": "竖屏短视频",
        "format": "vertical_9_16",
        "aspect_ratio": "9:16",
        "target_width": 1080,
        "target_height": 1920,
        "target_fps": 30,
        "safe_zone": {"top": 8, "right": 9, "bottom": 17, "left": 9},
        "note": "生活方式内容优先竖屏；标题、价格和人物脸部留在中央区域。",
        "source": "https://creator.xiaohongshu.com/",
    },
    {
        "id": "instagram_feed",
        "label": "Instagram 4:5",
        "group": "信息流",
        "format": "portrait_4_5",
        "aspect_ratio": "4:5",
        "target_width": 1080,
        "target_height": 1350,
        "target_fps": 30,
        "safe_zone": {"top": 6, "right": 6, "bottom": 9, "left": 6},
        "note": "适合信息流占屏；避免把关键内容贴在四周裁切边缘。",
        "source": "https://www.facebook.com/business/help/103816146375741",
    },
    {
        "id": "youtube_landscape",
        "label": "YouTube 横屏",
        "group": "横屏内容",
        "format": "landscape_16_9",
        "aspect_ratio": "16:9",
        "target_width": 1920,
        "target_height": 1080,
        "target_fps": 30,
        "safe_zone": {"top": 6, "right": 6, "bottom": 8, "left": 6},
        "note": "标准 16:9 1080p；不要主动加黑边，交给播放器适配。",
        "source": "https://support.google.com/youtube/answer/6375112",
    },
    {
        "id": "bilibili_landscape",
        "label": "Bilibili 横屏",
        "group": "横屏内容",
        "format": "landscape_16_9",
        "aspect_ratio": "16:9",
        "target_width": 1920,
        "target_height": 1080,
        "target_fps": 30,
        "safe_zone": {"top": 5, "right": 5, "bottom": 8, "left": 5},
        "note": "通用 1080p 横屏母版；字幕与角标留出播放器边缘。",
        "source": "https://member.bilibili.com/",
    },
]


# Dimensions are model-facing and intentionally use multiples of 32. Exact
# social output sizes are shown separately and handled by post-processing.
ENGINE_DIMENSIONS: dict[str, dict[str, dict[str, tuple[int, int]]]] = {
    "minimax_h3": {
        "vertical_9_16": {
            "preview": (480, 864),
            "balanced": (768, 1344),
            "quality": (1088, 1920),
        },
        "portrait_4_5": {
            "preview": (480, 608),
            "balanced": (768, 960),
            "quality": (1088, 1376),
        },
        "landscape_16_9": {
            "preview": (864, 480),
            "balanced": (1344, 768),
            "quality": (1920, 1088),
        },
    },
    "ltx25": {
        "vertical_9_16": {
            "preview": (352, 640),
            "balanced": (704, 1280),
            "quality": (1088, 1920),
        },
        "portrait_4_5": {
            "preview": (512, 640),
            "balanced": (768, 960),
            "quality": (1088, 1376),
        },
        "landscape_16_9": {
            "preview": (640, 352),
            "balanced": (1280, 704),
            "quality": (1920, 1088),
        },
    },
    "generic": {
        "vertical_9_16": {
            "preview": (480, 832),
            "balanced": (704, 1280),
            "quality": (1088, 1920),
        },
        "portrait_4_5": {
            "preview": (480, 608),
            "balanced": (768, 960),
            "quality": (1088, 1376),
        },
        "landscape_16_9": {
            "preview": (832, 480),
            "balanced": (1280, 704),
            "quality": (1920, 1088),
        },
    },
}


MODE_ENGINES = {
    "minimax_h3_t2v": "minimax_h3",
    "minimax_h3_i2v": "minimax_h3",
    "minimax_h3_r2v": "minimax_h3",
    "ltx25_t2v": "ltx25",
    "ltx25_i2v": "ltx25",
}


FRAME_RULES = {
    "minimax_h3": {"fps": 24, "step": 17, "offset": 5, "minimum": 22, "maximum": 362},
    "ltx25": {"fps": 24, "step": 8, "offset": 1, "minimum": 9, "maximum": 481},
    "generic": {"fps": 24, "step": 4, "offset": 1, "minimum": 17, "maximum": 481},
}


def _by_id(rows: list[dict[str, Any]], item_id: str, fallback: str) -> dict[str, Any]:
    return next((row for row in rows if row["id"] == item_id), next(row for row in rows if row["id"] == fallback))


def _aligned_frames(engine: str, seconds: float) -> tuple[int, int]:
    rule = FRAME_RULES.get(engine, FRAME_RULES["generic"])
    fps = int(rule["fps"])
    target = max(1, round(float(seconds) * fps))
    step = int(rule["step"])
    offset = int(rule["offset"])
    index = round((target - offset) / step)
    frames = offset + max(0, index) * step
    frames = max(int(rule["minimum"]), min(int(rule["maximum"]), frames))
    return frames, fps


def resolve_social_recipe(
    *, mode: str, target_id: str = "tiktok", quality_id: str = "balanced"
) -> dict[str, Any]:
    target = _by_id(SOCIAL_TARGETS, str(target_id or ""), "tiktok")
    quality = _by_id(QUALITY_TIERS, str(quality_id or ""), "balanced")
    engine = MODE_ENGINES.get(str(mode or ""), "generic")
    dimensions = ENGINE_DIMENSIONS.get(engine, ENGINE_DIMENSIONS["generic"])
    width, height = dimensions.get(target["format"], dimensions["landscape_16_9"])[quality["id"]]
    length, fps = _aligned_frames(engine, float(quality["seconds"]))

    advanced: dict[str, Any] = {}
    if engine == "minimax_h3":
        advanced["h3_prompt_format"] = "official_three_part"
    elif engine == "ltx25":
        advanced["ltx25_pipeline_profile"] = quality["id"]

    pipeline = {
        "deflicker": quality["id"] in {"balanced", "quality"},
        "rife": False,
        "upscale": quality["id"] == "quality",
    }
    return {
        "mode": str(mode or ""),
        "engine": engine,
        "target_id": target["id"],
        "quality_id": quality["id"],
        "generation": {
            "width": width,
            "height": height,
            "length": length,
            "fps": fps,
            "seconds": round(length / fps, 2),
            "steps": 20 if engine == "minimax_h3" else 11 if engine == "ltx25" else None,
            "cfg": 1.0 if engine in {"minimax_h3", "ltx25"} else None,
        },
        "delivery": {
            "width": target["target_width"],
            "height": target["target_height"],
            "fps": target["target_fps"],
            "aspect_ratio": target["aspect_ratio"],
        },
        "safe_zone": deepcopy(target["safe_zone"]),
        "advanced": advanced,
        "pipeline": pipeline,
        "note": target["note"],
    }


def social_presets_payload() -> dict[str, Any]:
    recipes: dict[str, Any] = {}
    representative_modes = {
        "minimax_h3": "minimax_h3_t2v",
        "ltx25": "ltx25_t2v",
        "generic": "ti2v_5b",
    }
    for engine, mode in representative_modes.items():
        recipes[engine] = {
            target["id"]: {
                quality["id"]: resolve_social_recipe(
                    mode=mode,
                    target_id=target["id"],
                    quality_id=quality["id"],
                )
                for quality in QUALITY_TIERS
            }
            for target in SOCIAL_TARGETS
        }
    return {
        "default_target": "tiktok",
        "default_quality": "balanced",
        "targets": deepcopy(SOCIAL_TARGETS),
        "quality_tiers": deepcopy(QUALITY_TIERS),
        "recipes": recipes,
    }
