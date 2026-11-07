"""CPU-only regression for the October Qwen 2.1 additions."""
from __future__ import annotations

import asyncio
import copy
import os
from pathlib import Path
import sys
import tempfile
from contextlib import ExitStack
from unittest.mock import AsyncMock, patch

os.environ["BEGINNER_FRONTEND_DISABLE_GPU_PROBES"] = "1"
os.environ["BEGINNER_FRONTEND_DISABLE_JOB_PERSISTENCE"] = "1"
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from beginner_frontend import app as backend
from beginner_frontend.image_studio import IMAGE_PROFILES, ASPECT_PRESETS, image_profile, build_image_prompt
from beginner_frontend.model_catalog import MODEL_ASSETS, INSTALL_PROFILES, MODEL_CATALOG
from beginner_frontend.qwen21_updates import ASSETS


def graph(profile, **kwargs):
    return build_image_prompt(prompt="A ceramic cup on a table", negative="blur", width=1024,
                              height=1024, seed=3, profile_id=profile, **kwargs)


def check_manifest():
    for rows in (IMAGE_PROFILES, MODEL_ASSETS, MODEL_CATALOG):
        ids = [row["id"] for row in rows]
        assert len(ids) == len(set(ids)), "Duplicate registry IDs"
    by_id = {row["id"]: row for row in MODEL_ASSETS}
    for asset in ASSETS:
        assert len(asset["sha256"]) == 64 and "/resolve/main/" not in asset["url"]
        profile = image_profile(asset["id"])
        assert profile["id"] == asset["id"]
        assert all(key in by_id for key in profile["required_asset_ids"] + profile["optional_asset_ids"])
        assert profile["install_profile"] in INSTALL_PROFILES
        assert all(asset["id"] in p["profiles"] for p in ASPECT_PRESETS if p["id"].startswith("qwen21-"))
    legacy = by_id["qwen_image_21_uncensored_q8"]
    assert legacy["sha256"] == "763ee46b76069d9c54ab26719a0b9222575751560c8bf3a48275736c44351c0e"
    assert all(asset["dest"] != legacy["dest"] for asset in ASSETS)


def check_graphs():
    for asset in ASSETS:
        profile = image_profile(asset["id"])
        before = copy.deepcopy(profile)
        edit_only = profile.get("generation_supported") is False
        for source in (["target.png"] if edit_only else ["", "target.png"]):
            params = {"source_image": source, "reference_images": ["ref.png"] if source else []}
            standard = graph(profile["id"], **params)
            assert not backend.validate_graph(standard)
            assert graph(profile["id"], **params, nsfw=False) == standard
            sampler = standard["7"]["inputs"]
            assert sampler["steps"] == (8 if profile["id"] == "qwen21_turbo_int8" else 25)
            assert sampler["cfg"] == 1.0
            if source:
                assert standard["7"]["inputs"]["latent_image"] == ["5", 2]
                assert standard["5"]["inputs"]["images.image_2"] == ["22", 0]
            if asset.get("sensitive"):
                enabled = graph(profile["id"], **params, nsfw=True, nsfw_lora_strength=0.7)
                assert not backend.validate_graph(enabled)
                if "q8" in profile["id"]:
                    assert enabled["1"]["class_type"] == "UnetLoaderGGUF"
                    assert "UC-Q8" in enabled["1"]["inputs"]["unet_name"]
                elif "int8" in profile["id"]:
                    assert enabled["1"]["class_type"] == "UNETLoader"
                    assert "UC-int8" in enabled["1"]["inputs"]["unet_name"]
                else:
                    assert enabled["16"]["inputs"]["strength_model"] == 0.7
                    zero = graph(profile["id"], **params, nsfw=True, nsfw_lora_strength=0)
                    assert zero == standard
                assert graph(profile["id"], **params, nsfw=False) == standard
            if edit_only:
                assert standard["15"]["inputs"]["lora_name"] == profile["lora"]
                assert standard["4"]["inputs"]["model"] == ["15", 0]
        if edit_only:
            try:
                graph(profile["id"])
            except ValueError:
                pass
            else:
                raise AssertionError("Edit-only LoRA accepted T2I")
        assert profile == before, "Builder mutated shared configuration"
    turbo = graph("qwen21_turbo_int8", steps=50, cfg=9, sampler="heun", scheduler="beta")
    assert turbo["7"]["inputs"]["steps"] == 8
    assert turbo["7"]["inputs"]["sampler_name"] == "euler"
    assert turbo["7"]["inputs"]["scheduler"] == "simple"
    legacy = graph("qwen_image_21_int8", nsfw=True)
    assert "Community-202610" not in legacy["1"]["inputs"]["unet_name"]


def check_readiness():
    for asset in [a for a in ASSETS if a.get("sensitive")]:
        profile = image_profile(asset["id"])
        config = profile["nsfw"]
        node = config.get("model_loader") or "LoraLoaderModelOnly"
        field = "lora_name" if config.get("lora_name") else "unet_name"
        name = config.get("lora_name") or config["model_override"]
        schema = {node: {"input": {"required": {field: [[name.replace("/", "\\")], {}]}}}}
        assets = [{"id": key, "ok": True} for key in profile["required_asset_ids"] + profile["optional_asset_ids"]]
        with tempfile.TemporaryDirectory() as temp, ExitStack() as stack:
            base = Path(temp)
            entry = base / "custom_nodes/ComfyUI-GGUF/__init__.py"
            entry.parent.mkdir(parents=True)
            entry.touch()
            stack.enter_context(patch.object(backend, "active_comfy_paths", AsyncMock(return_value={
                key: base for key in ("base_dir", "input_dir", "output_dir", "temp_dir", "user_dir")})))
            objects = stack.enter_context(patch.object(backend, "get_comfy_object_info", AsyncMock(return_value={})))
            stack.enter_context(patch.object(backend, "collect_asset_checks", return_value=assets))
            stack.enter_context(patch.object(backend, "IMAGE_PROFILES", [profile]))
            stack.enter_context(patch.object(backend, "read_local_config", return_value={}))
            stack.enter_context(patch.object(backend, "face_swap_capability_payload", return_value={}))
            stack.enter_context(patch.object(backend, "model_storage_candidates", return_value=[]))
            stack.enter_context(patch.object(backend, "image_studio_job_history_page", return_value={"items": []}))

            def status():
                return asyncio.run(backend.image_studio_bootstrap(profile=profile["id"], target_dir=str(base)))["profiles"][0]["nsfw"]

            assert status()["addon_installed"] and not status()["addon_ready"]
            objects.return_value = schema
            assert status()["addon_ready"]
            objects.return_value = {node: {"input": {"required": {field: [[], {}]}}}}
            assert not status()["addon_ready"]
            objects.side_effect = backend.HTTPException(503, "offline")
            assert not status()["addon_ready"]
            objects.side_effect = None
            objects.return_value = schema
            assets[-1]["ok"] = False
            assert not status()["addon_installed"] and not status()["addon_ready"]


if __name__ == "__main__":
    for check in (check_manifest, check_graphs, check_readiness):
        check()
        print(f"PASS {check.__name__}")
    assert "torch" not in sys.modules
    print("PASS: no torch import, no inference, no live API requests")
