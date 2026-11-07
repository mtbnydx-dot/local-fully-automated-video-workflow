"""Configurable NSFW playbook: presets, linkage helpers, and local overrides.

All defaults are data — users can override via local workflow config under key
`nsfw_playbook` without editing code. UI should always expose the raw knobs
(strength, trigger, auto-inject, negative strip, etc.) alongside presets.
"""

from __future__ import annotations

import copy
import re
import time
import uuid
from typing import Any


PLAYBOOK_CONFIG_KEY = "nsfw_playbook"
CHARACTER_BOX_CONFIG_KEY = "character_box"

DEFAULT_NEGATIVE_STRIP_TERMS = (
    "nsfw",
    "nude",
    "naked",
    "explicit",
    "uncensored",
    "色情",
    "裸露",
    "裸体",
)

# Multipliers applied to a profile's strength_default. Users can still drag the slider.
DEFAULT_INTENSITY_PRESETS: list[dict[str, Any]] = [
    {
        "id": "soft",
        "label": "柔和",
        "multiplier": 0.7,
        "note": "更克制，优先保留构图与画质",
    },
    {
        "id": "medium",
        "label": "标准",
        "multiplier": 1.0,
        "note": "按模型推荐默认强度",
    },
    {
        "id": "strong",
        "label": "强烈",
        "multiplier": 1.15,
        "note": "效果更明显，伪影风险更高",
    },
]

DEFAULT_IMAGE_SCENE_PRESETS: list[dict[str, Any]] = [
    {
        "id": "studio_portrait",
        "label": "影棚人像",
        "group": "摄影",
        "prompt": "成年人物影棚半身人像，柔和轮廓光，干净背景，皮肤质感真实，构图稳定",
        "prompt_en": "adult studio half-body portrait, soft rim light, clean backdrop, realistic skin texture, stable composition",
        "style_hint": "photo",
        "intensity_hint": "medium",
    },
    {
        "id": "boudoir_window",
        "label": "窗边私房",
        "group": "摄影",
        "prompt": "成年人物靠在落地窗边，暖色室内光与窗外冷光对比，丝质织物与皮肤质感清楚，情绪克制",
        "prompt_en": "adult by a floor-to-ceiling window, warm interior light against cool daylight, clear fabric and skin texture, restrained mood",
        "style_hint": "cinematic",
        "intensity_hint": "medium",
    },
    {
        "id": "golden_hour_beach",
        "label": "黄昏海边",
        "group": "外景",
        "prompt": "成年人物站在黄昏海边，逆光轮廓，海风与湿润空气感，电影感长焦构图",
        "prompt_en": "adult standing on a beach at golden hour, backlight silhouette, humid air, cinematic telephoto framing",
        "style_hint": "cinematic",
        "intensity_hint": "soft",
    },
    {
        "id": "rain_neon",
        "label": "雨夜霓虹",
        "group": "外景",
        "prompt": "成年人物走在雨夜霓虹街道，路面反光，潮湿氛围，纪实摄影感",
        "prompt_en": "adult walking a rainy neon street at night, reflective pavement, humid atmosphere, documentary photography feel",
        "style_hint": "photo",
        "intensity_hint": "medium",
    },
    {
        "id": "onsen_steam",
        "label": "温泉蒸汽",
        "group": "场景",
        "prompt": "成年人物在日式温泉池边，热气与木纹细节，柔和散射光，安静氛围",
        "prompt_en": "adult at a Japanese onsen edge, steam and wood grain detail, soft scattered light, quiet atmosphere",
        "style_hint": "photo",
        "intensity_hint": "medium",
    },
    {
        "id": "anime_character",
        "label": "二次元角色",
        "group": "插画",
        "prompt": "成年动漫角色全身立绘，干净线稿，明确服装结构与光影层次，背景简洁",
        "prompt_en": "adult anime character full-body illustration, clean linework, clear outfit structure and lighting layers, simple background",
        "style_hint": "anime",
        "intensity_hint": "strong",
    },
    {
        "id": "editorial_fashion",
        "label": "编辑时尚",
        "group": "摄影",
        "prompt": "成年人物时尚编辑摄影，大胆构图，织物纹理与妆造清楚，杂志封面感",
        "prompt_en": "adult editorial fashion photography, bold composition, clear fabric texture and styling, magazine-cover feel",
        "style_hint": "photo",
        "intensity_hint": "medium",
    },
    {
        "id": "bedroom_lamp",
        "label": "卧室暖光",
        "group": "私密",
        "prompt": "成年人物坐在卧室床边，暖色台灯，床单褶皱清楚，皮肤与织物质感真实，亲密但构图稳定",
        "prompt_en": "adult sitting at the edge of a bedroom bed, warm lamp light, clear sheet folds, realistic skin and fabric, intimate stable framing",
        "style_hint": "nsfw_body_photo",
        "intensity_hint": "strong",
        "fill_mode": "replace",
    },
    {
        "id": "lingerie_mirror",
        "label": "镜前内衣",
        "group": "私密",
        "prompt": "成年人物站在卧室镜前，内衣或丝质织物贴身，镜面反射清楚，柔和室内光，身体结构准确",
        "prompt_en": "adult standing before a bedroom mirror, close-fitting lingerie or silk, clear reflection, soft indoor light, accurate body structure",
        "style_hint": "nsfw_lingerie",
        "intensity_hint": "strong",
        "fill_mode": "replace",
    },
    {
        "id": "nude_portrait",
        "label": "人体特写",
        "group": "私密",
        "prompt": "成年人物裸身人体摄影，自然皮肤纹理，准确身体结构，柔和影棚光，构图稳定，情绪直接",
        "prompt_en": "adult nude body photography, natural skin texture, accurate anatomy, soft studio light, stable framing, direct mood",
        "style_hint": "nsfw_body_photo",
        "intensity_hint": "strong",
        "fill_mode": "replace",
    },
    {
        "id": "shower_steam",
        "label": "淋浴水汽",
        "group": "私密",
        "prompt": "成年人物在淋浴间，水珠与蒸汽，湿润皮肤高光，瓷砖反光，身体结构清楚",
        "prompt_en": "adult in a shower stall, water droplets and steam, wet skin highlights, tile reflections, clear body structure",
        "style_hint": "nsfw_wet",
        "intensity_hint": "strong",
        "fill_mode": "replace",
    },
    {
        "id": "bed_sheets",
        "label": "床单特写",
        "group": "私密",
        "prompt": "成年人物躺在凌乱床单上，近景身体与织物交叠，暖色床头光，皮肤质感清楚",
        "prompt_en": "adult lying on rumpled sheets, close framing of body and fabric, warm bedside light, clear skin texture",
        "style_hint": "nsfw_skin_close",
        "intensity_hint": "strong",
        "fill_mode": "replace",
    },
    {
        "id": "couple_close",
        "label": "双人贴近",
        "group": "双人",
        "prompt": "两名成年人物贴近拥抱，身体接触清楚，亲密氛围，面部与皮肤质感真实，构图稳定",
        "prompt_en": "two adults in a close embrace, clear body contact, intimate mood, realistic faces and skin, stable composition",
        "style_hint": "nsfw_couple",
        "intensity_hint": "strong",
        "fill_mode": "replace",
    },
    {
        "id": "couple_bed",
        "label": "双人床上",
        "group": "双人",
        "prompt": "两名成年人物在床上贴近，肢体交叠，暖色室内光，皮肤与床单质感清楚，动作未开始但关系明确",
        "prompt_en": "two adults close together on a bed, overlapping limbs, warm indoor light, clear skin and sheet texture, relationship clear before motion",
        "style_hint": "nsfw_couple",
        "intensity_hint": "strong",
        "fill_mode": "replace",
    },
    {
        "id": "anime_bedroom",
        "label": "二次元卧室",
        "group": "插画",
        "prompt": "成年动漫角色在卧室场景，身体结构准确，服装或裸身细节清楚，干净线稿，光影层次明确",
        "prompt_en": "adult anime character in a bedroom, accurate body structure, clear clothing or nude detail, clean linework, distinct lighting layers",
        "style_hint": "nsfw_anime_adult",
        "intensity_hint": "strong",
        "fill_mode": "replace",
    },
    {
        "id": "anime_couple",
        "label": "二次元双人",
        "group": "插画",
        "prompt": "两名成年动漫角色贴近，身体接触清楚，线条干净，表情与身体结构准确，背景简洁",
        "prompt_en": "two adult anime characters close together, clear body contact, clean lines, accurate expressions and anatomy, simple background",
        "style_hint": "nsfw_anime_adult",
        "intensity_hint": "strong",
        "fill_mode": "replace",
    },
    {
        "id": "custom_blank",
        "label": "空白自定义",
        "group": "自定义",
        "prompt": "",
        "prompt_en": "",
        "style_hint": "none",
        "intensity_hint": "medium",
        "fill_mode": "replace",
    },
]

DEFAULT_NSFW_STYLE_PRESETS: list[dict[str, Any]] = [
    {
        "id": "nsfw_body_photo",
        "label": "写实人体",
        "prompt": "写实人体摄影，自然皮肤纹理，准确解剖结构，柔和影棚光",
        "prompt_en": "realistic body photography, natural skin texture, accurate anatomy, soft studio light",
        "nsfw_only": True,
    },
    {
        "id": "nsfw_film_grain",
        "label": "胶片颗粒",
        "prompt": "胶片摄影质感，细腻颗粒，柔和高光，色彩轻微复古",
        "prompt_en": "film photography look, fine grain, soft highlights, slightly vintage color",
        "nsfw_only": True,
    },
    {
        "id": "nsfw_anime_adult",
        "label": "成年二次元",
        "prompt": "高完成度成年向动画插画，线条干净，身体结构准确，色彩统一",
        "prompt_en": "high-finish adult anime illustration, clean lines, accurate body structure, cohesive color",
        "nsfw_only": True,
    },
    {
        "id": "nsfw_dark_moody",
        "label": "暗调情绪",
        "prompt": "暗调情绪光，高对比轮廓，低关键细节保留，氛围压抑而克制",
        "prompt_en": "dark moody lighting, high-contrast rim light, preserved shadow detail, restrained atmosphere",
        "nsfw_only": True,
    },
    {
        "id": "nsfw_skin_close",
        "label": "皮肤特写",
        "prompt": "近景皮肤质感，毛孔与高光清楚，身体结构准确，浅景深",
        "prompt_en": "close-up skin texture, visible pores and highlights, accurate anatomy, shallow depth of field",
        "nsfw_only": True,
    },
    {
        "id": "nsfw_wet",
        "label": "水感湿润",
        "prompt": "湿润皮肤与水珠高光，蒸汽或水雾，材质反光清楚",
        "prompt_en": "wet skin and water-bead highlights, steam or mist, clear material reflections",
        "nsfw_only": True,
    },
    {
        "id": "nsfw_lingerie",
        "label": "内衣质感",
        "prompt": "贴身织物与皮肤交界清楚，蕾丝或丝质纹理，身体曲线准确",
        "prompt_en": "clear fabric-to-skin edges, lace or silk texture, accurate body curves",
        "nsfw_only": True,
    },
    {
        "id": "nsfw_couple",
        "label": "双人亲密",
        "prompt": "双人身体接触清楚，皮肤贴合与手部位置合理，亲密光影",
        "prompt_en": "clear two-person body contact, plausible skin contact and hand placement, intimate lighting",
        "nsfw_only": True,
    },
]

DEFAULT_VIDEO_SCENE_PRESETS: list[dict[str, Any]] = [
    {
        "id": "slow_approach",
        "label": "缓慢走近",
        "group": "镜头",
        "prompt_suffix": "镜头缓慢推向主体，步伐自然，主体外观与构图保持稳定",
        "prompt_suffix_en": "camera slowly pushes in toward the subject, natural walking pace, stable appearance and framing",
        "motion_hint": "soft",
    },
    {
        "id": "turn_look",
        "label": "转身回看",
        "group": "动作",
        "prompt_suffix": "主体自然转身回看镜头，动作连贯，面部与身份细节保持一致",
        "prompt_suffix_en": "subject naturally turns to look back at camera, coherent motion, consistent face and identity detail",
        "motion_hint": "medium",
    },
    {
        "id": "hair_wind",
        "label": "发丝随风",
        "group": "氛围",
        "prompt_suffix": "微风吹动发丝与织物或皮肤高光，动态细腻，背景轻微景深变化",
        "prompt_suffix_en": "light wind moves hair and fabric or skin highlights, subtle motion, mild depth-of-field change in background",
        "motion_hint": "soft",
    },
    {
        "id": "lie_down",
        "label": "缓缓躺下",
        "group": "动作",
        "prompt_suffix": "主体缓慢躺下并调整姿态，动作平滑，肢体结构保持合理",
        "prompt_suffix_en": "subject slowly lies down and adjusts pose, smooth motion, anatomically coherent limbs",
        "motion_hint": "medium",
    },
    {
        "id": "orbit_shot",
        "label": "环绕运镜",
        "group": "镜头",
        "prompt_suffix": "镜头绕主体缓慢环绕，主体姿态稳定，光影随角度自然变化",
        "prompt_suffix_en": "camera slowly orbits the subject, stable pose, lighting shifts naturally with angle",
        "motion_hint": "strong",
    },
    {
        "id": "breathe_idle",
        "label": "呼吸微动",
        "group": "氛围",
        "prompt_suffix": "主体几乎静止，只有呼吸与细微重心变化，身份与构图保持稳定",
        "prompt_suffix_en": "subject almost still, only breathing and tiny weight shifts, stable identity and framing",
        "motion_hint": "soft",
    },
    {
        "id": "lean_in",
        "label": "靠近镜头",
        "group": "镜头",
        "prompt_suffix": "主体缓慢靠近镜头，上身前倾，面部与身体结构保持稳定",
        "prompt_suffix_en": "subject slowly leans toward camera, torso coming closer, stable face and body structure",
        "motion_hint": "medium",
    },
    {
        "id": "undress_slow",
        "label": "缓缓更衣",
        "group": "亲密",
        "prompt_suffix": "衣物缓慢滑落或解开，动作连贯，身份与面部保持稳定",
        "prompt_suffix_en": "clothing slowly slips or unfastens, coherent motion, stable identity and face",
        "motion_hint": "medium",
    },
    {
        "id": "hands_body",
        "label": "手部抚过",
        "group": "亲密",
        "prompt_suffix": "手沿身体缓慢移动，接触清楚，节奏平稳，身体结构保持合理",
        "prompt_suffix_en": "a hand slowly travels along the body, clear contact, steady rhythm, anatomically coherent",
        "motion_hint": "medium",
    },
    {
        "id": "lie_intimate",
        "label": "躺卧贴近",
        "group": "亲密",
        "prompt_suffix": "主体在床上缓慢调整姿态并贴近镜头，动作平滑，身份保持稳定",
        "prompt_suffix_en": "subject slowly adjusts pose on the bed and draws closer to camera, smooth motion, stable identity",
        "motion_hint": "soft",
    },
    {
        "id": "two_person_close",
        "label": "两人靠近",
        "group": "亲密",
        "prompt_suffix": "两人自然靠近拥抱，身体接触增加，动作连贯，面部身份保持稳定",
        "prompt_suffix_en": "two people naturally draw into an embrace, increasing body contact, coherent motion, stable facial identity",
        "motion_hint": "soft",
    },
    {
        "id": "kiss_close",
        "label": "亲吻靠近",
        "group": "亲密",
        "prompt_suffix": "两人深吻靠近，头部与手部动作自然，身份保持稳定",
        "prompt_suffix_en": "two people kiss closely, natural head and hand motion, stable identity",
        "motion_hint": "medium",
    },
    {
        "id": "hip_sway",
        "label": "髋部律动",
        "group": "直给",
        "prompt_suffix": "主体扭动髋部，节奏清楚，身体结构保持合理",
        "prompt_suffix_en": "subject sways the hips with a clear rhythm, anatomically coherent",
        "motion_hint": "medium",
    },
    {
        "id": "doggy_motion",
        "label": "后入节奏",
        "group": "直给",
        "prompt_suffix": "后入姿态，节奏稳定，身体接触清楚，身份保持稳定",
        "prompt_suffix_en": "doggy-style pose, steady rhythm, clear body contact, stable identity",
        "motion_hint": "strong",
    },
    {
        "id": "missionary_pov",
        "label": "传教士 POV",
        "group": "直给",
        "prompt_suffix": "POV 传教士姿态，镜头贴近，节奏自然，面部与身体结构保持稳定",
        "prompt_suffix_en": "POV missionary pose, camera close, natural rhythm, stable face and body structure",
        "motion_hint": "medium",
    },
    {
        "id": "reverse_cowgirl",
        "label": "反向骑乘",
        "group": "直给",
        "prompt_suffix": "反向骑乘姿态，上下律动，节奏清楚，身体结构保持合理",
        "prompt_suffix_en": "reverse cowgirl pose, up-and-down motion, clear rhythm, anatomically coherent",
        "motion_hint": "strong",
    },
    {
        "id": "hand_motion",
        "label": "手部往复",
        "group": "直给",
        "prompt_suffix": "手部往复动作，节奏清晰，接触清楚，身份保持稳定",
        "prompt_suffix_en": "reciprocating hand motion, clear rhythm and contact, stable identity",
        "motion_hint": "medium",
    },
]

DEFAULT_VIDEO_MOTION_PRESETS: list[dict[str, Any]] = [
    {
        "id": "soft",
        "label": "弱动",
        "length_factor": 0.85,
        "cfg_delta": -0.5,
        "prompt_suffix": "动作幅度很小，优先保持主体稳定",
        "prompt_suffix_en": "very small motion amplitude, prioritize subject stability",
        "unrestricted_multiplier": 0.85,
    },
    {
        "id": "medium",
        "label": "中动",
        "length_factor": 1.0,
        "cfg_delta": 0.0,
        "prompt_suffix": "动作自然适中，兼顾稳定与动态",
        "prompt_suffix_en": "natural moderate motion, balance stability and dynamics",
        "unrestricted_multiplier": 1.0,
    },
    {
        "id": "strong",
        "label": "大动",
        "length_factor": 1.15,
        "cfg_delta": 0.5,
        "prompt_suffix": "动作更明显，接受更多形变风险",
        "prompt_suffix_en": "stronger motion, accept higher deformation risk",
        "unrestricted_multiplier": 1.1,
    },
]

DEFAULT_FACE_STRENGTH_PRESETS: list[dict[str, Any]] = [
    {"id": "preserve", "label": "保留五官", "strength": 35.0, "note": "更像原图，替换感弱"},
    {"id": "balanced", "label": "均衡", "strength": 70.0, "note": "身份与原图折中"},
    {"id": "replace", "label": "强替换", "strength": 95.0, "note": "更贴近身份脸"},
]

DEFAULT_KEYFRAME_CONSISTENCY_NEGATIVE: tuple[str, ...] = (
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

DEFAULT_EDIT_STRENGTH_PRESETS: list[dict[str, Any]] = [
    {"id": "soft", "label": "柔和", "strength": 0.25, "note": "更贴近原图，改动小"},
    {"id": "medium", "label": "标准", "strength": 0.4, "note": "均衡编辑幅度"},
    {"id": "strong", "label": "强烈", "strength": 0.65, "note": "改动更大，结构变化更明显"},
]

DEFAULT_MOTION_LORA_PACKS: list[dict[str, Any]] = [
    {
        "id": "orbit_shot",
        "label": "环绕运镜 Orbit",
        "high": "Wan2.2/Motion/orbit_shot_high.safetensors",
        "low": "Wan2.2/Motion/orbit_shot_low.safetensors",
        "trigger": "orbit 360",
        "prompt_suffix": "镜头绕主体缓慢环绕 360 度",
        "motion_hint": "strong",
        "install_profile": "wan22-motion-lora-pack",
        "note": "ostris 环绕运镜；触发词 orbit 360。",
    },
    {
        "id": "dance_hip",
        "label": "髋部律动 Dance Hip",
        "high": "Wan2.2/Motion/dance_hip_high.safetensors",
        "low": "Wan2.2/Motion/dance_hip_low.safetensors",
        "trigger": "",
        "prompt_suffix": "主体随节奏扭动髋部，动作连贯",
        "motion_hint": "medium",
        "install_profile": "wan22-motion-lora-pack",
        "note": "舞蹈向髋部律动。",
    },
    {
        "id": "twerk",
        "label": "扭臀律动 Twerk",
        "high": "Wan2.2/Motion/twerk_high.safetensors",
        "low": "Wan2.2/Motion/twerk_low.safetensors",
        "trigger": "",
        "prompt_suffix": "主体扭臀律动，节奏明显",
        "motion_hint": "strong",
        "install_profile": "wan22-motion-lora-pack",
        "note": "扭臀舞蹈动作。",
    },
    {
        "id": "hug",
        "label": "拥抱 Hug",
        "high": "Wan2.2/Motion/hug_high.safetensors",
        "low": "Wan2.2/Motion/hug_low.safetensors",
        "trigger": "",
        "prompt_suffix": "两人自然拥抱靠近",
        "motion_hint": "soft",
        "install_profile": "wan22-motion-lora-pack",
        "note": "拥抱靠近动作。",
    },
    {
        "id": "sleep_lie",
        "label": "躺卧入睡 Sleep",
        "high": "Wan2.2/Motion/sleep_high.safetensors",
        "low": "Wan2.2/Motion/sleep_low.safetensors",
        "trigger": "",
        "prompt_suffix": "主体缓慢躺下并进入休息姿态",
        "motion_hint": "soft",
        "install_profile": "wan22-motion-lora-pack",
        "note": "躺卧 / 入睡动作。",
    },
    {
        "id": "french_kiss",
        "label": "法式接吻 French Kiss",
        "high": "Wan2.2/Motion/french_kiss_high.safetensors",
        "low": "Wan2.2/Motion/french_kiss_low.safetensors",
        "trigger": "",
        "prompt_suffix": "两人深吻，动作自然",
        "motion_hint": "medium",
        "install_profile": "wan22-motion-lora-pack",
        "note": "接吻动作。",
    },
    {
        "id": "doggy",
        "label": "后入 Doggy",
        "high": "Wan2.2/Motion/doggy_high.safetensors",
        "low": "Wan2.2/Motion/doggy_low.safetensors",
        "trigger": "",
        "prompt_suffix": "后入姿态，节奏稳定",
        "motion_hint": "strong",
        "install_profile": "wan22-motion-lora-pack",
        "note": "成人后入动作（I2V）。",
    },
    {
        "id": "missionary_pov",
        "label": "传教士 POV",
        "high": "Wan2.2/Motion/missionary_pov_high.safetensors",
        "low": "Wan2.2/Motion/missionary_pov_low.safetensors",
        "trigger": "",
        "prompt_suffix": "POV 传教士姿态，镜头贴近",
        "motion_hint": "medium",
        "install_profile": "wan22-motion-lora-pack",
        "note": "成人传教士 POV。",
    },
    {
        "id": "reverse_cowgirl",
        "label": "反向骑乘 Cowgirl",
        "high": "Wan2.2/Motion/reverse_cowgirl_high.safetensors",
        "low": "Wan2.2/Motion/reverse_cowgirl_low.safetensors",
        "trigger": "",
        "prompt_suffix": "反向骑乘姿态，上下律动",
        "motion_hint": "strong",
        "install_profile": "wan22-motion-lora-pack",
        "note": "成人反向骑乘。",
    },
    {
        "id": "handjob",
        "label": "手部动作 Handjob",
        "high": "Wan2.2/Motion/handjob_high.safetensors",
        "low": "Wan2.2/Motion/handjob_low.safetensors",
        "trigger": "",
        "prompt_suffix": "手部往复动作，节奏清晰",
        "motion_hint": "medium",
        "install_profile": "wan22-motion-lora-pack",
        "note": "成人手部动作。",
    },
]

DEFAULT_VIDEO_MODEL_FALLBACKS: dict[str, list[str]] = {
    "i2v": ["minimax_h3_i2v", "ltx25_i2v", "i2v_a14b"],
    "t2v": ["minimax_h3_t2v", "ltx25_t2v", "t2v_a14b"],
}

DEFAULT_WIZARD_MODES: list[dict[str, Any]] = [
    {
        "id": "tasteful",
        "label": "唯美克制",
        "group": "成片",
        "note": "Qwen 静帧 → H3 图生视频，呼吸微动",
        "image_scene": "studio_portrait",
        "image_style": "nsfw_body_photo",
        "intensity": "soft",
        "video_scene": "breathe_idle",
        "video_motion": "soft",
        "auto_unrestricted": True,
        "auto_inject_trigger": True,
        "auto_strip_negative": True,
        "preferred_image_profile": "qwen2512_lightning_fp8",
        "preferred_image_profiles": ["qwen2512_lightning_fp8", "lustify_sdxl_v40"],
        "preferred_video_model": "minimax_h3_i2v",
        "preferred_video_models": ["minimax_h3_i2v", "ltx25_i2v"],
        "one_click": True,
        "pipeline": "still_then_i2v",
    },
    {
        "id": "bold",
        "label": "卧室私房",
        "group": "成片",
        "note": "Lustify 卧室静帧 → H3 躺卧微动",
        "image_scene": "bedroom_lamp",
        "image_style": "nsfw_body_photo",
        "intensity": "strong",
        "video_scene": "lie_intimate",
        "video_motion": "soft",
        "auto_unrestricted": True,
        "auto_inject_trigger": True,
        "auto_strip_negative": True,
        "preferred_image_profile": "lustify_sdxl_v40",
        "preferred_image_profiles": ["lustify_sdxl_v40", "qwen2512_lightning_fp8"],
        "preferred_video_model": "minimax_h3_i2v",
        "preferred_video_models": ["minimax_h3_i2v", "ltx25_i2v"],
        "one_click": True,
        "pipeline": "still_then_i2v",
    },
    {
        "id": "wet",
        "label": "水感湿身",
        "group": "成片",
        "note": "淋浴静帧 → H3，发丝与水珠微动",
        "image_scene": "shower_steam",
        "image_style": "nsfw_wet",
        "intensity": "strong",
        "video_scene": "hair_wind",
        "video_motion": "soft",
        "auto_unrestricted": True,
        "auto_inject_trigger": True,
        "auto_strip_negative": True,
        "preferred_image_profile": "lustify_sdxl_v40",
        "preferred_image_profiles": ["lustify_sdxl_v40", "qwen2512_lightning_fp8"],
        "preferred_video_model": "minimax_h3_i2v",
        "preferred_video_models": ["minimax_h3_i2v", "ltx25_i2v"],
        "one_click": True,
        "pipeline": "still_then_i2v",
    },
    {
        "id": "couple",
        "label": "双人亲密",
        "group": "成片",
        "note": "双人静帧 → H3 靠近拥抱",
        "image_scene": "couple_close",
        "image_style": "nsfw_couple",
        "intensity": "strong",
        "video_scene": "two_person_close",
        "video_motion": "soft",
        "auto_unrestricted": True,
        "auto_inject_trigger": True,
        "auto_strip_negative": True,
        "preferred_image_profile": "lustify_sdxl_v40",
        "preferred_image_profiles": ["lustify_sdxl_v40", "qwen2512_lightning_fp8"],
        "preferred_video_model": "minimax_h3_i2v",
        "preferred_video_models": ["minimax_h3_i2v", "ltx25_i2v"],
        "one_click": True,
        "pipeline": "still_then_i2v",
    },
    {
        "id": "kiss",
        "label": "亲吻靠近",
        "group": "成片",
        "note": "双人静帧 → H3 亲吻",
        "image_scene": "couple_close",
        "image_style": "nsfw_couple",
        "intensity": "strong",
        "video_scene": "kiss_close",
        "video_motion": "medium",
        "auto_unrestricted": True,
        "auto_inject_trigger": True,
        "auto_strip_negative": True,
        "preferred_image_profile": "lustify_sdxl_v40",
        "preferred_image_profiles": ["lustify_sdxl_v40", "qwen2512_lightning_fp8"],
        "preferred_video_model": "minimax_h3_i2v",
        "preferred_video_models": ["minimax_h3_i2v", "ltx25_i2v"],
        "one_click": True,
        "pipeline": "still_then_i2v",
    },
    {
        "id": "undress",
        "label": "缓缓更衣",
        "group": "成片",
        "note": "镜前内衣静帧 → H3 更衣过渡",
        "image_scene": "lingerie_mirror",
        "image_style": "nsfw_lingerie",
        "intensity": "strong",
        "video_scene": "undress_slow",
        "video_motion": "medium",
        "auto_unrestricted": True,
        "auto_inject_trigger": True,
        "auto_strip_negative": True,
        "preferred_image_profile": "lustify_sdxl_v40",
        "preferred_image_profiles": ["lustify_sdxl_v40", "qwen2512_lightning_fp8"],
        "preferred_video_model": "minimax_h3_i2v",
        "preferred_video_models": ["minimax_h3_i2v", "ltx25_i2v"],
        "one_click": True,
        "pipeline": "still_then_i2v",
    },
    {
        "id": "explicit",
        "label": "直给图生视频",
        "group": "直给",
        "note": "人体静帧 → H3，靠近镜头；可再点视频动作模板",
        "image_scene": "nude_portrait",
        "image_style": "nsfw_body_photo",
        "intensity": "strong",
        "video_scene": "lean_in",
        "video_motion": "medium",
        "auto_unrestricted": True,
        "auto_inject_trigger": True,
        "auto_strip_negative": True,
        "preferred_image_profile": "lustify_sdxl_v40",
        "preferred_image_profiles": ["lustify_sdxl_v40", "qwen2512_lightning_fp8"],
        "preferred_video_model": "minimax_h3_i2v",
        "preferred_video_models": ["minimax_h3_i2v", "ltx25_i2v"],
        "one_click": True,
        "pipeline": "still_then_i2v",
    },
    {
        "id": "anime",
        "label": "二次元",
        "group": "插画",
        "note": "WAI 角色静帧 → H3 转身回看",
        "image_scene": "anime_character",
        "image_style": "nsfw_anime_adult",
        "intensity": "strong",
        "video_scene": "turn_look",
        "video_motion": "medium",
        "auto_unrestricted": True,
        "auto_inject_trigger": True,
        "auto_strip_negative": True,
        "preferred_image_profile": "wai_nsfw_illustrious_v90",
        "preferred_image_profiles": ["wai_nsfw_illustrious_v90", "qwen2512_lightning_fp8"],
        "preferred_video_model": "minimax_h3_i2v",
        "preferred_video_models": ["minimax_h3_i2v", "ltx25_i2v"],
        "one_click": True,
        "pipeline": "still_then_i2v",
    },
    {
        "id": "action",
        "label": "动作文生视频",
        "group": "视频",
        "note": "不改静帧，切 H3 文生视频并加大动作",
        "image_scene": "",
        "image_style": "nsfw_film_grain",
        "intensity": "medium",
        "video_scene": "hip_sway",
        "video_motion": "strong",
        "auto_unrestricted": True,
        "auto_inject_trigger": True,
        "auto_strip_negative": True,
        "skip_image_prompt": True,
        "preferred_image_profile": "",
        "preferred_video_model": "minimax_h3_t2v",
        "preferred_video_models": ["minimax_h3_t2v", "ltx25_t2v"],
        "one_click": True,
        "pipeline": "t2v",
    },
    {
        "id": "wan_motion",
        "label": "Wan 动作包",
        "group": "直给",
        "note": "优先 Wan A14B 图生视频并叠动作 LoRA；没有则退回 H3 并用提示词",
        "image_scene": "couple_bed",
        "image_style": "nsfw_couple",
        "intensity": "strong",
        "video_scene": "doggy_motion",
        "video_motion": "strong",
        "video_motion_lora_pack": "doggy",
        "auto_unrestricted": True,
        "auto_inject_trigger": True,
        "auto_strip_negative": True,
        "preferred_image_profile": "lustify_sdxl_v40",
        "preferred_image_profiles": ["lustify_sdxl_v40", "qwen2512_lightning_fp8"],
        "preferred_video_model": "i2v_a14b",
        "preferred_video_models": ["i2v_a14b", "minimax_h3_i2v", "ltx25_i2v"],
        "one_click": True,
        "pipeline": "still_then_i2v",
    },
    {
        "id": "keyframe",
        "label": "已有静帧",
        "group": "视频",
        "note": "不改图片提示词，只开视频无限制并套呼吸微动",
        "image_scene": "",
        "image_style": "",
        "intensity": "medium",
        "video_scene": "breathe_idle",
        "video_motion": "soft",
        "auto_unrestricted": True,
        "auto_inject_trigger": True,
        "auto_strip_negative": True,
        "skip_image_prompt": True,
        "preferred_image_profile": "",
        "preferred_video_model": "minimax_h3_i2v",
        "preferred_video_models": ["minimax_h3_i2v", "ltx25_i2v"],
        "one_click": True,
        "pipeline": "keyframe",
    },
    {
        "id": "manual",
        "label": "全手动",
        "group": "自定义",
        "note": "不自动切模型，只留下手动旋钮",
        "image_scene": "custom_blank",
        "image_style": "none",
        "intensity": "medium",
        "video_scene": "",
        "video_motion": "medium",
        "auto_unrestricted": False,
        "auto_inject_trigger": False,
        "auto_strip_negative": False,
        "preferred_image_profile": "",
        "preferred_video_model": "",
        "one_click": False,
        "pipeline": "manual",
    },
]

DEFAULT_LINKAGE: dict[str, Any] = {
    "auto_inject_trigger": True,
    "auto_strip_negative": True,
    "handoff_carry_unrestricted": True,
    "handoff_carry_prompt": True,
    "handoff_append_motion": True,
    "handoff_apply_video_scene": True,
    "wizard_one_click": True,
    "wizard_visible_always": True,
    "scene_applies_style": True,
    "scene_applies_intensity": True,
    "intensity_updates_strength": True,
    "motion_updates_length": True,
    "motion_updates_cfg": True,
    "motion_updates_unrestricted_strength": True,
    "motion_appends_prompt": True,
    "wizard_applies_all": True,
    "show_trigger_in_ui": True,
    "face_auth_reuse": True,
    "face_strength_presets_enabled": True,
    "character_box_shared": True,
}

# Optional advanced modules — all data-driven; UI shows toggles/install links without hard-wiring graphs.
DEFAULT_ADVANCED_MODULES: list[dict[str, Any]] = [
    {
        "id": "dual_lora",
        "label": "双 LoRA 槽位",
        "group": "图片",
        "status": "profile_native",
        "note": "Wan I2V 无限制已是 High/Low 双 LoRA；强度滑条同时作用于两者。其他模型可在配置里声明 secondary_lora。",
        "enabled_default": True,
        "install_profile": "",
        "requires_unrestricted": True,
    },
    {
        "id": "openpose_control",
        "label": "姿态控制（OpenPose）",
        "group": "图片",
        "status": "workflow_native",
        "note": "需上传 OpenPose 图 + ControlNet 模型；无预处理器时用姿态图。",
        "enabled_default": False,
        "install_profile": "",
        "requires_unrestricted": False,
    },
    {
        "id": "detailer",
        "label": "面部/细节 Detailer",
        "group": "图片",
        "status": "workflow_native",
        "note": "Impact FaceDetailer 缺失时使用 ReActorRestoreFace。",
        "enabled_default": False,
        "install_profile": "",
        "requires_unrestricted": False,
    },
    {
        "id": "regional_prompt",
        "label": "分区提示词",
        "group": "图片",
        "status": "workflow_native",
        "note": "ConditioningSetArea + ConditioningCombine 驱动面/体分区提示。",
        "enabled_default": False,
        "install_profile": "",
        "requires_unrestricted": False,
    },
    {
        "id": "video_motion_lora",
        "label": "视频动作 LoRA 包",
        "group": "视频",
        "status": "workflow_native",
        "note": "安装 wan22-motion-lora-pack 后，在视频无限制面板选择动作包叠加 High/Low LoRA。",
        "enabled_default": False,
        "install_profile": "wan22-motion-lora-pack",
        "requires_unrestricted": True,
    },
    {
        "id": "video_face_swap",
        "label": "视频换脸链路",
        "group": "视频",
        "status": "workflow_native",
        "note": "VHS + ReActor 视频换脸；需 face-swap-reactor 安装档。",
        "enabled_default": False,
        "install_profile": "face-swap-reactor",
        "requires_unrestricted": False,
    },
    {
        "id": "rife_auto_chain",
        "label": "RIFE 自动插帧链",
        "group": "视频",
        "status": "workflow_native",
        "note": "视频生成后已有插帧步骤；开关控制是否在交接时建议跳转插帧。",
        "enabled_default": True,
        "install_profile": "",
        "requires_unrestricted": False,
    },
    {
        "id": "klein_visual_lora",
        "label": "Klein 视觉 LoRA",
        "group": "模型扩展",
        "status": "planned_addon",
        "note": "可选视觉侧 LoRA，与 TE 破限独立；需自行准备权重并在配置中启用。",
        "enabled_default": False,
        "install_profile": "",
        "requires_unrestricted": True,
    },
    {
        "id": "ernie_uncensor_te",
        "label": "ERNIE 破限 TE",
        "group": "模型扩展",
        "status": "planned_addon",
        "note": "尚无稳定单文件 TE 破限方案；有可用权重后可在配置中挂接。",
        "enabled_default": False,
        "install_profile": "",
        "requires_unrestricted": True,
    },
]


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _merge_by_id(defaults: list[dict[str, Any]], overrides: Any) -> list[dict[str, Any]]:
    merged = {str(item.get("id")): copy.deepcopy(item) for item in defaults if item.get("id")}
    for item in _as_list(overrides):
        if not isinstance(item, dict) or not item.get("id"):
            continue
        key = str(item["id"])
        if key in merged:
            merged[key].update(item)
        else:
            merged[key] = copy.deepcopy(item)
    # Preserve default order, then append unknown custom ids.
    ordered: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in defaults:
        key = str(item.get("id") or "")
        if key and key in merged:
            ordered.append(merged[key])
            seen.add(key)
    for key, item in merged.items():
        if key not in seen:
            ordered.append(item)
    return ordered


def default_playbook() -> dict[str, Any]:
    return {
        "intensity_presets": copy.deepcopy(DEFAULT_INTENSITY_PRESETS),
        "image_scenes": copy.deepcopy(DEFAULT_IMAGE_SCENE_PRESETS),
        "nsfw_styles": copy.deepcopy(DEFAULT_NSFW_STYLE_PRESETS),
        "video_scenes": copy.deepcopy(DEFAULT_VIDEO_SCENE_PRESETS),
        "video_motion": copy.deepcopy(DEFAULT_VIDEO_MOTION_PRESETS),
        "face_strength_presets": copy.deepcopy(DEFAULT_FACE_STRENGTH_PRESETS),
        "wizard_modes": copy.deepcopy(DEFAULT_WIZARD_MODES),
        "video_model_fallbacks": copy.deepcopy(DEFAULT_VIDEO_MODEL_FALLBACKS),
        "advanced_modules": copy.deepcopy(DEFAULT_ADVANCED_MODULES),
        "motion_lora_packs": copy.deepcopy(DEFAULT_MOTION_LORA_PACKS),
        "keyframe_consistency_negative": list(DEFAULT_KEYFRAME_CONSISTENCY_NEGATIVE),
        "edit_strength_presets": copy.deepcopy(DEFAULT_EDIT_STRENGTH_PRESETS),
        "negative_strip_terms": list(DEFAULT_NEGATIVE_STRIP_TERMS),
        "linkage": copy.deepcopy(DEFAULT_LINKAGE),
        "customized": False,
    }


def resolve_playbook(config: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = {}
    if isinstance(config, dict):
        candidate = config.get(PLAYBOOK_CONFIG_KEY)
        if isinstance(candidate, dict):
            raw = candidate
    base = default_playbook()
    if not raw:
        return base
    return {
        "intensity_presets": _merge_by_id(base["intensity_presets"], raw.get("intensity_presets")),
        "image_scenes": _merge_by_id(base["image_scenes"], raw.get("image_scenes")),
        "nsfw_styles": _merge_by_id(base["nsfw_styles"], raw.get("nsfw_styles")),
        "video_scenes": _merge_by_id(base["video_scenes"], raw.get("video_scenes")),
        "video_motion": _merge_by_id(base["video_motion"], raw.get("video_motion")),
        "face_strength_presets": _merge_by_id(base["face_strength_presets"], raw.get("face_strength_presets")),
        "wizard_modes": _merge_by_id(base["wizard_modes"], raw.get("wizard_modes")),
        "video_model_fallbacks": {
            **base["video_model_fallbacks"],
            **(raw.get("video_model_fallbacks") if isinstance(raw.get("video_model_fallbacks"), dict) else {}),
        },
        "advanced_modules": _merge_by_id(base["advanced_modules"], raw.get("advanced_modules")),
        "motion_lora_packs": _merge_by_id(base["motion_lora_packs"], raw.get("motion_lora_packs")),
        "keyframe_consistency_negative": [
            str(term).strip()
            for term in (
                raw.get("keyframe_consistency_negative")
                if isinstance(raw.get("keyframe_consistency_negative"), list)
                else base["keyframe_consistency_negative"]
            )
            if str(term).strip()
        ][:80],
        "edit_strength_presets": _merge_by_id(base["edit_strength_presets"], raw.get("edit_strength_presets")),
        "negative_strip_terms": [
            str(term).strip()
            for term in (raw.get("negative_strip_terms") if isinstance(raw.get("negative_strip_terms"), list) else base["negative_strip_terms"])
            if str(term).strip()
        ][:80],
        "linkage": {**base["linkage"], **(raw.get("linkage") if isinstance(raw.get("linkage"), dict) else {})},
        "customized": True,
    }


def playbook_payload(config: dict[str, Any] | None = None) -> dict[str, Any]:
    resolved = resolve_playbook(config)
    return {"ok": True, **resolved}


def find_preset(items: list[dict[str, Any]] | None, preset_id: str) -> dict[str, Any] | None:
    needle = str(preset_id or "").strip()
    if not needle:
        return None
    return next((item for item in (items or []) if str(item.get("id") or "") == needle), None)


def apply_video_motion(
    *,
    length: int,
    cfg: float,
    unrestricted_strength: float,
    prompt: str = "",
    motion_id: str = "medium",
    playbook: dict[str, Any] | None = None,
    language: str = "zh",
) -> dict[str, Any]:
    """Apply motion preset linkage. All multipliers come from playbook data."""
    book = playbook or default_playbook()
    linkage = book.get("linkage") or {}
    motion = find_preset(book.get("video_motion"), motion_id) or find_preset(book.get("video_motion"), "medium") or {}
    next_length = int(length)
    next_cfg = float(cfg)
    next_strength = float(unrestricted_strength)
    next_prompt = str(prompt or "")
    if linkage.get("motion_updates_length", True) and motion.get("length_factor") is not None:
        next_length = max(9, int(round(next_length * float(motion["length_factor"]))))
    if linkage.get("motion_updates_cfg", True) and motion.get("cfg_delta") is not None:
        next_cfg = max(0.1, min(20.0, round(next_cfg + float(motion["cfg_delta"]), 3)))
    if linkage.get("motion_updates_unrestricted_strength", True) and motion.get("unrestricted_multiplier") is not None:
        next_strength = max(0.0, min(1.5, round(next_strength * float(motion["unrestricted_multiplier"]), 4)))
    if linkage.get("motion_appends_prompt", True):
        suffix = motion.get("prompt_suffix_en") if language == "en" else motion.get("prompt_suffix")
        if not suffix:
            suffix = motion.get("prompt_suffix") or motion.get("prompt_suffix_en")
        next_prompt = append_clause(next_prompt, str(suffix or ""))
    return {
        "length": next_length,
        "cfg": next_cfg,
        "unrestricted_strength": next_strength,
        "prompt": next_prompt,
        "motion": motion,
    }


def intensity_strength(profile_nsfw: dict[str, Any] | None, intensity_id: str, playbook: dict[str, Any] | None = None) -> float | None:
    config = profile_nsfw or {}
    if not config.get("lora_name") and config.get("strength_default") is None:
        return None
    book = playbook or default_playbook()
    preset = next((item for item in book["intensity_presets"] if item.get("id") == intensity_id), None)
    if not preset:
        return None
    default = float(config.get("strength_default") or 0.8)
    minimum = float(config.get("strength_min") or 0.0)
    maximum = float(config.get("strength_max") or 1.5)
    value = default * float(preset.get("multiplier") or 1.0)
    return max(minimum, min(maximum, round(value, 4)))


def strip_negative_terms(text: str, terms: list[str] | tuple[str, ...] | None = None) -> str:
    value = str(text or "")
    selected = list(terms) if terms is not None else list(DEFAULT_NEGATIVE_STRIP_TERMS)
    for term in selected:
        token = str(term or "").strip()
        if not token:
            continue
        if token.isascii() and re.search(r"[A-Za-z0-9]", token):
            value = re.sub(rf"(?i)(?:^|[,，]\s*){re.escape(token)}(?=\s*[,，]|$)", ",", value)
        else:
            value = value.replace(token, "")
    value = re.sub(r"\s*,\s*,+", ", ", value)
    return value.strip(" ,，")


def inject_trigger(prompt: str, trigger: str, *, enabled: bool = True) -> str:
    text = str(prompt or "").strip()
    token = str(trigger or "").strip().strip(",")
    if not enabled or not token:
        return text
    # Avoid duplicating an existing trigger (case-insensitive for ascii).
    if token.isascii():
        pattern = rf"(?i)(?:^|[,，\s]){re.escape(token)}(?:[,，\s]|$)"
        if re.search(pattern, text):
            return text
    elif token in text:
        return text
    return f"{token}, {text}" if text else token


def append_clause(prompt: str, clause: str) -> str:
    base = str(prompt or "").strip()
    extra = str(clause or "").strip()
    if not extra:
        return base
    if not base:
        return extra
    if extra in base:
        return base
    joiner = "。" if re.search(r"[\u4e00-\u9fff]", extra) and not base.endswith(("。", ".", "!", "？", "?")) else " "
    if re.search(r"[\u4e00-\u9fff]", extra):
        return f"{base.rstrip('。.')}。{extra}"
    return f"{base.rstrip(', ')}, {extra}"


def normalize_character_box(entries: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in _as_list(entries):
        if not isinstance(raw, dict):
            continue
        identity = str(raw.get("identity_filename") or "").strip()
        if not identity:
            continue
        item_id = str(raw.get("id") or uuid.uuid4().hex[:10])
        if item_id in seen:
            continue
        seen.add(item_id)
        items.append(
            {
                "id": item_id,
                "label": str(raw.get("label") or identity)[:80],
                "identity_filename": identity,
                "identity_subfolder": str(raw.get("identity_subfolder") or ""),
                "identity_type": str(raw.get("identity_type") or "input"),
                "preview_url": str(raw.get("preview_url") or ""),
                "notes": str(raw.get("notes") or "")[:200],
                "created_at": int(raw.get("created_at") or time.time()),
            }
        )
        if len(items) >= 40:
            break
    return items


def character_box_payload(config: dict[str, Any] | None = None) -> dict[str, Any]:
    entries = []
    if isinstance(config, dict):
        entries = config.get(CHARACTER_BOX_CONFIG_KEY) or []
    items = normalize_character_box(entries)
    return {"ok": True, "items": items, "count": len(items)}
