"""Offline H3 creative workflow contracts. No torch imports or GPU requests."""

import asyncio
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import AsyncMock, patch

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "-1")
os.environ.setdefault("BEGINNER_FRONTEND_DISABLE_GPU_PROBES", "1")
os.environ.setdefault("BEGINNER_FRONTEND_DISABLE_JOB_PERSISTENCE", "1")
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException, UploadFile
from fastapi.testclient import TestClient
from beginner_frontend import app, h3_workflows as h3, video_params
from beginner_frontend.model_catalog import MODEL_ASSETS, INSTALL_PROFILES


def base(mode="minimax_h3_t2v", **options):
    adv = video_params.resolve(mode, options)
    kwargs = dict(prompt="A dancer moves slowly in a studio.", negative="", width=1920, height=1088,
                  length=124, fps=24, seed=42, steps=20, cfg=1, adv=adv)
    if mode == "minimax_h3_r2v":
        graph = app.build_minimax_h3_reference_prompt(**kwargs, reference_images=["a.png"] * 9,
                                                     reference_videos=["a.mp4"] * 3, reference_audios=["a.wav"] * 3)
    else:
        graph = app.build_minimax_h3_prompt(**kwargs, image_name="a.png" if mode.endswith("i2v") else "")
    return graph, adv


def check_graph_routes():
    for mode in h3.H3_MODES:
        graph, adv = base(mode)
        assert h3.apply_extensions(graph, mode, adv) == graph, "default baseline changed"
        original = deepcopy(graph)
        adv["h3_attention_backend"] = "kitchen_int8"
        result = h3.apply_extensions(graph, mode, adv)
        assert graph == original, "builder mutated its input"
        assert result["180"]["inputs"]["model"] == ["4", 0]
        assert result["8"]["inputs"]["model"] == result["9"]["inputs"]["model"] == ["180", 0]
        assert result["2"] == graph["2"] and not app.validate_graph(result)
    for task in ("control", "inpaint"):
        for mask_video in (False, True):
            graph, adv = base(h3_task=task)
            result = h3.apply_extensions(graph, "minimax_h3_t2v", adv, control_name="control.mp4",
                                        source_name="source.mp4", mask_name="mask.mp4" if mask_video else "mask.png",
                                        mask_is_video=mask_video, source_has_audio=True)
            assert result["186"]["class_type"] == "MiniMaxH3FunControlNetApply"
            assert result["8"]["inputs"]["model"] == ["186", 0]
            assert not app.validate_graph(result)
            assert result["182"]["inputs"]["frame_load_cap"] == 124
            if task == "control":
                assert result["183"]["class_type"] == "Canny"
                adv["h3_control_type"] = "pose"
                pose = h3.apply_extensions(graph, "minimax_h3_t2v", adv, control_name="pose.mp4")
                assert pose["186"]["inputs"]["control_video"] == ["182", 0]
                assert "183" not in pose
            else:
                assert result["187"]["inputs"]["destination"] == ["182", 0]
                assert result["187"]["inputs"]["mask"] == ["185", 0]
                assert result["16"]["inputs"]["image"] == ["187", 0]
                assert result["12"]["inputs"]["audio"] == ["182", 2]
                silent = h3.apply_extensions(graph, "minimax_h3_t2v", adv, source_name="source.mp4", mask_name="mask.png")
                assert "audio" not in silent["12"]["inputs"]


def check_latent_upscale():
    for mode in h3.H3_MODES:
        graph, adv = base(mode, h3_latent_upscale=True)
        result = h3.apply_extensions(graph, mode, adv)
        assert result["5"]["inputs"]["width"] == 1280
        assert result["5"]["inputs"]["height"] == 736
        assert result["195"]["inputs"]["width"] == 1920
        assert result["195"]["inputs"]["height"] == 1088
        assert result["191"]["inputs"]["latent"] == ["190", 0], "must split nested AV"
        assert result["191"]["inputs"]["mode.width"] == 1920
        assert result["193"]["inputs"]["samples"] == ["190", 1]
        assert result["192"]["inputs"]["value"] == 0, "audio must not receive refine noise"
        assert result["197"]["inputs"]["conditioning"] == ["195", 0]
        assert result["11"]["inputs"]["samples"] == ["198", 0]
        assert result["15"]["inputs"]["samples"] == ["10", 0], "delivery audio must remain original"
        assert result["16"]["inputs"]["height"] == 1080
        assert result["196"]["inputs"]["steps"] == 8
        assert isinstance(result["196"]["inputs"]["steps"], int)
        if mode.endswith("r2v"):
            assert all(result[str(i)] == graph[str(i)] for i in range(50, 65))
            assert result["195"]["inputs"]["ref_images.ref_image_0"] == ["50", 0]
        if mode.endswith("i2v"):
            assert result["195"]["inputs"]["first_frame"] == ["20", 0]
        assert not app.validate_graph(result)
    assert h3.dimensions(1088, 1920, 2)["delivery"] == [1080, 1920]


def check_dynamic_schema():
    schema = {"MinimaxH3LatentUpscaler3D": {"input": {"required": {
        "mode": ["COMFY_DYNAMICCOMBO_V3", {"options": [
            {"key": "target dimensions", "inputs": {"required": {"width": ["INT"], "height": ["INT"]}}},
            {"key": "scale by multiplier", "inputs": {"required": {"scale": ["FLOAT"]}}},
        ]}],
    }}}}
    original = deepcopy(schema)
    inputs = {"mode": "target dimensions", "mode.width": 1920, "mode.height": 1088}
    graph = {"1": {"class_type": "MinimaxH3LatentUpscaler3D", "inputs": inputs}}
    assert not app.graph_node_schema_errors(graph, schema)
    del inputs["mode.height"]
    assert "mode.height" in " ".join(app.graph_node_schema_errors(graph, schema))
    inputs["mode.scale"] = 2
    assert "mode.scale" in " ".join(app.graph_node_schema_errors(graph, schema))
    assert schema == original, "live schema must not be mutated"
    inputs.update(mode="scale by multiplier")
    del inputs["mode.width"]
    assert not app.graph_node_schema_errors(graph, schema)


def check_guards_and_manifest():
    for options in ({"h3_task": "control"}, {"h3_task": "inpaint"},
                    {"h3_task": "control", "h3_latent_upscale": True},
                    {"h3_latent_upscale": True, "h3_acceleration_profile": "lightx4_v12_768p"}):
        adv = video_params.resolve("minimax_h3_t2v", options)
        assert h3.requirement_errors("minimax_h3_t2v", adv)
    adv = video_params.resolve("minimax_h3_r2v", {"h3_task": "control"})
    assert h3.requirement_errors("minimax_h3_r2v", adv, control=True)
    graph, adv = base(h3_attention_backend="kitchen_int8")
    graph = h3.apply_extensions(graph, "minimax_h3_t2v", adv)
    assert h3.runtime_errors(graph, {"ModelAttentionBackend": {"input": {"required": {"attention": [["pytorch attention"]]}}}})
    assert not h3.runtime_errors(graph, {"ModelAttentionBackend": {"input": {"required": {"attention": ["COMBO", {"options": ["comfy kitchen attention"]}]}}}})
    manifest = {item["id"]: item for item in MODEL_ASSETS}
    for asset_id in INSTALL_PROFILES["minimax-h3-creative-addon"]["asset_ids"]:
        assert len(manifest[asset_id]["sha256"]) == 64


def check_save_video_compatibility():
    graph = {"1": {"class_type": "SaveVideo", "inputs": {"format": "mp4", "codec": "h264"}}}
    old_schema = {"SaveVideo": {"input": {"required": {"format": [["mp4"]], "codec": [["h264"]]}}}}
    assert app.resolve_graph_model_option_names(deepcopy(graph), old_schema) == graph
    nested = {"SaveVideo": {"input": {"required": {"format": ["COMFY_DYNAMICCOMBO_V3", {"options": [
        {"key": "mp4", "inputs": {"required": {"codec": ["COMFY_DYNAMICCOMBO_V3", {"options": [
            {"key": "h264", "inputs": {"optional": {"encoding": ["COMFY_DYNAMICCOMBO_V3", {"options": [
                {"key": "re-encode", "inputs": {"required": {"crf": ["FLOAT"]}}}
            ]}]}}}
        ]}]}}}
    ]}]}}}}
    result = app.resolve_graph_model_option_names(deepcopy(graph), nested)
    assert result["1"]["inputs"] == {"format": "mp4", "format.codec": "h264"}
    assert not app.graph_node_schema_errors(result, nested)
    result["1"]["inputs"]["format.codec.encoding"] = "re-encode"
    assert "format.codec.encoding.crf" in " ".join(app.graph_node_schema_errors(result, nested))
    result["1"]["inputs"]["format.codec.encoding.crf"] = 23.0
    assert not app.graph_node_schema_errors(result, nested)


def check_shared_node_preserved():
    from scripts import install_workflow_assets as installer
    repo = next(item for item in installer.CUSTOM_NODE_REPOS if item["id"] == "video_helper_suite")
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        (root / repo["dest"] / ".git").mkdir(parents=True)
        with patch.object(installer, "CUSTOM_NODE_REPOS", [repo]), \
             patch.object(installer, "run", side_effect=AssertionError("must not change shared node")), \
             patch.object(installer, "run_optional", side_effect=AssertionError("must not update shared node")), \
             patch.object(installer, "install_node_dependencies", side_effect=AssertionError("must not replace dependencies")):
            installer.ensure_custom_nodes(root, profile="minimax-h3-creative-addon")


def check_http_boundaries():
    # Missing media must fail before discovering runtime paths or touching ComfyUI.
    with patch.object(app, "active_comfy_paths", AsyncMock(side_effect=AssertionError("No runtime access"))), \
         patch.object(app, "comfy_post", AsyncMock(side_effect=AssertionError("No GPU submission"))):
        with TestClient(app.app) as client:
            for options in ({"h3_task": "control"}, {"h3_task": "inpaint"},
                            {"h3_latent_upscale": True, "h3_acceleration_profile": "lightx8_v10_768p"}):
                response = client.get("/api/workflow", params={"mode": "minimax_h3_t2v", "advanced": json.dumps(options)})
                assert response.status_code == 200 and not response.json()["ok"], response.text
                response = client.post("/api/generate", data={"mode": "minimax_h3_t2v", "advanced": json.dumps(options)})
                assert response.status_code == 400, response.text
    # Prove both routes call the same extension builder, then stop before validation/submission.
    graph_capture = []
    real_apply = h3.apply_extensions
    def capture(*args, **kwargs):
        result = real_apply(*args, **kwargs)
        graph_capture.append(result)
        raise HTTPException(status_code=409, detail="Offline graph captured")
    with patch.object(app, "active_comfy_paths", AsyncMock(return_value={})), \
         patch.object(app, "prepare_h3_uploads", AsyncMock(return_value={})), \
         patch.object(h3, "apply_extensions", side_effect=capture), \
         patch.object(app, "comfy_post", AsyncMock(side_effect=AssertionError("No GPU submission"))):
        with TestClient(app.app) as client:
            parameters = {"mode": "minimax_h3_t2v", "prompt": "A dancer moves slowly.", "width": 1920, "height": 1088, "length": 124,
                          "advanced": json.dumps({"h3_latent_upscale": True, "h3_attention_backend": "kitchen_int8"})}
            assert client.get("/api/workflow", params=parameters).status_code == 409
            response = client.post("/api/generate", data=parameters)
            assert response.status_code == 409, response.text
    assert len(graph_capture) == 2
    for graph in graph_capture:
        assert graph["191"]["class_type"] == "MinimaxH3LatentUpscaler3D"
        assert graph["197"]["inputs"]["model"] == ["180", 0]


def check_media_guards():
    def upload(name):
        return UploadFile(filename=name, file=io.BytesIO(b"fixture"))
    adv = video_params.resolve("minimax_h3_t2v", {"h3_task": "inpaint"})
    def run():
        return asyncio.run(app.prepare_h3_uploads("minimax_h3_t2v", adv, 124, {}, None, upload("source.mp4"), upload("mask.png")))
    source = {"width": 1280, "height": 720, "duration": 6, "audio": True}
    mask = {**source, "duration": 0, "audio": False}
    with patch.object(app, "save_upload", AsyncMock(side_effect=lambda upload, *args: upload.filename)), \
         patch.object(app, "input_media_path", side_effect=lambda name, *args: Path(name)), \
         patch.object(app, "probe_h3_media", side_effect=[source, mask]):
        result = run()
        assert result["source_has_audio"] and not result["mask_is_video"]
    for results in ([{**source, "duration": 5}], [source, {**mask, "width": 640}]):
        with patch.object(app, "save_upload", AsyncMock(side_effect=lambda upload, *args: upload.filename)), \
             patch.object(app, "input_media_path", side_effect=lambda name, *args: Path(name)), \
             patch.object(app, "probe_h3_media", side_effect=results):
            try:
                run()
            except HTTPException as exc:
                assert exc.status_code == 400
            else:
                raise AssertionError("invalid media accepted")


CHECKS = [check_graph_routes, check_latent_upscale, check_dynamic_schema, check_guards_and_manifest,
          check_save_video_compatibility, check_shared_node_preserved, check_http_boundaries, check_media_guards]

if __name__ == "__main__":
    for check in CHECKS:
        check()
        print(f"PASS {check.__name__}")
    assert "torch" not in sys.modules
    print(f"PASS all {len(CHECKS)} H3 creative CPU-only checks; torch not imported")
