"""Pinned Qwen 2.1 additions; importing this registry never loads model weights."""

COMFY_REVISION = "a8342359c61979b06a8dafb1a47991fe1f30e994"
COMMUNITY_REVISION = "7959e658915f52274897fb573ffeda49de8dc16b"
COMMUNITY_REPO = "abenzerps/Qwen-Image-2.1-Uncensored-Quantized"
BASE_ASSETS = ["qwen_image_21_int8", "qwen_image_21_text_encoder_int8", "qwen_image_21_vae_bf16"]

ASSETS = [
    {
        "id": "qwen21_turbo_int8", "group": "qwen_image_21",
        "label": "Qwen 2.1 Turbo INT8 / 8 步", "step": "文生图 / 多参考编辑",
        "name": "qwen_image_2.1_turbo_int8_convrot.safetensors",
        "url": f"https://huggingface.co/Comfy-Org/Qwen-Image-2.1/resolve/{COMFY_REVISION}/diffusion_models/qwen_image_2.1_turbo_int8_convrot.safetensors",
        "dest": "models/diffusion_models/qwen_image_2.1_turbo_int8_convrot.safetensors",
        "bytes": 7256787829,
        "sha256": "8144a0182964aa8403ad6dbc011db837304167d235161b9aabaa8532e967314c",
    },
    {
        "id": "qwen21_uc_q8_202610", "group": "qwen_image_21",
        "label": "Qwen 2.1 社区 UC Q8 / 2026-10", "step": "独立社区扩散模型",
        "name": "qwen-image-2.1-UC-Q8_0.gguf",
        "url": f"https://huggingface.co/{COMMUNITY_REPO}/resolve/{COMMUNITY_REVISION}/qwen-image-2.1-UC-Q8_0.gguf",
        "dest": "models/diffusion_models/Qwen-Image-2.1-Community-202610/qwen-image-2.1-UC-Q8_0.gguf",
        "bytes": 7591557920,
        "sha256": "cde456c72ea3ecebfc1be783300e972711d875e0c5f1bed33d42b66b156affa8",
        "sensitive": True,
    },
    {
        "id": "qwen21_uc_int8_202610", "group": "qwen_image_21",
        "label": "Qwen 2.1 社区 UC INT8 / 2026-10", "step": "原生节点社区扩散模型",
        "name": "qwen-image-2.1-UC-int8_convrot.safetensors",
        "url": f"https://huggingface.co/{COMMUNITY_REPO}/resolve/{COMMUNITY_REVISION}/qwen-image-2.1-UC-int8_convrot.safetensors",
        "dest": "models/diffusion_models/Qwen-Image-2.1-Community-202610/qwen-image-2.1-UC-int8_convrot.safetensors",
        "bytes": 7256796840,
        "sha256": "5bc5a6c007eff1e0d4004344a24c4af966b9d2c83d142e613b0d456ccceb19ae",
        "sensitive": True,
    },
    {
        "id": "qwen21_uc_lora", "group": "qwen_image_21",
        "label": "Qwen 2.1 社区 UC LoRA / 实验", "step": "可调强度社区扩展",
        "name": "qwen-image-2.1-uncensored-lora.safetensors",
        "url": f"https://huggingface.co/{COMMUNITY_REPO}/resolve/{COMMUNITY_REVISION}/qwen-image-2.1-uncensored-lora.safetensors",
        "dest": "models/loras/Qwen-Image-2.1/qwen-image-2.1-uncensored-lora.safetensors",
        "bytes": 33586704,
        "sha256": "00ee2cb7f00a37b097640c1880ed0d17e368e30599f34bb348fee0e8c2cc4ca1",
        "sensitive": True,
    },
    {
        "id": "qwen21_consistency_lora", "group": "qwen_image_21",
        "label": "Qwen 2.1 Consistency / 保构图编辑", "step": "局部编辑与画面稳定",
        "name": "qwen-image-2.1-consistency.safetensors",
        "url": "https://huggingface.co/ausboss/Qwen-Image-2.1-Consistency-LoRA/resolve/1b58c4406925d6ec5fa9abd2d080531030f7cc0d/qwen-image-2.1-consistency.safetensors",
        "dest": "models/loras/Qwen-Image-2.1/qwen-image-2.1-consistency.safetensors",
        "bytes": 159436496,
        "sha256": "4f44ada1be2189cc23b3d010f9603543403f48454e2f76842a3d30109b20bd63",
    },
    {
        "id": "qwen21_restore_lora", "group": "qwen_image_21",
        "label": "Qwen 2.1 Restore / 照片修复", "step": "降低过度纹理与压缩损伤",
        "name": "qwen-image-2.1-restore.safetensors",
        "url": "https://huggingface.co/ausboss/Qwen-Image-2.1-Restore-LoRA/resolve/30cb947f5b9c6682a85f8d31017be4807c459682/qwen-image-2.1-restore.safetensors",
        "dest": "models/loras/Qwen-Image-2.1/qwen-image-2.1-restore.safetensors",
        "bytes": 159436584,
        "sha256": "65de4f6c2468071d5aa6ffbd82c76bfee7cc8ac28fe960e91bbca4a58f43c08c",
    },
]

INSTALL_PROFILES = {
    "qwen21-turbo-int8": {
        "label": "Qwen 2.1 Turbo 官方 8 步",
        "description": "安装独立 Turbo INT8 权重，复用 Qwen 2.1 编码器与 VAE；不覆盖原版。",
        "asset_ids": ["qwen21_turbo_int8", *BASE_ASSETS[1:]],
        "custom_node_ids": [], "installable": True, "required_comfy_version": "0.36.0", "order": 49.1,
    },
    "qwen21-creative-loras": {
        "label": "Qwen 2.1 保构图 / 照片修复",
        "description": "安装原生 2.1 基础文件及 Consistency / Restore LoRA。社区效果尚未本机实测。",
        "asset_ids": [*BASE_ASSETS, "qwen21_consistency_lora", "qwen21_restore_lora"],
        "custom_node_ids": [], "installable": True, "required_comfy_version": "0.36.0", "order": 49.2,
    },
}
for index, asset_id in enumerate(("qwen21_uc_q8_202610", "qwen21_uc_int8_202610", "qwen21_uc_lora")):
    asset = next(item for item in ASSETS if item["id"] == asset_id)
    INSTALL_PROFILES[f"{asset_id}-addon"] = {
        "label": asset["label"],
        "description": "独立可选扩展；需要 Qwen 2.1 标准基础文件。关闭社区模式即恢复标准图。未做 GPU 实测。",
        "asset_ids": [asset_id], "custom_node_ids": ["gguf_qwen21"] if "q8" in asset_id else [],
        "preserve_existing_node_ids": ["gguf_qwen21"] if "q8" in asset_id else [],
        "installable": True, "sensitive": True, "required_comfy_version": "0.36.0", "order": 49.6 + index / 10,
    }


def image_profiles(base: dict) -> list[dict]:
    """Reuse the native 2.1 contract while keeping every variant opt-in."""
    import copy

    result = []
    for asset in ASSETS:
        item = copy.deepcopy(base)
        item.update({"id": asset["id"], "released": "2026-10", "recommended": False,
                     "optional_asset_ids": [], "source": asset["url"].split("/resolve/")[0],
                     "validation_status": "static_only", "fixed_sampler": "euler", "fixed_scheduler": "simple"})
        if asset.get("sensitive"):
            item.update({"label": asset["label"], "short_label": asset["label"].replace("Qwen 2.1 ", ""),
                         "quantization": "标准 INT8 / 社区 Q8_0" if "q8" in asset["id"] else "INT8 ConvRot / BF16 LoRA" if "lora" in asset["id"] else "INT8 ConvRot",
                         "description": "标准模式使用官方 INT8；确认成人与授权条件后开启社区模式，使用独立扩展。作者标注 Uncensored，不代表平台已验证效果。",
                         "optional_asset_ids": [asset["id"]], "fixed_steps": 25})
            config = {
                "status": "experimental_community", "label": asset["label"], "toggle_enabled": True,
                "asset_id": asset["id"], "addon_profile": f"{asset['id']}-addon", "source": item["source"],
                "standard_model_label": "Qwen-Image-2.1 官方 INT8（标准模式）",
                "trigger": "", "note": "2026-10 固定版本。标准模式保留官方模型；社区效果未做本机 GPU 验证，不自动叠加 Turbo 或旧版 Qwen LoRA。",
            }
            if asset["id"] == "qwen21_uc_lora":
                config.update({"lora_name": asset["dest"].removeprefix("models/loras/"),
                               "required_nodes": ["LoraLoaderModelOnly"], "strength_default": 0.8,
                               "strength_min": 0.0, "strength_max": 1.0, "strength_step": 0.05,
                               "strength_recommended": "0.5-1.0（平台试用范围，非作者实测结论）",
                               "strength_help": "控制社区 LoRA 影响。0 完全旁路；首次建议 0.8，过强可能引起纹理或构图变化。"})
            else:
                loader = "UnetLoaderGGUF" if asset["name"].endswith(".gguf") else "UNETLoader"
                config.update({"model_override": asset["dest"].removeprefix("models/diffusion_models/"),
                               "model_loader": loader, "model_label": asset["label"], "required_nodes": [loader]})
            item["nsfw"] = config
        elif asset["id"] == "qwen21_turbo_int8":
            item.update({"label": "Qwen 2.1 Turbo INT8 · 官方 8 步", "short_label": "Qwen 2.1 Turbo 8 步",
                         "description": "官方 Turbo 独立权重，固定 8 步 / CFG 1 / Euler Simple；支持文生图与多参考编辑。",
                         "model": asset["name"], "install_profile": "qwen21-turbo-int8",
                         "required_asset_ids": [asset["id"], *BASE_ASSETS[1:]], "default_steps": 8,
                         "fixed_steps": 8, "min_steps": 8, "max_steps": 8,
                         "nsfw": {"toggle_enabled": False, "status": "unverified", "label": "此档保持官方 Turbo",
                                  "note": "社区扩展请切换独立社区档，不将 25 步旧 Q8 当成 Turbo。"}})
        else:
            restore = asset["id"] == "qwen21_restore_lora"
            item.update({"label": asset["label"], "short_label": "照片修复 25 步" if restore else "保构图编辑 25 步",
                         "description": ("照片修复试用档，LoRA 0.5，适合模糊或压缩图片；不是无损还原，也不保证人物细节完全一致。" if restore else
                                         "保构图编辑试用档，LoRA 1.0；作者报告可能抑制转头和姿态变化，此类编辑请切回标准档。"),
                         "generation_supported": False, "install_profile": "qwen21-creative-loras",
                         "required_asset_ids": [*BASE_ASSETS, asset["id"]], "uses_lora": True,
                         "lora": asset["dest"].removeprefix("models/loras/"), "lora_strength": 0.5 if restore else 1.0,
                         "fixed_steps": 25, "max_pixels": 2_100_000 if restore else base["max_pixels"],
                         "nsfw": {"toggle_enabled": False, "status": "unverified", "label": "独立编辑 LoRA",
                                  "note": "此档不叠加社区成人扩展，便于单独判断编辑效果。"}})
        result.append(item)
    return result
