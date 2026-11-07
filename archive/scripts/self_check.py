from __future__ import annotations

import argparse
import ast
import asyncio
import contextlib
import http.client
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import importlib
import inspect
import urllib.error
import zipfile
from pathlib import Path
from unittest.mock import patch


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


sys.dont_write_bytecode = True
os.environ.setdefault("BEGINNER_FRONTEND_DISABLE_JOB_PERSISTENCE", "1")
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "-1")

ROOT = Path(__file__).resolve().parents[1]
RELEASE_PACKAGE = ROOT / "github_upload" / "wan22-local-video-workflow"
PACKAGE = RELEASE_PACKAGE if RELEASE_PACKAGE.exists() else ROOT


BASE_PYTHON_FILES = [
    ROOT / "START_WORKFLOW.py",
    ROOT / "beginner_frontend" / "app.py",
    ROOT / "beginner_frontend" / "image_studio.py",
    ROOT / "beginner_frontend" / "model_catalog.py",
    ROOT / "beginner_frontend" / "qwen21_updates.py",
    ROOT / "scripts" / "test_qwen21_updates.py",
    ROOT / "scripts" / "prepare_qwen21_updates.py",
    ROOT / "beginner_frontend" / "social_presets.py",
    ROOT / "beginner_frontend" / "video_params.py",
    ROOT / "beginner_frontend" / "h3_workflows.py",
    ROOT / "scripts" / "test_h3_creative.py",
    ROOT / "scripts" / "prerequisite_doctor.py",
    ROOT / "scripts" / "install_workflow_assets.py",
    ROOT / "scripts" / "install_comfyui.py",
    ROOT / "scripts" / "release_smoke.py",
    ROOT / "scripts" / "clean_bootstrap_smoke.py",
    ROOT / "scripts" / "check_fal_h3_max_release.py",
    ROOT / "scripts" / "test_platform_upgrade.py",
    ROOT / "scripts" / "test_qwen_image_21.py",
    ROOT / "scripts" / "test_qwen_image_21_gguf_cpu.py",
]

PACKAGE_PYTHON_FILES = [
    PACKAGE / "START_WORKFLOW.py",
    PACKAGE / "beginner_frontend" / "app.py",
    PACKAGE / "beginner_frontend" / "image_studio.py",
    PACKAGE / "beginner_frontend" / "model_catalog.py",
    PACKAGE / "beginner_frontend" / "qwen21_updates.py",
    PACKAGE / "scripts" / "test_qwen21_updates.py",
    PACKAGE / "scripts" / "prepare_qwen21_updates.py",
    PACKAGE / "beginner_frontend" / "social_presets.py",
    PACKAGE / "beginner_frontend" / "video_params.py",
    PACKAGE / "beginner_frontend" / "h3_workflows.py",
    PACKAGE / "scripts" / "test_h3_creative.py",
    PACKAGE / "scripts" / "prerequisite_doctor.py",
    PACKAGE / "scripts" / "install_workflow_assets.py",
    PACKAGE / "scripts" / "install_comfyui.py",
    PACKAGE / "scripts" / "release_smoke.py",
    PACKAGE / "scripts" / "clean_bootstrap_smoke.py",
    PACKAGE / "scripts" / "check_fal_h3_max_release.py",
    PACKAGE / "scripts" / "test_platform_upgrade.py",
    PACKAGE / "scripts" / "test_qwen_image_21.py",
    PACKAGE / "scripts" / "test_qwen_image_21_gguf_cpu.py",
]

PYTHON_FILES = BASE_PYTHON_FILES + ([] if PACKAGE == ROOT else PACKAGE_PYTHON_FILES)
for _root in {ROOT, PACKAGE}:
    PYTHON_FILES.extend(_root / name for name in (
        "beginner_frontend/job_queries.py", "beginner_frontend/media_metadata.py", "scripts/test_workbench_logic.py",
    ))

BASE_JS_FILES = [
    ROOT / "scripts" / "test_h3_frontend.cjs",
    ROOT / "beginner_frontend" / "static" / "app.js",
    ROOT / "beginner_frontend" / "static" / "image-studio.js",
    ROOT / "beginner_frontend" / "static" / "download-center.js",
]

PACKAGE_JS_FILES = [
    PACKAGE / "scripts" / "test_h3_frontend.cjs",
    PACKAGE / "beginner_frontend" / "static" / "app.js",
    PACKAGE / "beginner_frontend" / "static" / "image-studio.js",
    PACKAGE / "beginner_frontend" / "static" / "download-center.js",
]

JS_FILES = BASE_JS_FILES + ([] if PACKAGE == ROOT else PACKAGE_JS_FILES)
for _root in {ROOT, PACKAGE}:
    JS_FILES.extend(_root / name for name in (
        "beginner_frontend/static/workflow-state.js", "scripts/test_workbench_state.cjs", "scripts/test_workbench_frontend.cjs",
        "beginner_frontend/static/workbench-journey.js", "scripts/test_workbench_journey.cjs",
    ))

POLLUTION_RE = re.compile(
    r"(__pycache__|\.pyc$|\.DS_Store$|\.log$|\.out\.log$|\.err\.log$|"
    r"\.safetensors$|\.ckpt$|\.pt$|\.pth$|\.gguf$|\.bin$|\.onnx$|"
    r"\.zip$|\.tar$|\.tar\.gz$|\.tgz$|\.7z$|\.rar$|"
    r"\.mp4$|\.mov$|\.mkv$|\.webm$|\.avi$|\.part$)",
    re.IGNORECASE,
)

TEXT_SCAN_SUFFIXES = {
    ".bat",
    ".command",
    ".css",
    ".html",
    ".js",
    ".json",
    ".md",
    ".ps1",
    ".py",
    ".txt",
    ".yaml",
    ".yml",
}

SOURCE_PACKAGE_DIRS = ("beginner_frontend", "scripts", "workflows")
SOURCE_PACKAGE_FILE_SUFFIXES = TEXT_SCAN_SUFFIXES | {".command"}
DEVELOPMENT_EXCLUDED_NAMES = {
    ".git",
    ".venv",
    "ComfyUI",
    "github_upload",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "models",
    "input",
    "output",
    "temp",
    "user",
    "custom_nodes",
}

LOCAL_PATH_PATTERNS = [
    ("local E drive workspace", re.compile(re.escape("E:\\" + "ai photo creat"), re.IGNORECASE)),
    ("local Windows user profile", re.compile(re.escape("C:\\Users\\" + "zlk"), re.IGNORECASE)),
    ("absolute Windows user profile", re.compile(r"C:\\Users\\[^\\\r\n\"']+", re.IGNORECASE)),
    ("local macOS user profile", re.compile(re.escape("/Users/" + "bb" + "zlk"), re.IGNORECASE)),
    ("local macOS user name", re.compile(r"\b" + re.escape("bb" + "zlk") + r"\b", re.IGNORECASE)),
]


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(path)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def package_paths() -> list[Path]:
    if PACKAGE != ROOT:
        return list(PACKAGE.rglob("*"))
    paths = [
        path
        for path in ROOT.iterdir()
        if path.is_file() and not path.name.startswith(".") and path.suffix.lower() in SOURCE_PACKAGE_FILE_SUFFIXES
    ]
    for directory_name in SOURCE_PACKAGE_DIRS:
        directory = ROOT / directory_name
        if not directory.exists():
            continue
        paths.extend(
            path
            for path in directory.rglob("*")
            if not any(part in DEVELOPMENT_EXCLUDED_NAMES for part in path.relative_to(ROOT).parts)
        )
    return paths


def ast_check() -> list[str]:
    checked: list[str] = []
    for path in PYTHON_FILES:
        check(path.exists(), f"missing Python file: {rel(path)}")
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        checked.append(rel(path))
    return checked


def js_check() -> list[str]:
    checked: list[str] = []
    node = shutil_which("node")
    if not node:
        return ["node not found; skipped JS syntax check"]
    for path in JS_FILES:
        check(path.exists(), f"missing JS file: {rel(path)}")
        result = subprocess.run([node, "--check", str(path)], capture_output=True, text=True)
        check(result.returncode == 0, f"JS syntax failed for {rel(path)}: {result.stderr}")
        checked.append(rel(path))
    return checked


def shutil_which(name: str) -> str | None:
    from shutil import which

    return which(name)


def manifest_check() -> dict[str, int]:
    sys.path.insert(0, str(ROOT))
    from beginner_frontend import app as frontend
    from beginner_frontend import model_catalog as catalog
    from scripts import install_workflow_assets as installer

    assets = frontend.workflow_asset_manifest(frontend.BASE_DIR)
    nodes = frontend.custom_node_manifest(frontend.BASE_DIR)
    asset_ids = {item["id"] for item in assets}
    installer_ids = {item["id"] for item in installer.MODEL_FILES}
    check(installer_ids <= asset_ids, "frontend manifest does not cover installer MODEL_FILES")
    check(
        {"ti2v_5b", "rife49", "realesrgan_x2", "seedvr2_3b_int8", "seedvr2_vae_fp16"} <= asset_ids,
        "required asset ids missing",
    )
    h3_asset_ids = {
        "minimax_h3_fl2va_int8",
        "minimax_h3_text_int8",
        "minimax_h3_video_vae",
        "minimax_h3_audio_vae",
    }
    check(h3_asset_ids <= asset_ids, "MiniMax H3 four-file manifest is incomplete")
    check("minimax_h3_lightx4_v11_768p" in asset_ids, "MiniMax H3 LightX v1.1 speed LoRA is missing")
    seedvr2_asset_ids = {"seedvr2_3b_int8", "seedvr2_vae_fp16"}
    seedvr2_7b_asset_ids = {"seedvr2_7b_nvfp4", "seedvr2_7b_sharp_nvfp4", "seedvr2_vae_fp16"}
    check(seedvr2_7b_asset_ids <= asset_ids, "SeedVR2 7B NVFP4 manifest is incomplete")
    catalog_node_ids = {item["id"] for item in catalog.CUSTOM_NODE_REPOS}
    check({item["id"] for item in nodes} == catalog_node_ids, "custom node manifest mismatch")
    check(installer.MODEL_FILES is catalog.MODEL_ASSETS, "installer should use the canonical model asset registry")
    check(installer.CUSTOM_NODE_REPOS is catalog.CUSTOM_NODE_REPOS, "installer should use the canonical custom node registry")
    for profile_id, profile in catalog.INSTALL_PROFILES.items():
        check(set(profile.get("asset_ids", [])) <= installer_ids, f"{profile_id} references an unknown asset")
        check(set(profile.get("custom_node_ids", [])) <= catalog_node_ids, f"{profile_id} references an unknown custom node")
    plan = frontend.install_plan_payload(
        profile="cuda-full",
        assets=frontend.collect_asset_checks(frontend.BASE_DIR),
        custom_nodes=frontend.collect_custom_node_checks(frontend.BASE_DIR),
        missing=[],
    )
    planned_asset_ids = {item["id"] for item in plan["items"] if item["item_type"] == "asset"}
    check(
        planned_asset_ids == set(catalog.INSTALL_PROFILES["cuda-full"]["asset_ids"]),
        "cuda-full plan does not match the canonical profile",
    )
    check(plan["custom_node_count"] == 2, "cuda-full should include two custom nodes")
    check("disk" in plan and "ok" in plan["disk"], "install plan missing disk preflight")
    exact_missing = frontend.installable_missing_items(
        [
            {
                "id": "exact_progress",
                "label": "Exact progress",
                "installable": True,
                "ok": False,
                "expected_bytes": 6_938_041_288,
                "downloaded_bytes": 4_445_962_240,
                "expected_gb": 6.46,
                "partial_gb": 4.14,
            }
        ],
        [],
    )
    exact_progress = frontend.initialize_install_progress(exact_missing)
    check(
        exact_progress["total_bytes"] == 6_938_041_288
        and exact_progress["downloaded_bytes"] == 4_445_962_240,
        "install progress should preserve exact manifest and .part byte counts from the first response",
    )
    wan5b_items = {item["id"] for item in installer.selected_model_items("cuda-wan5b")}
    check({"ti2v_5b", "umt5", "wan22_vae", "rife49", "realesrgan_x2"} <= wan5b_items, "cuda-wan5b profile missing required assets")
    check("i2v_high" not in wan5b_items and "t2v_high" not in wan5b_items, "cuda-wan5b profile should not download A14B full assets")
    check("cuda-wan5b" in frontend.INSTALL_PROFILE_ASSETS, "frontend missing cuda-wan5b install profile")
    a14b_items = {item["id"] for item in installer.selected_model_items("cuda-a14b")}
    a14b_core = {item["id"] for item in installer.selected_model_items("cuda-a14b", skip_post=True)}
    check(
        "ti2v_5b" not in a14b_items and "i2v_high" in a14b_items and "t2v_high" in a14b_items and "rife49" in a14b_items,
        "cuda-a14b should install A14B I2V/T2V without the 5B warehouse",
    )
    check("rife49" not in a14b_core and "i2v_high" in a14b_core, "skip_post should drop RIFE/upscale from the A14B core pack")
    h3_items = {item["id"] for item in installer.selected_model_items("minimax-h3-fl2va-int8")}
    check(
        h3_asset_ids <= h3_items
        and "minimax_h3_lightx4_v11_768p" in h3_items
        and "minimax_h3_spectrum"
        in set(catalog.INSTALL_PROFILES["minimax-h3-fl2va-int8"].get("custom_node_ids") or [])
        and catalog.INSTALL_PROFILES["minimax-h3-fl2va-int8"].get("required_comfy_version") == "0.31.0",
        "MiniMax H3 install profile must contain the four base models, speed add-ons, and ComfyUI floor",
    )
    seedvr2_items = {item["id"] for item in installer.selected_model_items("seedvr2-upscale")}
    check(
        seedvr2_asset_ids == seedvr2_items
        and catalog.INSTALL_PROFILES["seedvr2-upscale"].get("required_comfy_version") == "0.30.1",
        "SeedVR2 install profile must contain only the native 3B INT8 model and VAE",
    )
    check(
        {"seedvr2_7b_nvfp4", "seedvr2_vae_fp16"}
        == {item["id"] for item in installer.selected_model_items("seedvr2-upscale-7b")}
        and {"seedvr2_7b_sharp_nvfp4", "seedvr2_vae_fp16"}
        == {item["id"] for item in installer.selected_model_items("seedvr2-upscale-7b-sharp")},
        "SeedVR2 7B install profiles must keep the normal and Sharp checkpoints separate",
    )
    check(
        {
            "ltx23_fp8_distilled",
            "ltx23_gemma3_fp4",
            "ltx23_spatial_upscaler",
            "ltx23_distilled_lora",
            "rife49",
            "realesrgan_x2",
        }
        <= {item["id"] for item in installer.selected_model_items("ltx23-fp8-distilled")},
        "LTX 2.3 distilled profile is incomplete",
    )
    check(
        not catalog.INSTALL_PROFILES["ltx23-fp8-distilled"].get("external_requirement"),
        "LTX 2.3 should use the direct Comfy-Org Gemma repack instead of a stale gated requirement",
    )
    qwen_items = {item["id"] for item in installer.selected_model_items("qwen-image-2512-fp8")}
    check(
        {
            "qwen_image_2512_fp8",
            "qwen_image_text_encoder_fp8",
            "qwen_image_vae",
            "qwen_image_lightning_lora",
        }
        == qwen_items,
        "Qwen-Image-2512 install profile should contain only the four image assets",
    )
    image_profile_assets = {
        "qwen-image-edit-2511-fp8": {
            "qwen_image_edit_2511_fp8mixed",
            "qwen_image_text_encoder_fp8",
            "qwen_image_vae",
            "qwen_image_edit_2511_lightning_lora",
        },
        "hidream-i1-fast-fp8": {
            "hidream_i1_fast_fp8",
            "hidream_i1_clip_l",
            "hidream_i1_clip_g",
            "chroma_t5xxl_fp8",
            "hidream_i1_llama_fp8",
            "z_image_vae",
        },
        "hidream-i1-dev-fp8": {
            "hidream_i1_dev_fp8",
            "hidream_i1_clip_l",
            "hidream_i1_clip_g",
            "chroma_t5xxl_fp8",
            "hidream_i1_llama_fp8",
            "z_image_vae",
        },
        "hidream-i1-full-fp8": {
            "hidream_i1_full_fp8",
            "hidream_i1_clip_l",
            "hidream_i1_clip_g",
            "chroma_t5xxl_fp8",
            "hidream_i1_llama_fp8",
            "z_image_vae",
        },
        "hidream-o1-dev2604-fp8": {"hidream_o1_dev2604_fp8", "hidream_gemma4_prompt_fp8"},
        "hidream-o1-full-fp8": {"hidream_o1_full_fp8", "hidream_gemma4_prompt_fp8"},
        "flux2-dev-fp8": {"flux2_dev_fp8", "flux2_text_encoder_fp8", "flux2_vae"},
        "flux2-dev-nvfp4": {"flux2_dev_nvfp4", "flux2_text_encoder_fp4", "flux2_vae"},
        "flux2-klein-4b-fp8": {"flux2_klein_4b_fp8", "flux2_klein_qwen3_4b_fp4", "flux2_vae"},
        "flux2-klein-base-4b-fp8": {"flux2_klein_base_4b_fp8", "flux2_klein_qwen3_4b", "flux2_vae"},
        "chroma1-hd-bf16": {"chroma1_hd_bf16", "chroma_t5xxl_fp8", "z_image_vae"},
        "noobai-xl-11": {"noobai_xl_11"},
        "illustrious-xl-v20": {"illustrious_xl_v20"},
        "wai-nsfw-illustrious-v90": {"wai_nsfw_illustrious_v90"},
        "cyberrealistic-pony-v18": {"cyberrealistic_pony_v18"},
        "lustify-sdxl-v40": {"lustify_sdxl_v40"},
        "z-image-base-bf16": {"z_image_base_bf16", "z_image_text_encoder_fp8", "z_image_vae"},
        "z-image-turbo-nvfp4": {"z_image_turbo_nvfp4", "z_image_text_encoder_fp4", "z_image_vae"},
        "ernie-image-standard": {"ernie_image_standard", "ernie_ministral_text_encoder", "ernie_prompt_enhancer", "flux2_vae"},
        "ernie-image-turbo": {"ernie_image_turbo", "ernie_ministral_text_encoder", "ernie_prompt_enhancer", "flux2_vae"},
    }
    for profile_id, expected_ids in image_profile_assets.items():
        check(
            {item["id"] for item in installer.selected_model_items(profile_id)} == expected_ids,
            f"{profile_id} image install profile is incomplete",
        )
    hunyuan_profile_assets = {
        "hunyuan15-t2v-480-fp8": {"hunyuan15_t2v_480_fp8_distilled"},
        "hunyuan15-i2v-480-fp8": {"hunyuan15_i2v_480_fp8_distilled", "hunyuan15_sigclip"},
        "hunyuan15-t2v-720-fp16": {"hunyuan15_t2v_720_fp16"},
        "hunyuan15-i2v-720-fp16": {"hunyuan15_i2v_720_fp16", "hunyuan15_sigclip"},
    }
    for profile_id, model_ids in hunyuan_profile_assets.items():
        selected_ids = {item["id"] for item in installer.selected_model_items(profile_id)}
        check(
            model_ids <= selected_ids
            and {"qwen_image_text_encoder_fp8", "hunyuan15_byt5", "hunyuan15_vae"} <= selected_ids,
            f"{profile_id} HunyuanVideo 1.5 install profile is incomplete",
        )
    check(
        {item["id"] for item in installer.selected_model_items("qwen-image-2512-nsfw-addon")} == {"qwen_image_nsfw_lora"}
        and {item["id"] for item in installer.selected_model_items("z-image-nsfw-addon")} == {"z_image_nsfw_lora"}
        and {item["id"] for item in installer.selected_model_items("wan22-i2v-unrestricted-addon")}
        == {"wan22_i2v_nsfw_high", "wan22_i2v_nsfw_low"}
        and {item["id"] for item in installer.selected_model_items("flux2-uncensored-te-addon")}
        == {"flux2_uncensored_te_fp8"}
        and {item["id"] for item in installer.selected_model_items("flux2-klein-uncensored-te-addon")}
        == {"flux2_klein_uncensored_te_nvfp4", "flux2_klein_uncensored_te_fp8"},
        "community adult add-ons must remain separate from base model profiles",
    )
    payload = catalog.model_catalog_payload()
    check(len(payload["items"]) >= 37, "model catalog is unexpectedly small")
    fal_h3_max = next(item for item in payload["items"] if item["id"] == "fal_h3_max_api")
    check(
        fal_h3_max["generation_target"] == "cloud_api"
        and fal_h3_max["can_generate_here"]
        and not fal_h3_max["one_click_install"]
        and not fal_h3_max["files"],
        "fal H3 Max must remain an API-only route with no fake local checkpoint download",
    )
    check(
        frontend.video_params.mode_capabilities("fal_h3_max_t2v")["smoke_test"] is False
        and frontend.video_params.mode_capabilities("fal_h3_max_i2v")["image_input"] == "required"
        and catalog.INSTALL_PROFILES["fal-h3-max-api"]["installable"] is False,
        "fal H3 Max capabilities and non-installable API profile are inconsistent",
    )
    ltx23_dev = next(item for item in payload["items"] if item["id"] == "ltx_23_22b_fp8_dev")
    qwen_image = next(item for item in payload["items"] if item["id"] == "qwen_image_2512_fp8")
    bernini = next(item for item in payload["items"] if item["id"] == "bernini_r_fp8")
    chroma = next(item for item in payload["items"] if item["id"] == "chroma1_hd_bf16")
    noobai = next(item for item in payload["items"] if item["id"] == "noobai_xl_11")
    wai_illustrious = next(item for item in payload["items"] if item["id"] == "wai_nsfw_illustrious_v90")
    cyberrealistic = next(item for item in payload["items"] if item["id"] == "cyberrealistic_pony_v18")
    qwen_edit_2511 = next(item for item in payload["items"] if item["id"] == "qwen_image_edit_2511_fp8mixed")
    hidream_i1 = next(item for item in payload["items"] if item["id"] == "hidream_i1_dev_fp8")
    hunyuan15 = next(item for item in payload["items"] if item["id"] == "hunyuan15_i2v_480_fp8_distilled")
    minimax_h3 = next(item for item in payload["items"] if item["id"] == "minimax_h3_fl2va_pruned_int8")
    ltx25_int8 = next(item for item in payload["items"] if item["id"] == "ltx_25_22b_distilled_int8")
    ltx25_nvfp4 = next(item for item in payload["items"] if item["id"] == "ltx_25_22b_distilled_nvfp4")
    check(
        qwen_image.get("platform_support") == "native"
        and qwen_image.get("one_click_install") is True
        and qwen_image.get("workflow_modes") == {"image": "qwen_image_2512"},
        "Qwen-Image-2512 should be a native one-click image model",
    )
    check(
        bernini.get("platform_support") == "official_workflow"
        and bernini.get("one_click_install") is True
        and bernini.get("install_asset_count", 0) >= 5
        and bernini.get("install_expected_bytes", 0) > 0
        and bernini.get("released") == "2026-06",
        "Bernini-R should expose a sized one-click official ComfyUI workflow",
    )
    check(
        frontend.install_profile_for_asset("cyberrealistic_pony_v18") == "cyberrealistic-pony-v18",
        "a managed partial model should resolve to its smallest installable resume profile",
    )
    check(
        chroma.get("platform_support") == "native"
        and chroma.get("one_click_install") is True
        and chroma.get("nsfw", {}).get("status") == "native_unaligned"
        and noobai.get("platform_support") == "native"
        and noobai.get("nsfw", {}).get("status") == "native_unaligned",
        "Chroma and NoobAI should remain native installable unaligned image profiles",
    )
    check(
        wai_illustrious.get("platform_support") == "native"
        and wai_illustrious.get("one_click_install") is True
        and cyberrealistic.get("released") == "2026-05"
        and cyberrealistic.get("one_click_install") is True,
        "new Illustrious and Pony community profiles should be native one-click SDXL workflows",
    )
    check(
        ltx23_dev.get("platform_support") == "native"
        and ltx23_dev.get("workflow_modes") == {"draft": "ltx23_t2v", "final": "ltx23_t2v"},
        "LTX 2.3 Dev FP8 should stay wired to the native draft/final workflow",
    )
    check(
        qwen_edit_2511.get("platform_support") == "native"
        and qwen_edit_2511.get("workflow_modes") == {"image": "qwen_image_edit_2511"}
        and hidream_i1.get("platform_support") == "native"
        and hidream_i1.get("released") == "2025-04",
        "Qwen Edit 2511 and HiDream-I1 should be native image choices",
    )
    check(
        hunyuan15.get("platform_support") == "native"
        and hunyuan15.get("one_click_install") is True
        and hunyuan15.get("workflow_modes") == {"draft": "hunyuan15_i2v", "final": "hunyuan15_i2v"},
        "HunyuanVideo 1.5 should expose a native one-click I2V workflow",
    )
    check(
        minimax_h3.get("platform_support") == "native"
        and minimax_h3.get("one_click_install") is True
        and minimax_h3.get("workflow_modes") == {"draft": "minimax_h3_t2v", "final": "minimax_h3_i2v"}
        and set(minimax_h3.get("files") or [])
        == {
            "minimax_h3_fl2va_pruned_int8_convrot.safetensors",
            "qwen3vl_32b_minimax_h3_int8_convrot.safetensors",
            "minimax_h3_video_vae_fp16.safetensors",
            "minimax_h3_audio_vae_fp32.safetensors",
        },
        "MiniMax H3 should expose the exact native T2V/I2V four-file route",
    )
    check(
        minimax_h3.get("nsfw", {}).get("status") == "prompt_passthrough"
        and ltx25_int8.get("nsfw", {}).get("status") == "prompt_passthrough"
        and ltx25_nvfp4.get("nsfw", {}).get("status") == "prompt_passthrough",
        "H3 and LTX 2.5 should expose prompt-passthrough unrestricted mode without Wan LoRAs",
    )
    check(
        ltx25_int8.get("platform_support") == "native"
        and ltx25_int8.get("one_click_install") is True
        and ltx25_int8.get("workflow_modes") == {"draft": "ltx25_t2v", "final": "ltx25_i2v"}
        and ltx25_nvfp4.get("default_install_profile") == "ltx25-distilled-nvfp4"
        and "ltx-2.5-video-vae-bf16.safetensors" in set(ltx25_int8.get("files") or [])
        and "ltx-2.5-audio-vae-bf16.safetensors" in set(ltx25_int8.get("files") or []),
        "LTX 2.5 should expose native INT8/NVFP4 T2V-I2V routes with split video/audio assets",
    )
    ltx23_distilled = next(item for item in payload["items"] if item["id"] == "ltx_23_22b_fp8_distilled")
    ltx23_gguf = next(item for item in payload["items"] if item["id"] == "ltx_23_22b_gguf_q4")
    wan_a14b = next(item for item in payload["items"] if item["id"] == "wan22_a14b_fp8")
    check(
        minimax_h3.get("generation_target") == "native"
        and qwen_image.get("generation_target") == "native"
        and ltx23_distilled.get("generation_target") == "comfy_template"
        and bernini.get("generation_target") == "comfy_template"
        and ltx23_gguf.get("generation_target") == "catalog_only"
        and wan_a14b.get("default_install_profile") == "cuda-a14b"
        and wan_a14b.get("workflow_modes") == {"draft": "t2v_a14b", "final": "i2v_a14b"}
        and wan_a14b.get("can_generate_here") is True
        and ltx23_distilled.get("can_generate_here") is False
        and ltx23_distilled.get("one_click_install") is True,
        "catalog cards must distinguish generate-here, Comfy-template, and catalog-only without faking one-click generate",
    )
    core_plan = frontend.install_plan_payload(
        profile="cuda-full",
        assets=frontend.collect_asset_checks(frontend.BASE_DIR),
        custom_nodes=frontend.collect_custom_node_checks(frontend.BASE_DIR),
        missing=[],
        include_post=False,
    )
    core_asset_ids = {item["id"] for item in core_plan["items"] if item["item_type"] == "asset"}
    check(
        "rife49" not in core_asset_ids and "ti2v_5b" in core_asset_ids and core_plan.get("include_post") is False,
        "include_post=false should drop the RIFE/upscale warehouse from an install plan",
    )
    check(
        {item["id"] for item in installer.selected_model_items("ltx25-distilled-int8")}
        >= {
            "ltx25_distilled_int8",
            "ltx25_text_int8",
            "ltx25_video_vae_diff",
            "ltx25_video_vae_conv",
            "ltx25_audio_vae",
            "ltx25_spatial_upscaler",
            "ltx25_duration_head",
        },
        "LTX 2.5 INT8 install profile should include every native workflow component",
    )
    with patch("beginner_frontend.app.saved_model_catalog_id", return_value="ltx_23_22b_fp8_dev"):
        selected_catalog = frontend.model_catalog_payload_with_selection()["selected_model"]
    check(
        selected_catalog.get("install_profile_label") == "LTX 2.3 Dev FP8"
        and selected_catalog.get("one_click_install") is True,
        "selected model summary should use the same enriched catalog item as the model list",
    )
    with tempfile.TemporaryDirectory(prefix="model_sync_catalog_") as temp_name:
        sync = frontend.catalog_model_sync(
            base_dir=Path(temp_name),
            assets=[{"name": name, "ok": True, "path": name} for name in ltx23_dev.get("files", [])],
            selected_model_id="ltx_23_22b_fp8_dev",
        )
    check(
        sync["selected_model"].get("install_profile_label") == "LTX 2.3 Dev FP8"
        and sync["selected_model"].get("one_click_install") is True,
        "environment model-sync summary should preserve enriched install metadata",
    )
    check({"international", "china", "custom"} == {item["id"] for item in payload["source_presets"]}, "download source presets mismatch")
    check(
        frontend.install_profile_for_hardware({"platform_strategy": "cuda_multi_model", "max_vram_gb": 96}) == "minimax-h3-fl2va-int8",
        "80GB+ CUDA should default to the native audio/video high-memory route",
    )
    check(
        frontend.install_profile_for_hardware({"platform_strategy": "cuda_multi_model", "max_vram_gb": 48}) == "ltx25-distilled-int8",
        "48GB CUDA should default to the LTX 2.5 balanced route",
    )
    check(
        frontend.install_profile_for_hardware({"platform_strategy": "post_only", "max_vram_gb": 0}) == "post-only",
        "non-accelerated systems should default to post-only",
    )
    check(
        frontend.version_at_least("0.32.0", "0.32.0")
        and frontend.version_at_least("0.33.1", "0.32.0")
        and not frontend.version_at_least("0.31.9", "0.32.0"),
        "ComfyUI minimum-version checks should reject pre-LTX-2.5 runtimes",
    )
    disk_plan = installer.disk_space_plan(ROOT, 0)
    check(disk_plan["ok"] is True, "zero-byte disk plan should be ok")
    return {"installer_assets": len(installer_ids), "frontend_assets": len(asset_ids), "custom_nodes": len(nodes), "catalog_models": len(payload["items"])}


def workflow_check() -> dict[str, int]:
    sys.path.insert(0, str(ROOT))
    from beginner_frontend import app as frontend

    graphs = [
        frontend.build_ti2v_prompt(
            prompt="test",
            negative="bad",
            image_name=frontend.KEYFRAME_UPLOAD_PLACEHOLDER,
            width=1280,
            height=704,
            length=81,
            fps=24,
            seed=1,
            steps=20,
            cfg=5.0,
        ),
        frontend.build_ltx_i2v_prompt(
            prompt="test",
            negative="bad",
            image_name=frontend.KEYFRAME_UPLOAD_PLACEHOLDER,
            width=512,
            height=320,
            length=25,
            fps=24,
            seed=1,
            steps=12,
            cfg=3.0,
        ),
        frontend.build_ltx23_t2v_prompt(
            prompt="test",
            negative="bad",
            width=512,
            height=320,
            length=25,
            fps=25,
            seed=1,
            steps=11,
            cfg=1.0,
        ),
        frontend.build_ltx23_i2v_prompt(
            prompt="test",
            negative="bad",
            image_name=frontend.KEYFRAME_UPLOAD_PLACEHOLDER,
            width=512,
            height=320,
            length=25,
            fps=25,
            seed=1,
            steps=11,
            cfg=1.0,
        ),
        frontend.build_rife_prompt(video_name="sample.mp4", fps=24, multiplier=2),
        frontend.build_video_upscale_prompt(video_name="sample.mp4", fps=24),
        frontend.build_qwen_image_prompt(
            prompt="上海雨夜，霓虹灯下的书店",
            negative="模糊",
            width=1328,
            height=1328,
            seed=1,
            profile_id="qwen2512_lightning_fp8",
            steps=4,
            cfg=1.0,
            batch_size=2,
        ),
    ]
    ti2v_text_graph = frontend.build_ti2v_prompt(
        prompt="test",
        negative="bad",
        image_name="",
        width=832,
        height=480,
        length=49,
        fps=24,
        seed=1,
        steps=18,
        cfg=5.0,
    )
    graphs.append(ti2v_text_graph)
    h3_t2v_graph = frontend.build_minimax_h3_prompt(
        prompt="A quiet room, distant piano and rain",
        negative="ignored",
        image_name="",
        width=864,
        height=480,
        length=73,
        fps=30,
        seed=1,
        steps=20,
        cfg=7.0,
    )
    h3_i2v_graph = frontend.build_minimax_h3_prompt(
        prompt="A person turns toward camera and says hello",
        negative="ignored",
        image_name=frontend.KEYFRAME_UPLOAD_PLACEHOLDER,
        end_image_name=frontend.KEYFRAME_UPLOAD_PLACEHOLDER,
        width=864,
        height=480,
        length=81,
        fps=30,
        seed=2,
        steps=20,
        cfg=7.0,
    )
    seedvr2_graph = frontend.build_seedvr2_upscale_prompt(video_name="sample.mp4", fps=24, seed=3)
    seedvr2_7b_graph = frontend.build_seedvr2_upscale_prompt(
        video_name="sample.mp4",
        fps=24,
        seed=3,
        model_name=frontend.SEEDVR2_7B_MODEL,
        scale=1.5,
    )
    h3_1080_graph = frontend.build_minimax_h3_prompt(
        prompt="A static studio product shot",
        negative="ignored",
        image_name="",
        width=1920,
        height=1088,
        length=22,
        fps=24,
        seed=3,
        steps=8,
        cfg=1.0,
    )
    h3_spectrum_graph = frontend.build_minimax_h3_prompt(
        prompt="A quiet room",
        negative="ignored",
        image_name="",
        width=864,
        height=480,
        length=73,
        fps=24,
        seed=4,
        steps=8,
        cfg=1.0,
        adv=frontend.video_params.resolve(
            "minimax_h3_t2v",
            {"h3_acceleration_profile": "spectrum_balanced"},
        ),
    )
    h3_turbo_graph = frontend.build_minimax_h3_prompt(
        prompt="A quiet room",
        negative="ignored",
        image_name="",
        width=1344,
        height=768,
        length=73,
        fps=24,
        seed=5,
        steps=20,
        cfg=1.0,
        adv=frontend.video_params.resolve(
            "minimax_h3_t2v",
            {
                "h3_acceleration_profile": "lightx4_v11_768p",
                "h3_prompt_format": "official_three_part",
                "h3_tiled_decode": True,
            },
        ),
    )
    graphs.extend(
        [
            h3_t2v_graph,
            h3_i2v_graph,
            seedvr2_graph,
            h3_1080_graph,
            h3_spectrum_graph,
            h3_turbo_graph,
        ]
    )
    ltx25_t2v_graph = frontend.build_ltx25_t2v_prompt(
        prompt="A cinematic room tone with synchronized footsteps",
        negative="bad",
        width=1280,
        height=704,
        length=121,
        fps=24,
        seed=4,
        steps=11,
        cfg=1.0,
    )
    ltx25_i2v_graph = frontend.build_ltx25_i2v_prompt(
        prompt="The subject turns toward camera",
        negative="bad",
        image_name=frontend.KEYFRAME_UPLOAD_PLACEHOLDER,
        width=1280,
        height=704,
        length=121,
        fps=24,
        seed=5,
        steps=11,
        cfg=1.0,
    )
    ltx25_flf_graph = frontend.build_ltx25_i2v_prompt(
        prompt="The subject crosses the room between two matching frames",
        negative="bad",
        image_name=frontend.KEYFRAME_UPLOAD_PLACEHOLDER,
        end_image_name=frontend.KEYFRAME_UPLOAD_PLACEHOLDER,
        width=704,
        height=1280,
        length=121,
        fps=24,
        seed=6,
        steps=8,
        cfg=1.0,
    )
    graphs.extend([ltx25_t2v_graph, ltx25_i2v_graph, ltx25_flf_graph])
    for graph in graphs:
        check(not frontend.validate_graph(graph), "workflow graph validation failed")
        check("%date:" not in json.dumps(graph), "workflow graph still contains date template")
    ltx23_graph = graphs[2]
    ltx23_i2v_graph = graphs[3]
    check(
        {"LTXAVTextEncoderLoader", "LTXVAudioVAELoader", "LTXVLatentUpsampler", "SaveVideo"}
        <= set(frontend.graph_class_types(ltx23_graph)),
        "LTX 2.3 native graph is missing its audio/two-stage nodes",
    )
    check(
        {"LoadImage", "LTXVPreprocess", "LTXVImgToVideoInplace"}
        <= set(frontend.graph_class_types(ltx23_i2v_graph))
        and sum(item["class_type"] == "LTXVImgToVideoInplace" for item in ltx23_i2v_graph.values()) == 2,
        "LTX 2.3 I2V should apply the uploaded frame before and after latent upscaling",
    )
    adjusted_ltx23_graph = frontend.build_ltx23_t2v_prompt(
        prompt="test",
        negative="bad",
        width=512,
        height=320,
        length=25,
        fps=25,
        seed=1,
        steps=17,
        cfg=1.0,
    )
    check(
        adjusted_ltx23_graph["13"]["inputs"]["sigmas"] != ltx23_graph["13"]["inputs"]["sigmas"]
        and adjusted_ltx23_graph["23"]["inputs"]["sigmas"] != ltx23_graph["23"]["inputs"]["sigmas"],
        "LTX 2.3 sampling steps should change both sigma stages",
    )
    check(
        ltx23_graph["12"]["inputs"]["sampler_name"] == "euler_ancestral_cfg_pp"
        and ltx23_graph["22"]["inputs"]["sampler_name"] == "euler_cfg_pp",
        "LTX 2.3 should track the current official two-stage samplers",
    )
    ltx23_nvfp4_graph = frontend.build_ltx23_t2v_prompt(
        prompt="test",
        negative="bad",
        width=512,
        height=320,
        length=25,
        fps=25,
        seed=1,
        steps=11,
        cfg=1.0,
        checkpoint_name=frontend.LTX23_NVFP4_CHECKPOINT,
    )
    check(
        ltx23_nvfp4_graph["1"]["inputs"]["ckpt_name"] == frontend.LTX23_NVFP4_CHECKPOINT
        and ltx23_nvfp4_graph["2"]["inputs"]["ckpt_name"] == frontend.LTX23_NVFP4_CHECKPOINT,
        "LTX 2.3 NVFP4 should use its selected checkpoint throughout the native graph",
    )
    check(
        {
            "UNETLoader",
            "CLIPLoader",
            "LTXVDualCFGGuider",
            "LTXVLatentUpsampler",
            "LTXVAudioVAEDecode",
            "SaveVideo",
        }
        <= set(frontend.graph_class_types(ltx25_t2v_graph))
        and ltx25_t2v_graph["1"]["inputs"]["unet_name"] == frontend.LTX25_DISTILLED_INT8_MODEL
        and ltx25_t2v_graph["12"]["inputs"]["sampler_name"] == "euler_ancestral",
        "LTX 2.5 T2V should follow the native split-model two-stage audio workflow",
    )
    check(
        sum(item["class_type"] == "LTXVImgToVideoInplace" for item in ltx25_i2v_graph.values()) == 2
        and {"LTXVAddGuide", "SamplerEulerAncestral", "LTXVCropGuides"}
        <= set(frontend.graph_class_types(ltx25_flf_graph))
        and "LTXVLatentUpsampler" not in frontend.graph_class_types(ltx25_flf_graph),
        "LTX 2.5 should use two-stage I2V and the official single-stage first/last-frame guide path",
    )
    hunyuan_t2v_graph = frontend.build_hunyuan15_prompt(
        prompt="test",
        negative="bad",
        image_name="",
        width=832,
        height=480,
        length=49,
        fps=24,
        seed=1,
        steps=8,
        cfg=6.0,
        model_name=frontend.HUNYUAN15_T2V_480_MODEL,
        distilled=True,
    )
    hunyuan_i2v_graph = frontend.build_hunyuan15_prompt(
        prompt="test",
        negative="bad",
        image_name=frontend.KEYFRAME_UPLOAD_PLACEHOLDER,
        width=1280,
        height=704,
        length=49,
        fps=24,
        seed=1,
        steps=20,
        cfg=6.0,
        model_name=frontend.HUNYUAN15_I2V_720_MODEL,
        distilled=False,
    )
    check(
        not frontend.validate_graph(hunyuan_t2v_graph)
        and {"DualCLIPLoader", "EmptyHunyuanVideo15Latent", "SamplerCustomAdvanced", "SaveVideo"}
        <= set(frontend.graph_class_types(hunyuan_t2v_graph))
        and hunyuan_t2v_graph["11"]["inputs"]["cfg"] == 1.0,
        "HunyuanVideo 1.5 distilled T2V should use its native graph and fixed CFG=1",
    )
    check(
        not frontend.validate_graph(hunyuan_i2v_graph)
        and {"CLIPVisionLoader", "CLIPVisionEncode", "HunyuanVideo15ImageToVideo"}
        <= set(frontend.graph_class_types(hunyuan_i2v_graph))
        and hunyuan_i2v_graph["11"]["inputs"]["cfg"] == 6.0,
        "HunyuanVideo 1.5 I2V should apply the keyframe through native vision conditioning",
    )
    check(
        {
            "MiniMaxH3ImageToVideo",
            "MiniMaxH3SigmaShift",
            "BasicGuider",
            "VAEDecodeAudio",
            "CreateVideo",
            "SaveVideo",
        }
        <= set(frontend.graph_class_types(h3_t2v_graph))
        and h3_t2v_graph["1"]["inputs"]["unet_name"] == frontend.MINIMAX_H3_FL2VA_MODEL
        and h3_t2v_graph["2"]["inputs"]["clip_name"] == frontend.MINIMAX_H3_TEXT_ENCODER
        and h3_t2v_graph["12"]["inputs"]["fps"] == 24.0,
        "MiniMax H3 T2V should use the exact INT8 models and native audio-video graph",
    )
    check(
        h3_i2v_graph["5"]["inputs"]["length"] == 90
        and h3_i2v_graph["5"]["inputs"]["first_frame"] == ["20", 0]
        and h3_i2v_graph["5"]["inputs"]["last_frame"] == ["21", 0]
        and (h3_i2v_graph["5"]["inputs"]["length"] - 5) % 17 == 0,
        "MiniMax H3 I2V should preserve first/last frames and snap to the 17k+5 frame grid",
    )
    check(
        h3_spectrum_graph["31"]["class_type"] == "SpectrumApplyMiniMaxH3"
        and h3_spectrum_graph["8"]["inputs"]["steps"] == 20
        and h3_spectrum_graph["8"]["inputs"]["model"] == ["31", 0]
        and h3_spectrum_graph["31"]["inputs"]["history_storage"] == "system_ram"
        and h3_spectrum_graph["31"]["inputs"]["audio_blend_weight"] == 0.0,
        "MiniMax H3 Spectrum profile should retain the 20-step path and system-RAM safety defaults",
    )
    check(
        h3_turbo_graph["30"]["class_type"] == "LoraLoaderModelOnly"
        and h3_turbo_graph["30"]["inputs"]["lora_name"] == frontend.MINIMAX_H3_LIGHTX4_V11_LORA
        and h3_turbo_graph["4"]["inputs"]["shift_video"] == 6.0
        and h3_turbo_graph["7"]["inputs"]["sampler_name"] == "euler"
        and h3_turbo_graph["8"]["inputs"]["steps"] == 4
        and h3_turbo_graph["11"]["class_type"] == "VAEDecodeTiled"
        and h3_turbo_graph["5"]["inputs"]["prompt"].startswith("integrated_multimodal_description:"),
        "MiniMax H3 LightX profile should apply the v1.1 LoRA and its exact four-step 768P settings",
    )
    check(
        {
            "SeedVR2Preprocess",
            "SeedVR2TemporalChunk",
            "SeedVR2Conditioning",
            "SeedVR2TemporalMerge",
            "SeedVR2PostProcessing",
        }
        <= set(frontend.graph_class_types(seedvr2_graph))
        and seedvr2_graph["13"]["inputs"].get("audio") == ["1", 2]
        and seedvr2_graph["9"]["inputs"]["steps"] == 1,
        "SeedVR2 graph should use the native one-step temporal restoration path and preserve audio",
    )
    check(
        seedvr2_7b_graph["6"]["inputs"]["unet_name"] == frontend.SEEDVR2_7B_MODEL
        and seedvr2_7b_graph["2"]["inputs"]["scale_by"] == 1.5,
        "SeedVR2 7B graph should preserve the selected checkpoint and 720P-to-1080P scale",
    )
    check(
        h3_1080_graph["5"]["inputs"]["width"] == 1920
        and h3_1080_graph["5"]["inputs"]["height"] == 1088
        and h3_1080_graph["16"]["class_type"] == "ImageCrop"
        and h3_1080_graph["16"]["inputs"]["height"] == 1080,
        "MiniMax H3 1080P preset should generate at an aligned size and crop to standard 1920x1080",
    )
    check(
        graphs[4]["3"]["inputs"].get("audio") == ["1", 2]
        and graphs[5]["4"]["inputs"].get("audio") == ["1", 2],
        "RIFE and upscale workflows should preserve the source audio track",
    )
    check(graphs[4]["2"]["inputs"]["dtype"] == "float32", "RIFE should default to the portable float32 dtype")
    qwen_graph = graphs[6]
    check(
        {"UNETLoader", "CLIPLoader", "ModelSamplingAuraFlow", "EmptySD3LatentImage", "SaveImage"}
        <= set(frontend.graph_class_types(qwen_graph)),
        "Qwen image graph is missing native ComfyUI nodes",
    )
    check(
        next(item for item in qwen_graph.values() if item["class_type"] == "EmptySD3LatentImage")["inputs"]["batch_size"] == 2
        and next(item for item in qwen_graph.values() if item["class_type"] == "KSampler")["inputs"]["steps"] == 4
        and next(item for item in qwen_graph.values() if item["class_type"] == "KSampler")["inputs"]["cfg"] == 1.0,
        "Qwen Lightning graph should preserve batch size and fixed 4-step settings",
    )
    image_graphs: dict[str, dict[str, object]] = {}
    for profile in frontend.IMAGE_PROFILES:
        image_graph = frontend.build_image_prompt(
            prompt="中文产品海报",
            negative="模糊",
            width=1024,
            height=1024,
            seed=7,
            profile_id=profile["id"],
            steps=profile["default_steps"],
            cfg=profile["default_cfg"],
            sampler=profile["default_sampler"],
            scheduler=profile["default_scheduler"],
            batch_size=1,
            source_image="beginner_frontend/edit-source.png"
            if profile.get("generation_supported") is False
            else "",
        )
        image_graphs[profile["id"]] = image_graph
        check(not frontend.validate_graph(image_graph), f"{profile['id']} image graph validation failed")
        check("SaveImage" in frontend.graph_class_types(image_graph), f"{profile['id']} image graph has no SaveImage output")
    check(
        {"T5TokenizerOptions", "BetaSamplingScheduler", "SamplerCustomAdvanced"}
        <= set(frontend.graph_class_types(image_graphs["chroma1_hd_bf16"])),
        "Chroma should use its native T5 and beta-scheduler graph",
    )
    check(
        {"QuadrupleCLIPLoader", "ModelSamplingSD3", "EmptySD3LatentImage"}
        <= set(frontend.graph_class_types(image_graphs["hidream_i1_dev_fp8"]))
        and image_graphs["hidream_i1_dev_fp8"]["4"]["inputs"]["shift"] == 6.0,
        "HiDream-I1 Dev should use four text encoders and the official shift",
    )
    check(
        {"TextEncodeQwenImageEditPlus", "FluxKontextImageScale", "CFGNorm", "VAEEncode"}
        <= set(frontend.graph_class_types(image_graphs["qwen_edit_2511_quality_fp8"]))
        and "EmptySD3LatentImage" not in frontend.graph_class_types(image_graphs["qwen_edit_2511_quality_fp8"]),
        "Qwen-Image-Edit-2511 should remain an edit-only native graph",
    )
    check(
        "ConditioningZeroOut" in frontend.graph_class_types(image_graphs["flux2_klein_4b_fp8"])
        and next(item for item in image_graphs["flux2_klein_4b_fp8"].values() if item["class_type"] == "Flux2Scheduler")["inputs"]["steps"] == 4,
        "FLUX.2 Klein distilled should keep its native four-step graph",
    )
    check(
        {"CheckpointLoaderSimple", "EmptyLatentImage", "KSampler"}
        <= set(frontend.graph_class_types(image_graphs["noobai_xl_11"])),
        "NoobAI XL should use the native SDXL checkpoint graph",
    )
    check(
        all(
            {"CheckpointLoaderSimple", "EmptyLatentImage", "KSampler"}
            <= set(frontend.graph_class_types(image_graphs[profile_id]))
            for profile_id in (
                "illustrious_xl_v20",
                "wai_nsfw_illustrious_v90",
                "cyberrealistic_pony_v18",
                "lustify_sdxl_v40",
            )
        )
        and "score_9" in image_graphs["cyberrealistic_pony_v18"]["2"]["inputs"]["text"],
        "new community checkpoints should use the optimized native SDXL graph and profile prefix",
    )
    qwen_edit_graph = frontend.build_image_prompt(
        prompt="保留主体，只调整背景光线",
        negative="模糊",
        width=1024,
        height=1024,
        seed=7,
        profile_id="qwen2512_lightning_fp8",
        steps=4,
        cfg=1.0,
        sampler="euler",
        scheduler="simple",
        batch_size=2,
        source_image="beginner_frontend/edit-source.png",
        edit_strength=0.65,
    )
    qwen_edit_sampler = next(item for item in qwen_edit_graph.values() if item["class_type"] == "KSampler")
    repeat_node_id = next(node_id for node_id, item in qwen_edit_graph.items() if item["class_type"] == "RepeatLatentBatch")
    check(
        {"LoadImage", "ImageScale", "VAEEncode", "RepeatLatentBatch"}
        <= set(frontend.graph_class_types(qwen_edit_graph))
        and "EmptySD3LatentImage" not in frontend.graph_class_types(qwen_edit_graph)
        and qwen_edit_sampler["inputs"]["denoise"] == 0.65
        and qwen_edit_sampler["inputs"]["latent_image"] == [repeat_node_id, 0],
        "Qwen image edit should encode, resize, repeat, and denoise the source latent",
    )
    flux_edit_graph = frontend.build_image_prompt(
        prompt="change the product color to red",
        negative="",
        width=1024,
        height=1024,
        seed=8,
        profile_id="flux2_klein_base_4b_fp8",
        steps=20,
        cfg=4.0,
        sampler="euler",
        scheduler="flux2",
        source_image="beginner_frontend/edit-source.png",
    )
    check(
        {"LoadImage", "ImageScaleToTotalPixels", "VAEEncode", "ReferenceLatent", "EmptyFlux2LatentImage"}
        <= set(frontend.graph_class_types(flux_edit_graph)),
        "FLUX.2 image edit should use native reference latents while keeping a target latent",
    )
    hidream_edit_graph = frontend.build_image_prompt(
        prompt="把背景改成雨夜街道",
        negative="",
        width=2048,
        height=2048,
        seed=9,
        profile_id="hidream_o1_dev2604_fp8",
        steps=28,
        cfg=1.0,
        sampler="lcm",
        scheduler="normal",
        source_image="beginner_frontend/edit-source.png",
    )
    hidream_reference_id = next(
        node_id for node_id, item in hidream_edit_graph.items() if item["class_type"] == "HiDreamO1ReferenceImages"
    )
    check(
        "images.image_1" in hidream_edit_graph[hidream_reference_id]["inputs"]
        and hidream_edit_graph["9"]["inputs"]["positive"] == [hidream_reference_id, 0],
        "HiDream O1 image edit should use its native reference-image conditioning",
    )
    prompt_data = frontend.build_effective_prompt(
        "中国风茶叶海报",
        prompt_mode="structured",
        style_preset="poster",
        exact_text="春日新茶",
    )
    check(
        "中国风茶叶海报" in prompt_data["effective"]
        and "春日新茶" in prompt_data["effective"]
        and "不得改写" in prompt_data["effective"],
        "Chinese prompt enhancement should preserve the source and protected display text",
    )
    english_prompt_data = frontend.build_effective_prompt(
        "A brushed aluminum espresso machine on a clean studio table",
        prompt_mode="structured",
        style_preset="product",
        exact_text="NOVA",
    )
    check(
        english_prompt_data["language"] == "en"
        and "Subject and scene:" in english_prompt_data["effective"]
        and "Visual style:" in english_prompt_data["effective"]
        and "Clearly and exactly render" in english_prompt_data["effective"]
        and "画面主题" not in english_prompt_data["effective"],
        "pure English prompts should stay in an English prompt pipeline",
    )
    edit_prompt_data = frontend.build_effective_prompt(
        "只把背景改为雨夜霓虹街道",
        prompt_mode="structured",
        style_preset="none",
        edit_mode=True,
    )
    check(
        edit_prompt_data["edit_mode"] is True
        and "编辑要求" in edit_prompt_data["effective"]
        and "未明确要求修改" in edit_prompt_data["effective"]
        and "构图要求：主体明确" not in edit_prompt_data["effective"],
        "image edit prompts should use instruction and preservation wording instead of text-to-image composition prose",
    )
    raw_english_prompt = frontend.build_effective_prompt(
        "A quiet library at midnight",
        prompt_mode="native",
        style_preset="none",
    )
    check(
        raw_english_prompt["effective"] == "A quiet library at midnight."
        and raw_english_prompt["language"] == "en",
        "native prompt mode should submit a pure English prompt without Chinese wrappers",
    )
    image_studio_payload = frontend.image_studio_static_payload()
    aspect_presets = image_studio_payload["aspect_presets"]
    check(len(aspect_presets) >= 24, "image studio should expose the expanded resolution preset catalog")
    check(
        all(int(item["width"]) % 16 == 0 and int(item["height"]) % 16 == 0 for item in aspect_presets),
        "image resolution presets should stay aligned to 16 pixels",
    )
    flux_4k = frontend.normalize_image_dimensions(1, 1, "4k-landscape", "flux2_dev_fp8")
    check(flux_4k == (3840, 2160, "4k-landscape"), "FLUX.2 should preserve the 4K landscape preset")
    limited_4k = frontend.normalize_image_dimensions(1, 1, "4k-landscape", "qwen2512_quality_fp8")
    check(limited_4k == (2048, 1152, "custom"), "oversized presets should scale down without changing aspect ratio")
    custom_size = frontend.normalize_image_dimensions(1733, 999, "custom", "qwen2512_quality_fp8")
    check(custom_size == (1728, 992, "custom"), "custom image dimensions should align to 16 pixels")
    check(
        frontend.normalize_image_output_subdir("") == "image_studio"
        and frontend.normalize_image_output_subdir("renders\\posters") == "renders/posters",
        "image studio output directories should default correctly and preserve safe nested folders",
    )
    image_prefix = frontend.image_studio_output_prefix("qwen2512_lightning_fp8", "renders/posters")
    check(
        image_prefix.startswith("renders/posters/qwen2512_lightning_fp8_"),
        "image generation should write through the configured output subdirectory",
    )
    unrestricted_prompt = frontend.build_effective_prompt(
        "影棚人物摄影",
        profile_id="qwen2512_lightning_fp8",
        nsfw=True,
    )
    check(
        unrestricted_prompt["nsfw"] is True
        and "无限制模式" not in unrestricted_prompt["effective"]
        and "明确成年人" not in unrestricted_prompt["effective"],
        "unrestricted mode should not inject policy prose into the visual prompt",
    )
    klein_standard = frontend.build_image_prompt(
        prompt="test",
        negative="",
        width=1024,
        height=1024,
        seed=1,
        profile_id="flux2_klein_4b_fp8",
        nsfw=False,
    )
    klein_unrestricted = frontend.build_image_prompt(
        prompt="test",
        negative="",
        width=1024,
        height=1024,
        seed=1,
        profile_id="flux2_klein_4b_fp8",
        nsfw=True,
    )
    flux_unrestricted = frontend.build_image_prompt(
        prompt="test",
        negative="",
        width=1024,
        height=1024,
        seed=1,
        profile_id="flux2_dev_fp8",
        nsfw=True,
    )
    check(
        klein_standard["2"]["inputs"]["clip_name"] == "qwen_3_4b_fp4_flux2.safetensors"
        and klein_unrestricted["2"]["inputs"]["clip_name"] == "qwen3-4b-heretic_nvfp4.safetensors"
        and flux_unrestricted["2"]["inputs"]["clip_name"]
        == "mistral_small_3_abliterated_v2_fp8mixed.safetensors",
        "Klein/FLUX.2 unrestricted mode should swap in the community uncensored text encoders",
    )
    native_unrestricted_prompt = frontend.build_effective_prompt(
        "成年角色插画",
        profile_id="noobai_xl_11",
        nsfw=True,
    )
    check(
        native_unrestricted_prompt["nsfw"] is True
        and native_unrestricted_prompt["nsfw_status"] == "native_unaligned",
        "native unaligned image profiles should enable unrestricted mode without an add-on",
    )
    standard_wan_i2v = frontend.build_a14b_i2v_prompt(
        prompt="test",
        negative="bad",
        image_name=frontend.KEYFRAME_UPLOAD_PLACEHOLDER,
        width=832,
        height=480,
        length=49,
        fps=24,
        seed=1,
        steps=4,
        cfg=1.0,
    )
    unrestricted_wan_i2v = frontend.build_a14b_i2v_prompt(
        prompt="test",
        negative="bad, NSFW",
        image_name=frontend.KEYFRAME_UPLOAD_PLACEHOLDER,
        width=832,
        height=480,
        length=49,
        fps=24,
        seed=1,
        steps=4,
        cfg=1.0,
        unrestricted=True,
        unrestricted_strength=0.85,
    )
    standard_loras = [item["inputs"]["lora_name"] for item in standard_wan_i2v.values() if item["class_type"] == "LoraLoaderModelOnly"]
    unrestricted_loras = [item["inputs"]["lora_name"] for item in unrestricted_wan_i2v.values() if item["class_type"] == "LoraLoaderModelOnly"]
    check(
        not any("Unrestricted" in name for name in standard_loras)
        and {"Wan2.2/Unrestricted/NSFW-22-H-e8.safetensors", "Wan2.2/Unrestricted/NSFW-22-L-e8.safetensors"}
        <= set(unrestricted_loras)
        and unrestricted_wan_i2v["33"]["inputs"]["strength_model"] == 0.85
        and "nsfwsks" in unrestricted_wan_i2v["11"]["inputs"]["text"]
        and "nsfw" not in unrestricted_wan_i2v["12"]["inputs"]["text"].lower(),
        "Wan unrestricted mode should load the paired I2V experts only when enabled",
    )
    empty_motion = frontend.resolve_motion_lora_names(pack_id="")
    orbit_motion = frontend.resolve_motion_lora_names(pack_id="orbit_shot")
    check(
        empty_motion == ("", "")
        and "orbit_shot_high" in orbit_motion[0]
        and "orbit_shot_low" in orbit_motion[1],
        "empty motion pack selection must not fall back to orbit LoRA",
    )
    check(
        "nsfw" not in frontend.DEFAULT_NEGATIVE.lower(),
        "default video negative must not include NSFW as a censorship term",
    )
    h3_unrestricted_graph = frontend.build_minimax_h3_prompt(
        prompt="a quiet room",
        negative="bad, NSFW",
        image_name="",
        width=864,
        height=480,
        length=73,
        fps=24,
        seed=1,
        steps=20,
        cfg=1.0,
        unrestricted=True,
        trigger="customtrig",
    )
    h3_unrestricted_loras = [
        item["inputs"]["lora_name"]
        for item in h3_unrestricted_graph.values()
        if item["class_type"] == "LoraLoaderModelOnly"
    ]
    check(
        "customtrig" in h3_unrestricted_graph["5"]["inputs"]["prompt"]
        and not h3_unrestricted_loras
        and frontend.video_mode_allows_unrestricted("minimax_h3_t2v")
        and frontend.video_mode_allows_unrestricted("minimax_h3_i2v"),
        "H3 unrestricted mode should pass the prompt through without Wan NSFW LoRAs",
    )
    ltx25_unrestricted_graph = frontend.build_ltx25_t2v_prompt(
        prompt="a cinematic room",
        negative="bad, NSFW",
        width=1280,
        height=704,
        length=121,
        fps=24,
        seed=4,
        steps=11,
        cfg=1.0,
        unrestricted=True,
        trigger="customtrig",
    )
    ltx25_unrestricted_loras = [
        item["inputs"]["lora_name"]
        for item in ltx25_unrestricted_graph.values()
        if item["class_type"] == "LoraLoaderModelOnly"
    ]
    check(
        "customtrig" in ltx25_unrestricted_graph["5"]["inputs"]["text"]
        and "nsfw" not in ltx25_unrestricted_graph["6"]["inputs"]["text"].lower()
        and not ltx25_unrestricted_loras
        and frontend.video_mode_allows_unrestricted("ltx25_t2v")
        and frontend.video_mode_allows_unrestricted("ltx25_i2v"),
        "LTX 2.5 unrestricted mode should keep the prompt and strip conflicting negative terms without Wan LoRAs",
    )
    cuda_rife = frontend.build_rife_prompt(video_name="sample.mp4", fps=24, multiplier=2, dtype="float16", batch_size=4)
    check(cuda_rife["2"]["inputs"]["dtype"] == "float16", "CUDA RIFE should allow the optimized float16 dtype")
    check(
        "LoadImage" not in frontend.graph_class_types(ti2v_text_graph)
        and "start_image" not in ti2v_text_graph["8"]["inputs"],
        "Wan2.2 TI2V should build a text-video graph when no keyframe is supplied",
    )
    check(
        not frontend.keyframe_requirement_errors(mode="ti2v_5b", has_upload=False),
        "Wan2.2 TI2V keyframe should be optional",
    )
    check(
        frontend.keyframe_requirement_errors(mode="ltx_i2v", has_upload=False),
        "image-only workflow preflight should require a user-uploaded keyframe",
    )
    check(
        not frontend.keyframe_requirement_errors(mode="ltx_i2v", has_upload=True),
        "uploaded keyframe should satisfy the image-only workflow requirement",
    )
    check(
        not frontend.keyframe_requirement_errors(mode="ltx23_t2v", has_upload=False),
        "text-video workflow should not require a keyframe",
    )
    check(
        frontend.keyframe_requirement_errors(mode="ltx23_i2v", has_upload=False)
        and not frontend.keyframe_requirement_errors(mode="ltx23_i2v", has_upload=True),
        "LTX 2.3 I2V should require only a user-provided keyframe",
    )
    check(
        not frontend.keyframe_requirement_errors(mode="ltx25_t2v", has_upload=False)
        and frontend.keyframe_requirement_errors(mode="ltx25_i2v", has_upload=False)
        and not frontend.keyframe_requirement_errors(mode="ltx25_i2v", has_upload=True),
        "LTX 2.5 should require a keyframe only for I2V/first-last-frame generation",
    )
    check(
        frontend.keyframe_requirement_errors(mode="hunyuan15_i2v", has_upload=False)
        and not frontend.keyframe_requirement_errors(mode="hunyuan15_i2v", has_upload=True)
        and not frontend.keyframe_requirement_errors(mode="hunyuan15_t2v", has_upload=False),
        "HunyuanVideo 1.5 should require a keyframe only for I2V",
    )
    schema_errors = frontend.graph_node_schema_errors(
        {"1": frontend.node("ExampleNode", {"known": 1, "stale": 2})},
        {"ExampleNode": {"input": {"required": {"known": ["INT"]}, "optional": {}}}},
    )
    check(schema_errors and "stale" in schema_errors[0], "workflow schema validation should catch stale node inputs")
    dynamic_schema_errors = frontend.graph_node_schema_errors(
        {"1": frontend.node("DynamicFormatNode", {"images": ["0", 0], "format": "video/h264-mp4", "crf": 19})},
        {
            "DynamicFormatNode": {
                "input": {
                    "required": {
                        "images": ["IMAGE"],
                        "format": [
                            ["video/h264-mp4"],
                            {"formats": {"video/h264-mp4": [["crf", "INT", {"default": 19}]]}},
                        ],
                    },
                    "optional": {},
                }
            }
        },
    )
    check(not dynamic_schema_errors, "workflow schema validation should allow active format-dependent widgets")
    dynamic_combo_schema = {
        "SeedVR2TemporalChunk": {
            "input": {
                "required": {
                    "chunking_mode": [
                        "COMFY_DYNAMICCOMBO_V3",
                        {"options": [{"key": "auto", "inputs": {"required": {}}}]},
                    ]
                },
                "optional": {},
            }
        }
    }
    check(
        not frontend.graph_node_schema_errors(
            {"1": frontend.node("SeedVR2TemporalChunk", {"chunking_mode": "auto"})},
            dynamic_combo_schema,
        )
        and frontend.graph_node_schema_errors(
            {"1": frontend.node("SeedVR2TemporalChunk", {"chunking_mode": {"chunking_mode": "auto"}})},
            dynamic_combo_schema,
        ),
        "workflow schema validation should preserve ComfyUI V3 dynamic combo wire format",
    )
    return {"graphs": len(graphs)}


def hardware_matrix_check() -> dict[str, object]:
    sys.path.insert(0, str(ROOT))
    from beginner_frontend import app as frontend

    with tempfile.TemporaryDirectory(prefix="multimodel_hardware_matrix_") as temp_name:
        base_dir = Path(temp_name)
        assets = [dict(item, ok=True) for item in frontend.workflow_asset_manifest(base_dir)]
        custom_nodes = [dict(item, ok=True) for item in frontend.custom_node_manifest(base_dir)]
        node_checks = [dict(item, ok=True) for item in frontend.collect_node_checks({})]
        tool_checks = [
            {"name": "ffmpeg", "ok": True},
            {"name": "ffmpeg:deflicker", "ok": True},
            {"name": "ffmpeg:hqdn3d", "ok": True},
        ]

        cases = [
            {
                "name": "cuda_96gb",
                "os": {"name": "Windows"},
                "hardware": {"accelerator": "cuda", "platform_strategy": "cuda_multi_model", "max_vram_gb": 96, "mac": {}},
                "install_profile": "minimax-h3-fl2va-int8",
                "draft": "minimax_h3_fl2va_int8_t2v",
                "final": "minimax_h3_fl2va_int8_i2v",
            },
            {
                "name": "cuda_48gb",
                "os": {"name": "Windows"},
                "hardware": {"accelerator": "cuda", "platform_strategy": "cuda_multi_model", "max_vram_gb": 48, "mac": {}},
                "install_profile": "ltx25-distilled-int8",
                "draft": "ltx25_distilled_int8_t2v",
                "final": "ltx25_distilled_int8_i2v",
            },
            {
                "name": "mac_16gb",
                "os": {"name": "Darwin"},
                "hardware": {
                    "accelerator": "mps",
                    "platform_strategy": "mac_mps",
                    "max_vram_gb": 0,
                    "front_torch_mps_ready": True,
                    "comfy_torch_mps_ready": False,
                    "mac_video_tier": "mac_ltx_low",
                    "mac": {"is_macos": True, "apple_silicon": True, "unified_memory_gb": 16},
                },
                "install_profile": "mac-low",
                "draft": "mac_ltx_low_i2v",
                "final": "mac_ltx_low_i2v",
            },
            {
                "name": "mac_128gb",
                "os": {"name": "Darwin"},
                "hardware": {
                    "accelerator": "mps",
                    "platform_strategy": "mac_mps",
                    "max_vram_gb": 0,
                    "front_torch_mps_ready": True,
                    "comfy_torch_mps_ready": False,
                    "mac_video_tier": "mac_wan5b_720p_experimental",
                    "mac": {"is_macos": True, "apple_silicon": True, "unified_memory_gb": 128},
                },
                "install_profile": "mac-wan5b",
                "draft": "mac_ltx_quality_i2v",
                "final": "mac_wan5b_720p_experimental",
            },
            {
                "name": "cpu_only",
                "os": {"name": "Windows"},
                "hardware": {"accelerator": "cpu", "platform_strategy": "post_only", "max_vram_gb": 0, "mac": {}},
                "install_profile": "post-only",
                "draft": "no_local_video_draft",
                "final": "no_local_video_final",
            },
        ]

        results: dict[str, dict[str, str]] = {}
        for case in cases:
            with patch("beginner_frontend.app.saved_model_catalog_id", return_value="__hardware_defaults__"):
                options = frontend.workflow_model_options(
                    os_info=case["os"],
                    hardware=case["hardware"],
                    assets=assets,
                    custom_nodes=custom_nodes,
                    tool_checks=tool_checks,
                    node_checks=node_checks,
                    base_dir=base_dir,
                )
            recommended = options["recommended"]
            profile = frontend.install_profile_for_hardware(case["hardware"])
            check(profile == case["install_profile"], f"{case['name']} install profile mismatch: {profile}")
            check(recommended["keyframe"] == "upload_keyframe", f"{case['name']} should keep the optional upload as the keyframe default")
            check(recommended["draft"] == case["draft"], f"{case['name']} draft mismatch: {recommended['draft']}")
            check(recommended["final"] == case["final"], f"{case['name']} final mismatch: {recommended['final']}")
            results[case["name"]] = {
                "install_profile": profile,
                "draft": recommended["draft"],
                "final": recommended["final"],
            }

        wan5b_ids = {"ti2v_5b", "umt5", "wan22_vae", "rife49", "realesrgan_x2", "ultrasharp_x4"}
        wan5b_only_assets = [dict(item, ok=item["id"] in wan5b_ids) for item in frontend.workflow_asset_manifest(base_dir)]
        with patch("beginner_frontend.app.saved_model_catalog_id", return_value="wan22_ti2v_5b_fp16"):
            wan5b_only_recommendations = frontend.model_recommendations(
                os_info={"name": "Windows"},
                hardware={"accelerator": "cuda", "platform_strategy": "cuda_wan_workflow", "max_vram_gb": 48, "mac": {}},
                assets=wan5b_only_assets,
                custom_nodes=custom_nodes,
                tool_checks=tool_checks,
                node_checks=node_checks,
                base_dir=base_dir,
            )
        generation = next(item for item in wan5b_only_recommendations if item["step"] == "视频生成")
        check(generation["status"] != "blocked", "48GB Wan5B-only profile should stay usable when any unified video route is ready")

        h3_options = frontend.workflow_model_options(
            os_info={"name": "Windows"},
            hardware={"accelerator": "cuda", "platform_strategy": "cuda_multi_model", "max_vram_gb": 96, "mac": {}},
            assets=assets,
            custom_nodes=custom_nodes,
            tool_checks=tool_checks,
            node_checks=node_checks,
            base_dir=base_dir,
            selected_model_id="minimax_h3_fl2va_pruned_int8",
        )
        h3_i2v = next(item for item in h3_options["options"]["draft"] if item["id"] == "minimax_h3_fl2va_int8_i2v")
        check(
            h3_i2v["capabilities"]["native_audio"]
            and h3_i2v["capabilities"]["last_frame"]
            and h3_i2v["counterparts"]["text"] == "minimax_h3_fl2va_int8_t2v",
            "model options should expose capability-driven audio/end-frame metadata and T2V/I2V pairing",
        )
        check(
            h3_i2v["catalog_id"] == "minimax_h3_fl2va_pruned_int8"
            and h3_i2v["capabilities"]["frame_rule"] == "17n+5"
            and any(
                item.get("width") == 1920 and item.get("height") == 1088
                for item in h3_i2v["capabilities"]["resolution_presets"]
            )
            and h3_i2v["capabilities"]["max_dimension"] == 2048,
            "video options should link back to the shared catalog and expose the H3 1080P UI preset",
        )
        seed_option = next(item for item in h3_options["options"]["upscale"] if item["id"] == "seedvr2_7b_1080p")
        check(
            h3_options["recommended"]["upscale"] == "seedvr2_7b_1080p"
            and seed_option["mode"] == "upscale_seedvr2"
            and seed_option["install_profile"] == "seedvr2-upscale-7b"
            and seed_option["scale"] == 1.5,
            "96GB CUDA should default to the validated SeedVR2 7B 1080P temporal upscaler",
        )

        unsupported_preview = asyncio.run(
            frontend.workflow_preview(mode="unsupported", model_profile="no_local_video_draft")
        )
        check(not unsupported_preview["ok"], "unsupported video profile should fail workflow preflight")
        check(
            "后期处理路线" in " ".join(unsupported_preview.get("errors", [])),
            "unsupported video profile should explain the post-only route",
        )

        with patch("beginner_frontend.app.saved_model_catalog_id", return_value="ltx_23_22b_fp8_distilled"):
            official_options = frontend.workflow_model_options(
                os_info={"name": "Windows"},
                hardware={"accelerator": "cuda", "platform_strategy": "cuda_wan_workflow", "max_vram_gb": 48, "mac": {}},
                assets=assets,
                custom_nodes=custom_nodes,
                tool_checks=tool_checks,
                node_checks=node_checks,
                base_dir=base_dir,
            )
            official_draft = official_options["options"]["draft"][0]
            check(official_draft["mode"] == "external_workflow", "official workflow models must not silently fall back to Wan generation")
            check(
                len(official_options["options"]["draft"]) > 1
                and any(item.get("mode") == "ltx23_t2v" for item in official_options["options"]["draft"]),
                "an external catalog choice must not erase the platform's native video model options",
            )
            external_preview = asyncio.run(
                frontend.workflow_preview(mode="external_workflow", model_profile=official_draft["id"], model_label=official_draft["label"])
            )
            check(not external_preview["ok"] and "官方 ComfyUI 工作流" in external_preview["message"], "official workflow preflight guidance is missing")
        with patch("beginner_frontend.app.saved_model_catalog_id", return_value="hunyuan15_i2v_480_fp8_distilled"):
            hunyuan_options = frontend.workflow_model_options(
                os_info={"name": "Windows"},
                hardware={"accelerator": "cuda", "platform_strategy": "cuda_wan_workflow", "max_vram_gb": 48, "mac": {}},
                assets=assets,
                custom_nodes=custom_nodes,
                tool_checks=tool_checks,
                node_checks=node_checks,
                base_dir=base_dir,
            )
        check(
            hunyuan_options["recommended"]["final"] == "hunyuan15_i2v_480_fp8"
            and any(item["id"] == "hunyuan15_i2v_720_fp16" for item in hunyuan_options["options"]["draft"])
            and any(item["id"] == "wan22_i2v_a14b_720p" for item in hunyuan_options["options"]["draft"])
            and any(item["id"] == "hunyuan15_i2v_720_fp16" for item in hunyuan_options["options"]["final"])
            and any(item["id"] == "ltx23_nvfp4_dev_t2v" for item in hunyuan_options["options"]["final"]),
            "video choices should expose HunyuanVideo 1.5 and LTX 2.3 NVFP4 without hiding alternatives",
        )
        a14b_options = frontend.workflow_model_options(
            os_info={"name": "Windows"},
            hardware={"accelerator": "cuda", "platform_strategy": "cuda_wan_workflow", "max_vram_gb": 96, "mac": {}},
            assets=assets,
            custom_nodes=custom_nodes,
            tool_checks=tool_checks,
            node_checks=node_checks,
            base_dir=base_dir,
            selected_model_id="wan22_a14b_fp8",
        )
        a14b_draft = next(item for item in a14b_options["options"]["draft"] if item["id"] == "wan22_t2v_a14b_720p")
        a14b_i2v = next(item for item in a14b_options["options"]["draft"] if item["id"] == "wan22_i2v_a14b_720p")
        check(
            a14b_options["recommended"]["draft"] == "wan22_t2v_a14b_720p"
            and a14b_options["recommended"]["final"] == "wan22_i2v_a14b_720p"
            and a14b_draft["catalog_id"] == "wan22_a14b_fp8"
            and a14b_i2v["catalog_id"] == "wan22_a14b_fp8"
            and a14b_draft["install_profile"] == "cuda-a14b"
            and a14b_i2v["install_profile"] == "cuda-a14b",
            "A14B catalog selection must map generate-page options to cuda-a14b, not the 5B warehouse",
        )
        check(
            frontend.install_profile_for_selected_model("cuda-wan5b", "ltx_23_22b_gguf_q4") == "manual",
            "manual catalog models must keep the manual profile instead of falling back to a different model",
        )

    return {"cases": results}


def fallback_check() -> dict[str, str | bool]:
    sys.path.insert(0, str(ROOT))
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("COMFY_URL", None)
        sys.modules.pop("START_WORKFLOW", None)
        launcher = importlib.import_module("START_WORKFLOW")
    from beginner_frontend import app as frontend
    from scripts import install_comfyui, install_workflow_assets
    from scripts import prerequisite_doctor

    check(launcher.APP_VERSION == frontend.APP_VERSION, "launcher and frontend app versions differ")
    check("http://127.0.0.1:8188" in launcher.common_comfy_urls(), "launcher ComfyUI autodiscovery must include 8188")
    with patch.object(
        launcher.urllib.request,
        "urlopen",
        side_effect=http.client.RemoteDisconnected("probe endpoint closed the connection"),
    ):
        check(
            launcher.get_json("http://127.0.0.1:8000/system_stats") is None,
            "launcher ComfyUI discovery must tolerate a non-Comfy service closing the connection",
        )
    check("COMFY_URL" not in launcher.build_frontend_env(comfy_detected=False), "launcher should not pin COMFY_URL when no ComfyUI was discovered")
    check(launcher.build_frontend_env(comfy_detected=True).get("COMFY_URL") == launcher.COMFY_URL, "launcher should pass discovered ComfyUI URL to frontend")
    with patch.object(launcher, "COMFY_URL_CONFIGURED", True), patch.object(launcher, "COMFY_URL", "http://127.0.0.1:8188"):
        check(
            launcher.build_frontend_env(comfy_detected=False).get("COMFY_URL") == "http://127.0.0.1:8188",
            "launcher should respect explicit COMFY_URL even before discovery",
        )
    with patch("beginner_frontend.app.COMFY_URL_CONFIGURED", False):
        check("http://127.0.0.1:8188" in frontend.common_comfy_urls(), "frontend ComfyUI autodiscovery must include 8188")
    check(frontend.COMFY_DISCOVERY_TIMEOUT <= 2.0, "frontend ComfyUI discovery timeout should stay short")
    check(frontend.COMFY_DISCOVERY_FAILURE_TTL <= 5.0, "failed ComfyUI discovery cache should refresh quickly")
    check(frontend.JOB_LOST_AFTER_MS >= 30 * 60 * 1000, "long video jobs should not be declared lost after a short queue gap")
    check(frontend.MAX_VIDEO_FRAMES >= 481, "video frame limit should cover longer native Wan/LTX clips")
    check(launcher.choose_frontend_url() == launcher.FRONTEND_URL, "frontend port must remain fixed instead of silently changing")
    with patch.object(launcher, "matching_frontend_health", return_value=False), patch.object(
        launcher,
        "get_json",
        return_value={"app_version": "2026.08.05.33", "workspace_dir": r"E:\old-workbench", "process_id": 4242},
    ), patch.object(launcher, "pids_listening_on_port", return_value={4242, 4243}), patch.object(
        launcher,
        "process_command_line",
        side_effect=lambda pid: "python -m uvicorn beginner_frontend.app:app --port 7860"
        if pid == 4242
        else r"E:\old-workbench\.venv\Scripts\python.exe START_WORKFLOW.py",
    ), patch.object(launcher, "stop_pid") as stop_pid, patch.object(
        launcher, "port_is_free", side_effect=[False, False, True]
    ), patch.object(launcher.time, "sleep", return_value=None):
        check(launcher.stop_stale_frontend("http://127.0.0.1:7860") is True, "launcher should stop an old workbench on the frontend port")
        check({call.args[0] for call in stop_pid.call_args_list} == {4242, 4243}, "launcher should stop the old frontend listener and its launcher")
    with patch.object(launcher, "matching_frontend_health", return_value=False), patch.object(
        launcher, "get_json", return_value=None
    ), patch.object(launcher, "pids_listening_on_port", return_value={8188}), patch.object(
        launcher,
        "process_command_line",
        return_value=r"E:\ai photo creat\ComfyUI\resources\ComfyUI\main.py --port 8188",
    ), patch.object(launcher, "stop_pid") as stop_pid, patch.object(launcher, "port_is_free", return_value=False):
        check(launcher.stop_stale_frontend("http://127.0.0.1:7860") is False, "launcher must not kill ComfyUI when stopping a stale frontend")
        check(stop_pid.call_count == 0, "launcher must not send taskkill to ComfyUI")
    if os.name == "nt":
        hidden_options = {
            "launcher": launcher.hidden_process_options(),
            "frontend": frontend._hidden_popen_options(),
            "ComfyUI installer": install_comfyui.hidden_process_options(),
            "asset installer": install_workflow_assets.hidden_process_options(),
            "prerequisite doctor": prerequisite_doctor.hidden_process_options(),
        }
        for label, options in hidden_options.items():
            check(
                bool(int(options.get("creationflags") or 0) & subprocess.CREATE_NO_WINDOW)
                and options.get("startupinfo") is not None,
                f"{label} subprocesses should stay hidden on Windows",
            )

    with tempfile.TemporaryDirectory(prefix="wan22_job_store_") as temp_name:
        job_store = Path(temp_name) / "jobs.json"
        generation_backup = dict(frontend.JOBS)
        install_backup = dict(frontend.INSTALL_JOBS)
        try:
            frontend.JOBS.clear()
            frontend.INSTALL_JOBS.clear()
            with patch.object(frontend, "JOB_STORE_PATH", job_store), patch.object(frontend, "JOB_PERSISTENCE_ENABLED", True):
                frontend.store_generation_job(
                    {
                        "id": "persisted-generation",
                        "prompt_id": "prompt-1",
                        "status": "queued",
                        "completed": False,
                        "created_at": 1,
                        "media": [],
                    }
                )
                check(job_store.is_file(), "generation jobs should be persisted atomically")
                frontend.JOBS.clear()
                frontend.load_persisted_job_stores()
                restored = frontend.JOBS.get("persisted-generation") or {}
                check(restored.get("status") == "reconnecting" and restored.get("recovered"), "ComfyUI jobs should recover after frontend restart")

                frontend.JOBS.clear()
                with patch.object(frontend, "persist_job_stores", return_value=None):
                    frontend.reserve_generation_job_slot(
                        job_id="reserved-one",
                        kind="video_generation",
                        mode="minimax_h3_t2v",
                        title="first",
                        created_at=1,
                    )
                    reservation_blocked = False
                    try:
                        frontend.reserve_generation_job_slot(
                            job_id="reserved-two",
                            kind="video_generation",
                            mode="minimax_h3_t2v",
                            title="second",
                            created_at=2,
                        )
                    except frontend.HTTPException as exc:
                        reservation_blocked = exc.status_code == 409
                    check(reservation_blocked, "a second heavy job must be rejected before ComfyUI submission")
                    frontend.finalize_generation_job_slot(
                        {
                            "id": "reserved-one",
                            "kind": "video_generation",
                            "mode": "minimax_h3_t2v",
                            "title": "first",
                            "status": "success",
                            "completed": True,
                            "created_at": 1,
                            "media": [],
                        }
                    )
                    frontend.reserve_generation_job_slot(
                        job_id="reserved-two",
                        kind="video_generation",
                        mode="minimax_h3_t2v",
                        title="second",
                        created_at=2,
                    )
                    frontend.fail_generation_job_slot("reserved-two", "expected test failure")
                    check(
                        frontend.job_is_terminal(frontend.JOBS["reserved-two"]),
                        "a failed ComfyUI submission must release the heavy-generation slot",
                    )

                    frontend.JOBS["recovered-missing"] = {
                        "id": "recovered-missing",
                        "kind": "video_generation",
                        "mode": "minimax_h3_t2v",
                        "status": "reconnecting",
                        "completed": False,
                        "created_at": 0,
                        "prompt_id": "missing-prompt",
                        "prompt_ids": ["missing-prompt"],
                        "recovered": True,
                        "missing_seen_at": frontend.now_ms(),
                    }

                    async def refresh_missing_recovered_job() -> dict[str, object]:
                        async def fake_comfy_get(path: str) -> dict[str, object]:
                            if path.startswith("/history/"):
                                return {}
                            if path == "/queue":
                                return {"queue_running": [], "queue_pending": []}
                            raise AssertionError(path)

                        with patch.object(frontend, "comfy_get", side_effect=fake_comfy_get):
                            return await frontend.refresh_generation_job("recovered-missing")

                    recovered_missing = asyncio.run(refresh_missing_recovered_job())
                    check(
                        recovered_missing["status"] == "interrupted" and recovered_missing["completed"] is True,
                        "a reachable ComfyUI with no recovered prompt should release the slot immediately",
                    )
        finally:
            frontend.JOBS.clear()
            frontend.JOBS.update(generation_backup)
            frontend.INSTALL_JOBS.clear()
            frontend.INSTALL_JOBS.update(install_backup)

    for endpoint in (frontend.generate, frontend.video_smoke_test, frontend.video_face_swap):
        endpoint_source = inspect.getsource(endpoint)
        reserve_at = endpoint_source.find("reserve_generation_job_slot(")
        submit_at = endpoint_source.find('comfy_post("/prompt"')
        finalize_at = endpoint_source.find("finalize_generation_job_slot(")
        check(
            0 <= reserve_at < submit_at < finalize_at,
            f"{endpoint.__name__} must reserve the heavy slot before submitting to ComfyUI",
        )

    async def object_info_cache_check() -> int:
        calls = 0

        async def fake_comfy_get(path: str) -> dict[str, object]:
            nonlocal calls
            calls += 1
            return {"ExampleNode": {"input": {"required": {}, "optional": {}}}}

        frontend.OBJECT_INFO_CACHE.update({"url": None, "value": None, "checked_at": 0.0})
        with patch("beginner_frontend.app.comfy_get", side_effect=fake_comfy_get):
            await frontend.get_comfy_object_info()
            await frontend.get_comfy_object_info()
        return calls

    check(asyncio.run(object_info_cache_check()) == 1, "ComfyUI object_info should be cached between workflow checks")

    progress_job = {
        "id": "self-check-image-progress",
        "kind": "image_generation",
        "prompt_id": "image-prompt-1",
        "prompt_ids": ["image-prompt-1", "image-prompt-2"],
        "generation_mode": "sequential",
        "batch_size": 2,
        "status": "queued",
        "completed": False,
        "media": [],
        "completed_prompt_ids": [],
        "failed_prompt_ids": [],
        "prompt_progress": {},
    }
    frontend.JOBS[progress_job["id"]] = progress_job
    try:
        with patch.object(frontend, "persist_job_stores", return_value=None):
            frontend.apply_comfy_progress_event(
                {
                    "type": "progress",
                    "data": {"prompt_id": "image-prompt-1", "value": 2, "max": 4, "node": "sampler"},
                }
            )
        check(
            progress_job["status"] == "running"
            and progress_job["progress"]["percent"] == 25.0
            and progress_job["progress"]["current_percent"] == 50.0,
            "image progress should aggregate real ComfyUI sampler steps across sequential outputs",
        )
    finally:
        frontend.JOBS.pop(progress_job["id"], None)

    async def partial_sequential_image_check() -> dict[str, object]:
        job = {
            "id": "self-check-partial-images",
            "kind": "image_generation",
            "prompt_id": "partial-1",
            "prompt_ids": ["partial-1", "partial-2"],
            "generation_mode": "sequential",
            "batch_size": 2,
            "status": "running",
            "completed": False,
            "media": [],
            "completed_prompt_ids": [],
            "failed_prompt_ids": [],
            "prompt_progress": {},
        }

        async def fake_comfy_get(path: str) -> dict[str, object]:
            if path == "/history/partial-1":
                return {
                    "partial-1": {
                        "status": {"status_str": "success", "completed": True, "messages": []},
                        "outputs": {
                            "save": {
                                "images": [
                                    {"filename": "partial-one.png", "subfolder": "image_studio", "type": "output"}
                                ]
                            }
                        },
                    }
                }
            if path == "/history/partial-2":
                return {}
            if path == "/queue":
                return {"queue_running": [], "queue_pending": [[1, "partial-2", {}, {}, []]]}
            raise AssertionError(path)

        with patch("beginner_frontend.app.comfy_get", side_effect=fake_comfy_get), patch.object(
            frontend, "persist_job_stores", return_value=None
        ):
            return await frontend.refresh_multi_prompt_image_job(job)

    partial_job = asyncio.run(partial_sequential_image_check())
    check(
        partial_job["status"] == "running"
        and len(partial_job["media"]) == 1
        and partial_job["progress"]["completed"] == 1
        and partial_job["progress"]["percent"] == 50.0,
        "sequential image jobs should expose each completed image before the remaining queue finishes",
    )

    async def sequential_submission_check() -> tuple[dict[str, object], list[dict[str, object]]]:
        submissions: list[dict[str, object]] = []

        async def fake_paths() -> dict[str, str]:
            return {"output_dir": temp_name}

        async def fake_object_info() -> dict[str, object]:
            return {}

        async def fake_listener() -> bool:
            return True

        async def fake_post(_path: str, payload: dict[str, object]) -> dict[str, str]:
            submissions.append(payload)
            return {"prompt_id": f"sequential-{len(submissions)}"}

        with tempfile.TemporaryDirectory(prefix="image_sequential_") as temp_name, patch.object(
            frontend, "active_comfy_paths", side_effect=fake_paths
        ), patch.object(frontend, "saved_image_output_subdir", return_value="qa"), patch.object(
            frontend, "get_comfy_object_info", side_effect=fake_object_info
        ), patch.object(
            frontend, "resolve_graph_model_option_names", side_effect=lambda graph, _object_info: graph
        ), patch.object(
            frontend, "image_studio_graph_errors", return_value=[]
        ), patch.object(
            frontend, "ensure_comfy_progress_listener", side_effect=fake_listener
        ), patch.object(
            frontend, "comfy_post", side_effect=fake_post
        ), patch.object(
            frontend, "store_generation_job", side_effect=lambda job: job
        ):
            response = await frontend.image_studio_generate(
                prompt="中文海报",
                negative="bad",
                prompt_mode="structured",
                style_preset="photo",
                exact_text="",
                profile="qwen2512_lightning_fp8",
                aspect="landscape",
                width=1024,
                height=1024,
                steps=4,
                cfg=1.0,
                sampler="euler",
                scheduler="simple",
                batch_size=3,
                generation_mode="sequential",
                seed="100",
                edit_mode=False,
                edit_operation="instruction",
                edit_strength=0.35,
                source_adherence=0.65,
                edit_resize_mode="crop",
                source_image_filename="",
                source_image_subfolder="",
                source_image_type="",
                nsfw=False,
                nsfw_lora_strength=1.0,
                source_image=None,
            )
        return json.loads(response.body), submissions

    sequential_job, sequential_submissions = asyncio.run(sequential_submission_check())
    sequential_graph_batches = [
        next(
            node["inputs"]["batch_size"]
            for node in submission["prompt"].values()
            if node["class_type"] == "EmptySD3LatentImage"
        )
        for submission in sequential_submissions
    ]
    check(
        sequential_job["prompt_seeds"] == [100, 101, 102]
        and len(sequential_submissions) == 3
        and sequential_graph_batches == [1, 1, 1],
        "sequential image generation should submit one single-image graph per requested output with deterministic seeds",
    )

    async def image_edit_submission_check() -> tuple[dict[str, object], dict[str, object], bool]:
        submissions: list[dict[str, object]] = []
        with tempfile.TemporaryDirectory(prefix="image_edit_submission_") as temp_name:
            root = Path(temp_name)
            input_dir = root / "input"
            output_dir = root / "output"
            temp_dir = root / "temp"
            source_dir = output_dir / "image_studio"
            source_dir.mkdir(parents=True)
            source_path = source_dir / "source.png"
            source_path.write_bytes(b"self-check-image")

            async def fake_paths() -> dict[str, object]:
                return {
                    "base_dir": root,
                    "input_dir": input_dir,
                    "output_dir": output_dir,
                    "temp_dir": temp_dir,
                    "user_dir": root / "user",
                    "source": "self-check",
                    "base_dir_source": "self-check",
                    "base_dir_mismatch": False,
                }

            async def fake_object_info() -> dict[str, object]:
                return {}

            async def fake_listener() -> bool:
                return True

            async def fake_post(_path: str, payload: dict[str, object]) -> dict[str, str]:
                submissions.append(payload)
                return {"prompt_id": "image-edit-1"}

            with patch.object(frontend, "active_comfy_paths", side_effect=fake_paths), patch.object(
                frontend, "saved_image_output_subdir", return_value="qa"
            ), patch.object(frontend, "get_comfy_object_info", side_effect=fake_object_info), patch.object(
                frontend, "resolve_graph_model_option_names", side_effect=lambda graph, _object_info: graph
            ), patch.object(frontend, "image_studio_graph_errors", return_value=[]), patch.object(
                frontend, "ensure_comfy_progress_listener", side_effect=fake_listener
            ), patch.object(frontend, "comfy_post", side_effect=fake_post), patch.object(
                frontend, "store_generation_job", side_effect=lambda job: job
            ):
                response = await frontend.image_studio_generate(
                    prompt="只把背景改为蓝色",
                    negative="bad",
                    prompt_mode="structured",
                    style_preset="none",
                    exact_text="",
                    profile="qwen2512_lightning_fp8",
                    aspect="custom",
                    width=1024,
                    height=1024,
                    steps=4,
                    cfg=1.0,
                    sampler="euler",
                    scheduler="simple",
                    batch_size=1,
                    generation_mode="batch",
                    seed="200",
                    edit_mode=True,
                    edit_operation="instruction",
                    edit_strength=0.65,
                    source_adherence=0.35,
                    edit_resize_mode="crop",
                    source_image_filename="source.png",
                    source_image_subfolder="image_studio",
                    source_image_type="output",
                    source_processing="full",
                    face_authorization_confirmed=False,
                    face_extract_id="",
                    face_index=-1,
                    face_crop_mode="face",
                    nsfw=False,
                    nsfw_lora_strength=1.0,
                    source_image=None,
                )
            job = json.loads(response.body)
            copied = Path(str(job["source_image"]["path"])).exists()
            return job, submissions[0]["prompt"], copied

    edit_job, edit_submission_graph, edit_source_copied = asyncio.run(image_edit_submission_check())
    edit_sampler = next(item for item in edit_submission_graph.values() if item["class_type"] == "KSampler")
    check(
        edit_job["edit_mode"] is True
        and edit_job["mode"] == "image_edit"
        and edit_job["source_image"]["origin"] == "history"
        and edit_source_copied
        and {"LoadImage", "ImageScale", "VAEEncode"} <= set(frontend.graph_class_types(edit_submission_graph))
        and edit_sampler["inputs"]["denoise"] == 0.65,
        "image edit submission should copy history media into ComfyUI input and submit a real img2img graph",
    )

    latent_controls = frontend.normalize_image_edit_controls(
        "qwen2512_quality_fp8",
        source_adherence=0.8,
        edit_strength=0.9,
    )
    semantic_controls = frontend.normalize_image_edit_controls(
        "flux2_dev_fp8",
        source_adherence=0.9,
        edit_strength=0.2,
    )
    check(
        latent_controls["numeric"] is True
        and latent_controls["edit_strength"] == 0.2
        and latent_controls["source_adherence"] == 0.8
        and semantic_controls["numeric"] is False
        and semantic_controls["edit_strength"] == 1.0
        and semantic_controls["source_adherence"] == 0.9,
        "original-image adherence should invert real denoise only for latent img2img and stay semantic for native reference edits",
    )

    def reactor_object_info() -> dict[str, object]:
        return {
            "ReActorSetWeight": {
                "input": {
                    "required": {
                        "input_image": ["IMAGE", {}],
                        "source_image": ["IMAGE", {}],
                        "faceswap_weight": [["0%", "12.5%", "25%", "37.5%", "50%", "62.5%", "75%", "87.5%", "100%"], {"default": "100%"}],
                    }
                },
                "output": ["IMAGE", "FACE_MODEL"],
            },
            "ReActorFaceSwap": {
                "input": {
                    "required": {
                        "enabled": ["BOOLEAN", {"default": True}],
                        "input_image": ["IMAGE", {}],
                        "swap_model": [["inswapper_128.onnx"]],
                        "facedetection": [["retinaface_resnet50", "retinaface_mobile0.25"]],
                        "face_restore_model": [["none", "GFPGANv1.4.onnx"]],
                        "face_restore_visibility": ["FLOAT", {"default": 0.8}],
                        "codeformer_weight": ["FLOAT", {"default": 0.5}],
                        "detect_gender_input": [["no", "female", "male"]],
                        "detect_gender_source": [["no", "female", "male"]],
                        "input_faces_index": ["STRING", {"default": "0"}],
                        "source_faces_index": ["STRING", {"default": "0"}],
                        "console_log_level": [[0, 1, 2]],
                    },
                    "optional": {
                        "source_image": ["IMAGE", {}],
                        "face_model": ["FACE_MODEL", {}],
                        "input_faces_order": [["large-small", "small-large"]],
                        "source_faces_order": [["large-small", "small-large"]],
                    },
                },
                "output": ["IMAGE", "FACE_MODEL"],
            },
        }

    reactor_info = reactor_object_info()
    reactor_graph, reactor_resolved = frontend.build_face_swap_prompt(
        object_info=reactor_info,
        target_image="target.png",
        target_face_image="faces/target-2.png",
        identity_face_image="faces/identity-1.png",
        target_face_index=1,
        strength=82.0,
        restore_model="GFPGANv1.4.onnx",
        restore_visibility=0.75,
        filename_prefix="qa/face-swap",
    )
    check(
        reactor_graph["5"]["inputs"]["input_image"] == ["1", 0]
        and reactor_graph["5"]["inputs"]["face_model"] == ["4", 1]
        and reactor_graph["4"]["inputs"]["input_image"] == ["2", 0]
        and reactor_graph["4"]["inputs"]["source_image"] == ["3", 0]
        and reactor_graph["5"]["inputs"]["input_faces_index"] == "1"
        and reactor_graph["5"]["inputs"]["input_faces_order"] == "large-small"
        and reactor_resolved["strength"] == "87.5%",
        "face-swap graph should preserve the full target image, blend the selected target/donor identities, and address the selected target face",
    )

    fake_face_assets = [
        {"id": asset_id, "ok": True, "expected_gb": 0.1, "relative_path": asset_id, "installable": True}
        for asset_id in frontend.INSTALL_PROFILE_ASSETS[frontend.FACE_SWAP_INSTALL_PROFILE]
    ]
    fake_face_nodes = [{"id": "reactor", "ok": True, "path": "custom_nodes/ComfyUI-ReActor", "installable": True}]
    with tempfile.TemporaryDirectory(prefix="reactor_capability_") as temp_name, patch.object(
        frontend, "collect_asset_checks", return_value=fake_face_assets
    ), patch.object(frontend, "collect_custom_node_checks", return_value=fake_face_nodes):
        face_capability = frontend.face_swap_capability_payload(reactor_info, Path(temp_name))
    check(
        face_capability["ready"] is True
        and face_capability["required_active_base"] is True
        and face_capability["swap_models"] == ["inswapper_128.onnx"]
        and face_capability["missing"] == [],
        "face-swap capability should require the active ComfyUI base and report ready only when nodes and tracked models are present",
    )

    with tempfile.TemporaryDirectory(prefix="reactor_active_base_") as temp_name:
        active_base = Path(temp_name) / "active"
        other_base = Path(temp_name) / "other"
        active_base.mkdir()
        other_base.mkdir()
        check(
            frontend.install_base_dir_for_profile(frontend.FACE_SWAP_INSTALL_PROFILE, str(active_base), active_base) == active_base,
            "face-swap install should accept the active ComfyUI base",
        )
        rejected_other_base = False
        try:
            frontend.install_base_dir_for_profile(frontend.FACE_SWAP_INSTALL_PROFILE, str(other_base), active_base)
        except frontend.HTTPException as exc:
            rejected_other_base = exc.status_code == 400
        check(rejected_other_base, "face-swap install should reject a detached model-only directory")

    face_progress = frontend.generation_progress_payload(
        {
            "mode": "image_face_swap",
            "status": "running",
            "prompt_id": "face-progress-1",
            "prompt_ids": ["face-progress-1"],
            "active_node": "5",
            "batch_size": 1,
            "media": [],
            "completed_prompt_ids": [],
            "failed_prompt_ids": [],
            "prompt_progress": {},
        }
    )
    check(
        face_progress["percent"] == 72.0 and "替换目标脸" in face_progress["label"],
        "face-swap progress should report ReActor execution stages instead of fake sampler steps",
    )

    async def face_swap_submission_check() -> tuple[dict[str, object], dict[str, object], bool]:
        authorization_rejected = False
        try:
            await frontend.image_studio_face_swap(
                authorization_confirmed=False,
                target_face_extract_id="target-extraction",
                target_face_index=0,
                identity_face_extract_id="identity-extraction",
                identity_face_index=0,
                face_swap_strength=100.0,
                face_restore_model="none",
                face_restore_visibility=0.8,
            )
        except frontend.HTTPException as exc:
            authorization_rejected = exc.status_code == 403

        submissions: list[dict[str, object]] = []
        with tempfile.TemporaryDirectory(prefix="face_swap_submission_") as temp_name:
            root = Path(temp_name)
            input_dir = root / "input"
            output_dir = root / "output"
            face_dir = input_dir / "faces"
            face_dir.mkdir(parents=True)
            output_dir.mkdir()
            for filename in ("target.png", "identity.png"):
                (input_dir / filename).write_bytes(b"original")
            for filename in ("target-1.png", "target-2.png", "identity-1.png"):
                (face_dir / filename).write_bytes(b"face")

            target_record = {
                "id": "target-extraction",
                "created_at": frontend.now_ms(),
                "authorization_confirmed": True,
                "original": {"filename": "target.png", "subfolder": "", "type": "input", "width": 1280, "height": 720},
                "faces": [
                    {"index": 0, "filename": "target-1.png", "subfolder": "faces", "type": "input"},
                    {"index": 1, "filename": "target-2.png", "subfolder": "faces", "type": "input"},
                ],
            }
            identity_record = {
                "id": "identity-extraction",
                "created_at": frontend.now_ms(),
                "authorization_confirmed": True,
                "original": {"filename": "identity.png", "subfolder": "", "type": "input", "width": 640, "height": 640},
                "faces": [{"index": 0, "filename": "identity-1.png", "subfolder": "faces", "type": "input"}],
            }
            with frontend.FACE_EXTRACTION_LOCK:
                frontend.FACE_EXTRACTIONS.clear()
            frontend.register_face_extraction(target_record)
            frontend.register_face_extraction(identity_record)

            async def fake_paths() -> dict[str, object]:
                return {
                    "base_dir": root,
                    "input_dir": input_dir,
                    "output_dir": output_dir,
                    "temp_dir": root / "temp",
                    "user_dir": root / "user",
                }

            async def fake_object_info() -> dict[str, object]:
                return reactor_info

            async def fake_listener() -> bool:
                return True

            async def fake_post(_path: str, payload: dict[str, object]) -> dict[str, str]:
                submissions.append(payload)
                return {"prompt_id": "face-swap-1"}

            with patch.object(frontend, "active_comfy_paths", side_effect=fake_paths), patch.object(
                frontend, "get_comfy_object_info", side_effect=fake_object_info
            ), patch.object(frontend, "face_swap_capability_payload", return_value={"ready": True}), patch.object(
                frontend, "image_studio_graph_errors", return_value=[]
            ), patch.object(frontend, "ensure_comfy_progress_listener", side_effect=fake_listener), patch.object(
                frontend, "comfy_post", side_effect=fake_post
            ), patch.object(frontend, "saved_image_output_subdir", return_value="qa"), patch.object(
                frontend, "store_generation_job", side_effect=lambda job: job
            ):
                response = await frontend.image_studio_face_swap(
                    authorization_confirmed=True,
                    target_face_extract_id="target-extraction",
                    target_face_index=1,
                    identity_face_extract_id="identity-extraction",
                    identity_face_index=0,
                    face_swap_strength=100.0,
                    face_restore_model="none",
                    face_restore_visibility=0.8,
                )
            with frontend.FACE_EXTRACTION_LOCK:
                frontend.FACE_EXTRACTIONS.clear()
            return json.loads(response.body), submissions[0]["prompt"], authorization_rejected

    face_swap_job, face_swap_graph, face_swap_auth_rejected = asyncio.run(face_swap_submission_check())
    check(
        face_swap_auth_rejected
        and face_swap_job["mode"] == "image_face_swap"
        and face_swap_job["source_adherence_mode"] == "target_pixels_except_selected_face"
        and face_swap_job["face_swap"]["target_face_index"] == 1
        and face_swap_graph["1"]["inputs"]["image"] == "target.png"
        and face_swap_graph["2"]["inputs"]["image"] == "faces/target-2.png"
        and face_swap_graph["3"]["inputs"]["image"] == "faces/identity-1.png"
        and face_swap_graph["5"]["inputs"]["input_image"] == ["1", 0],
        "face-swap endpoint should enforce dual authorization records and submit the selected target/donor faces without diffusing the full target",
    )

    def face_extraction_check() -> tuple[dict[str, object], bool, bool]:
        if frontend.Image is None:
            return {}, False, False
        with tempfile.TemporaryDirectory(prefix="face_extraction_") as temp_name:
            root = Path(temp_name)
            input_dir = root / "input"
            input_dir.mkdir(parents=True)
            source_path = root / "authorized-source.png"
            frontend.Image.new("RGB", (640, 480), (225, 220, 210)).save(source_path)
            detected = [
                {
                    "box": {"x": 230, "y": 90, "width": 120, "height": 120},
                    "confidence": 1.0,
                }
            ]
            extraction_id = "face-self-check"
            with patch.object(frontend, "detect_face_boxes", return_value=detected):
                faces = frontend.extract_faces_to_input(
                    source_path,
                    {"input_dir": input_dir},
                    extraction_id=extraction_id,
                    crop_mode="head_shoulders",
                )
            candidate = faces[0]
            crop_path = input_dir / str(candidate["subfolder"]) / str(candidate["filename"])
            record = {
                "id": extraction_id,
                "created_at": frontend.now_ms(),
                "crop_mode": "head_shoulders",
                "authorization_confirmed": True,
                "original": {"filename": source_path.name, "type": "input"},
                "faces": faces,
            }
            with frontend.FACE_EXTRACTION_LOCK:
                frontend.FACE_EXTRACTIONS.clear()
            frontend.register_face_extraction(record)
            selected, selected_record = frontend.validated_face_extraction_candidate(
                extraction_id,
                0,
                str(candidate["filename"]),
                str(candidate["subfolder"]),
                str(candidate["type"]),
            )
            forged_rejected = False
            try:
                frontend.validated_face_extraction_candidate(
                    extraction_id,
                    0,
                    "forged.png",
                    str(candidate["subfolder"]),
                    str(candidate["type"]),
                )
            except frontend.HTTPException as exc:
                forged_rejected = exc.status_code == 400
            return selected_record, crop_path.is_file() and int(selected["height"]) > 120, forged_rejected

    face_record, face_crop_created, forged_face_rejected = face_extraction_check()
    check(
        frontend.Image is None
        or (
            face_record["authorization_confirmed"] is True
            and face_record["crop_mode"] == "head_shoulders"
            and face_crop_created
            and forged_face_rejected
        ),
        "authorized local face extraction should create a real ComfyUI input crop and reject forged candidate references",
    )

    async def face_authorization_guard_check() -> tuple[bool, bool]:
        endpoint_rejected = False
        generation_rejected = False
        try:
            await frontend.image_studio_face_extract(
                authorization_confirmed=False,
                crop_mode="face",
                source_image_filename="source.png",
                source_image_subfolder="image_studio",
                source_image_type="output",
                source_image=None,
            )
        except frontend.HTTPException as exc:
            endpoint_rejected = exc.status_code == 403

        async def fake_paths() -> dict[str, Path | str | bool]:
            return {
                "input_dir": ROOT / ".runtime" / "self-check-input",
                "output_dir": ROOT / ".runtime" / "self-check-output",
            }

        try:
            with patch.object(frontend, "active_comfy_paths", side_effect=fake_paths):
                await frontend.image_studio_generate(
                    prompt="保留构图并调整背景",
                    negative="bad",
                    prompt_mode="structured",
                    style_preset="none",
                    exact_text="",
                    profile="qwen2512_lightning_fp8",
                    aspect="custom",
                    width=512,
                    height=512,
                    steps=4,
                    cfg=1.0,
                    sampler="euler",
                    scheduler="simple",
                    batch_size=1,
                    generation_mode="batch",
                    seed="201",
                    edit_mode=True,
                    edit_operation="instruction",
                    edit_strength=0.65,
                    source_adherence=0.35,
                    edit_resize_mode="crop",
                    source_image_filename="face.png",
                    source_image_subfolder="beginner_frontend/face_extract",
                    source_image_type="input",
                    source_processing="face",
                    face_authorization_confirmed=False,
                    face_extract_id="face-self-check",
                    face_index=0,
                    face_crop_mode="head_shoulders",
                    nsfw=False,
                    nsfw_lora_strength=1.0,
                    source_image=None,
                )
        except frontend.HTTPException as exc:
            generation_rejected = exc.status_code == 403
        return endpoint_rejected, generation_rejected

    face_endpoint_rejected, face_generation_rejected = asyncio.run(face_authorization_guard_check())
    check(
        face_endpoint_rejected and face_generation_rejected,
        "face extraction and face-reference generation should both reject submissions without explicit authorization",
    )

    async def targeted_cancel_check() -> tuple[dict[str, object], list[tuple[str, dict[str, object]]]]:
        job = {
            "id": "self-check-cancel-image",
            "kind": "image_generation",
            "prompt_id": "cancel-1",
            "prompt_ids": ["cancel-1", "cancel-2"],
            "generation_mode": "sequential",
            "batch_size": 2,
            "status": "running",
            "completed": False,
            "created_at": 1,
            "media": [],
            "completed_prompt_ids": [],
            "failed_prompt_ids": [],
            "prompt_progress": {},
        }
        frontend.JOBS[job["id"]] = job
        queue_calls = 0
        posts: list[tuple[str, dict[str, object]]] = []

        async def fake_refresh(_job_id: str) -> dict[str, object]:
            return job

        async def fake_get(path: str) -> dict[str, object]:
            nonlocal queue_calls
            if path.startswith("/history/"):
                return {}
            if path != "/queue":
                raise AssertionError(path)
            queue_calls += 1
            if queue_calls == 1:
                return {
                    "queue_running": [[1, "cancel-1", {}, {}, []]],
                    "queue_pending": [[2, "cancel-2", {}, {}, []], [3, "other-job", {}, {}, []]],
                }
            if queue_calls == 2:
                return {
                    "queue_running": [[1, "cancel-1", {}, {}, []]],
                    "queue_pending": [[3, "other-job", {}, {}, []]],
                }
            return {"queue_running": [], "queue_pending": [[3, "other-job", {}, {}, []]]}

        async def fake_post(path: str, payload: dict[str, object]) -> dict[str, object]:
            posts.append((path, payload))
            return {}

        try:
            with patch.object(frontend, "refresh_generation_job", side_effect=fake_refresh), patch.object(
                frontend, "comfy_get", side_effect=fake_get
            ), patch.object(frontend, "comfy_post", side_effect=fake_post), patch.object(
                frontend, "persist_job_stores", return_value=None
            ), patch.object(frontend, "signal_generation_job", return_value=None):
                result = await frontend.cancel_generation_job(job["id"])
            return result, posts
        finally:
            frontend.JOBS.pop(job["id"], None)

    canceled_job, cancel_posts = asyncio.run(targeted_cancel_check())
    check(
        canceled_job["status"] == "canceled"
        and canceled_job["completed"] is True
        and ("/queue", {"delete": ["cancel-2"]}) in cancel_posts
        and any(path == "/interrupt" for path, _payload in cancel_posts)
        and all("other-job" not in str(payload) for _path, payload in cancel_posts),
        "targeted cancellation should delete only this job's pending prompts and interrupt only its running prompt",
    )

    async def vram_cleanup_check() -> tuple[dict[str, object], list[tuple[str, dict[str, object]]], dict[str, object], list[tuple[str, dict[str, object]]], dict[str, object]]:
        def make_job(job_id: str, prompt_id: str) -> dict[str, object]:
            return {
                "id": job_id,
                "kind": "image_generation",
                "prompt_id": prompt_id,
                "prompt_ids": [prompt_id],
                "status": "running",
                "completed": False,
                "created_at": 1,
                "media": [],
                "completed_prompt_ids": [],
                "failed_prompt_ids": [],
                "prompt_progress": {},
            }

        idle_job = make_job("self-check-vram-idle", "vram-idle")
        busy_job = make_job("self-check-vram-busy", "vram-busy")
        other_job = {
            "id": "self-check-vram-other",
            "kind": "video_generation",
            "prompt_id": "vram-other",
            "prompt_ids": ["vram-other"],
            "status": "running",
            "completed": False,
            "created_at": 1,
        }
        idle_posts: list[tuple[str, dict[str, object]]] = []
        busy_posts: list[tuple[str, dict[str, object]]] = []

        async def fake_history_get(path: str) -> dict[str, object]:
            if path.startswith("/history/"):
                prompt_id = path.rsplit("/", 1)[-1]
                return {
                    prompt_id: {
                        "status": {"status_str": "success", "completed": True, "messages": []},
                        "outputs": {},
                    }
                }
            if path == "/queue":
                return {"queue_running": [], "queue_pending": []}
            raise AssertionError(path)

        async def fake_idle_post(path: str, payload: dict[str, object]) -> dict[str, object]:
            idle_posts.append((path, payload))
            return {}

        async def fake_busy_post(path: str, payload: dict[str, object]) -> dict[str, object]:
            busy_posts.append((path, payload))
            return {}

        frontend.JOBS[idle_job["id"]] = idle_job
        try:
            with patch.object(frontend, "comfy_get", side_effect=fake_history_get), patch.object(
                frontend, "comfy_post", side_effect=fake_idle_post
            ), patch.object(frontend, "persist_job_stores", return_value=None):
                idle_result = await frontend.refresh_generation_job(idle_job["id"])
                idle_again = await frontend.refresh_generation_job(idle_job["id"])
            frontend.JOBS[busy_job["id"]] = busy_job
            frontend.JOBS[other_job["id"]] = other_job
            with patch.object(frontend, "comfy_get", side_effect=fake_history_get), patch.object(
                frontend, "comfy_post", side_effect=fake_busy_post
            ), patch.object(frontend, "persist_job_stores", return_value=None):
                busy_result = await frontend.refresh_generation_job(busy_job["id"])
            return idle_result, idle_posts, busy_result, busy_posts, idle_again
        finally:
            frontend.JOBS.pop(idle_job["id"], None)
            frontend.JOBS.pop(busy_job["id"], None)
            frontend.JOBS.pop(other_job["id"], None)

    idle_vram_job, idle_vram_posts, busy_vram_job, busy_vram_posts, idle_vram_again = asyncio.run(vram_cleanup_check())
    check(
        idle_vram_job["status"] == "success"
        and idle_vram_job.get("vram_cleanup", {}).get("status") == "skipped"
        and idle_vram_job.get("vram_cleanup", {}).get("reason") == "disabled"
        and idle_vram_posts.count(("/free", {"unload_models": True, "free_memory": True})) == 0
        and idle_vram_again.get("vram_cleanup", {}).get("status") == "skipped"
        and idle_vram_again.get("vram_cleanup", {}).get("reason") == "disabled"
        and busy_vram_job.get("vram_cleanup", {}).get("status") == "skipped"
        and busy_vram_job.get("vram_cleanup", {}).get("reason") == "disabled"
        and not any(path == "/free" for path, _payload in busy_vram_posts),
        "finished generation jobs skip ComfyUI model unload by default",
    )

    async def selected_history_delete_check() -> tuple[dict[str, object], bool, bool]:
        with tempfile.TemporaryDirectory(prefix="image_history_delete_") as temp_name:
            base = Path(temp_name)
            output_dir = base / "output"
            image_dir = output_dir / "image_studio"
            image_dir.mkdir(parents=True)
            image_path = image_dir / "delete-me.png"
            image_path.write_bytes(b"png")
            paths = {
                "base_dir": str(base),
                "input_dir": str(base / "input"),
                "output_dir": str(output_dir),
                "temp_dir": str(base / "temp"),
            }
            job_id = "self-check-delete-image"
            frontend.JOBS[job_id] = {
                "id": job_id,
                "kind": "image_generation",
                "status": "success",
                "completed": True,
                "created_at": 1,
                "media": [
                    {
                        "kind": "image",
                        "filename": image_path.name,
                        "subfolder": "image_studio",
                        "type": "output",
                    }
                ],
            }

            async def fake_paths() -> dict[str, str]:
                return paths

            try:
                with patch.object(frontend, "active_comfy_paths", side_effect=fake_paths), patch.object(
                    frontend, "persist_job_stores", return_value=None
                ):
                    result = await frontend.delete_image_studio_history(
                        {
                            "limit": "not-a-number",
                            "items": [
                                {
                                    "job_id": job_id,
                                    "filename": image_path.name,
                                    "subfolder": "image_studio",
                                    "type": "output",
                                }
                            ]
                        }
                    )
                return result, image_path.exists(), job_id in frontend.JOBS
            finally:
                frontend.JOBS.pop(job_id, None)

    delete_result, deleted_file_exists, deleted_job_exists = asyncio.run(selected_history_delete_check())
    check(
        delete_result["removed"] == 1
        and isinstance(delete_result["history"], list)
        and not deleted_file_exists
        and not deleted_job_exists,
        "selected image history deletion should remove its file and tolerate a malformed history limit",
    )
    launcher_text = (ROOT / "START_WORKFLOW.py").read_text(encoding="utf-8")
    parent_start_py = ROOT.parent / "START.py"
    if parent_start_py.exists():
        parent_text = parent_start_py.read_text(encoding="utf-8")
        check(
            'APP_DIR_NAME = "video creat"' in parent_text
            and "START_WORKFLOW.py" in parent_text
            and "beginner_frontend" in parent_text
            and "ComfyUI" in parent_text
            and "r18-studio" not in parent_text,
            "workspace-root START.py must launch video creat instead of the parent ComfyUI venv or r18-studio",
        )
        for name in ("START.bat", "START.ps1", "START.command", "启动.bat"):
            path = ROOT.parent / name
            check(path.exists(), f"workspace-root {name} is missing")
            if name.endswith(".bat"):
                data = path.read_bytes()
                check(not data.startswith(b"\xef\xbb\xbf"), f"workspace-root {name} must not have a UTF-8 BOM")
                check(data.startswith(b"@echo off"), f"workspace-root {name} must start with @echo off")
                check(b"\n" not in data.replace(b"\r\n", b""), f"workspace-root {name} must use CRLF line endings")
                try:
                    text = data.decode("ascii")
                except UnicodeDecodeError as exc:
                    check(False, f"workspace-root {name} must be ASCII for cmd.exe: {exc}")
                    continue
            else:
                text = path.read_text(encoding="utf-8")
            if name == "启动.bat":
                check("START.bat" in text, "workspace-root 启动.bat must delegate to START.bat")
            else:
                check(
                    "video creat" in text and "START_WORKFLOW" in text,
                    f"workspace-root {name} must delegate to video creat\\START_WORKFLOW",
                )
            if name == "START.bat":
                check(
                    "START_WORKFLOW.ps1" in text
                    and "pause" in text
                    and "wscript" not in text.lower(),
                    "workspace-root START.bat must keep a visible console instead of the silent VBS path",
                )
    check(r".\START_WORKFLOW.bat" in launcher_text, "Windows Python help should point beginners to START_WORKFLOW.bat")
    check('argv[0] == "--check"' in launcher_text, "Python launcher should support --check without starting the server")
    check("def print_usage()" in launcher_text and '"--help"' in launcher_text, "Python launcher should support --help without starting the server")
    check("--no-browser" in launcher_text and "Ready:" in launcher_text, "Python launcher should support headless frontend startup for clean bootstrap smoke")
    check(
        "def stop_stale_frontend" in launcher_text and "taskkill" in launcher_text,
        "launcher should stop a stale frontend before binding the fixed port",
    )
    check("--accept-package-agreements" in launcher_text, "Python launcher help should include winget agreement flags")
    check("https://www.python.org/downloads/windows/" in launcher_text, "Python launcher should include official Windows Python download fallback")
    check("frontend dependency setup failed" in launcher_text, "Python launcher should explain frontend dependency failures")
    check(
        "bootstrap_subprocess_env" in launcher_text and "PIP_INDEX_URL" in launcher_text and "proxy_url" in launcher_text,
        "launcher should reuse saved proxy and pip mirror settings when installing frontend dependencies",
    )
    check(
        "--set-pip-index" in launcher_text and "--set-proxy" in launcher_text and "--show-download-settings" in launcher_text,
        "launcher should expose pre-frontend download setting commands for first-run pip failures",
    )
    check(
        "ensure_pip_available" in launcher_text and "ensurepip" in launcher_text and "run_pip" in launcher_text,
        "launcher should repair missing pip and retry frontend dependency installs",
    )
    check(
        "offer_frontend_dependency_retry" in launcher_text and "保存网络设置并立即重试" in launcher_text,
        "launcher should offer an interactive pip mirror/proxy rescue before the frontend can open",
    )
    launcher_pip_calls: list[list[str]] = []

    def flaky_launcher_pip(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        launcher_pip_calls.append(command)
        if len(launcher_pip_calls) == 1:
            raise subprocess.CalledProcessError(1, command)
        return subprocess.CompletedProcess(command, 0, "", "")

    with patch.object(launcher.subprocess, "run", side_effect=flaky_launcher_pip), patch.object(launcher.time, "sleep", return_value=None):
        launcher.run_pip([str(Path("python")), "-m", "pip", "install", "fastapi"], env={})
    check(len(launcher_pip_calls) == 2, "launcher pip installs should retry after a transient failure")
    with tempfile.TemporaryDirectory(prefix="launcher_download_settings_") as temp_name:
        config_path = Path(temp_name) / ".local_ai_workbench_config.json"
        with patch.object(launcher, "LOCAL_CONFIG_FILE", config_path), patch.object(launcher, "LEGACY_LOCAL_CONFIG_FILES", ()):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = launcher.handle_download_settings_cli(
                    [
                        "--set-pip-index",
                        "https://pypi.example/simple",
                        "--set-proxy",
                        "http://user:secret@127.0.0.1:7890",
                    ]
                )
            saved_config = launcher.read_local_config()
            check(result == 0, "launcher download setting command should succeed")
            check(saved_config.get("pip_index_url") == "https://pypi.example/simple", "launcher should save pip mirror before frontend dependencies install")
            check(saved_config.get("proxy_url") == "http://user:secret@127.0.0.1:7890", "launcher should save proxy before frontend dependencies install")
            check("secret" not in output.getvalue() and "***:***@127.0.0.1:7890" in output.getvalue(), "launcher should redact proxy credentials when showing settings")
            with contextlib.redirect_stdout(io.StringIO()):
                result = launcher.handle_download_settings_cli(["--clear-download-settings"])
            check(result == 0 and json.loads(config_path.read_text(encoding="utf-8")) == {}, "launcher should clear saved download settings")
            output = io.StringIO()
            with patch.object(launcher, "stdin_is_interactive", return_value=True), patch(
                "builtins.input",
                side_effect=["Y", "https://pypi.retry/simple", "http://user:secret@127.0.0.1:7890"],
            ), contextlib.redirect_stdout(output):
                should_retry = launcher.offer_frontend_dependency_retry(RuntimeError("pip failed"))
            saved_config = launcher.read_local_config()
            check(should_retry is True, "launcher interactive dependency rescue should retry after saving settings")
            check(saved_config.get("pip_index_url") == "https://pypi.retry/simple", "launcher interactive rescue should save pip mirror")
            check(saved_config.get("proxy_url") == "http://user:secret@127.0.0.1:7890", "launcher interactive rescue should save proxy")
            check("secret" not in output.getvalue() and "***:***@127.0.0.1:7890" in output.getvalue(), "launcher interactive rescue should redact proxy credentials")
    ps1_text = (ROOT / "START_WORKFLOW.ps1").read_text(encoding="utf-8")
    vbs_text = (ROOT / "START_WORKFLOW.vbs").read_text(encoding="utf-8")
    command_text = (ROOT / "START_WORKFLOW.command").read_text(encoding="utf-8")
    bat_text = (ROOT / "START_WORKFLOW.bat").read_text(encoding="utf-8")
    release_smoke_text = (ROOT / "scripts" / "release_smoke.py").read_text(encoding="utf-8")
    clean_bootstrap_text = (ROOT / "scripts" / "clean_bootstrap_smoke.py").read_text(encoding="utf-8")
    prerequisite_text = (ROOT / "scripts" / "prerequisite_doctor.py").read_text(encoding="utf-8")
    requirements_text = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    requirements_lock_text = (ROOT / "requirements.lock").read_text(encoding="utf-8")
    requirement_lines = {line.split(">=", 1)[0]: line for line in requirements_text.splitlines() if ">=" in line}
    for dependency in ("fastapi", "httpx", "imageio-ffmpeg", "python-multipart", "uvicorn[standard]"):
        check("<1.0" in requirement_lines.get(dependency, ""), f"{dependency} should have a conservative upper bound for first-run stability")
    for dependency, upper_bound in {
        "numpy": "<3.0",
        "opencv-python-headless": "<5.0",
        "Pillow": "<13.0",
        "websockets": "<17",
    }.items():
        check(upper_bound in requirement_lines.get(dependency, ""), f"{dependency} should have a conservative upper bound")
    check(
        "numpy==2.2.6" in requirements_lock_text,
        "frontend lock must pin a NumPy release compatible with the supported Python 3.10-3.12 range",
    )
    check(
        "FRONTEND_REQUIRED_MODULES" in launcher_text and '"cv2"' in launcher_text and '"PIL"' in launcher_text,
        "launcher should select a frontend Python that can perform local face extraction",
    )
    check(
        '"Pillow": "PIL"' in prerequisite_text and '"OpenCV": "cv2"' in prerequisite_text,
        "prerequisite doctor should diagnose local image and face-processing dependencies",
    )
    check("reconfigure" in prerequisite_text and 'encoding="utf-8"' in prerequisite_text, "prerequisite doctor should force UTF-8 CLI output on Windows")
    check("reconfigure" in release_smoke_text and 'encoding="utf-8"' in release_smoke_text, "release smoke should force UTF-8 CLI output and subprocess decoding")
    check("START_WORKFLOW.ps1 OK" in ps1_text and "@scriptArgs" in ps1_text, "PowerShell launcher should support --check and forward script args")
    check("$pythonCommand = @(Find-Python)" in ps1_text, "PowerShell launcher should preserve a single Python path with spaces as one array item")
    check("--help" in ps1_text and "Beginner path" in ps1_text, "PowerShell launcher should support --help without bootstrapping Python")
    check("--no-browser" in ps1_text, "PowerShell launcher help should expose headless startup")
    check("--set-hf-endpoint" in ps1_text and "--set-pip-index" in ps1_text and "--show-download-settings" in ps1_text, "PowerShell help should expose pre-frontend download settings")
    check("$launcher @scriptArgs" in ps1_text, "PowerShell launcher should pass START_WORKFLOW.py before script args")
    check("--accept-source-agreements" in ps1_text and "Install-PythonWithWinget" in ps1_text, "PowerShell launcher should install Python with winget agreement flags and fallback")
    check("Open-PythonDownloadPage" in ps1_text and "https://www.python.org/downloads/windows/" in ps1_text, "PowerShell launcher should offer a no-winget Python download fallback")
    check(
        "WindowStyle Hidden" in vbs_text and "shell.Run command, 0, False" in vbs_text,
        "Windows double-click launcher should detach without a visible terminal",
    )
    check('"$@"' in command_text and "START_WORKFLOW.command OK" in command_text, "macOS launcher should support --check and forward args")
    check("--help" in command_text and "Beginner path" in command_text, "macOS launcher should support --help without bootstrapping Python")
    check("--no-browser" in command_text, "macOS launcher help should expose headless startup")
    check("--set-hf-endpoint" in command_text and "--set-pip-index" in command_text and "--show-download-settings" in command_text, "macOS help should expose pre-frontend download settings")
    check("/opt/homebrew/bin/python3.12" in command_text and "bash ./START_WORKFLOW.command" in command_text, "macOS launcher should check common Homebrew/Python paths and explain bash fallback")
    check("HOMEBREW_INSTALL_URL" in command_text and "load_homebrew_path" in command_text, "macOS launcher should offer a Homebrew/Python bootstrap path")
    check("open \"$PYTHON_DOWNLOAD_URL\"" in command_text, "macOS launcher should offer the official Python download page when package managers are unavailable")
    check('START_WORKFLOW.ps1" %*' in bat_text, "Windows batch launcher should forward args to PowerShell")
    check("START_WORKFLOW.vbs" in bat_text and "wscript.exe //nologo" in bat_text, "Windows batch launcher should use the silent double-click path")
    check("--help" in bat_text and "Beginner path" in bat_text, "Windows batch launcher should support --help without starting PowerShell")
    check("--no-browser" in bat_text, "Windows batch launcher help should expose headless startup")
    check("--set-hf-endpoint" in bat_text and "--set-pip-index" in bat_text and "--show-download-settings" in bat_text, "Windows batch help should expose pre-frontend download settings")
    check("--accept-package-agreements" in bat_text, "Windows batch fallback should include winget agreement flags")
    check("https://www.python.org/downloads/windows/" in bat_text, "Windows batch launcher should print the official Python download page")
    check("START_WORKFLOW.bat" in release_smoke_text and "start_beginner_frontend.ps1" in release_smoke_text, "release smoke should cover packaged Windows launchers")
    check("START_WORKFLOW.py\", \"--no-browser\"" in clean_bootstrap_text and "created_venv" in clean_bootstrap_text, "clean bootstrap smoke should verify no-venv first-run frontend startup")
    check("taskkill" in clean_bootstrap_text and '"/T"' in clean_bootstrap_text, "clean bootstrap smoke should terminate the Windows frontend process tree")
    check("prerequisites_have_python_download_fallback" in release_smoke_text, "release smoke should verify package-manager-free Python fallback commands")
    check("run_install_profile_matrix" in release_smoke_text and "mac_wan5b_excludes_a14b" in release_smoke_text, "release smoke should verify all beginner install profiles")
    check("full_setup_dry_run_ok" in release_smoke_text and "/api/bootstrap/full-setup" in release_smoke_text, "release smoke should cover one-click full setup dry-run")
    check("video_smoke_disconnected_guidance" in release_smoke_text and "post_json_expect_error" in release_smoke_text, "release smoke should verify beginner guidance when ComfyUI is disconnected")
    frontend_js_text = (ROOT / "beginner_frontend" / "static" / "app.js").read_text(encoding="utf-8")
    index_text = (ROOT / "beginner_frontend" / "static" / "index.html").read_text(encoding="utf-8")
    check("ComfyUI 已运行" in frontend_js_text, "bootstrap UI should disable start button when ComfyUI is already running")
    check("先安装 ComfyUI" in frontend_js_text, "bootstrap UI should guide beginners to install before starting")
    check("/api/diagnostics" in frontend_js_text, "frontend should expose copyable diagnostics")
    check("prerequisiteChecks" in frontend_js_text, "frontend should render first-run prerequisite checks")
    check("startSelfTest" in frontend_js_text and "/api/self-test" in frontend_js_text, "frontend should expose one-click self-test")
    check("startFullSetup" in frontend_js_text and "/api/bootstrap/full-setup" in frontend_js_text, "frontend should expose one-click full environment setup")
    check(
        "updateFullSetupAvailability" in frontend_js_text
        and "正在刷新当前档位安装计划" in frontend_js_text
        and "安装计划刷新失败，请重新侦测后再一键准备" in frontend_js_text,
        "full setup button should follow selected install profile disk preflight",
    )
    check(
        "async function loadInstallPlan" in frontend_js_text
        and "setFullSetupConfirming(false);\n  setWorkflowAssetInstallConfirming(false);" in frontend_js_text,
        "profile changes and environment refresh should clear stale install confirmations",
    )
    check("PyTorch 下载源" in frontend_js_text, "full setup confirmation should mention download-source network preflight")
    check(
        "跳过源码版安装/更新" in frontend_js_text and "currentModelDownloadPath" in frontend_js_text,
        "full setup confirmation should explain running ComfyUI and selected model directory behavior",
    )
    check(
        "一键准备环境启动失败" in frontend_js_text
        and "一键准备环境轮询失败" in frontend_js_text
        and frontend_js_text.count("await loadEnvironment(") >= 5,
        "full setup failure paths should reload environment state so buttons recover",
    )
    check("startVideoSmokeTest" in frontend_js_text and "/api/video-smoke-test" in frontend_js_text, "frontend should expose one-click real generation smoke test")
    check(
        "new EventSource" in frontend_js_text
        and "ACTIVE_JOB_STORAGE_KEY" in frontend_js_text
        and "startJobPollingFallback" in frontend_js_text,
        "generation jobs should use SSE with polling and reload recovery fallbacks",
    )
    check("detail.actions" in frontend_js_text and "下一步：" in frontend_js_text, "frontend should render structured API recovery actions")
    check("formatJobFailureHint" in frontend_js_text, "frontend should render structured install failure hints")
    check("installPlanRequestId" in frontend_js_text, "install plan refresh should ignore stale responses")
    check("浏览器阻止剪贴板写入" in frontend_js_text, "diagnostics copy should fall back when clipboard is blocked")
    check(
        "allowDefaultKeyframe" not in frontend_js_text
        and "内置示例图" not in frontend_js_text
        and "switchImageModelsToTextVideo" in frontend_js_text,
        "keyframe step should be optional and must not fall back to a built-in sample image",
    )
    check('if (stepId === "keyframe") stepId = "draft";' in frontend_js_text,
          "legacy keyframe entry should open generation directly without a confirmation gate")
    check(
        "switchTextModelsToImageVideo" in frontend_js_text
        and "capabilityCounterpart" in frontend_js_text
        and '"image_to_video"' in frontend_js_text,
        "uploaded keyframes should activate the selected engine's capability-matched I2V route",
    )
    check(
        "optionCapabilities" in frontend_js_text
        and "capabilityCounterpart" in frontend_js_text
        and "pairedId" not in frontend_js_text
        and "targetModes" not in frontend_js_text,
        "model switching should be capability-driven instead of hardcoding model-specific T2V/I2V pairs",
    )
    check(
        "renderModelPresets" in frontend_js_text
        and "alignedFrameCount" in frontend_js_text
        and "syncCatalogSelectionForWorkflowOption" in frontend_js_text
        and 'id="mode" name="mode" type="hidden" value=""' in index_text,
        "video model changes should synchronize catalog/install context and render model-specific size and duration presets",
    )
    check(
        'data-view="environment">环境与模型' in index_text
        and 'class="view view-environment"' in index_text
        and 'id="enterWorkflowButton"' in index_text,
        "first launch should start with environment detection and an explicit continue action",
    )
    frontend_py_text = (ROOT / "beginner_frontend" / "app.py").read_text(encoding="utf-8")
    check('@app.get("/api/diagnostics")' in frontend_py_text, "backend diagnostics endpoint missing")
    check('@app.get("/api/prerequisites")' in frontend_py_text, "backend prerequisites endpoint missing")
    check('@app.post("/api/self-test")' in frontend_py_text, "backend self-test endpoint missing")
    check('@app.post("/api/bootstrap/full-setup")' in frontend_py_text, "backend full setup endpoint missing")
    check("run_full_setup_worker" in frontend_py_text and "dry_run" in frontend_py_text, "backend should orchestrate full setup with dry-run support")
    check(
        "skip_comfy_install" in frontend_py_text
        and "source_install_skipped" in frontend_py_text
        and "use_local_comfy_python" in frontend_py_text
        and "running_main_py == local_main_py" in frontend_py_text
        and "bool(runtime.get(\"source_ready\"))" in frontend_py_text,
        "full setup should skip source install and reuse the right Python for running or detected ComfyUI runtimes",
    )
    check(
        "def run_json_command" in frontend_py_text
        and 'encoding="utf-8"' in frontend_py_text
        and 'errors="replace"' in frontend_py_text,
        "backend subprocess capture should decode UTF-8 CLI output for self-test",
    )
    check('@app.post("/api/video-smoke-test")' in frontend_py_text, "backend video smoke-test endpoint missing")
    check(
        '@app.get("/api/jobs/{job_id}/events")' in frontend_py_text
        and "StreamingResponse" in frontend_py_text
        and "refresh_generation_job" in frontend_py_text,
        "backend should stream generation state and share one resilient refresh path",
    )
    check(
        "def comfy_http_client" in frontend_py_text
        and "trust_env=False" in frontend_py_text
        and "proxy=None" in frontend_py_text,
        "ComfyUI HTTP and WebSocket control traffic should bypass download and system proxies",
    )
    check(
        "JOB_STORE_PATH" in frontend_py_text
        and "load_persisted_job_stores" in frontend_py_text
        and "JOB_LOST_AFTER_MS" in frontend_py_text,
        "generation and install job history should survive frontend restarts",
    )
    check(
        "get_comfy_object_info" in frontend_py_text
        and "cached_hardware_probe" in frontend_py_text
        and "catalog_file_index" in frontend_py_text,
        "environment detection should cache heavy ComfyUI, hardware, and filesystem probes",
    )
    check(
        "queue_local_video_job" in frontend_py_text
        and "run_local_video_worker" in frontend_py_text
        and "run_ffmpeg_with_progress" in frontend_py_text,
        "stitch and deflicker should run as background jobs with progress",
    )
    check("graph_node_schema_errors" in frontend_py_text and "build_ltx23_i2v_prompt" in frontend_py_text, "LTX 2.3 I2V and node-contract validation should be wired into the backend")
    check(
        "build_minimax_h3_prompt" in frontend_py_text
        and "normalize_minimax_h3_frames" in frontend_py_text
        and "MiniMaxH3SigmaShift" in frontend_py_text,
        "MiniMax H3 native graph and frame normalization should be wired into the backend",
    )
    check("choose_video_smoke_option" in frontend_py_text and "VIDEO_SMOKE_PRIORITY" in frontend_py_text, "backend should choose a conservative smoke-test model")
    check(
        "COMFY_START_JOB_ID" in frontend_py_text
        and "wait_for_comfyui_ready_worker" in frontend_py_text
        and "ComfyUI 已就绪" in frontend_py_text,
        "start ComfyUI job should complete when /system_stats becomes ready instead of waiting for process exit",
    )
    check("comfy_not_connected_detail" in frontend_py_text and "一键准备环境" in frontend_py_text, "ComfyUI connection failures should include beginner recovery actions")
    check(
        '"--base-dir"' in frontend_py_text and '"--install-dir"' in frontend_py_text and "prerequisite_doctor.py" in frontend_py_text,
        "self-test prerequisite doctor should use the same base/install dirs as the frontend",
    )
    check(
        "def comfy_runtime_info" in frontend_py_text
        and "desktop_runtime" in frontend_py_text
        and "bundled_comfy_main_py" in frontend_py_text
        and "runtime_source_ready" in frontend_py_text
        and "desktop_available" in frontend_py_text,
        "frontend should detect source ComfyUI, ComfyUI Desktop bundled runtime, and Desktop app fallback",
    )
    check(
        "looks_like_comfy_base" in prerequisite_text
        and "default_base_dir" in prerequisite_text
        and "workspace.parent" in prerequisite_text,
        "prerequisite doctor should use the same parent-ComfyUI base discovery as the launcher/frontend",
    )
    check(
        "desktop_comfy_main_candidates" in prerequisite_text
        and "looks_like_comfy_desktop_runtime" in prerequisite_text
        and "runtime\": \"desktop\"" in prerequisite_text,
        "prerequisite doctor should treat ComfyUI Desktop/runtime directories as usable instead of blocking them",
    )
    check('install_profile == "cuda-wan5b"' in frontend_py_text, "validate should cover cuda-wan5b workflows")
    check(
        '"i2v_a14b": "cuda-a14b"' in frontend_py_text
        and '"t2v_a14b": "cuda-a14b"' in frontend_py_text
        and 'install_profile in {"cuda-full", "cuda-a14b"}' in frontend_py_text,
        "A14B generate-page install and smoke graphs must use cuda-a14b instead of the cuda-full warehouse",
    )
    styles_text = (ROOT / "beginner_frontend" / "static" / "styles.css").read_text(encoding="utf-8")
    image_studio_js_text = (ROOT / "beginner_frontend" / "static" / "image-studio.js").read_text(encoding="utf-8")
    download_center_js_text = (ROOT / "beginner_frontend" / "static" / "download-center.js").read_text(encoding="utf-8")
    check(
        'data-view="download-center"' in index_text
        and 'id="downloadTransferList"' in index_text
        and 'id="downloadResourceList"' in index_text
        and "/api/download-center" in download_center_js_text
        and "data-download-action" in download_center_js_text
        and "PAGE_SIZE = 20" in download_center_js_text
        and "download-center-page" in styles_text
        and '@app.get("/api/download-center")' in frontend_py_text,
        "frontend should expose a standalone download center with task controls and paginated local resources",
    )
    check(
        "data-catalog-install" in frontend_js_text
        and "showInstallInDownloadCenter" in frontend_js_text
        and "正在为 ${label} 创建下载任务" in frontend_js_text,
        "model catalog actions should start a download directly and route to the download center",
    )
    check(
        "/api/download-center/resume" in download_center_js_text
        and "data-resume-partial" in download_center_js_text
        and '@app.post("/api/download-center/resume")' in frontend_py_text
        and '"--asset-id"' in (ROOT / "scripts" / "install_workflow_assets.py").read_text(encoding="utf-8"),
        "managed .part files should expose targeted one-click resume without reinstalling a full profile",
    )
    check(
        "imageQualityPresets" in index_text
        and "imageStepsRange" in index_text
        and "qualityStepPresets" in image_studio_js_text
        and "previewQualityInput" in image_studio_js_text,
        "image studio should expose quality presets plus free integer step selection",
    )
    check(
        "无限制模式" in index_text and "成人内容模式" not in index_text,
        "image studio should use the unrestricted-mode label consistently",
    )
    check(
        'id="videoUnrestrictedToggle"' in index_text
        and "renderVideoUnrestricted" in frontend_js_text
        and "wan22-i2v-unrestricted-addon" in frontend_py_text,
        "video workflow should expose the model-scoped Wan I2V unrestricted add-on state",
    )
    check(
        '@app.post("/api/image-studio/handoff")' in frontend_py_text
        and "source_image_filename" in frontend_py_text
        and "acceptImageStudioKeyframe" in frontend_js_text
        and "/api/image-studio/handoff" in image_studio_js_text
        and "DataTransfer" not in image_studio_js_text,
        "image-to-video handoff should use a persistent ComfyUI input reference instead of a browser-only file shim",
    )
    check(
        'id="topModelContext"' in index_text
        and 'refs.viewTab?.classList.contains("active")' in image_studio_js_text
        and "refs.topModel.textContent = profile.label" in image_studio_js_text
        and re.search(r'!\[[^\]]*"image-studio"[^\]]*"video-face-swap"[^\]]*\]\.includes\(activeView\)', frontend_js_text),
        "image and video face-swap workspaces should own the header model label while active",
    )
    check(
        "imageOutputPathButton" in index_text
        and "imageOutputSubdir" in index_text
        and "/api/image-studio/output/open" in image_studio_js_text
        and "saveOutputLocation" in image_studio_js_text,
        "image studio should show, configure, and open its system output directory",
    )
    check(
        'id="imageBatchSize"' in index_text
        and 'max="20"' in index_text
        and 'name="generation_mode"' in index_text
        and "逐张出图" in index_text
        and "imageProgressPercent" in index_text,
        "image studio should expose a custom image count, sequential output mode, and numeric progress",
    )
    check(
        'id="imageTaskModeSwitch"' in index_text
        and 'id="imageEditFile"' in index_text
        and 'id="imageEditStrengthRange"' in index_text
        and 'id="imageEditFollowSize"' in index_text
        and 'id="imageEditResultButton"' in index_text
        and "useMediaForEdit" in image_studio_js_text
        and "data-history-edit" in image_studio_js_text
        and "source_image_filename" in frontend_py_text
        and "IMAGE_EDIT_SOURCE_PLACEHOLDER" in frontend_py_text,
        "image studio should expose upload/history image editing with source-size, strength, and iterative-edit controls",
    )
    check(
        'id="imageEditOperationSwitch"' in index_text
        and 'id="imageFaceCandidates"' in index_text
        and 'id="imageIdentityFaceFile"' in index_text
        and 'id="imageIdentityFaceCandidates"' in index_text
        and 'id="imageFaceSwapStrengthRange"' in index_text
        and 'id="imageFaceAuthModal"' in index_text
        and 'id="imageFaceAuthCheckbox"' in index_text
        and "/api/image-studio/face-extract" in image_studio_js_text
        and "/api/image-studio/face-swap" in image_studio_js_text
        and "selectFaceCandidate" in image_studio_js_text
        and "faceAuthorizationConfirmed" in image_studio_js_text
        and "FACE_SWAP_AUTHORIZATION_STATEMENT" in frontend_py_text
        and "validated_face_extraction" in frontend_py_text
        and "build_face_swap_prompt" in frontend_py_text,
        "image editing should offer authorized local target/donor face selection and a real face-swap workflow",
    )
    check(
        'name="source_adherence"' in index_text
        and 'id="imageEditAdherenceStatus"' in index_text
        and "normalize_image_edit_controls" in frontend_py_text
        and "source_adherence_mode" in frontend_py_text
        and "numeric_inverse_denoise" in image_studio_js_text,
        "image editing should expose and diagnose model-specific original-image adherence",
    )
    check(
        "apply_comfy_progress_event" in frontend_py_text
        and "ensure_comfy_progress_listener" in frontend_py_text
        and 'generation_mode: str = Form("batch")' in frontend_py_text
        and "refresh_multi_prompt_image_job" in frontend_py_text,
        "image generation should use ComfyUI progress events and aggregate sequential prompt jobs",
    )
    check(
        'status === "queued" ? "18%"' not in image_studio_js_text
        and "job.progress?.label" in image_studio_js_text
        and "media.length" in image_studio_js_text
        and "下载全部图片" in index_text,
        "image studio should render real progress, partial results, and explicit download actions",
    )
    check(
        'id="imageTaskQueueList"' in index_text
        and 'id="imageCancelJobButton"' in index_text
        and 'id="imageHistorySelectAll"' in index_text
        and 'id="imageHistoryDeleteButton"' in index_text
        and 'class="image-studio-workspace"' in index_text
        and 'id="imageHistoryPagination"' in index_text
        and 'id="imageHistoryPageNumbers"' in index_text
        and "/api/jobs/${encodeURIComponent(jobId)}/cancel" in image_studio_js_text
        and "/api/image-studio/history/delete" in image_studio_js_text
        and "/api/image-studio/history?${params}" in image_studio_js_text
        and "HISTORY_PAGE_SIZE = 20" in image_studio_js_text
        and "image_studio_job_history_page" in frontend_py_text
        and "image_studio_history_records" in frontend_py_text
        and "history_entry_id" in frontend_py_text
        and "BEGINNER_FRONTEND_MAX_COMPLETED_JOBS" in frontend_py_text
        and "activeJobIds" in image_studio_js_text,
        "image studio should support bounded sticky layout, paginated history, concurrent task tracking, targeted cancellation, and selected deletion",
    )
    check(
        'id="imageNsfwStrengthRange"' in index_text
        and 'id="videoUnrestrictedStrengthRange"' in index_text
        and "strength_recommended" in frontend_py_text
        and "明确成年人" not in frontend_py_text
        and "明确成年人" not in frontend_js_text
        and "明确成年人" not in image_studio_js_text
        and "chaotic background, NSFW" not in frontend_py_text
        and "chaotic background, NSFW" not in frontend_js_text,
        "unrestricted controls should expose model-specific strength ranges without injecting adult-policy prose",
    )
    check(
        "/api/nsfw-playbook" in frontend_py_text
        and "/api/character-box" in frontend_py_text
        and "/api/nsfw-extensions/capabilities" in frontend_py_text
        and "/api/video/face-swap" in frontend_py_text
        and "/api/video/extract-frame" in frontend_py_text
        and 'id="imageNsfwScenes"' in index_text
        and 'id="imageAdultRecipeChips"' in index_text
        and 'id="videoAdultRecipeChips"' in index_text
        and 'id="videoNsfwExtras"' in index_text
        and 'id="imageTripleCompare"' in index_text
        and "videoPlaybook" in frontend_js_text
        and "applyAdultPlaybookVideo" in frontend_js_text
        and "hasVideoKeyframe" in frontend_js_text
        and "queueVideoFromKeyframe" in frontend_js_text
        and "stripPromptClause" in frontend_js_text
        and "promptDerivedFrom" in frontend_js_text
        and "left.startsWith(right)" not in frontend_js_text
        and 'setStep("draft", { refresh: false })' in frontend_js_text
        and "replacedPrompt" in frontend_js_text
        and "replacePrompt" in frontend_js_text
        and "已切回文生图再套玩法" in image_studio_js_text
        and "已取消自动出视频" in image_studio_js_text
        and "const busy = Boolean(pendingStillToVideo);" in image_studio_js_text
        and "maybeQueueVideoAfterStill" in image_studio_js_text
        and 'id="imageAdultApplyVideoButton"' in index_text
        and 'id="imageStillToVideoButton"' in index_text
        and re.search(r'/static/image-studio\.js\?(?:v|build)=[^"\s]+', index_text)
        and "本页可生成" in frontend_js_text
        and "只下载、去 ComfyUI 跑模板" in frontend_js_text
        and "仅目录参考" in frontend_js_text
        and "include_post" in frontend_js_text
        and "finishCatalogInstall" in frontend_js_text
        and "goGenerateFromCatalog" in frontend_js_text
        and "selectWorkflowOptionForCatalog" in frontend_js_text
        and "downloadCenterGoGenerate" in index_text
        and "applyCatalogImageSelection" in image_studio_js_text
        and "支持直接下载" not in frontend_js_text
        and "--skip-post" in (ROOT / "scripts" / "install_workflow_assets.py").read_text(encoding="utf-8")
        and "confirm_requirement" in frontend_py_text
        and "preferred_video_models" in (ROOT / "beginner_frontend" / "nsfw_playbook.py").read_text(encoding="utf-8")
        and "undress_slow" in (ROOT / "beginner_frontend" / "nsfw_playbook.py").read_text(encoding="utf-8")
        and "bedroom_lamp" in (ROOT / "beginner_frontend" / "nsfw_playbook.py").read_text(encoding="utf-8")
        and "服装细节保持一致" not in (ROOT / "beginner_frontend" / "nsfw_playbook.py").read_text(encoding="utf-8")
        and "renderPlaybookControls" in image_studio_js_text
        and "applyAdultPlaybook" in image_studio_js_text
        and "syncBooleanFormFields" in image_studio_js_text
        and "ensureUnrestrictedVideoModels" in frontend_js_text
        and "build_video_face_swap_prompt" in (ROOT / "beginner_frontend" / "nsfw_extensions.py").read_text(encoding="utf-8")
        and "apply_face_detailer" in (ROOT / "beginner_frontend" / "nsfw_extensions.py").read_text(encoding="utf-8")
        and "advanced_modules" in (ROOT / "beginner_frontend" / "nsfw_playbook.py").read_text(encoding="utf-8"),
        "nsfw playbook should expose one-click adult recipes, grouped scene presets, character box, and image/video linkage controls",
    )
    check(
        'data-view="video-face-swap"' in index_text
        and 'id="videoFaceSwapQueueList"' in index_text
        and 'id="videoFaceSwapResultView"' in index_text
        and 'id="videoFaceSwapCancelButton"' in index_text
        and 'aria-label="视频微调与换脸"' not in index_text
        and "acceptSubmittedVideoJob(data, \"face_swap\")" in frontend_js_text
        and '? "face_swap"' in frontend_js_text
        and "workflowJobs = jobs.filter" in frontend_js_text,
        "video face swap should be a standalone workspace with its own queue, progress, result, and cancellation state",
    )
    check(
        "提示词处理" in index_text
        and 'id="imageRejectionTerms"' not in index_text
        and "/api/image-studio/rejection-terms" not in image_studio_js_text
        and "/api/image-studio/rejection-terms" not in frontend_py_text
        and "UNRESTRICTED_REJECTION_TERMS_KEY" not in frontend_py_text
        and "flux2-klein-uncensored-te-addon" in (ROOT / "beginner_frontend" / "image_studio.py").read_text(encoding="utf-8")
        and "flux2-uncensored-te-addon" in (ROOT / "beginner_frontend" / "image_studio.py").read_text(encoding="utf-8"),
        "image studio should keep pure-language prompts and no longer ship prompt rejection filters",
    )
    check(
        "RECOVERED_JOB_MISSING_AFTER_MS" in frontend_py_text
        and 'job["status"] = "interrupted" if recovered else "lost"' in frontend_py_text
        and "ComfyUI 重启或队列被清空" in frontend_py_text,
        "recovered jobs should fail quickly after an engine restart without shortening the normal lost-job timeout",
    )
    check(
        "maybe_release_comfy_vram_for_completed_job" in frontend_py_text
        and 'comfy_post("/free"' in frontend_py_text
        and '"unload_models": True' in frontend_py_text
        and '"free_memory": True' in frontend_py_text
        and "BEGINNER_FRONTEND_UNLOAD_AFTER_JOB" in frontend_py_text,
        "finished generation jobs should ask ComfyUI to unload models and free VRAM",
    )
    check("installProfileSelector" in index_text, "environment UI should expose install profile selection")
    check(
        "hfEndpointInput" in index_text
        and "pipIndexInput" in index_text
        and "proxyUrlInput" in index_text
        and "saveDownloadSettingsButton" in index_text
        and "testDownloadSourcesButton" in index_text,
        "environment UI should expose Hugging Face, pip mirror, proxy settings, and a download-source test button",
    )
    check("runFullSetupButton" in index_text, "environment UI should expose one-click full setup button")
    check("runSelfTestButton" in index_text, "environment UI should expose one-click self-test button")
    check("runVideoSmokeButton" in index_text, "environment UI should expose real generation smoke-test button")
    check("prerequisiteChecks" in index_text, "environment UI should expose prerequisite checks")
    check("copyDiagnosticsButton" in index_text, "result panel should expose diagnostics copy button")
    check("downloadDiagnosticsButton" in index_text, "result panel should expose diagnostics download button")
    check(
        ".download-source-controls" in styles_text and "auto-fit" in styles_text and "minmax(240px, 1fr)" in styles_text,
        "download-source controls should use a responsive grid instead of cramped fixed columns",
    )
    check("/api/install-plan" in frontend_js_text, "frontend should refresh install plans when profile changes")
    check(
        "/api/settings" in frontend_js_text
        and "renderDownloadSettings" in frontend_js_text
        and "proxy_url" in frontend_js_text
        and "pip_index_url" in frontend_js_text,
        "frontend should save and render download-source/proxy/pip settings",
    )
    check(
        "testDownloadSources" in frontend_js_text
        and "/api/prerequisites?network=true" in frontend_js_text
        and "renderDownloadSourceTest" in frontend_js_text,
        "frontend should let beginners test saved download sources before starting installation",
    )
    check(
        "persistDownloadSettings({ refreshAfterSave: false })" in frontend_js_text
        and "正在保存当前填写的下载源并测试连通性" in frontend_js_text,
        "download-source test should save the current form values before network testing",
    )
    check(
        frontend_js_text.index('await loadBootstrap();', frontend_js_text.index("async function testDownloadSources"))
        < frontend_js_text.index('fetch("/api/prerequisites?network=true")')
        < frontend_js_text.index("renderDownloadSourceTest(data)"),
        "download-source test should refresh setup state before rendering the final reachability result",
    )
    check("downloadDiagnostics" in frontend_js_text and "local-ai-workbench-diagnostics-" in frontend_js_text and "URL.createObjectURL" in frontend_js_text, "frontend should download diagnostics as a JSON package")
    check(
        "fullSetupDownloadHosts" in frontend_js_text and "workflowAssetDownloadHosts" in frontend_js_text and "friendlyDownloadHostLabel" in frontend_js_text,
        "frontend confirmation prompts should list only the download hosts required by the selected setup path",
    )
    prerequisite_report = prerequisite_doctor.build_prerequisite_report(ROOT, ROOT, ROOT / "ComfyUI", include_network=False)
    check("checks" in prerequisite_report and any(item["id"] == "python" for item in prerequisite_report["checks"]), "prerequisite doctor should report Python readiness")
    check("install_commands" in prerequisite_report, "prerequisite doctor should include install commands")
    frontend_commands = prerequisite_report["install_commands"].get("frontend", [])
    check(
        any("ensurepip" in command for command in frontend_commands)
        and any("pip install -U pip" in command for command in frontend_commands),
        "prerequisite doctor frontend repair commands should include ensurepip and pip upgrade",
    )
    frontend_check = next(item for item in prerequisite_report["checks"] if item["id"] == "frontend_modules")
    check("source" in frontend_check and "python" in frontend_check, "prerequisite doctor should identify which Python environment was checked")
    check(
        {"github.com", "huggingface.co", "pypi.org", "download.pytorch.org"}.issubset(set(prerequisite_doctor.DOWNLOAD_HOSTS)),
        "network preflight should cover GitHub, Hugging Face, PyPI, and PyTorch downloads",
    )
    official_url = "https://huggingface.co/Org/Repo/resolve/main/model.safetensors"
    mirrored_url = install_workflow_assets.effective_download_url(official_url, "https://hf-mirror.example/root")
    check(
        mirrored_url == "https://hf-mirror.example/root/Org/Repo/resolve/main/model.safetensors",
        "model downloader should rewrite Hugging Face URLs to the configured endpoint without changing the repository path",
    )
    with patch.dict(os.environ, {"WAN22_HF_ENDPOINT": "https://hf-mirror.example"}, clear=False):
        targets = prerequisite_doctor.download_targets()
    check(
        "hf-mirror.example" in targets and "huggingface.co" not in targets,
        "network preflight should test the configured Hugging Face mirror instead of the official host",
    )
    with patch("beginner_frontend.app.saved_hf_endpoint", return_value="https://hf-mirror.example"), patch(
        "beginner_frontend.app.env_hf_endpoint",
        return_value="",
    ):
        check(frontend.effective_preflight_host("huggingface.co") == "hf-mirror.example", "frontend preflight should map Hugging Face requirements to the configured mirror host")
    with patch.dict(os.environ, {"PIP_INDEX_URL": "https://pypi.example/simple"}, clear=False):
        pip_targets = prerequisite_doctor.download_targets()
    check(
        "pypi.example" in pip_targets and "pypi.org" not in pip_targets,
        "network preflight should test the configured pip mirror instead of the official PyPI host",
    )
    with patch("beginner_frontend.app.saved_pip_index_url", return_value="https://pypi.example/simple"), patch(
        "beginner_frontend.app.env_pip_index_url",
        return_value="",
    ):
        check(frontend.effective_preflight_host("pypi.org") == "pypi.example", "frontend preflight should map PyPI requirements to the configured pip mirror host")
    check(frontend.redact_url("http://user:secret@127.0.0.1:7890") == "http://***:***@127.0.0.1:7890", "diagnostics should redact proxy credentials")
    check(
        frontend.redact_sensitive_text("proxy http://user:secret@127.0.0.1:7890/path") == "proxy http://***:***@127.0.0.1:7890/path",
        "diagnostics log redaction should hide URL credentials",
    )
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("HTTPS_PROXY", None)
        os.environ.pop("HTTP_PROXY", None)
        os.environ.pop("https_proxy", None)
        os.environ.pop("http_proxy", None)
        os.environ.pop("PIP_INDEX_URL", None)
        with patch("beginner_frontend.app.saved_proxy_url", return_value="http://127.0.0.1:7890"), patch(
            "beginner_frontend.app.saved_pip_index_url",
            return_value="https://pypi.example/simple",
        ):
            proxy_env = frontend.download_subprocess_env()
    check(
        proxy_env.get("HTTPS_PROXY") == "http://127.0.0.1:7890" and proxy_env.get("http_proxy") == "http://127.0.0.1:7890",
        "download subprocess env should propagate saved proxy settings to installers",
    )
    check(
        proxy_env.get("PIP_INDEX_URL") == "https://pypi.example/simple",
        "download subprocess env should propagate saved pip mirror settings to installers",
    )
    with patch.dict(os.environ, {"HTTPS_PROXY": "http://user:secret@proxy.local:8080"}, clear=False), patch(
        "scripts.prerequisite_doctor.url_reachable",
        return_value=True,
    ):
        network_check = prerequisite_doctor.check_network()
    check(
        "secret" not in str(network_check) and "***:***@proxy.local:8080" in str(network_check),
        "prerequisite network report should redact proxy credentials",
    )
    check('@app.post("/api/settings")' in frontend_py_text and "download_settings_payload" in frontend_py_text, "backend should expose persistent download-source settings")
    check(
        'label="ComfyUI 安装", env=download_subprocess_env()' in frontend_py_text
        and "args=(job_id, command, download_subprocess_env())" in frontend_py_text,
        "saved proxy settings should be passed to both full-setup and standalone ComfyUI installers",
    )
    check(
        "required_download_hosts_for_comfy_install" in frontend_py_text
        and "ComfyUI 安装前网络预检失败" in frontend_py_text,
        "standalone ComfyUI install should run download-source preflight before starting installers",
    )
    http_403 = urllib.error.HTTPError("https://download.pytorch.org/", 403, "Forbidden", hdrs=None, fp=None)
    with patch("scripts.prerequisite_doctor.urllib.request.urlopen", side_effect=http_403):
        check(prerequisite_doctor.url_reachable("https://download.pytorch.org/") is True, "network preflight should treat HTTP 4xx as reachable")
    check("--accept-source-agreements" in prerequisite_text and "start https://www.python.org/downloads/windows/" in prerequisite_text, "prerequisite doctor Windows install commands should match beginner launchers")
    check("open https://www.python.org/downloads/macos/" in prerequisite_text, "prerequisite doctor macOS install commands should match beginner launchers")
    network_hint = frontend.classify_install_failure(["[error] Could not download model: timed out"], return_code=1)
    check(network_hint["category"] == "network" and any(".part" in action for action in network_hint["actions"]), "network failures should explain .part retry behavior")
    license_hint = frontend.classify_install_failure(
        ["[error] 403 Forbidden huggingface.co Agree and Access"],
        return_code=1,
    )
    check(
        license_hint["category"] == "license" and license_hint["title"] == "需要先接受模型许可",
        "gated Hugging Face 403 should not be classified as a flaky download network",
    )
    network_hf_hint = frontend.classify_install_failure(["Could not download from huggingface.co: timed out"], return_code=1)
    check(network_hf_hint["category"] == "network", "Hugging Face timeouts should remain network failures")
    disk_hint = frontend.classify_install_failure(["Not enough free disk space"], return_code=1)
    check(disk_hint["category"] == "disk", "disk failures should be classified")
    missing_script_hint = frontend.classify_install_failure(["安装脚本不存在：scripts/install_workflow_assets.py"], return_code=1)
    check(missing_script_hint["category"] == "missing_script", "missing installer scripts should be classified")
    fake_job_id = "self_check_failure_hint"
    frontend.INSTALL_JOBS[fake_job_id] = {
        "id": fake_job_id,
        "kind": "install_assets",
        "status": "failed",
        "completed": True,
        "created_at": 1,
        "log": ["Could not download from huggingface.co: timed out"],
    }
    frontend.attach_failure_hint(frontend.INSTALL_JOBS[fake_job_id])
    recent_jobs = frontend.recent_jobs_payload()
    check(any(item.get("id") == fake_job_id and item.get("failure_hint") for item in recent_jobs), "diagnostics should include recent failed job hints")
    frontend.INSTALL_JOBS.pop(fake_job_id, None)
    redaction_job_id = "self_check_redacted_log"
    frontend.INSTALL_JOBS[redaction_job_id] = {
        "id": redaction_job_id,
        "kind": "install_assets",
        "status": "failed",
        "completed": True,
        "created_at": 2,
        "log": ["proxy=http://user:secret@127.0.0.1:7890"],
    }
    redacted_jobs = frontend.recent_jobs_payload()
    frontend.INSTALL_JOBS.pop(redaction_job_id, None)
    check("secret" not in str(redacted_jobs) and "***:***@127.0.0.1:7890" in str(redacted_jobs), "recent job diagnostics should redact URL credentials in logs")
    if sys.platform.startswith("win"):
        windows_python_paths = launcher.common_windows_python_paths()
        check(any("Python312" in str(path) for path in windows_python_paths), "Windows Python 3.12 path fallback missing")
        check("Get-CommonPythonPaths" in ps1_text, "PowerShell launcher missing common Python path fallback")
    with patch("beginner_frontend.app.shutil.which", return_value=None):
        payload = frontend.bootstrap_status_payload(False)
        check(payload["can_install_comfyui"] is True, "ComfyUI install should be available without git")
        check(payload["git_ready"] is False, "git_ready mock failed")
    full_setup_job_id = "self_check_full_setup_skip"
    frontend.INSTALL_JOBS[full_setup_job_id] = {
        "id": full_setup_job_id,
        "kind": "full_setup",
        "status": "queued",
        "completed": False,
        "created_at": 1,
        "dry_run": True,
        "log": [],
    }
    captured_commands: list[tuple[str, list[str]]] = []
    captured_command_envs: list[tuple[str, dict[str, str] | None]] = []

    def fake_logged_command(job: dict, command: list[str], *, label: str, **_: object) -> int:
        captured_commands.append((label, command))
        job["log"].append(f"{label}: fake")
        return 0

    with patch("beginner_frontend.app.run_logged_command", side_effect=fake_logged_command):
        frontend.run_full_setup_worker(
            full_setup_job_id,
            backend="skip",
            profile="post-only",
            base_dir=ROOT,
            dry_run=True,
            skip_comfy_install=True,
            use_local_comfy_python=False,
        )
    full_setup_job = frontend.INSTALL_JOBS.pop(full_setup_job_id)
    check(full_setup_job["status"] == "success", "full setup skip-source dry-run should succeed")
    check(not any(label == "ComfyUI 安装" for label, _ in captured_commands), "running ComfyUI full setup should skip source ComfyUI install")
    asset_commands = [command for label, command in captured_commands if label == "模型/节点安装"]
    check(asset_commands and "--comfy-python" not in asset_commands[0], "external running ComfyUI setup should not pass local comfy-python")

    captured_commands.clear()

    def fake_logged_command_with_env(job: dict, command: list[str], *, label: str, env: dict[str, str] | None = None, **_: object) -> int:
        captured_commands.append((label, command))
        captured_command_envs.append((label, env))
        job["log"].append(f"{label}: fake")
        return 0

    proxy_full_setup_job_id = "self_check_full_setup_proxy"
    frontend.INSTALL_JOBS[proxy_full_setup_job_id] = {
        "id": proxy_full_setup_job_id,
        "kind": "full_setup",
        "status": "queued",
        "completed": False,
        "created_at": 1,
        "dry_run": True,
        "log": [],
    }
    with patch.dict(os.environ, {}, clear=True), patch(
        "beginner_frontend.app.saved_proxy_url",
        return_value="http://127.0.0.1:7890",
    ), patch(
        "beginner_frontend.app.saved_pip_index_url",
        return_value="https://pypi.example/simple",
    ), patch(
        "beginner_frontend.app.run_logged_command",
        side_effect=fake_logged_command_with_env,
    ):
        frontend.run_full_setup_worker(
            proxy_full_setup_job_id,
            backend="skip",
            profile="post-only",
            base_dir=ROOT,
            dry_run=True,
            skip_comfy_install=False,
            use_local_comfy_python=False,
        )
    proxy_full_setup_job = frontend.INSTALL_JOBS.pop(proxy_full_setup_job_id)
    check(proxy_full_setup_job["status"] == "success", "full setup proxy dry-run should succeed")
    env_by_label = {label: env or {} for label, env in captured_command_envs}
    check(
        env_by_label.get("ComfyUI 安装", {}).get("HTTPS_PROXY") == "http://127.0.0.1:7890",
        "full setup should pass saved proxy settings to the ComfyUI installer",
    )
    check(
        env_by_label.get("模型/节点安装", {}).get("HTTPS_PROXY") == "http://127.0.0.1:7890",
        "full setup should pass saved proxy settings to the workflow asset installer",
    )
    check(
        env_by_label.get("ComfyUI 安装", {}).get("PIP_INDEX_URL") == "https://pypi.example/simple"
        and env_by_label.get("模型/节点安装", {}).get("PIP_INDEX_URL") == "https://pypi.example/simple",
        "full setup should pass saved pip mirror settings to both installers",
    )
    network_fail_job_id = "self_check_full_setup_network_fail"
    frontend.INSTALL_JOBS[network_fail_job_id] = {
        "id": network_fail_job_id,
        "kind": "full_setup",
        "status": "queued",
        "completed": False,
        "created_at": 1,
        "dry_run": False,
        "log": [],
    }

    def fake_prerequisite_report(*args: object, **kwargs: object) -> dict:
        check(kwargs.get("include_network") is True, "full setup should request network preflight before real downloads")
        return {
            "checks": [
                {
                    "id": "network",
                    "label": "下载网络",
                    "status": "warn",
                    "blocking": False,
                    "message": "部分下载站点不可连接：Hugging Face",
                    "action": "检查代理、DNS、防火墙或稍后重试。",
                    "reachable": {"github.com": True, "huggingface.co": False, "pypi.org": True, "download.pytorch.org": True},
                }
            ]
        }

    def fail_if_command_runs(*args: object, **kwargs: object) -> int:
        raise AssertionError("installer command should not run when network preflight fails")

    network_fail_assets = [
        {
            "id": "rife49",
            "ok": False,
            "installable": True,
            "download_host": "huggingface.co",
            "local_available": False,
        }
    ]
    network_fail_nodes: list[dict[str, object]] = []
    with patch("beginner_frontend.app.BUILD_PREREQUISITE_REPORT", side_effect=fake_prerequisite_report), patch(
        "beginner_frontend.app.collect_asset_checks",
        return_value=network_fail_assets,
    ), patch("beginner_frontend.app.collect_custom_node_checks", return_value=network_fail_nodes), patch(
        "beginner_frontend.app.run_logged_command",
        side_effect=fail_if_command_runs,
    ):
        frontend.run_full_setup_worker(
            network_fail_job_id,
            backend="skip",
            profile="post-only",
            base_dir=ROOT,
            dry_run=False,
            skip_comfy_install=True,
            use_local_comfy_python=False,
        )
    network_fail_job = frontend.INSTALL_JOBS.pop(network_fail_job_id)
    check(network_fail_job["status"] == "failed", "full setup should fail early when download network preflight fails")
    check(network_fail_job.get("failure_hint", {}).get("category") == "network", "network preflight failures should use network failure hints")
    no_hosts_job = {"id": "self_check_no_download_hosts", "log": []}
    frontend.run_download_network_preflight(no_hosts_job, set())
    check(no_hosts_job.get("network_preflight", {}).get("status") == "skipped", "download network preflight should skip when nothing needs downloading")
    check(
        frontend.required_download_hosts_for_comfy_install("skip") == {"github.com", "pypi.org"}
        and "download.pytorch.org" in frontend.required_download_hosts_for_comfy_install("cuda"),
        "standalone ComfyUI install should preflight GitHub/PyPI/PyTorch hosts according to backend",
    )
    with patch("beginner_frontend.app.COMFYUI_EFFECTIVE_BACKEND", return_value="mps"):
        check(
            frontend.required_download_hosts_for_comfy_install("auto") == {"github.com", "pypi.org"},
            "macOS/MPS ComfyUI install should not preflight download.pytorch.org because torch uses the configured PyPI source",
        )
    with patch("beginner_frontend.app.COMFYUI_EFFECTIVE_BACKEND", return_value="cpu"):
        check(
            "download.pytorch.org" in frontend.required_download_hosts_for_comfy_install("auto"),
            "CPU ComfyUI install should still preflight the PyTorch wheel host",
        )

    ready_assets = [
        {"id": "rife49", "ok": True, "download_host": "huggingface.co"},
        {"id": "realesrgan_x2", "ok": True, "download_host": "github.com"},
        {"id": "ultrasharp_x4", "ok": True, "download_host": "huggingface.co"},
    ]
    ready_nodes = [
        {"id": "video_helper_suite", "ok": True, "download_host": "github.com"},
        {"id": "frame_interpolation", "ok": True, "download_host": "github.com"},
    ]
    with patch("beginner_frontend.app.collect_asset_checks", return_value=ready_assets), patch("beginner_frontend.app.collect_custom_node_checks", return_value=ready_nodes):
        ready_hosts = frontend.required_download_hosts_for_full_setup(
            profile="post-only",
            base_dir=ROOT,
            backend="skip",
            skip_comfy_install=True,
            use_local_comfy_python=False,
        )
    check(ready_hosts == set(), "full setup should not preflight download hosts when selected assets and nodes are already ready")
    missing_asset_and_node_assets = [
        {"id": "rife49", "ok": False, "download_host": "huggingface.co"},
        {"id": "realesrgan_x2", "ok": True, "download_host": "github.com"},
        {"id": "ultrasharp_x4", "ok": True, "download_host": "huggingface.co"},
    ]
    missing_asset_and_node_nodes = [
        {"id": "video_helper_suite", "ok": True, "download_host": "github.com"},
        {"id": "frame_interpolation", "ok": False, "download_host": "github.com"},
    ]
    with patch("beginner_frontend.app.collect_asset_checks", return_value=missing_asset_and_node_assets), patch(
        "beginner_frontend.app.collect_custom_node_checks",
        return_value=missing_asset_and_node_nodes,
    ):
        asset_install_hosts = frontend.required_download_hosts_for_workflow_assets(
            profile="post-only",
            base_dir=ROOT,
            use_local_comfy_python=True,
        )
    check(
        {"huggingface.co", "github.com", "pypi.org"} <= asset_install_hosts and "download.pytorch.org" not in asset_install_hosts,
        "workflow asset install should preflight missing asset/node hosts and node requirement PyPI, but not PyTorch",
    )
    with patch("beginner_frontend.app.collect_asset_checks", return_value=ready_assets), patch(
        "beginner_frontend.app.collect_custom_node_checks",
        return_value=ready_nodes,
    ), patch("beginner_frontend.app.COMFYUI_EFFECTIVE_BACKEND", return_value="mps"):
        mps_hosts = frontend.required_download_hosts_for_full_setup(
            profile="post-only",
            base_dir=ROOT,
            backend="auto",
            skip_comfy_install=False,
            use_local_comfy_python=False,
        )
    check(
        {"github.com", "pypi.org"}.issubset(mps_hosts) and "download.pytorch.org" not in mps_hosts,
        "Mac/MPS full setup should require GitHub/PyPI but not the PyTorch wheel host",
    )

    def fake_nonrequired_network_report(*args: object, **kwargs: object) -> dict:
        check(kwargs.get("include_network") is True, "download network preflight should request network details")
        return {
            "checks": [
                {
                    "id": "network",
                    "label": "下载网络",
                    "status": "warn",
                    "blocking": False,
                    "message": "部分下载站点不可连接：PyPI",
                    "action": "检查代理、DNS、防火墙或稍后重试。",
                    "reachable": {"github.com": True, "huggingface.co": True, "pypi.org": False, "download.pytorch.org": True},
                }
            ]
        }

    nonrequired_fail_job = {"id": "self_check_nonrequired_network_fail", "log": []}
    with patch("beginner_frontend.app.BUILD_PREREQUISITE_REPORT", side_effect=fake_nonrequired_network_report), patch(
        "beginner_frontend.app.env_hf_endpoint",
        return_value="",
    ), patch("beginner_frontend.app.saved_hf_endpoint", return_value=""), patch(
        "beginner_frontend.app.env_pip_index_url",
        return_value="",
    ), patch("beginner_frontend.app.saved_pip_index_url", return_value=""):
        frontend.run_download_network_preflight(nonrequired_fail_job, {"github.com", "huggingface.co"})
    check(
        nonrequired_fail_job.get("network_preflight", {}).get("missing_required_hosts") == [],
        "download network preflight should ignore unreachable hosts that are not needed for the selected install profile",
    )
    with tempfile.TemporaryDirectory(prefix="wan22_install_dir_check_") as temp_name:
        temp_root = Path(temp_name)
        base_dir = temp_root / "base"
        alien_install = base_dir / "ComfyUI"
        project_dir = temp_root / "project"
        alien_install.mkdir(parents=True)
        project_dir.mkdir()
        (alien_install / "not_comfy.txt").write_text("occupied", encoding="utf-8")
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("COMFY_INSTALL_DIR", None)
            with patch("beginner_frontend.app.WORKSPACE_DIR", project_dir):
                check(
                    frontend.default_comfy_install_dir(base_dir) == project_dir / "ComfyUI",
                    "default ComfyUI install dir should fall back to project-local dir when base ComfyUI is occupied",
                )
        with patch.dict(os.environ, {"COMFY_INSTALL_DIR": str(alien_install)}, clear=False):
            check(
                frontend.default_comfy_install_dir(base_dir) == alien_install,
                "explicit COMFY_INSTALL_DIR should be respected even when occupied",
            )
    with tempfile.TemporaryDirectory(prefix="comfy_desktop_runtime_") as temp_name:
        temp_root = Path(temp_name)
        base_dir = temp_root / "base"
        project_dir = temp_root / "project"
        desktop_root = base_dir / "ComfyUI"
        bundled_main = desktop_root / "resources" / "ComfyUI" / "main.py"
        base_python = frontend.venv_python_for(base_dir / ".venv")
        bundled_main.parent.mkdir(parents=True)
        base_python.parent.mkdir(parents=True)
        bundled_main.write_text("# fake desktop ComfyUI", encoding="utf-8")
        base_python.write_text("", encoding="utf-8")
        project_dir.mkdir()
        if frontend.platform.system() == "Darwin":
            (desktop_root / "ComfyUI.app").mkdir(parents=True)
        else:
            (desktop_root / ("ComfyUI.exe" if frontend.platform.system() == "Windows" else "ComfyUI")).write_text("", encoding="utf-8")
        with patch("beginner_frontend.app.BASE_DIR", base_dir), patch(
            "beginner_frontend.app.WORKSPACE_DIR",
            project_dir,
        ), patch("beginner_frontend.app.COMFY_INSTALL_DIR", project_dir / "ComfyUI"):
            runtime = frontend.comfy_runtime_info()
            check(runtime["kind"] == "desktop_runtime", "ComfyUI Desktop bundled source should be detected as a startable runtime")
            check(Path(str(runtime["main_py"])) == bundled_main.resolve(), "Desktop runtime should use bundled ComfyUI main.py")
            check(Path(str(runtime["python"])) == base_python.resolve(), "Desktop runtime should use the base .venv Python")
            bootstrap = frontend.bootstrap_status_payload(False)
            check(bootstrap["can_start_comfyui"] is True and bootstrap["runtime_source_ready"] is True, "bootstrap should allow starting a detected Desktop runtime")
            start_command = frontend.comfy_start_command()
            check(str(bundled_main.resolve()) in start_command and str(base_python.resolve()) in start_command, "start command should target Desktop runtime paths")
        with patch.dict(os.environ, {"COMFY_INSTALL_DIR": ""}, clear=False):
            doctor_install = prerequisite_doctor.default_install_dir(base_dir)
        doctor_check = prerequisite_doctor.check_comfy_install_dir(doctor_install)
        check(doctor_install == desktop_root.resolve(), "prerequisite doctor should default to the parent ComfyUI Desktop directory")
        check(doctor_check["status"] == "ok" and doctor_check.get("runtime") == "desktop", "prerequisite doctor should not block ComfyUI Desktop runtime directories")
    ffmpeg_probe = frontend.ffmpeg_probe()
    check("name" in ffmpeg_probe and "install_hint" in ffmpeg_probe, "ffmpeg probe payload incomplete")
    ffmpeg_tools = frontend.ffmpeg_tool_checks()
    check({item["name"] for item in ffmpeg_tools} == {"ffmpeg", "ffmpeg:deflicker", "ffmpeg:hqdn3d"}, "ffmpeg tool checks incomplete")
    stitch_checked = False
    if ffmpeg_probe.get("ok"):
        with tempfile.TemporaryDirectory(prefix="local_stitch_check_") as temp_name:
            temp_root = Path(temp_name)
            input_dir = temp_root / "input"
            output_dir = temp_root / "output"
            temp_dir = temp_root / "temp"
            for directory in (input_dir, output_dir, temp_dir):
                directory.mkdir(parents=True, exist_ok=True)
            sources: list[Path] = []
            for index, color in enumerate(("red", "blue"), start=1):
                source = input_dir / f"clip_{index}.mp4"
                result = subprocess.run(
                    [
                        frontend.find_ffmpeg(),
                        "-y",
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-f",
                        "lavfi",
                        "-i",
                        f"color=c={color}:s=64x64:d=0.25:r=8",
                        "-pix_fmt",
                        "yuv420p",
                        str(source),
                    ],
                    capture_output=True,
                    text=True,
                )
                check(result.returncode == 0 and source.exists(), f"failed to create stitch fixture: {result.stderr}")
                sources.append(source)
            media = frontend.run_stitch(
                sources,
                width=64,
                height=64,
                fps=8,
                paths={
                    "base_dir": temp_root,
                    "input_dir": input_dir,
                    "output_dir": output_dir,
                    "temp_dir": temp_dir,
                },
            )
            stitched_path = output_dir / str(media.get("subfolder") or "") / str(media.get("filename") or "")
            check(stitched_path.exists() and stitched_path.stat().st_size > 0, "local multi-clip stitch should produce an MP4")
            stitch_checked = True
    connect_error_text = frontend.comfy_connection_error_text(frontend.httpx.ConnectError(""))
    check("连接被拒绝" in connect_error_text, "empty ComfyUI connection errors should become beginner-friendly text")
    with tempfile.TemporaryDirectory(prefix="comfy_argv_base_") as temp_name:
        comfy_root = Path(temp_name) / "ComfyUI"
        comfy_root.mkdir()
        main_py = comfy_root / "main.py"
        main_py.write_text("# fake", encoding="utf-8")
        inferred_paths = frontend.comfy_paths_from_system_stats({"system": {"argv": [str(main_py)]}})
        check(inferred_paths["source"] == "running_comfyui", "connected ComfyUI without --base-directory should still be treated as running")
        check(inferred_paths["base_dir_source"] == "argv_main_py", "ComfyUI base source should record argv main.py inference")
        check(Path(inferred_paths["base_dir"]) == comfy_root.resolve(), "ComfyUI base should be inferred from argv main.py when --base-directory is absent")
        serialized_paths = frontend.serializable_comfy_paths(inferred_paths)
        check(serialized_paths["main_py"] == str(main_py.resolve()), "serialized ComfyUI paths should include inferred main.py")
    check(install_comfyui.COMFY_ZIP_CANDIDATES, "ComfyUI zip fallback URLs missing")
    install_comfyui_text = (ROOT / "scripts" / "install_comfyui.py").read_text(encoding="utf-8")
    install_assets_text = (ROOT / "scripts" / "install_workflow_assets.py").read_text(encoding="utf-8")
    check("dest.name + \".part\"" in install_comfyui_text and "retries: int = 3" in install_comfyui_text, "ComfyUI zip fallback should retry via .part files")
    check("dest.name + \".part\"" in install_assets_text and "retries: int = 3" in install_assets_text, "custom node zip fallback should retry via .part files")
    check("ensure_pip_available" in install_comfyui_text and "ensurepip" in install_comfyui_text and "run_pip" in install_comfyui_text, "ComfyUI installer should repair missing pip and retry dependency installs")
    check("ensure_pip_available" in install_assets_text and "ensurepip" in install_assets_text and "run_pip" in install_assets_text, "workflow asset installer should repair missing pip and retry custom node dependency installs")
    check("Install target is not empty; refusing to replace it" in install_comfyui_text and "dest.rmdir()" in install_comfyui_text, "ComfyUI zip fallback should only replace an empty target directory")
    check("Custom node target is not empty; refusing to replace it" in install_assets_text and "dest.rmdir()" in install_assets_text, "custom node zip fallback should only replace an empty target directory")
    check("git clone failed" in install_comfyui_text and "install_repo_from_zip(install_dir)" in install_comfyui_text, "ComfyUI install should fall back to source zip when git clone fails")
    check("git clone failed" in install_assets_text and "install_node_from_zip" in install_assets_text, "custom node install should fall back to source zip when git clone fails")
    comfy_pip_calls: list[list[str]] = []

    def flaky_comfy_pip(command: list[str], cwd: Path | None = None) -> None:
        del cwd
        comfy_pip_calls.append(command)
        if len(comfy_pip_calls) == 1:
            raise subprocess.CalledProcessError(1, command)

    with patch("scripts.install_comfyui.run", side_effect=flaky_comfy_pip), patch("scripts.install_comfyui.time.sleep", return_value=None):
        install_comfyui.run_pip([str(Path("python")), "-m", "pip", "install", "torch"])
    check(len(comfy_pip_calls) == 2, "ComfyUI installer pip commands should retry after a transient failure")
    assets_pip_calls: list[list[str]] = []

    def flaky_assets_pip(command: list[str], cwd: Path) -> None:
        del cwd
        assets_pip_calls.append(command)
        if len(assets_pip_calls) == 1:
            raise subprocess.CalledProcessError(1, command)

    with patch("scripts.install_workflow_assets.run", side_effect=flaky_assets_pip), patch("scripts.install_workflow_assets.time.sleep", return_value=None):
        install_workflow_assets.run_pip([str(Path("python")), "-m", "pip", "install", "opencv-python"], ROOT)
    check(len(assets_pip_calls) == 2, "workflow asset installer pip commands should retry after a transient failure")
    with tempfile.TemporaryDirectory(prefix="comfy_clone_fallback_") as temp_name:
        install_dir = Path(temp_name) / "ComfyUI"

        def fail_comfy_clone(command: list[str], cwd: Path | None = None) -> None:
            del cwd
            install_dir.mkdir(parents=True, exist_ok=True)
            (install_dir / "partial.txt").write_text("partial", encoding="utf-8")
            raise subprocess.CalledProcessError(128, command)

        def fake_comfy_zip(dest: Path) -> None:
            dest.mkdir(parents=True, exist_ok=True)
            (dest / "main.py").write_text("# zip fallback", encoding="utf-8")

        with patch("scripts.install_comfyui.shutil.which", return_value="git"), patch("scripts.install_comfyui.run", side_effect=fail_comfy_clone), patch(
            "scripts.install_comfyui.install_repo_from_zip",
            side_effect=fake_comfy_zip,
        ):
            install_comfyui.ensure_repo(install_dir)
        check((install_dir / "main.py").exists() and not (install_dir / "partial.txt").exists(), "ComfyUI git clone failure should clean partial target and use zip fallback")
    with tempfile.TemporaryDirectory(prefix="node_clone_fallback_") as temp_name:
        base_dir = Path(temp_name)
        node_dest = base_dir / "custom_nodes" / "FakeNode"

        def fail_node_clone(command: list[str], cwd: Path) -> None:
            del cwd
            node_dest.mkdir(parents=True, exist_ok=True)
            (node_dest / "partial.txt").write_text("partial", encoding="utf-8")
            raise subprocess.CalledProcessError(128, command)

        def fake_node_zip(repo_url: str, dest: Path, ref: str = "") -> None:
            del repo_url, ref
            dest.mkdir(parents=True, exist_ok=True)
            (dest / "__init__.py").write_text("# zip fallback", encoding="utf-8")

        fake_repos = [{"id": "fake_node", "name": "FakeNode", "url": "https://github.com/example/FakeNode.git", "dest": "custom_nodes/FakeNode"}]
        fake_profiles = {"cuda-full": {"custom_node_ids": ["fake_node"]}}
        with patch("scripts.install_workflow_assets.CUSTOM_NODE_REPOS", fake_repos), patch(
            "scripts.install_workflow_assets.INSTALL_PROFILES",
            fake_profiles,
        ), patch(
            "scripts.install_workflow_assets.shutil.which",
            return_value="git",
        ), patch("scripts.install_workflow_assets.run", side_effect=fail_node_clone), patch(
            "scripts.install_workflow_assets.install_node_from_zip",
            side_effect=fake_node_zip,
        ):
            install_workflow_assets.ensure_custom_nodes(base_dir, install_requirements=False)
        check((node_dest / "__init__.py").exists() and not (node_dest / "partial.txt").exists(), "custom node git clone failure should clean partial target and use zip fallback")
    with patch("scripts.install_comfyui.platform.system", return_value="Darwin"):
        check(install_comfyui.effective_backend("auto") == "mps", "macOS auto backend should use MPS")
    with patch("scripts.install_comfyui.platform.system", return_value="Windows"), patch("scripts.install_comfyui.shutil.which", return_value=None):
        check(install_comfyui.effective_backend("auto") == "cpu", "Windows without NVIDIA should use CPU backend")
    fake_nvidia = subprocess.CompletedProcess(["nvidia-smi", "-L"], 0, stdout="GPU 0: NVIDIA RTX PRO 5000", stderr="")
    with patch("scripts.install_comfyui.platform.system", return_value="Windows"), patch("scripts.install_comfyui.shutil.which", return_value="nvidia-smi"), patch("scripts.install_comfyui.subprocess.run", return_value=fake_nvidia):
        check(install_comfyui.effective_backend("auto") == "cuda", "Windows with NVIDIA should use CUDA backend")
    comfy_disk_plan = install_comfyui.comfyui_disk_plan(ROOT / "ComfyUI", "skip")
    check("ok" in comfy_disk_plan and "recommended_free_gb" in comfy_disk_plan, "ComfyUI disk plan is incomplete")
    with tempfile.TemporaryDirectory(prefix="comfy_self_check_") as temp_name:
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "install_comfyui.py"),
                "--base-dir",
                str(Path(temp_name) / "base"),
                "--install-dir",
                str(Path(temp_name) / "ComfyUI"),
                "--backend",
                "skip",
                "--dry-run",
            ],
            capture_output=True,
            text=True,
        )
    check(result.returncode == 0, "ComfyUI installer dry-run failed: " + result.stderr + result.stdout)
    check(install_workflow_assets.github_zip_candidates("https://github.com/a/b.git")[0].endswith("/main.zip"), "node zip URL fallback failed")
    check(
        install_workflow_assets.github_zip_candidates("https://github.com/a/b.git", "abc123")[0].endswith("/abc123.zip"),
        "pinned custom-node zip fallback should use the requested ref",
    )
    reactor_repo = next(item for item in install_workflow_assets.CUSTOM_NODE_REPOS if item.get("id") == "reactor")
    check(
        reactor_repo.get("installer_packages") == ["setuptools", "importlib-metadata"],
        "ReActor should bootstrap its Python 3.13 installer imports before running install.py",
    )
    check(
        "albumentations" in (reactor_repo.get("verify_imports") or [])
        and "onnxruntime" in (reactor_repo.get("verify_imports") or [])
        and "opencv-python>=4.7.0.72" in (reactor_repo.get("checked_packages") or [])
        and reactor_repo.get("no_deps_packages") == ["albucore==0.0.24", "albumentations==2.0.8"],
        "ReActor should reuse ComfyUI OpenCV and verify its runtime imports after the upstream installer completes",
    )
    with tempfile.TemporaryDirectory(prefix="reactor_installer_bootstrap_") as temp_name:
        node_dir = Path(temp_name)
        (node_dir / "install.py").write_text("print('ok')\n", encoding="utf-8")
        (node_dir / "requirements.txt").write_text("albumentations>=1.4.16\n", encoding="utf-8")
        installer_calls: list[tuple[str, list[str]]] = []

        def record_pip(command: list[str], _cwd: Path, attempts: int = 3) -> None:
            installer_calls.append(("pip", command))

        def record_run(command: list[str], _cwd: Path) -> None:
            installer_calls.append(("run", command))

        with patch("scripts.install_workflow_assets.ensure_pip_available"), patch(
            "scripts.install_workflow_assets.run_pip", side_effect=record_pip
        ), patch("scripts.install_workflow_assets.run", side_effect=record_run):
            install_workflow_assets.install_node_dependencies(reactor_repo, node_dir, Path(sys.executable))
        check(
            [item[0] for item in installer_calls] == ["pip", "run", "pip", "pip", "run"]
            and "setuptools" in installer_calls[0][1]
            and installer_calls[1][1][-1].endswith("install.py")
            and "--no-deps" in installer_calls[3][1],
            "custom-node installer bootstrap packages, checked requirements, and runtime import verification should run in order",
        )
    with tempfile.TemporaryDirectory(prefix="reactor_archive_") as temp_name:
        root = Path(temp_name)
        archive_path = root / "models" / "insightface" / ".downloads" / "buffalo_l.zip"
        archive_path.parent.mkdir(parents=True)
        model_names = ("1k3d68.onnx", "2d106det.onnx", "det_10g.onnx", "genderage.onnx", "w600k_r50.onnx")
        with zipfile.ZipFile(archive_path, "w") as archive:
            for model_name in model_names:
                archive.writestr(f"buffalo_l/{model_name}", b"onnx-self-check")
        archive_item = {
            "archive": "zip",
            "extract_to": "models/insightface/models/buffalo_l",
            "strip_single_root": True,
            "required_paths": [f"models/insightface/models/buffalo_l/{name}" for name in model_names],
        }
        install_workflow_assets.finalize_model_asset(root, archive_item, archive_path)
        check(
            install_workflow_assets.required_asset_paths_ready(root, archive_item)
            and all((root / path).read_bytes() == b"onnx-self-check" for path in archive_item["required_paths"]),
            "archive model assets should be extracted and validated before custom-node dependencies run",
        )
    with tempfile.TemporaryDirectory(prefix="wan22_local_asset_") as temp_name:
        temp_root = Path(temp_name)
        cache_root = temp_root / "cache"
        base_dir = temp_root / "base"
        payload = b"local asset payload"
        fake_item = {
            "id": "fake_local_asset",
            "group": "post",
            "name": "fake_local_asset.safetensors",
            "url": "https://huggingface.co/example/fake/resolve/main/fake_local_asset.safetensors",
            "dest": "models/checkpoints/fake_local_asset.safetensors",
            "bytes": len(payload),
        }
        local_file = cache_root / "models" / "checkpoints" / "fake_local_asset.safetensors"
        local_file.parent.mkdir(parents=True)
        local_file.write_bytes(payload)
        target = base_dir / str(fake_item["dest"])
        with patch.dict(os.environ, {"WAN22_LOCAL_ASSET_DIRS": str(cache_root), "WAN22_COPY_LOCAL_ASSETS": "1"}, clear=False):
            check(
                install_workflow_assets.find_local_asset_candidate(fake_item, dest=target, base_dir=base_dir) == local_file.resolve(),
                "installer should discover matching files from WAN22_LOCAL_ASSET_DIRS",
            )
            check(
                install_workflow_assets.remaining_bytes_for_item(base_dir, fake_item) == 0,
                "local cache hits should not count as network download bytes",
            )
            check(
                install_workflow_assets.install_from_local_asset(fake_item, target, len(payload), base_dir) is True,
                "installer should copy/link a matching local asset before downloading",
            )
        check(target.read_bytes() == payload, "local asset copy/link wrote the wrong file")
        fake_frontend_asset = {
            "id": "rife49",
            "label": "Fake local RIFE",
            "step": "RIFE 插帧",
            "path": base_dir / str(fake_item["dest"]),
            "bytes": len(payload),
            "dest": str(fake_item["dest"]),
            "name": str(fake_item["name"]),
            "url": str(fake_item["url"]),
            "installable": True,
        }
        target.unlink()
        with patch.dict(os.environ, {"WAN22_LOCAL_ASSET_DIRS": str(cache_root)}, clear=False), patch(
            "beginner_frontend.app.workflow_asset_manifest",
            return_value=[fake_frontend_asset],
        ):
            local_check = frontend.collect_asset_checks(base_dir)[0]
            check(local_check["local_available"] is True and local_check["remaining_gb"] == 0, "frontend should surface reusable local assets")
            with patch("beginner_frontend.app.collect_asset_checks", return_value=[local_check]), patch(
                "beginner_frontend.app.collect_custom_node_checks",
                return_value=[],
            ):
                hosts = frontend.required_download_hosts_for_workflow_assets(
                    profile="post-only",
                    base_dir=base_dir,
                    use_local_comfy_python=False,
                )
            check("huggingface.co" not in hosts, "local asset hits should not force Hugging Face network preflight")
    with tempfile.TemporaryDirectory(prefix="wan22_self_check_") as temp_name:
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "install_workflow_assets.py"),
                "--base-dir",
                temp_name,
                "--profile",
                "post-only",
                "--dry-run",
                "--no-custom-nodes",
                "--no-node-requirements",
            ],
            capture_output=True,
            text=True,
        )
    check(result.returncode == 0, "installer dry-run failed: " + result.stderr + result.stdout)
    check(launcher.frontend_url_for_port(7861).endswith(":7861"), "launcher port helper failed")
    return {"zip_fallback": True, "local_stitch": stitch_checked, "launcher_version": launcher.APP_VERSION}


def download_resume_check() -> dict[str, bool]:
    sys.path.insert(0, str(ROOT))
    from beginner_frontend import app as frontend
    from scripts import install_workflow_assets

    class FakeResponse:
        def __init__(self, data: bytes, status: int = 206, headers: dict[str, str] | None = None) -> None:
            self.data = data
            self.status = status
            self.headers = headers or {}
            self.offset = 0

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def read(self, size: int = -1) -> bytes:
            if self.offset >= len(self.data):
                return b""
            if size < 0:
                size = len(self.data) - self.offset
            chunk = self.data[self.offset : self.offset + size]
            self.offset += len(chunk)
            return chunk

    payload = bytes((index % 251 for index in range(257 * 1024)))
    split_at = 41_000
    seen_ranges: list[str | None] = []

    def fake_urlopen(request: object, timeout: int = 60) -> FakeResponse:
        del timeout
        range_header = request.get_header("Range") if hasattr(request, "get_header") else None
        seen_ranges.append(range_header)
        check(range_header == f"bytes={split_at}-", "download resume should request the remaining byte range")
        return FakeResponse(
            payload[split_at:],
            status=206,
            headers={
                "Content-Range": f"bytes {split_at}-{len(payload) - 1}/{len(payload)}",
                "Content-Length": str(len(payload) - split_at),
            },
        )

    with tempfile.TemporaryDirectory(prefix="wan22_resume_check_") as temp_name:
        dest = Path(temp_name) / "model.safetensors"
        partial = dest.with_name(dest.name + ".part")
        partial.write_bytes(payload[:split_at])
        with patch("scripts.install_workflow_assets.urllib.request.urlopen", side_effect=fake_urlopen):
            with contextlib.redirect_stdout(io.StringIO()):
                install_workflow_assets.download_file("https://example.invalid/model", dest, len(payload), retries=1)
        check(dest.read_bytes() == payload, "resumed download should produce exact file contents")
        check(not partial.exists(), "partial file should be replaced after a complete resumed download")

    with tempfile.TemporaryDirectory(prefix="wan22_stale_size_check_") as temp_name:
        dest = Path(temp_name) / "updated-model.safetensors"
        stale_expected = len(payload) - 39

        def stale_size_urlopen(request: object, timeout: int = 60) -> FakeResponse:
            del request, timeout
            return FakeResponse(payload, status=200, headers={"Content-Length": str(len(payload))})

        with patch("scripts.install_workflow_assets.urllib.request.urlopen", side_effect=stale_size_urlopen):
            captured = io.StringIO()
            with contextlib.redirect_stdout(captured):
                install_workflow_assets.download_file(
                    "https://example.invalid/updated-model",
                    dest,
                    stale_expected,
                    retries=1,
                )
        check(dest.read_bytes() == payload, "server size should override stale catalog metadata")
        check("[size-update]" in captured.getvalue(), "stale size correction should be visible in download logs")

    with tempfile.TemporaryDirectory(prefix="wan22_complete_part_check_") as temp_name:
        dest = Path(temp_name) / "model.safetensors"
        partial = dest.with_name(dest.name + ".part")
        partial.write_bytes(payload)
        with patch("scripts.install_workflow_assets.urllib.request.urlopen", side_effect=AssertionError("network should not be used for complete .part")):
            with contextlib.redirect_stdout(io.StringIO()):
                install_workflow_assets.download_file("https://example.invalid/model", dest, len(payload), retries=1)
        check(dest.read_bytes() == payload, "complete .part should be finalized without a network request")
        check(not partial.exists(), "complete .part should be renamed to the final model file")

    auth_request = install_workflow_assets.authenticated_request(
        "https://huggingface.co/Lightricks/LTX-2.5/resolve/main/test.safetensors",
        hf_token="hf_private_test_token",
    )
    mirror_request = install_workflow_assets.authenticated_request(
        "https://hf-mirror.example/Lightricks/LTX-2.5/resolve/main/test.safetensors",
        hf_token="hf_private_test_token",
    )
    check(
        auth_request.unredirected_hdrs.get("Authorization") == "Bearer hf_private_test_token"
        and "Authorization" not in auth_request.headers
        and "Authorization" not in mirror_request.unredirected_hdrs,
        "Hugging Face tokens should be attached only to the initial official request and not forwarded to mirrors",
    )
    with tempfile.TemporaryDirectory(prefix="ltx25_gated_check_") as temp_name:
        dest = Path(temp_name) / "gated.safetensors"
        forbidden = urllib.error.HTTPError(
            "https://huggingface.co/Lightricks/LTX-2.5/resolve/main/test.safetensors",
            403,
            "Forbidden",
            {},
            None,
        )
        with patch("scripts.install_workflow_assets.urllib.request.urlopen", side_effect=forbidden):
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    install_workflow_assets.download_file(
                        forbidden.url,
                        dest,
                        len(payload),
                        retries=1,
                        hf_token="hf_private_test_token",
                        gated=True,
                    )
            except RuntimeError as exc:
                gated_error = str(exc)
            else:
                gated_error = ""
        check(
            "Agree and Access" in gated_error and "hf auth login" in gated_error,
            "gated LTX 2.5 downloads should explain the license and authentication steps",
        )

    # Partial-file UI fixtures must not recursively search the user's model disks.
    with tempfile.TemporaryDirectory(prefix="wan22_partial_ui_check_") as temp_name, patch.object(
        frontend, "INSTALL_FIND_LOCAL_ASSET_CANDIDATE", return_value=None
    ):
        base_dir = Path(temp_name)
        first_asset = frontend.workflow_asset_manifest(base_dir)[0]
        partial = Path(first_asset["path"]).with_name(Path(first_asset["path"]).name + ".part")
        partial.parent.mkdir(parents=True, exist_ok=True)
        partial.write_bytes(b"partial")
        asset = next(item for item in frontend.collect_asset_checks(base_dir) if item["id"] == first_asset["id"])
        check(asset["partial_exists"] is True, "frontend asset checks should expose .part files")
        check(asset["remaining_gb"] is not None, "frontend asset checks should expose remaining download size")
        check("断点续传" in asset["reason"], "frontend asset reason should explain resumable partial downloads")
        tiny_path = base_dir / "models" / "tiny.bin"
        tiny_asset = {
            "id": "tiny_complete_part",
            "label": "Tiny complete part",
            "step": "self-check",
            "path": tiny_path,
            "bytes": len(payload),
            "installable": True,
        }
        tiny_partial = tiny_path.with_name(tiny_path.name + ".part")
        tiny_partial.parent.mkdir(parents=True, exist_ok=True)
        tiny_partial.write_bytes(payload)
        with patch("beginner_frontend.app.workflow_asset_manifest", return_value=[tiny_asset]):
            complete_part_asset = next(item for item in frontend.collect_asset_checks(base_dir) if item["id"] == "tiny_complete_part")
        check(complete_part_asset["remaining_gb"] == 0, "complete .part should show zero remaining download")
        check("自动转正" in complete_part_asset["reason"], "frontend asset reason should explain complete .part finalization")

    progress = frontend.initialize_install_progress(
        [
            {
                "id": "large_model",
                "label": "Large model",
                "item_type": "asset",
                "path": "models/diffusion_models/large.safetensors",
                "expected_gb": 2.0,
                "partial_gb": 0.5,
            },
            {
                "id": "text_encoder",
                "label": "Text encoder",
                "item_type": "asset",
                "path": "models/text_encoders/text.safetensors",
                "expected_gb": 1.0,
            },
        ]
    )
    check(progress["total_bytes"] == 3 * 1024**3, "install progress should include all estimated model bytes")
    check(progress["downloaded_bytes"] == int(0.5 * 1024**3), "install progress should include existing .part bytes")
    check(progress["percent"] == 16.7, "install progress should report overall package percentage")
    check(progress["files"][0]["item_type"] == "asset", "estimated model files should remain asset progress items")

    with tempfile.TemporaryDirectory(prefix="wan22_progress_reconcile_") as temp_name:
        base_dir = Path(temp_name)
        relative_path = Path("models/diffusion_models/reconcile.safetensors")
        partial = (base_dir / relative_path).with_name("reconcile.safetensors.part")
        partial.parent.mkdir(parents=True, exist_ok=True)
        partial.write_bytes(b"x" * 1024)
        reconcile_job = {
            "base_dir": str(base_dir),
            "status": "paused",
            "missing": [
                {
                    "id": "reconcile_model",
                    "path": str(relative_path),
                    "expected_gb": 2048 / 1024**3,
                }
            ],
            "progress": frontend.initialize_install_progress(
                [
                    {
                        "id": "reconcile_model",
                        "label": "Reconcile model",
                        "item_type": "asset",
                        "path": str(relative_path),
                        "expected_gb": 2048 / 1024**3,
                    }
                ]
            ),
        }
        frontend.reconcile_install_progress_from_disk(reconcile_job)
        check(reconcile_job["progress"]["downloaded_bytes"] == 1024, "progress reconciliation should read .part size")
        check(reconcile_job["progress"]["percent"] == 50.0, "progress reconciliation should preserve overall percentage")

    uncensored_encoder = next(
        item for item in install_workflow_assets.MODEL_FILES if item.get("id") == "flux2_uncensored_te_fp8"
    )
    check(
        int(uncensored_encoder.get("bytes") or 0) == 18_034_679_973,
        "FLUX.2 community encoder should use the verified remote object size",
    )

    with tempfile.TemporaryDirectory(prefix="wan22_download_center_check_") as temp_name:
        base_dir = Path(temp_name)
        model_path = base_dir / "models" / "text_encoders" / "center-model.safetensors"
        partial = model_path.with_name(model_path.name + ".part")
        partial.parent.mkdir(parents=True, exist_ok=True)
        partial.write_bytes(b"x" * 512)
        node_path = base_dir / "custom_nodes" / "center-node"
        node_path.mkdir(parents=True)
        roots = [
            {
                "label": "Test root",
                "path": str(base_dir),
                "role": "active",
                "exists": True,
                "models_path": str(base_dir / "models"),
                "custom_nodes_path": str(base_dir / "custom_nodes"),
            }
        ]
        manifest = [
            {
                "id": "center_model",
                "label": "Download center model",
                "path": model_path,
                "bytes": 1024,
                "url": "https://example.invalid/model",
            }
        ]
        node_manifest = [
            {
                "id": "center_node",
                "label": "Download center node",
                "path": node_path,
                "url": "https://example.invalid/node",
            }
        ]
        with patch("beginner_frontend.app.workflow_asset_manifest", return_value=manifest), patch(
            "beginner_frontend.app.custom_node_manifest", return_value=node_manifest
        ):
            resources = frontend.scan_download_center_resources(roots, force=True)
        resources = frontend.overlay_download_job_state(
            resources,
            {
                frontend.normalized_resource_path(model_path): {
                    "job_id": "download-center-job",
                    "job_status": "running",
                    "expected_bytes": 1024,
                    "label": "Download center model",
                }
            },
        )
        partial_resource = next(item for item in resources if item.get("resource_type") == "partial")
        check(partial_resource["status"] == "downloading", "download center should mark active .part files clearly")
        check(partial_resource["percent"] == 50.0, "download center should report filesystem-backed partial progress")
        check(
            any(item.get("kind") == "custom_node" and item.get("managed") for item in resources),
            "download center should include installed custom nodes",
        )

    return {"range_resume": True, "partial_ui_state": True, "download_center": True}


def service_mode_check() -> dict[str, object]:
    sys.path.insert(0, str(ROOT))
    from fastapi.testclient import TestClient
    from beginner_frontend import app as frontend

    with tempfile.TemporaryDirectory(prefix="multimodel_service_mode_") as temp_name:
        temp_config = Path(temp_name) / ".local_ai_workbench_config.json"
        with patch.object(frontend, "LOCAL_CONFIG_FILE", temp_config), patch.object(frontend, "LEGACY_LOCAL_CONFIG_FILES", ()):
            client = TestClient(frontend.app)
            config_response = client.get("/api/client-config")
            check(config_response.status_code == 200, "/api/client-config should be available")
            initial_service = config_response.json()["service"]
            check(initial_service["mode"] == "both", "unconfigured service mode should default to both")
            check(initial_service["first_run_required"] is True, "unconfigured service mode should prompt first-run selection")
            check(initial_service["bind_host"] == "127.0.0.1", "unconfigured service mode should keep the launcher local-only")
            check(initial_service["binds_lan"] is False, "unconfigured service mode should not advertise LAN binding")

            first_save = client.post("/api/service-config", json={"service": {"mode": "both"}})
            check(first_save.status_code == 200, "saving initial both mode should work")
            saved_service = first_save.json()["service"]
            check(saved_service["bind_host"] == "0.0.0.0", "both mode should bind LAN after restart")
            check("access_token" not in saved_service, "non-loopback service payload should omit access_token")
            check(saved_service.get("access_token_configured") is True, "server/both mode should report a configured token")
            token = str(json.loads(temp_config.read_text(encoding="utf-8")).get("access_token") or "")
            check(bool(token), "server/both mode should create an access token")

            denied = client.post("/api/service-config", json={"service": {"mode": "server"}})
            check(denied.status_code == 401, "remote write should require a token after token is configured")

            headers = {"X-Local-AI-Token": token}
            server_save = client.post("/api/service-config", json={"service": {"mode": "server", "access_token": token}}, headers=headers)
            check(server_save.status_code == 200, "saving server mode with token should work")
            check(server_save.json()["service"]["bind_host"] == "0.0.0.0", "server mode should bind LAN after restart")

            client_save = client.post(
                "/api/service-config",
                json={"service": {"mode": "client", "server_url": "http://192.168.1.20:7860", "access_token": token}},
                headers=headers,
            )
            check(client_save.status_code == 200, "saving client mode with token should work")
            client_service = client_save.json()["service"]
            check(client_service["bind_host"] == "127.0.0.1", "client mode should stay local-only")
            check(client_service["api_base_url"] == "http://192.168.1.20:7860", "client mode should expose remote API base URL")
            health_response = client.get("/api/health")
            check("service" in health_response.json(), "/api/health should expose service metadata")

    frontend_js_text = (ROOT / "beginner_frontend" / "static" / "app.js").read_text(encoding="utf-8")
    index_text = (ROOT / "beginner_frontend" / "static" / "index.html").read_text(encoding="utf-8")
    launcher_text = (ROOT / "START_WORKFLOW.py").read_text(encoding="utf-8")
    check("servicePanel" in index_text and "运行入口模式" in index_text, "frontend should render a first-run service panel")
    check("rewriteApiUrl" in frontend_js_text and "/api/client-config" in frontend_js_text, "frontend should route API calls through selected service mode")
    check("mediaUrl(item.url)" in frontend_js_text, "remote client mode should render media links against the service API")
    check("保存并重启后显示" in frontend_js_text, "first-run service panel should not show LAN URL before the mode is saved")
    check("frontend_bind_host" in launcher_text and "WAN22_NODE_MODE" in launcher_text, "launcher should honor saved service mode when choosing bind host")
    return {"modes": ["both", "server", "client"], "token_required": True}


def package_check() -> dict[str, int]:
    check(PACKAGE.exists(), "github_upload package directory missing")
    bad: list[str] = []
    local_path_hits: list[str] = []
    scanned_paths = package_paths()
    for path in scanned_paths:
        if POLLUTION_RE.search(path.name):
            bad.append(rel(path))
        if not path.is_file() or path.name == "self_check.py" or path.suffix.lower() not in TEXT_SCAN_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for label, pattern in LOCAL_PATH_PATTERNS:
            if pattern.search(text):
                local_path_hits.append(f"{rel(path)} contains {label}")
    check(not bad, "release package contains local/generated artifacts: " + ", ".join(bad[:20]))
    check(not local_path_hits, "release package contains local machine paths: " + "; ".join(local_path_hits[:20]))
    required = [
        PACKAGE / "README.md",
        PACKAGE / "START_HERE.md",
        PACKAGE / "BEGINNER_FRONTEND_GUIDE.md",
        PACKAGE / "PROJECT_REVIEW.md",
        PACKAGE / "requirements.txt",
        PACKAGE / "requirements.lock",
        PACKAGE / "START_WORKFLOW.bat",
        PACKAGE / "START_WORKFLOW.py",
        PACKAGE / "START_WORKFLOW.ps1",
        PACKAGE / "START_WORKFLOW.command",
        PACKAGE / "beginner_frontend" / "app.py",
        PACKAGE / "beginner_frontend" / "model_catalog.py",
        PACKAGE / "beginner_frontend" / "social_presets.py",
        PACKAGE / "beginner_frontend" / "video_params.py",
        PACKAGE / "beginner_frontend" / "static" / "app.js",
        PACKAGE / "beginner_frontend" / "static" / "download-center.js",
        PACKAGE / "beginner_frontend" / "static" / "index.html",
        PACKAGE / "scripts" / "prerequisite_doctor.py",
        PACKAGE / "scripts" / "release_smoke.py",
        PACKAGE / "scripts" / "clean_bootstrap_smoke.py",
        PACKAGE / "scripts" / "check_fal_h3_max_release.py",
        PACKAGE / "scripts" / "test_platform_upgrade.py",
        PACKAGE / "scripts" / "test_qwen_image_21.py",
        PACKAGE / "scripts" / "configure_fal_h3_max.ps1",
        PACKAGE / "config" / "fal_h3_max.json",
    ]
    missing = [rel(path) for path in required if not path.exists()]
    check(not missing, "release package missing required files: " + ", ".join(missing))
    batch_text = (PACKAGE / "START_WORKFLOW.bat").read_text(encoding="utf-8")
    check("ExecutionPolicy Bypass" in batch_text, "Windows batch launcher must bypass PowerShell execution policy")
    check("START_WORKFLOW.ps1" in batch_text, "Windows batch launcher must delegate to START_WORKFLOW.ps1")
    check("--check" in batch_text, "Windows batch launcher should expose a non-starting check mode")
    check("python START_WORKFLOW.py" in batch_text, "Windows batch launcher should explain no-PowerShell fallback")
    return {"files": sum(1 for path in scanned_paths if path.is_file()), "source_mode": int(PACKAGE == ROOT)}


def keyword_check() -> list[str]:
    paths = [
        ROOT / "START_WORKFLOW.py",
        ROOT / "START_WORKFLOW.bat",
        ROOT / "START_WORKFLOW.ps1",
        ROOT / "START_WORKFLOW.command",
        ROOT / "beginner_frontend",
        ROOT / "scripts",
        ROOT / "workflows",
        ROOT / "BEGINNER_FRONTEND_GUIDE.md",
        *([PACKAGE] if PACKAGE != ROOT else []),
    ]
    patterns = ["%date:", "frontend_7860", "No module named uvicorn", "旧入口仍可用", "只下载 LTX", "Windows/Linux：默认走 CUDA"]
    hits: list[str] = []
    for path in paths:
        candidates = [path] if path.is_file() else [
            item
            for item in path.rglob("*")
            if item.is_file() and not any(part in DEVELOPMENT_EXCLUDED_NAMES for part in item.relative_to(ROOT).parts)
        ]
        for item in candidates:
            if item.name == "self_check.py":
                continue
            try:
                text = item.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for pattern in patterns:
                if pattern in text:
                    hits.append(f"{rel(item)} contains {pattern}")
    check(not hits, "stale keyword hits: " + "; ".join(hits[:20]))
    return [f"{len(patterns)} stale patterns checked"]


def platform_upgrade_check() -> dict[str, object]:
    from scripts import test_platform_upgrade as upgrade
    from scripts import test_h3_creative as creative

    checks = [
        upgrade.check_social_recipes,
        upgrade.check_h3_reference_graph,
        upgrade.check_ltx_profiles,
        upgrade.check_h3_profile_schedules,
        upgrade.check_h3_profile_manifest_and_status,
        upgrade.check_h3_missing_lora_preflight,
        upgrade.check_h3_optional_reference_schema,
        upgrade.check_adult_boundary,
        upgrade.check_frontend_contract,
        *creative.CHECKS,
    ]
    for item in checks:
        item()
    return {"cpu_only": True, "checks": [item.__name__ for item in checks]}


def qwen_image_21_check() -> dict[str, object]:
    from scripts import test_qwen_image_21 as qwen21

    return {"cpu_only": True, "checks": qwen21.run_all()}


def qwen21_updates_check() -> dict[str, object]:
    from scripts import test_qwen21_updates as updates

    checks = [updates.check_manifest, updates.check_graphs, updates.check_readiness]
    for check_fn in checks:
        check_fn()
    return {"cpu_only": True, "checks": [fn.__name__ for fn in checks]}


def run_all() -> dict[str, object]:
    return {
        "python_ast": ast_check(),
        "javascript": js_check(),
        "manifest": manifest_check(),
        "workflows": workflow_check(),
        "hardware_matrix": hardware_matrix_check(),
        "fallbacks": fallback_check(),
        "downloads": download_resume_check(),
        "service_mode": service_mode_check(),
        "platform_upgrade": platform_upgrade_check(),
        "qwen_image_21": qwen_image_21_check(),
        "qwen21_updates": qwen21_updates_check(),
        "workbench_logic": workbench_logic_check(),
        "package": package_check(),
        "stale_keywords_absent": keyword_check(),
    }


def workbench_logic_check() -> dict[str, object]:
    from scripts.test_workbench_logic import run_all as check_logic
    checks = check_logic()
    node = shutil_which("node")
    if node:
        for name in ("state", "journey"):
            result = subprocess.run([node, str(ROOT / f"scripts/test_workbench_{name}.cjs")], capture_output=True, text=True)
            check(result.returncode == 0, result.stderr)
            checks.append(f"workflow_{name}_node")
    return {"cpu_only": True, "checks": checks}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run repository smoke checks for the local video workflow.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()
    try:
        result = run_all()
    except Exception as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        else:
            print(f"SELF CHECK FAILED: {exc}")
        return 1
    if args.json:
        print(json.dumps({"ok": True, "result": result}, ensure_ascii=False, indent=2))
    else:
        print("SELF CHECK OK")
        for key, value in result.items():
            print(f"- {key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
