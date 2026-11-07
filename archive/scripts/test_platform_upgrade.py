"""CPU-only regression checks for the multi-model platform upgrade.

This script does not connect to ComfyUI, import torch, or submit inference.
Run it with: python scripts/test_platform_upgrade.py
"""

from __future__ import annotations

import os
import sys
import asyncio
import json
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import AsyncMock, patch

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "-1")
os.environ.setdefault("BEGINNER_FRONTEND_DISABLE_GPU_PROBES", "1")
os.environ.setdefault("BEGINNER_FRONTEND_DISABLE_JOB_PERSISTENCE", "1")
sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from beginner_frontend import video_params
from beginner_frontend import app as frontend
from beginner_frontend.model_catalog import MODEL_ASSETS, INSTALL_PROFILES
from beginner_frontend.app import (
    MINIMAX_H3_REF2VA_MODEL,
    apply_unrestricted_prompt_text,
    build_minimax_h3_reference_prompt,
    ltx25_pipeline_settings,
)
from beginner_frontend.social_presets import social_presets_payload


class IdCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if name == "id" and value:
                self.ids.append(value)


def check_social_recipes() -> None:
    payload = social_presets_payload()
    assert len(payload["targets"]) >= 8
    for engine, targets in payload["recipes"].items():
        for target_id, tiers in targets.items():
            for quality_id, recipe in tiers.items():
                width = recipe["generation"]["width"]
                height = recipe["generation"]["height"]
                length = recipe["generation"]["length"]
                assert width % 32 == 0 and height % 32 == 0, (engine, target_id, quality_id)
                if engine == "minimax_h3":
                    assert (length - 5) % 17 == 0
                    assert recipe["generation"]["fps"] == 24
                elif engine == "ltx25":
                    assert (length - 1) % 8 == 0


def check_h3_reference_graph() -> None:
    graph = build_minimax_h3_reference_prompt(
        prompt="<Picture 1> walks through <Video 1> while <Audio 1> plays.",
        negative="",
        reference_images=["person.png"],
        reference_videos=["motion.mp4"],
        reference_audios=["voice.wav"],
        width=864,
        height=480,
        length=73,
        fps=24,
        seed=1,
        steps=20,
        cfg=1.0,
    )
    assert graph["1"]["inputs"]["unet_name"] == MINIMAX_H3_REF2VA_MODEL
    assert graph["5"]["class_type"] == "MiniMaxH3ReferenceToVideo"
    inputs = graph["5"]["inputs"]
    assert "ref_images.ref_image_0" in inputs
    assert "ref_videos.ref_video_0" in inputs
    assert "ref_video_audios.ref_video_audio_0" in inputs
    assert "ref_audios.ref_audio_0" in inputs
    assert sum(item["class_type"] == "LoadImage" for item in graph.values()) == 1
    assert sum(item["class_type"] == "VHS_LoadVideo" for item in graph.values()) == 1
    assert sum(item["class_type"] == "LoadAudio" for item in graph.values()) == 1


def check_ltx_profiles() -> None:
    preview = video_params.resolve("ltx25_t2v", {"ltx25_pipeline_profile": "preview"})
    quality = video_params.resolve("ltx25_t2v", {"ltx25_pipeline_profile": "quality"})
    custom = video_params.resolve(
        "ltx25_t2v",
        {
            "ltx25_pipeline_profile": "custom",
            "spatial_upscale": False,
            "ltx25_decoder": "diffusion",
        },
    )
    assert ltx25_pipeline_settings(preview) == {"profile": "preview", "two_stage": False, "decoder": "conv"}
    assert ltx25_pipeline_settings(quality) == {"profile": "quality", "two_stage": True, "decoder": "diffusion"}
    assert ltx25_pipeline_settings(custom) == {"profile": "custom", "two_stage": False, "decoder": "diffusion"}


def h3_test_graph(profile: str, mode: str = "minimax_h3_t2v") -> dict:
    kwargs = dict(
        prompt="A slow pan across a quiet city.", negative="", width=1280, height=736,
        length=124, fps=24, seed=1, steps=31, cfg=1,
        adv=video_params.resolve(mode, {
            "h3_acceleration_profile": profile, "h3_shift_video": 8,
            "h3_shift_audio": 5, "denoise": 0.5,
        }),
    )
    if mode == "minimax_h3_r2v":
        return build_minimax_h3_reference_prompt(
            **kwargs, reference_images=["person.png"], reference_videos=[], reference_audios=[],
        )
    return frontend.build_minimax_h3_prompt(**kwargs, image_name="frame.png" if mode.endswith("i2v") else "")


def check_h3_profile_schedules() -> None:
    expected = {
        "lightx8_v10": (8, 12), "lightx_ref4_v01": (4, 12),
        "lightx8_v10_768p": (8, 6), "lightx4_v11_768p": (4, 6),
        "lightx4_v12_768p": (4, 6), "spectrum_balanced": (20, 12),
    }
    for profile, (steps, shift) in expected.items():
        modes = ["minimax_h3_r2v"] if profile == "lightx_ref4_v01" else ["minimax_h3_t2v", "minimax_h3_i2v"]
        for mode in modes:
            graph = h3_test_graph(profile, mode)
            recipe = video_params.H3_RUNTIME_PROFILES[profile]
            assert graph["4"]["inputs"]["shift_video"] == shift, profile
            assert graph["4"]["inputs"]["shift_audio"] == 3, profile
            assert graph["8"]["inputs"]["steps"] == steps, profile
            assert graph["8"]["inputs"]["denoise"] == 1, profile
            assert graph["8"]["inputs"]["scheduler"] == "simple", profile
            assert graph["7"]["inputs"]["sampler_name"] == recipe["sampler"], profile
            if recipe.get("lora_name"):
                assert graph["30"]["inputs"]["lora_name"] == recipe["lora_name"], profile
                assert graph["4"]["inputs"]["model"] == ["30", 0], profile
            assert not frontend.validate_graph(graph), profile
    native = h3_test_graph("native")
    assert native["4"]["inputs"]["shift_video"] == 8
    assert native["4"]["inputs"]["shift_audio"] == 5
    assert native["8"]["inputs"]["steps"] == 31 and native["8"]["inputs"]["denoise"] == 0.5
    assert "30" not in native and "31" not in native


def check_h3_profile_manifest_and_status() -> None:
    assets = {item["id"]: item for item in MODEL_ASSETS}
    for key, recipe in video_params.H3_RUNTIME_PROFILES.items():
        if not recipe.get("asset_id"):
            continue
        asset = assets[recipe["asset_id"]]
        assert asset["name"] == recipe["lora_name"], key
        assert len(asset["sha256"]) == 64 and asset["bytes"] > 0, key
        install = "minimax-h3-ref2va-int8" if key.startswith("lightx_ref") else "minimax-h3-fl2va-int8"
        assert asset["id"] in INSTALL_PROFILES[install]["asset_ids"], key
    for mode in ["minimax_h3_t2v", "minimax_h3_i2v", "minimax_h3_r2v"]:
        schema = frontend.workflow_advanced_param_schema(mode, [], frontend.collect_node_checks(None))
        spec = next(item for item in schema if item["id"] == "h3_acceleration_profile")
        assert set(spec["choice_details"]) == set(spec["choices"]) - {"native"}
        for key, info in spec["choice_details"].items():
            if info.get("asset_id"):
                assert spec["choice_status"][key]["state"] == "missing"
        if mode == "minimax_h3_r2v":
            assert spec["choices"] == ["native", "lightx_ref4_v01"]
        else:
            assert "lightx_ref4_v01" not in spec["choices"]
            assert spec["choice_status"]["spectrum_balanced"]["state"] == "unchecked"
    ready = frontend.workflow_advanced_param_schema(
        "minimax_h3_t2v", [{"id": "minimax_h3_lightx4_v11_768p", "ok": True}], [],
    )
    spec = next(item for item in ready if item["id"] == "h3_acceleration_profile")
    assert spec["choice_status"]["lightx4_v11_768p"]["state"] == "installed"
    assert spec["choice_status"]["lightx4_v12_768p"]["state"] == "missing"
    assert "待预检" in spec["choice_status"]["lightx4_v11_768p"]["label"]
    fresh = next(item for item in video_params.param_schema("minimax_h3_t2v") if item["id"] == spec["id"])
    assert "choice_status" not in fresh, "availability leaked between requests"


def check_h3_missing_lora_preflight() -> None:
    from fastapi.testclient import TestClient

    graph = h3_test_graph("lightx8_v10_768p")
    # Mimic the registry with every required model except the selected LoRA.
    registry = {item["class_type"]: {"input": {"required": {}}} for item in graph.values()}
    for item in graph.values():
        for name in ("unet_name", "clip_name", "vae_name", "lora_name"):
            if name in item["inputs"]:
                choices = registry[item["class_type"]]["input"]["required"].setdefault(name, [[]])[0]
                if name != "lora_name":
                    choices.append(item["inputs"][name])
    selected = video_params.H3_RUNTIME_PROFILES["lightx8_v10_768p"]["lora_name"]
    older = video_params.H3_RUNTIME_PROFILES["lightx8_v10"]["lora_name"]
    registry["LoraLoaderModelOnly"]["input"]["required"]["lora_name"] = [[f"MiniMaxH3\\{older}"]]
    resolved = frontend.resolve_graph_model_option_names(graph, registry)
    errors = frontend.graph_model_registry_errors(resolved, registry)
    assert len(errors) == 1 and selected in errors[0] and "下载中心" in errors[0]
    assert resolved["30"]["inputs"]["lora_name"] == selected, "must not fall back to legacy LoRA"
    with patch.object(frontend, "active_comfy_paths", AsyncMock(return_value={})), \
         patch.object(frontend, "get_comfy_object_info", AsyncMock(return_value=registry)), \
         patch.object(frontend, "comfy_node_availability", AsyncMock(return_value={"missing": [], "error": ""})), \
         patch.object(frontend, "comfy_get", AsyncMock(return_value={})), \
         patch.object(frontend, "build_hardware_summary", return_value={"accelerator": "cuda", "max_vram_gb": 96}), \
         patch.object(frontend, "graph_node_schema_errors", return_value=[]), \
         patch.object(frontend, "comfy_post", AsyncMock(side_effect=AssertionError("No inference allowed"))) as submit:
        preview = asyncio.run(frontend.workflow_preview(
            mode="minimax_h3_t2v", steps=31, include_graph=True,
            advanced=json.dumps({"h3_acceleration_profile": "lightx8_v10_768p"}),
        ))
        assert not preview["ok"] and any(selected in error for error in preview["errors"])
        assert preview["parameters"]["steps"] == 8
        assert preview["parameters"]["h3_runtime"]["shift_video"] == 6
        client = TestClient(frontend.app)
        response = client.post("/api/generate", data={
            "mode": "minimax_h3_t2v", "prompt": "A quiet city", "steps": "31",
            "advanced": json.dumps({"h3_acceleration_profile": "lightx8_v10_768p"}),
        })
        assert response.status_code == 400, response.text
        assert selected in response.text and "下载中心" in response.text, response.text
        submit.assert_not_called()
        client.close()
    for prefix in ["MiniMaxH3/", "MiniMaxH3\\"]:
        registry["LoraLoaderModelOnly"]["input"]["required"]["lora_name"] = [[prefix + selected]]
        resolved = frontend.resolve_graph_model_option_names(graph, registry)
        assert resolved["30"]["inputs"]["lora_name"] == prefix + selected
        assert not frontend.graph_model_registry_errors(resolved, registry)


def check_h3_optional_reference_schema() -> None:
    optional = {}
    for group, prefix, maximum in [
        ("ref_images", "ref_image_", 9), ("ref_videos", "ref_video_", 3),
        ("ref_video_audios", "ref_video_audio_", 3), ("ref_audios", "ref_audio_", 3),
    ]:
        optional[group] = ["COMFY_AUTOGROW_V3", {"template": {
            "input": {"required": {prefix.rstrip("_"): ["IMAGE", {}]}},
            "prefix": prefix, "min": 0, "max": maximum,
        }}]
    registry = {"MiniMaxH3ReferenceToVideo": {"input": {"required": {}, "optional": optional}}}
    fields = {"ref_images.ref_image_0": ["50", 0], "ref_images.ref_image_8": ["51", 0],
              "ref_videos.ref_video_0": ["52", 0], "ref_video_audios.ref_video_audio_0": ["52", 2],
              "ref_audios.ref_audio_2": ["53", 0]}
    graph = {"5": {"class_type": "MiniMaxH3ReferenceToVideo", "inputs": fields}}
    assert not frontend.graph_node_schema_errors(graph, registry)
    for invalid in ["ref_images.ref_image_9", "ref_images.wrong_0", "ref_videos.ref_video_3", "ref_audios.ref_audio_-1"]:
        fields[invalid] = ["50", 0]
        errors = frontend.graph_node_schema_errors(graph, registry)
        assert any(invalid in error for error in errors), invalid
        del fields[invalid]
    graph["5"]["inputs"] = {}
    assert not frontend.graph_node_schema_errors(graph, registry), "optional reference groups must remain optional"


def check_adult_boundary() -> None:
    prompt, _negative = apply_unrestricted_prompt_text(
        "cinematic private scene",
        "",
        enabled=True,
        playbook={"linkage": {}},
    )
    assert "consenting adults aged 21 or older" in prompt
    assert "without authorization" in prompt


def check_frontend_contract() -> None:
    parser = IdCollector()
    parser.feed((ROOT / "beginner_frontend" / "static" / "index.html").read_text(encoding="utf-8"))
    assert len(parser.ids) == len(set(parser.ids)), "index.html contains duplicate ids"
    required = {
        "socialPlatformSelect",
        "socialQualitySwitch",
        "socialGenerationSize",
        "referenceMediaInput",
        "referenceMediaList",
        "adultContentAck",
    }
    assert required.issubset(set(parser.ids)), sorted(required - set(parser.ids))


def main() -> None:
    checks = [
        check_social_recipes,
        check_h3_reference_graph,
        check_ltx_profiles,
        check_h3_profile_schedules,
        check_h3_profile_manifest_and_status,
        check_h3_missing_lora_preflight,
        check_h3_optional_reference_schema,
        check_adult_boundary,
        check_frontend_contract,
    ]
    for check in checks:
        check()
        print(f"PASS {check.__name__}")
    print(f"PASS all {len(checks)} CPU-only platform checks")


if __name__ == "__main__":
    main()
