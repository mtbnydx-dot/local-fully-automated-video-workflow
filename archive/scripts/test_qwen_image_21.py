from __future__ import annotations

import asyncio
import copy
import os
import shutil
import subprocess
import sys
import tempfile
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import AsyncMock, patch


os.environ.setdefault("CUDA_VISIBLE_DEVICES", "-1")
os.environ.setdefault("BEGINNER_FRONTEND_DISABLE_GPU_PROBES", "1")
os.environ.setdefault("BEGINNER_FRONTEND_DISABLE_JOB_PERSISTENCE", "1")
sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from beginner_frontend.image_studio import (  # noqa: E402
    ASPECT_PRESETS,
    QWEN_IMAGE_21_ASSET_IDS,
    QWEN_IMAGE_21_MAX_REFERENCES,
    QWEN_IMAGE_21_Q8_MODEL,
    build_image_prompt,
    image_edit_capability,
    image_profile,
    normalize_image_dimensions,
)
from beginner_frontend.model_catalog import CUSTOM_NODE_REPOS, INSTALL_PROFILES, MODEL_ASSETS, MODEL_CATALOG  # noqa: E402
from scripts.install_workflow_assets import selected_model_items  # noqa: E402


PROFILE_ID = "qwen_image_21_int8"
INSTALL_PROFILE = "qwen-image-2.1-int8"


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def node_by_type(graph: dict[str, dict[str, object]], class_type: str) -> tuple[str, dict[str, object]]:
    for node_id, node in graph.items():
        if node.get("class_type") == class_type:
            return node_id, node
    raise AssertionError(f"missing node: {class_type}")


def check_graphs() -> None:
    profile = image_profile(PROFILE_ID)
    check(profile["builder"] == "qwen21", "Qwen-Image-2.1 must use its own builder")
    check(profile["dimension_multiple"] == 32, "Qwen-Image-2.1 dimensions must align to 32 pixels")
    capability = image_edit_capability(PROFILE_ID)
    check(capability["method"] == "qwen21_reference", "native Qwen-Image-2.1 edit method is missing")
    check(capability["max_reference_images"] == QWEN_IMAGE_21_MAX_REFERENCES == 10, "reference image limit drifted")

    t2i = build_image_prompt(
        prompt="A clean product photograph",
        negative="blurred",
        width=2752,
        height=1536,
        seed=7,
        profile_id=PROFILE_ID,
        steps=25,
        cfg=1.0,
        sampler="euler",
        scheduler="simple",
    )
    _, encoder = node_by_type(t2i, "TextEncodeQwenImage21")
    _, latent = node_by_type(t2i, "EmptyLatentImage")
    check("QwenImage21Cache" not in {node["class_type"] for node in t2i.values()}, "T2I should not allocate the edit KV cache")
    check(encoder["inputs"]["negative_prompt"] == "blurred", "T2I negative prompt is not wired")
    check(latent["inputs"]["width"] == 2752 and latent["inputs"]["height"] == 1536, "native 2K latent size drifted")

    edit = build_image_prompt(
        prompt="Keep <image1>, borrow the material from <image2> and lighting from <image3>",
        negative="blurred",
        width=1024,
        height=1024,
        seed=8,
        profile_id=PROFILE_ID,
        steps=25,
        cfg=1.0,
        sampler="euler",
        scheduler="simple",
        source_image="target.png",
        reference_images=["material.png", "lighting.png"],
    )
    encoder_id, edit_encoder = node_by_type(edit, "TextEncodeQwenImage21")
    _, sampler = node_by_type(edit, "KSampler")
    load_images = [node["inputs"]["image"] for node in edit.values() if node["class_type"] == "LoadImage"]
    check(load_images == ["target.png", "material.png", "lighting.png"], "reference image order is not stable")
    check(edit_encoder["inputs"]["resolution"] == 1024, "native edit should follow the normalized target pixel budget")
    check(all(f"images.image_{index}" in edit_encoder["inputs"] for index in range(1, 4)), "dynamic reference inputs are incomplete")
    check(sampler["inputs"]["latent_image"] == [encoder_id, 2], "edit sampler must use the native encoder latent")
    node_by_type(edit, "QwenImage21Cache")


def check_dimensions() -> None:
    qwen21_presets = [item for item in ASPECT_PRESETS if str(item["id"]).startswith("qwen21-")]
    check(len(qwen21_presets) == 7, "official Qwen-Image-2.1 preset set is incomplete")
    check(
        all(PROFILE_ID in item.get("profiles", []) and
            all(image_profile(profile_id)["builder"] == "qwen21" for profile_id in item["profiles"])
            for item in qwen21_presets),
        "Qwen-Image-2.1 native presets must not leak into other image profiles",
    )
    width, height, preset = normalize_image_dimensions(1, 1, "qwen21-landscape-2k", PROFILE_ID)
    check((width, height, preset) == (2752, 1536, "qwen21-landscape-2k"), "official 16:9 2K preset changed")
    width, height, preset = normalize_image_dimensions(4000, 4000, "custom", PROFILE_ID)
    check(width % 32 == 0 and height % 32 == 0, "custom dimensions are not aligned to 32")
    check(width * height <= 4_301_000 and preset == "custom", "custom dimensions exceed the Qwen-Image-2.1 pixel budget")


def check_encoder_schema() -> None:
    from beginner_frontend.app import graph_node_schema_errors

    # Native node defaults are UI hints; API prompts must still supply required inputs.
    object_info = {
        "TextEncodeQwenImage21": {
            "input": {
                "required": {
                    "clip": ["CLIP", {}],
                    "prompt": ["STRING", {}],
                    "negative_prompt": ["STRING", {}],
                    "resolution": ["INT", {"default": 1024, "min": 0, "max": 4096, "step": 32}],
                    "images": ["COMFY_AUTOGROW_V3", {"template": {"min": 0, "names": [f"image_{i}" for i in range(1, 17)]}}],
                },
                "optional": {"vae": ["VAE", {}]},
            }
        }
    }
    presets = [item for item in ASPECT_PRESETS if PROFILE_ID in item.get("profiles", [])]
    for preset in presets:
        for source_image in ("", "target.png"):
            for batch_size in (1, 3):
                graph = build_image_prompt(
                    prompt="A clean product photograph", negative="blurred",
                    width=preset["width"], height=preset["height"], seed=7,
                    profile_id=PROFILE_ID, source_image=source_image, batch_size=batch_size,
                )
                check(not graph_node_schema_errors(graph, object_info), "Qwen 2.1 native input contract failed")
                _, encoder = node_by_type(graph, "TextEncodeQwenImage21")
                resolution = encoder["inputs"]["resolution"]
                check(isinstance(resolution, int) and 0 <= resolution <= 4096 and resolution % 32 == 0,
                      "encoder resolution must satisfy the native node bounds")
                if not source_image:
                    check(resolution == 1024, "T2I must explicitly supply the native encoder default")
                    _, latent = node_by_type(graph, "EmptyLatentImage")
                    check(latent["inputs"]["width"] == preset["width"] and latent["inputs"]["height"] == preset["height"],
                          "encoder resolution must not change T2I output dimensions")
                del encoder["inputs"]["resolution"]
                check(any("resolution" in error for error in graph_node_schema_errors(graph, object_info)),
                      "preflight must reject a missing resolution even when the node defines a default")


def check_manifest() -> None:
    expected_ids = set(QWEN_IMAGE_21_ASSET_IDS)
    selected = {item["id"] for item in selected_model_items(INSTALL_PROFILE)}
    check(selected == expected_ids, "one-click profile must contain exactly the three official Comfy assets")
    assets = {item["id"]: item for item in MODEL_ASSETS if item["id"] in expected_ids}
    check(set(assets) == expected_ids, "Qwen-Image-2.1 asset manifest is incomplete")
    check(all(int(item.get("bytes") or 0) > 0 for item in assets.values()), "asset byte sizes are missing")
    check(all(len(str(item.get("sha256") or "")) == 64 for item in assets.values()), "asset sha256 metadata is missing")
    profile = INSTALL_PROFILES[INSTALL_PROFILE]
    check(profile["installable"] is True and profile["required_comfy_version"] == "0.36.0", "install compatibility metadata drifted")
    catalog = next(item for item in MODEL_CATALOG if item["id"] == PROFILE_ID)
    check(catalog["platform_support"] == "native", "catalog must route Qwen-Image-2.1 to the native image studio")
    check(catalog["workflow_modes"] == {"image": PROFILE_ID}, "catalog image profile mapping is inconsistent")


def check_q8_addon() -> None:
    from beginner_frontend.app import graph_model_registry_errors, graph_node_schema_errors, resolve_graph_model_option_names

    profile = copy.deepcopy(image_profile(PROFILE_ID))
    config = profile["nsfw"]
    addon = INSTALL_PROFILES[config["addon_profile"]]
    check(addon["asset_ids"] == [config["asset_id"]], "Q8 addon must not redownload or replace the official base")
    check(addon["custom_node_ids"] == ["gguf_qwen21"], "Q8 addon needs the Qwen 2.1 compatible GGUF loader")
    repo = next(item for item in CUSTOM_NODE_REPOS if item["id"] == "gguf_qwen21")
    check(repo["url"] == "https://github.com/leejet/ComfyUI-GGUF.git" and len(repo["ref"]) == 40,
          "Qwen 2.1 GGUF plugin must use a pinned compatible fork")
    asset = next(item for item in MODEL_ASSETS if item["id"] == config["asset_id"])
    check(asset["dest"] == f"models/diffusion_models/{QWEN_IMAGE_21_Q8_MODEL}", "Q8 must have a separate model path")
    check(asset["bytes"] == 7591551648 and asset["sha256"] == "763ee46b76069d9c54ab26719a0b9222575751560c8bf3a48275736c44351c0e",
          "Q8 integrity metadata drifted")
    check(config["asset_id"] in profile["optional_asset_ids"] and config["asset_id"] not in profile["required_asset_ids"],
          "Q8 must remain optional for the standard workflow")

    for source in ("", "target.png"):
        args = dict(prompt="A clean product photograph", negative="blurred", width=1024, height=1024,
                    seed=7, profile_id=PROFILE_ID, source_image=source,
                    reference_images=["material.png", "lighting.png"] if source else [])
        standard = build_image_prompt(**args, nsfw=False)
        q8 = build_image_prompt(**args, nsfw=True)
        check(q8["1"]["class_type"] == "UnetLoaderGGUF", "Q8 toggle must select the GGUF loader")
        check(q8["1"]["inputs"] == {"unet_name": QWEN_IMAGE_21_Q8_MODEL}, "GGUF loader only accepts unet_name")
        check({key: value for key, value in standard.items() if key != "1"} ==
              {key: value for key, value in q8.items() if key != "1"},
              "Q8 must preserve the standard conditioning, VAE, references and sampler graph")
        check(build_image_prompt(**args, nsfw=False) == standard, "switching Q8 off must restore the standard graph")
        check(node_by_type(q8, "TextEncodeQwenImage21")[1]["inputs"]["resolution"] == 1024,
              "Q8 encoder must include the required resolution")
        windows_name = QWEN_IMAGE_21_Q8_MODEL.replace("/", "\\")
        schema = {"UnetLoaderGGUF": {"input": {"required": {"unet_name": [[windows_name], {}]}}}}
        q8 = resolve_graph_model_option_names(q8, schema)
        check(q8["1"]["inputs"]["unet_name"] == windows_name, "Q8 names must match ComfyUI on Windows")
        check(not graph_node_schema_errors({"1": q8["1"]}, schema), "GGUF loader input contract failed")
        check(not graph_model_registry_errors({"1": q8["1"]}, schema), "registered Q8 model was rejected")
        schema["UnetLoaderGGUF"]["input"]["required"]["unet_name"] = [["different.gguf"], {}]
        check(bool(graph_model_registry_errors({"1": q8["1"]}, schema)), "missing Q8 must fail model preflight")
    check(image_profile(PROFILE_ID) == profile, "Q8 graph building must not mutate the shared profile")


def check_q8_readiness() -> None:
    from beginner_frontend import app as backend

    profile = image_profile(PROFILE_ID)
    assets = [{"id": item_id, "ok": True} for item_id in [*profile["required_asset_ids"], *profile["optional_asset_ids"]]]
    schema = {"UnetLoaderGGUF": {"input": {"required": {"unet_name": [[QWEN_IMAGE_21_Q8_MODEL], {}]}}}}
    with tempfile.TemporaryDirectory(prefix="qwen21_q8_test_") as temporary, ExitStack() as stack:
        base = Path(temporary)
        entry = base / "custom_nodes" / "ComfyUI-GGUF" / "__init__.py"
        entry.parent.mkdir(parents=True)
        entry.touch()
        paths = {key: base for key in ("base_dir", "input_dir", "output_dir", "temp_dir", "user_dir")}
        stack.enter_context(patch.object(backend, "active_comfy_paths", AsyncMock(return_value=paths)))
        object_info = stack.enter_context(patch.object(backend, "get_comfy_object_info", AsyncMock(return_value={})))
        stack.enter_context(patch.object(backend, "collect_asset_checks", return_value=assets))
        stack.enter_context(patch.object(backend, "IMAGE_PROFILES", [profile]))
        stack.enter_context(patch.object(backend, "read_local_config", return_value={}))
        stack.enter_context(patch.object(backend, "face_swap_capability_payload", return_value={}))
        stack.enter_context(patch.object(backend, "image_studio_output_payload", return_value={}))
        stack.enter_context(patch.object(backend, "model_storage_candidates", return_value=[]))
        stack.enter_context(patch.object(backend, "image_studio_job_history_page", return_value={"items": []}))

        def status() -> dict:
            payload = asyncio.run(backend.image_studio_bootstrap(profile=PROFILE_ID, target_dir=str(base)))
            return payload["profiles"][0]["nsfw"]

        unloaded = status()
        check(unloaded["addon_installed"] and not unloaded["addon_ready"] and unloaded["missing_nodes"] == ["UnetLoaderGGUF"],
              "downloaded files alone must not enable Q8")
        check("ComfyUI" in unloaded["readiness_note"], "unloaded GGUF node must explain the restart requirement")
        object_info.return_value = schema
        ready = status()
        check(ready["addon_ready"] and ready["readiness_note"] == "", "registered Q8 addon should be ready")
        object_info.return_value = {"UnetLoaderGGUF": {"input": {"required": {"unet_name": [[], {}]}}}}
        check(not status()["addon_ready"], "loaded node without the model must not enable Q8")
        object_info.side_effect = backend.HTTPException(status_code=503, detail="offline")
        check(not status()["addon_ready"] and status()["readiness_note"], "disconnected ComfyUI must remain unready")
        object_info.side_effect = None
        object_info.return_value = schema
        assets[-1]["ok"] = False
        check(not status()["addon_installed"] and not status()["addon_ready"], "missing Q8 file must disable addon")
        assets[-1]["ok"] = True
        entry.unlink()
        check(not status()["addon_installed"], "missing custom-node files must allow reinstall")


def check_q8_frontend_state() -> None:
    node = shutil.which("node")
    if not node:
        print("SKIP Q8 frontend state check: Node.js is not installed")
        return
    # Exercise only the state renderer in a CPU-only VM, with no browser or network.
    script = r'''
const fs = require("node:fs");
const vm = require("node:vm");
const assert = require("node:assert/strict");
const source = fs.readFileSync(process.argv[1], "utf8");
const start = source.indexOf("  function renderNsfwSupport() {");
const end = source.indexOf("  function selectedPromptMode()", start);
assert(start >= 0 && end > start);
const element = () => ({classList: {toggle(name, value) { this[name] = value; }}, dataset: {}});
const refs = Object.fromEntries(["nsfw", "nsfwStrengthField", "installNsfw", "nsfwSource", "nsfwStatus", "nsfwExtras"].map(k => [k, element()]));
const profile = {label: "official INT8", nsfw: {toggle_enabled: true, addon_profile: "q8", model_label: "Q8_0", label: "Q8", note: "not generation-tested"}};
const noop = () => {};
const context = vm.createContext({refs, activeProfile: () => profile, bootstrap: {},
  renderPlaybookControls: noop, renderEditStrengthPresetSwitches: noop, renderStyleOptions: noop, updateTriggerPreview: noop});
vm.runInContext(source.slice(start, end), context);
const render = () => vm.runInContext("renderNsfwSupport()", context);
render();
assert(refs.nsfw.disabled && !refs.installNsfw.classList.hidden);
Object.assign(profile.nsfw, {addon_installed: true, addon_ready: false, readiness_note: "Restart ComfyUI"});
refs.nsfw.checked = true;
render();
assert(refs.nsfw.disabled && !refs.nsfw.checked && refs.installNsfw.classList.hidden);
assert(refs.nsfwStatus.textContent.includes("Restart ComfyUI"));
profile.nsfw.addon_ready = true;
render();
assert(!refs.nsfw.disabled && refs.nsfwStatus.textContent.includes("official INT8"));
refs.nsfw.checked = true;
render();
assert(refs.nsfwStatus.textContent.includes("Q8_0") && refs.nsfwStrengthField.classList.hidden);
refs.nsfw.checked = false;
render();
assert(refs.nsfwStatus.textContent.includes("official INT8"));
'''
    result = subprocess.run([node, "-e", script, str(ROOT / "beginner_frontend/static/image-studio.js")],
                            capture_output=True, text=True, timeout=30)
    check(result.returncode == 0, f"Q8 frontend renderer failed: {result.stderr}")


def check_q8_norm_patch() -> None:
    from scripts.install_workflow_assets import (
        QWEN21_GGUF_NORM_ANCHOR, QWEN21_GGUF_NORM_PATCH, apply_custom_node_compatibility,
    )

    with tempfile.TemporaryDirectory(prefix="qwen21_norm_patch_") as temporary:
        directory = Path(temporary)
        loader = directory / "loader.py"
        source = ("def fake_loader():\n    if True:\n" + QWEN21_GGUF_NORM_ANCHOR).replace("\n", "\r\n").encode()
        loader.write_bytes(source)
        check(not apply_custom_node_compatibility({"id": "other_node"}, directory), "other custom nodes must not be modified")
        check(loader.read_bytes() == source, "unrelated plugin changed")
        check(apply_custom_node_compatibility({"id": "gguf_qwen21"}, directory), "Q8 norm patch was not installed")
        updated = loader.read_bytes()
        check(QWEN21_GGUF_NORM_PATCH in updated.decode().replace("\r\n", "\n"), "Q8 norm patch is incomplete")
        check(loader.with_name("loader.py.before-qwen21-norm-fix").read_bytes() == source, "original plugin backup is missing")
        check(not apply_custom_node_compatibility({"id": "gguf_qwen21"}, directory), "Q8 norm patch must be idempotent")
        check(loader.read_bytes() == updated, "repeat installation changed the patched loader")
        loader.write_text("# unexpected upstream layout\n", encoding="utf-8")
        try:
            apply_custom_node_compatibility({"id": "gguf_qwen21"}, directory)
        except RuntimeError:
            pass
        else:
            raise AssertionError("unknown loader versions must fail closed")
        check(loader.read_text(encoding="utf-8") == "# unexpected upstream layout\n", "unknown upstream loader was overwritten")


def check_frontend_contract() -> None:
    html = (ROOT / "beginner_frontend" / "static" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "beginner_frontend" / "static" / "image-studio.js").read_text(encoding="utf-8")
    app = (ROOT / "beginner_frontend" / "app.py").read_text(encoding="utf-8")
    check('id="imageReferenceFiles"' in html and 'name="reference_images"' in html, "multi-reference picker is missing")
    check("reference_count" in js and 'payload.append("reference_images"' in js, "frontend does not submit or preflight references")
    check("visibleAspectPresets" in js and "profiles.includes(profileId)" in js, "frontend does not scope model-specific aspect presets")
    check('refs.viewTab?.classList.contains("active")' in js, "image studio does not recover an early tab activation")
    check("reference_images: list[UploadFile] | None" in app, "backend multipart reference contract is missing")
    check("reference_images=reference_image_names" in app, "backend does not pass references into the graph")


def run_all() -> list[str]:
    checks = [check_graphs, check_dimensions, check_encoder_schema, check_manifest,
              check_q8_addon, check_q8_readiness, check_q8_frontend_state, check_q8_norm_patch, check_frontend_contract]
    for item in checks:
        item()
    return [item.__name__ for item in checks]


def main() -> int:
    try:
        checks = run_all()
    except Exception as exc:
        print(f"QWEN IMAGE 2.1 CHECK FAILED: {exc}")
        return 1
    print("QWEN IMAGE 2.1 CHECK OK")
    for item in checks:
        print(f"- {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
