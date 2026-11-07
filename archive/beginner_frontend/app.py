from __future__ import annotations

import asyncio
import base64
import contextvars
import hashlib
import hmac
import mimetypes
import json
import math
import os
import platform
import random
import re
import signal
import shutil
import socket
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

try:
    import cv2
except ImportError:  # The app stays usable while diagnostics explain the missing optional feature.
    cv2 = None

try:
    import numpy as np
except ImportError:
    np = None

try:
    from PIL import Image, ImageOps
except ImportError:
    Image = None
    ImageOps = None


def _hidden_popen_options(*, new_process_group: bool = False) -> dict[str, Any]:
    """Keep Windows console tools in the background without changing Unix behavior."""
    if platform.system() != "Windows":
        return {"start_new_session": True} if new_process_group else {}
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if new_process_group:
        creationflags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 0)
    startupinfo.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
    return {"creationflags": creationflags, "startupinfo": startupinfo}

import httpx
import yaml
from fastapi import Body, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

try:
    import websockets
except ImportError:  # uvicorn[standard] normally provides this; polling remains available without it.
    websockets = None

from beginner_frontend.image_studio import (
    DEFAULT_IMAGE_NEGATIVE,
    DEFAULT_IMAGE_PROMPT,
    IMAGE_ASSET_IDS,
    IMAGE_PROFILES,
    QWEN_IMAGE_21_MODEL,
    QWEN_IMAGE_21_TEXT_ENCODER,
    QWEN_IMAGE_21_VAE,
    QWEN_IMAGE_ASSET_IDS,
    QWEN_IMAGE_INSTALL_PROFILE,
    QWEN_IMAGE_LIGHTNING_LORA,
    QWEN_IMAGE_MODEL,
    QWEN_IMAGE_TEXT_ENCODER,
    QWEN_IMAGE_VAE,
    build_effective_prompt,
    build_image_prompt,
    build_qwen_image_prompt,
    image_edit_capability,
    image_profile,
    image_studio_static_payload,
    normalize_image_edit_controls,
    normalize_image_dimensions,
    normalized_generation_settings,
)
from beginner_frontend.nsfw_playbook import (
    CHARACTER_BOX_CONFIG_KEY,
    PLAYBOOK_CONFIG_KEY,
    apply_video_motion,
    character_box_payload,
    inject_trigger,
    intensity_strength,
    normalize_character_box,
    playbook_payload,
    resolve_playbook,
    strip_negative_terms,
)
from beginner_frontend.nsfw_extensions import (
    EDIT_STRENGTH_PRESETS,
    append_consistency_negative,
    apply_face_detailer,
    build_video_face_swap_prompt,
    capability_payload,
    expand_prompt_from_style,
)
from beginner_frontend import video_params, h3_workflows
from beginner_frontend.video_params import AdvancedParams
from beginner_frontend.social_presets import (
    resolve_social_recipe,
    social_presets_payload,
)

try:
    from beginner_frontend.model_catalog import (
        CUSTOM_NODE_REPOS as CATALOG_CUSTOM_NODE_REPOS,
        DOWNLOAD_SOURCE_PRESETS,
        INSTALL_PROFILES as CATALOG_INSTALL_PROFILES,
        MODEL_ASSETS as CATALOG_MODEL_ASSETS,
        MODEL_CATALOG,
        OPTIONAL_POST_NODE_IDS as CATALOG_OPTIONAL_POST_NODE_IDS,
        POST_ASSET_IDS as CATALOG_POST_ASSET_IDS,
        catalog_generation_target,
        model_catalog_payload,
    )
except Exception:
    CATALOG_CUSTOM_NODE_REPOS = []
    CATALOG_INSTALL_PROFILES = {}
    CATALOG_MODEL_ASSETS = []
    CATALOG_OPTIONAL_POST_NODE_IDS = ["frame_interpolation"]
    CATALOG_POST_ASSET_IDS = []
    DOWNLOAD_SOURCE_PRESETS = []
    MODEL_CATALOG = []
    model_catalog_payload = None

    def catalog_generation_target(item):
        support = str((item or {}).get("platform_support") or "manual")
        modes = (item or {}).get("workflow_modes") or {}
        if support == "native" and any(str(modes.get(step) or "").strip() for step in ("draft", "final", "image")):
            return "native"
        if support == "cloud_api" and any(str(modes.get(step) or "").strip() for step in ("draft", "final", "image")):
            return "cloud_api"
        if support == "official_workflow":
            return "comfy_template"
        return "catalog_only"

try:
    from scripts.install_comfyui import comfyui_disk_plan as COMFYUI_DISK_PLAN
    from scripts.install_comfyui import effective_backend as COMFYUI_EFFECTIVE_BACKEND
except Exception:
    COMFYUI_DISK_PLAN = None
    COMFYUI_EFFECTIVE_BACKEND = None

try:
    from scripts.prerequisite_doctor import build_prerequisite_report as BUILD_PREREQUISITE_REPORT
except Exception:
    BUILD_PREREQUISITE_REPORT = None

try:
    from scripts.install_workflow_assets import disk_space_plan as INSTALL_DISK_SPACE_PLAN
    from scripts.install_workflow_assets import find_local_asset_candidate as INSTALL_FIND_LOCAL_ASSET_CANDIDATE
    from scripts.install_workflow_assets import planned_download_bytes as INSTALL_PLANNED_DOWNLOAD_BYTES
    from scripts.install_workflow_assets import selected_model_items as INSTALL_SELECTED_MODEL_ITEMS
except Exception:
    INSTALL_DISK_SPACE_PLAN = None
    INSTALL_FIND_LOCAL_ASSET_CANDIDATE = None
    INSTALL_PLANNED_DOWNLOAD_BYTES = None
    INSTALL_SELECTED_MODEL_ITEMS = None

INSTALL_CUSTOM_NODE_REPOS = CATALOG_CUSTOM_NODE_REPOS
INSTALL_MODEL_FILES = CATALOG_MODEL_ASSETS


APP_DIR = Path(__file__).resolve().parent
WORKSPACE_DIR = APP_DIR.parent
APP_VERSION = os.environ.get("BEGINNER_FRONTEND_APP_VERSION", "2026.10.23.2")
STARTED_AT = time.time()
LOCAL_CONFIG_FILE = WORKSPACE_DIR / ".local_ai_workbench_config.json"
LEGACY_LOCAL_CONFIG_FILES = (WORKSPACE_DIR / ".wan22_workflow_config.json",)
HF_ENDPOINT_ENV_NAMES = ("LOCAL_AI_HF_ENDPOINT", "WAN22_HF_ENDPOINT", "HF_ENDPOINT")
PROXY_ENV_NAMES = ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "https_proxy", "http_proxy", "all_proxy")
PIP_INDEX_ENV_NAMES = ("PIP_INDEX_URL", "pip_index_url")
SERVICE_MODES = {"server", "client", "both"}
CONFIG_LOCK = threading.RLock()
DOWNLOAD_ENV_LOCK = threading.RLock()


def looks_like_comfy_base(path: Path) -> bool:
    return all((path / name).exists() for name in ("models", "input", "output", "custom_nodes"))


def comfy_desktop_shared_candidates() -> list[Path]:
    candidates: list[Path] = []
    configured = os.environ.get("COMFY_DESKTOP_SHARED_DIR")
    if configured:
        candidates.append(Path(configured))
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidates.extend(
            [
                Path(local_app_data) / "Comfy-Desktop" / "ComfyUI-Shared",
                Path(local_app_data) / "ComfyUI" / "ComfyUI-Shared",
            ]
        )
    return candidates


def detected_comfy_desktop_shared_dir() -> Path | None:
    for candidate in comfy_desktop_shared_candidates():
        try:
            resolved = candidate.expanduser().resolve()
        except Exception:
            continue
        if looks_like_comfy_base(resolved):
            return resolved
    return None


def normalize_hf_endpoint(value: str | None) -> str:
    value = (value or "").strip().rstrip("/")
    if not value:
        return ""
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("下载源必须是 http(s) URL，例如 https://huggingface.co")
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}"


def normalize_proxy_url(value: str | None) -> str:
    value = (value or "").strip().rstrip("/")
    if not value:
        return ""
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("代理地址必须是 http(s) URL，例如 http://127.0.0.1:7890")
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}"


def normalize_pip_index_url(value: str | None) -> str:
    value = (value or "").strip().rstrip("/")
    if not value:
        return ""
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("pip 镜像源必须是 http(s) URL，例如 https://pypi.org/simple")
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}"


def normalize_service_mode(value: str | None) -> str:
    mode = (value or "").strip().lower()
    return mode if mode in SERVICE_MODES else ""


def normalize_server_url(value: str | None) -> str:
    value = (value or "").strip().rstrip("/")
    if not value:
        return ""
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("服务端地址必须是 http(s) URL，例如 http://192.168.1.20:7860")
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}"


def redact_url(value: str | None) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    parsed = urlparse(value)
    if not parsed.netloc:
        return value
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    if parsed.username or parsed.password:
        netloc = f"***:***@{host}{port}"
    else:
        netloc = parsed.netloc
    return f"{parsed.scheme}://{netloc}{parsed.path or ''}" + (f"?{parsed.query}" if parsed.query else "")


def redact_sensitive_text(value: Any) -> str:
    text = str(value)
    return re.sub(r"(https?://)[^/\s:@]+:[^/\s@]+@", r"\1***:***@", text)


def read_local_config() -> dict[str, Any]:
    with CONFIG_LOCK:
        for config_file in (LOCAL_CONFIG_FILE, *LEGACY_LOCAL_CONFIG_FILES):
            if not config_file.exists():
                continue
            try:
                data = json.loads(config_file.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(data, dict):
                return data
        return {}


def write_local_config(config: dict[str, Any]) -> None:
    with CONFIG_LOCK:
        cleaned = {key: value for key, value in config.items() if value not in ("", None, [], {})}
        LOCAL_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        temporary = LOCAL_CONFIG_FILE.with_name(f"{LOCAL_CONFIG_FILE.name}.{uuid.uuid4().hex}.tmp")
        try:
            temporary.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temporary, LOCAL_CONFIG_FILE)
        finally:
            temporary.unlink(missing_ok=True)



def current_nsfw_playbook() -> dict[str, Any]:
    return resolve_playbook(read_local_config())


def merged_style_presets(playbook: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    book = playbook or current_nsfw_playbook()
    styles = [dict(item) for item in image_studio_static_payload()["style_presets"]]
    # static payload already merges; keep unique by id
    seen: set[str] = set()
    ordered: list[dict[str, Any]] = []
    for item in styles:
        key = str(item.get("id") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        ordered.append(item)
    for item in book.get("nsfw_styles") or []:
        key = str(item.get("id") or "")
        if key and key not in seen:
            seen.add(key)
            ordered.append(dict(item))
    return ordered


def apply_unrestricted_prompt_text(
    prompt: str,
    negative: str,
    *,
    enabled: bool,
    trigger: str = "",
    auto_inject_trigger: bool = True,
    auto_strip_negative: bool = True,
    playbook: dict[str, Any] | None = None,
) -> tuple[str, str]:
    book = playbook or current_nsfw_playbook()
    linkage = book.get("linkage") or {}
    effective_prompt = str(prompt or "")
    effective_negative = str(negative or "")
    if not enabled:
        return effective_prompt, effective_negative
    inject = auto_inject_trigger if auto_inject_trigger is not None else bool(linkage.get("auto_inject_trigger", True))
    strip = auto_strip_negative if auto_strip_negative is not None else bool(linkage.get("auto_strip_negative", True))
    if inject:
        effective_prompt = inject_trigger(effective_prompt, trigger, enabled=True)
    boundary = (
        "All depicted people are consenting adults aged 21 or older. "
        "Do not imitate a real person's intimate appearance without authorization."
    )
    if boundary.lower() not in effective_prompt.lower():
        effective_prompt = f"{boundary} {effective_prompt}".strip()
    if strip:
        effective_negative = strip_negative_terms(effective_negative, book.get("negative_strip_terms"))
    return effective_prompt, effective_negative


def resolve_motion_lora_names(
    *,
    motion_lora_high: str = "",
    motion_lora_low: str = "",
    pack_id: str = "",
    config: dict[str, Any] | None = None,
) -> tuple[str, str]:
    high = str(motion_lora_high or "").strip()
    low = str(motion_lora_low or "").strip()
    if high or low:
        return high, low
    from beginner_frontend.nsfw_playbook import find_preset

    book = resolve_playbook(config)
    packs = book.get("motion_lora_packs") or []
    pack_id = str(pack_id or "").strip()
    if not pack_id:
        return "", ""
    pack = find_preset(packs, pack_id)
    if not pack:
        return "", ""
    return str(pack.get("high") or "").strip(), str(pack.get("low") or "").strip()


def parse_advanced_module_ids(raw: str) -> set[str]:
    text = str(raw or "").strip()
    if not text:
        return set()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return set()
    if isinstance(parsed, list):
        return {str(item).strip() for item in parsed if str(item).strip()}
    if isinstance(parsed, dict):
        return {str(key).strip() for key, value in parsed.items() if value}
    return set()


def video_frame_extract_path(
    source: Path,
    *,
    position: float = 0.5,
    paths: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    position = max(0.0, min(1.0, float(position)))
    ffmpeg_path = find_ffmpeg()
    duration_probe = subprocess.run(
        [ffmpeg_path, "-hide_banner", "-i", str(source)],
        capture_output=True,
        text=True,
        **_hidden_popen_options(),
    )
    duration = 0.0
    for line in (duration_probe.stderr or "").splitlines():
        if "Duration:" in line:
            token = line.split("Duration:", 1)[1].split(",", 1)[0].strip()
            parts = token.split(":")
            if len(parts) == 3:
                hours, minutes, seconds = parts
                duration = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
            break
    timestamp = max(0.0, duration * position) if duration > 0 else 0.0
    upload_dir = upload_dir_for(paths)
    upload_dir.mkdir(parents=True, exist_ok=True)
    destination_name = unique_upload_filename(f"frame_{uuid.uuid4().hex[:8]}.png")
    destination = upload_dir / destination_name
    command = [
        ffmpeg_path,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{timestamp:.3f}",
        "-i",
        str(source),
        "-frames:v",
        "1",
        str(destination),
    ]
    result = subprocess.run(command, capture_output=True, text=True, **_hidden_popen_options())
    if result.returncode != 0 or not destination.is_file():
        detail = (result.stderr or result.stdout or "").strip()[-2000:] or "ffmpeg 抽帧失败"
        raise HTTPException(status_code=500, detail=detail)
    input_name = f"beginner_frontend/{destination_name}"
    width = height = 0
    if Image is not None:
        try:
            with Image.open(destination) as opened:
                width, height = opened.size
        except (OSError, ValueError):
            pass
    preview_item = {
        "filename": destination_name,
        "subfolder": "beginner_frontend",
        "type": "input",
    }
    meta = {
        "input_name": input_name,
        "preview_url": media_url(preview_item),
        "width": width,
        "height": height,
        "position": position,
        "timestamp_seconds": round(timestamp, 3),
        "source": str(source),
    }
    return input_name, meta


def resolve_video_unrestricted_knobs(
    *,
    trigger: str = "",
    motion_id: str = "medium",
    length: int,
    cfg: float,
    unrestricted_strength: float,
    prompt: str = "",
    apply_motion_to_prompt: bool = False,
) -> dict[str, Any]:
    book = current_nsfw_playbook()
    language = "zh" if re.search(r"[\u4e00-\u9fff]", prompt or "") else "en"
    moved = apply_video_motion(
        length=length,
        cfg=cfg,
        unrestricted_strength=unrestricted_strength,
        prompt=prompt if apply_motion_to_prompt else "",
        motion_id=motion_id or "medium",
        playbook=book,
        language=language,
    )
    if not apply_motion_to_prompt:
        moved["prompt"] = str(prompt or "")
    return {
        "trigger": str(trigger or "").strip(),
        "playbook": book,
        **moved,
    }


def saved_model_download_dir() -> str:
    return str(read_local_config().get("model_download_dir") or "").strip()


def normalize_model_download_dir(value: str | None, fallback: Path) -> Path:
    raw = (value or "").strip()
    candidate = Path(raw).expanduser() if raw else fallback
    if not candidate.is_absolute():
        raise ValueError("模型下载目录必须是绝对路径")
    return candidate.resolve()


def model_storage_candidates(active_base_dir: Path) -> list[dict[str, Any]]:
    candidates: list[tuple[str, Path]] = [("ComfyUI 当前目录", active_base_dir)]
    saved = saved_model_download_dir()
    if saved:
        try:
            candidates.append(("上次选择", Path(saved).expanduser().resolve()))
        except OSError:
            pass
    candidates.append(("项目目录", WORKSPACE_DIR))
    if platform.system() == "Windows":
        drive_roots: list[Path] = []
        try:
            import ctypes

            drive_mask = int(ctypes.windll.kernel32.GetLogicalDrives())
            for index, letter in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
                if drive_mask & (1 << index):
                    root_text = f"{letter}:\\"
                    # Only suggest local fixed disks. Network and empty optical
                    # drives can make a first-page storage scan stall for seconds.
                    if int(ctypes.windll.kernel32.GetDriveTypeW(root_text)) == 3:
                        drive_roots.append(Path(root_text))
        except (AttributeError, OSError, ValueError):
            anchors = {Path(active_base_dir.anchor), Path(WORKSPACE_DIR.anchor)}
            drive_roots = [root for root in anchors if str(root)]
        for root in drive_roots:
            candidates.append((f"{str(root)[:2]} 盘", root / "AI-Models"))
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for label, path in candidates:
        key = os.path.normcase(str(path))
        if key in seen:
            continue
        seen.add(key)
        usage_path = path if path.exists() else path.parent
        try:
            usage = shutil.disk_usage(usage_path)
            free_gb = round(usage.free / (1024**3), 2)
        except OSError:
            free_gb = None
        result.append(
            {
                "label": label,
                "path": str(path),
                "free_gb": free_gb,
                "active": os.path.normcase(str(path)) == os.path.normcase(str(active_base_dir)),
                "saved": bool(saved and os.path.normcase(str(path)) == os.path.normcase(str(Path(saved).expanduser()))),
            }
        )
    return result


def register_comfy_extra_model_path(target_base_dir: Path, comfy_paths: dict[str, Any]) -> str:
    active_base_dir = Path(str(comfy_paths.get("base_dir") or BASE_DIR)).resolve()
    if os.path.normcase(str(target_base_dir)) == os.path.normcase(str(active_base_dir)):
        return ""
    main_py = Path(str(comfy_paths.get("main_py") or ""))
    if not main_py.exists():
        raise ValueError("无法定位 ComfyUI main.py，不能自动注册自定义模型目录")
    config_path = main_py.parent / "extra_model_paths.yaml"
    existing: dict[str, Any] = {}
    if config_path.exists():
        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            existing = loaded
    existing["ai_video_platform"] = {
        "base_path": str(target_base_dir),
        "checkpoints": "models/checkpoints",
        "loras": "models/loras",
        "vae": "models/vae",
        "text_encoders": "models/text_encoders",
        "diffusion_models": "models/diffusion_models",
        "clip_vision": "models/clip_vision",
        "style_models": "models/style_models",
        "embeddings": "models/embeddings",
        "upscale_models": "models/upscale_models",
        "latent_upscale_models": "models/latent_upscale_models",
        "controlnet": "models/controlnet",
        "model_patches": "models/model_patches",
    }
    config_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = config_path.with_name(f"{config_path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(yaml.safe_dump(existing, allow_unicode=True, sort_keys=False), encoding="utf-8")
        os.replace(temporary, config_path)
    finally:
        temporary.unlink(missing_ok=True)
    return str(config_path)


def saved_service_mode() -> str:
    return normalize_service_mode(str(read_local_config().get("node_mode") or ""))


def effective_service_mode() -> str:
    return normalize_service_mode(os.environ.get("WAN22_NODE_MODE")) or saved_service_mode() or "both"


def configured_access_token() -> str:
    return str(
        os.environ.get("LOCAL_AI_ACCESS_TOKEN")
        or os.environ.get("WAN22_ACCESS_TOKEN")
        or read_local_config().get("access_token")
        or ""
    ).strip()


def get_lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return ""


def request_origin(request: Request) -> str:
    return str(request.base_url).rstrip("/")


def service_url_payload(request: Request) -> dict[str, str]:
    parsed = urlparse(request_origin(request))
    port = f":{parsed.port}" if parsed.port else ""
    local_url = f"{parsed.scheme}://127.0.0.1{port}"
    lan_ip = get_lan_ip()
    lan_url = f"{parsed.scheme}://{lan_ip}{port}" if lan_ip else ""
    return {"local_url": local_url, "lan_url": lan_url, "lan_ip": lan_ip}


def service_config_payload(request: Request | None = None, *, include_sensitive: bool = False) -> dict[str, Any]:
    config = read_local_config()
    env_mode = normalize_service_mode(os.environ.get("WAN22_NODE_MODE"))
    saved_mode = normalize_service_mode(str(config.get("node_mode") or ""))
    mode_configured = bool(env_mode or saved_mode)
    mode = env_mode or saved_mode or "both"
    bind_host = (
        os.environ.get("BEGINNER_FRONTEND_BIND_HOST")
        or os.environ.get("BEGINNER_FRONTEND_HOST")
        or str(config.get("bind_host") or "")
        or ("0.0.0.0" if mode_configured and mode in {"server", "both"} else "127.0.0.1")
    )
    try:
        server_url = normalize_server_url(str(config.get("server_url") or ""))
    except ValueError:
        server_url = ""
    token = configured_access_token()
    urls = service_url_payload(request) if request else {"local_url": "", "lan_url": "", "lan_ip": ""}
    api_base_url = server_url if mode == "client" else ""
    payload: dict[str, Any] = {
        "mode": mode,
        "mode_configured": mode_configured,
        "first_run_required": not mode_configured,
        "mode_source": "environment" if env_mode else "saved" if saved_mode else "default",
        "bind_host": bind_host,
        "binds_lan": bind_host in {"0.0.0.0", "::"} or not bind_host.startswith("127."),
        "server_url": server_url,
        "api_base_url": api_base_url,
        "local_url": urls["local_url"],
        "lan_url": urls["lan_url"],
        "lan_ip": urls["lan_ip"],
        "access_token_configured": bool(token),
        "cors_enabled": True,
        "requires_restart_hint": "切换服务端/双模式后，需要重启 start.bat 才会监听局域网地址。",
    }
    if include_sensitive:
        payload["access_token"] = token
    return payload


def is_loopback_request(request: Request | None) -> bool:
    if request is None:
        return False
    host = (request.client.host if request.client else "") or ""
    return host in {"127.0.0.1", "::1", "localhost"} or host.startswith("127.")


def env_hf_endpoint() -> str:
    for name in HF_ENDPOINT_ENV_NAMES:
        try:
            endpoint = normalize_hf_endpoint(os.environ.get(name))
        except ValueError:
            continue
        if endpoint:
            return endpoint
    return ""


def saved_hf_endpoint() -> str:
    try:
        return normalize_hf_endpoint(str(read_local_config().get("hf_endpoint") or ""))
    except ValueError:
        return ""


def effective_hf_endpoint() -> str:
    return env_hf_endpoint() or saved_hf_endpoint()


def saved_download_region() -> str:
    region = str(read_local_config().get("download_region") or "").strip()
    preset_ids = {str(item.get("id") or "") for item in DOWNLOAD_SOURCE_PRESETS}
    return region if region in preset_ids else ""


# ---- 用户在线导入的模型库（Hugging Face / Civitai 搜索入库） ----
USER_MODEL_CATALOG_KEY = "user_model_catalog"
USER_MODEL_TARGET_SUBDIRS = {
    "checkpoints",
    "diffusion_models",
    "loras",
    "vae",
    "text_encoders",
    "clip",
    "clip_vision",
    "controlnet",
    "upscale_models",
    "embeddings",
}
MODEL_SEARCH_ALLOWED_HOSTS = {"huggingface.co", "civitai.com"}


def read_user_model_catalog() -> list[dict[str, Any]]:
    raw = read_local_config().get(USER_MODEL_CATALOG_KEY)
    return [item for item in raw if isinstance(item, dict) and item.get("id")] if isinstance(raw, list) else []


def write_user_model_catalog(items: list[dict[str, Any]]) -> None:
    with CONFIG_LOCK:
        config = read_local_config()
        config[USER_MODEL_CATALOG_KEY] = items
        write_local_config(config)


def user_catalog_item_by_id(model_id: str) -> dict[str, Any] | None:
    return next((item for item in read_user_model_catalog() if str(item.get("id") or "") == model_id), None)


def catalog_item_by_id(model_id: str | None) -> dict[str, Any] | None:
    model_id = (model_id or "").strip()
    for item in MODEL_CATALOG:
        if str(item.get("id") or "") == model_id:
            return item
    if model_id.startswith("user_"):
        return user_catalog_item_by_id(model_id)
    return None


def saved_model_catalog_id() -> str:
    configured = str(read_local_config().get("selected_model_catalog_id") or "").strip()
    if catalog_item_by_id(configured):
        return configured
    return ""


def catalog_model_for_hardware(hardware: dict[str, Any]) -> str:
    strategy = str(hardware.get("platform_strategy") or "")
    max_vram = float(hardware.get("max_vram_gb") or 0)
    if strategy == "mac_mps":
        candidate = "ltx_098_2b_fp8"
    elif strategy in {"cuda_multi_model", "cuda_wan_workflow"} and max_vram >= 80:
        candidate = "minimax_h3_fl2va_pruned_int8"
    elif strategy in {"cuda_multi_model", "cuda_wan_workflow"} and max_vram >= 40:
        candidate = "ltx_23_22b_fp8_dev"
    elif strategy in {"cuda_multi_model", "cuda_wan_workflow"} and max_vram >= 16:
        candidate = "hunyuan15_t2v_480_fp8_distilled"
    elif strategy in {"cuda_multi_model", "cuda_wan_workflow"}:
        candidate = "ltx_098_2b_fp8"
    else:
        candidate = ""
    return candidate if catalog_item_by_id(candidate) else ""


def annotate_catalog_install_state(items: list[Any], base_dir: Path) -> None:
    """给每个目录条目补 files_found/files_total/install_state，让前端能按“已下载”找模型。

    走 catalog_file_index 的 TTL 缓存索引，批量标注 40+ 模型也只有一次目录扫描。
    """
    for item in items:
        if not isinstance(item, dict):
            continue
        files = [str(name) for name in (item.get("files") or []) if str(name)]
        if not files:
            item["files_total"] = 0
            item["files_found"] = 0
            item["install_state"] = "unknown"
            continue
        found = sum(1 for name in files if find_catalog_file(base_dir, name))
        item["files_total"] = len(files)
        item["files_found"] = found
        item["install_state"] = "ready" if found == len(files) else ("partial" if found else "missing")


def model_catalog_payload_with_selection(
    selected_model_id: str | None = None,
    *,
    base_dir: Path | None = None,
) -> dict[str, Any]:
    payload = model_catalog_payload() if model_catalog_payload else {"items": []}
    user_items = read_user_model_catalog()
    if user_items:
        payload["items"] = list(payload.get("items") or []) + [dict(item) for item in user_items]
        families = list(payload.get("families") or [])
        quants = list(payload.get("quantizations") or [])
        for item in user_items:
            family = str(item.get("family") or "")
            quant = str(item.get("quantization") or "")
            if family and family not in families:
                families.append(family)
            if quant and quant not in quants:
                quants.append(quant)
        payload["families"] = families
        payload["quantizations"] = quants
    try:
        state_base = base_dir or Path(str(configured_comfy_paths().get("base_dir") or BASE_DIR))
        annotate_catalog_install_state(payload.get("items", []), state_base)
    except (OSError, KeyError, TypeError):
        pass
    selected_id = selected_model_id if selected_model_id is not None else saved_model_catalog_id()
    selected = next(
        (
            item
            for item in payload.get("items", [])
            if isinstance(item, dict) and str(item.get("id") or "") == selected_id
        ),
        None,
    ) or catalog_item_by_id(selected_id)
    payload["selected_model_id"] = selected_id
    payload["selected_model"] = dict(selected or {})
    return payload


def external_workflow_detail() -> dict[str, Any]:
    item = catalog_item_by_id(saved_model_catalog_id()) or {}
    label = str(item.get("label") or "当前目标模型")
    platform_support = str(item.get("platform_support") or "manual")
    profile = CATALOG_INSTALL_PROFILES.get(str(item.get("default_install_profile") or "manual")) or {}
    official = platform_support == "official_workflow"
    errors = [str(item.get("workflow_support") or "").strip(), str(profile.get("external_requirement") or "").strip()]
    return {
        "message": f"{label} 需要通过{'官方 ComfyUI 工作流' if official else '手动接入工作流'}运行",
        "errors": [item for item in errors if item],
        "actions": [
            "先在第 1 步按当前模型档位准备 checkpoint 和节点。" if official else "按模型目录中的来源准备模型与工作流。",
            "在 ComfyUI 中打开模型节点提供的 workflow，再从该 workflow 生成视频。",
        ],
    }


def env_proxy_url() -> str:
    for name in PROXY_ENV_NAMES:
        try:
            proxy_url = normalize_proxy_url(os.environ.get(name))
        except ValueError:
            continue
        if proxy_url:
            return proxy_url
    return ""


def saved_proxy_url() -> str:
    try:
        return normalize_proxy_url(str(read_local_config().get("proxy_url") or ""))
    except ValueError:
        return ""


def effective_proxy_url() -> str:
    return env_proxy_url() or saved_proxy_url()


def env_pip_index_url() -> str:
    for name in PIP_INDEX_ENV_NAMES:
        try:
            pip_index = normalize_pip_index_url(os.environ.get(name))
        except ValueError:
            continue
        if pip_index:
            return pip_index
    return ""


def saved_pip_index_url() -> str:
    try:
        return normalize_pip_index_url(str(read_local_config().get("pip_index_url") or ""))
    except ValueError:
        return ""


def effective_pip_index_url() -> str:
    return env_pip_index_url() or saved_pip_index_url()


def effective_download_url(url: str, hf_endpoint: str | None = None) -> str:
    endpoint = normalize_hf_endpoint(hf_endpoint) if hf_endpoint is not None else effective_hf_endpoint()
    if not endpoint:
        return url
    parsed = urlparse(url)
    if parsed.hostname != "huggingface.co":
        return url
    mirror = urlparse(endpoint)
    mirror_path = mirror.path.rstrip("/")
    path = f"{mirror_path}{parsed.path}" if mirror_path else parsed.path
    return f"{mirror.scheme}://{mirror.netloc}{path}" + (f"?{parsed.query}" if parsed.query else "")


def download_settings_payload(*, include_sensitive: bool = False) -> dict[str, Any]:
    env_endpoint = env_hf_endpoint()
    saved_endpoint = saved_hf_endpoint()
    effective = env_endpoint or saved_endpoint
    env_proxy = env_proxy_url()
    saved_proxy = saved_proxy_url()
    effective_proxy = env_proxy or saved_proxy
    env_pip_index = env_pip_index_url()
    saved_pip_index = saved_pip_index_url()
    effective_pip_index = env_pip_index or saved_pip_index
    return {
        "hf_endpoint": effective,
        "saved_hf_endpoint": saved_endpoint,
        "env_hf_endpoint": env_endpoint,
        "source": "environment" if env_endpoint else "saved" if saved_endpoint else "official",
        "proxy_url": effective_proxy if include_sensitive else redact_url(effective_proxy),
        "saved_proxy_url": saved_proxy if include_sensitive else redact_url(saved_proxy),
        "env_proxy_url": redact_url(env_proxy),
        "proxy_source": "environment" if env_proxy else "saved" if saved_proxy else "none",
        "pip_index_url": effective_pip_index,
        "saved_pip_index_url": saved_pip_index,
        "env_pip_index_url": env_pip_index,
        "pip_index_source": "environment" if env_pip_index else "saved" if saved_pip_index else "official",
        "official_pip_index_url": "https://pypi.org/simple",
        "sensitive": include_sensitive,
        "official_hf_endpoint": "https://huggingface.co",
        "download_region": saved_download_region() or ("custom" if saved_endpoint or saved_pip_index else "international"),
        "source_presets": DOWNLOAD_SOURCE_PRESETS,
        "config_file": str(LOCAL_CONFIG_FILE),
    }


def apply_effective_download_env(env: dict[str, str]) -> dict[str, str]:
    endpoint = effective_hf_endpoint()
    if endpoint:
        env["WAN22_HF_ENDPOINT"] = endpoint
    proxy_url = effective_proxy_url()
    if proxy_url:
        for name in ("HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy"):
            env[name] = proxy_url
    pip_index_url = effective_pip_index_url()
    if pip_index_url:
        env["PIP_INDEX_URL"] = pip_index_url
    return env


def download_subprocess_env() -> dict[str, str]:
    return apply_effective_download_env(os.environ.copy())


def call_with_download_env(func: Any, *args: Any, **kwargs: Any) -> Any:
    with DOWNLOAD_ENV_LOCK:
        original = {name: os.environ.get(name) for name in (*HF_ENDPOINT_ENV_NAMES, *PROXY_ENV_NAMES, *PIP_INDEX_ENV_NAMES)}
        try:
            apply_effective_download_env(os.environ)
            return func(*args, **kwargs)
        finally:
            for name, value in original.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value


def default_comfy_base_dir() -> Path:
    configured = os.environ.get("COMFY_BASE_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    desktop_shared = detected_comfy_desktop_shared_dir()
    if desktop_shared:
        return desktop_shared
    parent = WORKSPACE_DIR.parent
    if looks_like_comfy_base(parent):
        return parent.resolve()
    return WORKSPACE_DIR.resolve()


def looks_like_comfy_install_dir(path: Path) -> bool:
    return (path / "main.py").exists() or (path / ".git").exists()


def install_dir_available(path: Path) -> bool:
    return not path.exists() or not any(path.iterdir()) or looks_like_comfy_install_dir(path)


def default_comfy_install_dir(base_dir: Path) -> Path:
    configured = os.environ.get("COMFY_INSTALL_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    preferred = (base_dir / "ComfyUI").expanduser().resolve()
    if install_dir_available(preferred):
        return preferred
    project_local = (WORKSPACE_DIR / "ComfyUI").expanduser().resolve()
    if project_local != preferred and install_dir_available(project_local):
        return project_local
    return preferred


BASE_DIR = default_comfy_base_dir()
INPUT_DIR = BASE_DIR / "input"
OUTPUT_DIR = BASE_DIR / "output"
TEMP_DIR = BASE_DIR / "temp"
UPLOAD_DIR = INPUT_DIR / "beginner_frontend"
STATIC_DIR = APP_DIR / "static"

COMFY_URL_CONFIGURED = bool(os.environ.get("COMFY_URL"))
COMFY_URL = os.environ.get("COMFY_URL", "http://127.0.0.1:8188").rstrip("/")
CLIENT_ID = f"beginner-frontend-{uuid.uuid4()}"
COMFY_INSTALL_DIR = default_comfy_install_dir(BASE_DIR)

KEYFRAME_UPLOAD_PLACEHOLDER = "keyframe-upload-required.png"
IMAGE_EDIT_SOURCE_PLACEHOLDER = "beginner_frontend/image-edit-source.png"
FACE_AUTHORIZATION_STATEMENT = (
    "我确认我是照片中的本人，或已获得照片中所有可识别人物的明确授权，"
    "可以提取并处理其面部用于本次图片生成。"
)
FACE_SWAP_AUTHORIZATION_STATEMENT = (
    "我确认目标图片和身份参考图片中的所有可识别人物均为本人，或我已取得其明确授权，"
    "可以在本机提取、比对并替换所选面部用于本次图片微调。"
)
FACE_SWAP_INSTALL_PROFILE = "face-swap-reactor"
FACE_AUTH_TOKEN_TTL_SECONDS = 6 * 3600


def issue_face_authorization_token(*, statement: str = FACE_AUTHORIZATION_STATEMENT) -> str:
    token = uuid.uuid4().hex
    with FACE_EXTRACTION_LOCK:
        FACE_AUTH_TOKENS[token] = {
            "created_at": time.time(),
            "statement": str(statement or FACE_AUTHORIZATION_STATEMENT),
        }
    return token


def face_authorization_token_valid(token: str) -> bool:
    value = str(token or "").strip()
    if not value:
        return False
    with FACE_EXTRACTION_LOCK:
        record = FACE_AUTH_TOKENS.get(value)
        if not record:
            return False
        age = time.time() - float(record.get("created_at") or 0)
        if age > FACE_AUTH_TOKEN_TTL_SECONDS:
            FACE_AUTH_TOKENS.pop(value, None)
            return False
    return True


def resolve_face_authorization(
    *,
    confirmed: bool,
    token: str = "",
    statement: str = FACE_AUTHORIZATION_STATEMENT,
) -> tuple[bool, str]:
    if confirmed:
        return True, issue_face_authorization_token(statement=statement)
    if face_authorization_token_valid(token):
        return True, str(token).strip()
    return False, ""


DEFAULT_PROMPT = ""
SMOKE_TEST_PROMPT = (
    "a simple red ceramic cup on a wooden table, natural daylight, static camera, "
    "realistic details, short stable video, no scene cuts"
)
DEFAULT_NEGATIVE = (
    "overexposed, low quality, blurry, jpeg artifacts, distorted hands, deformed face, "
    "extra fingers, warped screens, unreadable text, watermark, subtitles, flicker, "
    "jitter, chaotic background"
)

VIDEO_UNRESTRICTED_MODES = frozenset(
    {
        "i2v_a14b",
        "t2v_a14b",
        "minimax_h3_t2v",
        "minimax_h3_i2v",
        "minimax_h3_r2v",
        "ltx25_t2v",
        "ltx25_i2v",
    }
)


def video_mode_allows_unrestricted(mode: str) -> bool:
    return str(mode or "") in VIDEO_UNRESTRICTED_MODES

LTX23_DEV_CHECKPOINT = "ltx-2.3-22b-dev-fp8.safetensors"
LTX23_NVFP4_CHECKPOINT = "ltx-2.3-22b-dev-nvfp4.safetensors"
LTX23_TEXT_ENCODER = "gemma_3_12B_it_fp4_mixed.safetensors"
LTX23_DISTILLED_LORA = "ltx-2.3-22b-distilled-lora-384.safetensors"
LTX23_DISTILLED_LORA_ALTERNATIVES = (
    "ltx_2.3_22b_distilled_1.1_lora_dynamic_fro09_avg_rank_111_bf16.safetensors",
)
LTX23_SPATIAL_UPSCALER = "ltx-2.3-spatial-upscaler-x2-1.1.safetensors"
LTX25_DISTILLED_INT8_MODEL = "ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors"
LTX25_DISTILLED_NVFP4_MODEL = "ltx-2.5-22b-distilled-transformer-nvfp4.safetensors"
LTX25_TEXT_ENCODER = "gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors"
LTX25_VIDEO_VAE_DIFF = "ltx-2.5-video-vae-bf16.safetensors"
LTX25_VIDEO_VAE_CONV = "ltx-2.5-video-vae-conv-bf16.safetensors"
LTX25_AUDIO_VAE = "ltx-2.5-audio-vae-bf16.safetensors"
LTX25_SPATIAL_UPSCALER = "ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors"
LTX25_DURATION_HEAD = "ltx-2.5-duration-head-bf16.safetensors"
HUNYUAN15_T2V_720_MODEL = "hunyuanvideo1.5_720p_t2v_fp16.safetensors"
HUNYUAN15_I2V_720_MODEL = "hunyuanvideo1.5_720p_i2v_fp16.safetensors"
HUNYUAN15_T2V_480_MODEL = "hunyuanvideo1.5_480p_t2v_cfg_distilled_fp8_scaled.safetensors"
HUNYUAN15_I2V_480_MODEL = "hunyuanvideo1.5_480p_i2v_cfg_distilled_fp8_scaled.safetensors"
HUNYUAN15_QWEN_ENCODER = "qwen_2.5_vl_7b_fp8_scaled.safetensors"
HUNYUAN15_BYT5_ENCODER = "byt5_small_glyphxl_fp16.safetensors"
HUNYUAN15_VAE = "hunyuanvideo15_vae_fp16.safetensors"
HUNYUAN15_SIGCLIP = "sigclip_vision_patch14_384.safetensors"
MINIMAX_H3_FL2VA_MODEL = "minimax_h3_fl2va_pruned_int8_convrot.safetensors"
MINIMAX_H3_REF2VA_MODEL = "minimax_h3_ref2va_pruned_int8_convrot.safetensors"
MINIMAX_H3_TEXT_ENCODER = "qwen3vl_32b_minimax_h3_int8_convrot.safetensors"
MINIMAX_H3_VIDEO_VAE = "minimax_h3_video_vae_fp16.safetensors"
MINIMAX_H3_AUDIO_VAE = "minimax_h3_audio_vae_fp32.safetensors"
MINIMAX_H3_LIGHTX4_V11_LORA = "minimax_h3_fl2v_turbo_4step_v1.1_768p_comfyui_bf16.safetensors"
MINIMAX_H3_LIGHTX8_V10_LORA = "minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors"
MINIMAX_H3_REF_LIGHTX4_V01_LORA = "minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors"
FAL_H3_MAX_T2V_ENDPOINT = "minimax/h3-max/text-to-video"
FAL_H3_MAX_I2V_ENDPOINT = "minimax/h3-max/image-to-video"
FAL_QUEUE_ORIGIN = "https://queue.fal.run"
FAL_H3_MAX_MAX_IMAGE_BYTES = 20 * 1024 * 1024
SEEDVR2_3B_MODEL = "seedvr2_3b_int8_convrot.safetensors"
SEEDVR2_7B_MODEL = "seedvr2_7b_nvfp4.safetensors"
SEEDVR2_7B_SHARP_MODEL = "seedvr2_7b_sharp_nvfp4.safetensors"
SEEDVR2_MODELS = {SEEDVR2_3B_MODEL, SEEDVR2_7B_MODEL, SEEDVR2_7B_SHARP_MODEL}
SEEDVR2_VIDEO_VAE = "seedvr2_ema_vae_fp16.safetensors"
try:
    MAX_VIDEO_FRAMES = max(241, min(2001, int(os.environ.get("BEGINNER_FRONTEND_MAX_VIDEO_FRAMES", "481"))))
except ValueError:
    MAX_VIDEO_FRAMES = 481

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi"}
AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".m4a", ".aac", ".ogg"}
IMAGE_STUDIO_OUTPUT_SUBDIR = "image_studio"
VIDEO_OUTPUT_SUBDIR = "local_ai_workbench"
LEGACY_VIDEO_OUTPUT_SUBDIRS = ("wan22_frontend",)
REQUIRED_IMAGE_WORKFLOW_MODES = video_params.required_image_modes()
VIDEO_SMOKE_MODES = video_params.smoke_test_modes()
VIDEO_GENERATION_MODES = video_params.generation_modes()

JOBS: dict[str, dict[str, Any]] = {}
INSTALL_JOBS: dict[str, dict[str, Any]] = {}
INSTALL_PROCESSES: dict[str, subprocess.Popen[str]] = {}
LOCAL_VIDEO_PROCESSES: dict[str, subprocess.Popen[str]] = {}
FACE_EXTRACTIONS: dict[str, dict[str, Any]] = {}
FACE_AUTH_TOKENS: dict[str, dict[str, Any]] = {}
JOB_STORE_LOCK = threading.RLock()
INSTALL_JOB_LOCK = threading.RLock()
LOCAL_VIDEO_PROCESS_LOCK = threading.RLock()
FACE_EXTRACTION_LOCK = threading.RLock()
JOB_PERSIST_LOCK = threading.RLock()
COMFY_STATE_LOCK = threading.RLock()
COMFY_DISCOVERY_ASYNC_LOCKS: dict[asyncio.AbstractEventLoop, asyncio.Lock] = {}
JOB_REFRESH_ASYNC_LOCKS: dict[tuple[asyncio.AbstractEventLoop, str], asyncio.Lock] = {}
JOB_PROGRESS_SIGNALS: dict[tuple[asyncio.AbstractEventLoop, str], asyncio.Event] = {}
COMFY_PROGRESS_TASKS: dict[asyncio.AbstractEventLoop, asyncio.Task[None]] = {}
COMFY_PROGRESS_READY_EVENTS: dict[asyncio.AbstractEventLoop, asyncio.Event] = {}
COMFY_PROGRESS_TASK_URLS: dict[asyncio.AbstractEventLoop, str] = {}
COMFY_PROGRESS_LISTENER_LOCK = threading.RLock()
try:
    MAX_COMPLETED_JOBS = max(100, min(5000, int(os.environ.get("BEGINNER_FRONTEND_MAX_COMPLETED_JOBS", "1000"))))
except ValueError:
    MAX_COMPLETED_JOBS = 1000
MAX_COMPLETED_INSTALL_JOBS = 50
HEAVY_INSTALL_KINDS = {"full_setup", "install_comfyui", "install_workflow_assets"}
TERMINAL_JOB_STATUSES = {"success", "failed", "error", "stopped", "lost", "canceled", "cancelled", "interrupted"}
RUNTIME_DIR = WORKSPACE_DIR / ".runtime"
JOB_STORE_PATH = Path(os.environ.get("BEGINNER_FRONTEND_JOB_STORE", str(RUNTIME_DIR / "jobs.json")))
COMFY_LOG_PATH = Path(os.environ.get("BEGINNER_FRONTEND_COMFY_LOG", str(RUNTIME_DIR / "comfyui.log")))
JOB_PERSISTENCE_ENABLED = os.environ.get("BEGINNER_FRONTEND_DISABLE_JOB_PERSISTENCE", "").strip().lower() not in {"1", "true", "yes"}
JOB_PERSIST_INTERVAL_SECONDS = 3.0
_LAST_JOB_PERSIST_AT = 0.0
COMFY_PROCESS: subprocess.Popen[str] | None = None
COMFY_START_JOB_ID: str | None = None
COMFY_DISCOVERY_CACHE: dict[str, Any] = {"url": None, "checked_at": 0.0, "errors": []}
COMFY_DISCOVERY_SUCCESS_TTL = 15.0
COMFY_DISCOVERY_FAILURE_TTL = 4.0
COMFY_DISCOVERY_TIMEOUT = 1.5
OBJECT_INFO_CACHE: dict[str, Any] = {"url": None, "value": None, "checked_at": 0.0}
OBJECT_INFO_CACHE_TTL = 60.0
OBJECT_INFO_ASYNC_LOCKS: dict[asyncio.AbstractEventLoop, asyncio.Lock] = {}
ENVIRONMENT_CACHE: dict[str, Any] = {"value": None, "checked_at": 0.0}
ENVIRONMENT_CACHE_TTL = 30.0
ENVIRONMENT_ASYNC_LOCKS: dict[asyncio.AbstractEventLoop, asyncio.Lock] = {}
HARDWARE_PROBE_CACHE: dict[str, Any] = {"value": None, "checked_at": 0.0}
HARDWARE_PROBE_CACHE_TTL = 30.0
HARDWARE_PROBE_LOCK = threading.RLock()
CATALOG_FILE_INDEX_CACHE: dict[str, dict[str, Any]] = {}
CATALOG_FILE_INDEX_TTL = 300.0
CATALOG_FILE_INDEX_LOCK = threading.RLock()
DOWNLOAD_CENTER_RESOURCE_CACHE: dict[str, Any] = {"key": "", "value": [], "checked_at": 0.0}
DOWNLOAD_CENTER_RESOURCE_CACHE_TTL = 4.0
DOWNLOAD_CENTER_RESOURCE_CACHE_LOCK = threading.RLock()


class VersionedStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope: dict[str, Any]) -> Response:
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


app = FastAPI(title="Local AI Video Workbench")
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=(
        r"^https?://(localhost|127\.\d+\.\d+\.\d+|\[::1\]|"
        r"192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+|"
        r"172\.(1[6-9]|2\d|3[01])\.\d+\.\d+)(:\d+)?$"
    ),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", VersionedStaticFiles(directory=STATIC_DIR), name="static")


def prune_completed_job_store(store: dict[str, dict[str, Any]], *, keep: int) -> None:
    completed = sorted(
        (
            (job_id, job)
            for job_id, job in store.items()
            if job.get("completed") or str(job.get("status") or "").lower() in TERMINAL_JOB_STATUSES
        ),
        key=lambda item: item[1].get("finished_at") or item[1].get("created_at") or 0,
        reverse=True,
    )
    for job_id, _job in completed[keep:]:
        store.pop(job_id, None)


def job_is_terminal(job: dict[str, Any]) -> bool:
    return bool(job.get("completed")) or str(job.get("status") or "").lower() in TERMINAL_JOB_STATUSES


def signal_generation_job(job_id: str) -> None:
    with JOB_STORE_LOCK:
        signals = [
            (loop, signal_event)
            for (loop, signal_job_id), signal_event in JOB_PROGRESS_SIGNALS.items()
            if signal_job_id == job_id
        ]
    for loop, signal_event in signals:
        if not loop.is_closed():
            loop.call_soon_threadsafe(signal_event.set)


def persist_job_stores(*, force: bool = False) -> None:
    global _LAST_JOB_PERSIST_AT
    if not JOB_PERSISTENCE_ENABLED:
        return
    now = time.monotonic()
    with JOB_PERSIST_LOCK:
        if not force and now - _LAST_JOB_PERSIST_AT < JOB_PERSIST_INTERVAL_SECONDS:
            return
        with JOB_STORE_LOCK, INSTALL_JOB_LOCK:
            payload = {
                "version": 1,
                "saved_at": int(time.time() * 1000),
                "generation_jobs": JOBS,
                "install_jobs": INSTALL_JOBS,
            }
            serialized = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
        try:
            JOB_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
            temporary = JOB_STORE_PATH.with_name(
                f"{JOB_STORE_PATH.name}.{os.getpid()}.{threading.get_ident()}.tmp"
            )
            temporary.write_text(serialized, encoding="utf-8")
            os.replace(temporary, JOB_STORE_PATH)
            _LAST_JOB_PERSIST_AT = now
        except OSError:
            # Job persistence must never take down the generation or install worker.
            return


def load_persisted_job_stores() -> None:
    if not JOB_PERSISTENCE_ENABLED or not JOB_STORE_PATH.is_file():
        return
    try:
        payload = json.loads(JOB_STORE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return

    generation_jobs = payload.get("generation_jobs") if isinstance(payload, dict) else None
    install_jobs = payload.get("install_jobs") if isinstance(payload, dict) else None
    now = int(time.time() * 1000)
    with JOB_STORE_LOCK:
        if isinstance(generation_jobs, dict):
            for job_id, raw_job in generation_jobs.items():
                if not isinstance(raw_job, dict):
                    continue
                job = dict(raw_job)
                job["id"] = str(job.get("id") or job_id)
                if not job_is_terminal(job):
                    if job.get("local"):
                        job.update(
                            {
                                "status": "interrupted",
                                "completed": True,
                                "finished_at": now,
                                "error": "前端重启中断了本地处理，请重新提交该步骤。",
                            }
                        )
                    elif job.get("provider") == "fal":
                        job["status"] = "reconnecting"
                        job["completed"] = False
                        job["recovered"] = True
                        job["connection_error"] = "前端已重启，正在从 fal 队列恢复任务状态。"
                    else:
                        job["status"] = "reconnecting"
                        job["completed"] = False
                        job["recovered"] = True
                        job["missing_seen_at"] = now
                        job["connection_error"] = "前端已重启，正在从 ComfyUI 恢复任务状态。"
                JOBS[job["id"]] = job
        prune_completed_job_store(JOBS, keep=MAX_COMPLETED_JOBS)

    with INSTALL_JOB_LOCK:
        if isinstance(install_jobs, dict):
            for job_id, raw_job in install_jobs.items():
                if not isinstance(raw_job, dict):
                    continue
                job = dict(raw_job)
                job["id"] = str(job.get("id") or job_id)
                if not job_is_terminal(job):
                    if str(job.get("status") or "").lower() in {"paused", "pausing"} and job.get("command_args"):
                        job.update({"status": "paused", "completed": False, "control_action": "pause"})
                        job.setdefault("log", []).append("前端已重启，下载仍保持暂停；可以从原任务继续断点续传。")
                    else:
                        job.update(
                            {
                                "status": "interrupted",
                                "completed": True,
                                "finished_at": now,
                                "error": "前端重启中断了安装进程；已下载的 .part 文件会保留，可重新安装并断点续传。",
                            }
                        )
                        job.setdefault("log", []).append(job["error"])
                INSTALL_JOBS[job["id"]] = job
        prune_completed_job_store(INSTALL_JOBS, keep=MAX_COMPLETED_INSTALL_JOBS)


def store_install_job(job: dict[str, Any], *, exclusive: bool = False) -> dict[str, Any]:
    with INSTALL_JOB_LOCK:
        if exclusive:
            active = next(
                (
                    item
                    for item in INSTALL_JOBS.values()
                    if not item.get("completed") and item.get("kind") in HEAVY_INSTALL_KINDS
                ),
                None,
            )
            if active:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "message": "已有安装任务正在运行",
                        "errors": [f"{active.get('kind') or 'install'}：{active.get('id')}"],
                        "actions": ["等待当前任务完成后再执行新的安装或一键准备。"],
                    },
                )
        INSTALL_JOBS[str(job["id"])] = job
        prune_completed_job_store(INSTALL_JOBS, keep=MAX_COMPLETED_INSTALL_JOBS)
    persist_job_stores(force=True)
    return job


HEAVY_GENERATION_KINDS = {
    "video_generation",
    "video_face_swap",
    "video_smoke_test",
    "video_postprocess",
}


def store_generation_job(job: dict[str, Any], *, exclusive: bool = False) -> dict[str, Any]:
    with JOB_STORE_LOCK:
        if exclusive:
            active = next(
                (
                    item
                    for item in JOBS.values()
                    if not job_is_terminal(item)
                    and not item.get("local")
                    and item.get("provider") != "fal"
                    and str(item.get("kind") or "") in HEAVY_GENERATION_KINDS
                ),
                None,
            )
            if active:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "message": "已有视频任务正在生成",
                        "errors": [f"{active.get('kind') or 'generation'}：{active.get('id')}"],
                        "actions": ["等待当前任务完成或先取消它，再提交新的视频任务。"],
                    },
                )
        JOBS[str(job["id"])] = job
        prune_completed_job_store(JOBS, keep=MAX_COMPLETED_JOBS)
    persist_job_stores(force=True)
    return job


def reserve_generation_job_slot(
    *,
    job_id: str,
    kind: str,
    mode: str,
    title: str,
    created_at: int,
) -> dict[str, Any]:
    """Reserve the single heavy-generation slot before submitting to ComfyUI."""
    reservation = {
        "id": job_id,
        "kind": kind,
        "mode": mode,
        "title": title,
        "status": "submitting",
        "completed": False,
        "created_at": created_at,
        "media": [],
        "prompt_ids": [],
        "reservation": True,
    }
    reservation["progress"] = {
        "percent": 0.0,
        "label": "正在提交到 ComfyUI",
        "source": "frontend",
        "accurate": False,
    }
    return store_generation_job(reservation, exclusive=True)


def finalize_generation_job_slot(job: dict[str, Any]) -> dict[str, Any]:
    job_id = str(job.get("id") or "")
    if not job_id:
        raise ValueError("任务缺少 id，无法完成提交")
    completed = dict(job)
    completed.pop("reservation", None)
    with JOB_STORE_LOCK:
        JOBS[job_id] = completed
        prune_completed_job_store(JOBS, keep=MAX_COMPLETED_JOBS)
    persist_job_stores(force=True)
    return completed


def fail_generation_job_slot(job_id: str, error: str) -> None:
    with JOB_STORE_LOCK:
        reservation = JOBS.get(str(job_id))
        if not reservation or not reservation.get("reservation"):
            return
        reservation.update(
            {
                "status": "failed",
                "completed": True,
                "finished_at": now_ms(),
                "error": str(error or "无法提交到 ComfyUI"),
            }
        )
        reservation.pop("reservation", None)
    persist_job_stores(force=True)


async def reconcile_heavy_generation_jobs_before_submit() -> None:
    """Refresh every non-terminal heavy job so stale recovered jobs cannot block a new run."""
    with JOB_STORE_LOCK:
        job_ids = [
            str(item.get("id") or "")
            for item in JOBS.values()
            if not job_is_terminal(item)
            and not item.get("local")
            and item.get("provider") != "fal"
            and not item.get("reservation")
            and str(item.get("kind") or "") in HEAVY_GENERATION_KINDS
        ]
    if not job_ids:
        return
    await asyncio.gather(
        *(refresh_generation_job(job_id) for job_id in job_ids if job_id),
        return_exceptions=True,
    )


load_persisted_job_stores()


# 局域网访问下，除写操作外，这些只读接口也必须带令牌：
# 它们能列出/下载全部生成的视频、图片和任务提示词，属于隐私内容。
PROTECTED_READ_API_PREFIXES = (
    "/api/media",
    "/api/view",
    "/api/outputs",
    "/api/jobs",
    "/api/image-studio/history",
    "/api/image-studio/output",
)


def is_protected_read_path(path: str) -> bool:
    return any(path == prefix or path.startswith(prefix + "/") for prefix in PROTECTED_READ_API_PREFIXES)


@app.middleware("http")
async def require_remote_write_token(request: Request, call_next):
    token = configured_access_token()
    if (
        token
        and request.url.path.startswith("/api/")
        and not is_loopback_request(request)
        and (
            request.method not in {"GET", "HEAD", "OPTIONS"}
            or (request.method in {"GET", "HEAD"} and is_protected_read_path(request.url.path))
        )
    ):
        supplied = (
            request.headers.get("X-Local-AI-Token")
            or request.headers.get("X-WAN22-Token")
            or request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
            or request.query_params.get("token", "")
        )
        if not hmac.compare_digest(supplied, token):
            return JSONResponse(
                status_code=401,
                content={
                    "detail": {
                        "message": "远程访问该接口需要访问令牌",
                        "actions": ["在客户端服务面板填写服务端显示的访问令牌。"],
                    }
                },
            )
    return await call_next(request)


def configured_comfy_paths() -> dict[str, Any]:
    return {
        "base_dir": BASE_DIR,
        "input_dir": INPUT_DIR,
        "output_dir": OUTPUT_DIR,
        "temp_dir": TEMP_DIR,
        "user_dir": BASE_DIR / "user",
        "source": "configured",
    }


def path_from_arg(argv: list[Any], flag: str) -> str | None:
    for index, item in enumerate(argv):
        value = str(item)
        if value == flag and index + 1 < len(argv):
            return str(argv[index + 1])
        prefix = f"{flag}="
        if value.startswith(prefix):
            return value[len(prefix) :]
    return None


def infer_comfy_main_from_argv(argv: list[Any]) -> Path | None:
    for item in argv:
        value = str(item)
        if Path(value).name.lower() == "main.py":
            main_path = Path(value).expanduser()
            if main_path.is_absolute():
                return main_path.resolve()
    return None


def comfy_paths_from_system_stats(system_stats: dict[str, Any] | None) -> dict[str, Any]:
    paths = configured_comfy_paths()
    argv = ((system_stats or {}).get("system") or {}).get("argv") or []
    source = "running_comfyui" if system_stats is not None else "configured"
    base_dir_source = "configured"
    inferred_main = infer_comfy_main_from_argv(argv)
    if inferred_main:
        paths["main_py"] = inferred_main

    base_arg = path_from_arg(argv, "--base-directory")
    if base_arg:
        paths["base_dir"] = Path(base_arg).expanduser().resolve()
        base_dir_source = "argv_base_directory"
    elif system_stats is not None:
        if inferred_main:
            paths["base_dir"] = inferred_main.parent
            base_dir_source = "argv_main_py"
        else:
            base_dir_source = "configured_fallback"

    base_dir = Path(paths["base_dir"])
    for key, flag, fallback in [
        ("input_dir", "--input-directory", base_dir / "input"),
        ("output_dir", "--output-directory", base_dir / "output"),
        ("temp_dir", "--temp-directory", base_dir / "temp"),
        ("user_dir", "--user-directory", base_dir / "user"),
    ]:
        arg = path_from_arg(argv, flag)
        paths[key] = Path(arg).expanduser().resolve() if arg else fallback

    paths["source"] = source
    paths["base_dir_source"] = base_dir_source
    paths["base_dir_mismatch"] = Path(paths["base_dir"]).resolve() != BASE_DIR.resolve()
    return paths


def serializable_comfy_paths(paths: dict[str, Any]) -> dict[str, Any]:
    return {
        "configured_base_dir": str(BASE_DIR),
        "active_base_dir": str(paths["base_dir"]),
        "input_dir": str(paths["input_dir"]),
        "output_dir": str(paths["output_dir"]),
        "temp_dir": str(paths["temp_dir"]),
        "user_dir": str(paths["user_dir"]),
        "source": paths.get("source", "configured"),
        "base_dir_source": paths.get("base_dir_source", "configured"),
        "main_py": str(paths["main_py"]) if paths.get("main_py") else "",
        "base_dir_mismatch": bool(paths.get("base_dir_mismatch")),
    }


async def active_comfy_paths() -> dict[str, Any]:
    try:
        system_stats = await comfy_get("/system_stats")
    except HTTPException:
        return configured_comfy_paths()
    return comfy_paths_from_system_stats(system_stats)


def upload_dir_for(paths: dict[str, Any] | None = None) -> Path:
    return Path((paths or configured_comfy_paths())["input_dir"]) / "beginner_frontend"


def os_release_label() -> str:
    # platform.release() 在 Windows 11 上仍返回 "10"（内核版本），
    # 用 build 号（>=22000 即 Win11）修正展示，避免诊断信息误导。
    release = platform.release()
    if platform.system() == "Windows" and release == "10":
        try:
            if sys.getwindowsversion().build >= 22000:
                return "11"
        except (AttributeError, OSError):
            pass
    return release


def now_ms() -> int:
    return int(time.time() * 1000)


def current_comfy_url() -> str:
    with COMFY_STATE_LOCK:
        return COMFY_URL


def set_current_comfy_url(url: str) -> str:
    global COMFY_URL
    normalized = url.rstrip("/")
    with COMFY_STATE_LOCK:
        COMFY_URL = normalized
    return normalized


def discovery_async_lock() -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    with COMFY_STATE_LOCK:
        return COMFY_DISCOVERY_ASYNC_LOCKS.setdefault(loop, asyncio.Lock())


def object_info_async_lock() -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    with COMFY_STATE_LOCK:
        return OBJECT_INFO_ASYNC_LOCKS.setdefault(loop, asyncio.Lock())


def environment_async_lock() -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    with COMFY_STATE_LOCK:
        return ENVIRONMENT_ASYNC_LOCKS.setdefault(loop, asyncio.Lock())


def job_refresh_async_lock(job_id: str) -> asyncio.Lock:
    key = (asyncio.get_running_loop(), job_id)
    with JOB_STORE_LOCK:
        return JOB_REFRESH_ASYNC_LOCKS.setdefault(key, asyncio.Lock())


def invalidate_runtime_caches(*, include_hardware: bool = False) -> None:
    with COMFY_STATE_LOCK:
        OBJECT_INFO_CACHE.update({"url": None, "value": None, "checked_at": 0.0})
        ENVIRONMENT_CACHE.update({"value": None, "checked_at": 0.0})
    with CATALOG_FILE_INDEX_LOCK:
        CATALOG_FILE_INDEX_CACHE.clear()
    if include_hardware:
        with HARDWARE_PROBE_LOCK:
            HARDWARE_PROBE_CACHE.update({"value": None, "checked_at": 0.0})


def common_comfy_urls() -> list[str]:
    urls = [current_comfy_url()]
    if not COMFY_URL_CONFIGURED:
        urls.extend(
            [
                "http://127.0.0.1:8000",
                "http://127.0.0.1:8188",
                "http://localhost:8000",
                "http://localhost:8188",
            ]
        )
    unique: list[str] = []
    for url in urls:
        normalized = url.rstrip("/")
        if normalized not in unique:
            unique.append(normalized)
    return unique


COMFY_HTTP_CLIENTS: dict[asyncio.AbstractEventLoop, httpx.AsyncClient] = {}


def comfy_http_client() -> httpx.AsyncClient:
    loop = asyncio.get_running_loop()
    client = COMFY_HTTP_CLIENTS.get(loop)
    if client is None or client.is_closed:
        # ComfyUI control traffic must not inherit download/system proxies, especially on loopback.
        client = httpx.AsyncClient(
            trust_env=False,
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )
        COMFY_HTTP_CLIENTS[loop] = client
    return client


async def request_comfy_json(
    method: str,
    base_url: str,
    path: str,
    payload: dict[str, Any] | None = None,
    timeout: float | None = None,
) -> Any:
    timeout = timeout if timeout is not None else (60 if method == "POST" else 30)
    client = comfy_http_client()
    if method == "POST":
        response = await client.post(f"{base_url}{path}", json=payload, timeout=timeout)
    else:
        response = await client.get(f"{base_url}{path}", timeout=timeout)
    if response.status_code >= 400:
        try:
            detail = response.json()
        except ValueError:
            detail = response.text
        raise HTTPException(status_code=response.status_code, detail=detail)
    return response.json()


def comfy_connection_error_text(exc: BaseException | Any) -> str:
    if isinstance(exc, HTTPException):
        detail = exc.detail
        if isinstance(detail, (dict, list)):
            return json.dumps(detail, ensure_ascii=False)
        text = str(detail or "").strip()
        return text or "ComfyUI 返回了空错误。"
    if isinstance(exc, (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.TimeoutException)):
        return "连接超时，请确认 ComfyUI 已启动且端口可访问。"
    if isinstance(exc, httpx.ConnectError):
        return "连接被拒绝，请先启动 ComfyUI，或检查端口是否为 8000/8188。"
    if isinstance(exc, ValueError):
        return "返回内容不是 ComfyUI JSON，请确认该端口运行的是 ComfyUI。"
    text = str(exc or "").strip()
    return text or exc.__class__.__name__


async def discover_comfy_url(force: bool = False) -> tuple[str | None, list[str]]:
    def cached_result() -> tuple[str | None, list[str]] | None:
        now = time.time()
        with COMFY_STATE_LOCK:
            cached_url = COMFY_DISCOVERY_CACHE.get("url")
            checked_at = float(COMFY_DISCOVERY_CACHE.get("checked_at") or 0)
            errors = list(COMFY_DISCOVERY_CACHE.get("errors") or [])
        if not force and cached_url and now - checked_at < COMFY_DISCOVERY_SUCCESS_TTL:
            return str(cached_url), []
        if not force and not cached_url and checked_at and now - checked_at < COMFY_DISCOVERY_FAILURE_TTL:
            return None, errors
        return None

    cached = cached_result()
    if cached is not None:
        return cached

    async with discovery_async_lock():
        cached = cached_result()
        if cached is not None:
            return cached

        errors: list[str] = []
        for url in common_comfy_urls():
            try:
                await request_comfy_json("GET", url, "/system_stats", timeout=COMFY_DISCOVERY_TIMEOUT)
                discovered = set_current_comfy_url(url)
                with COMFY_STATE_LOCK:
                    COMFY_DISCOVERY_CACHE.update({"url": discovered, "checked_at": time.time(), "errors": []})
                return discovered, []
            except HTTPException as exc:
                errors.append(f"{url}: {comfy_connection_error_text(exc)}")
            except (httpx.HTTPError, ValueError) as exc:
                errors.append(f"{url}: {comfy_connection_error_text(exc)}")
        with COMFY_STATE_LOCK:
            COMFY_DISCOVERY_CACHE.update({"url": None, "checked_at": time.time(), "errors": errors})
        return None, errors


def safe_filename(name: str) -> str:
    suffix = Path(name).suffix.lower()
    stem = Path(name).stem
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-") or "upload"
    return f"{stem}_{uuid.uuid4().hex[:8]}{suffix}"


def clamp_int(value: int, low: int, high: int) -> int:
    return max(low, min(high, int(value)))


def clamp_float(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


def normalize_frames(length: int) -> int:
    length = clamp_int(length, 17, MAX_VIDEO_FRAMES)
    # Wan video latents use 1 + 4n frame counts.
    return 1 + 4 * round((length - 1) / 4)


def normalize_ltx_frames(length: int) -> int:
    length = clamp_int(length, 9, MAX_VIDEO_FRAMES)
    # LTXV latent video nodes use 1 + 8n frame counts.
    return 1 + 8 * round((length - 1) / 8)


def normalize_minimax_h3_frames(length: int) -> int:
    """Snap to H3's 17k+5 frame grid and stay inside its trained 15s range."""
    length = clamp_int(length, 5, 362)
    aligned = length + (5 - (length % 17)) % 17
    return min(aligned, 362)


def normalize_dimension(value: int, maximum: int = 1536) -> int:
    value = clamp_int(value, 256, maximum)
    return max(32, round(value / 32) * 32)


def normalize_mode_dimensions(mode: str, width: int, height: int) -> tuple[int, int]:
    maximum = clamp_int(video_params.mode_capabilities(mode).get("max_dimension", 1536), 1536, 4096)
    return normalize_dimension(width, maximum), normalize_dimension(height, maximum)


def normalize_seed(seed: str | int | None) -> int:
    if seed in (None, "", "-1"):
        return random.randint(0, 2**63 - 1)
    try:
        parsed = int(seed)
    except ValueError:
        return random.randint(0, 2**63 - 1)
    if parsed < 0:
        return random.randint(0, 2**63 - 1)
    return parsed


def text_or_default(value: str | None, fallback: str) -> str:
    if not isinstance(value, str):
        return fallback
    value = value.strip()
    return value or fallback


# 当前请求的项目标签：/api/generate 在构图前设置，output_prefix 据此把输出
# 落到项目子目录，避免逐个改动十几处 graph builder 的调用签名。
CURRENT_PROJECT_TAG: contextvars.ContextVar[str] = contextvars.ContextVar("current_project_tag", default="")


def sanitize_project_tag(value: str | None) -> str:
    """项目标签用作输出子目录名：保留中英文与数字，剔除路径与非法字符。"""
    text = re.sub(r"\s+", " ", str(value or "").strip())
    text = re.sub(r'[\\/<>:"|?*\x00-\x1f]+', "", text)
    text = text.strip(". ")
    if text in {"", ".", "..", OUTPUT_TRASH_DIRNAME}:
        return ""
    return text.replace(" ", "_")[:40]


def output_prefix(label: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", label).strip("._-") or "video"
    subdir = normalize_output_subdir(saved_output_subdir())
    project = CURRENT_PROJECT_TAG.get()
    if project:
        subdir = f"{subdir}/{project}"
    return f"{subdir}/{safe}_{time.strftime('%Y-%m-%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"


def clean_label(value: str | None) -> str:
    value = re.sub(r"\s+", " ", (value or "").strip())
    return value[:80]


def clean_id(value: str | None) -> str:
    return re.sub(r"[^A-Za-z0-9_.:-]+", "", (value or "").strip())[:80]


def workflow_profile_specs() -> dict[str, dict[str, Any]]:
    return {
        "wan22_ti2v_5b_720p": {
            "mode": "ti2v_5b",
            "label": "Wan2.2 TI2V-5B 720P",
        },
        "wan22_ti2v_5b_480p": {
            "mode": "ti2v_5b",
            "label": "Wan2.2 TI2V-5B 480P 小显存",
        },
        "wan22_i2v_a14b_720p": {
            "mode": "i2v_a14b",
            "label": "Wan2.2 I2V-A14B 720P",
        },
        "wan22_i2v_a14b_480p": {
            "mode": "i2v_a14b",
            "label": "Wan2.2 I2V-A14B 480P",
        },
        "wan22_t2v_a14b_720p": {
            "mode": "t2v_a14b",
            "label": "Wan2.2 T2V-A14B 720P",
        },
        "wan22_t2v_a14b_480p": {
            "mode": "t2v_a14b",
            "label": "Wan2.2 T2V-A14B 480P",
        },
        "wan22_ti2v_5b_final_720p": {
            "mode": "ti2v_5b",
            "label": "Wan2.2 TI2V-5B 720P 高质量",
        },
        "wan22_ti2v_5b_final_480p": {
            "mode": "ti2v_5b",
            "label": "Wan2.2 TI2V-5B 480P 小显存质量",
        },
        "ltx098_i2v_480p": {
            "mode": "ltx_i2v",
            "label": "LTXV 0.9.8 2B I2V 480P",
        },
        "ltx098_t2v_480p": {
            "mode": "ltx_t2v",
            "label": "LTXV 0.9.8 2B T2V 480P",
        },
        "ltx23_fp8_dev_t2v": {
            "mode": "ltx23_t2v",
            "label": "LTX-Video 2.3 22B Dev FP8 T2V",
            "checkpoint": LTX23_DEV_CHECKPOINT,
        },
        "ltx23_fp8_dev_i2v": {
            "mode": "ltx23_i2v",
            "label": "LTX-Video 2.3 22B Dev FP8 I2V",
            "checkpoint": LTX23_DEV_CHECKPOINT,
        },
        "ltx23_nvfp4_dev_t2v": {
            "mode": "ltx23_t2v",
            "label": "LTX-Video 2.3 22B Dev NVFP4 T2V",
            "checkpoint": LTX23_NVFP4_CHECKPOINT,
        },
        "ltx23_nvfp4_dev_i2v": {
            "mode": "ltx23_i2v",
            "label": "LTX-Video 2.3 22B Dev NVFP4 I2V",
            "checkpoint": LTX23_NVFP4_CHECKPOINT,
        },
        "ltx25_distilled_int8_t2v": {
            "mode": "ltx25_t2v",
            "label": "LTX-Video 2.5 22B Distilled INT8 T2V + 原生音频",
            "model_name": LTX25_DISTILLED_INT8_MODEL,
            "text_encoder": LTX25_TEXT_ENCODER,
            "video_vae_diff": LTX25_VIDEO_VAE_DIFF,
            "video_vae_conv": LTX25_VIDEO_VAE_CONV,
            "audio_vae": LTX25_AUDIO_VAE,
            "spatial_upscaler": LTX25_SPATIAL_UPSCALER,
            "duration_head": LTX25_DURATION_HEAD,
            "distilled": True,
        },
        "ltx25_distilled_int8_i2v": {
            "mode": "ltx25_i2v",
            "label": "LTX-Video 2.5 22B Distilled INT8 首帧/首尾帧 + 原生音频",
            "model_name": LTX25_DISTILLED_INT8_MODEL,
            "text_encoder": LTX25_TEXT_ENCODER,
            "video_vae_diff": LTX25_VIDEO_VAE_DIFF,
            "video_vae_conv": LTX25_VIDEO_VAE_CONV,
            "audio_vae": LTX25_AUDIO_VAE,
            "spatial_upscaler": LTX25_SPATIAL_UPSCALER,
            "duration_head": LTX25_DURATION_HEAD,
            "distilled": True,
        },
        "ltx25_distilled_nvfp4_t2v": {
            "mode": "ltx25_t2v",
            "label": "LTX-Video 2.5 22B Distilled NVFP4 T2V + 原生音频",
            "model_name": LTX25_DISTILLED_NVFP4_MODEL,
            "text_encoder": LTX25_TEXT_ENCODER,
            "video_vae_diff": LTX25_VIDEO_VAE_DIFF,
            "video_vae_conv": LTX25_VIDEO_VAE_CONV,
            "audio_vae": LTX25_AUDIO_VAE,
            "spatial_upscaler": LTX25_SPATIAL_UPSCALER,
            "duration_head": LTX25_DURATION_HEAD,
            "distilled": True,
        },
        "ltx25_distilled_nvfp4_i2v": {
            "mode": "ltx25_i2v",
            "label": "LTX-Video 2.5 22B Distilled NVFP4 首帧/首尾帧 + 原生音频",
            "model_name": LTX25_DISTILLED_NVFP4_MODEL,
            "text_encoder": LTX25_TEXT_ENCODER,
            "video_vae_diff": LTX25_VIDEO_VAE_DIFF,
            "video_vae_conv": LTX25_VIDEO_VAE_CONV,
            "audio_vae": LTX25_AUDIO_VAE,
            "spatial_upscaler": LTX25_SPATIAL_UPSCALER,
            "duration_head": LTX25_DURATION_HEAD,
            "distilled": True,
        },
        "hunyuan15_t2v_480_fp8": {
            "mode": "hunyuan15_t2v",
            "label": "HunyuanVideo 1.5 T2V 480P Distilled FP8",
            "model_name": HUNYUAN15_T2V_480_MODEL,
            "distilled": True,
        },
        "hunyuan15_i2v_480_fp8": {
            "mode": "hunyuan15_i2v",
            "label": "HunyuanVideo 1.5 I2V 480P Distilled FP8",
            "model_name": HUNYUAN15_I2V_480_MODEL,
            "distilled": True,
        },
        "hunyuan15_t2v_720_fp16": {
            "mode": "hunyuan15_t2v",
            "label": "HunyuanVideo 1.5 T2V 720P FP16",
            "model_name": HUNYUAN15_T2V_720_MODEL,
            "distilled": False,
        },
        "hunyuan15_i2v_720_fp16": {
            "mode": "hunyuan15_i2v",
            "label": "HunyuanVideo 1.5 I2V 720P FP16",
            "model_name": HUNYUAN15_I2V_720_MODEL,
            "distilled": False,
        },
        "minimax_h3_fl2va_int8_t2v": {
            "mode": "minimax_h3_t2v",
            "label": "MiniMax H3 FL2VA INT8 T2V + 原生音频",
        },
        "minimax_h3_fl2va_int8_i2v": {
            "mode": "minimax_h3_i2v",
            "label": "MiniMax H3 FL2VA INT8 首帧/首尾帧 + 原生音频",
        },
        "minimax_h3_ref2va_int8_r2v": {
            "mode": "minimax_h3_r2v",
            "label": "MiniMax H3 Ref2VA INT8 多参考素材 + 原生音频",
        },
        "fal_h3_max_t2v": {
            "mode": "fal_h3_max_t2v",
            "label": "H3 Max（fal 后训练版）文字生音视频",
        },
        "fal_h3_max_i2v": {
            "mode": "fal_h3_max_i2v",
            "label": "H3 Max（fal 后训练版）首帧/首尾帧生音视频",
        },
        "mac_ltx_low_i2v": {
            "mode": "ltx_i2v",
            "label": "Mac LTX I2V 低档 384P",
        },
        "mac_ltx_balanced_i2v": {
            "mode": "ltx_i2v",
            "label": "Mac LTX I2V 均衡 512P",
        },
        "mac_ltx_quality_i2v": {
            "mode": "ltx_i2v",
            "label": "Mac LTX I2V 质量档",
        },
        "mac_ltx_low_t2v": {
            "mode": "ltx_t2v",
            "label": "Mac LTX T2V 低档",
        },
        "mac_ltx_balanced_t2v": {
            "mode": "ltx_t2v",
            "label": "Mac LTX T2V 均衡档",
        },
        "mac_wan5b_480p": {
            "mode": "ti2v_5b",
            "label": "Mac Wan2.2 TI2V-5B 480P 实验档",
        },
        "mac_wan5b_720p_experimental": {
            "mode": "ti2v_5b",
            "label": "Mac Wan2.2 TI2V-5B 720P 高内存实验档",
        },
        "no_local_video_draft": {
            "mode": "unsupported",
            "label": "当前硬件不建议本地生视频",
        },
        "no_local_video_final": {
            "mode": "unsupported",
            "label": "当前硬件不建议本地生视频",
        },
        "ffmpeg_deflicker_balanced": {
            "mode": "deflicker",
            "label": "ffmpeg deflicker + hqdn3d",
            "local": True,
        },
        "rife49_2x": {
            "mode": "rife_2x",
            "label": "RIFE 4.9 2x",
            "rife_multiplier": 2,
        },
        "rife49_4x": {
            "mode": "rife_2x",
            "label": "RIFE 4.9 4x",
            "rife_multiplier": 4,
        },
        "seedvr2_7b_1080p": {
            "mode": "upscale_seedvr2",
            "label": "SeedVR2 7B NVFP4 1.5x（720P→1080P）",
            "upscale_model": SEEDVR2_7B_MODEL,
            "scale": 1.5,
        },
        "seedvr2_7b_sharp_1080p": {
            "mode": "upscale_seedvr2",
            "label": "SeedVR2 7B Sharp NVFP4 1.5x（实验）",
            "upscale_model": SEEDVR2_7B_SHARP_MODEL,
            "scale": 1.5,
        },
        "seedvr2_3b_2x": {
            "mode": "upscale_seedvr2",
            "label": "SeedVR2 3B INT8 时序视频超分 2x",
            "upscale_model": SEEDVR2_3B_MODEL,
            "scale": 2,
        },
        "realesrgan_x2plus": {
            "mode": "upscale_2x",
            "label": "RealESRGAN x2plus 2x",
            "upscale_model": "RealESRGAN_x2plus.pth",
            "scale": 2,
        },
        "ultrasharp_4x": {
            "mode": "upscale_2x",
            "label": "4x-UltraSharp 4x",
            "upscale_model": "4x-UltraSharp.pth",
            "scale": 4,
        },
    }


def resolve_workflow_profile(
    *,
    model_profile: str | None,
    mode: str,
    model_label: str | None,
    upscale_model: str,
    rife_multiplier: int,
) -> dict[str, Any]:
    profile_id = clean_id(model_profile)
    spec = workflow_profile_specs().get(profile_id, {})
    resolved_mode = spec.get("mode", mode)
    resolved_label = clean_label(model_label) or spec.get("label", "")
    resolved_upscale = spec.get("upscale_model", upscale_model)
    resolved_rife = int(spec.get("rife_multiplier", rife_multiplier))
    return {
        "profile": profile_id,
        "mode": resolved_mode,
        "label": resolved_label,
        "upscale_model": resolved_upscale,
        "rife_multiplier": resolved_rife,
        "scale": spec.get("scale"),
        "local": bool(spec.get("local")),
        "checkpoint": str(spec.get("checkpoint") or ""),
        "model_name": str(spec.get("model_name") or ""),
        "text_encoder": str(spec.get("text_encoder") or ""),
        "video_vae_diff": str(spec.get("video_vae_diff") or ""),
        "video_vae_conv": str(spec.get("video_vae_conv") or ""),
        "audio_vae": str(spec.get("audio_vae") or ""),
        "spatial_upscaler": str(spec.get("spatial_upscaler") or ""),
        "duration_head": str(spec.get("duration_head") or ""),
        "distilled": bool(spec.get("distilled")),
    }


def fal_api_key() -> str:
    return str(os.environ.get("FAL_KEY") or "").strip()


def fal_h3_max_config_payload() -> dict[str, Any]:
    return {
        "available": bool(fal_api_key()),
        "key_env": "FAL_KEY",
        "weights_available": False,
        "local_weights_note": "fal 尚未发布 H3 Max 官方本地权重；当前配置只使用 fal 云端 API。",
        "endpoints": {
            "text_to_video": FAL_H3_MAX_T2V_ENDPOINT,
            "image_to_video": FAL_H3_MAX_I2V_ENDPOINT,
        },
        "uses_comfyui": False,
        "uses_local_gpu": False,
    }


def fal_auth_headers() -> dict[str, str]:
    key = fal_api_key()
    if not key:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "H3 Max 尚未配置 FAL_KEY",
                "errors": [
                    "fal 当前没有发布 H3 Max 本地权重，因此这一路线只能调用官方云端 API。",
                    "请在系统环境变量中设置 FAL_KEY 后只重启前端；不需要启动或重启 ComfyUI。",
                ],
            },
        )
    return {"Authorization": f"Key {key}", "Accept": "application/json"}


def checked_fal_queue_url(value: str) -> str:
    parsed = urlparse(str(value or "").strip())
    if parsed.scheme != "https" or parsed.hostname != "queue.fal.run":
        raise HTTPException(status_code=502, detail="fal 返回了不受信任的队列地址")
    return parsed.geturl()


def checked_fal_media_url(value: str) -> str:
    parsed = urlparse(str(value or "").strip())
    hostname = str(parsed.hostname or "").lower()
    if parsed.scheme != "https" or not (hostname == "fal.media" or hostname.endswith(".fal.media")):
        raise HTTPException(status_code=502, detail="fal 返回了不受信任的媒体地址")
    return parsed.geturl()


def fal_error_message(response: httpx.Response) -> str:
    if response.status_code in {401, 403}:
        return "fal 拒绝了请求，请检查 FAL_KEY、账户状态和模型访问权限。"
    if response.status_code == 429:
        return "fal 当前请求过多或额度受限，请稍后再试。"
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    detail = payload.get("detail") if isinstance(payload, dict) else None
    if isinstance(detail, list):
        detail = "; ".join(str(item) for item in detail[:4])
    return str(detail or f"fal API 返回 HTTP {response.status_code}")[:600]


async def fal_request_json(method: str, url: str, *, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    checked_url = checked_fal_queue_url(url)
    timeout = httpx.Timeout(connect=20.0, read=60.0, write=60.0, pool=20.0)
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            response = await client.request(method, checked_url, headers=fal_auth_headers(), json=payload)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail=f"无法连接 fal：{exc}") from exc
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=fal_error_message(response))
    if response.status_code == 204 or not response.content:
        return {}
    try:
        data = response.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="fal 返回了无法解析的响应") from exc
    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="fal 返回格式不正确")
    return data


async def fal_queue_submit(endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
    if endpoint not in {FAL_H3_MAX_T2V_ENDPOINT, FAL_H3_MAX_I2V_ENDPOINT}:
        raise HTTPException(status_code=400, detail="未知 fal H3 Max 端点")
    response = await fal_request_json("POST", f"{FAL_QUEUE_ORIGIN}/{endpoint}", payload=payload)
    request_id = str(response.get("request_id") or "").strip()
    if not request_id:
        raise HTTPException(status_code=502, detail="fal 未返回 request_id")
    base = f"{FAL_QUEUE_ORIGIN}/{endpoint}/requests/{quote(request_id, safe='')}"
    response["request_id"] = request_id
    response["status_url"] = checked_fal_queue_url(str(response.get("status_url") or f"{base}/status"))
    response["response_url"] = checked_fal_queue_url(str(response.get("response_url") or base))
    response["cancel_url"] = checked_fal_queue_url(str(response.get("cancel_url") or f"{base}/cancel"))
    return response


def closest_fal_aspect_ratio(width: int, height: int) -> str:
    candidates = {
        "21:9": 21 / 9,
        "16:9": 16 / 9,
        "4:3": 4 / 3,
        "1:1": 1.0,
        "3:4": 3 / 4,
        "9:16": 9 / 16,
    }
    ratio = max(1, width) / max(1, height)
    return min(candidates, key=lambda name: abs(math.log(ratio / candidates[name])))


def fal_h3_max_resolution(width: int, height: int) -> str:
    return "480P" if max(width, height) <= 900 else "768P"


def fal_h3_max_duration(length: int, fps: int = 24) -> int:
    return clamp_int(round(max(1, length) / max(1, fps)), 5, 15)


def image_bytes_data_uri(data: bytes, *, filename: str, content_type: str = "") -> str:
    suffix = Path(filename or "image.png").suffix.lower()
    if suffix not in IMAGE_EXTENSIONS:
        raise HTTPException(status_code=400, detail="H3 Max 关键帧只支持 PNG、JPG、WEBP 或 BMP")
    if not data:
        raise HTTPException(status_code=400, detail="H3 Max 关键帧文件为空")
    if len(data) > FAL_H3_MAX_MAX_IMAGE_BYTES:
        raise HTTPException(status_code=400, detail="H3 Max 关键帧不能超过 20MB")
    mime = content_type if str(content_type).startswith("image/") else mimetypes.guess_type(filename)[0]
    mime = mime or "image/png"
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{encoded}"


async def fal_upload_data_uri(upload: UploadFile) -> str:
    data = await upload.read(FAL_H3_MAX_MAX_IMAGE_BYTES + 1)
    return image_bytes_data_uri(data, filename=upload.filename or "image.png", content_type=upload.content_type or "")


def fal_path_data_uri(path: Path) -> str:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"无法读取 H3 Max 关键帧：{exc}") from exc
    return image_bytes_data_uri(data, filename=path.name, content_type=mimetypes.guess_type(path.name)[0] or "")


def fal_output_destination(relative_path: str) -> tuple[Path, dict[str, Any]]:
    output_root = Path(configured_comfy_paths()["output_dir"]).expanduser().resolve()
    candidate = (output_root / Path(relative_path.replace("/", os.sep))).resolve()
    try:
        relative = candidate.relative_to(output_root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="fal 输出路径不安全") from exc
    candidate.parent.mkdir(parents=True, exist_ok=True)
    subfolder = "" if relative.parent == Path(".") else relative.parent.as_posix()
    media = {
        "kind": "video",
        "filename": relative.name,
        "subfolder": subfolder,
        "type": "output",
    }
    media["url"] = media_url(media)
    return candidate, media


async def download_fal_video(url: str, destination: Path) -> None:
    source_url = checked_fal_media_url(url)
    temporary = destination.with_suffix(f"{destination.suffix}.part")
    timeout = httpx.Timeout(connect=20.0, read=300.0, write=60.0, pool=20.0)
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            async with client.stream("GET", source_url) as response:
                if response.status_code >= 400:
                    raise HTTPException(status_code=502, detail=f"下载 fal 成片失败：HTTP {response.status_code}")
                with temporary.open("wb") as handle:
                    async for chunk in response.aiter_bytes(1024 * 1024):
                        handle.write(chunk)
        if not temporary.is_file() or temporary.stat().st_size == 0:
            raise HTTPException(status_code=502, detail="fal 成片下载结果为空")
        os.replace(temporary, destination)
    finally:
        if temporary.exists() and not destination.exists():
            temporary.unlink(missing_ok=True)


async def comfy_get(path: str) -> Any:
    discovered, errors = await discover_comfy_url()
    if discovered:
        try:
            result = await request_comfy_json("GET", discovered, path)
            set_current_comfy_url(discovered)
            return result
        except HTTPException as exc:
            error = f"{discovered}: {comfy_connection_error_text(exc)}"
            with COMFY_STATE_LOCK:
                COMFY_DISCOVERY_CACHE.update({"url": None, "checked_at": 0.0, "errors": [error]})
            errors = [error]
        except (httpx.HTTPError, ValueError) as exc:
            error = f"{discovered}: {comfy_connection_error_text(exc)}"
            with COMFY_STATE_LOCK:
                COMFY_DISCOVERY_CACHE.update({"url": None, "checked_at": 0.0, "errors": [error]})
            errors = [error]
    raise HTTPException(
        status_code=503,
        detail=f"ComfyUI 连接失败。已尝试：{'; '.join(errors) or ', '.join(common_comfy_urls())}",
    )


async def comfy_post(path: str, payload: dict[str, Any]) -> Any:
    discovered, errors = await discover_comfy_url()
    if not discovered:
        raise HTTPException(
            status_code=503,
            detail=f"ComfyUI 连接失败。已尝试：{'; '.join(errors) or ', '.join(common_comfy_urls())}",
        )
    try:
        return await request_comfy_json("POST", discovered, path, payload)
    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(
            status_code=503,
            detail=f"ComfyUI 连接失败：{comfy_connection_error_text(exc)}",
        ) from exc


def comfy_websocket_url(base_url: str | None = None) -> str:
    parsed = urlparse((base_url or current_comfy_url()).rstrip("/"))
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return f"{scheme}://{parsed.netloc}{parsed.path.rstrip('/')}/ws?clientId={quote(CLIENT_ID)}"


async def comfy_progress_listener(base_url: str, ready: asyncio.Event) -> None:
    if websockets is None:
        return
    websocket_url = comfy_websocket_url(base_url)
    while True:
        try:
            async with websockets.connect(
                websocket_url,
                proxy=None,
                open_timeout=3,
                close_timeout=2,
                ping_interval=20,
                ping_timeout=20,
                max_size=4 * 1024 * 1024,
            ) as socket:
                ready.set()
                async for raw_message in socket:
                    if not isinstance(raw_message, str):
                        continue
                    try:
                        message = json.loads(raw_message)
                    except ValueError:
                        continue
                    apply_comfy_progress_event(message)
        except asyncio.CancelledError:
            raise
        except Exception:
            ready.clear()
            await asyncio.sleep(1.0)


async def ensure_comfy_progress_listener(*, timeout: float = 2.5) -> bool:
    if websockets is None:
        return False
    loop = asyncio.get_running_loop()
    base_url = current_comfy_url()
    with COMFY_PROGRESS_LISTENER_LOCK:
        task = COMFY_PROGRESS_TASKS.get(loop)
        if task and not task.done() and COMFY_PROGRESS_TASK_URLS.get(loop) != base_url:
            task.cancel()
            task = None
        if task is None or task.done():
            ready = asyncio.Event()
            task = loop.create_task(
                comfy_progress_listener(base_url, ready),
                name="comfy-progress-listener",
            )
            COMFY_PROGRESS_TASKS[loop] = task
            COMFY_PROGRESS_READY_EVENTS[loop] = ready
            COMFY_PROGRESS_TASK_URLS[loop] = base_url
        ready = COMFY_PROGRESS_READY_EVENTS[loop]
    try:
        await asyncio.wait_for(ready.wait(), timeout=timeout)
        return True
    except TimeoutError:
        return False


async def get_comfy_object_info(*, force: bool = False) -> dict[str, Any]:
    def cached_value() -> dict[str, Any] | None:
        url = current_comfy_url()
        with COMFY_STATE_LOCK:
            value = OBJECT_INFO_CACHE.get("value")
            cached_url = OBJECT_INFO_CACHE.get("url")
            checked_at = float(OBJECT_INFO_CACHE.get("checked_at") or 0)
        if not force and isinstance(value, dict) and cached_url == url and time.time() - checked_at < OBJECT_INFO_CACHE_TTL:
            return value
        return None

    cached = cached_value()
    if cached is not None:
        return cached
    async with object_info_async_lock():
        cached = cached_value()
        if cached is not None:
            return cached
        value = await comfy_get("/object_info")
        if not isinstance(value, dict):
            raise HTTPException(status_code=502, detail="ComfyUI /object_info 返回格式无效")
        with COMFY_STATE_LOCK:
            OBJECT_INFO_CACHE.update(
                {"url": current_comfy_url(), "value": value, "checked_at": time.time()}
            )
        return value


def comfy_not_connected_detail(action: str, original_detail: Any) -> dict[str, Any]:
    return {
        "message": f"ComfyUI 未连接，无法{action}",
        "errors": [str(original_detail)],
        "actions": [
            "在第 1 步“环境侦测”点击“一键准备环境”。",
            "如果 ComfyUI 已安装但未运行，点击“启动 ComfyUI”，等待状态变成“已连接”。",
            "状态已连接后，先运行“生成链路测试”，通过后再生成正式镜头。",
        ],
    }


async def save_upload(upload: UploadFile, allowed: set[str], paths: dict[str, Any] | None = None) -> str:
    suffix = Path(upload.filename or "").suffix.lower()
    if suffix not in allowed:
        allowed_text = ", ".join(sorted(allowed))
        raise HTTPException(status_code=400, detail=f"文件格式不支持，请使用：{allowed_text}")

    upload_dir = upload_dir_for(paths)
    upload_dir.mkdir(parents=True, exist_ok=True)
    filename = unique_upload_filename(upload.filename or f"upload{suffix}")
    destination = upload_dir / filename
    with destination.open("wb") as output:
        shutil.copyfileobj(upload.file, output)
    return f"beginner_frontend/{filename}"


def unique_upload_filename(name: str) -> str:
    safe = safe_filename(name)
    path = Path(safe)
    suffix = path.suffix
    stem = path.stem or "upload"
    return f"{stem}_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}{suffix}"


def copy_media_to_input(filename: str, subfolder: str, file_type: str, paths: dict[str, Any] | None = None) -> str:
    source = safe_media_path(filename, subfolder, file_type, paths)
    if source.suffix.lower() not in VIDEO_EXTENSIONS:
        raise HTTPException(status_code=400, detail="上一阶段输出不是可处理的视频")

    upload_dir = upload_dir_for(paths)
    upload_dir.mkdir(parents=True, exist_ok=True)
    destination_name = unique_upload_filename(source.name)
    destination = upload_dir / destination_name
    shutil.copy2(source, destination)
    return f"beginner_frontend/{destination_name}"


def copy_image_to_input(filename: str, subfolder: str, file_type: str, paths: dict[str, Any] | None = None) -> str:
    source = safe_media_path(filename, subfolder, file_type, paths)
    if source.suffix.lower() not in IMAGE_EXTENSIONS:
        raise HTTPException(status_code=400, detail="所选文件不是可用的图片")

    upload_dir = upload_dir_for(paths)
    upload_dir.mkdir(parents=True, exist_ok=True)
    destination_name = unique_upload_filename(source.name)
    destination = upload_dir / destination_name
    shutil.copy2(source, destination)
    return f"beginner_frontend/{destination_name}"


def face_extraction_capability_payload() -> dict[str, Any]:
    available = bool(cv2 is not None and np is not None and Image is not None and ImageOps is not None)
    cascade_path = ""
    if available:
        cascade_path = str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml")
        available = Path(cascade_path).is_file()
    return {
        "available": available,
        "method": "opencv_local_face_detection",
        "local_only": True,
        "identity_recognition": False,
        "authorization_required": True,
        "authorization_statement": FACE_AUTHORIZATION_STATEMENT,
        "crop_modes": [
            {"id": "face", "label": "面部特写", "description": "保留脸部、发型边缘和少量背景。"},
            {"id": "head_shoulders", "label": "头肩参考", "description": "扩大到头发、颈部和肩部，更适合人物一致性。"},
        ],
        "error": "" if available else "当前前端 Python 缺少 OpenCV、NumPy、Pillow 或人脸检测数据。",
    }


def normalize_face_crop_mode(value: str) -> str:
    return "head_shoulders" if value == "head_shoulders" else "face"


def face_box_iou(first: tuple[int, int, int, int], second: tuple[int, int, int, int]) -> float:
    ax, ay, aw, ah = first
    bx, by, bw, bh = second
    left = max(ax, bx)
    top = max(ay, by)
    right = min(ax + aw, bx + bw)
    bottom = min(ay + ah, by + bh)
    intersection = max(0, right - left) * max(0, bottom - top)
    union = aw * ah + bw * bh - intersection
    return intersection / union if union > 0 else 0.0


def detect_face_boxes(image: Any) -> list[dict[str, Any]]:
    capability = face_extraction_capability_payload()
    if not capability["available"]:
        raise HTTPException(status_code=503, detail=capability["error"])

    original_width, original_height = image.size
    longest = max(original_width, original_height)
    detection_scale = min(1.0, 2048.0 / longest) if longest else 1.0
    detection_image = image
    if detection_scale < 1.0:
        resampling = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
        detection_image = image.resize(
            (max(1, round(original_width * detection_scale)), max(1, round(original_height * detection_scale))),
            resampling,
        )
    rgb = np.asarray(detection_image.convert("RGB"))
    gray = cv2.equalizeHist(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY))
    minimum = max(36, round(min(gray.shape[:2]) * 0.035))

    cascade_names = ("haarcascade_frontalface_default.xml", "haarcascade_frontalface_alt2.xml")
    detections: list[tuple[tuple[int, int, int, int], float]] = []
    for cascade_index, cascade_name in enumerate(cascade_names):
        cascade = cv2.CascadeClassifier(str(Path(cv2.data.haarcascades) / cascade_name))
        if cascade.empty():
            continue
        try:
            boxes, _levels, weights = cascade.detectMultiScale3(
                gray,
                scaleFactor=1.08,
                minNeighbors=6 if cascade_index == 0 else 7,
                minSize=(minimum, minimum),
                outputRejectLevels=True,
            )
            weighted = zip(boxes, weights)
        except AttributeError:
            boxes = cascade.detectMultiScale(
                gray,
                scaleFactor=1.08,
                minNeighbors=6 if cascade_index == 0 else 7,
                minSize=(minimum, minimum),
            )
            weighted = ((box, 1.0) for box in boxes)
        for raw_box, raw_weight in weighted:
            x, y, width, height = [int(value) for value in raw_box]
            if detection_scale < 1.0:
                x, y, width, height = [round(value / detection_scale) for value in (x, y, width, height)]
            box = (
                max(0, min(original_width - 1, x)),
                max(0, min(original_height - 1, y)),
                max(1, min(original_width - x, width)),
                max(1, min(original_height - y, height)),
            )
            weight = float(raw_weight[0] if hasattr(raw_weight, "__len__") else raw_weight)
            detections.append((box, weight))

    detections.sort(key=lambda item: (item[0][2] * item[0][3], item[1]), reverse=True)
    unique: list[tuple[tuple[int, int, int, int], float]] = []
    for box, weight in detections:
        if any(face_box_iou(box, existing_box) >= 0.35 for existing_box, _ in unique):
            continue
        unique.append((box, weight))
        if len(unique) >= 8:
            break
    return [
        {
            "box": {"x": box[0], "y": box[1], "width": box[2], "height": box[3]},
            "confidence": round(weight, 3),
        }
        for box, weight in unique
    ]


def face_crop_bounds(
    box: dict[str, int], image_size: tuple[int, int], crop_mode: str
) -> tuple[int, int, int, int]:
    image_width, image_height = image_size
    x, y = int(box["x"]), int(box["y"])
    width, height = int(box["width"]), int(box["height"])
    center_x = x + width / 2
    if normalize_face_crop_mode(crop_mode) == "head_shoulders":
        crop_height = max(height * 4.0, width * 4.0)
        crop_width = crop_height * 0.8
        center_y = y + height * 1.35
    else:
        crop_width = crop_height = max(width, height) * 2.15
        center_y = y + height * 0.58
    crop_width = min(float(image_width), crop_width)
    crop_height = min(float(image_height), crop_height)
    left = center_x - crop_width / 2
    top = center_y - crop_height / 2
    left = max(0.0, min(float(image_width) - crop_width, left))
    top = max(0.0, min(float(image_height) - crop_height, top))
    return (
        round(left),
        round(top),
        round(left + crop_width),
        round(top + crop_height),
    )


def extract_faces_to_input(
    source_path: Path,
    comfy_paths: dict[str, Any],
    *,
    extraction_id: str,
    crop_mode: str,
) -> list[dict[str, Any]]:
    try:
        with Image.open(source_path) as opened:
            image = ImageOps.exif_transpose(opened).convert("RGB")
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"源图片无法读取：{exc}") from exc
    faces = detect_face_boxes(image)
    if not faces:
        raise HTTPException(
            status_code=422,
            detail="没有检测到清晰面部。请换一张光线充足、脸部较大且无遮挡的正面照片，或改用整张图片。",
        )

    crop_mode = normalize_face_crop_mode(crop_mode)
    input_dir = Path(comfy_paths["input_dir"])
    relative_dir = Path("beginner_frontend") / "face_extract"
    destination_dir = input_dir / relative_dir
    destination_dir.mkdir(parents=True, exist_ok=True)
    safe_stem = Path(safe_filename(source_path.stem)).stem or "face"
    candidates: list[dict[str, Any]] = []
    for index, face in enumerate(faces):
        bounds = face_crop_bounds(face["box"], image.size, crop_mode)
        crop = image.crop(bounds)
        filename = f"{safe_stem}_{extraction_id[:10]}_{crop_mode}_{index + 1}.png"
        destination = destination_dir / filename
        crop.save(destination, format="PNG", optimize=True)
        item = {
            "index": index,
            "label": f"面部 {index + 1}",
            "filename": filename,
            "subfolder": relative_dir.as_posix(),
            "type": "input",
            "width": crop.width,
            "height": crop.height,
            "face_box": face["box"],
            "crop_box": {
                "left": bounds[0],
                "top": bounds[1],
                "right": bounds[2],
                "bottom": bounds[3],
            },
            "confidence": face["confidence"],
        }
        item["url"] = media_url(item)
        candidates.append(item)
    return candidates


def register_face_extraction(record: dict[str, Any]) -> None:
    cutoff = now_ms() - 6 * 60 * 60 * 1000
    with FACE_EXTRACTION_LOCK:
        for item_id in [
            item_id
            for item_id, item in FACE_EXTRACTIONS.items()
            if int(item.get("created_at") or 0) < cutoff
        ]:
            FACE_EXTRACTIONS.pop(item_id, None)
        FACE_EXTRACTIONS[str(record["id"])] = record
        if len(FACE_EXTRACTIONS) > 100:
            oldest = sorted(FACE_EXTRACTIONS.values(), key=lambda item: int(item.get("created_at") or 0))
            for item in oldest[: len(FACE_EXTRACTIONS) - 100]:
                FACE_EXTRACTIONS.pop(str(item.get("id") or ""), None)


def validated_face_extraction_candidate(
    extraction_id: str,
    face_index: int,
    filename: str,
    subfolder: str,
    file_type: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    candidate, record = validated_face_extraction(extraction_id, face_index)
    expected = (
        str(candidate.get("filename") or ""),
        str(candidate.get("subfolder") or ""),
        str(candidate.get("type") or "input"),
    )
    actual = (filename, subfolder, file_type or "input")
    if expected != actual:
        raise HTTPException(status_code=400, detail="面部提取结果与提交图片不一致，请重新选择面部。")
    return candidate, record


def validated_face_extraction(extraction_id: str, face_index: int) -> tuple[dict[str, Any], dict[str, Any]]:
    with FACE_EXTRACTION_LOCK:
        record = FACE_EXTRACTIONS.get(extraction_id)
        if record is None:
            raise HTTPException(status_code=400, detail="面部提取记录已失效，请重新确认授权并提取面部。")
        candidates = list(record.get("faces") or [])
        candidate = next((item for item in candidates if int(item.get("index", -1)) == face_index), None)
        if candidate is None:
            raise HTTPException(status_code=400, detail="所选面部不存在，请重新检测。")
        if not record.get("authorization_confirmed"):
            raise HTTPException(status_code=403, detail="面部提取记录缺少授权确认，请重新确认并检测。")
        return dict(candidate), dict(record)


def node(class_type: str, inputs: dict[str, Any]) -> dict[str, Any]:
    return {"class_type": class_type, "inputs": inputs}


def advanced_or_defaults(mode: str, adv: AdvancedParams | None) -> AdvancedParams:
    """builder 既被 /api/generate 调用，也被预览和自检调用；后两者不一定带高级参数。"""
    return adv if adv is not None else video_params.resolve(mode, None)


def vae_tiled_decode(adv: AdvancedParams, *, samples: list[Any], vae: list[Any]) -> dict[str, Any]:
    return node(
        "VAEDecodeTiled",
        {
            "samples": samples,
            "vae": vae,
            "tile_size": adv["vae_tile_size"],
            "overlap": adv["vae_tile_overlap"],
            "temporal_size": adv["vae_temporal_size"],
            "temporal_overlap": adv["vae_temporal_overlap"],
        },
    )


def stack_model_loras(
    graph: dict[str, Any],
    *,
    base: list[Any],
    entries: list[tuple[str, str, float]],
) -> list[Any]:
    """按顺序把 LoRA 串在模型链上，返回链尾。

    ``entries`` 里每项是 ``(node_id, lora_name, strength)``；强度为 0 或名字为空时
    整个节点会被跳过（而不是以 0 强度加载），这样"关掉加速 LoRA 跑全步数"才是真的关掉。
    """
    current = list(base)
    for node_id, lora_name, strength in entries:
        name = str(lora_name or "").strip()
        if not name or strength <= 0:
            continue
        graph[node_id] = node(
            "LoraLoaderModelOnly",
            {"model": current, "lora_name": name, "strength_model": float(strength)},
        )
        current = [node_id, 0]
    return current


def build_ti2v_prompt(
    *,
    prompt: str,
    negative: str,
    image_name: str = "",
    width: int,
    height: int,
    length: int,
    fps: int,
    seed: int,
    steps: int,
    cfg: float,
    adv: AdvancedParams | None = None,
) -> dict[str, Any]:
    adv = advanced_or_defaults("ti2v_5b", adv)
    latent_inputs: dict[str, Any] = {
        "vae": ["3", 0],
        "width": width,
        "height": height,
        "length": length,
        "batch_size": adv["batch_size"],
    }
    graph = {
        "2": node(
            "CLIPLoader",
            {
                "clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors",
                "type": "wan",
                "device": "default",
            },
        ),
        "3": node("VAELoader", {"vae_name": "wan2.2_vae.safetensors"}),
        "4": node(
            "UNETLoader",
            {
                "unet_name": "Wan2.2/wan2.2_ti2v_5B_fp16.safetensors",
                "weight_dtype": "default",
            },
        ),
        "5": node("ModelSamplingSD3", {"model": ["4", 0], "shift": adv["shift"] or 5.0}),
        "6": node("CLIPTextEncode", {"text": prompt, "clip": ["2", 0]}),
        "7": node("CLIPTextEncode", {"text": negative, "clip": ["2", 0]}),
        "8": node(
            "Wan22ImageToVideoLatent",
            latent_inputs,
        ),
        "9": node(
            "KSampler",
            {
                "model": ["5", 0],
                "seed": seed,
                "steps": steps,
                "cfg": cfg,
                "sampler_name": adv["sampler_name"],
                "scheduler": adv["scheduler"],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["8", 0],
                "denoise": adv["denoise"],
            },
        ),
        "10": vae_tiled_decode(adv, samples=["9", 0], vae=["3", 0]),
        "11": node("CreateVideo", {"images": ["10", 0], "fps": fps}),
        "12": node(
            "SaveVideo",
            {
                "video": ["11", 0],
                "filename_prefix": output_prefix("TI2V_draft"),
                "format": "mp4",
                "codec": "h264",
            },
        ),
    }
    if image_name:
        graph["1"] = node("LoadImage", {"image": image_name})
        latent_inputs["start_image"] = ["1", 0]
    return graph


def build_ltx_t2v_prompt(
    *,
    prompt: str,
    negative: str,
    width: int,
    height: int,
    length: int,
    fps: int,
    seed: int,
    steps: int,
    cfg: float,
    adv: AdvancedParams | None = None,
) -> dict[str, Any]:
    adv = advanced_or_defaults("ltx_t2v", adv)
    return {
        "1": node("CheckpointLoaderSimple", {"ckpt_name": "ltxv-2b-0.9.8-distilled-fp8.safetensors"}),
        "2": node(
            "CLIPLoader",
            {
                "clip_name": "t5xxl_fp16.safetensors",
                "type": "ltxv",
                "device": "default",
            },
        ),
        "3": node("CLIPTextEncode", {"text": prompt, "clip": ["2", 0]}),
        "4": node("CLIPTextEncode", {"text": negative, "clip": ["2", 0]}),
        "5": node("LTXVConditioning", {"frame_rate": float(fps), "positive": ["3", 0], "negative": ["4", 0]}),
        "6": node(
            "EmptyLTXVLatentVideo",
            {
                "width": width,
                "height": height,
                "length": normalize_ltx_frames(length),
                "batch_size": adv["batch_size"],
            },
        ),
        "7": node(
            "LTXVScheduler",
            {
                "steps": steps,
                "max_shift": adv["ltx_max_shift"],
                "base_shift": adv["ltx_base_shift"],
                "stretch": adv.enabled("ltx_stretch"),
                "terminal": adv["ltx_terminal"],
                "latent": ["6", 0],
            },
        ),
        "8": node("KSamplerSelect", {"sampler_name": adv["sampler_name"]}),
        "9": node(
            "SamplerCustom",
            {
                "model": ["1", 0],
                "add_noise": True,
                "noise_seed": seed,
                "cfg": cfg,
                "positive": ["5", 0],
                "negative": ["5", 1],
                "sampler": ["8", 0],
                "sigmas": ["7", 0],
                "latent_image": ["6", 0],
            },
        ),
        "10": node("VAEDecode", {"samples": ["9", 0], "vae": ["1", 2]}),
        "11": node("CreateVideo", {"images": ["10", 0], "fps": float(fps)}),
        "12": node(
            "SaveVideo",
            {
                "video": ["11", 0],
                "filename_prefix": output_prefix("Mac_LTX_T2V"),
                "format": "mp4",
                "codec": "h264",
            },
        ),
    }


def resample_sigma_schedule(values: list[float], step_count: int) -> str:
    step_count = max(1, int(step_count))
    if step_count == len(values) - 1:
        sampled = values
    else:
        sampled: list[float] = []
        last_index = len(values) - 1
        for index in range(step_count + 1):
            position = index * last_index / step_count
            left = int(position)
            right = min(last_index, left + 1)
            fraction = position - left
            sampled.append(values[left] + (values[right] - values[left]) * fraction)
    return ", ".join(f"{value:.6f}".rstrip("0").rstrip(".") for value in sampled)


LTX23_FIRST_SIGMAS = [1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0]
LTX23_SECOND_SIGMAS = [0.85, 0.725, 0.4219, 0.0]


def ltx23_sigma_schedules(
    steps: int,
    first_stage_ratio: float = 8 / 11,
    *,
    two_stage: bool = True,
) -> tuple[str, str]:
    total_steps = clamp_int(steps, 5, 40)
    if not two_stage:
        # 单段模式下第一段的曲线已经降到 0，本身就是一次完整去噪。
        return resample_sigma_schedule(LTX23_FIRST_SIGMAS, total_steps), ""
    first_steps = clamp_int(round(total_steps * first_stage_ratio), 3, total_steps - 2)
    second_steps = total_steps - first_steps
    return (
        resample_sigma_schedule(LTX23_FIRST_SIGMAS, first_steps),
        resample_sigma_schedule(LTX23_SECOND_SIGMAS, second_steps),
    )


def build_ltx23_t2v_prompt(
    *,
    prompt: str,
    negative: str,
    width: int,
    height: int,
    length: int,
    fps: int,
    seed: int,
    steps: int,
    cfg: float,
    checkpoint_name: str = LTX23_DEV_CHECKPOINT,
    adv: AdvancedParams | None = None,
) -> dict[str, Any]:
    adv = advanced_or_defaults("ltx23_t2v", adv)
    two_stage = adv.enabled("spatial_upscale")
    first_sigmas, second_sigmas = ltx23_sigma_schedules(
        steps,
        float(adv["first_stage_ratio"]),
        two_stage=two_stage,
    )
    # 两段式：先半分辨率采样再超分精修，显存友好，是官方推荐路径。
    # 关闭后按目标分辨率单段直出，快约一半但显存占用高得多。
    low_width = max(64, normalize_dimension(width) // (2 if two_stage else 1))
    low_height = max(64, normalize_dimension(height) // (2 if two_stage else 1))
    frames = normalize_ltx_frames(length)
    cfg_value = clamp_float(cfg, 0.1, 20.0)
    second_seed = (seed + 1) % (2**63 - 1)
    batch = adv["batch_size"]
    graph: dict[str, Any] = {
        "1": node("CheckpointLoaderSimple", {"ckpt_name": checkpoint_name}),
        "2": node(
            "LTXAVTextEncoderLoader",
            {
                "text_encoder": LTX23_TEXT_ENCODER,
                "ckpt_name": checkpoint_name,
                "device": "default",
            },
        ),
        "3": node("CLIPTextEncode", {"text": prompt, "clip": ["2", 0]}),
        "4": node("CLIPTextEncode", {"text": negative, "clip": ["2", 0]}),
        "5": node(
            "LTXVConditioning",
            {"frame_rate": float(fps), "positive": ["3", 0], "negative": ["4", 0]},
        ),
        "6": node("LTXVAudioVAELoader", {"ckpt_name": checkpoint_name}),
        "7": node(
            "EmptyLTXVLatentVideo",
            {"width": low_width, "height": low_height, "length": frames, "batch_size": batch},
        ),
        "8": node(
            "LTXVEmptyLatentAudio",
            {"frames_number": frames, "frame_rate": fps, "batch_size": batch, "audio_vae": ["6", 0]},
        ),
        "9": node("LTXVConcatAVLatent", {"video_latent": ["7", 0], "audio_latent": ["8", 0]}),
        "10": node(
            "LoraLoaderModelOnly",
            {
                "model": ["1", 0],
                "lora_name": LTX23_DISTILLED_LORA,
                "strength_model": float(adv["distill_lora_strength"]),
            },
        ),
        "11": node("RandomNoise", {"noise_seed": seed}),
        "12": node("KSamplerSelect", {"sampler_name": adv["sampler_name"]}),
        "13": node(
            "ManualSigmas",
            {"sigmas": first_sigmas},
        ),
        "14": node(
            "CFGGuider",
            {"model": ["10", 0], "positive": ["5", 0], "negative": ["5", 1], "cfg": cfg_value},
        ),
        "15": node(
            "SamplerCustomAdvanced",
            {
                "noise": ["11", 0],
                "guider": ["14", 0],
                "sampler": ["12", 0],
                "sigmas": ["13", 0],
                "latent_image": ["9", 0],
            },
        ),
        "16": node("LTXVSeparateAVLatent", {"av_latent": ["15", 0]}),
    }
    video_source: list[Any] = ["16", 0]
    audio_source: list[Any] = ["16", 1]
    if two_stage:
        graph.update(
            {
                "17": node("LatentUpscaleModelLoader", {"model_name": LTX23_SPATIAL_UPSCALER}),
                "18": node(
                    "LTXVLatentUpsampler",
                    {"samples": ["16", 0], "upscale_model": ["17", 0], "vae": ["1", 2]},
                ),
                "19": node(
                    "LTXVCropGuides",
                    {"positive": ["5", 0], "negative": ["5", 1], "latent": ["16", 0]},
                ),
                "20": node("LTXVConcatAVLatent", {"video_latent": ["18", 0], "audio_latent": ["16", 1]}),
                "21": node("RandomNoise", {"noise_seed": second_seed}),
                "22": node("KSamplerSelect", {"sampler_name": adv["sampler_name_refine"]}),
                "23": node("ManualSigmas", {"sigmas": second_sigmas}),
                "24": node(
                    "CFGGuider",
                    {"model": ["10", 0], "positive": ["19", 0], "negative": ["19", 1], "cfg": cfg_value},
                ),
                "25": node(
                    "SamplerCustomAdvanced",
                    {
                        "noise": ["21", 0],
                        "guider": ["24", 0],
                        "sampler": ["22", 0],
                        "sigmas": ["23", 0],
                        "latent_image": ["20", 0],
                    },
                ),
                "26": node("LTXVSeparateAVLatent", {"av_latent": ["25", 0]}),
            }
        )
        video_source = ["26", 0]
        audio_source = ["26", 1]
    graph["27"] = vae_tiled_decode(adv, samples=video_source, vae=["1", 2])
    # CreateVideo 的 audio 是可选输入。关掉音频只摘掉解码这个叶子节点，采样阶段
    # 仍然按 AV 潜变量跑 —— LTXVConcatAVLatent 是模型要求的结构，不能随便拆。
    video_inputs: dict[str, Any] = {"images": ["27", 0], "fps": float(fps)}
    if adv.enabled("ltx_audio"):
        graph["28"] = node("LTXVAudioVAEDecode", {"samples": audio_source, "audio_vae": ["6", 0]})
        video_inputs["audio"] = ["28", 0]
    graph["29"] = node("CreateVideo", video_inputs)
    graph["30"] = node(
        "SaveVideo",
        {
            "video": ["29", 0],
            "filename_prefix": output_prefix("LTX23_T2V"),
            "format": "mp4",
            "codec": "h264",
        },
    )
    return graph


def build_ltx23_i2v_prompt(
    *,
    prompt: str,
    negative: str,
    image_name: str,
    width: int,
    height: int,
    length: int,
    fps: int,
    seed: int,
    steps: int,
    cfg: float,
    checkpoint_name: str = LTX23_DEV_CHECKPOINT,
    adv: AdvancedParams | None = None,
) -> dict[str, Any]:
    adv = advanced_or_defaults("ltx23_i2v", adv)
    graph = build_ltx23_t2v_prompt(
        prompt=prompt,
        negative=negative,
        width=width,
        height=height,
        length=length,
        fps=fps,
        seed=seed,
        steps=steps,
        cfg=cfg,
        checkpoint_name=checkpoint_name,
        adv=adv,
    )
    graph["31"] = node("LoadImage", {"image": image_name})
    graph["32"] = node("LTXVPreprocess", {"image": ["31", 0], "img_compression": 18})
    graph["33"] = node(
        "LTXVImgToVideoInplace",
        {
            "vae": ["1", 2],
            "image": ["32", 0],
            "latent": ["7", 0],
            "strength": 0.7,
            "bypass": False,
        },
    )
    graph["9"]["inputs"]["video_latent"] = ["33", 0]
    # 关闭两段式超分时没有 18/20 这两个节点，精修段的关键帧注入自然也就不存在。
    if "18" in graph and "20" in graph:
        graph["34"] = node(
            "LTXVImgToVideoInplace",
            {
                "vae": ["1", 2],
                "image": ["32", 0],
                "latent": ["18", 0],
                "strength": 1.0,
                "bypass": False,
            },
        )
        graph["20"]["inputs"]["video_latent"] = ["34", 0]
    graph["30"]["inputs"]["filename_prefix"] = output_prefix("LTX23_I2V")
    return graph


def ltx25_pipeline_settings(adv: AdvancedParams, *, force_single_stage: bool = False) -> dict[str, Any]:
    profile = str(adv["ltx25_pipeline_profile"] or "balanced")
    if profile == "preview":
        two_stage = False
        decoder = "conv"
    elif profile == "quality":
        two_stage = True
        decoder = "diffusion"
    elif profile == "custom":
        two_stage = adv.enabled("spatial_upscale")
        decoder = str(adv["ltx25_decoder"] or "diffusion")
    else:
        two_stage = True
        decoder = "conv"
    if force_single_stage:
        two_stage = False
    return {"profile": profile, "two_stage": two_stage, "decoder": decoder}


def build_ltx25_t2v_prompt(
    *,
    prompt: str,
    negative: str,
    width: int,
    height: int,
    length: int,
    fps: int,
    seed: int,
    steps: int,
    cfg: float,
    model_name: str = LTX25_DISTILLED_INT8_MODEL,
    text_encoder_name: str = LTX25_TEXT_ENCODER,
    video_vae_diff_name: str = LTX25_VIDEO_VAE_DIFF,
    video_vae_conv_name: str = LTX25_VIDEO_VAE_CONV,
    audio_vae_name: str = LTX25_AUDIO_VAE,
    spatial_upscaler_name: str = LTX25_SPATIAL_UPSCALER,
    duration_head_name: str = LTX25_DURATION_HEAD,
    adv: AdvancedParams | None = None,
    force_single_stage: bool = False,
    unrestricted: bool = False,
    trigger: str = "",
    auto_inject_trigger: bool = True,
    auto_strip_negative: bool = True,
) -> dict[str, Any]:
    adv = advanced_or_defaults("ltx25_t2v", adv)
    prompt, negative = apply_unrestricted_prompt_text(
        prompt,
        negative,
        enabled=unrestricted,
        trigger=trigger,
        auto_inject_trigger=auto_inject_trigger,
        auto_strip_negative=auto_strip_negative,
    )
    pipeline = ltx25_pipeline_settings(adv, force_single_stage=force_single_stage)
    two_stage = bool(pipeline["two_stage"] and adv.enabled("spatial_upscale"))
    first_sigmas, second_sigmas = ltx23_sigma_schedules(
        steps,
        float(adv["first_stage_ratio"]),
        two_stage=two_stage,
    )
    target_width = normalize_dimension(width, 2048)
    target_height = normalize_dimension(height, 2048)
    low_width = max(64, target_width // (2 if two_stage else 1))
    low_height = max(64, target_height // (2 if two_stage else 1))
    frames = normalize_ltx_frames(length)
    frame_input: int | list[Any] = frames
    cfg_value = clamp_float(cfg, 0.0, 100.0)
    audio_cfg = clamp_float(float(adv["ltx_audio_cfg"]), 0.0, 100.0)
    batch = int(adv["batch_size"])
    second_seed = (seed + 1) % (2**63 - 1)
    decoder = str(pipeline["decoder"])
    video_vae_name = video_vae_conv_name if decoder == "conv" else video_vae_diff_name

    graph: dict[str, Any] = {
        "1": node("UNETLoader", {"unet_name": model_name, "weight_dtype": "default"}),
        "2": node(
            "CLIPLoader",
            {"clip_name": text_encoder_name, "type": "ltxv", "device": "default"},
        ),
        "3": node("VAELoader", {"vae_name": video_vae_name}),
        "4": node("VAELoader", {"vae_name": audio_vae_name}),
        "5": node("CLIPTextEncode", {"text": prompt, "clip": ["2", 0]}),
        "6": node("CLIPTextEncode", {"text": negative, "clip": ["2", 0]}),
        "7": node(
            "LTXVConditioning",
            {"positive": ["5", 0], "negative": ["6", 0], "frame_rate": float(fps)},
        ),
        "8": node(
            "EmptyLTXVLatentVideo",
            {"width": low_width, "height": low_height, "length": frame_input, "batch_size": batch},
        ),
        "9": node(
            "LTXVEmptyLatentAudio",
            {
                "frames_number": frame_input,
                "frame_rate": float(fps),
                "batch_size": batch,
                "audio_vae": ["4", 0],
            },
        ),
        "10": node("LTXVConcatAVLatent", {"video_latent": ["8", 0], "audio_latent": ["9", 0]}),
        "11": node("RandomNoise", {"noise_seed": seed}),
        "12": node("KSamplerSelect", {"sampler_name": str(adv["sampler_name"])}),
        "13": node("ManualSigmas", {"sigmas": first_sigmas}),
        "14": node(
            "LTXVDualCFGGuider",
            {
                "model": ["1", 0],
                "positive": ["7", 0],
                "negative": ["7", 1],
                "video_cfg": cfg_value,
                "audio_cfg": audio_cfg,
            },
        ),
        "15": node(
            "SamplerCustomAdvanced",
            {
                "noise": ["11", 0],
                "guider": ["14", 0],
                "sampler": ["12", 0],
                "sigmas": ["13", 0],
                "latent_image": ["10", 0],
            },
        ),
        "16": node("LTXVSeparateAVLatent", {"av_latent": ["15", 0]}),
    }

    if adv.enabled("ltx25_auto_duration"):
        minimum = clamp_float(float(adv["ltx25_min_seconds"]), 0.5, 120.0)
        maximum = max(minimum, clamp_float(float(adv["ltx25_max_seconds"]), 0.5, 120.0))
        graph["40"] = node("ModelPatchLoader", {"name": duration_head_name})
        graph["41"] = node(
            "LTXVDurationPredictor",
            {
                "model": ["1", 0],
                "positive": ["7", 0],
                "duration_head": ["40", 0],
                "frame_rate": float(fps),
                "min_seconds": minimum,
                "max_seconds": maximum,
            },
        )
        graph["8"]["inputs"]["length"] = ["41", 0]
        graph["9"]["inputs"]["frames_number"] = ["41", 0]

    video_source: list[Any] = ["16", 0]
    audio_source: list[Any] = ["16", 1]
    if two_stage:
        graph.update(
            {
                "17": node("LatentUpscaleModelLoader", {"model_name": spatial_upscaler_name}),
                "18": node(
                    "LTXVLatentUpsampler",
                    {"samples": ["16", 0], "upscale_model": ["17", 0], "vae": ["3", 0]},
                ),
                "19": node(
                    "LTXVCropGuides",
                    {"positive": ["7", 0], "negative": ["7", 1], "latent": ["16", 0]},
                ),
                "20": node(
                    "LTXVConcatAVLatent",
                    {"video_latent": ["18", 0], "audio_latent": ["16", 1]},
                ),
                "21": node("RandomNoise", {"noise_seed": second_seed}),
                "22": node("KSamplerSelect", {"sampler_name": str(adv["sampler_name_refine"])}),
                "23": node("ManualSigmas", {"sigmas": second_sigmas}),
                "24": node(
                    "LTXVDualCFGGuider",
                    {
                        "model": ["1", 0],
                        "positive": ["19", 0],
                        "negative": ["19", 1],
                        "video_cfg": cfg_value,
                        "audio_cfg": audio_cfg,
                    },
                ),
                "25": node(
                    "SamplerCustomAdvanced",
                    {
                        "noise": ["21", 0],
                        "guider": ["24", 0],
                        "sampler": ["22", 0],
                        "sigmas": ["23", 0],
                        "latent_image": ["20", 0],
                    },
                ),
                "26": node("LTXVSeparateAVLatent", {"av_latent": ["25", 0]}),
            }
        )
        video_source = ["26", 0]
        audio_source = ["26", 1]

    graph["27"] = vae_tiled_decode(adv, samples=video_source, vae=["3", 0])
    video_inputs: dict[str, Any] = {"images": ["27", 0], "fps": float(fps)}
    if adv.enabled("ltx_audio"):
        graph["28"] = node("LTXVAudioVAEDecode", {"samples": audio_source, "audio_vae": ["4", 0]})
        video_inputs["audio"] = ["28", 0]
    graph["29"] = node("CreateVideo", video_inputs)
    graph["30"] = node(
        "SaveVideo",
        {
            "video": ["29", 0],
            "filename_prefix": output_prefix("LTX25_T2V"),
            "format": "mp4",
            "codec": "h264",
        },
    )
    return graph


def build_ltx25_i2v_prompt(
    *,
    prompt: str,
    negative: str,
    image_name: str,
    end_image_name: str = "",
    width: int,
    height: int,
    length: int,
    fps: int,
    seed: int,
    steps: int,
    cfg: float,
    model_name: str = LTX25_DISTILLED_INT8_MODEL,
    text_encoder_name: str = LTX25_TEXT_ENCODER,
    video_vae_diff_name: str = LTX25_VIDEO_VAE_DIFF,
    video_vae_conv_name: str = LTX25_VIDEO_VAE_CONV,
    audio_vae_name: str = LTX25_AUDIO_VAE,
    spatial_upscaler_name: str = LTX25_SPATIAL_UPSCALER,
    duration_head_name: str = LTX25_DURATION_HEAD,
    adv: AdvancedParams | None = None,
    unrestricted: bool = False,
    trigger: str = "",
    auto_inject_trigger: bool = True,
    auto_strip_negative: bool = True,
) -> dict[str, Any]:
    adv = advanced_or_defaults("ltx25_i2v", adv)
    has_end_frame = bool(str(end_image_name or "").strip())
    graph = build_ltx25_t2v_prompt(
        prompt=prompt,
        negative=negative,
        width=width,
        height=height,
        length=length,
        fps=fps,
        seed=seed,
        steps=steps,
        cfg=cfg,
        model_name=model_name,
        text_encoder_name=text_encoder_name,
        video_vae_diff_name=video_vae_diff_name,
        video_vae_conv_name=video_vae_conv_name,
        audio_vae_name=audio_vae_name,
        spatial_upscaler_name=spatial_upscaler_name,
        duration_head_name=duration_head_name,
        adv=adv,
        force_single_stage=has_end_frame,
        unrestricted=unrestricted,
        trigger=trigger,
        auto_inject_trigger=auto_inject_trigger,
        auto_strip_negative=auto_strip_negative,
    )
    strength = clamp_float(float(adv["ltx25_image_strength"]), 0.0, 1.0)
    graph["31"] = node("LoadImage", {"image": image_name})
    graph["32"] = node("LTXVPreprocess", {"image": ["31", 0], "img_compression": 18})

    if has_end_frame:
        graph["35"] = node("LoadImage", {"image": end_image_name})
        graph["36"] = node("LTXVPreprocess", {"image": ["35", 0], "img_compression": 18})
        graph["37"] = node(
            "LTXVAddGuide",
            {
                "positive": ["7", 0],
                "negative": ["7", 1],
                "vae": ["3", 0],
                "latent": ["8", 0],
                "image": ["32", 0],
                "frame_idx": 0,
                "strength": strength,
            },
        )
        graph["38"] = node(
            "LTXVAddGuide",
            {
                "positive": ["37", 0],
                "negative": ["37", 1],
                "vae": ["3", 0],
                "latent": ["37", 2],
                "image": ["36", 0],
                "frame_idx": -1,
                "strength": strength,
            },
        )
        graph["10"]["inputs"]["video_latent"] = ["38", 2]
        graph["12"] = node("SamplerEulerAncestral", {"eta": 0.0, "s_noise": 1.0})
        graph["14"]["inputs"]["positive"] = ["38", 0]
        graph["14"]["inputs"]["negative"] = ["38", 1]
        graph["42"] = node(
            "LTXVCropGuides",
            {"positive": ["38", 0], "negative": ["38", 1], "latent": ["16", 0]},
        )
        graph["27"]["inputs"]["samples"] = ["42", 2]
        graph["30"]["inputs"]["filename_prefix"] = output_prefix("LTX25_FLF2V")
        return graph

    graph["33"] = node(
        "LTXVImgToVideoInplace",
        {
            "vae": ["3", 0],
            "image": ["32", 0],
            "latent": ["8", 0],
            "strength": strength,
            "bypass": False,
        },
    )
    graph["10"]["inputs"]["video_latent"] = ["33", 0]
    if "18" in graph and "20" in graph:
        graph["34"] = node(
            "LTXVImgToVideoInplace",
            {
                "vae": ["3", 0],
                "image": ["32", 0],
                "latent": ["18", 0],
                "strength": 1.0,
                "bypass": False,
            },
        )
        graph["20"]["inputs"]["video_latent"] = ["34", 0]
    graph["30"]["inputs"]["filename_prefix"] = output_prefix("LTX25_I2V")
    return graph


def build_hunyuan15_prompt(
    *,
    prompt: str,
    negative: str,
    image_name: str,
    width: int,
    height: int,
    length: int,
    fps: int,
    seed: int,
    steps: int,
    cfg: float,
    model_name: str,
    distilled: bool = False,
    adv: AdvancedParams | None = None,
) -> dict[str, Any]:
    is_i2v = bool(str(image_name or "").strip())
    adv = advanced_or_defaults("hunyuan15_i2v" if is_i2v else "hunyuan15_t2v", adv)
    width = normalize_dimension(width)
    height = normalize_dimension(height)
    frames = normalize_frames(length)
    auto_shift = 7.0 if is_i2v and height >= 704 else 9.0 if height >= 704 else 5.0
    shift = float(adv["shift"]) or auto_shift
    cfg_value = 1.0 if distilled else clamp_float(cfg, 1.0, 12.0)
    graph: dict[str, Any] = {
        "1": node("UNETLoader", {"unet_name": model_name, "weight_dtype": "default"}),
        "2": node(
            "DualCLIPLoader",
            {
                "clip_name1": HUNYUAN15_QWEN_ENCODER,
                "clip_name2": HUNYUAN15_BYT5_ENCODER,
                "type": "hunyuan_video_15",
                "device": "default",
            },
        ),
        "3": node("VAELoader", {"vae_name": HUNYUAN15_VAE}),
        "4": node("ModelSamplingSD3", {"model": ["1", 0], "shift": shift}),
        "5": node("CLIPTextEncode", {"text": prompt, "clip": ["2", 0]}),
        "6": node("CLIPTextEncode", {"text": negative, "clip": ["2", 0]}),
    }
    positive_source: list[Any] = ["5", 0]
    negative_source: list[Any] = ["6", 0]
    latent_source: list[Any]
    if is_i2v:
        graph["16"] = node("LoadImage", {"image": image_name})
        graph["17"] = node("CLIPVisionLoader", {"clip_name": HUNYUAN15_SIGCLIP})
        graph["18"] = node(
            "CLIPVisionEncode",
            {"clip_vision": ["17", 0], "image": ["16", 0], "crop": "center"},
        )
        graph["7"] = node(
            "HunyuanVideo15ImageToVideo",
            {
                "positive": positive_source,
                "negative": negative_source,
                "vae": ["3", 0],
                "width": width,
                "height": height,
                "length": frames,
                "batch_size": adv["batch_size"],
                "start_image": ["16", 0],
                "clip_vision_output": ["18", 0],
            },
        )
        positive_source = ["7", 0]
        negative_source = ["7", 1]
        latent_source = ["7", 2]
    else:
        graph["7"] = node(
            "EmptyHunyuanVideo15Latent",
            {"width": width, "height": height, "length": frames, "batch_size": adv["batch_size"]},
        )
        latent_source = ["7", 0]
    graph.update(
        {
            "8": node("RandomNoise", {"noise_seed": seed}),
            "9": node("KSamplerSelect", {"sampler_name": adv["sampler_name"]}),
            "10": node(
                "BasicScheduler",
                {
                    "model": ["4", 0],
                    "scheduler": adv["scheduler"],
                    "steps": clamp_int(steps, 4, 60),
                    "denoise": adv["denoise"],
                },
            ),
            "11": node(
                "CFGGuider",
                {"model": ["4", 0], "positive": positive_source, "negative": negative_source, "cfg": cfg_value},
            ),
            "12": node(
                "SamplerCustomAdvanced",
                {
                    "noise": ["8", 0],
                    "guider": ["11", 0],
                    "sampler": ["9", 0],
                    "sigmas": ["10", 0],
                    "latent_image": latent_source,
                },
            ),
            "13": node("VAEDecode", {"samples": ["12", 0], "vae": ["3", 0]}),
            "14": node("CreateVideo", {"images": ["13", 0], "fps": float(fps)}),
            "15": node(
                "SaveVideo",
                {
                    "video": ["14", 0],
                    "filename_prefix": output_prefix("Hunyuan15_I2V" if is_i2v else "Hunyuan15_T2V"),
                    "format": "mp4",
                    "codec": "h264",
                },
            ),
        }
    )
    return graph


def format_minimax_h3_prompt(prompt: str) -> str:
    """Wrap a plain brief in MiniMax's documented three-field prompt shape."""
    text = str(prompt or "").strip()
    lowered = text.lower()
    if "integrated_multimodal_description:" in lowered:
        return text
    visual = text if "[shot " in lowered else f"[Shot 1] {text}"
    return (
        f"integrated_multimodal_description:\n{visual}\n\n"
        "overall_soundscape:\n"
        "Natural scene ambience synchronized with the visible action. "
        "No dialogue unless dialogue is explicitly requested above.\n\n"
        "non_diegetic_music:\nN/A"
    )


def minimax_h3_runtime_settings(adv: AdvancedParams, steps: int) -> dict[str, Any]:
    profile = str(adv["h3_acceleration_profile"] or "native")
    settings: dict[str, Any] = {
        "profile": profile,
        "steps": clamp_int(steps, 4, 40),
        "sampler": str(adv["sampler_name"]),
        "scheduler": str(adv["scheduler"]),
        "shift_video": float(adv["h3_shift_video"]),
        "shift_audio": float(adv["h3_shift_audio"]),
        "turbo_lora": "",
        "turbo_strength": 0.0,
        "spectrum": False,
        "denoise": float(adv["denoise"]),
    }
    recipe = video_params.H3_RUNTIME_PROFILES.get(profile)
    if recipe:
        settings.update({key: recipe[key] for key in (
            "steps", "sampler", "scheduler", "shift_video", "shift_audio"
        )})
        settings.update(
            spectrum=bool(recipe.get("spectrum")),
            turbo_lora=str(recipe.get("lora_name") or ""),
            turbo_strength=float(adv["h3_turbo_strength"]) if recipe.get("lora_name") else 0.0,
            denoise=1.0,
        )
    return settings


def build_minimax_h3_prompt(
    *,
    prompt: str,
    negative: str,
    image_name: str,
    end_image_name: str = "",
    width: int,
    height: int,
    length: int,
    fps: int,
    seed: int,
    steps: int,
    cfg: float,
    adv: AdvancedParams | None = None,
    unrestricted: bool = False,
    trigger: str = "",
    auto_inject_trigger: bool = True,
    auto_strip_negative: bool = True,
) -> dict[str, Any]:
    """Build the official MiniMax H3 FL2VA joint audio-video sampling graph."""
    is_i2v = bool(str(image_name or "").strip() or str(end_image_name or "").strip())
    mode = "minimax_h3_i2v" if is_i2v else "minimax_h3_t2v"
    adv = advanced_or_defaults(mode, adv)
    width = normalize_dimension(width, 2048)
    height = normalize_dimension(height, 2048)
    frames = normalize_minimax_h3_frames(length)
    effective_prompt, _effective_negative = apply_unrestricted_prompt_text(
        prompt,
        negative,
        enabled=unrestricted,
        trigger=trigger,
        auto_inject_trigger=auto_inject_trigger,
        auto_strip_negative=auto_strip_negative,
    )
    if adv["h3_prompt_format"] == "official_three_part":
        effective_prompt = format_minimax_h3_prompt(effective_prompt)
    runtime = minimax_h3_runtime_settings(adv, steps)
    # H3 Base is CFG-distilled and fixed at 24 fps. BasicGuider intentionally
    # has no negative-conditioning or CFG input in the official workflow.
    _ = _effective_negative, fps, cfg
    graph: dict[str, Any] = {
        "1": node("UNETLoader", {"unet_name": MINIMAX_H3_FL2VA_MODEL, "weight_dtype": "default"}),
        "2": node(
            "CLIPLoader",
            {"clip_name": MINIMAX_H3_TEXT_ENCODER, "type": "minimax", "device": "default"},
        ),
        "3": node("VAELoader", {"vae_name": MINIMAX_H3_VIDEO_VAE}),
        "5": node(
            "MiniMaxH3ImageToVideo",
            {
                "clip": ["2", 0],
                "vae": ["3", 0],
                "prompt": effective_prompt,
                "width": width,
                "height": height,
                "length": frames,
            },
        ),
        "6": node("RandomNoise", {"noise_seed": seed}),
    }
    model_source: list[Any] = ["1", 0]
    if runtime["turbo_lora"]:
        graph["30"] = node(
            "LoraLoaderModelOnly",
            {
                "model": model_source,
                "lora_name": runtime["turbo_lora"],
                "strength_model": runtime["turbo_strength"],
            },
        )
        model_source = ["30", 0]
    graph["4"] = node(
        "MiniMaxH3SigmaShift",
        {
            "model": model_source,
            "shift_video": runtime["shift_video"],
            "shift_audio": runtime["shift_audio"],
        },
    )
    sampling_model: list[Any] = ["4", 0]
    if runtime["spectrum"]:
        graph["31"] = node(
            "SpectrumApplyMiniMaxH3",
            {
                "model": sampling_model,
                "enabled": True,
                "blend_weight": 0.5,
                "degree": 1,
                "ridge_lambda": 0.1,
                "window_size": 2.0,
                "flex_window": 0.75,
                "warmup_steps": 1,
                "tail_actual_steps": 1,
                "max_history": 8,
                "debug": False,
                "history_storage": "system_ram",
                "bootstrap_first_forecast": True,
                "offline_smoothing_replay": True,
                "audio_blend_weight": 0.0,
                "offline_archive_storage": "system_ram",
                "model_aware_mode": "off",
            },
        )
        sampling_model = ["31", 0]
    graph.update(
        {
            "7": node("KSamplerSelect", {"sampler_name": runtime["sampler"]}),
            "8": node(
                "BasicScheduler",
                {
                    "model": sampling_model,
                    "scheduler": runtime["scheduler"],
                    "steps": runtime["steps"],
                    "denoise": runtime["denoise"],
                },
            ),
            "9": node("BasicGuider", {"model": sampling_model, "conditioning": ["5", 0]}),
            "10": node(
                "SamplerCustomAdvanced",
                {
                    "noise": ["6", 0],
                    "guider": ["9", 0],
                    "sampler": ["7", 0],
                    "sigmas": ["8", 0],
                    "latent_image": ["5", 1],
                },
            ),
            "11": (
                node(
                    "VAEDecodeTiled",
                    {
                        "samples": ["10", 0],
                        "vae": ["3", 0],
                        "tile_size": 512,
                        "overlap": 64,
                        "temporal_size": 64,
                        "temporal_overlap": 8,
                    },
                )
                if adv["h3_tiled_decode"]
                else node("VAEDecode", {"samples": ["10", 0], "vae": ["3", 0]})
            ),
            "12": node("CreateVideo", {"images": ["11", 0], "fps": 24.0}),
            "13": node(
                "SaveVideo",
                {
                    "video": ["12", 0],
                    "filename_prefix": output_prefix(
                        ("MiniMax_H3_FL2VA" if is_i2v else "MiniMax_H3_T2V")
                        + {
                            "spectrum_balanced": "_Spectrum",
                            "lightx8_v10": "_LightX8_v10",
                            "lightx4_v11_768p": "_LightX4_v11",
                            "lightx4_v12_768p": "_LightX4_v12_768P",
                            "lightx8_v10_768p": "_LightX8_v10_768P",
                        }.get(runtime["profile"], "")
                    ),
                    "format": "mp4",
                    "codec": "h264",
                },
            ),
        }
    )
    if image_name:
        graph["20"] = node("LoadImage", {"image": image_name})
        graph["5"]["inputs"]["first_frame"] = ["20", 0]
    if end_image_name:
        graph["21"] = node("LoadImage", {"image": end_image_name})
        graph["5"]["inputs"]["last_frame"] = ["21", 0]
    if adv["h3_audio"]:
        graph["14"] = node("VAELoader", {"vae_name": MINIMAX_H3_AUDIO_VAE})
        graph["15"] = node("VAEDecodeAudio", {"samples": ["10", 0], "vae": ["14", 0]})
        graph["12"]["inputs"]["audio"] = ["15", 0]
    if width == 1920 and height == 1088:
        graph["16"] = node("ImageCrop", {"image": ["11", 0], "width": 1920, "height": 1080, "x": 0, "y": 4})
        graph["12"]["inputs"]["images"] = ["16", 0]
    elif width == 1088 and height == 1920:
        graph["16"] = node("ImageCrop", {"image": ["11", 0], "width": 1080, "height": 1920, "x": 4, "y": 0})
        graph["12"]["inputs"]["images"] = ["16", 0]
    return graph


def build_minimax_h3_reference_prompt(
    *,
    prompt: str,
    negative: str,
    reference_images: list[str],
    reference_videos: list[str],
    reference_audios: list[str],
    width: int,
    height: int,
    length: int,
    fps: int,
    seed: int,
    steps: int,
    cfg: float,
    adv: AdvancedParams | None = None,
    unrestricted: bool = False,
    trigger: str = "",
    auto_inject_trigger: bool = True,
    auto_strip_negative: bool = True,
) -> dict[str, Any]:
    """Build MiniMax H3 ref2va with image, video and audio references."""
    adv = advanced_or_defaults("minimax_h3_r2v", adv)
    graph = build_minimax_h3_prompt(
        prompt=prompt,
        negative=negative,
        image_name="",
        width=width,
        height=height,
        length=length,
        fps=fps,
        seed=seed,
        steps=steps,
        cfg=cfg,
        adv=adv,
        unrestricted=unrestricted,
        trigger=trigger,
        auto_inject_trigger=auto_inject_trigger,
        auto_strip_negative=auto_strip_negative,
    )
    graph["1"]["inputs"]["unet_name"] = MINIMAX_H3_REF2VA_MODEL
    graph.setdefault("14", node("VAELoader", {"vae_name": MINIMAX_H3_AUDIO_VAE}))
    conditioning_inputs: dict[str, Any] = {
        "clip": ["2", 0],
        "vae": ["3", 0],
        "audio_vae": ["14", 0],
        "prompt": graph["5"]["inputs"]["prompt"],
        "width": normalize_dimension(width, 2048),
        "height": normalize_dimension(height, 2048),
        "length": normalize_minimax_h3_frames(length),
        "ref_image_size": str(adv["h3_reference_size"]),
    }

    next_node = 50
    for index, image_name in enumerate(reference_images[:9]):
        node_id = str(next_node)
        next_node += 1
        graph[node_id] = node("LoadImage", {"image": image_name})
        conditioning_inputs[f"ref_images.ref_image_{index}"] = [node_id, 0]

    for index, video_name in enumerate(reference_videos[:3]):
        node_id = str(next_node)
        next_node += 1
        graph[node_id] = node(
            "VHS_LoadVideo",
            {
                "video": video_name,
                "force_rate": 24,
                "custom_width": 0,
                "custom_height": 0,
                "frame_load_cap": 360,
                "skip_first_frames": 0,
                "select_every_nth": 1,
            },
        )
        conditioning_inputs[f"ref_videos.ref_video_{index}"] = [node_id, 0]
        conditioning_inputs[f"ref_video_audios.ref_video_audio_{index}"] = [node_id, 2]

    for index, audio_name in enumerate(reference_audios[:3]):
        node_id = str(next_node)
        next_node += 1
        graph[node_id] = node("LoadAudio", {"audio": audio_name})
        conditioning_inputs[f"ref_audios.ref_audio_{index}"] = [node_id, 0]

    graph["5"] = node("MiniMaxH3ReferenceToVideo", conditioning_inputs)
    runtime = minimax_h3_runtime_settings(adv, steps)
    suffix = "_LightXRef4" if runtime["profile"] == "lightx_ref4_v01" else ""
    graph["13"]["inputs"]["filename_prefix"] = output_prefix(f"MiniMax_H3_R2V{suffix}")
    return graph


def build_ltx_i2v_prompt(
    *,
    prompt: str,
    negative: str,
    image_name: str,
    width: int,
    height: int,
    length: int,
    fps: int,
    seed: int,
    steps: int,
    cfg: float,
    adv: AdvancedParams | None = None,
) -> dict[str, Any]:
    adv = advanced_or_defaults("ltx_i2v", adv)
    return {
        "1": node("LoadImage", {"image": image_name}),
        "2": node("LTXVPreprocess", {"image": ["1", 0], "img_compression": 40}),
        "3": node("CheckpointLoaderSimple", {"ckpt_name": "ltxv-2b-0.9.8-distilled-fp8.safetensors"}),
        "4": node(
            "CLIPLoader",
            {
                "clip_name": "t5xxl_fp16.safetensors",
                "type": "ltxv",
                "device": "default",
            },
        ),
        "5": node("CLIPTextEncode", {"text": prompt, "clip": ["4", 0]}),
        "6": node("CLIPTextEncode", {"text": negative, "clip": ["4", 0]}),
        "7": node(
            "LTXVImgToVideo",
            {
                "positive": ["5", 0],
                "negative": ["6", 0],
                "vae": ["3", 2],
                "image": ["2", 0],
                "width": width,
                "height": height,
                "length": normalize_ltx_frames(length),
                "batch_size": adv["batch_size"],
                "strength": 1.0,
            },
        ),
        "8": node("LTXVConditioning", {"frame_rate": float(fps), "positive": ["7", 0], "negative": ["7", 1]}),
        "9": node(
            "LTXVScheduler",
            {
                "steps": steps,
                "max_shift": adv["ltx_max_shift"],
                "base_shift": adv["ltx_base_shift"],
                "stretch": adv.enabled("ltx_stretch"),
                "terminal": adv["ltx_terminal"],
                "latent": ["7", 2],
            },
        ),
        "10": node("KSamplerSelect", {"sampler_name": adv["sampler_name"]}),
        "11": node(
            "SamplerCustom",
            {
                "model": ["3", 0],
                "add_noise": True,
                "noise_seed": seed,
                "cfg": cfg,
                "positive": ["8", 0],
                "negative": ["8", 1],
                "sampler": ["10", 0],
                "sigmas": ["9", 0],
                "latent_image": ["7", 2],
            },
        ),
        "12": node("VAEDecode", {"samples": ["11", 0], "vae": ["3", 2]}),
        "13": node("CreateVideo", {"images": ["12", 0], "fps": float(fps)}),
        "14": node(
            "SaveVideo",
            {
                "video": ["13", 0],
                "filename_prefix": output_prefix("Mac_LTX_I2V"),
                "format": "mp4",
                "codec": "h264",
            },
        ),
    }


def build_a14b_i2v_prompt(
    *,
    prompt: str,
    negative: str,
    image_name: str,
    width: int,
    height: int,
    length: int,
    fps: int,
    seed: int,
    steps: int,
    cfg: float,
    end_image_name: str = "",
    unrestricted: bool = False,
    unrestricted_strength: float = 0.8,
    trigger: str = "nsfwsks",
    auto_inject_trigger: bool = True,
    auto_strip_negative: bool = True,
    motion_lora_high: str = "",
    motion_lora_low: str = "",
    adv: AdvancedParams | None = None,
) -> dict[str, Any]:
    adv = advanced_or_defaults("i2v_a14b", adv)
    end_image_name = str(end_image_name or "").strip()
    split_step = clamp_int(round(steps * float(adv["boundary_ratio"])), 1, max(1, steps - 1))
    shift = float(adv["shift"]) or 5.0
    cfg_high = float(adv["cfg_high"]) or cfg
    cfg_low = float(adv["cfg_low"]) or cfg
    effective_prompt = prompt
    effective_negative = negative
    if unrestricted:
        effective_prompt, effective_negative = apply_unrestricted_prompt_text(
            prompt,
            negative,
            enabled=True,
            trigger=trigger or "nsfwsks",
            auto_inject_trigger=auto_inject_trigger,
            auto_strip_negative=auto_strip_negative,
        )
        effective_negative = append_consistency_negative(effective_negative, enabled=True)
    graph = {
        "10": node(
            "CLIPLoader",
            {
                "clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors",
                "type": "wan",
                "device": "default",
            },
        ),
        "11": node("CLIPTextEncode", {"text": effective_prompt, "clip": ["10", 0]}),
        "12": node("CLIPTextEncode", {"text": effective_negative, "clip": ["10", 0]}),
        "13": node("VAELoader", {"vae_name": "wan_2.1_vae.safetensors"}),
        "14": node("LoadImage", {"image": image_name}),
        "30": node(
            "UNETLoader",
            {
                "unet_name": "Wan2.2/wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors",
                "weight_dtype": "default",
            },
        ),
        "40": node(
            "UNETLoader",
            {
                "unet_name": "Wan2.2/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors",
                "weight_dtype": "default",
            },
        ),
        "50": node(
            "KSamplerAdvanced",
            {
                "model": ["32", 0],
                "add_noise": "enable",
                "noise_seed": seed,
                "steps": steps,
                "cfg": cfg_high,
                "sampler_name": adv["sampler_name"],
                "scheduler": adv["scheduler"],
                "positive": ["20", 0],
                "negative": ["20", 1],
                "latent_image": ["20", 2],
                "start_at_step": 0,
                "end_at_step": split_step,
                "return_with_leftover_noise": "enable",
            },
        ),
        "51": node(
            "KSamplerAdvanced",
            {
                "model": ["42", 0],
                "add_noise": "disable",
                "noise_seed": seed,
                "steps": steps,
                "cfg": cfg_low,
                "sampler_name": adv["sampler_name"],
                "scheduler": adv["scheduler"],
                "positive": ["20", 0],
                "negative": ["20", 1],
                "latent_image": ["50", 0],
                "start_at_step": split_step,
                "end_at_step": steps,
                "return_with_leftover_noise": "disable",
            },
        ),
        "60": vae_tiled_decode(adv, samples=["51", 0], vae=["13", 0]),
        "70": node("CreateVideo", {"images": ["60", 0], "fps": fps}),
        "80": node(
            "SaveVideo",
            {
                "video": ["70", 0],
                "filename_prefix": output_prefix("I2V_A14B"),
                "format": "mp4",
                "codec": "h264",
            },
        ),
    }
    # 有尾帧就换成首尾帧节点。两者的输出都是 (positive, negative, latent)，
    # 所以下游 50/51 引用的 ["20", 0/1/2] 完全不用改。
    latent_inputs: dict[str, Any] = {
        "positive": ["11", 0],
        "negative": ["12", 0],
        "vae": ["13", 0],
        "width": width,
        "height": height,
        "length": length,
        "batch_size": adv["batch_size"],
        "start_image": ["14", 0],
    }
    if end_image_name:
        graph["15"] = node("LoadImage", {"image": end_image_name})
        latent_inputs["end_image"] = ["15", 0]
        graph["20"] = node("WanFirstLastFrameToVideo", latent_inputs)
    else:
        graph["20"] = node("WanImageToVideo", latent_inputs)

    # 模型链顺序：UNET -> 加速 LoRA -> 无限制 LoRA -> 动作 LoRA -> ModelSamplingSD3。
    # 强度为 0 的环节会被整段跳过，所以"关掉加速 LoRA 跑全步数"是真的没加载它。
    nsfw_strength = clamp_float(unrestricted_strength, 0.0, 1.2) if unrestricted else 0.0
    motion_strength = float(adv["motion_lora_strength"])
    lightx2v_strength = float(adv["lightx2v_strength"])
    high_source = stack_model_loras(
        graph,
        base=["30", 0],
        entries=[
            ("31", "Wan2.2/wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors", lightx2v_strength),
            ("33", "Wan2.2/Unrestricted/NSFW-22-H-e8.safetensors", nsfw_strength),
            ("34", motion_lora_high, motion_strength),
        ],
    )
    low_source = stack_model_loras(
        graph,
        base=["40", 0],
        entries=[
            ("41", "Wan2.2/wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors", lightx2v_strength),
            ("43", "Wan2.2/Unrestricted/NSFW-22-L-e8.safetensors", nsfw_strength),
            ("44", motion_lora_low, motion_strength),
        ],
    )
    graph["32"] = node("ModelSamplingSD3", {"model": high_source, "shift": shift})
    graph["42"] = node("ModelSamplingSD3", {"model": low_source, "shift": shift})
    return graph


def build_a14b_t2v_prompt(
    *,
    prompt: str,
    negative: str,
    width: int,
    height: int,
    length: int,
    fps: int,
    seed: int,
    steps: int,
    cfg: float,
    unrestricted: bool = False,
    unrestricted_strength: float = 0.8,
    trigger: str = "",
    auto_inject_trigger: bool = True,
    auto_strip_negative: bool = True,
    motion_lora_high: str = "",
    motion_lora_low: str = "",
    adv: AdvancedParams | None = None,
) -> dict[str, Any]:
    adv = advanced_or_defaults("t2v_a14b", adv)
    split_step = clamp_int(round(steps * float(adv["boundary_ratio"])), 1, max(1, steps - 1))
    shift = float(adv["shift"]) or 5.0
    cfg_high = float(adv["cfg_high"]) or cfg
    cfg_low = float(adv["cfg_low"]) or cfg
    effective_prompt, effective_negative = apply_unrestricted_prompt_text(
        prompt,
        negative,
        enabled=unrestricted,
        trigger=trigger,
        auto_inject_trigger=auto_inject_trigger,
        auto_strip_negative=auto_strip_negative,
    )
    if unrestricted:
        effective_negative = append_consistency_negative(effective_negative, enabled=True)
    graph = {
        "10": node(
            "CLIPLoader",
            {
                "clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors",
                "type": "wan",
                "device": "default",
            },
        ),
        "11": node("CLIPTextEncode", {"text": effective_prompt, "clip": ["10", 0]}),
        "12": node("CLIPTextEncode", {"text": effective_negative, "clip": ["10", 0]}),
        "13": node("VAELoader", {"vae_name": "wan_2.1_vae.safetensors"}),
        # The official ComfyUI Wan2.2 T2V template uses this generic video latent node.
        "20": node(
            "EmptyHunyuanLatentVideo",
            {"width": width, "height": height, "length": length, "batch_size": adv["batch_size"]},
        ),
        "30": node(
            "UNETLoader",
            {
                "unet_name": "Wan2.2/wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors",
                "weight_dtype": "default",
            },
        ),
        "40": node(
            "UNETLoader",
            {
                "unet_name": "Wan2.2/wan2.2_t2v_low_noise_14B_fp8_scaled.safetensors",
                "weight_dtype": "default",
            },
        ),
        "50": node(
            "KSamplerAdvanced",
            {
                "model": ["32", 0],
                "add_noise": "enable",
                "noise_seed": seed,
                "steps": steps,
                "cfg": cfg_high,
                "sampler_name": adv["sampler_name"],
                "scheduler": adv["scheduler"],
                "positive": ["11", 0],
                "negative": ["12", 0],
                "latent_image": ["20", 0],
                "start_at_step": 0,
                "end_at_step": split_step,
                "return_with_leftover_noise": "enable",
            },
        ),
        "51": node(
            "KSamplerAdvanced",
            {
                "model": ["42", 0],
                "add_noise": "disable",
                "noise_seed": seed,
                "steps": steps,
                "cfg": cfg_low,
                "sampler_name": adv["sampler_name"],
                "scheduler": adv["scheduler"],
                "positive": ["11", 0],
                "negative": ["12", 0],
                "latent_image": ["50", 0],
                "start_at_step": split_step,
                "end_at_step": steps,
                "return_with_leftover_noise": "disable",
            },
        ),
        "60": vae_tiled_decode(adv, samples=["51", 0], vae=["13", 0]),
        "70": node("CreateVideo", {"images": ["60", 0], "fps": fps}),
        "80": node(
            "SaveVideo",
            {
                "video": ["70", 0],
                "filename_prefix": output_prefix("T2V_A14B"),
                "format": "mp4",
                "codec": "h264",
            },
        ),
    }
    nsfw_strength = clamp_float(unrestricted_strength, 0.0, 1.2) if unrestricted else 0.0
    motion_strength = float(adv["motion_lora_strength"])
    lightx2v_strength = float(adv["lightx2v_strength"])
    high_source = stack_model_loras(
        graph,
        base=["30", 0],
        entries=[
            ("31", "Wan2.2/wan2.2_t2v_lightx2v_4steps_lora_v1.1_high_noise.safetensors", lightx2v_strength),
            ("33", "Wan2.2/Unrestricted/NSFW-22-H-e8.safetensors", nsfw_strength),
            ("34", motion_lora_high, motion_strength),
        ],
    )
    low_source = stack_model_loras(
        graph,
        base=["40", 0],
        entries=[
            ("41", "Wan2.2/wan2.2_t2v_lightx2v_4steps_lora_v1.1_low_noise.safetensors", lightx2v_strength),
            ("43", "Wan2.2/Unrestricted/NSFW-22-L-e8.safetensors", nsfw_strength),
            ("44", motion_lora_low, motion_strength),
        ],
    )
    graph["32"] = node("ModelSamplingSD3", {"model": high_source, "shift": shift})
    graph["42"] = node("ModelSamplingSD3", {"model": low_source, "shift": shift})
    return graph


def build_rife_prompt(
    *,
    video_name: str,
    fps: int,
    multiplier: int,
    dtype: str = "float32",
    batch_size: int | None = None,
    adv: AdvancedParams | None = None,
) -> dict[str, Any]:
    adv = advanced_or_defaults("rife_2x", adv)
    multiplier = clamp_int(multiplier, 2, 4)
    output_fps = clamp_int(fps * multiplier, 1, 120)
    dtype = dtype if dtype in {"float32", "float16", "bfloat16"} else "float32"
    if batch_size is None:
        batch_size = 4 if dtype in {"float16", "bfloat16"} else 1
    batch_size = clamp_int(batch_size, 1, 16)
    return {
        "1": node(
            "VHS_LoadVideo",
            {
                "video": video_name,
                "force_rate": fps,
                "custom_width": 0,
                "custom_height": 0,
                "frame_load_cap": 0,
                "skip_first_frames": 0,
                "select_every_nth": 1,
            },
        ),
        "2": node(
            "RIFE VFI",
            {
                "ckpt_name": "rife49.pth",
                "frames": ["1", 0],
                "clear_cache_after_n_frames": 10,
                "multiplier": multiplier,
                "fast_mode": adv.enabled("rife_fast_mode"),
                "ensemble": adv.enabled("rife_ensemble"),
                "scale_factor": 1.0,
                "dtype": dtype,
                "torch_compile": False,
                "batch_size": batch_size,
            },
        ),
        "3": node(
            "VHS_VideoCombine",
            {
                "images": ["2", 0],
                "audio": ["1", 2],
                "frame_rate": output_fps,
                "loop_count": 0,
                "filename_prefix": output_prefix(f"RIFE_{multiplier}x"),
                "format": "video/h264-mp4",
                "pix_fmt": adv["pix_fmt"],
                "crf": adv["crf"],
                "save_metadata": True,
                "trim_to_audio": False,
                "pingpong": False,
                "save_output": True,
            },
        ),
    }


def rife_runtime_options(hardware: dict[str, Any] | None = None) -> dict[str, Any]:
    hardware = hardware or build_hardware_summary(None)
    accelerator = str(hardware.get("accelerator") or "cpu")
    if accelerator == "cuda":
        return {"dtype": "float16", "batch_size": 4}
    return {"dtype": "float32", "batch_size": 1}


def build_seedvr2_upscale_prompt(
    *,
    video_name: str,
    fps: int,
    seed: int = 1,
    model_name: str = SEEDVR2_3B_MODEL,
    scale: float = 2.0,
    adv: AdvancedParams | None = None,
) -> dict[str, Any]:
    """Build the native ComfyUI SeedVR2 temporal restoration workflow."""
    adv = advanced_or_defaults("upscale_seedvr2", adv)
    fps = clamp_int(fps, 1, 120)
    model_name = model_name if model_name in SEEDVR2_MODELS else SEEDVR2_3B_MODEL
    scale = clamp_float(scale, 1.0, 4.0)
    return {
        "1": node(
            "VHS_LoadVideo",
            {
                "video": video_name,
                "force_rate": fps,
                "custom_width": 0,
                "custom_height": 0,
                "frame_load_cap": 0,
                "skip_first_frames": 0,
                "select_every_nth": 1,
            },
        ),
        "2": node("ImageScaleBy", {"image": ["1", 0], "upscale_method": "lanczos", "scale_by": scale}),
        "3": node("SeedVR2Preprocess", {"resized_images": ["2", 0]}),
        "4": node("VAELoader", {"vae_name": SEEDVR2_VIDEO_VAE}),
        "5": node(
            "VAEEncodeTiled",
            {
                "pixels": ["3", 0],
                "vae": ["4", 0],
                "tile_size": adv["vae_tile_size"],
                "overlap": adv["vae_tile_overlap"],
                "temporal_size": adv["vae_temporal_size"],
                "temporal_overlap": adv["vae_temporal_overlap"],
            },
        ),
        "6": node("UNETLoader", {"unet_name": model_name, "weight_dtype": "default"}),
        "7": node(
            "SeedVR2TemporalChunk",
            {
                "latent": ["5", 0],
                "temporal_overlap": adv["seedvr_temporal_overlap"],
                "chunking_mode": "auto",
            },
        ),
        "8": node("SeedVR2Conditioning", {"model": ["6", 0], "vae_conditioning": ["7", 0]}),
        "9": node(
            "KSampler",
            {
                "model": ["6", 0],
                "seed": seed,
                "steps": 1,
                "cfg": 1.0,
                "sampler_name": "euler",
                "scheduler": "simple",
                "positive": ["8", 0],
                "negative": ["8", 1],
                "latent_image": ["7", 0],
                "denoise": adv["denoise"],
            },
        ),
        "10": node("SeedVR2TemporalMerge", {"latents": ["9", 0], "temporal_overlap": ["7", 1]}),
        "11": node(
            "VAEDecodeTiled",
            {
                "samples": ["10", 0],
                "vae": ["4", 0],
                "tile_size": adv["vae_tile_size"],
                "overlap": adv["vae_tile_overlap"],
                "temporal_size": adv["vae_temporal_size"],
                "temporal_overlap": adv["vae_temporal_overlap"],
            },
        ),
        "12": node(
            "SeedVR2PostProcessing",
            {
                "images": ["11", 0],
                "original_resized_images": ["2", 0],
                "color_correction_method": adv["seedvr_color_correction"],
            },
        ),
        "13": node(
            "VHS_VideoCombine",
            {
                "images": ["12", 0],
                "audio": ["1", 2],
                "frame_rate": fps,
                "loop_count": 0,
                "filename_prefix": output_prefix(f"SeedVR2_{scale:g}x"),
                "format": "video/h264-mp4",
                "pix_fmt": adv["pix_fmt"],
                "crf": adv["crf"],
                "save_metadata": True,
                "trim_to_audio": False,
                "pingpong": False,
                "save_output": True,
            },
        ),
    }


def build_video_upscale_prompt(
    *,
    video_name: str,
    fps: int,
    model_name: str = "RealESRGAN_x2plus.pth",
    adv: AdvancedParams | None = None,
) -> dict[str, Any]:
    adv = advanced_or_defaults("upscale_2x", adv)
    fps = clamp_int(fps, 1, 120)
    allowed_models = {"RealESRGAN_x2plus.pth", "4x-UltraSharp.pth"}
    if model_name not in allowed_models:
        model_name = "RealESRGAN_x2plus.pth"
    return {
        "1": node(
            "VHS_LoadVideo",
            {
                "video": video_name,
                "force_rate": fps,
                "custom_width": 0,
                "custom_height": 0,
                "frame_load_cap": 0,
                "skip_first_frames": 0,
                "select_every_nth": 1,
            },
        ),
        "2": node("UpscaleModelLoader", {"model_name": model_name}),
        "3": node(
            "ImageUpscaleWithModel",
            {
                "upscale_model": ["2", 0],
                "image": ["1", 0],
            },
        ),
        "4": node(
            "VHS_VideoCombine",
            {
                "images": ["3", 0],
                "audio": ["1", 2],
                "frame_rate": fps,
                "loop_count": 0,
                "filename_prefix": output_prefix("Upscale_2x"),
                "format": "video/h264-mp4",
                "pix_fmt": adv["pix_fmt"],
                "crf": adv["crf"],
                "save_metadata": True,
                "trim_to_audio": False,
                "pingpong": False,
                "save_output": True,
            },
        ),
    }


def build_preview_workflow_graph(
    *,
    mode: str,
    model_profile: str = "",
    prompt: str,
    negative: str,
    width: int,
    height: int,
    length: int,
    fps: int,
    seed: int,
    steps: int,
    cfg: float,
    upscale_model: str,
    upscale_scale: float = 2.0,
    rife_multiplier: int,
    has_image: bool = False,
    has_end_image: bool = False,
    has_reference_media: bool = False,
    unrestricted: bool = False,
    unrestricted_strength: float = 0.8,
    trigger: str = "",
    auto_inject_trigger: bool = True,
    auto_strip_negative: bool = True,
    adv: AdvancedParams | None = None,
) -> dict[str, Any] | None:
    profile_spec = workflow_profile_specs().get(clean_id(model_profile), {})
    # 预览必须和真正提交的图完全一致，否则预检通过了实跑还会炸。
    adv = advanced_or_defaults(mode, adv)
    if mode == "i2v_a14b":
        return build_a14b_i2v_prompt(
            prompt=prompt,
            negative=negative,
            image_name=KEYFRAME_UPLOAD_PLACEHOLDER,
            end_image_name=KEYFRAME_UPLOAD_PLACEHOLDER if has_end_image else "",
            width=width,
            height=height,
            length=length,
            fps=fps,
            seed=seed,
            steps=steps,
            cfg=cfg,
            unrestricted=unrestricted,
            unrestricted_strength=unrestricted_strength,
            trigger=trigger or "nsfwsks",
            auto_inject_trigger=auto_inject_trigger,
            auto_strip_negative=auto_strip_negative,
            adv=adv,
        )
    if mode == "t2v_a14b":
        return build_a14b_t2v_prompt(
            prompt=prompt,
            negative=negative,
            width=width,
            height=height,
            length=length,
            fps=fps,
            seed=seed,
            steps=steps,
            cfg=cfg,
            unrestricted=unrestricted,
            unrestricted_strength=unrestricted_strength,
            trigger=trigger,
            auto_inject_trigger=auto_inject_trigger,
            auto_strip_negative=auto_strip_negative,
            adv=adv,
        )
    if mode == "ti2v_5b":
        return build_ti2v_prompt(
            prompt=prompt,
            negative=negative,
            image_name=KEYFRAME_UPLOAD_PLACEHOLDER if has_image else "",
            width=width,
            height=height,
            length=length,
            fps=fps,
            seed=seed,
            steps=steps,
            cfg=cfg,
            adv=adv,
        )
    if mode == "ltx_i2v":
        return build_ltx_i2v_prompt(
            prompt=prompt,
            negative=negative,
            image_name=KEYFRAME_UPLOAD_PLACEHOLDER,
            width=width,
            height=height,
            length=normalize_ltx_frames(length),
            fps=fps,
            seed=seed,
            steps=steps,
            cfg=cfg,
            adv=adv,
        )
    if mode == "ltx_t2v":
        return build_ltx_t2v_prompt(
            prompt=prompt,
            negative=negative,
            width=width,
            height=height,
            length=normalize_ltx_frames(length),
            fps=fps,
            seed=seed,
            steps=steps,
            cfg=cfg,
            adv=adv,
        )
    if mode == "ltx23_t2v":
        return build_ltx23_t2v_prompt(
            prompt=prompt,
            negative=negative,
            width=width,
            height=height,
            length=length,
            fps=fps,
            seed=seed,
            steps=steps,
            cfg=cfg,
            checkpoint_name=str(profile_spec.get("checkpoint") or LTX23_DEV_CHECKPOINT),
            adv=adv,
        )
    if mode == "ltx23_i2v":
        return build_ltx23_i2v_prompt(
            prompt=prompt,
            negative=negative,
            image_name=KEYFRAME_UPLOAD_PLACEHOLDER,
            width=width,
            height=height,
            length=length,
            fps=fps,
            seed=seed,
            steps=steps,
            cfg=cfg,
            checkpoint_name=str(profile_spec.get("checkpoint") or LTX23_DEV_CHECKPOINT),
            adv=adv,
        )
    if mode in {"hunyuan15_t2v", "hunyuan15_i2v"}:
        default_model = HUNYUAN15_I2V_480_MODEL if mode == "hunyuan15_i2v" else HUNYUAN15_T2V_480_MODEL
        return build_hunyuan15_prompt(
            prompt=prompt,
            negative=negative,
            image_name=KEYFRAME_UPLOAD_PLACEHOLDER if mode == "hunyuan15_i2v" else "",
            width=width,
            height=height,
            length=length,
            fps=fps,
            seed=seed,
            steps=steps,
            cfg=cfg,
            model_name=str(profile_spec.get("model_name") or default_model),
            distilled=bool(profile_spec.get("distilled", True)),
            adv=adv,
        )
    if mode == "ltx25_t2v":
        return build_ltx25_t2v_prompt(
            prompt=prompt,
            negative=negative,
            width=width,
            height=height,
            length=length,
            fps=fps,
            seed=seed,
            steps=steps,
            cfg=cfg,
            model_name=str(profile_spec.get("model_name") or LTX25_DISTILLED_INT8_MODEL),
            text_encoder_name=str(profile_spec.get("text_encoder") or LTX25_TEXT_ENCODER),
            video_vae_diff_name=str(profile_spec.get("video_vae_diff") or LTX25_VIDEO_VAE_DIFF),
            video_vae_conv_name=str(profile_spec.get("video_vae_conv") or LTX25_VIDEO_VAE_CONV),
            audio_vae_name=str(profile_spec.get("audio_vae") or LTX25_AUDIO_VAE),
            spatial_upscaler_name=str(profile_spec.get("spatial_upscaler") or LTX25_SPATIAL_UPSCALER),
            duration_head_name=str(profile_spec.get("duration_head") or LTX25_DURATION_HEAD),
            adv=adv,
            unrestricted=unrestricted,
            trigger=trigger,
            auto_inject_trigger=auto_inject_trigger,
            auto_strip_negative=auto_strip_negative,
        )
    if mode == "ltx25_i2v":
        return build_ltx25_i2v_prompt(
            prompt=prompt,
            negative=negative,
            image_name=KEYFRAME_UPLOAD_PLACEHOLDER,
            end_image_name=KEYFRAME_UPLOAD_PLACEHOLDER if has_end_image else "",
            width=width,
            height=height,
            length=length,
            fps=fps,
            seed=seed,
            steps=steps,
            cfg=cfg,
            model_name=str(profile_spec.get("model_name") or LTX25_DISTILLED_INT8_MODEL),
            text_encoder_name=str(profile_spec.get("text_encoder") or LTX25_TEXT_ENCODER),
            video_vae_diff_name=str(profile_spec.get("video_vae_diff") or LTX25_VIDEO_VAE_DIFF),
            video_vae_conv_name=str(profile_spec.get("video_vae_conv") or LTX25_VIDEO_VAE_CONV),
            audio_vae_name=str(profile_spec.get("audio_vae") or LTX25_AUDIO_VAE),
            spatial_upscaler_name=str(profile_spec.get("spatial_upscaler") or LTX25_SPATIAL_UPSCALER),
            duration_head_name=str(profile_spec.get("duration_head") or LTX25_DURATION_HEAD),
            adv=adv,
            unrestricted=unrestricted,
            trigger=trigger,
            auto_inject_trigger=auto_inject_trigger,
            auto_strip_negative=auto_strip_negative,
        )
    if mode == "minimax_h3_r2v":
        return build_minimax_h3_reference_prompt(
            prompt=prompt,
            negative=negative,
            reference_images=[KEYFRAME_UPLOAD_PLACEHOLDER],
            reference_videos=[],
            reference_audios=[],
            width=width,
            height=height,
            length=length,
            fps=24,
            seed=seed,
            steps=steps,
            cfg=cfg,
            adv=adv,
            unrestricted=unrestricted,
            trigger=trigger,
            auto_inject_trigger=auto_inject_trigger,
            auto_strip_negative=auto_strip_negative,
        )
    if mode in {"minimax_h3_t2v", "minimax_h3_i2v"}:
        return build_minimax_h3_prompt(
            prompt=prompt,
            negative=negative,
            image_name=KEYFRAME_UPLOAD_PLACEHOLDER if mode == "minimax_h3_i2v" else "",
            end_image_name=KEYFRAME_UPLOAD_PLACEHOLDER if has_end_image else "",
            width=width,
            height=height,
            length=length,
            fps=24,
            seed=seed,
            steps=steps,
            cfg=cfg,
            adv=adv,
            unrestricted=unrestricted,
            trigger=trigger,
            auto_inject_trigger=auto_inject_trigger,
            auto_strip_negative=auto_strip_negative,
        )
    if mode == "rife_2x":
        return build_rife_prompt(video_name="sample.mp4", fps=fps, multiplier=rife_multiplier, adv=adv)
    if mode == "upscale_2x":
        return build_video_upscale_prompt(video_name="sample.mp4", fps=fps, model_name=upscale_model, adv=adv)
    if mode == "upscale_seedvr2":
        return build_seedvr2_upscale_prompt(
            video_name="sample.mp4",
            fps=fps,
            seed=seed,
            model_name=upscale_model,
            scale=upscale_scale,
            adv=adv,
        )
    return None


def validate_graph(prompt: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not any(item.get("class_type") in {"SaveVideo", "VHS_VideoCombine", "SaveImage"} for item in prompt.values()):
        errors.append("缺少输出节点")
    for node_id, item in prompt.items():
        inputs = item.get("inputs", {})
        for key, value in inputs.items():
            if (
                isinstance(value, list)
                and len(value) == 2
                and isinstance(value[0], str)
                and isinstance(value[1], int)
                and value[0] not in prompt
            ):
                errors.append(f"{node_id}.{key} 连接到不存在的节点 {value[0]}")
    return errors


def graph_node_schema_errors(
    prompt: dict[str, Any],
    object_info: dict[str, Any] | None,
) -> list[str]:
    if not object_info:
        return []
    errors: list[str] = []
    for node_id, item in prompt.items():
        class_type = str(item.get("class_type") or "")
        node_info = object_info.get(class_type)
        if not isinstance(node_info, dict):
            continue
        schema = node_info.get("input") or {}
        required = dict(schema.get("required") or {})
        optional = dict(schema.get("optional") or {})
        hidden = schema.get("hidden") or {}
        if not isinstance(required, dict) or not isinstance(optional, dict):
            continue
        inputs = item.get("inputs") or {}
        if not isinstance(inputs, dict):
            errors.append(f"节点 {node_id}（{class_type}）inputs 不是对象")
            continue
        dynamic_prefixes: dict[str, tuple[int, set[str]]] = {}
        dynamic_combo_choices: dict[str, set[str]] = {}
        pending_descriptors = [(name, descriptor, 0) for name, descriptor in {**required, **optional}.items()]
        for input_name, descriptor, depth in pending_descriptors:
            if not isinstance(descriptor, (list, tuple)) or len(descriptor) < 2:
                continue
            metadata = descriptor[1] if isinstance(descriptor[1], dict) else {}
            if descriptor[0] == "COMFY_DYNAMICCOMBO_V3":
                dynamic_combo_choices[str(input_name)] = {
                    str(option.get("key"))
                    for option in (metadata.get("options") or [])
                    if isinstance(option, dict) and str(option.get("key") or "")
                }
                selected = next((option for option in metadata.get("options", [])
                                 if isinstance(option, dict) and option.get("key") == inputs.get(input_name)), {})
                child_schema = selected.get("inputs") or {}
                for section, target in (("required", required), ("optional", optional)):
                    for child, child_descriptor in (child_schema.get(section) or {}).items():
                        child_name = f"{input_name}.{child}"
                        target[child_name] = child_descriptor
                        if depth < 8:
                            pending_descriptors.append((child_name, child_descriptor, depth + 1))
                continue
            if descriptor[0] != "COMFY_AUTOGROW_V3":
                continue
            template = metadata.get("template") if isinstance(metadata.get("template"), dict) else {}
            minimum = max(0, int(template.get("min") or 0))
            allowed = {str(name) for name in (template.get("names") or []) if str(name)}
            # H3 references use optional TemplatePrefix slots; Qwen uses TemplateNames.
            if "prefix" in template:
                maximum = max(0, min(100, int(template.get("max") or 0)))
                allowed = {f"{template['prefix']}{index}" for index in range(maximum)}
            dynamic_prefixes[str(input_name)] = (minimum, allowed)
        missing = sorted(
            str(name)
            for name in required
            if name not in inputs
            and not (
                str(name) in dynamic_prefixes
                and len([key for key in inputs if str(key).startswith(f"{name}.")]) >= dynamic_prefixes[str(name)][0]
            )
        )
        if missing:
            errors.append(f"节点 {node_id}（{class_type}）缺少必填输入：{', '.join(missing)}")
        for input_name, choices in dynamic_combo_choices.items():
            if input_name not in inputs or not choices:
                continue
            value = inputs[input_name]
            if not isinstance(value, str) or value not in choices:
                errors.append(
                    f"节点 {node_id}（{class_type}）动态选项 {input_name} 无效："
                    f"应为 {', '.join(sorted(choices))} 之一"
                )
        valid_names = set(required) | set(optional)
        if isinstance(hidden, dict):
            valid_names |= set(hidden)
        # Some custom nodes expose format-dependent widgets inside an input's
        # schema metadata instead of the top-level required/optional maps.
        for input_name, descriptor in required.items():
            if not isinstance(descriptor, (list, tuple)) or len(descriptor) < 2:
                continue
            metadata = descriptor[1]
            if not isinstance(metadata, dict):
                continue
            formats = metadata.get("formats")
            selected_format = inputs.get(input_name)
            if not isinstance(formats, dict) or not isinstance(selected_format, str):
                continue
            dynamic_widgets = formats.get(selected_format) or []
            for widget in dynamic_widgets:
                if isinstance(widget, (list, tuple)) and widget and isinstance(widget[0], str):
                    valid_names.add(widget[0])
        unknown: list[str] = []
        for name in inputs:
            name_text = str(name)
            if name in valid_names:
                continue
            matched_dynamic = False
            for prefix, (_minimum, allowed) in dynamic_prefixes.items():
                if not name_text.startswith(f"{prefix}."):
                    continue
                child_name = name_text[len(prefix) + 1 :]
                if child_name in allowed:
                    matched_dynamic = True
                    break
            if not matched_dynamic:
                unknown.append(name_text)
        unknown.sort()
        if unknown:
            errors.append(f"节点 {node_id}（{class_type}）包含当前版本不支持的输入：{', '.join(unknown)}")
    return errors


def graph_class_types(prompt: dict[str, Any]) -> list[str]:
    return sorted({str(item.get("class_type", "")) for item in prompt.values() if item.get("class_type")})


async def comfy_node_availability(prompt: dict[str, Any]) -> dict[str, Any]:
    class_types = graph_class_types(prompt)
    try:
        object_info = await get_comfy_object_info()
    except HTTPException as exc:
        return {
            "connected": False,
            "missing": class_types,
            "error": str(exc.detail),
        }
    missing = [name for name in class_types if name not in object_info]
    return {
        "connected": True,
        "missing": missing,
        "error": "",
    }


def media_url(item: dict[str, Any]) -> str:
    filename = item.get("filename", "")
    subfolder = item.get("subfolder", "")
    file_type = item.get("type", "output")
    return (
        f"/api/view?filename={quote(filename)}"
        f"&subfolder={quote(subfolder)}"
        f"&type={quote(file_type)}"
    )


def extract_media(history_item: dict[str, Any]) -> list[dict[str, Any]]:
    media: list[dict[str, Any]] = []
    outputs = history_item.get("outputs", {})
    for node_output in outputs.values():
        for key in ("videos", "gifs", "images"):
            for item in node_output.get(key, []) or []:
                filename = item.get("filename")
                if not filename:
                    continue
                suffix = Path(filename).suffix.lower()
                kind = "video" if suffix in VIDEO_EXTENSIONS else "image"
                media.append(
                    {
                        "kind": kind,
                        "filename": filename,
                        "subfolder": item.get("subfolder", ""),
                        "type": item.get("type", "output"),
                        "url": media_url(item),
                    }
                )
    return media


def safe_media_path(filename: str, subfolder: str, file_type: str, paths: dict[str, Any] | None = None) -> Path:
    paths = paths or configured_comfy_paths()
    roots = {
        "input": Path(paths["input_dir"]),
        "output": Path(paths["output_dir"]),
        "temp": Path(paths["temp_dir"]),
    }
    root = roots.get(file_type)
    if root is None:
        raise HTTPException(status_code=400, detail="未知文件类型")

    base = root.resolve()
    candidate = (root / subfolder / filename).resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        raise HTTPException(status_code=400, detail="文件路径不安全")
    if not candidate.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    return candidate


def input_media_path(relative_name: str, paths: dict[str, Any] | None = None) -> Path:
    paths = paths or configured_comfy_paths()
    normalized = relative_name.replace("\\", "/")
    relative = Path(normalized)
    if relative.is_absolute() or ".." in relative.parts:
        raise HTTPException(status_code=400, detail="输入文件路径不安全")

    input_dir = Path(paths["input_dir"])
    base = input_dir.resolve()
    candidate = (input_dir / relative).resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        raise HTTPException(status_code=400, detail="输入文件路径不安全")
    if not candidate.exists():
        raise HTTPException(status_code=404, detail="输入文件不存在")
    return candidate


def keyframe_requirement_errors(*, mode: str, has_upload: bool) -> list[str]:
    if mode not in REQUIRED_IMAGE_WORKFLOW_MODES or has_upload:
        return []
    return [
        "当前选择的是 I2V/TI2V 图生视频模型，需要你上传关键帧图片。"
        "平台不会使用内置示例图；请上传 PNG/JPG，或切换到名称中带 T2V 的文字生视频模型。"
    ]


def output_media_item(path: Path, paths: dict[str, Any] | None = None) -> dict[str, Any]:
    paths = paths or configured_comfy_paths()
    output_base = Path(paths["output_dir"]).resolve()
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(output_base)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="输出文件不在 ComfyUI output 目录") from exc

    subfolder = "" if relative.parent == Path(".") else str(relative.parent).replace("\\", "/")
    item = {
        "filename": relative.name,
        "subfolder": subfolder,
        "type": "output",
    }
    return {
        "kind": "video" if resolved.suffix.lower() in VIDEO_EXTENSIONS else "image",
        **item,
        "url": media_url(item),
    }


FFMPEG_INSTALL_HINT = (
    "请重新运行 START_WORKFLOW 启动器安装前端依赖，或手动安装 ffmpeg；"
    "Windows 可用 winget install Gyan.FFmpeg，macOS 可用 brew install ffmpeg。"
)


def ffmpeg_candidates() -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    env_path = os.environ.get("FFMPEG_PATH")
    if env_path:
        candidates.append(("FFMPEG_PATH", env_path.strip().strip('"')))
    system_path = shutil.which("ffmpeg")
    if system_path:
        candidates.append(("system", system_path))
    try:
        from imageio_ffmpeg import get_ffmpeg_exe

        candidates.append(("imageio-ffmpeg", get_ffmpeg_exe()))
    except Exception:
        pass
    bundled_dirs = [
        WORKSPACE_DIR / ".venv" / "Lib" / "site-packages" / "imageio_ffmpeg" / "binaries",
        WORKSPACE_DIR / "ComfyUI" / ".venv" / "Lib" / "site-packages" / "imageio_ffmpeg" / "binaries",
        Path(sys.prefix) / "Lib" / "site-packages" / "imageio_ffmpeg" / "binaries",
    ]
    for environment_root in (WORKSPACE_DIR / ".venv", WORKSPACE_DIR / "ComfyUI" / ".venv", Path(sys.prefix)):
        bundled_dirs.extend(environment_root.glob("lib/python*/site-packages/imageio_ffmpeg/binaries"))
    for bundled_dir in bundled_dirs:
        if not bundled_dir.is_dir():
            continue
        for executable in sorted(bundled_dir.glob("ffmpeg*")):
            if executable.is_file():
                candidates.append(("project imageio-ffmpeg", str(executable)))
    unique: list[tuple[str, str]] = []
    seen: set[str] = set()
    for source, path in candidates:
        if path and path not in seen:
            unique.append((source, path))
            seen.add(path)
    return unique


def ffmpeg_probe() -> dict[str, Any]:
    errors: list[str] = []
    for source, path in ffmpeg_candidates():
        try:
            result = subprocess.run(
                [path, "-version"],
                capture_output=True,
                text=True,
                timeout=10,
                **_hidden_popen_options(),
            )
        except Exception as exc:
            errors.append(f"{source}: {exc}")
            continue
        if result.returncode == 0:
            version = (result.stdout.splitlines() or ["ffmpeg"])[0]
            return {
                "name": "ffmpeg",
                "ok": True,
                "path": path,
                "source": source,
                "version": version,
                "message": f"已检测到 {source} ffmpeg。",
                "install_hint": "",
                "required": True,
            }
        errors.append(f"{source}: exit {result.returncode} {(result.stderr or result.stdout).strip()[:240]}")
    return {
        "name": "ffmpeg",
        "ok": False,
        "path": "",
        "source": "",
        "version": "",
        "message": "未找到可执行的 ffmpeg，闪烁修复与成片拼接不可用。" if not errors else "ffmpeg 不可执行：" + "；".join(errors[:3]),
        "install_hint": FFMPEG_INSTALL_HINT,
        "required": True,
    }


def find_ffmpeg() -> str:
    probe = ffmpeg_probe()
    if probe.get("ok") and probe.get("path"):
        return str(probe["path"])
    raise HTTPException(status_code=503, detail=probe.get("message") or "未找到 ffmpeg，无法执行本地视频处理")


def ffmpeg_filter_check(filter_name: str, probe: dict[str, Any] | None = None) -> dict[str, Any]:
    probe = probe or ffmpeg_probe()
    path = str(probe.get("path") or "")
    if not probe.get("ok") or not path:
        return {
            "name": f"ffmpeg:{filter_name}",
            "ok": False,
            "path": path,
            "source": probe.get("source", ""),
            "message": probe.get("message") or f"无法检测 {filter_name} 滤镜。",
            "install_hint": probe.get("install_hint") or FFMPEG_INSTALL_HINT,
            "required": True,
        }
    try:
        result = subprocess.run(
            [path, "-hide_banner", "-filters"],
            capture_output=True,
            check=True,
            text=True,
            timeout=20,
            **_hidden_popen_options(),
        )
        ok = filter_name in result.stdout
    except Exception as exc:
        return {
            "name": f"ffmpeg:{filter_name}",
            "ok": False,
            "path": path,
            "source": probe.get("source", ""),
            "message": f"检测 {filter_name} 滤镜失败：{exc}",
            "install_hint": FFMPEG_INSTALL_HINT,
            "required": True,
        }
    return {
        "name": f"ffmpeg:{filter_name}",
        "ok": ok,
        "path": path,
        "source": probe.get("source", ""),
        "message": f"已检测到 {filter_name} 滤镜。" if ok else f"当前 ffmpeg 缺少 {filter_name} 滤镜。",
        "install_hint": "" if ok else FFMPEG_INSTALL_HINT,
        "required": True,
    }


def ffmpeg_has_filter(filter_name: str) -> bool:
    return bool(ffmpeg_filter_check(filter_name).get("ok"))


def ffmpeg_tool_checks() -> list[dict[str, Any]]:
    probe = ffmpeg_probe()
    return [
        probe,
        ffmpeg_filter_check("deflicker", probe),
        ffmpeg_filter_check("hqdn3d", probe),
    ]


ASSET_METADATA = {
    str(item.get("id") or ""): {"label": item.get("label"), "step": item.get("step")}
    for item in INSTALL_MODEL_FILES
}

CUSTOM_NODE_METADATA = {
    str(item.get("id") or ""): {"label": item.get("name")}
    for item in INSTALL_CUSTOM_NODE_REPOS
}


def workflow_asset_manifest(base_dir: Path | None = None) -> list[dict[str, Any]]:
    base_dir = (base_dir or BASE_DIR).expanduser().resolve()
    items: list[dict[str, Any]] = []
    for source in INSTALL_MODEL_FILES:
        item_id = str(source.get("id") or "")
        if not item_id:
            continue
        meta = ASSET_METADATA.get(item_id, {})
        items.append(
            {
                "id": item_id,
                "label": meta.get("label") or source.get("name") or item_id,
                "step": meta.get("step") or "工作流资产",
                "path": base_dir / str(source["dest"]),
                "bytes": int(source["bytes"]),
                "dest": str(source["dest"]),
                "name": str(source.get("name") or Path(str(source["dest"])).name),
                "url": effective_download_url(str(source.get("url") or "")),
                "alternatives": [
                    {
                        **alternative,
                        "path": base_dir / str(alternative.get("dest") or alternative.get("name") or ""),
                    }
                    for alternative in (source.get("alternatives") or [])
                    if alternative.get("dest") or alternative.get("name")
                ],
                "archive": str(source.get("archive") or ""),
                "extract_to": str(source.get("extract_to") or ""),
                "required_paths": [base_dir / str(path) for path in source.get("required_paths") or []],
                "installable": True,
            }
        )
    return items


def custom_node_manifest(base_dir: Path | None = None) -> list[dict[str, Any]]:
    base_dir = (base_dir or BASE_DIR).expanduser().resolve()
    items: list[dict[str, Any]] = []
    for source in INSTALL_CUSTOM_NODE_REPOS:
        item_id = str(source.get("id") or "")
        if not item_id:
            continue
        meta = CUSTOM_NODE_METADATA.get(item_id, {})
        items.append(
            {
                "id": item_id,
                "label": meta.get("label") or source.get("name") or item_id,
                "path": base_dir / str(source["dest"]),
                "url": str(source.get("url") or ""),
                "installable": True,
            }
        )
    return items

def path_label(path: Path, base_dir: Path | None = None) -> str:
    base_dir = (base_dir or BASE_DIR).expanduser().resolve()
    try:
        return str(path.resolve().relative_to(base_dir)).replace("\\", "/")
    except ValueError:
        return str(path)


def collect_asset_checks(base_dir: Path | None = None) -> list[dict[str, Any]]:
    base_dir = (base_dir or BASE_DIR).expanduser().resolve()
    checks: list[dict[str, Any]] = []
    for item in workflow_asset_manifest(base_dir):
        primary_path = item["path"]
        primary_expected = item.get("bytes")
        matched_alternative = next(
            (
                alternative
                for alternative in (item.get("alternatives") or [])
                if Path(alternative["path"]).is_file()
                and (
                    not alternative.get("bytes")
                    or Path(alternative["path"]).stat().st_size == int(alternative["bytes"])
                )
            ),
            None,
        )
        path = Path(matched_alternative["path"]) if matched_alternative else primary_path
        expected = int(matched_alternative["bytes"]) if matched_alternative and matched_alternative.get("bytes") else primary_expected
        partial = path.with_name(path.name + ".part")
        exists = path.exists()
        size = path.stat().st_size if exists else 0
        partial_exists = partial.exists()
        partial_size = partial.stat().st_size if partial_exists else 0
        file_size_ok = exists and (not expected or size == expected)
        required_paths = [Path(required) for required in item.get("required_paths") or []]
        missing_required_paths = [required for required in required_paths if not required.is_file() or required.stat().st_size <= 0]
        extracted_ok = not missing_required_paths
        size_ok = file_size_ok and extracted_ok
        local_candidate = None
        local_available = False
        if expected and not file_size_ok and INSTALL_FIND_LOCAL_ASSET_CANDIDATE:
            try:
                local_candidate = INSTALL_FIND_LOCAL_ASSET_CANDIDATE(
                    {
                        "id": item.get("id"),
                        "name": item.get("name") or path.name,
                        "dest": item.get("dest") or path.name,
                        "bytes": expected,
                    },
                    dest=primary_path,
                    base_dir=base_dir,
                    recursive=False,
                )
                local_available = bool(local_candidate)
            except Exception:
                local_candidate = None
                local_available = False
        remaining = None
        if expected:
            if file_size_ok:
                remaining = 0
            elif local_available:
                remaining = 0
            elif partial_exists:
                remaining = max(0, int(expected) - min(partial_size, int(expected)))
            elif exists:
                remaining = max(0, int(expected) - min(size, int(expected)))
            else:
                remaining = int(expected)
        if not exists and partial_exists and expected:
            if partial_size == int(expected):
                reason = f"已完整下载为 .part：{partial_size} / {expected} bytes；点击安装会自动转正"
            elif partial_size > int(expected):
                reason = f".part 大于预期：{partial_size} / {expected} bytes；请删除该 .part 后重试"
            else:
                reason = f"已下载 {partial_size} / {expected} bytes，可断点续传"
        elif file_size_ok and not extracted_ok:
            reason = f"压缩包已下载，仍需解压校验 {len(missing_required_paths)} 个文件；再次安装会自动完成"
        elif local_available:
            reason = f"本地缓存可用：{local_candidate}；点击安装会复用本地文件"
        elif not exists:
            reason = "缺失"
        elif expected and size != expected:
            reason = f"大小不一致：{size} / {expected} bytes；重新安装会转为断点续传"
        elif matched_alternative:
            reason = f"已就绪（兼容资产：{path.name}）"
        else:
            reason = "已就绪"
        checks.append(
            {
                "id": item["id"],
                "name": item.get("name") or primary_path.name,
                "label": item["label"],
                "step": item["step"],
                "path": str(path),
                "relative_path": path_label(path, base_dir),
                "ok": bool(size_ok),
                "exists": exists,
                "size_gb": round(size / 1024**3, 2) if exists else 0,
                "partial_exists": partial_exists,
                "partial_gb": round(partial_size / 1024**3, 2) if partial_exists else 0,
                "downloaded_bytes": int(expected) if file_size_ok and expected else int(min(partial_size or size, int(expected or 0))),
                "expected_bytes": int(expected) if expected else 0,
                "remaining_bytes": int(remaining) if remaining is not None else None,
                "remaining_gb": round(remaining / 1024**3, 2) if remaining is not None else None,
                "expected_gb": round(expected / 1024**3, 2) if expected else None,
                "url": item.get("url") or "",
                "download_host": urlparse(str(item.get("url") or "")).hostname or "",
                "installable": bool(item.get("installable")),
                "local_available": local_available,
                "local_path": str(local_candidate) if local_candidate else "",
                "alternative_used": bool(matched_alternative),
                "archive": item.get("archive") or "",
                "extracted_ok": extracted_ok,
                "missing_required_paths": [path_label(path, base_dir) for path in missing_required_paths],
                "primary_path": str(primary_path),
                "reason": reason,
            }
        )
    return checks


def collect_runtime_asset_checks(active_base_dir: Path) -> list[dict[str, Any]]:
    """Merge the active Comfy base with the platform's registered external model root."""
    active_base_dir = active_base_dir.expanduser().resolve()
    roots = [active_base_dir]
    saved = saved_model_download_dir()
    if saved:
        try:
            saved_root = Path(saved).expanduser().resolve()
            if os.path.normcase(str(saved_root)) != os.path.normcase(str(active_base_dir)):
                roots.append(saved_root)
        except OSError:
            pass
    candidates_by_id: dict[str, list[dict[str, Any]]] = {}
    for root in roots:
        for item in collect_asset_checks(root):
            candidate = dict(item)
            candidate["storage_root"] = str(root)
            candidates_by_id.setdefault(str(item.get("id") or ""), []).append(candidate)

    merged: list[dict[str, Any]] = []
    for candidates in candidates_by_id.values():
        selected = max(
            candidates,
            key=lambda item: (
                bool(item.get("ok")),
                bool(item.get("local_available")),
                int(item.get("downloaded_bytes") or 0),
            ),
        )
        merged.append(selected)
    return merged


def collect_custom_node_checks(base_dir: Path | None = None) -> list[dict[str, Any]]:
    base_dir = (base_dir or BASE_DIR).expanduser().resolve()
    checks: list[dict[str, Any]] = []
    for item in custom_node_manifest(base_dir):
        path = item["path"]
        ok = path.exists() and path.is_dir()
        checks.append(
            {
                "id": item["id"],
                "label": item["label"],
                "path": str(path),
                "relative_path": path_label(path, base_dir),
                "url": item.get("url") or "",
                "download_host": urlparse(str(item.get("url") or "")).hostname or "",
                "ok": ok,
                "installable": bool(item.get("installable")),
                "reason": "已就绪" if ok else "缺失",
            }
        )
    return checks


def catalog_file_index(base_dir: Path, *, force: bool = False) -> dict[str, Path]:
    base_dir = base_dir.expanduser().resolve()
    cache_key = str(base_dir).lower()
    now = time.time()
    with CATALOG_FILE_INDEX_LOCK:
        cached = CATALOG_FILE_INDEX_CACHE.get(cache_key)
        if (
            not force
            and cached
            and now - float(cached.get("checked_at") or 0) < CATALOG_FILE_INDEX_TTL
        ):
            return cached["files"]

    index: dict[str, Path] = {}
    ignored_dirs = {".git", ".venv", "__pycache__", "node_modules", ".pytest_cache", ".cache"}
    for root in (base_dir / "models",):
        if not root.is_dir():
            continue
        try:
            for current, directories, files in os.walk(root):
                directories[:] = [name for name in directories if name not in ignored_dirs]
                current_path = Path(current)
                for file_name in files:
                    if file_name.endswith(".part"):
                        continue
                    index.setdefault(file_name.lower(), current_path / file_name)
        except (OSError, PermissionError):
            continue

    with CATALOG_FILE_INDEX_LOCK:
        CATALOG_FILE_INDEX_CACHE[cache_key] = {"files": index, "checked_at": time.time()}
    return index


def find_catalog_file(base_dir: Path, name: str) -> Path | None:
    if not name:
        return None
    base_dir = base_dir.expanduser().resolve()
    roots = [base_dir / "models", base_dir / "custom_nodes", base_dir / "input"]
    common_dirs = [
        "diffusion_models",
        "unet",
        "checkpoints",
        "loras",
        "vae",
        "text_encoders",
        "clip",
        "clip_vision",
        "upscale_models",
    ]
    for root in roots:
        direct = root / name
        if direct.is_file():
            return direct
    for folder in common_dirs:
        direct = base_dir / "models" / folder / name
        if direct.is_file():
            return direct
    candidate = catalog_file_index(base_dir).get(name.lower())
    return candidate if candidate and candidate.is_file() else None


def catalog_model_sync(
    *,
    base_dir: Path,
    assets: list[dict[str, Any]],
    selected_model_id: str | None = None,
) -> dict[str, Any]:
    selected_id = selected_model_id or saved_model_catalog_id()
    item = catalog_item_by_id(selected_id)
    if not item:
        return {
            "selected_model_id": "",
            "selected_model": {},
            "level": "warn",
            "message": "当前没有可同步的模型目录选择。",
            "found_files": [],
            "missing_files": [],
            "diagnostics": [],
        }

    asset_by_name = {str(asset.get("name") or Path(str(asset.get("path") or "")).name): asset for asset in assets}
    found_files: list[dict[str, Any]] = []
    missing_files: list[str] = []
    for name in item.get("files") or []:
        file_name = str(name)
        asset = asset_by_name.get(file_name)
        if asset:
            if asset.get("ok"):
                found_files.append({"name": file_name, "path": asset.get("relative_path") or asset.get("path"), "source": "installer"})
            else:
                missing_files.append(file_name)
            continue
        candidate = find_catalog_file(base_dir, file_name)
        if candidate:
            found_files.append({"name": file_name, "path": path_label(candidate, base_dir), "source": "filesystem"})
        else:
            missing_files.append(file_name)

    platform_support = str(item.get("platform_support") or "manual")
    native = platform_support == "native"
    cloud_api = platform_support == "cloud_api"
    install_profile = str(item.get("default_install_profile") or "manual")
    profile_info = CATALOG_INSTALL_PROFILES.get(install_profile) or {}
    if native and missing_files:
        level = "blocked"
    elif cloud_api:
        level = "ok" if fal_api_key() else "warn"
    elif missing_files or platform_support != "native":
        level = "warn"
    else:
        level = "ok"

    file_message = (
        f"已找到 {len(found_files)} 个，未确认 {len(missing_files)} 个：{', '.join(missing_files[:6])}"
        if missing_files
        else f"已找到 {len(found_files)} 个关联文件。"
    )
    workflow_support = str(item.get("workflow_support") or "")
    diagnostics = [
        {
            "level": level,
            "title": f"当前关注模型：{item.get('label') or selected_id}",
            "message": (
                f"{item.get('family') or ''} | {item.get('quantization') or ''} | "
                f"{item.get('vram_hint') or ''}。{workflow_support}"
            ),
        },
        {
            "level": "ok" if not missing_files else ("blocked" if native else "warn"),
            "title": "关注模型文件同步",
            "message": file_message,
        },
    ]
    selected_model = dict(item)
    generation_target = catalog_generation_target(item)
    selected_model.update(
        {
            "install_profile": install_profile,
            "install_profile_label": profile_info.get("label") or install_profile,
            "one_click_install": bool(profile_info.get("installable")),
            "external_requirement": profile_info.get("external_requirement") or "",
            "required_comfy_version": profile_info.get("required_comfy_version") or "",
            "generation_target": generation_target,
            "generation_target_label": {
                "native": "本页可生成",
                "cloud_api": "本页云端生成",
                "comfy_template": "只下载、去 ComfyUI 跑模板",
                "catalog_only": "仅目录参考",
            }.get(generation_target, "仅目录参考"),
            "can_generate_here": generation_target in {"native", "cloud_api"},
        }
    )
    return {
        "selected_model_id": selected_id,
        "selected_model": selected_model,
        "level": level,
        "message": file_message,
        "found_files": found_files,
        "missing_files": missing_files,
        "install_profile": install_profile,
        "install_profile_label": profile_info.get("label") or install_profile,
        "one_click_install": bool(profile_info.get("installable")),
        "platform_support": platform_support,
        "generation_target": generation_target,
        "can_generate_here": generation_target in {"native", "cloud_api"},
        "workflow_modes": item.get("workflow_modes") or {},
        "external_requirement": profile_info.get("external_requirement") or "",
        "diagnostics": diagnostics,
    }


def get_system_memory_gb() -> float | None:
    system_name = platform.system()
    try:
        if system_name == "Windows":
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            memory = MEMORYSTATUSEX()
            memory.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory))
            return round(memory.ullTotalPhys / 1024**3, 1)
        if system_name == "Darwin":
            result = subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                capture_output=True,
                check=True,
                text=True,
                timeout=5,
                **_hidden_popen_options(),
            )
            return round(int(result.stdout.strip()) / 1024**3, 1)
        meminfo = Path("/proc/meminfo")
        if meminfo.exists():
            for line in meminfo.read_text(encoding="utf-8", errors="ignore").splitlines():
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    return round(kb / 1024**2, 1)
    except Exception:
        return None
    return None


def collect_torch_hardware() -> dict[str, Any]:
    info: dict[str, Any] = {
        "available": False,
        "version": None,
        "cuda_available": False,
        "mps_available": False,
        "devices": [],
    }
    try:
        import torch

        info["available"] = True
        info["version"] = getattr(torch, "__version__", None)
        info["cuda_available"] = bool(torch.cuda.is_available())
        if info["cuda_available"]:
            for index in range(torch.cuda.device_count()):
                props = torch.cuda.get_device_properties(index)
                info["devices"].append(
                    {
                        "index": index,
                        "name": torch.cuda.get_device_name(index),
                        "type": "cuda",
                        "vram_total_gb": round(props.total_memory / 1024**3, 1),
                    }
                )
        mps_backend = getattr(getattr(torch, "backends", None), "mps", None)
        if mps_backend is not None:
            info["mps_available"] = bool(mps_backend.is_available())
    except Exception as exc:
        info["error"] = str(exc)
    return info


def run_text_command(command: list[str], timeout: int = 8) -> str:
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
        timeout=timeout,
        **_hidden_popen_options(),
    )
    return result.stdout.strip()


def mac_chip_tier(chip_name: str) -> str:
    value = chip_name.lower()
    if "ultra" in value:
        return "ultra"
    if "max" in value:
        return "max"
    if "pro" in value:
        return "pro"
    if value:
        return "base"
    return ""


def detect_mac_hardware() -> dict[str, Any]:
    info: dict[str, Any] = {
        "is_macos": platform.system() == "Darwin",
        "apple_silicon": False,
        "chip": "",
        "chip_tier": "",
        "unified_memory_gb": None,
        "machine_model": "",
        "machine_name": "",
        "mps_capable": False,
    }
    if not info["is_macos"]:
        return info

    machine = platform.machine()
    info["apple_silicon"] = machine == "arm64"
    try:
        info["chip"] = run_text_command(["sysctl", "-n", "machdep.cpu.brand_string"], timeout=5)
    except Exception:
        info["chip"] = platform.processor() or ""

    try:
        mem_bytes = int(run_text_command(["sysctl", "-n", "hw.memsize"], timeout=5))
        info["unified_memory_gb"] = round(mem_bytes / 1024**3, 1)
    except Exception:
        info["unified_memory_gb"] = get_system_memory_gb()

    try:
        raw = run_text_command(["system_profiler", "SPHardwareDataType", "-json"], timeout=12)
        payload = json.loads(raw)
        hardware_items = payload.get("SPHardwareDataType") or []
        if hardware_items:
            hardware = hardware_items[0]
            info["machine_model"] = hardware.get("machine_model", "") or ""
            info["machine_name"] = hardware.get("machine_name", "") or ""
            if hardware.get("chip_type"):
                info["chip"] = hardware.get("chip_type")
    except Exception:
        pass

    info["chip_tier"] = mac_chip_tier(str(info.get("chip") or ""))
    info["mps_capable"] = bool(info["apple_silicon"])
    return info


def probe_python_torch(python: Path) -> dict[str, Any]:
    probe: dict[str, Any] = {
        "python": str(python),
        "exists": python.exists(),
        "available": False,
        "cuda_available": False,
        "mps_built": False,
        "mps_available": False,
    }
    if not python.exists():
        return probe
    code = (
        "import json\n"
        "payload={'available': False, 'cuda_available': False, 'mps_built': False, 'mps_available': False}\n"
        "try:\n"
        " import torch\n"
        " payload['available']=True\n"
        " payload['version']=getattr(torch,'__version__',None)\n"
        " payload['cuda_available']=bool(torch.cuda.is_available())\n"
        " mps=getattr(getattr(torch,'backends',None),'mps',None)\n"
        " payload['mps_built']=bool(mps and mps.is_built())\n"
        " payload['mps_available']=bool(mps and mps.is_available())\n"
        "except Exception as exc:\n"
        " payload['error']=str(exc)\n"
        "print(json.dumps(payload))\n"
    )
    try:
        result = subprocess.run(
            [str(python), "-c", code],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            check=False,
            **_hidden_popen_options(),
        )
        if result.stdout.strip():
            probe.update(json.loads(result.stdout.strip().splitlines()[-1]))
        if result.returncode != 0 and result.stderr.strip():
            probe["error"] = result.stderr.strip()[-1000:]
    except Exception as exc:
        probe["error"] = str(exc)
    return probe


def comfy_torch_probe() -> dict[str, Any]:
    try:
        return probe_python_torch(comfy_venv_python())
    except Exception as exc:
        return {
            "python": str(COMFY_INSTALL_DIR),
            "exists": False,
            "available": False,
            "cuda_available": False,
            "mps_built": False,
            "mps_available": False,
            "error": str(exc),
        }


def comfy_devices_have_mps(devices: list[dict[str, Any]]) -> bool:
    for device in devices:
        text = f"{device.get('type', '')} {device.get('name', '')}".lower()
        if any(token in text for token in ("mps", "metal", "apple")):
            return True
    return False


def mac_video_tier(mac: dict[str, Any]) -> str:
    if not mac.get("is_macos"):
        return ""
    if not mac.get("apple_silicon"):
        return "mac_post_only"

    memory = float(mac.get("unified_memory_gb") or 0)
    chip_tier = str(mac.get("chip_tier") or "base")
    if memory < 12:
        tier = "mac_ltx_low"
    elif memory < 24:
        tier = "mac_ltx_low"
    elif memory < 32:
        tier = "mac_ltx_balanced"
    elif memory < 48:
        tier = "mac_ltx_quality"
    elif memory < 96:
        tier = "mac_wan5b_480p"
    else:
        tier = "mac_wan5b_720p_experimental"

    if chip_tier == "base" and tier not in {"mac_ltx_low", "mac_ltx_balanced"}:
        return "mac_ltx_balanced"
    if chip_tier == "pro" and tier in {"mac_wan5b_480p", "mac_wan5b_720p_experimental"}:
        return "mac_ltx_quality"
    return tier


def platform_strategy_for(
    *,
    mac: dict[str, Any],
    has_cuda: bool,
    has_mps_capability: bool,
) -> str:
    if mac.get("is_macos"):
        if mac.get("apple_silicon") and has_mps_capability:
            return "mac_mps"
        return "mac_post_only"
    if has_cuda:
        return "cuda_multi_model"
    return "post_only"


def summarize_comfy_devices(system_stats: dict[str, Any] | None) -> list[dict[str, Any]]:
    devices: list[dict[str, Any]] = []
    for index, device in enumerate((system_stats or {}).get("devices") or []):
        vram_total = device.get("vram_total") or device.get("total_memory") or 0
        vram_free = device.get("vram_free") or device.get("free_memory") or 0
        devices.append(
            {
                "index": index,
                "name": device.get("name") or f"Device {index}",
                "type": device.get("type") or device.get("device_type") or "",
                "vram_total_gb": round(vram_total / 1024**3, 1) if vram_total else None,
                "vram_free_gb": round(vram_free / 1024**3, 1) if vram_free else None,
            }
        )
    return devices


def detect_nvidia_smi_devices() -> list[dict[str, Any]]:
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return []
    try:
        result = subprocess.run(
            [
                nvidia_smi,
                "--query-gpu=name,memory.total,memory.free",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=True,
            **_hidden_popen_options(),
        )
    except Exception:
        return []
    devices: list[dict[str, Any]] = []
    for index, line in enumerate(result.stdout.splitlines()):
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 3:
            continue
        try:
            total_gb = round(float(parts[1]) / 1024, 1)
            free_gb = round(float(parts[2]) / 1024, 1)
        except ValueError:
            total_gb = 0
            free_gb = 0
        devices.append(
            {
                "index": index,
                "name": parts[0],
                "type": "cuda",
                "vram_total_gb": total_gb,
                "vram_free_gb": free_gb,
                "source": "nvidia-smi",
            }
        )
    return devices


def cached_hardware_probe(*, force: bool = False) -> dict[str, Any]:
    now = time.time()
    with HARDWARE_PROBE_LOCK:
        cached = HARDWARE_PROBE_CACHE.get("value")
        checked_at = float(HARDWARE_PROBE_CACHE.get("checked_at") or 0)
        if not force and isinstance(cached, dict) and now - checked_at < HARDWARE_PROBE_CACHE_TTL:
            return cached
        probes_disabled = str(os.environ.get("BEGINNER_FRONTEND_DISABLE_GPU_PROBES") or "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        disabled_probe = {
            "available": False,
            "cuda_available": False,
            "mps_available": False,
            "devices": [],
            "disabled": True,
            "reason": "BEGINNER_FRONTEND_DISABLE_GPU_PROBES",
        }
        value = {
            "torch": dict(disabled_probe) if probes_disabled else collect_torch_hardware(),
            "mac": detect_mac_hardware(),
            "comfy_torch": dict(disabled_probe) if probes_disabled else comfy_torch_probe(),
            "nvidia_smi_devices": [] if probes_disabled else detect_nvidia_smi_devices(),
            "system_memory_gb": get_system_memory_gb(),
            "gpu_probes_disabled": probes_disabled,
        }
        HARDWARE_PROBE_CACHE.update({"value": value, "checked_at": time.time()})
        return value


def build_hardware_summary(
    system_stats: dict[str, Any] | None,
    *,
    force_probe: bool = False,
) -> dict[str, Any]:
    probe = cached_hardware_probe(force=force_probe)
    torch_info = probe["torch"]
    mac_info = probe["mac"]
    comfy_torch = probe["comfy_torch"]
    comfy_devices = summarize_comfy_devices(system_stats)
    nvidia_smi_devices = probe["nvidia_smi_devices"]
    devices = comfy_devices or torch_info.get("devices") or nvidia_smi_devices or []
    max_vram = max((device.get("vram_total_gb") or 0 for device in devices), default=0)
    sum_vram = round(sum((device.get("vram_total_gb") or 0 for device in devices)), 1)
    has_cuda = bool(torch_info.get("cuda_available")) or any(
        "cuda" in str(device.get("type", "")).lower() or "nvidia" in str(device.get("name", "")).lower()
        for device in devices
    )
    comfy_reports_mps = comfy_devices_have_mps(comfy_devices)
    front_mps_ready = bool(torch_info.get("mps_available"))
    comfy_mps_ready = bool(comfy_torch.get("mps_available")) or comfy_reports_mps
    has_mps_capability = bool(mac_info.get("mps_capable") or front_mps_ready or comfy_mps_ready)
    has_mps = bool(front_mps_ready or comfy_mps_ready or mac_info.get("mps_capable"))
    accelerator = "cuda" if has_cuda else "mps" if has_mps else "cpu"
    platform_strategy = platform_strategy_for(
        mac=mac_info,
        has_cuda=has_cuda,
        has_mps_capability=has_mps_capability,
    )
    mac_tier = mac_video_tier(mac_info)
    return {
        "accelerator": accelerator,
        "platform_strategy": platform_strategy,
        "devices": devices,
        "nvidia_smi_devices": nvidia_smi_devices,
        "gpu_count": len(devices),
        "max_vram_gb": round(max_vram, 1),
        "sum_vram_gb": sum_vram,
        "system_memory_gb": probe["system_memory_gb"],
        "torch": torch_info,
        "front_torch_mps_ready": front_mps_ready,
        "comfy_torch": comfy_torch,
        "comfy_torch_mps_ready": comfy_mps_ready,
        "mac": mac_info,
        "mac_video_tier": mac_tier,
        "gpu_probes_disabled": bool(probe.get("gpu_probes_disabled")),
    }


def collect_node_checks(object_info: dict[str, Any] | None) -> list[dict[str, Any]]:
    required_nodes = [
        "SaveVideo",
        "CreateVideo",
        "LoadImage",
        "UNETLoader",
        "CLIPLoader",
        "DualCLIPLoader",
        "CLIPVisionLoader",
        "CLIPVisionEncode",
        "VAELoader",
        "CLIPTextEncode",
        "WanImageToVideo",
        "Wan22ImageToVideoLatent",
        "EmptyHunyuanLatentVideo",
        "EmptyHunyuanVideo15Latent",
        "HunyuanVideo15ImageToVideo",
        "MiniMaxH3ImageToVideo",
        "MiniMaxH3SigmaShift",
        "MiniMaxH3FunControlNetApply",
        "MinimaxH3LatentUpscaler3D",
        "ModelAttentionBackend",
        "Canny",
        "ImageToMask",
        "ImageCompositeMasked",
        "SpectrumApplyMiniMaxH3",
        "KSampler",
        "KSamplerAdvanced",
        "VAEDecodeTiled",
        "LoraLoaderModelOnly",
        "ModelSamplingSD3",
        "CheckpointLoaderSimple",
        "EmptyLTXVLatentVideo",
        "LTXVConditioning",
        "LTXVScheduler",
        "LTXVImgToVideo",
        "LTXVImgToVideoInplace",
        "LTXVAddGuide",
        "LTXVPreprocess",
        "SamplerCustom",
        "KSamplerSelect",
        "VAEDecode",
        "LTXAVTextEncoderLoader",
        "LTXVAudioVAELoader",
        "LTXVAudioVAEDecode",
        "LTXVEmptyLatentAudio",
        "LTXVConcatAVLatent",
        "LTXVSeparateAVLatent",
        "LTXVCropGuides",
        "RandomNoise",
        "ManualSigmas",
        "BasicScheduler",
        "BasicGuider",
        "CFGGuider",
        "LTXVDualCFGGuider",
        "SamplerEulerAncestral",
        "SamplerCustomAdvanced",
        "VAEDecodeAudio",
        "LatentUpscaleModelLoader",
        "LTXVLatentUpsampler",
        "ModelPatchLoader",
        "LTXVDurationPredictor",
        "VHS_LoadVideo",
        "VHS_VideoCombine",
        "RIFE VFI",
        "UpscaleModelLoader",
        "ImageUpscaleWithModel",
        "ImageCrop",
        "ImageScaleBy",
        "VAEEncodeTiled",
        "SeedVR2Preprocess",
        "SeedVR2TemporalChunk",
        "SeedVR2Conditioning",
        "SeedVR2TemporalMerge",
        "SeedVR2PostProcessing",
    ]
    if object_info is None:
        return [{"name": name, "ok": False, "reason": "ComfyUI 未连接"} for name in required_nodes]
    return [{"name": name, "ok": name in object_info, "reason": "已加载" if name in object_info else "缺少",
             **({"options": node_input_options(object_info, name, "attention")} if name == "ModelAttentionBackend" else {})}
            for name in required_nodes]


def node_input_options(object_info: dict[str, Any] | None, node_name: str, input_name: str) -> list[str]:
    if not object_info or node_name not in object_info:
        return []
    node_info = object_info.get(node_name) or {}
    value = ((node_info.get("input") or {}).get("required") or {}).get(input_name)
    if value is None:
        value = ((node_info.get("input") or {}).get("optional") or {}).get(input_name)

    if isinstance(value, (list, tuple)):
        if value and isinstance(value[0], (list, tuple)):
            return [str(item) for item in value[0]]
        if len(value) > 1 and isinstance(value[1], dict) and isinstance(value[1].get("options"), (list, tuple)):
            return [str(item) for item in value[1]["options"]]
        if value and all(not isinstance(item, (dict, list, tuple)) for item in value):
            return [str(item) for item in value]
    if isinstance(value, dict) and isinstance(value.get("options"), (list, tuple)):
        return [str(item) for item in value["options"]]
    return []


def node_input_option_values(object_info: dict[str, Any] | None, node_name: str, input_name: str) -> list[Any]:
    if not object_info or node_name not in object_info:
        return []
    node_info = object_info.get(node_name) or {}
    value = ((node_info.get("input") or {}).get("required") or {}).get(input_name)
    if value is None:
        value = ((node_info.get("input") or {}).get("optional") or {}).get(input_name)
    if isinstance(value, (list, tuple)):
        if value and isinstance(value[0], (list, tuple)):
            return list(value[0])
        if len(value) > 1 and isinstance(value[1], dict) and isinstance(value[1].get("options"), (list, tuple)):
            return list(value[1]["options"])
    if isinstance(value, dict) and isinstance(value.get("options"), (list, tuple)):
        return list(value["options"])
    return []


def node_input_default(
    object_info: dict[str, Any] | None,
    node_name: str,
    input_name: str,
    fallback: Any = None,
) -> Any:
    if not object_info or node_name not in object_info:
        return fallback
    node_info = object_info.get(node_name) or {}
    descriptor = ((node_info.get("input") or {}).get("required") or {}).get(input_name)
    if descriptor is None:
        descriptor = ((node_info.get("input") or {}).get("optional") or {}).get(input_name)
    if isinstance(descriptor, (list, tuple)) and len(descriptor) > 1 and isinstance(descriptor[1], dict):
        return descriptor[1].get("default", fallback)
    if isinstance(descriptor, dict):
        return descriptor.get("default", fallback)
    options = node_input_option_values(object_info, node_name, input_name)
    return options[0] if options else fallback


def model_option_matches(options: list[str], expected: str) -> bool:
    expected_norm = expected.replace("\\", "/").lower()
    expected_base = Path(expected_norm).name
    for option in options:
        option_norm = option.replace("\\", "/").lower()
        if option_norm == expected_norm or option_norm.endswith(f"/{expected_norm}"):
            return True
        if Path(option_norm).name == expected_base:
            return True
    return False


def resolve_graph_model_option_names(graph: dict[str, Any], object_info: dict[str, Any]) -> dict[str, Any]:
    input_by_class = {
        "CheckpointLoaderSimple": ("ckpt_name",),
        "UNETLoader": ("unet_name",),
        "UnetLoaderGGUF": ("unet_name",),
        "LoraLoaderModelOnly": ("lora_name",),
        "VAELoader": ("vae_name",),
        "CLIPLoader": ("clip_name",),
        "DualCLIPLoader": ("clip_name1", "clip_name2"),
        "QuadrupleCLIPLoader": ("clip_name1", "clip_name2", "clip_name3", "clip_name4"),
        "CLIPVisionLoader": ("clip_name",),
        "UpscaleModelLoader": ("model_name",),
        "LTXAVTextEncoderLoader": ("text_encoder", "ckpt_name"),
        "LTXVAudioVAELoader": ("ckpt_name",),
        "LatentUpscaleModelLoader": ("model_name",),
        "ModelPatchLoader": ("name",),
        "MinimaxH3LatentUpscaler3D": ("model_name",),
    }
    for item in graph.values():
        class_type = str(item.get("class_type") or "")
        # SaveVideo 0.36 nests codec under the selected container; older cores
        # still require the flat input. Resolve against the connected schema.
        if class_type == "SaveVideo":
            inputs = item.get("inputs") or {}
            descriptor = object_info.get(class_type, {}).get("input", {}).get("required", {}).get("format", [])
            if descriptor and descriptor[0] == "COMFY_DYNAMICCOMBO_V3" and "codec" in inputs:
                inputs.setdefault("format.codec", inputs.pop("codec"))
        input_names = input_by_class.get(class_type)
        if not input_names:
            continue
        inputs = item.get("inputs") or {}
        for input_name in input_names:
            current = inputs.get(input_name)
            if not isinstance(current, str):
                continue
            options = node_input_options(object_info, class_type, input_name)
            match = next((option for option in options if model_option_matches([option], current)), None)
            if not match and class_type == "LoraLoaderModelOnly" and current == LTX23_DISTILLED_LORA:
                accepted = (LTX23_DISTILLED_LORA, *LTX23_DISTILLED_LORA_ALTERNATIVES)
                match = next((option for option in options if any(model_option_matches([option], name) for name in accepted)), None)
            if match:
                inputs[input_name] = match
    return graph


def graph_model_registry_errors(graph: dict[str, Any], object_info: dict[str, Any] | None) -> list[str]:
    if object_info is None:
        return ["ComfyUI 未连接，无法验证 workflow 里的模型名。"]

    input_by_class = {
        "CheckpointLoaderSimple": ("ckpt_name",),
        "UNETLoader": ("unet_name",),
        "UnetLoaderGGUF": ("unet_name",),
        "LoraLoaderModelOnly": ("lora_name",),
        "VAELoader": ("vae_name",),
        "CLIPLoader": ("clip_name",),
        "DualCLIPLoader": ("clip_name1", "clip_name2"),
        "QuadrupleCLIPLoader": ("clip_name1", "clip_name2", "clip_name3", "clip_name4"),
        "CLIPVisionLoader": ("clip_name",),
        "UpscaleModelLoader": ("model_name",),
        "LTXAVTextEncoderLoader": ("text_encoder", "ckpt_name"),
        "LTXVAudioVAELoader": ("ckpt_name",),
        "LatentUpscaleModelLoader": ("model_name",),
        "ModelPatchLoader": ("name",),
        "MinimaxH3LatentUpscaler3D": ("model_name",),
    }
    errors: list[str] = h3_workflows.runtime_errors(graph, object_info)
    for node_id, item in graph.items():
        class_type = str(item.get("class_type") or "")
        input_names = input_by_class.get(class_type)
        if not input_names:
            continue
        inputs = item.get("inputs") or {}
        for input_name in input_names:
            current = inputs.get(input_name)
            if not isinstance(current, str):
                continue
            options = node_input_options(object_info, class_type, input_name)
            if not model_option_matches(options, current):
                message = f"{node_id}.{class_type}.{input_name} 模型未出现在 ComfyUI 列表：{current}"
                recipe = next((item for item in video_params.H3_RUNTIME_PROFILES.values()
                               if item.get("lora_name") == current.replace("\\", "/").rsplit("/", 1)[-1]), None)
                if input_name == "lora_name" and recipe:
                    message += f"。{recipe['label']} 需要此专用 LoRA，请在下载中心安装后重新预检；不会自动替换为其他版本。"
                errors.append(message)
    return errors


def workflow_risk_checks(*, mode: str, hardware: dict[str, Any], width: int, height: int, length: int) -> list[dict[str, str]]:
    checks: list[dict[str, str]] = []
    strategy = hardware.get("platform_strategy")
    accelerator = str(hardware.get("accelerator") or "cpu")
    max_vram = float(hardware.get("max_vram_gb") or 0)
    if mode in {"minimax_h3_t2v", "minimax_h3_i2v", "minimax_h3_r2v"}:
        if accelerator != "cuda":
            checks.append(
                {
                    "level": "blocked",
                    "title": "MiniMax H3 需要 NVIDIA CUDA",
                    "message": "当前 H3 INT8 原生音视频路线只对 CUDA 开放；Mac/MPS 和纯 CPU 暂不作为可用档位。",
                }
            )
        elif max_vram < 40:
            checks.append(
                {
                    "level": "blocked",
                    "title": "MiniMax H3 显存不足",
                    "message": "H3 主模型、32B 文本编码器和双 VAE 总计约 53.9GB；低于 40GB 显存不建议直接运行。",
                }
            )
        elif max_vram < 80:
            checks.append(
                {
                    "level": "warn",
                    "title": "MiniMax H3 需要模型卸载",
                    "message": "40GB 到 79GB 属于实验档，ComfyUI 可能把文本编码器或 VAE 卸载到内存，速度会明显下降。",
                }
            )
        if width * height >= 1920 * 1088:
            checks.append(
                {
                    "level": "warn",
                    "title": "H3 1080P 原生生成实验档",
                    "message": "平台按 1920x1088 或 1088x1920 生成后裁到标准 1080p。先用 864x480 短镜头确认，再考虑原生 1080p 或 SeedVR2 超分。",
                }
            )
        elif width * height >= 1344 * 768 or length > 124:
            checks.append(
                {
                    "level": "warn",
                    "title": "H3 高分辨率或长镜头",
                    "message": "建议先用 864x480、73 帧完成试镜，再提高到 768P 或 5 秒以上。R2V 使用 max 参考精度时成本还会继续增加。",
                }
            )
    if mode in {"ltx25_t2v", "ltx25_i2v"}:
        if accelerator != "cuda":
            checks.append(
                {
                    "level": "blocked",
                    "title": "LTX 2.5 当前开箱路线需要 NVIDIA CUDA",
                    "message": "官方 LTX 2.5 节点当前把 CUDA 作为本地运行主线；Mac/MPS 暂保留 LTXV 轻量路线。",
                }
            )
        elif max_vram < 32:
            checks.append(
                {
                    "level": "blocked",
                    "title": "LTX 2.5 显存不足",
                    "message": "当前原生工作流需要约 32GB 或更多显存。低显存专用加载器尚未接入小白前端。",
                }
            )
        elif max_vram < 48:
            checks.append(
                {
                    "level": "warn",
                    "title": "LTX 2.5 需要模型卸载",
                    "message": "32GB 到 47GB 建议使用 Conv VAE、640x352 短镜头，并允许 ComfyUI 自动卸载模型。",
                }
            )
        if width * height >= 1920 * 1088:
            checks.append(
                {
                    "level": "warn",
                    "title": "LTX 2.5 1080P 画布实验档",
                    "message": "先用 720P 确认提示词和运动。1080P 画布会显著增加时间和显存，长镜头更适合拆分后再拼接。",
                }
            )
        elif width * height >= 1280 * 704 and length > 121:
            checks.append(
                {
                    "level": "warn",
                    "title": "LTX 2.5 高分辨率长镜头",
                    "message": "720P 超过约 5 秒时先做 640x352 smoke test；人物一致性优先按 3 到 6 秒分镜生成。",
                }
            )
    if mode == "upscale_seedvr2":
        if accelerator != "cuda":
            checks.append(
                {
                    "level": "blocked",
                    "title": "SeedVR2 当前需要 NVIDIA CUDA",
                    "message": "这一档使用 INT8 ConvRot 时序模型；Mac/MPS 和纯 CPU 暂不作为开箱即用路线。请改用 RealESRGAN 快速兼容档。",
                }
            )
        elif max_vram < 12:
            checks.append(
                {
                    "level": "blocked",
                    "title": "SeedVR2 显存不足",
                    "message": "当前显存低于 12GB。请改用 RealESRGAN，或先缩短、缩小源视频。",
                }
            )
        elif max_vram < 24:
            checks.append(
                {
                    "level": "warn",
                    "title": "SeedVR2 小显存模式",
                    "message": "12GB 到 23GB 会依赖自动时间分块，速度较慢；长视频建议先按镜头处理。",
                }
            )
        if width * height >= 1280 * 720 or length > 240:
            checks.append(
                {
                    "level": "warn",
                    "title": "高分辨率长片超分",
                    "message": "SeedVR2 会把源视频放大 2 倍并联合修复连续帧。720P 长片输出接近 2K，建议按镜头处理，自动分块会更慢但更稳。",
                }
            )
    if strategy != "mac_mps":
        return checks

    mps_ready = bool(hardware.get("front_torch_mps_ready") or hardware.get("comfy_torch_mps_ready"))
    if mode in {"i2v_a14b", "t2v_a14b"}:
        checks.append(
            {
                "level": "blocked",
                "title": "A14B Mac 专家风险",
                "message": "Wan2.2 A14B 的 fp8/MPS 兼容风险较高，Mac 默认不开放。请先使用 LTX 或 Wan5B 实验档。",
            }
        )
    if mode == "ti2v_5b":
        checks.append(
            {
                "level": "warn",
                "title": "Wan5B MPS smoke test",
                "message": "Mac 上运行 Wan5B 前建议先用 512x320、9 到 17 帧、低步数跑一次 smoke test，再提高到当前分辨率。",
            }
        )
        if width >= 1280 or height >= 704 or length > 49:
            checks.append(
                {
                    "level": "warn",
                    "title": "720P 高内存实验",
                    "message": "当前参数属于 Mac 高内存实验范围；如果出现 OOM、dtype 或黑屏，先退回 480P/短帧数。",
                }
            )
    if mode in {"ltx_i2v", "ltx_t2v"} and not mps_ready:
        checks.append(
            {
                "level": "warn",
                "title": "MPS 状态未确认",
                "message": "未在前端或 ComfyUI Python 中确认 torch.backends.mps 可用；这不一定代表不能跑，但建议先启动 ComfyUI 后刷新环境。",
            }
        )
    return checks


async def apply_comfy_model_option_names(graph: dict[str, Any]) -> dict[str, Any]:
    try:
        object_info = await get_comfy_object_info()
    except HTTPException:
        return graph
    return resolve_graph_model_option_names(graph, object_info)


def collect_model_registry_checks(object_info: dict[str, Any] | None) -> list[dict[str, Any]]:
    expectations = [
        {
            "id": "minimax_h3_fl2va_int8",
            "label": "MiniMax H3 FL2VA INT8 扩散模型",
            "node": "UNETLoader",
            "input": "unet_name",
            "name": MINIMAX_H3_FL2VA_MODEL,
        },
        {
            "id": "minimax_h3_ref2va_int8",
            "label": "MiniMax H3 Ref2VA INT8 扩散模型",
            "node": "UNETLoader",
            "input": "unet_name",
            "name": MINIMAX_H3_REF2VA_MODEL,
        },
        {
            "id": "minimax_h3_text_int8",
            "label": "MiniMax H3 Qwen3-VL 32B INT8 文本编码器",
            "node": "CLIPLoader",
            "input": "clip_name",
            "name": MINIMAX_H3_TEXT_ENCODER,
        },
        {
            "id": "minimax_h3_video_vae",
            "label": "MiniMax H3 视频 VAE FP16",
            "node": "VAELoader",
            "input": "vae_name",
            "name": MINIMAX_H3_VIDEO_VAE,
        },
        {
            "id": "minimax_h3_audio_vae",
            "label": "MiniMax H3 音频 VAE FP32",
            "node": "VAELoader",
            "input": "vae_name",
            "name": MINIMAX_H3_AUDIO_VAE,
        },
        {
            "id": "seedvr2_3b_int8",
            "label": "SeedVR2 3B INT8 时序视频修复模型",
            "node": "UNETLoader",
            "input": "unet_name",
            "name": SEEDVR2_3B_MODEL,
        },
        {
            "id": "seedvr2_vae_fp16",
            "label": "SeedVR2 视频 VAE FP16",
            "node": "VAELoader",
            "input": "vae_name",
            "name": SEEDVR2_VIDEO_VAE,
        },
        {
            "id": "ti2v_5b",
            "label": "Wan2.2 TI2V-5B fp16",
            "node": "UNETLoader",
            "input": "unet_name",
            "name": "Wan2.2/wan2.2_ti2v_5B_fp16.safetensors",
        },
        {
            "id": "i2v_high",
            "label": "Wan2.2 I2V-A14B high noise fp8",
            "node": "UNETLoader",
            "input": "unet_name",
            "name": "Wan2.2/wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors",
        },
        {
            "id": "i2v_low",
            "label": "Wan2.2 I2V-A14B low noise fp8",
            "node": "UNETLoader",
            "input": "unet_name",
            "name": "Wan2.2/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors",
        },
        {
            "id": "t2v_high",
            "label": "Wan2.2 T2V-A14B high noise fp8",
            "node": "UNETLoader",
            "input": "unet_name",
            "name": "Wan2.2/wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors",
        },
        {
            "id": "t2v_low",
            "label": "Wan2.2 T2V-A14B low noise fp8",
            "node": "UNETLoader",
            "input": "unet_name",
            "name": "Wan2.2/wan2.2_t2v_low_noise_14B_fp8_scaled.safetensors",
        },
        {
            "id": "umt5",
            "label": "UMT5 XXL fp8 文本编码器",
            "node": "CLIPLoader",
            "input": "clip_name",
            "name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors",
        },
        {
            "id": "wan21_vae",
            "label": "Wan 2.1 VAE",
            "node": "VAELoader",
            "input": "vae_name",
            "name": "wan_2.1_vae.safetensors",
        },
        {
            "id": "wan22_vae",
            "label": "Wan 2.2 VAE",
            "node": "VAELoader",
            "input": "vae_name",
            "name": "wan2.2_vae.safetensors",
        },
        {
            "id": "ltx_2b_098",
            "label": "LTXV 0.9.8 2B distilled fp8",
            "node": "CheckpointLoaderSimple",
            "input": "ckpt_name",
            "name": "ltxv-2b-0.9.8-distilled-fp8.safetensors",
        },
        {
            "id": "t5xxl_fp16",
            "label": "T5 XXL fp16 文本编码器",
            "node": "CLIPLoader",
            "input": "clip_name",
            "name": "t5xxl_fp16.safetensors",
        },
        {
            "id": "ltx23_fp8_distilled",
            "label": "LTX-Video 2.3 22B Distilled FP8",
            "node": "CheckpointLoaderSimple",
            "input": "ckpt_name",
            "name": "ltx-2.3-22b-distilled-fp8.safetensors",
        },
        {
            "id": "ltx23_fp8_dev",
            "label": "LTX-Video 2.3 22B Dev FP8",
            "node": "CheckpointLoaderSimple",
            "input": "ckpt_name",
            "name": LTX23_DEV_CHECKPOINT,
        },
        {
            "id": "ltx23_nvfp4_dev",
            "label": "LTX-Video 2.3 22B Dev NVFP4",
            "node": "CheckpointLoaderSimple",
            "input": "ckpt_name",
            "name": "ltx-2.3-22b-dev-nvfp4.safetensors",
        },
        {
            "id": "ltx23_gemma3_fp4",
            "label": "Gemma 3 12B FP4 文本编码器",
            "node": "LTXAVTextEncoderLoader",
            "input": "text_encoder",
            "name": LTX23_TEXT_ENCODER,
        },
        {
            "id": "ltx23_spatial_upscaler",
            "label": "LTX 2.3 空间潜变量 2x 超分模型",
            "node": "LatentUpscaleModelLoader",
            "input": "model_name",
            "name": LTX23_SPATIAL_UPSCALER,
        },
        {
            "id": "ltx23_distilled_lora",
            "label": "LTX 2.3 22B Distilled LoRA",
            "node": "LoraLoaderModelOnly",
            "input": "lora_name",
            "name": LTX23_DISTILLED_LORA,
            "alternatives": list(LTX23_DISTILLED_LORA_ALTERNATIVES),
        },
        {
            "id": "ltx25_distilled_int8",
            "label": "LTX-Video 2.5 22B Distilled INT8",
            "node": "UNETLoader",
            "input": "unet_name",
            "name": LTX25_DISTILLED_INT8_MODEL,
        },
        {
            "id": "ltx25_distilled_nvfp4",
            "label": "LTX-Video 2.5 22B Distilled NVFP4",
            "node": "UNETLoader",
            "input": "unet_name",
            "name": LTX25_DISTILLED_NVFP4_MODEL,
        },
        {
            "id": "ltx25_text_int8",
            "label": "LTX 2.5 Gemma 4 12B INT8 文本编码器",
            "node": "CLIPLoader",
            "input": "clip_name",
            "name": LTX25_TEXT_ENCODER,
        },
        {
            "id": "ltx25_video_vae_diff",
            "label": "LTX 2.5 DiffVAE",
            "node": "VAELoader",
            "input": "vae_name",
            "name": LTX25_VIDEO_VAE_DIFF,
        },
        {
            "id": "ltx25_video_vae_conv",
            "label": "LTX 2.5 Conv VAE",
            "node": "VAELoader",
            "input": "vae_name",
            "name": LTX25_VIDEO_VAE_CONV,
        },
        {
            "id": "ltx25_audio_vae",
            "label": "LTX 2.5 Audio VAE",
            "node": "VAELoader",
            "input": "vae_name",
            "name": LTX25_AUDIO_VAE,
        },
        {
            "id": "ltx25_spatial_upscaler",
            "label": "LTX 2.5 潜变量 2x 超分模型",
            "node": "LatentUpscaleModelLoader",
            "input": "model_name",
            "name": LTX25_SPATIAL_UPSCALER,
        },
        {
            "id": "ltx25_duration_head",
            "label": "LTX 2.5 自动时长预测头",
            "node": "ModelPatchLoader",
            "input": "name",
            "name": LTX25_DURATION_HEAD,
        },
        {
            "id": "qwen_image_21_int8",
            "label": "Qwen-Image-2.1 INT8 ConvRot",
            "node": "UNETLoader",
            "input": "unet_name",
            "name": QWEN_IMAGE_21_MODEL,
        },
        {
            "id": "qwen_image_21_text_encoder_int8",
            "label": "Qwen3-VL 8B INT8 ConvRot 文本编码器",
            "node": "CLIPLoader",
            "input": "clip_name",
            "name": QWEN_IMAGE_21_TEXT_ENCODER,
        },
        {
            "id": "qwen_image_21_vae_bf16",
            "label": "Qwen-Image-2.1 VAE BF16",
            "node": "VAELoader",
            "input": "vae_name",
            "name": QWEN_IMAGE_21_VAE,
        },
        {
            "id": "qwen_image_2512_fp8",
            "label": "Qwen-Image-2512 FP8",
            "node": "UNETLoader",
            "input": "unet_name",
            "name": QWEN_IMAGE_MODEL,
        },
        {
            "id": "qwen_image_text_encoder_fp8",
            "label": "Qwen 2.5 VL 7B FP8 文本编码器",
            "node": "CLIPLoader",
            "input": "clip_name",
            "name": QWEN_IMAGE_TEXT_ENCODER,
        },
        {
            "id": "qwen_image_vae",
            "label": "Qwen-Image VAE",
            "node": "VAELoader",
            "input": "vae_name",
            "name": QWEN_IMAGE_VAE,
        },
        {
            "id": "qwen_image_lightning_lora",
            "label": "Qwen-Image Lightning 4 步 LoRA",
            "node": "LoraLoaderModelOnly",
            "input": "lora_name",
            "name": QWEN_IMAGE_LIGHTNING_LORA,
        },
        {
            "id": "qwen_image_nsfw_lora",
            "label": "Qwen-Image 社区无限制 LoRA",
            "node": "LoraLoaderModelOnly",
            "input": "lora_name",
            "name": "qwen_image_nsfw.safetensors",
        },
        {
            "id": "hidream_o1_full_fp8",
            "label": "HiDream-O1-Image Full FP8",
            "node": "CheckpointLoaderSimple",
            "input": "ckpt_name",
            "name": "hidream_o1_image_fp8_scaled.safetensors",
        },
        {
            "id": "hidream_o1_dev2604_fp8",
            "label": "HiDream-O1-Image Dev-2604 FP8",
            "node": "CheckpointLoaderSimple",
            "input": "ckpt_name",
            "name": "hidream_o1_image_dev_fp8_scaled.safetensors",
        },
        {
            "id": "hidream_gemma4_prompt_fp8",
            "label": "Gemma 4 E4B FP8 提示词增强器",
            "node": "CLIPLoader",
            "input": "clip_name",
            "name": "gemma4_e4b_it_fp8_scaled.safetensors",
        },
        {
            "id": "flux2_dev_fp8",
            "label": "FLUX.2-dev FP8 Mixed",
            "node": "UNETLoader",
            "input": "unet_name",
            "name": "flux2_dev_fp8mixed.safetensors",
        },
        {
            "id": "flux2_dev_nvfp4",
            "label": "FLUX.2-dev NVFP4 Mixed",
            "node": "UNETLoader",
            "input": "unet_name",
            "name": "flux2-dev-nvfp4-mixed.safetensors",
        },
        {
            "id": "flux2_text_encoder_fp8",
            "label": "FLUX.2 Mistral 3 Small FP8",
            "node": "CLIPLoader",
            "input": "clip_name",
            "name": "mistral_3_small_flux2_fp8.safetensors",
        },
        {
            "id": "flux2_text_encoder_fp4",
            "label": "FLUX.2 Mistral 3 Small FP4",
            "node": "CLIPLoader",
            "input": "clip_name",
            "name": "mistral_3_small_flux2_fp4_mixed.safetensors",
        },
        {
            "id": "flux2_vae",
            "label": "FLUX.2 / ERNIE VAE",
            "node": "VAELoader",
            "input": "vae_name",
            "name": "flux2-vae.safetensors",
        },
        {
            "id": "z_image_base_bf16",
            "label": "Z-Image Base BF16",
            "node": "UNETLoader",
            "input": "unet_name",
            "name": "z_image_bf16.safetensors",
        },
        {
            "id": "z_image_turbo_nvfp4",
            "label": "Z-Image Turbo NVFP4",
            "node": "UNETLoader",
            "input": "unet_name",
            "name": "z_image_turbo_nvfp4.safetensors",
        },
        {
            "id": "z_image_text_encoder_fp8",
            "label": "Z-Image Qwen 3 4B FP8",
            "node": "CLIPLoader",
            "input": "clip_name",
            "name": "qwen_3_4b_fp8_mixed.safetensors",
        },
        {
            "id": "z_image_text_encoder_fp4",
            "label": "Z-Image Qwen 3 4B FP4",
            "node": "CLIPLoader",
            "input": "clip_name",
            "name": "qwen_3_4b_fp4_mixed.safetensors",
        },
        {
            "id": "z_image_vae",
            "label": "Z-Image VAE",
            "node": "VAELoader",
            "input": "vae_name",
            "name": "ae.safetensors",
        },
        {
            "id": "z_image_nsfw_lora",
            "label": "Z-Image 社区无限制 LoRA",
            "node": "LoraLoaderModelOnly",
            "input": "lora_name",
            "name": "z_image_nsfw_community.safetensors",
        },
        {
            "id": "ernie_image_standard",
            "label": "ERNIE-Image 标准版",
            "node": "UNETLoader",
            "input": "unet_name",
            "name": "ernie-image.safetensors",
        },
        {
            "id": "ernie_image_turbo",
            "label": "ERNIE-Image Turbo",
            "node": "UNETLoader",
            "input": "unet_name",
            "name": "ernie-image-turbo.safetensors",
        },
        {
            "id": "ernie_ministral_text_encoder",
            "label": "ERNIE Ministral 3 3B",
            "node": "CLIPLoader",
            "input": "clip_name",
            "name": "ministral-3-3b.safetensors",
        },
        {
            "id": "ernie_prompt_enhancer",
            "label": "ERNIE 提示词增强器",
            "node": "CLIPLoader",
            "input": "clip_name",
            "name": "ernie-image-prompt-enhancer.safetensors",
        },
        {
            "id": "bernini_r_high_fp8",
            "label": "Bernini-R High Noise FP8",
            "node": "UNETLoader",
            "input": "unet_name",
            "name": "wan2.2_bernini_r_high_noise_fp8_scaled.safetensors",
        },
        {
            "id": "bernini_r_low_fp8",
            "label": "Bernini-R Low Noise FP8",
            "node": "UNETLoader",
            "input": "unet_name",
            "name": "wan2.2_bernini_r_low_noise_fp8_scaled.safetensors",
        },
        {
            "id": "bernini_lightx2v_lora",
            "label": "Bernini-R LightX2V LoRA",
            "node": "LoraLoaderModelOnly",
            "input": "lora_name",
            "name": "lightx2v_T2V_14B_cfg_step_distill_v2_lora_rank64_bf16.safetensors",
        },
        {
            "id": "bernini_vae",
            "label": "Bernini-R Wan VAE BF16",
            "node": "VAELoader",
            "input": "vae_name",
            "name": "Wan2_1_VAE_bf16.safetensors",
        },
        {
            "id": "i2v_lora_high",
            "label": "I2V 4步 LoRA high noise",
            "node": "LoraLoaderModelOnly",
            "input": "lora_name",
            "name": "Wan2.2/wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors",
        },
        {
            "id": "i2v_lora_low",
            "label": "I2V 4步 LoRA low noise",
            "node": "LoraLoaderModelOnly",
            "input": "lora_name",
            "name": "Wan2.2/wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors",
        },
        {
            "id": "t2v_lora_high",
            "label": "T2V 4步 LoRA high noise",
            "node": "LoraLoaderModelOnly",
            "input": "lora_name",
            "name": "Wan2.2/wan2.2_t2v_lightx2v_4steps_lora_v1.1_high_noise.safetensors",
        },
        {
            "id": "t2v_lora_low",
            "label": "T2V 4步 LoRA low noise",
            "node": "LoraLoaderModelOnly",
            "input": "lora_name",
            "name": "Wan2.2/wan2.2_t2v_lightx2v_4steps_lora_v1.1_low_noise.safetensors",
        },
        {
            "id": "realesrgan_x2",
            "label": "RealESRGAN x2 视频超分权重",
            "node": "UpscaleModelLoader",
            "input": "model_name",
            "name": "RealESRGAN_x2plus.pth",
        },
        {
            "id": "ultrasharp_x4",
            "label": "4x-UltraSharp 备用超分权重",
            "node": "UpscaleModelLoader",
            "input": "model_name",
            "name": "4x-UltraSharp.pth",
        },
    ]
    checks: list[dict[str, Any]] = []
    for item in expectations:
        options = node_input_options(object_info, item["node"], item["input"])
        accepted_names = [item["name"], *(item.get("alternatives") or [])]
        ok = any(model_option_matches(options, name) for name in accepted_names)
        reason = "已出现在 ComfyUI 模型列表" if ok else "ComfyUI 模型列表未加载"
        if object_info is None:
            reason = "ComfyUI 未连接"
        elif item["node"] not in object_info:
            reason = f"节点未加载：{item['node']}"
        checks.append(
            {
                **item,
                "ok": ok,
                "reason": reason,
                "options_count": len(options),
            }
        )
    return checks


def build_load_diagnostics(
    *,
    paths: dict[str, Any],
    assets: list[dict[str, Any]],
    custom_nodes: list[dict[str, Any]],
    node_checks: list[dict[str, Any]],
    registry_checks: list[dict[str, Any]],
    object_info: dict[str, Any] | None,
) -> list[dict[str, str]]:
    diagnostics: list[dict[str, str]] = []
    if paths.get("base_dir_mismatch"):
        diagnostics.append(
            {
                "level": "warn",
                "title": "检测到 ComfyUI 实际目录和前端默认目录不同",
                "message": f"本次会按 ComfyUI 正在使用的目录工作：{paths['base_dir']}。如果之前下载到 {BASE_DIR}，那些文件不会被当前 ComfyUI 自动加载。",
            }
        )

    asset_by_id = {item["id"]: item for item in assets}
    loaded_missing = [
        item
        for item in registry_checks
        if not item["ok"] and asset_by_id.get(item["id"], {}).get("ok")
    ]
    if loaded_missing and object_info is not None:
        labels = "、".join(item["label"] for item in loaded_missing[:4])
        suffix = " 等" if len(loaded_missing) > 4 else ""
        diagnostics.append(
            {
                "level": "blocked",
                "title": "文件已存在，但 ComfyUI 模型列表没有加载",
                "message": f"{labels}{suffix} 已在磁盘上，但没有出现在 ComfyUI 的模型下拉列表里。通常是下载目录不一致，或安装后还没有重启 ComfyUI。",
            }
        )

    node_by_name = {item["name"]: item for item in node_checks}
    custom_by_id = {item["id"]: item for item in custom_nodes}
    if object_info is not None and custom_by_id.get("video_helper_suite", {}).get("ok") and not (
        node_by_name.get("VHS_LoadVideo", {}).get("ok") and node_by_name.get("VHS_VideoCombine", {}).get("ok")
    ):
        diagnostics.append(
            {
                "level": "blocked",
                "title": "VideoHelperSuite 目录存在，但节点未加载",
                "message": "这通常是 ComfyUI 没有重启，或自定义节点 requirements 没装进 ComfyUI 的 Python 环境。请重新执行一键安装缺失项，然后重启 ComfyUI。",
            }
        )
    if object_info is not None and custom_by_id.get("frame_interpolation", {}).get("ok") and not node_by_name.get("RIFE VFI", {}).get("ok"):
        diagnostics.append(
            {
                "level": "blocked",
                "title": "Frame-Interpolation 目录存在，但 RIFE 节点未加载",
                "message": "安装脚本现在会自动尝试安装该节点的 requirements。安装后需要重启 ComfyUI 才会出现 RIFE VFI 节点。",
            }
        )

    if object_info is None and any(item.get("ok") for item in custom_nodes):
        diagnostics.append(
            {
                "level": "warn",
                "title": "ComfyUI 尚未连接，节点加载状态待确认",
                "message": "磁盘上的自定义节点目录已检测到；请先启动 ComfyUI，前端会再从 /object_info 验证节点是否真的加载成功。",
            }
        )

    partial = [item for item in assets if item.get("exists") and not item.get("ok")]
    if partial:
        labels = "、".join(item["label"] for item in partial[:3])
        diagnostics.append(
            {
                "level": "warn",
                "title": "发现未完整下载的文件",
                "message": f"{labels} 文件大小不匹配。一键安装会尝试断点续传，若仍失败请删除对应 partial 文件后重试。",
            }
        )

    if not diagnostics:
        diagnostics.append(
            {
                "level": "ok",
                "title": "加载链路正常",
                "message": "模型文件、自定义节点目录和 ComfyUI 加载状态没有发现明显不一致。",
            }
        )
    return diagnostics


def model_recommendations(
    *,
    os_info: dict[str, Any],
    hardware: dict[str, Any],
    assets: list[dict[str, Any]],
    custom_nodes: list[dict[str, Any]],
    tool_checks: list[dict[str, Any]],
    node_checks: list[dict[str, Any]],
    base_dir: Path | None = None,
    selected_model_id: str | None = None,
) -> list[dict[str, Any]]:
    base_dir = (base_dir or BASE_DIR).expanduser().resolve()
    asset_ok = {item["id"]: bool(item["ok"]) for item in assets}
    node_ok = {item["name"]: bool(item["ok"]) for item in node_checks}
    custom_ok = {item["id"]: bool(item["ok"]) for item in custom_nodes}
    tool_ok = {item["name"]: bool(item["ok"]) for item in tool_checks}
    accelerator = hardware.get("accelerator")
    max_vram = float(hardware.get("max_vram_gb") or 0)
    sum_vram = float(hardware.get("sum_vram_gb") or 0)
    gpu_count = int(hardware.get("gpu_count") or 0)
    is_macos = os_info["name"] == "Darwin"
    platform_strategy = hardware.get("platform_strategy")
    mac_tier = str(hardware.get("mac_video_tier") or "")
    mac_info = hardware.get("mac") or {}
    mac_memory = float(mac_info.get("unified_memory_gb") or hardware.get("system_memory_gb") or 0)
    mac_mps_ready = bool(hardware.get("front_torch_mps_ready") or hardware.get("comfy_torch_mps_ready"))
    post_only_video = platform_strategy in {"post_only", "mac_post_only"} or accelerator == "cpu"
    fal_ready = bool(fal_api_key())

    def all_assets(*ids: str) -> bool:
        return all(asset_ok.get(item) for item in ids)

    def all_nodes(*names: str) -> bool:
        return all(node_ok.get(item) for item in names)

    def upscale_recommendation(context: str = "") -> dict[str, Any]:
        seedvr2_nodes_ready = all_nodes(
            "UNETLoader",
            "VAELoader",
            "ImageScaleBy",
            "VAEEncodeTiled",
            "SeedVR2Preprocess",
            "SeedVR2TemporalChunk",
            "SeedVR2Conditioning",
            "SeedVR2TemporalMerge",
            "VAEDecodeTiled",
            "SeedVR2PostProcessing",
            "VHS_LoadVideo",
            "VHS_VideoCombine",
        )
        seedvr2_3b_ready = all_assets("seedvr2_3b_int8", "seedvr2_vae_fp16") and seedvr2_nodes_ready
        seedvr2_7b_ready = all_assets("seedvr2_7b_nvfp4", "seedvr2_vae_fp16") and seedvr2_nodes_ready
        seedvr2_ready = seedvr2_7b_ready or seedvr2_3b_ready
        legacy_ready = all_assets("realesrgan_x2") and all_nodes(
            "UpscaleModelLoader",
            "ImageUpscaleWithModel",
        )
        seedvr2_usable = seedvr2_ready and accelerator == "cuda" and max_vram >= 12
        prefix = f"{context.rstrip('。')}。" if context.strip() else ""
        if seedvr2_usable:
            preferred = (
                "SeedVR2 7B NVFP4 1.5x（720P→1080P）"
                if seedvr2_7b_ready and max_vram >= 48
                else "SeedVR2 3B INT8 时序视频超分 2x"
            )
            return {
                "step": "清晰度增强",
                "status": "ok" if max_vram >= 24 else "warn",
                "recommended": [preferred, "RealESRGAN 快速兼容 2x"],
                "reason": f"{prefix}SeedVR2 会联合修复连续帧，能减少逐帧超分造成的纹理跳动；48GB+ 优先 7B，RealESRGAN 保留为快速兼容档。",
            }
        if legacy_ready:
            seed_note = "SeedVR2 当前仅开放 CUDA 路线；" if seedvr2_ready else "SeedVR2 尚未就绪；"
            return {
                "step": "清晰度增强",
                "status": "warn",
                "recommended": ["RealESRGAN 快速兼容 2x"],
                "reason": f"{prefix}{seed_note}当前可使用 RealESRGAN 快速兼容档。",
            }
        return {
            "step": "清晰度增强",
            "status": "blocked",
            "recommended": ["SeedVR2 7B/3B 时序视频超分"],
            "reason": f"{prefix}SeedVR2/RealESRGAN 权重或 ComfyUI 节点尚未就绪。",
        }

    recommendations: list[dict[str, Any]] = []

    def consolidated_recommendations(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        generation_items = [item for item in items if item.get("step") == "视频生成"]
        if len(generation_items) <= 1:
            return items
        status_rank = {"blocked": 0, "warn": 1, "ok": 2}
        merged = {
            "step": "视频生成",
            "status": max(generation_items, key=lambda item: status_rank.get(str(item.get("status")), 0)).get("status", "blocked"),
            "recommended": list(
                dict.fromkeys(
                    str(value)
                    for item in generation_items
                    for value in (item.get("recommended") or [])
                    if str(value).strip()
                )
            ),
            "reason": " ".join(
                dict.fromkeys(
                    str(item.get("reason") or "").strip()
                    for item in generation_items
                    if str(item.get("reason") or "").strip()
                )
            ),
        }
        first_index = next(index for index, item in enumerate(items) if item.get("step") == "视频生成")
        remaining = [item for item in items if item.get("step") != "视频生成"]
        remaining.insert(first_index, merged)
        return remaining

    # LTX 2.3 uses a separate Gemma encoder plus audio/two-stage latent nodes.
    selected_catalog = catalog_item_by_id(selected_model_id if selected_model_id is not None else saved_model_catalog_id()) or {}
    selected_profile = str(selected_catalog.get("default_install_profile") or "")
    selected_workflow_modes = selected_catalog.get("workflow_modes") or {}
    selected_image_only = "image" in selected_workflow_modes and not any(
        step in selected_workflow_modes for step in ("draft", "final")
    )
    if selected_catalog and selected_image_only:
        selected_label = str(selected_catalog.get("label") or "当前图片模型")
        recommendations.extend(
            [
                {
                    "step": "关键帧",
                    "status": "ok",
                    "recommended": [selected_label, "在独立图片生成工作台运行"],
                    "reason": "生成完成后可一键送入视频工作流作为关键帧。",
                },
                {
                    "step": "视频生成",
                    "status": "warn",
                    "recommended": ["请在模型控制台选择一个视频模型"],
                    "reason": "当前关注项是图片模型，不会被平台暗中替换成其他视频模型。",
                },
                {
                    "step": "闪烁修复",
                    "status": "ok" if tool_ok.get("ffmpeg") else "blocked",
                    "recommended": ["上传已有视频后处理"],
                    "reason": "图片模型选择不影响本地视频后期工具。",
                },
            ]
        )
        return consolidated_recommendations(recommendations)

    selected_generation_target = catalog_generation_target(selected_catalog)
    if selected_catalog and selected_generation_target == "cloud_api":
        selected_label = str(selected_catalog.get("label") or "H3 Max（fal 后训练版）")
        fal_ready = bool(fal_api_key())
        recommendations.extend(
            [
                {
                    "step": "关键帧",
                    "status": "ok",
                    "recommended": ["关键帧可选", "支持首帧 / 首尾帧"],
                    "reason": "无图时走文字生视频；上传首帧可锁定构图，上传尾帧可控制镜头终点。",
                },
                {
                    "step": "视频生成",
                    "status": "ok" if fal_ready else "blocked",
                    "recommended": [selected_label, "fal 官方云端队列 API"],
                    "reason": (
                        "FAL_KEY 已配置。本路线不调用 ComfyUI、不加载本机视频模型，也不占用本机生成显存。"
                        if fal_ready
                        else "请先设置 FAL_KEY 并只重启前端；fal 尚未发布 H3 Max 官方本地权重。"
                    ),
                },
                {
                    "step": "闪烁修复",
                    "status": "ok" if tool_ok.get("ffmpeg") else "blocked",
                    "recommended": ["成片回存后按需使用 ffmpeg deflicker"],
                    "reason": "fal 成片会自动下载到本地输出目录，之后可继续使用现有后期流程。",
                },
                {
                    "step": "插帧",
                    "status": "ok" if all_assets("rife49") and all_nodes("RIFE VFI") else "blocked",
                    "recommended": ["RIFE 4.9 2x（按需）"],
                    "reason": "H3 Max 固定 24fps；需要 48fps 时再对回存成片插帧。",
                },
                upscale_recommendation("fal 成片回存后可继续超分"),
                {
                    "step": "拼接剪辑",
                    "status": "ok" if tool_ok.get("ffmpeg") else "blocked",
                    "recommended": ["本地 ffmpeg 顺序拼接"],
                    "reason": "云端只负责生成；下载后的镜头仍由本地项目管理和拼接。",
                },
            ]
        )
        return consolidated_recommendations(recommendations)

    if selected_catalog and selected_generation_target != "native":
        selected_label = str(selected_catalog.get("label") or "当前模型")
        generation_target = catalog_generation_target(selected_catalog)
        support_label = "官方 ComfyUI 工作流" if generation_target == "comfy_template" else "手动接入"
        requirement = " ".join(
            part
            for part in (
                str(selected_catalog.get("workflow_support") or ""),
                str((CATALOG_INSTALL_PROFILES.get(selected_profile) or {}).get("external_requirement") or ""),
            )
            if part
        ).strip()
        recommendations.extend(
            [
                {
                    "step": "关键帧",
                    "status": "ok",
                    "recommended": ["关键帧可选"],
                    "reason": "按外部工作流要求决定是否上传关键帧。",
                },
                {
                    "step": "视频生成",
                    "status": "warn",
                    "recommended": [selected_label, support_label],
                    "reason": requirement or f"{selected_label} 需要通过{support_label}运行。",
                },
                {
                    "step": "闪烁修复",
                    "status": "ok" if tool_ok.get("ffmpeg") else "blocked",
                    "recommended": ["ffmpeg deflicker + hqdn3d"],
                    "reason": "外部生成的视频仍可回到平台继续做后期。",
                },
                {
                    "step": "插帧",
                    "status": "ok" if all_assets("rife49") and all_nodes("RIFE VFI") else "blocked",
                    "recommended": ["RIFE 4.9 2x"],
                    "reason": "外部生成的视频可直接上传插帧。",
                },
                upscale_recommendation("外部生成的视频也可直接上传超分"),
                {
                    "step": "拼接剪辑",
                    "status": "ok" if tool_ok.get("ffmpeg") else "blocked",
                    "recommended": ["本地 ffmpeg 顺序拼接"],
                    "reason": "平台可继续统一尺寸、帧率并拼接多个片段。",
                },
            ]
        )
        return consolidated_recommendations(recommendations)

    if selected_profile.startswith("ltx25-"):
        main_asset = (
            "ltx25_distilled_nvfp4"
            if selected_profile == "ltx25-distilled-nvfp4"
            else "ltx25_distilled_int8"
        )
        ltx25_ready = (
            all_assets(
                main_asset,
                "ltx25_text_int8",
                "ltx25_audio_vae",
                "ltx25_spatial_upscaler",
            )
            and bool(asset_ok.get("ltx25_video_vae_diff") or asset_ok.get("ltx25_video_vae_conv"))
            and all_nodes(
                "UNETLoader",
                "CLIPLoader",
                "VAELoader",
                "LTXVConditioning",
                "LTXVEmptyLatentAudio",
                "LTXVConcatAVLatent",
                "LTXVSeparateAVLatent",
                "LTXVDualCFGGuider",
                "LTXVLatentUpsampler",
                "LatentUpscaleModelLoader",
                "ManualSigmas",
                "SamplerCustomAdvanced",
                "VAEDecodeTiled",
                "LTXVAudioVAEDecode",
                "CreateVideo",
                "SaveVideo",
            )
        )
        if not ltx25_ready:
            status = "blocked"
        elif accelerator == "cuda" and max_vram >= 48:
            status = "ok"
        elif accelerator == "cuda" and max_vram >= 32:
            status = "warn"
        else:
            status = "blocked"
        selected_label = str(selected_catalog.get("label") or "LTX-Video 2.5")
        generation_reason = (
            f"{selected_label} 已就绪；建议先跑 640x352 短镜头，再提高到 720P。"
            if ltx25_ready
            else f"{selected_label} 尚缺模型文件或 LTX 2.5 节点，请在环境与安装页补齐。"
        )
        recommendations.extend(
            [
                {
                    "step": "关键帧",
                    "status": "ok",
                    "recommended": ["首帧可选", "可加尾帧控制镜头终点"],
                    "reason": "T2V 无需图片；I2V 使用首帧，首尾帧模式会按官方单阶段配方生成。",
                },
                {
                    "step": "视频生成",
                    "status": status,
                    "recommended": [selected_label, "Distilled 两阶段 + 原生音频"],
                    "reason": generation_reason,
                },
                {
                    "step": "无图生视频",
                    "status": status,
                    "recommended": [f"{selected_label} T2V", "先低分辨率试镜"],
                    "reason": generation_reason,
                },
                {
                    "step": "闪烁修复",
                    "status": "ok" if tool_ok.get("ffmpeg") else "blocked",
                    "recommended": ["ffmpeg deflicker + hqdn3d"],
                    "reason": "生成完成后可继续修曝光闪烁和轻微纹理跳动。",
                },
                {
                    "step": "插帧",
                    "status": "ok" if all_assets("rife49") and all_nodes("RIFE VFI") else "blocked",
                    "recommended": ["RIFE 4.9 2x"],
                    "reason": "按镜头需要把 24fps 提升到 48fps。",
                },
                upscale_recommendation("LTX 2.5 输出可直接进入时序超分"),
                {
                    "step": "拼接剪辑",
                    "status": "ok" if tool_ok.get("ffmpeg") else "blocked",
                    "recommended": ["本地 ffmpeg 顺序拼接"],
                    "reason": "把多个短镜头统一尺寸、帧率后合成完整 MP4。",
                },
            ]
        )
        return consolidated_recommendations(recommendations)

    if selected_profile.startswith("ltx23-"):
        # 该档位主模型资产 id（ltx23_nvfp4_dev / ltx23_fp8_dev / ltx23_fp8_distilled）
        ltx23_asset_map = {
            "ltx23-nvfp4-dev": "ltx23_nvfp4_dev",
            "ltx23-fp8-dev": "ltx23_fp8_dev",
            "ltx23-fp8-distilled": "ltx23_fp8_distilled",
        }
        main_asset = ltx23_asset_map.get(selected_profile, "ltx23_nvfp4_dev")
        ltx23_ready = all_assets(
            main_asset,
            "ltx23_gemma3_fp4",
            "ltx23_spatial_upscaler",
            "ltx23_distilled_lora",
        ) and all_nodes(
            "CheckpointLoaderSimple",
            "LTXAVTextEncoderLoader",
            "LTXVConditioning",
            "LTXVAudioVAELoader",
            "LTXVEmptyLatentAudio",
            "LTXVConcatAVLatent",
            "LTXVSeparateAVLatent",
            "LTXVCropGuides",
            "LTXVLatentUpsampler",
            "LatentUpscaleModelLoader",
            "ManualSigmas",
            "CFGGuider",
            "SamplerCustomAdvanced",
            "VAEDecodeTiled",
            "LTXVAudioVAEDecode",
            "CreateVideo",
            "SaveVideo",
        )
        comfy_ready = bool(tool_ok.get("ffmpeg"))
        rife_ready = all_assets("rife49") and all_nodes("RIFE VFI")
        status = "ok" if ltx23_ready else "blocked"
        reason = (
            f"{selected_catalog.get('label') or 'LTX 2.3'} 已就绪，可自由调整短镜头、分辨率与质量参数。"
            if ltx23_ready
            else f"{selected_catalog.get('label') or 'LTX 2.3'} 所需主模型或 LTX 节点不完整，请在环境与安装里补齐。"
        )
        recommendations.append(
            {"step": "关键帧", "status": "ok", "recommended": ["上传 PNG/JPG 关键帧", "或用本地生图模型生成首帧"], "reason": "关键帧只决定首帧画面，与视频模型无关。"}
        )
        recommendations.append(
            {"step": "视频生成", "status": status, "recommended": [f"{selected_catalog.get('label') or 'LTX 2.3'} 短镜头", "低分辨率先确认动作"], "reason": reason}
        )
        recommendations.append(
            {"step": "视频生成", "status": status, "recommended": [f"{selected_catalog.get('label') or 'LTX 2.3'} 高质量档", "短镜头分段生成"], "reason": reason}
        )
        recommendations.append(
            {"step": "无图生视频", "status": status, "recommended": [f"{selected_catalog.get('label') or 'LTX 2.3'} T2V", "无关键帧时使用"], "reason": reason}
        )
        recommendations.append(
            {
                "step": "闪烁修复",
                "status": "ok" if comfy_ready else "blocked",
                "recommended": ["ffmpeg deflicker + hqdn3d"],
                "reason": "可修正曝光闪烁和轻微纹理跳动；人物结构变形仍要回到生成步骤重跑。" if comfy_ready else "未检测到 ffmpeg 或所需滤镜。",
            }
        )
        recommendations.append(
            {
                "step": "插帧",
                "status": "ok" if rife_ready else "blocked",
                "recommended": ["RIFE 4.9 2x 插帧"],
                "reason": "RIFE 权重或自定义节点未就绪。" if not rife_ready else "把视频插到更高帧率，运动更顺。",
            }
        )
        recommendations.append(upscale_recommendation("适合在最终交付前处理"))
        recommendations.append(
            {
                "step": "拼接剪辑",
                "status": "ok" if comfy_ready else "blocked",
                "recommended": ["本地 ffmpeg 顺序拼接"],
                "reason": "把多个短镜头统一尺寸、帧率后合成 MP4。" if comfy_ready else "本地拼接需要 ffmpeg。",
            }
        )
        return consolidated_recommendations(recommendations)

    if selected_profile.startswith("hunyuan15-"):
        main_asset_map = {
            "hunyuan15-t2v-480-fp8": "hunyuan15_t2v_480_fp8_distilled",
            "hunyuan15-i2v-480-fp8": "hunyuan15_i2v_480_fp8_distilled",
            "hunyuan15-t2v-720-fp16": "hunyuan15_t2v_720_fp16",
            "hunyuan15-i2v-720-fp16": "hunyuan15_i2v_720_fp16",
        }
        is_i2v = "-i2v-" in selected_profile
        required_assets = [
            main_asset_map.get(selected_profile, "hunyuan15_t2v_480_fp8_distilled"),
            "qwen_image_text_encoder_fp8",
            "hunyuan15_byt5",
            "hunyuan15_vae",
        ]
        if is_i2v:
            required_assets.append("hunyuan15_sigclip")
        required_nodes = [
            "UNETLoader",
            "DualCLIPLoader",
            "ModelSamplingSD3",
            "BasicScheduler",
            "CFGGuider",
            "SamplerCustomAdvanced",
            "VAEDecode",
            "CreateVideo",
            "SaveVideo",
        ]
        if is_i2v:
            required_nodes.extend(["CLIPVisionLoader", "CLIPVisionEncode", "HunyuanVideo15ImageToVideo"])
        else:
            required_nodes.append("EmptyHunyuanVideo15Latent")
        generation_ready = all_assets(*required_assets) and all_nodes(*required_nodes)
        generation_status = "ok" if generation_ready and accelerator == "cuda" else "warn" if generation_ready else "blocked"
        selected_label = str(selected_catalog.get("label") or "HunyuanVideo 1.5")
        recommendations.extend(
            [
                {
                    "step": "关键帧",
                    "status": "ok",
                    "recommended": ["上传 PNG/JPG 关键帧" if is_i2v else "T2V 可不上传关键帧"],
                    "reason": "I2V 档使用 SigCLIP 和起始帧双条件稳定主体。" if is_i2v else "当前是文字生视频档，不要求关键帧。",
                },
                {
                    "step": "视频生成",
                    "status": generation_status,
                    "recommended": [selected_label, "先生成短镜头再提高分辨率和时长"],
                    "reason": "模型与 ComfyUI 原生节点已就绪。" if generation_ready else "主模型、双文本编码器、VAE 或原生 HunyuanVideo 1.5 节点尚未补齐。",
                },
                {
                    "step": "闪烁修复",
                    "status": "ok" if tool_ok.get("ffmpeg") else "blocked",
                    "recommended": ["ffmpeg deflicker + hqdn3d"],
                    "reason": "用于曝光和细纹理闪烁；结构漂移仍应重生成。",
                },
                {
                    "step": "插帧",
                    "status": "ok" if all_assets("rife49") and all_nodes("RIFE VFI") else "blocked",
                    "recommended": ["RIFE 4.9 2x"],
                    "reason": "生成完成后按需提高帧率。",
                },
                upscale_recommendation("480P 档建议在最终成片时做 2x 超分"),
                {
                    "step": "拼接剪辑",
                    "status": "ok" if tool_ok.get("ffmpeg") else "blocked",
                    "recommended": ["本地 ffmpeg 顺序拼接"],
                    "reason": "把多个短镜头统一尺寸和帧率后合成。",
                },
            ]
        )
        return consolidated_recommendations(recommendations)

    if selected_profile in {"ltx098", "mac-low", "mac-balanced"}:
        generation_ready = all_assets("ltx_2b_098", "t5xxl_fp16") and all_nodes(
            "CheckpointLoaderSimple",
            "CLIPLoader",
            "CLIPTextEncode",
            "LTXVConditioning",
            "LTXVScheduler",
            "LTXVImgToVideo",
            "SamplerCustom",
            "VAEDecode",
            "CreateVideo",
            "SaveVideo",
        )
        generation_status = "ok" if generation_ready and accelerator in {"cuda", "mps"} else "warn" if generation_ready else "blocked"
        selected_label = str(selected_catalog.get("label") or "LTXV 0.9.8 2B")
        post_ready = bool(tool_ok.get("ffmpeg"))
        rife_ready = all_assets("rife49") and all_nodes("RIFE VFI")
        recommendations.extend(
            [
                {
                    "step": "关键帧",
                    "status": "ok",
                    "recommended": ["优先上传关键帧", "无图时也可切换同系列 T2V"],
                    "reason": "轻量模型更适合用关键帧锁定主体和构图。",
                },
                {
                    "step": "视频生成",
                    "status": generation_status,
                    "recommended": [selected_label, "先用 512x320 / 2 秒跑通"],
                    "reason": "模型和 LTX 原生节点已就绪。" if generation_ready else "LTX checkpoint、文本编码器或原生节点尚未补齐。",
                },
                {
                    "step": "闪烁修复",
                    "status": "ok" if post_ready else "blocked",
                    "recommended": ["ffmpeg deflicker + hqdn3d"],
                    "reason": "轻量模型建议在短镜头生成后做曝光和纹理稳定。",
                },
                {
                    "step": "插帧",
                    "status": "ok" if rife_ready else "blocked",
                    "recommended": ["RIFE 4.9 2x"],
                    "reason": "按需提高运动流畅度。",
                },
                upscale_recommendation("低分辨率先确认内容，再对选中的成片超分"),
                {
                    "step": "拼接剪辑",
                    "status": "ok" if post_ready else "blocked",
                    "recommended": ["本地 ffmpeg 顺序拼接"],
                    "reason": "把多个短镜头统一尺寸和帧率后合成。",
                },
            ]
        )
        return consolidated_recommendations(recommendations)

    if selected_profile == "minimax-h3-fl2va-int8":
        generation_ready = all_assets(
            "minimax_h3_fl2va_int8",
            "minimax_h3_text_int8",
            "minimax_h3_video_vae",
            "minimax_h3_audio_vae",
        ) and all_nodes(
            "UNETLoader",
            "CLIPLoader",
            "VAELoader",
            "MiniMaxH3ImageToVideo",
            "MiniMaxH3SigmaShift",
            "SamplerCustomAdvanced",
            "VAEDecode",
            "VAEDecodeAudio",
            "CreateVideo",
            "SaveVideo",
        )
        if not generation_ready:
            generation_status = "blocked"
        elif accelerator == "cuda" and max_vram >= 80:
            generation_status = "ok"
        else:
            generation_status = "warn"
        selected_label = str(selected_catalog.get("label") or "MiniMax H3 FL2VA INT8")
        post_ready = bool(tool_ok.get("ffmpeg"))
        rife_ready = all_assets("rife49") and all_nodes("RIFE VFI")
        recommendations.extend(
            [
                {
                    "step": "关键帧",
                    "status": "ok",
                    "recommended": ["可不上传直接 T2V", "上传首帧或首尾帧可加强构图控制"],
                    "reason": "H3 同时支持文字生音视频、首帧 I2V 和首尾帧 FL2VA。",
                },
                {
                    "step": "视频生成",
                    "status": generation_status,
                    "recommended": [selected_label, "固定 24 FPS", "先用 480P / 3 秒验证音画"],
                    "reason": (
                        "模型、视频/音频 VAE 与 ComfyUI 原生节点已就绪。"
                        if generation_ready
                        else "H3 主模型、Qwen3-VL 文本编码器、视频/音频 VAE 或 ComfyUI 原生节点尚未补齐。"
                    ),
                },
                {
                    "step": "闪烁修复",
                    "status": "ok" if post_ready else "blocked",
                    "recommended": ["ffmpeg deflicker + hqdn3d"],
                    "reason": "只修曝光和细纹理跳动；音画内容或主体漂移应缩短镜头后重生成。",
                },
                {
                    "step": "插帧",
                    "status": "ok" if rife_ready else "blocked",
                    "recommended": ["RIFE 4.9 2x"],
                    "reason": "原片固定 24 FPS，可在成片前按需插到 48 FPS。",
                },
                upscale_recommendation("先用较低分辨率确认动作和声音，再对最终短镜头做超分"),
                {
                    "step": "拼接剪辑",
                    "status": "ok" if post_ready else "blocked",
                    "recommended": ["本地 ffmpeg 顺序拼接"],
                    "reason": "短镜头分段生成后统一尺寸、帧率并保留可用音轨。",
                },
            ]
        )
        return consolidated_recommendations(recommendations)

    has_flux = (base_dir / "models" / "diffusion_models" / "flux2_dev_fp8mixed.safetensors").exists()
    has_sdxl = any((base_dir / "models" / "checkpoints").glob("*.safetensors"))
    keyframe_models = ["上传 PNG/JPG 关键帧"]
    if has_flux:
        keyframe_models.insert(0, "Flux/Flux2 本地生图")
    if has_sdxl:
        keyframe_models.insert(0, "SDXL 本地生图")
    recommendations.append(
        {
            "step": "关键帧",
            "status": "ok" if has_flux or has_sdxl else "warn",
            "recommended": keyframe_models,
            "reason": "检测到本地生图模型，可先生成首帧。" if has_flux or has_sdxl else "未检测到本地生图模型，也可以直接上传外部生成的关键帧。",
        }
    )

    ti2v_ready = all_assets("ti2v_5b", "umt5", "wan22_vae") and all_nodes(
        "Wan22ImageToVideoLatent", "UNETLoader", "CLIPLoader", "VAELoader"
    )
    ltx_ready = all_assets("ltx_2b_098", "t5xxl_fp16") and all_nodes(
        "CheckpointLoaderSimple",
        "CLIPLoader",
        "CLIPTextEncode",
        "LTXVConditioning",
        "LTXVScheduler",
        "LTXVImgToVideo",
        "SamplerCustom",
        "VAEDecode",
        "CreateVideo",
        "SaveVideo",
    )
    if platform_strategy == "mac_mps":
        if ltx_ready and mac_mps_ready:
            status_text = "ok"
            reason = f"检测到 Apple Silicon 与约 {mac_memory:g}GB 统一内存，默认用 LTX 短镜头跑通 Mac 视频生成。"
        elif ltx_ready:
            status_text = "warn"
            reason = "LTX 模型和节点已在，但当前没有确认 ComfyUI 的 MPS torch 状态；可先跑低分辨率 smoke test。"
        else:
            status_text = "warn"
            reason = "Mac 默认走 LTX 小模型路线；一键配置会先补齐 LTX 2B 与 T5 文本编码器。"
        recommended_ltx = ["Mac LTX I2V 低档/均衡档", "512x320 或 576x320", "2 到 3 秒短镜头"]
        if mac_tier in {"mac_ltx_quality", "mac_wan5b_480p", "mac_wan5b_720p_experimental"}:
            recommended_ltx = ["Mac LTX I2V 质量档", "704x416 或 768x512", "2 到 4 秒短镜头"]
        recommendations.append(
            {
                "step": "视频生成",
                "status": status_text,
                "recommended": recommended_ltx,
                "reason": reason,
            }
        )
    elif not ti2v_ready:
        status_text = "blocked"
        reason = "TI2V-5B 所需模型或 ComfyUI 节点不完整。"
    elif accelerator == "cuda" and max_vram >= 24:
        status_text = "ok"
        reason = f"单卡可用显存档位足够跑 720P 视频，检测到最高单卡约 {max_vram:g}GB。"
    elif accelerator == "cuda" and max_vram >= 16:
        status_text = "warn"
        reason = "可尝试较短镜头或降低分辨率；建议开启 offload。"
    elif is_macos and accelerator == "mps":
        status_text = "warn"
        reason = "macOS 可作为兼容目标，但 Wan 视频节点在 MPS 上通常更慢且更挑版本。"
    else:
        status_text = "blocked"
        reason = "未检测到适合本地视频生成的 GPU 后端。"
    if platform_strategy != "mac_mps":
        draft_recommended = ["Wan2.2 TI2V-5B 720P", "横屏 1280x704 / 竖屏 704x1280", "3 到 5 秒短镜头"]
        if post_only_video:
            draft_recommended = ["当前硬件不建议本地生视频", "可上传外部视频进入后期", "或换 CUDA / Apple Silicon MPS 环境"]
        recommendations.append(
            {
                "step": "视频生成",
                "status": status_text,
                "recommended": draft_recommended,
                "reason": reason,
            }
        )

    i2v_ready = all_assets(
        "i2v_high",
        "i2v_low",
        "umt5",
        "wan21_vae",
        "i2v_lora_high",
        "i2v_lora_low",
    ) and all_nodes("WanImageToVideo", "KSamplerAdvanced", "LoraLoaderModelOnly")
    if platform_strategy == "mac_mps":
        if mac_tier == "mac_wan5b_720p_experimental":
            formal_status = "warn" if ti2v_ready else "blocked"
            formal_recommended = ["Wan2.2 TI2V-5B 720P 高内存实验档", "优先关键帧 I2V/TI2V", "先跑 smoke test"]
            formal_reason = "96GB/128GB+ Apple Silicon 可以尝试 Wan5B 720P 短镜头，但仍需通过 MPS dtype 与节点预检；A14B 不默认开放。"
        elif mac_tier == "mac_wan5b_480p":
            formal_status = "warn" if ti2v_ready else "blocked"
            formal_recommended = ["Wan2.2 TI2V-5B 480P 实验档", "短镜头", "必要时降低帧数"]
            formal_reason = "48GB/64GB Apple Silicon 可尝试 Wan5B 480P；720P 仍标为实验。"
        else:
            formal_status = "ok" if ltx_ready and mac_mps_ready else "warn"
            if mac_tier == "mac_ltx_low":
                formal_recommended = ["Mac LTX I2V 低档", "512x320", "1 到 2 秒短镜头"]
                formal_reason = "该 Mac 档位优先保证跑通，正式画质通过更短分镜、去闪烁和后期超分补足。"
            else:
                formal_recommended = ["Mac LTX I2V 质量档", "短镜头分镜", "后期超分"]
                formal_reason = "该 Mac 档位更适合 LTX 小模型短片段，正式画质通过分镜、去闪烁和超分补足。"
        recommendations.append(
            {
                "step": "视频生成",
                "status": formal_status,
                "recommended": formal_recommended,
                "reason": formal_reason,
            }
        )
    elif accelerator == "cuda" and max_vram >= 80:
        status_text = "ok" if i2v_ready else "blocked"
        reason = (
            f"适合跑 A14B 720P 高质量视频，最高单卡约 {max_vram:g}GB。"
            if i2v_ready
            else "A14B I2V 所需模型、LoRA、VAE 或节点不完整。"
        )
        formal_recommended = ["Wan2.2 I2V-A14B fp8 + 4步 LoRA", "优先图生视频", "720P 3 到 5 秒"]
    elif accelerator == "cuda" and max_vram >= 48:
        status_text = "ok" if ti2v_ready else "blocked"
        reason = (
            "48GB 保守档默认用 Wan2.2 TI2V-5B；A14B 480P 只作为手动尝试。"
            if ti2v_ready
            else "Wan2.2 TI2V-5B 所需模型、VAE、文本编码器或节点不完整。"
        )
        formal_recommended = ["Wan2.2 TI2V-5B 720P 高质量", "A14B 480P 可手动尝试", "短镜头后期超分"]
    elif accelerator == "cuda" and max_vram >= 16:
        status_text = "ok" if ti2v_ready else "blocked"
        reason = (
            "16GB 到 24GB 更适合 Wan2.2 TI2V-5B 480P/短镜头；A14B 不作为默认路线。"
            if ti2v_ready
            else "Wan2.2 TI2V-5B 所需模型、VAE、文本编码器或节点不完整。"
        )
        formal_recommended = ["Wan2.2 TI2V-5B 480P 小显存质量", "短镜头", "必要时降低帧数"]
    elif not i2v_ready:
        status_text = "blocked"
        reason = "A14B I2V 所需模型、LoRA、VAE 或节点不完整。"
        formal_recommended = ["Wan2.2 I2V-A14B fp8 + 4步 LoRA", "优先图生视频", "720P 3 到 5 秒"]
    elif gpu_count >= 2 and sum_vram >= 80:
        status_text = "warn"
        reason = "多卡总显存足够，但单个 ComfyUI 视频任务通常更看单卡显存；可并行跑镜头，不等价于单卡 96GB。"
        formal_recommended = ["Wan2.2 I2V-A14B fp8 + 4步 LoRA", "优先图生视频", "720P 3 到 5 秒"]
    else:
        status_text = "blocked"
        reason = "A14B 720P 高质量档建议至少 80GB 单卡显存；当前环境不建议直接运行。"
        formal_recommended = ["Wan2.2 I2V-A14B fp8 + 4步 LoRA", "优先图生视频", "720P 3 到 5 秒"]
    if platform_strategy != "mac_mps":
        final_recommended = formal_recommended
        if post_only_video:
            final_recommended = ["当前硬件不建议本地生视频", "先用外部视频或更强 GPU 生成", "本机可继续做去闪烁、插帧、超分"]
        recommendations.append(
            {
                "step": "视频生成",
                "status": status_text,
                "recommended": final_recommended,
                "reason": reason,
            }
        )

    t2v_ready = all_assets(
        "t2v_high",
        "t2v_low",
        "umt5",
        "wan21_vae",
        "t2v_lora_high",
        "t2v_lora_low",
    ) and all_nodes("EmptyHunyuanLatentVideo", "KSamplerAdvanced", "LoraLoaderModelOnly")
    if platform_strategy == "mac_mps":
        recommendations.append(
            {
                "step": "无图生视频",
                "status": "ok" if ltx_ready and mac_mps_ready else "warn",
                "recommended": ["Mac LTX T2V 低档/均衡档"],
                "reason": "Mac 上也可以文字生视频，但仍建议优先 I2V，人物和空间更可控。",
            }
        )
    else:
        recommendations.append(
            {
                "step": "无图生视频",
                "status": "ok" if t2v_ready and accelerator == "cuda" and max_vram >= 80 else "warn" if t2v_ready else "blocked",
                "recommended": ["Wan2.2 T2V-A14B fp8 + 4步 LoRA"],
                "reason": "可用，但品牌、人物和空间一致性不如 I2V；建议只在没有关键帧时使用。"
                if t2v_ready
                else "T2V-A14B 所需模型或节点不完整。",
            }
        )

    deflicker_ok = tool_ok.get("ffmpeg") and tool_ok.get("ffmpeg:deflicker") and tool_ok.get("ffmpeg:hqdn3d")
    recommendations.append(
        {
            "step": "闪烁修复",
            "status": "ok" if deflicker_ok else "blocked",
            "recommended": ["ffmpeg deflicker + hqdn3d"],
            "reason": "可修正曝光闪烁和轻微纹理跳动；人物结构变形仍要回到生成步骤重跑。"
            if deflicker_ok
            else "未检测到 ffmpeg 或所需滤镜。",
        }
    )

    rife_ready = asset_ok.get("rife49") and custom_ok.get("frame_interpolation") and all_nodes("RIFE VFI")
    recommendations.append(
        {
            "step": "插帧",
            "status": "ok" if rife_ready and accelerator == "cuda" else "warn" if rife_ready else "blocked",
            "recommended": ["RIFE 4.9 2x 插帧"],
            "reason": "CUDA 下适合把 24fps 提到 48fps。"
            if rife_ready and accelerator == "cuda"
            else "权重和节点已在，但非 CUDA 后端可能很慢或需要额外兼容配置。"
            if rife_ready
            else "RIFE 权重或自定义节点未就绪。",
        }
    )

    recommendations.append(upscale_recommendation("适合最终成片处理"))

    recommendations.append(
        {
            "step": "拼接剪辑",
            "status": "ok" if tool_ok.get("ffmpeg") else "blocked",
            "recommended": ["平台内置 ffmpeg 顺序拼接", "剪映 / DaVinci Resolve / Premiere Pro 精剪"],
            "reason": "平台可先把同一项目的短镜头统一尺寸、帧率并顺序拼接，再交给剪辑软件调色、字幕和声音。"
            if tool_ok.get("ffmpeg")
            else "本地拼接需要 ffmpeg；安装后即可在第 8 步直接输出完整 MP4。",
        }
    )
    return consolidated_recommendations(recommendations)


def workflow_advanced_param_schema(
    mode: str, assets: list[dict[str, Any]], node_checks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    schema = video_params.param_schema(mode)
    asset_ok = {item["id"]: bool(item["ok"]) for item in assets}
    nodes = {item["name"]: item for item in node_checks}
    for spec in schema:
        dependencies = {
            "h3_task": ("minimax_h3_fun_control_int8", "MiniMaxH3FunControlNetApply"),
            "h3_latent_upscale": ("minimax_h3_latent_upscale_3d", "MinimaxH3LatentUpscaler3D"),
        }
        if spec["id"] in dependencies:
            asset_id, node_name = dependencies[spec["id"]]
            spec["dependency_status"] = {
                "asset_ok": asset_ok.get(asset_id, False), "node_ok": bool(nodes.get(node_name, {}).get("ok")),
                "asset_id": asset_id, "node": node_name, "install_profile": "minimax-h3-creative-addon",
            }
        if spec["id"] == "h3_attention_backend":
            available = "comfy kitchen attention" in nodes.get("ModelAttentionBackend", {}).get("options", [])
            spec["choice_status"] = {"kitchen_int8": {
                "state": "installed" if available else "unchecked", "label": "内核已注册·待验证" if available else "待内核预检",
                "message": "仅修改 H3 模型的 Attention，不替换全局后端。",
            }}
        if spec["id"] != "h3_acceleration_profile":
            continue
        statuses = {}
        for key in spec["choices"]:
            recipe = video_params.H3_RUNTIME_PROFILES.get(key, {})
            status = {"state": "unchecked", "label": "待预检", "message": "提交前将检查模型、节点及硬件；尚未进行生成验证。"}
            if recipe.get("asset_id"):
                installed = asset_ok.get(recipe["asset_id"], False)
                status = {
                    "state": "installed" if installed else "missing",
                    "label": "LoRA 已齐·待预检" if installed else "缺少 LoRA",
                    "message": ("文件检查通过，仍需 ComfyUI 预检和生成验证。" if installed else
                                "请在下载中心安装此版本，然后刷新环境并重新预检：") + recipe["lora_name"],
                    "asset_id": recipe["asset_id"],
                }
            elif recipe.get("required_node"):
                node_check = nodes.get(recipe["required_node"], {})
                loaded = bool(node_check.get("ok"))
                offline = not node_check or node_check.get("reason") == "ComfyUI 未连接"
                status = {
                    "state": "installed" if loaded else "unchecked" if offline else "missing",
                    "label": "节点已加载·待预检" if loaded else "未连接·待预检" if offline else "缺少节点",
                    "message": f"需要 {recipe['required_node']}；已加载不代表生成效果已验证。",
                }
            statuses[key] = status
        spec["choice_status"] = statuses
    return schema


def workflow_model_options(
    *,
    os_info: dict[str, Any],
    hardware: dict[str, Any],
    assets: list[dict[str, Any]],
    custom_nodes: list[dict[str, Any]],
    tool_checks: list[dict[str, Any]],
    node_checks: list[dict[str, Any]],
    base_dir: Path | None = None,
    selected_model_id: str | None = None,
) -> dict[str, Any]:
    base_dir = (base_dir or BASE_DIR).expanduser().resolve()
    asset_ok = {item["id"]: bool(item["ok"]) for item in assets}
    node_ok = {item["name"]: bool(item["ok"]) for item in node_checks}
    custom_ok = {item["id"]: bool(item["ok"]) for item in custom_nodes}
    tool_ok = {item["name"]: bool(item["ok"]) for item in tool_checks}
    accelerator = hardware.get("accelerator")
    max_vram = float(hardware.get("max_vram_gb") or 0)
    is_macos = os_info["name"] == "Darwin"
    platform_strategy = hardware.get("platform_strategy")
    mac_tier = str(hardware.get("mac_video_tier") or "")
    mac_info = hardware.get("mac") or {}
    mac_memory = float(mac_info.get("unified_memory_gb") or hardware.get("system_memory_gb") or 0)
    mac_mps_ready = bool(hardware.get("front_torch_mps_ready") or hardware.get("comfy_torch_mps_ready"))
    post_only_video = platform_strategy in {"post_only", "mac_post_only"} or accelerator == "cpu"
    fal_ready = bool(fal_api_key())

    def all_assets(*ids: str) -> bool:
        return all(asset_ok.get(item) for item in ids)

    def all_nodes(*names: str) -> bool:
        return all(node_ok.get(item) for item in names)

    def cuda_status(*, ready: bool, ok_gb: float, warn_gb: float, mac_warn: bool = False) -> str:
        if not ready:
            return "blocked"
        if accelerator == "cuda" and max_vram >= ok_gb:
            return "ok"
        if accelerator == "cuda" and max_vram >= warn_gb:
            return "warn"
        if is_macos and accelerator == "mps" and mac_warn:
            return "warn"
        return "blocked"

    def mac_ltx_status(ready: bool) -> str:
        if platform_strategy != "mac_mps":
            return "blocked"
        if not ready:
            return "blocked"
        if ready and mac_mps_ready:
            return "ok"
        return "warn"

    def ltx_status(ready: bool) -> str:
        if not ready:
            return "blocked"
        if accelerator == "cuda":
            return "ok" if max_vram >= 12 else "warn"
        if accelerator == "mps":
            return "ok" if mac_mps_ready else "warn"
        return "warn"

    def mac_wan5b_status(ready: bool, *, min_memory_gb: float) -> str:
        if platform_strategy != "mac_mps" or mac_memory < min_memory_gb:
            return "blocked"
        if not ready:
            return "blocked"
        if ready and mac_mps_ready:
            return "warn"
        return "warn"

    def option(
        *,
        id: str,
        label: str,
        step: str,
        mode: str,
        status: str,
        reason: str,
        defaults: dict[str, Any] | None = None,
        uses_image: bool = True,
        model_label: str | None = None,
        supported: bool = True,
        scale: float | None = None,
        upscale_model: str | None = None,
        rife_multiplier: int | None = None,
        unrestricted: dict[str, Any] | None = None,
        install_profile: str | None = None,
        variant_group: str | None = None,
    ) -> dict[str, Any]:
        inferred_install_profile = install_profile
        if inferred_install_profile is None:
            inferred_install_profile = {
                "ti2v_5b": "mac-wan5b" if id.startswith("mac_") else "cuda-wan5b",
                "i2v_a14b": "cuda-a14b",
                "t2v_a14b": "cuda-a14b",
                "ltx_i2v": "mac-balanced" if id.startswith("mac_") else "ltx098",
                "ltx_t2v": "mac-balanced" if id.startswith("mac_") else "ltx098",
                "ltx23_t2v": "ltx23-fp8-dev",
                "ltx23_i2v": "ltx23-fp8-dev",
                "ltx25_t2v": "ltx25-distilled-int8",
                "ltx25_i2v": "ltx25-distilled-int8",
                "minimax_h3_t2v": "minimax-h3-fl2va-int8",
                "minimax_h3_i2v": "minimax-h3-fl2va-int8",
                "minimax_h3_r2v": "minimax-h3-ref2va-int8",
                "fal_h3_max_t2v": "fal-h3-max-api",
                "fal_h3_max_i2v": "fal-h3-max-api",
                "deflicker": "post-only",
                "rife_2x": "post-only",
                "upscale_2x": "post-only",
                "upscale_seedvr2": "seedvr2-upscale",
            }.get(mode)
        capabilities = video_params.mode_capabilities(mode)
        if capabilities["kind"] == "generation":
            image_required = capabilities["image_input"] == "required"
            image_optional = capabilities["image_input"] == "optional"
            uses_image = capabilities["image_to_video"]
        else:
            image_required = mode in REQUIRED_IMAGE_WORKFLOW_MODES
            image_optional = False
        if mode == "external_workflow":
            option_group = "外部 / 手动工作流"
        elif mode == "unsupported":
            option_group = "环境状态"
        elif capabilities["kind"] == "generation":
            if capabilities["text_to_video"] and capabilities["image_to_video"]:
                task_label = "图文生视频"
            elif capabilities["image_to_video"]:
                task_label = "图生视频"
            else:
                task_label = "文字生视频"
            if capabilities["native_audio"]:
                task_label = f"{task_label} + 原生音频"
            option_group = f"{capabilities['engine_label']} · {task_label}"
        else:
            option_group = "后期处理"
        if capabilities["text_to_video"] and capabilities["image_to_video"]:
            variant_role = "hybrid"
        elif capabilities["image_to_video"]:
            variant_role = "image"
        elif capabilities["text_to_video"]:
            variant_role = "text"
        else:
            variant_role = capabilities["kind"]
        inferred_variant_group = variant_group
        if not inferred_variant_group and capabilities["kind"] == "generation":
            inferred_variant_group = re.sub(r"(^|_)(?:t2v|i2v)(?=_|$)", r"\1video", id)
        catalog_id = ""
        if capabilities["kind"] == "generation":
            profile_matches = [
                item
                for item in MODEL_CATALOG
                if inferred_install_profile
                and str(item.get("default_install_profile") or "") == inferred_install_profile
            ]
            mode_matches = [
                item
                for item in MODEL_CATALOG
                if mode in set((item.get("workflow_modes") or {}).values())
            ]
            matched_catalog = next(
                (
                    item
                    for item in profile_matches
                    if mode in set((item.get("workflow_modes") or {}).values())
                ),
                None,
            )
            matched_catalog = matched_catalog or (profile_matches[0] if profile_matches else None)
            matched_catalog = matched_catalog or (mode_matches[0] if mode_matches else None)
            catalog_id = str((matched_catalog or {}).get("id") or "")
        return {
            "id": id,
            "label": label,
            "step": step,
            "mode": mode,
            "status": status,
            "reason": reason,
            "defaults": defaults or {},
            "uses_image": uses_image,
            "image_optional": image_optional,
            "image_required": image_required,
            "group": option_group,
            "engine": capabilities["engine"],
            "engine_label": capabilities["engine_label"],
            "variant_group": inferred_variant_group or id,
            "variant_role": variant_role,
            "capabilities": capabilities,
            "capability_labels": video_params.capability_labels(mode),
            "counterparts": {},
            "model_label": model_label or label,
            "supported": supported,
            "scale": scale,
            "upscale_model": upscale_model,
            "rife_multiplier": rife_multiplier,
            "unrestricted": unrestricted,
            "install_profile": inferred_install_profile,
            "catalog_id": catalog_id,
            # 前端照着这份 schema 动态渲染高级参数抽屉，加新模型不用改 HTML。
            "advanced_params": workflow_advanced_param_schema(mode, assets, node_checks),
            "supports_end_image": capabilities["last_frame"],
        }

    def attach_generation_counterparts(items: list[dict[str, Any]]) -> None:
        generation_items = [item for item in items if (item.get("capabilities") or {}).get("kind") == "generation"]

        def candidate_for(source: dict[str, Any], capability: str) -> dict[str, Any] | None:
            candidates = [
                item
                for item in generation_items
                if (item.get("capabilities") or {}).get(capability) and item.get("supported") is not False
            ]
            if not candidates:
                return None
            status_rank = {"ok": 0, "warn": 1, "blocked": 2}
            return min(
                candidates,
                key=lambda item: (
                    0 if item.get("variant_group") == source.get("variant_group") else 1,
                    0 if item.get("install_profile") == source.get("install_profile") else 1,
                    0 if item.get("engine") == source.get("engine") else 1,
                    status_rank.get(str(item.get("status") or "blocked"), 3),
                    str(item.get("id") or ""),
                ),
            )

        for item in generation_items:
            text_variant = candidate_for(item, "text_to_video")
            image_variant = candidate_for(item, "image_to_video")
            item["counterparts"] = {
                "text": str((text_variant or {}).get("id") or ""),
                "image": str((image_variant or {}).get("id") or ""),
            }

    ti2v_ready = all_assets("ti2v_5b", "umt5", "wan22_vae") and all_nodes(
        "Wan22ImageToVideoLatent", "UNETLoader", "CLIPLoader", "VAELoader", "KSampler"
    )
    seedvr2_nodes_ready = all_nodes(
        "UNETLoader",
        "VAELoader",
        "ImageScaleBy",
        "VAEEncodeTiled",
        "SeedVR2Preprocess",
        "SeedVR2TemporalChunk",
        "SeedVR2Conditioning",
        "SeedVR2TemporalMerge",
        "VAEDecodeTiled",
        "SeedVR2PostProcessing",
        "VHS_LoadVideo",
        "VHS_VideoCombine",
    )
    seedvr2_vae_ready = all_assets("seedvr2_vae_fp16")
    seedvr2_3b_ready = seedvr2_vae_ready and all_assets("seedvr2_3b_int8") and seedvr2_nodes_ready
    seedvr2_7b_ready = seedvr2_vae_ready and all_assets("seedvr2_7b_nvfp4") and seedvr2_nodes_ready
    seedvr2_7b_sharp_ready = seedvr2_vae_ready and all_assets("seedvr2_7b_sharp_nvfp4") and seedvr2_nodes_ready
    seedvr2_ready = seedvr2_3b_ready
    i2v_ready = all_assets(
        "i2v_high",
        "i2v_low",
        "umt5",
        "wan21_vae",
        "i2v_lora_high",
        "i2v_lora_low",
    ) and all_nodes("WanImageToVideo", "KSamplerAdvanced", "LoraLoaderModelOnly")
    t2v_ready = all_assets(
        "t2v_high",
        "t2v_low",
        "umt5",
        "wan21_vae",
        "t2v_lora_high",
        "t2v_lora_low",
    ) and all_nodes("EmptyHunyuanLatentVideo", "KSamplerAdvanced", "LoraLoaderModelOnly")
    wan_i2v_unrestricted = {
        "status": "community_addon",
        "label": "成熟社区 High/Low 双 LoRA",
        "toggle_enabled": True,
        "addon_profile": "wan22-i2v-unrestricted-addon",
        "addon_ready": all_assets("wan22_i2v_nsfw_high", "wan22_i2v_nsfw_low"),
        "source": "https://huggingface.co/lopi999/Wan2.2-I2V_General-NSFW-LoRA",
        "trigger": "nsfwsks",
        "note": "仅兼容 Wan2.2 A14B I2V；High/Low 必须成对加载并使用相同强度。",
        "strength_default": 0.8,
        "strength_min": 0.0,
        "strength_max": 1.2,
        "strength_step": 0.05,
        "strength_recommended": "0.60-0.95",
        "strength_help": "0.60-0.95 通常较平衡；同一数值会同时应用到 High/Low 两个 LoRA。超过 1.00 可能增加闪烁、形体漂移和纹理伪影。0 表示不加载效果。",
    }
    wan_t2v_unrestricted = {
        "status": "community_addon",
        "label": "实验性复用 I2V NSFW-22 双 LoRA",
        "toggle_enabled": True,
        "addon_profile": "wan22-i2v-unrestricted-addon",
        "lora_enabled": True,
        "addon_ready": all_assets("wan22_i2v_nsfw_high", "wan22_i2v_nsfw_low"),
        "source": "https://huggingface.co/lopi999/Wan2.2-I2V_General-NSFW-LoRA",
        "trigger": "",
        "note": "T2V 实验性复用与 I2V 相同的社区 NSFW-22 H/L 双 LoRA；High/Low 须成对加载并使用相同强度。",
        "strength_default": 0.8,
        "strength_min": 0.0,
        "strength_max": 1.2,
        "strength_step": 0.05,
        "strength_recommended": "0.60-0.95",
        "strength_help": "0.60-0.95 通常较平衡；同一数值会同时应用到 High/Low 两个 LoRA。超过 1.00 可能增加闪烁与形体漂移。",
    }
    h3_unrestricted = {
        "status": "prompt_passthrough",
        "label": "按原文生成",
        "toggle_enabled": True,
        "addon_ready": True,
        "lora_enabled": False,
        "trigger": "",
        "note": "H3 官方图没有负面条件，也不套用 Wan NSFW-22。开启后按提示词原文生成，可选用自定义触发词。",
    }
    ltx25_unrestricted = {
        "status": "prompt_passthrough",
        "label": "按原文生成",
        "toggle_enabled": True,
        "addon_ready": True,
        "lora_enabled": False,
        "trigger": "",
        "note": "LTX 2.5 暂无专用 LoRA，不套用 Wan NSFW-22。开启后按提示词原文生成，并可清理负面词里的冲突词。",
    }
    ltx_ready = all_assets("ltx_2b_098", "t5xxl_fp16") and all_nodes(
        "CheckpointLoaderSimple",
        "CLIPLoader",
        "CLIPTextEncode",
        "LTXVConditioning",
        "LTXVScheduler",
        "LTXVImgToVideo",
        "SamplerCustom",
        "VAEDecode",
        "CreateVideo",
        "SaveVideo",
    )
    ltx23_nodes_ready = all_nodes(
        "CheckpointLoaderSimple",
        "LTXAVTextEncoderLoader",
        "CLIPTextEncode",
        "LTXVConditioning",
        "LTXVAudioVAELoader",
        "LTXVEmptyLatentAudio",
        "EmptyLTXVLatentVideo",
        "LTXVConcatAVLatent",
        "RandomNoise",
        "KSamplerSelect",
        "ManualSigmas",
        "CFGGuider",
        "SamplerCustomAdvanced",
        "LTXVSeparateAVLatent",
        "LatentUpscaleModelLoader",
        "LTXVLatentUpsampler",
        "LTXVCropGuides",
        "LTXVPreprocess",
        "LTXVImgToVideoInplace",
        "LoadImage",
        "VAEDecodeTiled",
        "LTXVAudioVAEDecode",
        "CreateVideo",
        "SaveVideo",
    )
    ltx23_dev_ready = all_assets(
        "ltx23_fp8_dev",
        "ltx23_gemma3_fp4",
        "ltx23_spatial_upscaler",
        "ltx23_distilled_lora",
    ) and ltx23_nodes_ready
    ltx23_nvfp4_ready = all_assets(
        "ltx23_nvfp4_dev",
        "ltx23_gemma3_fp4",
        "ltx23_spatial_upscaler",
        "ltx23_distilled_lora",
    ) and ltx23_nodes_ready
    ltx25_nodes_ready = all_nodes(
        "UNETLoader",
        "CLIPLoader",
        "VAELoader",
        "CLIPTextEncode",
        "EmptyLTXVLatentVideo",
        "LTXVConditioning",
        "LTXVEmptyLatentAudio",
        "LTXVConcatAVLatent",
        "RandomNoise",
        "KSamplerSelect",
        "SamplerEulerAncestral",
        "ManualSigmas",
        "LTXVDualCFGGuider",
        "SamplerCustomAdvanced",
        "LTXVSeparateAVLatent",
        "LatentUpscaleModelLoader",
        "LTXVLatentUpsampler",
        "LTXVCropGuides",
        "LTXVPreprocess",
        "LTXVImgToVideoInplace",
        "LTXVAddGuide",
        "LoadImage",
        "VAEDecodeTiled",
        "LTXVAudioVAEDecode",
        "ModelPatchLoader",
        "LTXVDurationPredictor",
        "CreateVideo",
        "SaveVideo",
    )
    ltx25_shared_ready = all_assets(
        "ltx25_text_int8",
        "ltx25_video_vae_diff",
        "ltx25_video_vae_conv",
        "ltx25_audio_vae",
        "ltx25_spatial_upscaler",
        "ltx25_duration_head",
    )
    ltx25_int8_ready = ltx25_shared_ready and all_assets("ltx25_distilled_int8") and ltx25_nodes_ready
    ltx25_nvfp4_ready = ltx25_shared_ready and all_assets("ltx25_distilled_nvfp4") and ltx25_nodes_ready
    hunyuan15_t2v_nodes_ready = all_nodes(
        "UNETLoader",
        "DualCLIPLoader",
        "VAELoader",
        "ModelSamplingSD3",
        "CLIPTextEncode",
        "EmptyHunyuanVideo15Latent",
        "BasicScheduler",
        "CFGGuider",
        "SamplerCustomAdvanced",
        "BasicScheduler",
        "VAEDecode",
        "CreateVideo",
        "SaveVideo",
    )
    hunyuan15_i2v_nodes_ready = hunyuan15_t2v_nodes_ready and all_nodes(
        "LoadImage",
        "CLIPVisionLoader",
        "CLIPVisionEncode",
        "HunyuanVideo15ImageToVideo",
    )
    hunyuan15_shared_ready = all_assets("qwen_image_text_encoder_fp8", "hunyuan15_byt5", "hunyuan15_vae")
    hunyuan15_t2v_480_ready = (
        hunyuan15_shared_ready
        and all_assets("hunyuan15_t2v_480_fp8_distilled")
        and hunyuan15_t2v_nodes_ready
    )
    hunyuan15_i2v_480_ready = (
        hunyuan15_shared_ready
        and all_assets("hunyuan15_i2v_480_fp8_distilled", "hunyuan15_sigclip")
        and hunyuan15_i2v_nodes_ready
    )
    hunyuan15_t2v_720_ready = (
        hunyuan15_shared_ready and all_assets("hunyuan15_t2v_720_fp16") and hunyuan15_t2v_nodes_ready
    )
    hunyuan15_i2v_720_ready = (
        hunyuan15_shared_ready
        and all_assets("hunyuan15_i2v_720_fp16", "hunyuan15_sigclip")
        and hunyuan15_i2v_nodes_ready
    )
    minimax_h3_nodes_ready = all_nodes(
        "UNETLoader",
        "CLIPLoader",
        "VAELoader",
        "MiniMaxH3ImageToVideo",
        "MiniMaxH3SigmaShift",
        "RandomNoise",
        "KSamplerSelect",
        "BasicScheduler",
        "BasicGuider",
        "SamplerCustomAdvanced",
        "VAEDecode",
        "VAEDecodeAudio",
        "CreateVideo",
        "SaveVideo",
    )
    minimax_h3_ready = all_assets(
        "minimax_h3_fl2va_int8",
        "minimax_h3_text_int8",
        "minimax_h3_video_vae",
        "minimax_h3_audio_vae",
    ) and minimax_h3_nodes_ready
    minimax_h3_reference_nodes_ready = minimax_h3_nodes_ready and all_nodes(
        "MiniMaxH3ReferenceToVideo",
        "VHS_LoadVideo",
        "LoadAudio",
    )
    minimax_h3_reference_ready = all_assets(
        "minimax_h3_ref2va_int8",
        "minimax_h3_text_int8",
        "minimax_h3_video_vae",
        "minimax_h3_audio_vae",
    ) and minimax_h3_reference_nodes_ready
    deflicker_ready = bool(tool_ok.get("ffmpeg") and tool_ok.get("ffmpeg:deflicker") and tool_ok.get("ffmpeg:hqdn3d"))
    rife_ready = bool(asset_ok.get("rife49") and custom_ok.get("frame_interpolation") and all_nodes("RIFE VFI"))
    upscale_ready = all_nodes("UpscaleModelLoader", "ImageUpscaleWithModel")
    has_flux = (base_dir / "models" / "diffusion_models" / "flux2_dev_fp8mixed.safetensors").exists()
    has_sdxl = any((base_dir / "models" / "checkpoints").glob("*.safetensors"))

    options = {
        "keyframe": [
            option(
                id="upload_keyframe",
                label="上传关键帧（可选）",
                step="keyframe",
                mode="",
                status="ok",
                reason="可选。需要锁定人物和构图时上传；不上传则使用 T2V 文字生视频路线。",
                uses_image=True,
            ),
            option(
                id="sdxl_keyframe",
                label="SDXL 本地生图",
                step="keyframe",
                mode="",
                status="ok" if has_sdxl else "warn",
                reason="适合 8GB 以上 CUDA 或 Apple Silicon 生成关键帧；未接入自动生图按钮时可在 ComfyUI 里生成后上传。",
                uses_image=True,
                supported=False,
            ),
            option(
                id="flux_keyframe",
                label="Flux/Flux2 本地生图",
                step="keyframe",
                mode="",
                status="ok" if has_flux and (max_vram >= 24 or is_macos) else "warn",
                reason="画质和商业摄影感更强；低显存或 macOS 需要更谨慎的量化/低显存工作流。",
                uses_image=True,
                supported=False,
            ),
        ],
        "draft": [
            option(
                id="no_local_video_draft",
                label="当前硬件不建议本地生视频",
                step="draft",
                mode="unsupported",
                status="blocked",
                reason="未检测到 CUDA 或可用 Apple Silicon MPS。可以继续用本机做后期，或换更合适的硬件生成视频。",
                uses_image=False,
                supported=False,
            ),
            option(
                id="fal_h3_max_t2v",
                label="H3 Max（fal 后训练版）文字生音视频",
                step="draft",
                mode="fal_h3_max_t2v",
                status="ok" if fal_ready else "warn",
                reason=(
                    "fal 官方云端后训练版；不调用 ComfyUI、不加载本机视频模型，生成后自动回存本地。"
                    if fal_ready
                    else "需要先设置 FAL_KEY。当前没有可下载的 H3 Max 官方本地权重。"
                ),
                defaults={"width": 832, "height": 480, "length": 120, "fps": 24, "steps": 1, "cfg": 1.0},
                uses_image=False,
                install_profile="fal-h3-max-api",
            ),
            option(
                id="fal_h3_max_i2v",
                label="H3 Max（fal 后训练版）首帧 / 首尾帧",
                step="draft",
                mode="fal_h3_max_i2v",
                status="ok" if fal_ready else "warn",
                reason=(
                    "首帧锁定画面，尾帧可选；上传图片直接经后端转发给 fal，不经过 ComfyUI。"
                    if fal_ready
                    else "需要先设置 FAL_KEY；设置后只重启前端即可。"
                ),
                defaults={"width": 832, "height": 480, "length": 120, "fps": 24, "steps": 1, "cfg": 1.0},
                install_profile="fal-h3-max-api",
            ),
            option(
                id="ltx25_distilled_int8_t2v",
                label="LTX-Video 2.5 Distilled INT8 文字生音视频",
                step="draft",
                mode="ltx25_t2v",
                status=cuda_status(ready=ltx25_int8_ready, ok_gb=48, warn_gb=32),
                reason="LTX 2.5 官方 Distilled 两阶段试镜档；支持同步音频、DiffVAE/Conv VAE 和自动时长。",
                defaults={"width": 640, "height": 352, "length": 49, "fps": 24, "steps": 11, "cfg": 1.0},
                uses_image=False,
                install_profile="ltx25-distilled-int8",
                unrestricted=ltx25_unrestricted,
            ),
            option(
                id="ltx25_distilled_int8_i2v",
                label="LTX-Video 2.5 Distilled INT8 首帧/首尾帧",
                step="draft",
                mode="ltx25_i2v",
                status=cuda_status(ready=ltx25_int8_ready, ok_gb=48, warn_gb=32),
                reason="用首帧锁定主体，也可上传尾帧控制镜头终点；自带同步音轨。",
                defaults={"width": 640, "height": 352, "length": 49, "fps": 24, "steps": 11, "cfg": 1.0},
                install_profile="ltx25-distilled-int8",
                unrestricted=ltx25_unrestricted,
            ),
            option(
                id="ltx25_distilled_nvfp4_t2v",
                label="LTX-Video 2.5 Distilled NVFP4 文字生音视频",
                step="draft",
                mode="ltx25_t2v",
                status=cuda_status(ready=ltx25_nvfp4_ready, ok_gb=48, warn_gb=32),
                reason="体积更小的 NVFP4 试镜档；优先用于已确认 NVFP4 兼容的 RTX 50/PRO Blackwell。",
                defaults={"width": 640, "height": 352, "length": 49, "fps": 24, "steps": 11, "cfg": 1.0},
                uses_image=False,
                install_profile="ltx25-distilled-nvfp4",
                unrestricted=ltx25_unrestricted,
            ),
            option(
                id="ltx25_distilled_nvfp4_i2v",
                label="LTX-Video 2.5 Distilled NVFP4 首帧/首尾帧",
                step="draft",
                mode="ltx25_i2v",
                status=cuda_status(ready=ltx25_nvfp4_ready, ok_gb=48, warn_gb=32),
                reason="NVFP4 关键帧路线，支持首尾帧和同步音频；兼容性不确定时选 INT8。",
                defaults={"width": 640, "height": 352, "length": 49, "fps": 24, "steps": 11, "cfg": 1.0},
                install_profile="ltx25-distilled-nvfp4",
                unrestricted=ltx25_unrestricted,
            ),
            option(
                id="minimax_h3_fl2va_int8_t2v",
                label="MiniMax H3 FL2VA INT8 文字生音视频",
                step="draft",
                mode="minimax_h3_t2v",
                status=cuda_status(ready=minimax_h3_ready, ok_gb=80, warn_gb=40),
                reason="原生同步生成画面和声音；固定 24fps，先用约 3 秒保守档验证动作、对白与环境声。",
                defaults={"width": 864, "height": 480, "length": 73, "fps": 24, "steps": 20, "cfg": 1.0},
                uses_image=False,
                install_profile="minimax-h3-fl2va-int8",
                unrestricted=h3_unrestricted,
            ),
            option(
                id="minimax_h3_fl2va_int8_i2v",
                label="MiniMax H3 FL2VA INT8 首帧/首尾帧生音视频",
                step="draft",
                mode="minimax_h3_i2v",
                status=cuda_status(ready=minimax_h3_ready, ok_gb=80, warn_gb=40),
                reason="用首帧锁定人物和构图，也可加尾帧控制镜头终点，并同步生成对白、音效和环境声。",
                defaults={"width": 864, "height": 480, "length": 73, "fps": 24, "steps": 20, "cfg": 1.0},
                install_profile="minimax-h3-fl2va-int8",
                unrestricted=h3_unrestricted,
            ),
            option(
                id="minimax_h3_ref2va_int8_r2v",
                label="MiniMax H3 Ref2VA INT8 多参考素材",
                step="draft",
                mode="minimax_h3_r2v",
                status=cuda_status(ready=minimax_h3_reference_ready, ok_gb=80, warn_gb=40),
                reason="最多组合 9 张参考图、3 段参考视频和 3 条参考音频；用标签精确锁定人物、风格、动作、运镜或声音。",
                defaults={"width": 864, "height": 480, "length": 73, "fps": 24, "steps": 20, "cfg": 1.0},
                uses_image=False,
                install_profile="minimax-h3-ref2va-int8",
                unrestricted=h3_unrestricted,
            ),
            option(
                id="ltx23_fp8_dev_t2v",
                label="LTX-Video 2.3 22B Dev FP8 T2V",
                step="draft",
                mode="ltx23_t2v",
                status=cuda_status(ready=ltx23_dev_ready, ok_gb=40, warn_gb=32),
                reason="平台原生两阶段 LTX 2.3 链路；低分辨率短镜头适合先确认运动和提示词。",
                defaults={"width": 512, "height": 320, "length": 25, "fps": 25, "steps": 11, "cfg": 1.0},
                uses_image=False,
            ),
            option(
                id="ltx23_fp8_dev_i2v",
                label="LTX-Video 2.3 22B Dev FP8 I2V",
                step="draft",
                mode="ltx23_i2v",
                status=cuda_status(ready=ltx23_dev_ready, ok_gb=40, warn_gb=32),
                reason="平台原生两阶段 LTX 2.3 图生视频链路；使用上传关键帧稳定人物、产品和构图。",
                defaults={"width": 512, "height": 320, "length": 25, "fps": 25, "steps": 11, "cfg": 1.0},
            ),
            option(
                id="ltx23_nvfp4_dev_t2v",
                label="LTX-Video 2.3 22B Dev NVFP4 T2V",
                step="draft",
                mode="ltx23_t2v",
                status=cuda_status(ready=ltx23_nvfp4_ready, ok_gb=32, warn_gb=24),
                reason="平台原生两阶段 NVFP4 链路；checkpoint 更小，需兼容 NVFP4 的 CUDA 环境。",
                defaults={"width": 512, "height": 320, "length": 25, "fps": 25, "steps": 11, "cfg": 1.0},
                uses_image=False,
                install_profile="ltx23-nvfp4-dev",
            ),
            option(
                id="ltx23_nvfp4_dev_i2v",
                label="LTX-Video 2.3 22B Dev NVFP4 I2V",
                step="draft",
                mode="ltx23_i2v",
                status=cuda_status(ready=ltx23_nvfp4_ready, ok_gb=32, warn_gb=24),
                reason="NVFP4 两阶段图生视频；关键帧约束人物和构图，需兼容 NVFP4 的 CUDA 环境。",
                defaults={"width": 512, "height": 320, "length": 25, "fps": 25, "steps": 11, "cfg": 1.0},
                install_profile="ltx23-nvfp4-dev",
            ),
            option(
                id="hunyuan15_t2v_480_fp8",
                label="HunyuanVideo 1.5 T2V 480P Distilled FP8",
                step="draft",
                mode="hunyuan15_t2v",
                status=cuda_status(ready=hunyuan15_t2v_480_ready, ok_gb=24, warn_gb=16),
                reason="原生 8.3B 蒸馏 FP8 文字生视频，适合先验证中文提示词、动作和镜头。",
                defaults={"width": 832, "height": 480, "length": 49, "fps": 24, "steps": 8, "cfg": 1.0},
                uses_image=False,
                install_profile="hunyuan15-t2v-480-fp8",
            ),
            option(
                id="hunyuan15_i2v_480_fp8",
                label="HunyuanVideo 1.5 I2V 480P Distilled FP8",
                step="draft",
                mode="hunyuan15_i2v",
                status=cuda_status(ready=hunyuan15_i2v_480_ready, ok_gb=24, warn_gb=16),
                reason="原生 SigCLIP 关键帧条件，适合快速验证人物、产品和场景一致性。",
                defaults={"width": 832, "height": 480, "length": 49, "fps": 24, "steps": 8, "cfg": 1.0},
                install_profile="hunyuan15-i2v-480-fp8",
            ),
            option(
                id="ltx098_i2v_480p",
                label="LTXV 0.9.8 2B I2V 480P",
                step="draft",
                mode="ltx_i2v",
                status=ltx_status(ltx_ready),
                reason="平台内置的轻量 LTX 路线，适合低显存 CUDA、Apple Silicon 和快速短镜头。",
                defaults={"width": 832, "height": 480, "length": 49, "fps": 24, "steps": 12, "cfg": 3.0},
            ),
            option(
                id="ltx098_t2v_480p",
                label="LTXV 0.9.8 2B T2V 480P",
                step="draft",
                mode="ltx_t2v",
                status=ltx_status(ltx_ready),
                reason="无需关键帧的轻量文字生视频路线，适合直接从 Prompt 生成。",
                defaults={"width": 832, "height": 480, "length": 49, "fps": 24, "steps": 12, "cfg": 3.0},
                uses_image=False,
            ),
            option(
                id="mac_ltx_low_i2v",
                label="Mac LTX I2V 低档",
                step="draft",
                mode="ltx_i2v",
                status=mac_ltx_status(ltx_ready),
                reason="Apple Silicon 低内存或首次 smoke test 档；小分辨率、短镜头，优先验证能跑通。",
                defaults={"width": 512, "height": 320, "length": 25, "fps": 24, "steps": 12, "cfg": 3.0},
            ),
            option(
                id="mac_ltx_balanced_i2v",
                label="Mac LTX I2V 均衡档",
                step="draft",
                mode="ltx_i2v",
                status=mac_ltx_status(ltx_ready),
                reason="16GB 到 32GB+ Apple Silicon 的默认 Mac 视频路线，速度和稳定性优先。",
                defaults={"width": 576, "height": 320, "length": 49, "fps": 24, "steps": 16, "cfg": 3.0},
            ),
            option(
                id="mac_ltx_quality_i2v",
                label="Mac LTX I2V 质量档",
                step="draft",
                mode="ltx_i2v",
                status=mac_ltx_status(ltx_ready),
                reason="高内存 Apple Silicon 可先用 LTX 质量档试动作和镜头，再决定是否尝试其他高内存模型。",
                defaults={"width": 704, "height": 416, "length": 49, "fps": 24, "steps": 18, "cfg": 3.0},
            ),
            option(
                id="wan22_ti2v_5b_720p",
                label="Wan2.2 TI2V-5B 720P",
                step="draft",
                mode="ti2v_5b",
                status=cuda_status(ready=ti2v_ready, ok_gb=24, warn_gb=16, mac_warn=True),
                reason="Wan 家族的均衡档。关键帧可选；24GB 以上 CUDA 更舒服，macOS 可实验但速度和节点兼容性要看环境。",
                defaults={"width": 1280, "height": 704, "length": 81, "fps": 24, "steps": 20, "cfg": 5.0},
            ),
            option(
                id="wan22_ti2v_5b_480p",
                label="Wan2.2 TI2V-5B 480P 小显存",
                step="draft",
                mode="ti2v_5b",
                status=cuda_status(ready=ti2v_ready, ok_gb=16, warn_gb=8, mac_warn=True),
                reason="关键帧可选。给 8GB 到 16GB、Apple Silicon 或不稳定机器的保守档；更慢但更容易跑通。",
                defaults={"width": 832, "height": 480, "length": 49, "fps": 24, "steps": 18, "cfg": 5.0},
            ),
        ],
        "final": [
            option(
                id="no_local_video_final",
                label="当前硬件不建议本地生视频",
                step="final",
                mode="unsupported",
                status="blocked",
                reason="当前为后期处理路线，不会下载视频大模型。请上传外部视频进入后期，或切换到 CUDA / Apple Silicon MPS 环境。",
                uses_image=False,
                supported=False,
            ),
            option(
                id="fal_h3_max_t2v",
                label="H3 Max（fal 后训练版）768P 文字生音视频",
                step="final",
                mode="fal_h3_max_t2v",
                status="ok" if fal_ready else "warn",
                reason=(
                    "fal 云端 768P 正式档，支持 5-15 秒与原生同步音频；本机显卡保持给文本模型。"
                    if fal_ready
                    else "需要先设置 FAL_KEY。此项不要求 ComfyUI 在线。"
                ),
                defaults={"width": 1344, "height": 768, "length": 120, "fps": 24, "steps": 1, "cfg": 1.0},
                uses_image=False,
                install_profile="fal-h3-max-api",
            ),
            option(
                id="fal_h3_max_i2v",
                label="H3 Max（fal 后训练版）768P 首帧 / 首尾帧",
                step="final",
                mode="fal_h3_max_i2v",
                status="ok" if fal_ready else "warn",
                reason=(
                    "fal 云端正式 I2V 档，首帧必需、尾帧可选，成片自动下载回项目输出目录。"
                    if fal_ready
                    else "需要先设置 FAL_KEY。不会下载或加载本地视频大模型。"
                ),
                defaults={"width": 1344, "height": 768, "length": 120, "fps": 24, "steps": 1, "cfg": 1.0},
                install_profile="fal-h3-max-api",
            ),
            option(
                id="ltx25_distilled_int8_t2v",
                label="LTX-Video 2.5 Distilled INT8 720P 文字生音视频",
                step="final",
                mode="ltx25_t2v",
                status=cuda_status(ready=ltx25_int8_ready, ok_gb=48, warn_gb=32),
                reason="官方 Distilled 两阶段正式档，先半分辨率采样，再做潜变量 2x 超分并解码同步音频。",
                defaults={"width": 1280, "height": 704, "length": 121, "fps": 24, "steps": 11, "cfg": 1.0},
                uses_image=False,
                install_profile="ltx25-distilled-int8",
                unrestricted=ltx25_unrestricted,
            ),
            option(
                id="ltx25_distilled_int8_i2v",
                label="LTX-Video 2.5 Distilled INT8 720P 首帧/首尾帧",
                step="final",
                mode="ltx25_i2v",
                status=cuda_status(ready=ltx25_int8_ready, ok_gb=48, warn_gb=32),
                reason="720P 关键帧正式档；单首帧走两阶段，上传尾帧时自动切换官方首尾帧单阶段配方。",
                defaults={"width": 1280, "height": 704, "length": 121, "fps": 24, "steps": 11, "cfg": 1.0},
                install_profile="ltx25-distilled-int8",
                unrestricted=ltx25_unrestricted,
            ),
            option(
                id="ltx25_distilled_nvfp4_t2v",
                label="LTX-Video 2.5 Distilled NVFP4 720P 文字生音视频",
                step="final",
                mode="ltx25_t2v",
                status=cuda_status(ready=ltx25_nvfp4_ready, ok_gb=48, warn_gb=32),
                reason="Blackwell 优先的 NVFP4 正式档；与 INT8 档共享音频、DiffVAE 和潜变量超分。",
                defaults={"width": 1280, "height": 704, "length": 121, "fps": 24, "steps": 11, "cfg": 1.0},
                uses_image=False,
                install_profile="ltx25-distilled-nvfp4",
                unrestricted=ltx25_unrestricted,
            ),
            option(
                id="ltx25_distilled_nvfp4_i2v",
                label="LTX-Video 2.5 Distilled NVFP4 720P 首帧/首尾帧",
                step="final",
                mode="ltx25_i2v",
                status=cuda_status(ready=ltx25_nvfp4_ready, ok_gb=48, warn_gb=32),
                reason="NVFP4 关键帧正式档，支持首尾帧约束与原生同步音轨。",
                defaults={"width": 1280, "height": 704, "length": 121, "fps": 24, "steps": 11, "cfg": 1.0},
                install_profile="ltx25-distilled-nvfp4",
                unrestricted=ltx25_unrestricted,
            ),
            option(
                id="minimax_h3_fl2va_int8_t2v",
                label="MiniMax H3 FL2VA INT8 文字生音视频",
                step="final",
                mode="minimax_h3_t2v",
                status=cuda_status(ready=minimax_h3_ready, ok_gb=80, warn_gb=40),
                reason="H3 Base 原生音视频正式路线；96GB 显存可从 768P、约 5 秒开始，长镜头仍建议分镜生成。",
                defaults={"width": 1344, "height": 768, "length": 124, "fps": 24, "steps": 20, "cfg": 1.0},
                uses_image=False,
                install_profile="minimax-h3-fl2va-int8",
                unrestricted=h3_unrestricted,
            ),
            option(
                id="minimax_h3_fl2va_int8_i2v",
                label="MiniMax H3 FL2VA INT8 首帧/首尾帧生音视频",
                step="final",
                mode="minimax_h3_i2v",
                status=cuda_status(ready=minimax_h3_ready, ok_gb=80, warn_gb=40),
                reason="正式首帧或首尾帧 FL2VA 路线；适合在一条工作流里同时控制构图、镜头终点和同步声音。",
                defaults={"width": 1344, "height": 768, "length": 124, "fps": 24, "steps": 20, "cfg": 1.0},
                install_profile="minimax-h3-fl2va-int8",
                unrestricted=h3_unrestricted,
            ),
            option(
                id="ltx23_fp8_dev_t2v",
                label="LTX-Video 2.3 22B Dev FP8 T2V",
                step="final",
                mode="ltx23_t2v",
                status=cuda_status(ready=ltx23_dev_ready, ok_gb=40, warn_gb=32),
                reason="平台原生两阶段 LTX 2.3 高质量链路；生成音视频并在潜变量阶段做 2x 空间超分。",
                defaults={"width": 768, "height": 512, "length": 49, "fps": 25, "steps": 11, "cfg": 1.0},
                uses_image=False,
            ),
            option(
                id="ltx23_fp8_dev_i2v",
                label="LTX-Video 2.3 22B Dev FP8 I2V",
                step="final",
                mode="ltx23_i2v",
                status=cuda_status(ready=ltx23_dev_ready, ok_gb=40, warn_gb=32),
                reason="以关键帧约束画面，保留两阶段音视频生成与潜变量 2x 超分。",
                defaults={"width": 768, "height": 512, "length": 49, "fps": 25, "steps": 11, "cfg": 1.0},
            ),
            option(
                id="ltx23_nvfp4_dev_t2v",
                label="LTX-Video 2.3 22B Dev NVFP4 T2V",
                step="final",
                mode="ltx23_t2v",
                status=cuda_status(ready=ltx23_nvfp4_ready, ok_gb=32, warn_gb=24),
                reason="NVFP4 原生两阶段音视频链路，保留 Distilled LoRA 和潜变量 2x 超分。",
                defaults={"width": 768, "height": 512, "length": 49, "fps": 25, "steps": 11, "cfg": 1.0},
                uses_image=False,
                install_profile="ltx23-nvfp4-dev",
            ),
            option(
                id="ltx23_nvfp4_dev_i2v",
                label="LTX-Video 2.3 22B Dev NVFP4 I2V",
                step="final",
                mode="ltx23_i2v",
                status=cuda_status(ready=ltx23_nvfp4_ready, ok_gb=32, warn_gb=24),
                reason="NVFP4 原生两阶段 I2V，用关键帧稳定画面并保留潜变量超分。",
                defaults={"width": 768, "height": 512, "length": 49, "fps": 25, "steps": 11, "cfg": 1.0},
                install_profile="ltx23-nvfp4-dev",
            ),
            option(
                id="hunyuan15_t2v_480_fp8",
                label="HunyuanVideo 1.5 T2V 480P Distilled FP8",
                step="final",
                mode="hunyuan15_t2v",
                status=cuda_status(ready=hunyuan15_t2v_480_ready, ok_gb=24, warn_gb=16),
                reason="8.3B 蒸馏 FP8 轻量质量档，可自由调整 4-60 步，默认 8 步。",
                defaults={"width": 832, "height": 480, "length": 81, "fps": 24, "steps": 8, "cfg": 1.0},
                uses_image=False,
                install_profile="hunyuan15-t2v-480-fp8",
            ),
            option(
                id="hunyuan15_i2v_480_fp8",
                label="HunyuanVideo 1.5 I2V 480P Distilled FP8",
                step="final",
                mode="hunyuan15_i2v",
                status=cuda_status(ready=hunyuan15_i2v_480_ready, ok_gb=24, warn_gb=16),
                reason="轻量 I2V 正式档；使用 SigCLIP 与起始帧双条件保持主体和构图。",
                defaults={"width": 832, "height": 480, "length": 81, "fps": 24, "steps": 8, "cfg": 1.0},
                install_profile="hunyuan15-i2v-480-fp8",
            ),
            option(
                id="hunyuan15_t2v_720_fp16",
                label="HunyuanVideo 1.5 T2V 720P FP16",
                step="final",
                mode="hunyuan15_t2v",
                status=cuda_status(ready=hunyuan15_t2v_720_ready, ok_gb=40, warn_gb=24),
                reason="质量优先 FP16 文字生视频，适合正式镜头；步数和 CFG 可自由调整。",
                defaults={"width": 1280, "height": 704, "length": 81, "fps": 24, "steps": 20, "cfg": 6.0},
                uses_image=False,
                install_profile="hunyuan15-t2v-720-fp16",
            ),
            option(
                id="hunyuan15_i2v_720_fp16",
                label="HunyuanVideo 1.5 I2V 720P FP16",
                step="final",
                mode="hunyuan15_i2v",
                status=cuda_status(ready=hunyuan15_i2v_720_ready, ok_gb=40, warn_gb=24),
                reason="质量优先 FP16 图生视频，用关键帧提高人物、产品与场景一致性。",
                defaults={"width": 1280, "height": 704, "length": 81, "fps": 24, "steps": 20, "cfg": 6.0},
                install_profile="hunyuan15-i2v-720-fp16",
            ),
            option(
                id="ltx098_i2v_480p",
                label="LTXV 0.9.8 2B I2V 480P",
                step="final",
                mode="ltx_i2v",
                status=ltx_status(ltx_ready),
                reason="平台内置的轻量视频路线，建议短镜头生成后再去闪烁和超分。",
                defaults={"width": 832, "height": 480, "length": 49, "fps": 24, "steps": 14, "cfg": 3.0},
            ),
            option(
                id="ltx098_t2v_480p",
                label="LTXV 0.9.8 2B T2V 480P",
                step="final",
                mode="ltx_t2v",
                status=ltx_status(ltx_ready),
                reason="无需关键帧的轻量文字生视频路线，随机性高于 I2V。",
                defaults={"width": 832, "height": 480, "length": 49, "fps": 24, "steps": 14, "cfg": 3.0},
                uses_image=False,
            ),
            option(
                id="mac_ltx_low_i2v",
                label="Mac LTX I2V 低档",
                step="final",
                mode="ltx_i2v",
                status=mac_ltx_status(ltx_ready),
                reason="8GB/16GB Apple Silicon 的保守档。短镜头、小分辨率，优先保证跑通。",
                defaults={"width": 512, "height": 320, "length": 25, "fps": 24, "steps": 12, "cfg": 3.0},
            ),
            option(
                id="mac_ltx_quality_i2v",
                label="Mac LTX I2V 质量档",
                step="final",
                mode="ltx_i2v",
                status=mac_ltx_status(ltx_ready),
                reason="Mac 默认质量路线。先用关键帧稳定构图，再靠短镜头、去闪烁和超分补质量。",
                defaults={"width": 704, "height": 416, "length": 49, "fps": 24, "steps": 18, "cfg": 3.0},
            ),
            option(
                id="mac_ltx_balanced_t2v",
                label="Mac LTX T2V 均衡档",
                step="final",
                mode="ltx_t2v",
                status=mac_ltx_status(ltx_ready),
                reason="没有关键帧时可用；随机性更强，仍建议先做关键帧再 I2V。",
                defaults={"width": 576, "height": 320, "length": 49, "fps": 24, "steps": 16, "cfg": 3.0},
                uses_image=False,
            ),
            option(
                id="mac_wan5b_480p",
                label="Mac Wan2.2 TI2V-5B 480P 实验档",
                step="final",
                mode="ti2v_5b",
                status=mac_wan5b_status(ti2v_ready, min_memory_gb=24),
                reason="关键帧可选。高内存 Apple Silicon 的质量尝试档，需要先通过节点、模型名和 MPS dtype 预检。",
                defaults={"width": 832, "height": 480, "length": 49, "fps": 24, "steps": 20, "cfg": 5.0},
            ),
            option(
                id="mac_wan5b_720p_experimental",
                label="Mac Wan2.2 TI2V-5B 720P 高内存实验档",
                step="final",
                mode="ti2v_5b",
                status=mac_wan5b_status(ti2v_ready, min_memory_gb=96),
                reason="关键帧可选。96GB/128GB+ Apple Silicon 可尝试短镜头；A14B 仍不作为 Mac 默认推荐。",
                defaults={"width": 1280, "height": 704, "length": 49, "fps": 24, "steps": 20, "cfg": 5.0},
            ),
            option(
                id="wan22_i2v_a14b_720p",
                label="Wan2.2 I2V-A14B 720P",
                step="final",
                mode="i2v_a14b",
                status=cuda_status(ready=i2v_ready, ok_gb=80, warn_gb=64),
                reason="Wan 家族的高显存质量档，用关键帧控制画面，适合正式出片。",
                defaults={"width": 1280, "height": 704, "length": 81, "fps": 24, "steps": 4, "cfg": 1.0},
                unrestricted=wan_i2v_unrestricted,
                install_profile="cuda-a14b",
            ),
            option(
                id="wan22_i2v_a14b_480p",
                label="Wan2.2 I2V-A14B 480P",
                step="final",
                mode="i2v_a14b",
                status=cuda_status(ready=i2v_ready, ok_gb=48, warn_gb=32),
                reason="48GB 单卡更现实的 A14B 档位；可先 480P 出片，再做超分。",
                defaults={"width": 832, "height": 480, "length": 49, "fps": 24, "steps": 4, "cfg": 1.0},
                unrestricted=wan_i2v_unrestricted,
                install_profile="cuda-a14b",
            ),
            option(
                id="wan22_t2v_a14b_720p",
                label="Wan2.2 T2V-A14B 720P",
                step="final",
                mode="t2v_a14b",
                status=cuda_status(ready=t2v_ready, ok_gb=80, warn_gb=64),
                reason="没有关键帧时使用；随机性更大，品牌和人物一致性不如 I2V。",
                defaults={"width": 1280, "height": 704, "length": 81, "fps": 24, "steps": 4, "cfg": 1.0},
                uses_image=False,
                unrestricted=wan_t2v_unrestricted,
                install_profile="cuda-a14b",
            ),
            option(
                id="wan22_t2v_a14b_480p",
                label="Wan2.2 T2V-A14B 480P",
                step="final",
                mode="t2v_a14b",
                status=cuda_status(ready=t2v_ready, ok_gb=48, warn_gb=32),
                reason="48GB 或更紧张显存的文字生视频尝试档；仍建议优先 I2V。",
                defaults={"width": 832, "height": 480, "length": 49, "fps": 24, "steps": 4, "cfg": 1.0},
                uses_image=False,
                unrestricted=wan_t2v_unrestricted,
                install_profile="cuda-a14b",
            ),
            option(
                id="wan22_ti2v_5b_final_720p",
                label="Wan2.2 TI2V-5B 720P 高质量",
                step="final",
                mode="ti2v_5b",
                status=cuda_status(ready=ti2v_ready, ok_gb=24, warn_gb=16, mac_warn=True),
                reason="关键帧可选。24GB 到 48GB 可以把 5B 当最终模型用，画质不如 A14B，但更容易跑通。",
                defaults={"width": 1280, "height": 704, "length": 81, "fps": 24, "steps": 24, "cfg": 5.0},
            ),
            option(
                id="wan22_ti2v_5b_final_480p",
                label="Wan2.2 TI2V-5B 480P 小显存质量",
                step="final",
                mode="ti2v_5b",
                status=cuda_status(ready=ti2v_ready, ok_gb=16, warn_gb=8, mac_warn=True),
                reason="关键帧可选。低配 CUDA、Apple Silicon 或测试机的保底视频生成档。",
                defaults={"width": 832, "height": 480, "length": 49, "fps": 24, "steps": 22, "cfg": 5.0},
            ),
        ],
        "deflicker": [
            option(
                id="ffmpeg_deflicker_balanced",
                label="ffmpeg deflicker + hqdn3d",
                step="deflicker",
                mode="deflicker",
                status="ok" if deflicker_ready else "blocked",
                reason="CPU 也能跑，适合修曝光闪烁和轻微纹理跳动。",
                uses_image=False,
            )
        ],
        "rife": [
            option(
                id="rife49_2x",
                label="RIFE 4.9 2x",
                step="rife",
                mode="rife_2x",
                status="ok" if rife_ready and accelerator == "cuda" else "warn" if rife_ready else "blocked",
                reason="把 24fps 插到 48fps；CUDA 最稳，macOS/CPU 可能很慢。",
                uses_image=False,
                rife_multiplier=2,
            ),
            option(
                id="rife49_4x",
                label="RIFE 4.9 4x",
                step="rife",
                mode="rife_2x",
                status="ok" if rife_ready and accelerator == "cuda" and max_vram >= 16 else "warn" if rife_ready else "blocked",
                reason="更高帧率，耗时和伪影风险更高；只建议短片段。",
                uses_image=False,
                rife_multiplier=4,
            ),
        ],
        "upscale": [
            option(
                id="seedvr2_7b_1080p",
                label="SeedVR2 7B NVFP4 1.5x（720P→1080P）",
                step="upscale",
                mode="upscale_seedvr2",
                status="ok"
                if seedvr2_7b_ready and accelerator == "cuda" and max_vram >= 48
                else "warn"
                if seedvr2_7b_ready and accelerator == "cuda" and max_vram >= 24
                else "blocked",
                reason="96GB 实测推荐档：连续帧一起修复，720P 可直接输出标准 1080P；比 3B 更少人工锐化纹理。",
                uses_image=False,
                scale=1.5,
                upscale_model=SEEDVR2_7B_MODEL,
                install_profile="seedvr2-upscale-7b",
            ),
            option(
                id="seedvr2_7b_sharp_1080p",
                label="SeedVR2 7B Sharp NVFP4 1.5x（实验）",
                step="upscale",
                mode="upscale_seedvr2",
                status="ok"
                if seedvr2_7b_sharp_ready and accelerator == "cuda" and max_vram >= 48
                else "warn"
                if seedvr2_7b_sharp_ready and accelerator == "cuda" and max_vram >= 24
                else "blocked",
                reason="更锐利的实验档；适合自然纹理，屏幕、文字和产品边缘可能被过度强化，建议先跑样片。",
                uses_image=False,
                scale=1.5,
                upscale_model=SEEDVR2_7B_SHARP_MODEL,
                install_profile="seedvr2-upscale-7b-sharp",
            ),
            option(
                id="seedvr2_3b_2x",
                label="SeedVR2 3B INT8 时序视频超分 2x",
                step="upscale",
                mode="upscale_seedvr2",
                status="ok"
                if seedvr2_ready and accelerator == "cuda" and max_vram >= 24
                else "warn"
                if seedvr2_ready and accelerator == "cuda" and max_vram >= 12
                else "blocked",
                reason="高质量默认档：连续帧一起修复，细节更自然，也更不容易出现逐帧纹理跳动；比 RealESRGAN 慢。",
                uses_image=False,
                scale=2,
                upscale_model=SEEDVR2_3B_MODEL,
                install_profile="seedvr2-upscale",
            ),
            option(
                id="realesrgan_x2plus",
                label="RealESRGAN x2plus 快速兼容 2x",
                step="upscale",
                mode="upscale_2x",
                status="ok" if upscale_ready and asset_ok.get("realesrgan_x2") else "blocked",
                reason="旧但成熟的逐帧快速档，显存占用低；速度优先或 SeedVR2 不可用时使用。",
                uses_image=False,
                scale=2,
                upscale_model="RealESRGAN_x2plus.pth",
            ),
            option(
                id="ultrasharp_4x",
                label="4x-UltraSharp 4x",
                step="upscale",
                mode="upscale_2x",
                status="ok" if upscale_ready and asset_ok.get("ultrasharp_x4") and max_vram >= 16 else "warn" if asset_ok.get("ultrasharp_x4") else "blocked",
                reason="目标分辨率更高，文件和显存压力明显增加；适合最终短片段。",
                uses_image=False,
                scale=4,
                upscale_model="4x-UltraSharp.pth",
            ),
        ],
    }

    # The current UI has one generation step. Prefer the former quality profile,
    # then add genuinely different trial profiles while keeping legacy `final`
    # data available for older clients.
    unified_id_aliases = {
        "wan22_ti2v_5b_final_720p": "wan22_ti2v_5b_720p",
        "wan22_ti2v_5b_final_480p": "wan22_ti2v_5b_480p",
    }
    unified_generation: list[dict[str, Any]] = []
    visible_generation_ids: set[str] = set()
    visible_generation_signatures: set[tuple[Any, ...]] = set()
    for source_option in [*options["final"], *options["draft"]]:
        source_id = str(source_option.get("id") or "")
        if not source_id or source_id == "no_local_video_final":
            continue
        option_id = unified_id_aliases.get(source_id, source_id)
        defaults = source_option.get("defaults") or {}
        signature = (
            str(source_option.get("mode") or ""),
            int(defaults.get("width") or 0),
            int(defaults.get("height") or 0),
            bool(source_option.get("uses_image")),
            str(source_option.get("install_profile") or ""),
        )
        if option_id in visible_generation_ids or signature in visible_generation_signatures:
            continue
        unified_generation.append({**source_option, "id": option_id, "step": "draft"})
        visible_generation_ids.add(option_id)
        visible_generation_signatures.add(signature)
    options["draft"] = unified_generation
    if not post_only_video:
        options["draft"] = [item for item in options["draft"] if item.get("id") != "no_local_video_draft"]
    if not is_macos:
        options["draft"] = [item for item in options["draft"] if not str(item.get("id") or "").startswith("mac_")]
        options["final"] = [item for item in options["final"] if not str(item.get("id") or "").startswith("mac_")]

    for generation_step in ("draft", "final"):
        attach_generation_counterparts(options[generation_step])

    def first_ok(step: str, fallback: str) -> str:
        for item in options[step]:
            if item["status"] == "ok" and item["supported"]:
                return item["id"]
        for item in options[step]:
            if item["status"] == "warn" and item["supported"]:
                return item["id"]
        return fallback

    if platform_strategy == "mac_mps":
        if mac_tier == "mac_wan5b_720p_experimental":
            final_default = "mac_wan5b_720p_experimental"
            draft_default = "mac_ltx_quality_i2v"
        elif mac_tier == "mac_wan5b_480p":
            final_default = "mac_wan5b_480p"
            draft_default = "mac_ltx_quality_i2v"
        elif mac_tier == "mac_ltx_quality":
            final_default = "mac_ltx_quality_i2v"
            draft_default = "mac_ltx_balanced_i2v"
        elif mac_tier == "mac_ltx_balanced":
            final_default = "mac_ltx_quality_i2v"
            draft_default = "mac_ltx_balanced_i2v"
        else:
            final_default = "mac_ltx_low_i2v"
            draft_default = "mac_ltx_low_i2v"
    elif accelerator == "cuda" and max_vram >= 80:
        final_default = "minimax_h3_fl2va_int8_i2v"
        draft_default = "minimax_h3_fl2va_int8_t2v"
    elif accelerator == "cuda" and max_vram >= 40:
        final_default = "ltx25_distilled_int8_i2v"
        draft_default = "ltx25_distilled_int8_t2v"
    elif accelerator == "cuda" and max_vram >= 24:
        final_default = "hunyuan15_i2v_720_fp16"
        draft_default = "hunyuan15_t2v_480_fp8"
    elif accelerator == "cuda" and max_vram >= 16:
        final_default = "hunyuan15_i2v_480_fp8"
        draft_default = "hunyuan15_t2v_480_fp8"
    elif accelerator == "cuda":
        final_default = "ltx098_i2v_480p"
        draft_default = "ltx098_t2v_480p"
    elif post_only_video:
        final_default = "no_local_video_final"
        draft_default = "no_local_video_draft"
    else:
        final_default = first_ok("final", "ltx098_i2v_480p")
        draft_default = first_ok("draft", "ltx098_t2v_480p")

    recommended = {
        "keyframe": "upload_keyframe",
        "draft": draft_default,
        "final": final_default,
        "deflicker": first_ok("deflicker", "ffmpeg_deflicker_balanced"),
        "rife": first_ok("rife", "rife49_2x"),
        "upscale": "seedvr2_7b_1080p"
        if seedvr2_7b_ready and accelerator == "cuda" and max_vram >= 48
        else "seedvr2_3b_2x"
        if seedvr2_ready and accelerator == "cuda" and max_vram >= 24
        else "realesrgan_x2plus",
    }

    selected_catalog = catalog_item_by_id(selected_model_id if selected_model_id is not None else saved_model_catalog_id()) or {}
    target_modes = selected_catalog.get("workflow_modes") or {}
    preferred_profiles = {
        ("draft", "ti2v_5b"): "wan22_ti2v_5b_720p" if max_vram >= 24 else "wan22_ti2v_5b_480p",
        ("final", "ti2v_5b"): "wan22_ti2v_5b_final_720p" if max_vram >= 24 else "wan22_ti2v_5b_final_480p",
        ("draft", "t2v_a14b"): "wan22_t2v_a14b_720p" if max_vram >= 80 else "wan22_t2v_a14b_480p",
        ("draft", "i2v_a14b"): "wan22_i2v_a14b_720p" if max_vram >= 80 else "wan22_i2v_a14b_480p",
        ("final", "i2v_a14b"): "wan22_i2v_a14b_720p" if max_vram >= 80 else "wan22_i2v_a14b_480p",
        ("final", "t2v_a14b"): "wan22_t2v_a14b_720p" if max_vram >= 80 else "wan22_t2v_a14b_480p",
        ("draft", "ltx_i2v"): "ltx098_i2v_480p",
        ("final", "ltx_i2v"): "ltx098_i2v_480p",
        ("final", "ltx_t2v"): "ltx098_t2v_480p",
        ("draft", "ltx23_t2v"): "ltx23_fp8_dev_t2v",
        ("final", "ltx23_t2v"): "ltx23_fp8_dev_t2v",
        ("draft", "ltx23_i2v"): "ltx23_fp8_dev_i2v",
        ("final", "ltx23_i2v"): "ltx23_fp8_dev_i2v",
        ("draft", "ltx25_t2v"): "ltx25_distilled_int8_t2v",
        ("final", "ltx25_t2v"): "ltx25_distilled_int8_t2v",
        ("draft", "ltx25_i2v"): "ltx25_distilled_int8_i2v",
        ("final", "ltx25_i2v"): "ltx25_distilled_int8_i2v",
        ("draft", "hunyuan15_t2v"): "hunyuan15_t2v_480_fp8",
        ("final", "hunyuan15_t2v"): "hunyuan15_t2v_720_fp16" if max_vram >= 40 else "hunyuan15_t2v_480_fp8",
        ("draft", "hunyuan15_i2v"): "hunyuan15_i2v_480_fp8",
        ("final", "hunyuan15_i2v"): "hunyuan15_i2v_720_fp16" if max_vram >= 40 else "hunyuan15_i2v_480_fp8",
        ("draft", "minimax_h3_t2v"): "minimax_h3_fl2va_int8_t2v",
        ("final", "minimax_h3_i2v"): "minimax_h3_fl2va_int8_i2v",
        ("draft", "fal_h3_max_t2v"): "fal_h3_max_t2v",
        ("final", "fal_h3_max_i2v"): "fal_h3_max_i2v",
    }
    selected_install_profile = str(selected_catalog.get("default_install_profile") or "")
    catalog_profile_preferences = {
        "ltx25-distilled-int8": {
            "draft": "ltx25_distilled_int8_t2v",
            "final": "ltx25_distilled_int8_i2v",
        },
        "ltx25-distilled-nvfp4": {
            "draft": "ltx25_distilled_nvfp4_t2v",
            "final": "ltx25_distilled_nvfp4_i2v",
        },
        "ltx23-nvfp4-dev": {
            "draft": "ltx23_nvfp4_dev_t2v",
            "final": "ltx23_nvfp4_dev_t2v",
        },
        "hunyuan15-t2v-480-fp8": {"draft": "hunyuan15_t2v_480_fp8", "final": "hunyuan15_t2v_480_fp8"},
        "hunyuan15-i2v-480-fp8": {"draft": "hunyuan15_i2v_480_fp8", "final": "hunyuan15_i2v_480_fp8"},
        "hunyuan15-t2v-720-fp16": {"draft": "hunyuan15_t2v_720_fp16", "final": "hunyuan15_t2v_720_fp16"},
        "hunyuan15-i2v-720-fp16": {"draft": "hunyuan15_i2v_720_fp16", "final": "hunyuan15_i2v_720_fp16"},
        "minimax-h3-fl2va-int8": {
            "draft": "minimax_h3_fl2va_int8_t2v",
            "final": "minimax_h3_fl2va_int8_i2v",
        },
        "fal-h3-max-api": {
            "draft": "fal_h3_max_t2v",
            "final": "fal_h3_max_i2v",
        },
        "cuda-a14b": {
            "draft": "wan22_t2v_a14b_720p" if max_vram >= 80 else "wan22_t2v_a14b_480p",
            "final": "wan22_i2v_a14b_720p" if max_vram >= 80 else "wan22_i2v_a14b_480p",
        },
    }
    for step_id, target_mode in target_modes.items():
        preferred = catalog_profile_preferences.get(selected_install_profile, {}).get(str(step_id))
        preferred = preferred or preferred_profiles.get((str(step_id), str(target_mode)))
        if preferred and any(item.get("id") == preferred for item in options.get(str(step_id), [])):
            recommended[str(step_id)] = preferred

    platform_support = str(selected_catalog.get("platform_support") or "native")
    if selected_catalog and platform_support not in {"native", "cloud_api"}:
        catalog_label = str(selected_catalog.get("label") or "当前目标模型")
        profile = CATALOG_INSTALL_PROFILES.get(str(selected_catalog.get("default_install_profile") or "manual")) or {}
        support_label = "官方 ComfyUI 工作流" if platform_support == "official_workflow" else "手动接入"
        reason = " ".join(
            part
            for part in (
                str(selected_catalog.get("workflow_support") or ""),
                str(profile.get("external_requirement") or ""),
            )
            if part
        ).strip()
        for step_id in ("draft", "final"):
            item_id = f"catalog_{clean_id(str(selected_catalog.get('id') or 'external'))}_{step_id}"
            external_option = option(
                id=item_id,
                label=f"{catalog_label} · {support_label}",
                step=step_id,
                mode="external_workflow",
                status="warn",
                reason=reason or f"{catalog_label} 当前需要通过{support_label}运行。",
                uses_image=False,
                supported=False,
                model_label=catalog_label,
                install_profile=str(selected_catalog.get("default_install_profile") or "manual"),
            )
            options[step_id].insert(0, external_option)
            recommended[step_id] = item_id

    small_model_routes = [
        {
            "hardware": "8GB-12GB CUDA / 入门显卡",
            "route": "优先 LTXV 0.9.8 2B 小分辨率短镜头；模型目录中也可自选其他轻量路线。",
        },
        {
            "hardware": "16GB-24GB CUDA",
            "route": "优先 HunyuanVideo 1.5 FP8 或 LTX 轻量档；Wan2.2 5B 可作为备选。",
        },
        {
            "hardware": "48GB CUDA",
            "route": "优先 LTX-Video 2.5 Distilled INT8 短镜头；Blackwell 可试 NVFP4，也可选 HunyuanVideo 1.5 或 Wan2.2。",
        },
        {
            "hardware": "80GB-96GB CUDA",
            "route": "可运行 MiniMax H3、LTX-Video 2.5 原生音视频或 Wan2.2 A14B；先做短镜头 smoke test 再提升到 720P/1080P。",
        },
        {
            "hardware": "Apple Silicon / macOS",
            "route": "8GB/16GB 默认 LTXV 低档；24GB-36GB 用均衡/质量档；48GB+ 再开放高内存实验模型。",
        },
        {
            "hardware": "CPU / 无独显",
            "route": "不建议本地生视频；适合关键帧管理、剪辑拼接、ffmpeg 闪烁修复。",
        },
    ]

    return {
        "options": options,
        "recommended": recommended,
        "small_model_routes": small_model_routes,
        "unified_generation": True,
    }


VIDEO_SMOKE_PRIORITY = [
    "ltx25_distilled_int8_t2v",
    "ltx25_distilled_nvfp4_t2v",
    "ltx23_fp8_dev_t2v",
    "hunyuan15_t2v_480_fp8",
    "minimax_h3_fl2va_int8_t2v",
    "ltx098_t2v_480p",
    "mac_ltx_balanced_t2v",
    "wan22_t2v_a14b_480p",
    "wan22_t2v_a14b_720p",
    "wan22_ti2v_5b_480p",
    "wan22_ti2v_5b_720p",
]


def choose_video_smoke_option(model_options: dict[str, Any]) -> dict[str, Any] | None:
    candidates: dict[str, dict[str, Any]] = {}
    for step_id in ("draft", "final"):
        for item in (model_options.get("options") or {}).get(step_id, []):
            if (
                item.get("mode") in VIDEO_SMOKE_MODES
                and (item.get("uses_image") is False or item.get("image_optional") is True)
                and item.get("supported")
                and item.get("status") in {"ok", "warn"}
            ):
                candidates[str(item.get("id"))] = item
    recommended_id = str((model_options.get("recommended") or {}).get("draft") or "")
    if recommended_id in candidates:
        return candidates[recommended_id]
    for item_id in VIDEO_SMOKE_PRIORITY:
        if item_id in candidates:
            return candidates[item_id]
    return next(iter(candidates.values()), None)


def video_smoke_parameters(option: dict[str, Any]) -> dict[str, Any]:
    mode = str(option.get("mode") or "")
    defaults = dict(option.get("defaults") or {})
    if mode == "ltx25_t2v":
        return {
            "width": min(int(defaults.get("width") or 640), 640),
            "height": min(int(defaults.get("height") or 352), 352),
            "length": min(int(defaults.get("length") or 25), 25),
            "fps": min(int(defaults.get("fps") or 24), 24),
            "steps": 11,
            "cfg": 1.0,
        }
    if mode == "ltx23_t2v":
        return {
            "width": min(int(defaults.get("width") or 512), 512),
            "height": min(int(defaults.get("height") or 320), 320),
            "length": min(int(defaults.get("length") or 25), 25),
            "fps": min(int(defaults.get("fps") or 25), 25),
            "steps": 11,
            "cfg": 1.0,
        }
    if mode == "ltx_t2v":
        return {
            "width": min(int(defaults.get("width") or 512), 512),
            "height": min(int(defaults.get("height") or 320), 320),
            "length": min(int(defaults.get("length") or 25), 25),
            "fps": min(int(defaults.get("fps") or 24), 24),
            "steps": min(int(defaults.get("steps") or 12), 8),
            "cfg": float(defaults.get("cfg") or 3.0),
        }
    if mode == "hunyuan15_t2v":
        return {
            "width": min(int(defaults.get("width") or 832), 832),
            "height": min(int(defaults.get("height") or 480), 480),
            "length": min(int(defaults.get("length") or 25), 25),
            "fps": min(int(defaults.get("fps") or 24), 24),
            "steps": min(int(defaults.get("steps") or 8), 6),
            "cfg": float(defaults.get("cfg") or 1.0),
        }
    if mode == "minimax_h3_t2v":
        return {
            "width": min(int(defaults.get("width") or 608), 608),
            "height": min(int(defaults.get("height") or 352), 352),
            "length": 73,
            "fps": 24,
            "steps": min(int(defaults.get("steps") or 20), 10),
            "cfg": 1.0,
        }
    if mode == "ti2v_5b":
        return {
            "width": min(int(defaults.get("width") or 832), 832),
            "height": min(int(defaults.get("height") or 480), 480),
            "length": min(int(defaults.get("length") or 49), 49),
            "fps": min(int(defaults.get("fps") or 24), 24),
            "steps": min(int(defaults.get("steps") or 18), 8),
            "cfg": float(defaults.get("cfg") or 5.0),
        }
    return {
        "width": 832,
        "height": 480,
        "length": 49,
        "fps": 24,
        "steps": min(int(defaults.get("steps") or 4), 4),
        "cfg": float(defaults.get("cfg") or 1.0),
    }


def installable_missing_items(assets: list[dict[str, Any]], custom_nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    missing: list[dict[str, Any]] = []
    for item in assets:
        if not item.get("ok") and item.get("installable"):
            missing.append(
                {
                    "id": item.get("id"),
                    "label": item.get("label"),
                    "name": item.get("name"),
                    "item_type": "asset",
                    "path": item.get("relative_path") or item.get("path"),
                    "primary_path": item.get("primary_path") or item.get("relative_path") or item.get("path"),
                    "download_host": item.get("download_host") or "",
                    "reason": item.get("reason"),
                    "expected_bytes": item.get("expected_bytes"),
                    "downloaded_bytes": item.get("downloaded_bytes"),
                    "remaining_bytes": item.get("remaining_bytes"),
                    "expected_gb": item.get("expected_gb"),
                    "size_gb": item.get("size_gb"),
                    "partial_exists": item.get("partial_exists"),
                    "partial_gb": item.get("partial_gb"),
                    "remaining_gb": item.get("remaining_gb"),
                    "local_available": item.get("local_available"),
                    "local_path": item.get("local_path"),
                }
            )
    for item in custom_nodes:
        if not item.get("ok") and item.get("installable"):
            missing.append(
                {
                    "id": item.get("id"),
                    "label": item.get("label"),
                    "item_type": "custom_node",
                    "path": item.get("relative_path") or item.get("path"),
                    "download_host": item.get("download_host") or "",
                    "reason": item.get("reason"),
                    "expected_gb": item.get("expected_gb"),
                    "size_gb": item.get("size_gb"),
                    "partial_exists": item.get("partial_exists"),
                    "partial_gb": item.get("partial_gb"),
                    "remaining_gb": item.get("remaining_gb"),
                }
            )
    return missing


INSTALL_PROFILE_ASSETS = {
    profile_id: {str(item) for item in profile.get("asset_ids") or []}
    for profile_id, profile in CATALOG_INSTALL_PROFILES.items()
}

INSTALL_PROFILE_CUSTOM_NODES = {
    profile_id: {str(item) for item in profile.get("custom_node_ids") or []}
    for profile_id, profile in CATALOG_INSTALL_PROFILES.items()
}

INSTALL_PROFILE_INFO = {
    "auto": {
        "label": "跟随当前模型",
        "description": "使用当前目标模型的安装档位；手动接入模型会保持手动，不会偷偷回退到别的模型。",
    },
    **{
        profile_id: {
            "label": str(profile.get("label") or profile_id),
            "description": str(profile.get("description") or ""),
            "installable": bool(profile.get("installable")),
            "requires_active_base": bool(profile.get("requires_active_base")),
            "external_requirement": str(profile.get("external_requirement") or ""),
            "required_comfy_version": str(profile.get("required_comfy_version") or ""),
            "order": int(profile.get("order") or 50),
        }
        for profile_id, profile in CATALOG_INSTALL_PROFILES.items()
    },
}


def numeric_version(value: str | None) -> tuple[int, ...]:
    numbers = [int(part) for part in re.findall(r"\d+", str(value or ""))[:4]]
    return tuple(numbers)


def version_at_least(current: str | None, required: str | None) -> bool:
    current_parts = numeric_version(current)
    required_parts = numeric_version(required)
    if not current_parts or not required_parts:
        return False
    width = max(len(current_parts), len(required_parts))
    return current_parts + (0,) * (width - len(current_parts)) >= required_parts + (0,) * (width - len(required_parts))


def normalize_install_profile(profile: str | None) -> str:
    profile = (profile or "auto").strip()
    if profile == "auto" or profile in CATALOG_INSTALL_PROFILES:
        return profile
    return "auto"


def install_profile_for_asset(asset_id: str, preferred_profile: str = "") -> str | None:
    asset_id = str(asset_id or "").strip()
    if not asset_id:
        return None
    preferred_profile = str(preferred_profile or "").strip()
    if (
        preferred_profile in CATALOG_INSTALL_PROFILES
        and INSTALL_PROFILE_INFO.get(preferred_profile, {}).get("installable")
        and asset_id in INSTALL_PROFILE_ASSETS.get(preferred_profile, set())
    ):
        return preferred_profile
    candidates = [
        profile_id
        for profile_id, profile in CATALOG_INSTALL_PROFILES.items()
        if profile.get("installable") and asset_id in INSTALL_PROFILE_ASSETS.get(profile_id, set())
    ]
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda profile_id: (
            len(INSTALL_PROFILE_ASSETS.get(profile_id, set())),
            int(INSTALL_PROFILE_INFO.get(profile_id, {}).get("order") or 50),
            profile_id,
        ),
    )


def install_profile_for_hardware(hardware: dict[str, Any]) -> str:
    strategy = hardware.get("platform_strategy")
    tier = str(hardware.get("mac_video_tier") or "")
    if strategy == "mac_mps":
        if tier.startswith("mac_wan5b"):
            return "mac-wan5b"
        if tier in {"mac_ltx_balanced", "mac_ltx_quality"}:
            return "mac-balanced"
        return "mac-low"
    if strategy == "mac_post_only" or strategy == "post_only":
        return "post-only"
    if strategy in {"cuda_multi_model", "cuda_wan_workflow"}:
        max_vram = float(hardware.get("max_vram_gb") or 0)
        if max_vram >= 80:
            return "minimax-h3-fl2va-int8"
        if max_vram >= 40:
            return "ltx25-distilled-int8"
        if max_vram >= 16:
            return "hunyuan15-t2v-480-fp8"
        return "ltx098"
    return "post-only"


def install_profile_for_selected_model(hardware_profile: str, model_id: str | None = None) -> str:
    item = catalog_item_by_id(model_id or saved_model_catalog_id())
    profile = str((item or {}).get("default_install_profile") or "").strip()
    if profile in CATALOG_INSTALL_PROFILES:
        return profile
    return hardware_profile


def install_profile_options(recommended_profile: str) -> list[dict[str, Any]]:
    order = ["auto"]
    if recommended_profile in CATALOG_INSTALL_PROFILES:
        order.append(recommended_profile)
    if recommended_profile != "post-only":
        order.append("post-only")
    return [
        {
            "id": profile,
            "label": INSTALL_PROFILE_INFO[profile]["label"],
            "description": INSTALL_PROFILE_INFO[profile]["description"],
            "recommended": profile == "auto" or profile == recommended_profile,
            "effective_profile": recommended_profile if profile == "auto" else profile,
            "installable": bool(INSTALL_PROFILE_INFO[recommended_profile].get("installable"))
            if profile == "auto"
            else bool(INSTALL_PROFILE_INFO[profile].get("installable")),
            "external_requirement": INSTALL_PROFILE_INFO[recommended_profile].get("external_requirement", "")
            if profile == "auto"
            else INSTALL_PROFILE_INFO[profile].get("external_requirement", ""),
            "required_comfy_version": INSTALL_PROFILE_INFO[recommended_profile].get("required_comfy_version", "")
            if profile == "auto"
            else INSTALL_PROFILE_INFO[profile].get("required_comfy_version", ""),
        }
        for profile in order
    ]


def filter_assets_for_install_profile(
    assets: list[dict[str, Any]],
    profile: str,
    include_post: bool = True,
) -> list[dict[str, Any]]:
    allowed = set(INSTALL_PROFILE_ASSETS.get(profile, INSTALL_PROFILE_ASSETS.get("cuda-full", set())))
    if not include_post:
        allowed -= {str(item) for item in CATALOG_POST_ASSET_IDS}
    return [item for item in assets if item.get("id") in allowed]


def filter_custom_nodes_for_install_profile(
    custom_nodes: list[dict[str, Any]],
    profile: str,
    include_post: bool = True,
) -> list[dict[str, Any]]:
    allowed = set(INSTALL_PROFILE_CUSTOM_NODES.get(profile, INSTALL_PROFILE_CUSTOM_NODES.get("cuda-full", set())))
    if not include_post:
        allowed -= {str(item) for item in CATALOG_OPTIONAL_POST_NODE_IDS}
    return [item for item in custom_nodes if item.get("id") in allowed]


def filter_registry_for_install_profile(
    registry_checks: list[dict[str, Any]],
    profile: str,
    include_post: bool = True,
) -> list[dict[str, Any]]:
    allowed = set(INSTALL_PROFILE_ASSETS.get(profile, INSTALL_PROFILE_ASSETS.get("cuda-full", set())))
    if not include_post:
        allowed -= {str(item) for item in CATALOG_POST_ASSET_IDS}
    return [item for item in registry_checks if item.get("id") in allowed]


def install_disk_plan_payload(base_dir: Path, profile: str, include_post: bool = True) -> dict[str, Any]:
    if not (INSTALL_SELECTED_MODEL_ITEMS and INSTALL_PLANNED_DOWNLOAD_BYTES and INSTALL_DISK_SPACE_PLAN):
        return {
            "ok": None,
            "path": str(base_dir),
            "message": "安装器磁盘预检不可用。",
        }
    try:
        try:
            model_items = INSTALL_SELECTED_MODEL_ITEMS(profile, skip_post=not include_post)
        except TypeError:
            model_items = INSTALL_SELECTED_MODEL_ITEMS(profile)
            if not include_post:
                model_items = [
                    item for item in model_items if str(item.get("id") or "") not in CATALOG_POST_ASSET_IDS
                ]
        required_bytes = INSTALL_PLANNED_DOWNLOAD_BYTES(base_dir, model_items)
        plan = INSTALL_DISK_SPACE_PLAN(base_dir, required_bytes)
        plan["message"] = (
            "磁盘空间充足。"
            if plan.get("ok")
            else "磁盘空间不足，建议清理空间或更换 ComfyUI 工作目录后再下载。"
        )
        return plan
    except Exception as exc:
        return {
            "ok": None,
            "path": str(base_dir),
            "message": f"磁盘预检失败：{exc}",
        }


def install_plan_payload(
    *,
    profile: str,
    assets: list[dict[str, Any]],
    custom_nodes: list[dict[str, Any]],
    missing: list[dict[str, Any]],
    base_dir: Path | None = None,
    include_post: bool = True,
) -> dict[str, Any]:
    profile_info = INSTALL_PROFILE_INFO.get(profile, {})
    selected_assets = filter_assets_for_install_profile(assets, profile, include_post=include_post)
    selected_nodes = filter_custom_nodes_for_install_profile(custom_nodes, profile, include_post=include_post)
    total_expected_gb = round(sum(float(item.get("expected_gb") or 0) for item in selected_assets), 2)
    missing_expected_gb = round(sum(float(item.get("expected_gb") or 0) for item in missing), 2)
    return {
        "profile": profile,
        "profile_label": profile_info.get("label") or profile,
        "installable": bool(profile_info.get("installable", True)),
        "external_requirement": profile_info.get("external_requirement") or "",
        "required_comfy_version": profile_info.get("required_comfy_version") or "",
        "include_post": include_post,
        "asset_count": len(selected_assets),
        "custom_node_count": len(selected_nodes),
        "total_expected_gb": total_expected_gb,
        "missing_expected_gb": missing_expected_gb,
        "disk": install_disk_plan_payload(base_dir or BASE_DIR, profile, include_post=include_post),
        "items": [
            {
                "id": item.get("id"),
                "label": item.get("label"),
                "item_type": "asset" if item in selected_assets else "custom_node",
                "ok": bool(item.get("ok")),
                "expected_gb": item.get("expected_gb"),
                "path": item.get("relative_path") or item.get("path"),
                "download_host": item.get("download_host") or "",
                "local_available": item.get("local_available"),
                "local_path": item.get("local_path"),
            }
            for item in selected_assets + selected_nodes
        ],
    }


def install_base_dir_for_profile(profile: str, target_dir: str, active_base_dir: Path) -> Path:
    if INSTALL_PROFILE_INFO.get(profile, {}).get("requires_active_base"):
        if target_dir:
            try:
                requested = normalize_model_download_dir(target_dir, active_base_dir)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            if os.path.normcase(str(requested)) != os.path.normcase(str(active_base_dir)):
                raise HTTPException(
                    status_code=400,
                    detail=f"{INSTALL_PROFILE_INFO.get(profile, {}).get('label', profile)} 必须安装到当前 ComfyUI 目录：{active_base_dir}",
                )
        return active_base_dir
    try:
        return normalize_model_download_dir(target_dir or saved_model_download_dir(), active_base_dir)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


async def install_profile_plan_payload(profile: str = "auto", target_dir: str = "") -> dict[str, Any]:
    requested_profile = normalize_install_profile(profile)
    system_stats_for_profile: dict[str, Any] | None = None
    try:
        system_stats_for_profile = await comfy_get("/system_stats")
    except HTTPException:
        system_stats_for_profile = None
    hardware = build_hardware_summary(system_stats_for_profile)
    hardware_profile = install_profile_for_hardware(hardware)
    recommended_profile = install_profile_for_selected_model(hardware_profile)
    effective_profile = recommended_profile if requested_profile == "auto" else requested_profile
    comfy_paths = comfy_paths_from_system_stats(system_stats_for_profile)
    active_base_dir = Path(comfy_paths["base_dir"])
    install_base_dir = install_base_dir_for_profile(effective_profile, target_dir, active_base_dir)
    assets = filter_assets_for_install_profile(collect_asset_checks(install_base_dir), effective_profile)
    custom_nodes = filter_custom_nodes_for_install_profile(collect_custom_node_checks(active_base_dir), effective_profile)
    missing = installable_missing_items(assets, custom_nodes)
    return {
        "requested_profile": requested_profile,
        "profile": effective_profile,
        "recommended_profile": recommended_profile,
        "hardware_profile": hardware_profile,
        "selected_model_id": saved_model_catalog_id(),
        "profile_label": INSTALL_PROFILE_INFO.get(effective_profile, {}).get("label", effective_profile),
        "profile_description": INSTALL_PROFILE_INFO.get(effective_profile, {}).get("description", ""),
        "install_profiles": install_profile_options(recommended_profile),
        "base_dir": str(install_base_dir),
        "active_base_dir": str(active_base_dir),
        "custom_target": os.path.normcase(str(install_base_dir)) != os.path.normcase(str(active_base_dir)),
        "paths": serializable_comfy_paths(comfy_paths),
        "missing_installable": missing,
        "install_plan": install_plan_payload(
            profile=effective_profile,
            assets=assets,
            custom_nodes=custom_nodes,
            missing=missing,
            base_dir=install_base_dir,
        ),
    }


def install_command_text(command: list[str]) -> str:
    if platform.system() == "Windows":
        return subprocess.list2cmdline(command)
    return " ".join(command)


def classify_install_failure(log_lines: list[str], return_code: int | None = None, kind: str = "install") -> dict[str, Any]:
    text = "\n".join(log_lines[-80:])
    lowered = text.lower()
    title = "安装任务失败"
    message = "安装没有完成。请先复制诊断信息，再按建议处理后重试。"
    actions = [
        "点击“复制诊断信息”保存当前环境和日志。",
        "重新点击安装按钮；已下载的完整文件会跳过，.part 半截文件会断点续传。",
    ]
    category = "unknown"

    if "安装脚本不存在" in text or "script not found" in lowered or "no such file or directory" in lowered:
        category = "missing_script"
        title = "安装脚本缺失"
        message = "发布包或项目文件不完整，安装入口找不到需要执行的脚本。"
        actions = [
            "重新下载完整发布包，确认 scripts 目录没有被安全软件或手动操作删除。",
            "在发布包目录运行 python scripts/self_check.py --json，确认文件完整。",
        ]
    elif "not enough free disk space" in lowered or "磁盘空间不足" in text or "space" in lowered and "free" in lowered:
        category = "disk"
        title = "磁盘空间不足"
        message = "目标磁盘空间不够，安装已停止，未开始继续下载。"
        actions = [
            "清理目标磁盘，或把 COMFY_BASE_DIR / COMFY_INSTALL_DIR 指到更大的磁盘。",
            "也可以先切换到 Wan5B 保守档或仅后期工具，再重新安装。",
        ]
    elif any(
        token in lowered
        for token in ("agree and access", "gated", "hf_token", "hf auth login")
    ) or (
        any(token in lowered for token in ("401", "403", "unauthorized", "forbidden"))
        and "huggingface" in lowered
    ):
        category = "license"
        title = "需要先接受模型许可"
        message = "Hugging Face 拒绝了下载。请先在模型页点击 Agree and Access，再运行 hf auth login 或设置 HF_TOKEN。"
        actions = [
            "打开对应 Hugging Face 模型页，登录后点击 Agree and Access。",
            "本机运行 hf auth login，或设置 HF_TOKEN 后重试。",
            "许可未通过时续传也不会成功，不要把它当成普通网络抖动。",
        ]
    elif any(token in lowered for token in ("could not download", "urlopen", "timed out", "timeout", "ssl", "connection reset", "429", "huggingface.co", "github.com", "pypi.org", "download.pytorch.org", "下载网络预检")):
        category = "network"
        title = "下载网络不稳定"
        message = "模型或源码下载没有完成。已保留 .part 半截文件时，下次会从剩余字节继续。"
        actions = [
            "检查代理、DNS、防火墙、Hugging Face/GitHub/PyPI/PyTorch 下载源访问后重试。",
            "不要手动删除 .part 文件；重试会优先断点续传。",
            "如果持续 403/429，稍后再试或换网络。",
        ]
    elif any(token in lowered for token in ("larger than expected", "size check failed", "大小不一致", "incomplete")):
        category = "file_size"
        title = "文件大小异常"
        message = "检测到文件大小与 manifest 不一致，可能是下载被网页错误页、代理缓存或半截文件污染。"
        actions = [
            "删除日志里提到的异常文件或对应 .part 文件。",
            "重新点击一键安装，让安装器重新下载并校验大小。",
        ]
    elif any(token in lowered for token in ("pip install", "no matching distribution", "failed building wheel", "requirements.txt")):
        category = "python_dependency"
        title = "Python 依赖安装失败"
        message = "ComfyUI 或自定义节点依赖安装失败，常见原因是 Python 版本、pip 网络源或编译依赖问题。"
        actions = [
            "确认 Python 是 3.10-3.12。",
            "换网络后重试；必要时先单独运行日志里的 pip 命令。",
            "macOS 如遇编译依赖，先安装命令行工具或 Homebrew 依赖。",
        ]
    elif any(token in lowered for token in ("git clone", "git pull", "repository", "fatal:")):
        category = "git"
        title = "Git 更新/克隆失败"
        message = "源码仓库拉取失败。没有 Git 时会走 ZIP 兜底；已有 Git 但网络不稳定时可能失败。"
        actions = [
            "检查 GitHub 访问和代理设置后重试。",
            "如果已有节点目录损坏，可删除对应 custom_nodes 子目录后重试。",
        ]
    elif any(token in lowered for token in ("python", "not supported", "venv", "ensurepip")):
        category = "python_runtime"
        title = "Python/虚拟环境异常"
        message = "Python 版本或虚拟环境创建失败。"
        actions = [
            "安装 Python 3.12 后重新运行 START_WORKFLOW 启动器。",
            "如果 .venv 已损坏，可删除项目 .venv 后重新启动。",
        ]
    elif kind == "start_comfyui":
        category = "comfyui_start"
        title = "ComfyUI 启动失败"
        message = "ComfyUI 进程启动后退出或报错。"
        actions = [
            "查看日志尾部的缺失节点、模型或 Python 报错。",
            "重新执行安装/修复缺失项，然后再启动 ComfyUI。",
        ]

    return {
        "category": category,
        "title": title,
        "message": message,
        "actions": actions,
        "return_code": return_code,
    }


def attach_failure_hint(job: dict[str, Any]) -> None:
    if job.get("status") != "failed":
        return
    job["failure_hint"] = classify_install_failure(
        [str(line) for line in job.get("log", [])],
        return_code=job.get("return_code"),
        kind=str(job.get("kind") or "install"),
    )


def append_job_log(job: dict[str, Any], line: str) -> None:
    job["log"].append(line.rstrip())
    if len(job["log"]) > 800:
        job["log"] = job["log"][-800:]
    persist_job_stores()


def gib_to_bytes(value: Any) -> int:
    try:
        return max(0, int(float(value or 0) * 1024**3))
    except (TypeError, ValueError):
        return 0


def initialize_install_progress(items: list[dict[str, Any]]) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    for item in items:
        expected = int(item.get("expected_bytes") or 0) or gib_to_bytes(item.get("expected_gb"))
        downloaded = int(item.get("downloaded_bytes") or 0) or gib_to_bytes(
            item.get("partial_gb") or item.get("size_gb")
        )
        if item.get("local_available") and expected:
            downloaded = expected
        downloaded = max(0, min(downloaded, expected)) if expected else 0
        status = "cached" if item.get("local_available") else "partial" if downloaded else "pending"
        files.append(
            {
                "id": str(item.get("id") or ""),
                "label": str(item.get("label") or item.get("id") or "安装项"),
                "name": str(item.get("name") or Path(str(item.get("path") or "")).name),
                "path": str(item.get("primary_path") or item.get("path") or ""),
                "item_type": str(item.get("item_type") or ("asset" if expected else "custom_node")),
                "expected_bytes": expected,
                "downloaded_bytes": downloaded,
                "expected_gb": round(expected / 1024**3, 3) if expected else None,
                "downloaded_gb": round(downloaded / 1024**3, 3) if expected else None,
                "percent": round(downloaded / expected * 100, 1) if expected else None,
                "status": status,
            }
        )
    progress: dict[str, Any] = {
        "state": "queued",
        "percent": 0.0,
        "total_bytes": 0,
        "downloaded_bytes": 0,
        "total_gb": 0.0,
        "downloaded_gb": 0.0,
        "current_file": "",
        "current_file_percent": None,
        "speed_mb_s": None,
        "eta_seconds": None,
        "files": files,
        "updated_at": now_ms(),
    }
    recompute_install_progress(progress)
    return progress


def recompute_install_progress(progress: dict[str, Any]) -> None:
    files = progress.get("files") or []
    total = sum(int(item.get("expected_bytes") or 0) for item in files)
    downloaded = sum(
        min(int(item.get("downloaded_bytes") or 0), int(item.get("expected_bytes") or 0))
        for item in files
    )
    progress["total_bytes"] = total
    progress["downloaded_bytes"] = downloaded
    progress["total_gb"] = round(total / 1024**3, 3)
    progress["downloaded_gb"] = round(downloaded / 1024**3, 3)
    progress["percent"] = round(downloaded / total * 100, 1) if total else (100.0 if files else 0.0)
    progress["updated_at"] = now_ms()


def reconcile_install_progress_from_disk(job: dict[str, Any]) -> None:
    progress = job.get("progress")
    if not isinstance(progress, dict):
        return
    try:
        base_dir = Path(str(job.get("base_dir") or "")).expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        return
    missing_by_id = {
        str(item.get("id") or ""): item
        for item in (job.get("missing") or [])
        if isinstance(item, dict)
    }
    catalog_expected_by_id: dict[str, int] = {}
    try:
        catalog_expected_by_id = {
            str(item.get("id") or ""): int(item.get("bytes") or 0)
            for item in workflow_asset_manifest(base_dir)
            if item.get("id")
        }
    except (OSError, TypeError, ValueError):
        catalog_expected_by_id = {}
    for item in progress.get("files") or []:
        item_id = str(item.get("id") or "")
        source = missing_by_id.get(item_id, {})
        expected = int(catalog_expected_by_id.get(item_id) or 0)
        expected = expected or int(item.get("expected_bytes") or 0)
        expected = expected or int(source.get("expected_bytes") or 0) or gib_to_bytes(source.get("expected_gb"))
        relative_path = str(item.get("path") or source.get("path") or "").strip()
        destination = Path(relative_path).expanduser() if relative_path else None
        if destination is not None and not destination.is_absolute():
            destination = base_dir / destination
        partial = destination.with_name(destination.name + ".part") if destination is not None else None
        observed = 0
        complete = False
        try:
            if destination is not None and destination.is_file():
                observed = destination.stat().st_size
                complete = True
            elif partial is not None and partial.is_file():
                observed = partial.stat().st_size
        except OSError:
            observed = 0
        if complete and observed:
            expected = observed
            downloaded = observed
            item["status"] = "complete"
        else:
            if observed > expected:
                expected = observed
            downloaded = observed if observed else int(item.get("downloaded_bytes") or 0)
            downloaded = min(downloaded, expected) if expected else downloaded
            if observed:
                item["status"] = "downloading" if str(job.get("status") or "") == "running" else "partial"
        item["expected_bytes"] = expected
        item["downloaded_bytes"] = downloaded
        item["expected_gb"] = round(expected / 1024**3, 3) if expected else None
        item["downloaded_gb"] = round(downloaded / 1024**3, 3) if expected else None
        item["percent"] = round(downloaded / expected * 100, 1) if expected else None
    recompute_install_progress(progress)
    progress["measurement"] = "filesystem"
    sampled_at = int(progress.get("_disk_sample_at") or 0)
    sampled_bytes = int(progress.get("_disk_sample_bytes") or 0)
    current_at = now_ms()
    current_bytes = int(progress.get("downloaded_bytes") or 0)
    elapsed_ms = current_at - sampled_at if sampled_at else 0
    if elapsed_ms >= 900:
        delta = current_bytes - sampled_bytes
        if delta > 0:
            measured_speed = delta / (elapsed_ms / 1000) / 1024**2
            previous_speed = float(progress.get("speed_mb_s") or 0)
            speed = measured_speed if previous_speed <= 0 else previous_speed * 0.55 + measured_speed * 0.45
            progress["speed_mb_s"] = round(speed, 2)
            remaining = max(0, int(progress.get("total_bytes") or 0) - current_bytes)
            progress["eta_seconds"] = int(remaining / (speed * 1024**2)) if speed > 0 else None
        elif elapsed_ms >= 3_000 and str(job.get("status") or "") == "running":
            progress["speed_mb_s"] = 0.0
            progress["eta_seconds"] = None
        progress["_disk_sample_at"] = current_at
        progress["_disk_sample_bytes"] = current_bytes
    elif not sampled_at:
        progress["_disk_sample_at"] = current_at
        progress["_disk_sample_bytes"] = current_bytes


def install_progress_file(progress: dict[str, Any], name: str) -> dict[str, Any] | None:
    normalized = Path(str(name).strip()).name.lower()
    if not normalized:
        return None
    for item in progress.get("files") or []:
        aliases = {
            str(item.get("name") or "").lower(),
            Path(str(item.get("path") or "")).name.lower(),
        }
        if normalized in aliases:
            return item
    return None


def update_install_progress_from_log(job: dict[str, Any], line: str) -> None:
    progress = job.get("progress")
    if not isinstance(progress, dict):
        return
    text = line.strip()
    current: dict[str, Any] | None = None
    match = re.match(r"\[(?:download|resume|progress|ok|skip|retry|reset|size-update)\]\s+(.+?)(?::\s+\d+(?:\.\d+)?%|\s+\(|$)", text)
    if match:
        current = install_progress_file(progress, match.group(1))
    if current is not None:
        progress["current_file"] = current.get("label") or current.get("name") or ""
        expected = int(current.get("expected_bytes") or 0)
        progress_match = re.match(r"\[progress\]\s+.+?:\s+(\d+(?:\.\d+)?)%", text)
        resume_match = re.match(r"\[resume\]\s+.+?\s+\((\d+)\s+/\s+(\d+)\s+bytes\)", text)
        size_match = re.match(r"\[size-update\]\s+.+?\s+\((\d+)\s+->\s+(\d+)\s+bytes", text)
        previous_bytes = int(current.get("downloaded_bytes") or 0)
        if size_match:
            expected = int(size_match.group(2))
            current["expected_bytes"] = expected
            current["percent"] = round(previous_bytes / expected * 100, 1) if expected else None
        elif progress_match and expected:
            percent = max(0.0, min(100.0, float(progress_match.group(1))))
            current["downloaded_bytes"] = min(expected, int(expected * percent / 100))
            current["percent"] = round(percent, 1)
            current["status"] = "downloading"
        elif resume_match:
            resumed = int(resume_match.group(1))
            expected = int(resume_match.group(2))
            current["expected_bytes"] = expected
            current["downloaded_bytes"] = min(resumed, expected)
            current["percent"] = round(current["downloaded_bytes"] / expected * 100, 1) if expected else None
            current["status"] = "downloading"
        elif text.startswith("[download]"):
            current["status"] = "downloading"
        elif text.startswith(("[ok]", "[skip]")):
            current["downloaded_bytes"] = expected
            current["downloaded_gb"] = round(expected / 1024**3, 3) if expected else None
            current["percent"] = 100.0 if expected else None
            current["status"] = "complete"
        elif text.startswith("[reset]"):
            current["downloaded_bytes"] = 0
            current["downloaded_gb"] = 0.0 if expected else None
            current["percent"] = 0.0 if expected else None
            current["status"] = "pending"
        elif text.startswith("[retry]"):
            current["status"] = "retrying"
        current_bytes = int(current.get("downloaded_bytes") or 0)
        current["expected_gb"] = round(expected / 1024**3, 3) if expected else None
        current["downloaded_gb"] = round(current_bytes / 1024**3, 3) if expected else None
        progress["current_file_percent"] = current.get("percent")
        sample_at = int(progress.get("_sample_at") or 0)
        sample_bytes = int(progress.get("_sample_bytes") or 0)
        current_total = int(progress.get("downloaded_bytes") or 0) + max(0, current_bytes - previous_bytes)
        elapsed_ms = now_ms() - sample_at if sample_at else 0
        if elapsed_ms >= 900 and current_total >= sample_bytes:
            speed = (current_total - sample_bytes) / (elapsed_ms / 1000) / 1024**2
            if speed > 0:
                progress["speed_mb_s"] = round(speed, 2)
                remaining = max(0, int(progress.get("total_bytes") or 0) - current_total)
                progress["eta_seconds"] = int(remaining / (speed * 1024**2))
            progress["_sample_at"] = now_ms()
            progress["_sample_bytes"] = current_total
        elif not sample_at:
            progress["_sample_at"] = now_ms()
            progress["_sample_bytes"] = current_total
    progress["state"] = str(job.get("status") or "running")
    recompute_install_progress(progress)


def finish_install_progress(job: dict[str, Any], *, success: bool) -> None:
    progress = job.get("progress")
    if not isinstance(progress, dict):
        return
    progress["state"] = str(job.get("status") or ("success" if success else "failed"))
    if success:
        for item in progress.get("files") or []:
            expected = int(item.get("expected_bytes") or 0)
            if expected:
                item.update(
                    {
                        "downloaded_bytes": expected,
                        "downloaded_gb": round(expected / 1024**3, 3),
                        "percent": 100.0,
                        "status": "complete",
                    }
                )
        progress["current_file_percent"] = 100.0
        progress["eta_seconds"] = 0
    recompute_install_progress(progress)


def terminate_install_process(job_id: str) -> bool:
    with INSTALL_JOB_LOCK:
        process = INSTALL_PROCESSES.get(job_id)
    if not process or process.poll() is not None:
        return False
    if platform.system() == "Windows":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            **_hidden_popen_options(),
        )
    else:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            process.terminate()
    return True


def recent_jobs_payload(limit: int = 5) -> list[dict[str, Any]]:
    with INSTALL_JOB_LOCK:
        prune_completed_job_store(INSTALL_JOBS, keep=MAX_COMPLETED_INSTALL_JOBS)
        jobs = sorted(
            (dict(item) for item in INSTALL_JOBS.values()),
            key=lambda item: item.get("created_at") or 0,
            reverse=True,
        )
    payload: list[dict[str, Any]] = []
    for job in jobs[:limit]:
        payload.append(
            {
                "id": job.get("id"),
                "kind": job.get("kind"),
                "status": job.get("status"),
                "completed": job.get("completed"),
                "created_at": job.get("created_at"),
                "finished_at": job.get("finished_at"),
                "return_code": job.get("return_code"),
                "install_profile": job.get("install_profile"),
                "base_dir": job.get("base_dir"),
                "progress": job.get("progress"),
                "failure_hint": job.get("failure_hint"),
                "log_tail": [redact_sensitive_text(line) for line in job.get("log", [])[-25:]],
            }
        )
    return payload


DOWNLOAD_CENTER_MODEL_EXTENSIONS = {
    ".bin",
    ".ckpt",
    ".engine",
    ".gguf",
    ".onnx",
    ".pt",
    ".pth",
    ".safetensors",
    ".vae",
    ".zip",
}
DOWNLOAD_CENTER_IGNORED_DIRS = {".git", ".pytest_cache", "__pycache__"}


def normalized_resource_path(path: Path) -> str:
    try:
        resolved = path.expanduser().resolve()
    except (OSError, RuntimeError):
        resolved = path.expanduser().absolute()
    return os.path.normcase(str(resolved))


def download_center_storage_roots(active_base_dir: Path) -> list[dict[str, Any]]:
    candidates: list[tuple[str, Path, str]] = [("ComfyUI 当前目录", active_base_dir, "active")]
    saved = saved_model_download_dir()
    if saved:
        try:
            saved_path = Path(saved).expanduser().resolve()
            candidates.append(("自定义模型目录", saved_path, "saved"))
        except (OSError, RuntimeError):
            pass
    roots: list[dict[str, Any]] = []
    seen: set[str] = set()
    for label, path, role in candidates:
        key = normalized_resource_path(path)
        if key in seen:
            continue
        seen.add(key)
        roots.append(
            {
                "label": label,
                "path": str(path),
                "role": role,
                "exists": path.is_dir(),
                "models_path": str(path / "models"),
                "custom_nodes_path": str(path / "custom_nodes"),
            }
        )
    return roots


def download_center_catalog_maps(root: Path) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    assets: dict[str, dict[str, Any]] = {}
    nodes: dict[str, dict[str, Any]] = {}
    try:
        for item in workflow_asset_manifest(root):
            metadata = {
                "id": str(item.get("id") or ""),
                "label": str(item.get("label") or item.get("name") or ""),
                "expected_bytes": int(item.get("bytes") or 0),
                "url": str(item.get("url") or ""),
            }
            assets[normalized_resource_path(Path(item["path"]))] = metadata
            for alternative in item.get("alternatives") or []:
                if not isinstance(alternative, dict) or not alternative.get("path"):
                    continue
                alternative_metadata = dict(metadata)
                alternative_metadata["expected_bytes"] = int(alternative.get("bytes") or metadata["expected_bytes"])
                assets[normalized_resource_path(Path(alternative["path"]))] = alternative_metadata
    except (OSError, TypeError, ValueError):
        assets = {}
    try:
        for item in custom_node_manifest(root):
            nodes[normalized_resource_path(Path(item["path"]))] = {
                "id": str(item.get("id") or ""),
                "label": str(item.get("label") or item.get("id") or ""),
                "url": str(item.get("url") or ""),
            }
    except (OSError, TypeError, ValueError):
        nodes = {}
    return assets, nodes


def public_install_progress(progress: Any) -> dict[str, Any]:
    if not isinstance(progress, dict):
        return {}
    payload = {key: value for key, value in progress.items() if not str(key).startswith("_") and key != "files"}
    payload["files"] = [dict(item) for item in progress.get("files") or [] if isinstance(item, dict)]
    return payload


def download_center_transfer_payloads() -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    with INSTALL_JOB_LOCK:
        jobs = sorted(
            (
                job
                for job in INSTALL_JOBS.values()
                if str(job.get("kind") or "") in HEAVY_INSTALL_KINDS
            ),
            key=lambda item: int(item.get("created_at") or 0),
            reverse=True,
        )
    transfers: list[dict[str, Any]] = []
    path_jobs: dict[str, dict[str, Any]] = {}
    kind_labels = {
        "full_setup": "一键准备",
        "install_comfyui": "ComfyUI 安装",
        "install_workflow_assets": "模型与工作流资源",
    }
    for job in jobs:
        reconcile_install_progress_from_disk(job)
        progress = public_install_progress(job.get("progress"))
        status = str(job.get("status") or "unknown").lower()
        profile_id = str(job.get("install_profile") or "")
        profile = CATALOG_INSTALL_PROFILES.get(profile_id) or {}
        title = str(job.get("title") or profile.get("label") or kind_labels.get(str(job.get("kind") or "")) or "下载任务")
        command_args = job.get("command_args")
        can_resume = status in {"paused", "interrupted"} and isinstance(command_args, list) and bool(command_args)
        terminal = job_is_terminal(job) and status != "interrupted"
        transfer = {
            "id": str(job.get("id") or ""),
            "kind": str(job.get("kind") or ""),
            "title": title,
            "profile": profile_id,
            "status": status,
            "completed": bool(job.get("completed")),
            "created_at": job.get("created_at"),
            "started_at": job.get("started_at"),
            "finished_at": job.get("finished_at"),
            "base_dir": str(job.get("base_dir") or ""),
            "progress": progress,
            "can_pause": status in {"queued", "running"} and isinstance(command_args, list) and bool(command_args),
            "can_resume": can_resume,
            "can_cancel": not terminal and status in {"queued", "running", "pausing", "paused"},
            "error": str(job.get("error") or ""),
            "failure_hint": job.get("failure_hint") or {},
            "log_tail": [redact_sensitive_text(str(line)) for line in (job.get("log") or [])[-12:]],
        }
        transfers.append(transfer)

        try:
            base_dir = Path(str(job.get("base_dir") or "")).expanduser().resolve()
        except (OSError, RuntimeError, ValueError):
            continue
        for item in progress.get("files") or []:
            relative = str(item.get("path") or "").strip()
            if not relative:
                continue
            destination = Path(relative).expanduser()
            if not destination.is_absolute():
                destination = base_dir / destination
            key = normalized_resource_path(destination)
            path_jobs.setdefault(
                key,
                {
                    "job_id": transfer["id"],
                    "job_status": status,
                    "expected_bytes": int(item.get("expected_bytes") or 0),
                    "label": str(item.get("label") or item.get("name") or destination.name),
                },
            )
    return transfers, path_jobs


def scan_download_center_resources(
    roots: list[dict[str, Any]],
    *,
    force: bool = False,
) -> list[dict[str, Any]]:
    cache_key = "|".join(normalized_resource_path(Path(str(item["path"]))) for item in roots)
    now = time.time()
    with DOWNLOAD_CENTER_RESOURCE_CACHE_LOCK:
        cached = DOWNLOAD_CENTER_RESOURCE_CACHE
        if (
            not force
            and cached.get("key") == cache_key
            and now - float(cached.get("checked_at") or 0) < DOWNLOAD_CENTER_RESOURCE_CACHE_TTL
        ):
            return [dict(item) for item in cached.get("value") or []]

    resources: list[dict[str, Any]] = []
    for root_item in roots:
        root = Path(str(root_item["path"]))
        if not root.is_dir():
            continue
        asset_map, node_map = download_center_catalog_maps(root)
        models_root = root / "models"
        if models_root.is_dir():
            try:
                for current, directories, files in os.walk(models_root):
                    directories[:] = [name for name in directories if name not in DOWNLOAD_CENTER_IGNORED_DIRS]
                    current_path = Path(current)
                    for file_name in files:
                        partial = file_name.lower().endswith(".part")
                        final_name = file_name[:-5] if partial else file_name
                        final_suffix = Path(final_name).suffix.lower()
                        file_path = current_path / file_name
                        final_path = current_path / final_name
                        catalog = asset_map.get(normalized_resource_path(final_path), {})
                        if final_suffix not in DOWNLOAD_CENTER_MODEL_EXTENSIONS and not catalog:
                            continue
                        try:
                            stat = file_path.stat()
                        except OSError:
                            continue
                        relative = file_path.relative_to(root)
                        relative_parts = relative.parts
                        category = relative_parts[1] if len(relative_parts) > 2 else "models"
                        expected = int(catalog.get("expected_bytes") or 0)
                        size = int(stat.st_size)
                        resources.append(
                            {
                                "id": f"{root_item['role']}:{str(relative).replace(os.sep, '/')}",
                                "kind": "model",
                                "resource_type": "partial" if partial else "model",
                                "status": "partial" if partial else "installed",
                                "label": str(catalog.get("label") or final_name),
                                "name": file_name,
                                "catalog_id": str(catalog.get("id") or ""),
                                "managed": bool(catalog),
                                "category": category,
                                "size_bytes": size,
                                "expected_bytes": expected or None,
                                "percent": round(min(size, expected) / expected * 100, 1) if partial and expected else None,
                                "modified_at": int(stat.st_mtime * 1000),
                                "path": str(file_path),
                                "open_path": str(file_path.parent),
                                "relative_path": str(relative).replace("\\", "/"),
                                "storage_label": str(root_item["label"]),
                                "storage_root": str(root),
                                "_lookup_path": normalized_resource_path(final_path),
                            }
                        )
            except (OSError, PermissionError):
                pass

        nodes_root = root / "custom_nodes"
        if nodes_root.is_dir():
            try:
                node_entries = sorted(
                    (entry for entry in nodes_root.iterdir() if entry.is_dir() and entry.name not in DOWNLOAD_CENTER_IGNORED_DIRS),
                    key=lambda entry: entry.name.lower(),
                )
            except (OSError, PermissionError):
                node_entries = []
            for node_path in node_entries:
                catalog = node_map.get(normalized_resource_path(node_path), {})
                try:
                    modified_at = int(node_path.stat().st_mtime * 1000)
                except OSError:
                    modified_at = 0
                resources.append(
                    {
                        "id": f"{root_item['role']}:custom_nodes/{node_path.name}",
                        "kind": "custom_node",
                        "resource_type": "custom_node",
                        "status": "installed",
                        "label": str(catalog.get("label") or node_path.name),
                        "name": node_path.name,
                        "catalog_id": str(catalog.get("id") or ""),
                        "managed": bool(catalog),
                        "category": "custom_nodes",
                        "size_bytes": None,
                        "expected_bytes": None,
                        "percent": None,
                        "modified_at": modified_at,
                        "path": str(node_path),
                        "open_path": str(nodes_root),
                        "relative_path": f"custom_nodes/{node_path.name}",
                        "storage_label": str(root_item["label"]),
                        "storage_root": str(root),
                    }
                )

    with DOWNLOAD_CENTER_RESOURCE_CACHE_LOCK:
        DOWNLOAD_CENTER_RESOURCE_CACHE.update({"key": cache_key, "value": resources, "checked_at": time.time()})
    return [dict(item) for item in resources]


def overlay_download_job_state(
    resources: list[dict[str, Any]],
    path_jobs: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    active_statuses = {"queued", "running", "pausing", "canceling"}
    for resource in resources:
        lookup = str(resource.pop("_lookup_path", ""))
        job = path_jobs.get(lookup)
        if not job:
            continue
        resource["download_job_id"] = job["job_id"]
        resource["download_job_status"] = job["job_status"]
        if resource.get("resource_type") == "partial":
            expected = int(job.get("expected_bytes") or resource.get("expected_bytes") or 0)
            size = int(resource.get("size_bytes") or 0)
            resource["expected_bytes"] = expected or None
            resource["percent"] = round(min(size, expected) / expected * 100, 1) if expected else None
            if str(job.get("job_status") or "") in active_statuses:
                resource["status"] = "downloading"
            elif str(job.get("job_status") or "") == "paused":
                resource["status"] = "paused"
    return resources


def annotate_partial_resume_actions(resources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    active_statuses = {"queued", "running", "pausing", "canceling"}
    resumable_statuses = {"paused", "interrupted"}
    for resource in resources:
        if resource.get("resource_type") != "partial":
            continue
        asset_id = str(resource.get("catalog_id") or "").strip()
        job_id = str(resource.get("download_job_id") or "").strip()
        job = INSTALL_JOBS.get(job_id) if job_id else None
        job_status = str((job or {}).get("status") or resource.get("download_job_status") or "").lower()
        preferred_profile = str((job or {}).get("install_profile") or "")
        profile = install_profile_for_asset(asset_id, preferred_profile)
        can_resume_existing = (
            job_status in resumable_statuses
            and isinstance((job or {}).get("command_args"), list)
            and bool((job or {}).get("command_args"))
        )
        can_start_targeted = bool(resource.get("managed") and asset_id and profile and job_status not in active_statuses)
        resource["can_resume"] = bool(can_resume_existing or can_start_targeted)
        resource["resume_mode"] = "job" if can_resume_existing else "asset" if can_start_targeted else ""
        resource["resume_profile"] = profile or ""
        resource["resume_label"] = "继续原任务" if can_resume_existing else "一键续传" if can_start_targeted else ""
        if job_status in active_statuses:
            resource["resume_note"] = "该断点已有下载任务正在处理。"
        elif not resource.get("managed") or not asset_id:
            resource["resume_note"] = "未匹配到平台资源清单，无法确认原始下载地址。"
        elif not profile:
            resource["resume_note"] = "资源已登记，但没有可执行的自动安装档位。"
        else:
            resource["resume_note"] = "将保留现有 .part，并只续传这个文件。"
    return resources


def run_logged_command(job: dict[str, Any], command: list[str], *, label: str, env: dict[str, str] | None = None) -> int:
    append_job_log(job, f"{label}：{install_command_text(command)}")
    process = subprocess.Popen(
        command,
        cwd=str(WORKSPACE_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        **_hidden_popen_options(),
    )
    assert process.stdout is not None
    for line in process.stdout:
        append_job_log(job, line)
        update_install_progress_from_log(job, line)
    return process.wait()


def run_install_worker(job_id: str, command: list[str], env: dict[str, str] | None = None) -> None:
    job = INSTALL_JOBS[job_id]
    if job.get("control_action") == "pause":
        job["status"] = "paused"
        job["completed"] = False
        if isinstance(job.get("progress"), dict):
            job["progress"]["state"] = "paused"
        persist_job_stores(force=True)
        return
    job["status"] = "running"
    job["started_at"] = now_ms()
    job["completed"] = False
    job["control_action"] = ""
    if isinstance(job.get("progress"), dict):
        job["progress"]["state"] = "running"
    job["log"].append(f"启动安装：{install_command_text(command)}")
    try:
        popen_options: dict[str, Any] = _hidden_popen_options(new_process_group=True)
        process = subprocess.Popen(
            command,
            cwd=str(WORKSPACE_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            **popen_options,
        )
        with INSTALL_JOB_LOCK:
            INSTALL_PROCESSES[job_id] = process
        if job.get("control_action") in {"pause", "cancel"}:
            terminate_install_process(job_id)
        assert process.stdout is not None
        for line in process.stdout:
            append_job_log(job, line)
            update_install_progress_from_log(job, line)
        return_code = process.wait()
        job["return_code"] = return_code
        action = str(job.get("control_action") or "")
        if action == "pause":
            job["status"] = "paused"
            job["completed"] = False
            job.pop("finished_at", None)
            job["log"].append("下载已暂停；.part 文件已保留，可继续断点续传。")
            finish_install_progress(job, success=False)
        elif action == "cancel":
            job["status"] = "canceled"
            job["completed"] = True
            job["finished_at"] = now_ms()
            job["log"].append("安装任务已取消；已下载的 .part 文件仍保留。")
            finish_install_progress(job, success=False)
        elif return_code == 0:
            job["status"] = "success"
            job["completed"] = True
            job["finished_at"] = now_ms()
            job["log"].append("安装/校验完成。请重启 ComfyUI，让新节点和模型列表重新加载。")
            finish_install_progress(job, success=True)
        else:
            job["status"] = "failed"
            job["completed"] = True
            job["finished_at"] = now_ms()
            job["log"].append(f"安装脚本退出码：{return_code}")
            finish_install_progress(job, success=False)
            attach_failure_hint(job)
    except Exception as exc:
        job["status"] = "failed"
        job["completed"] = True
        job["finished_at"] = now_ms()
        job["error"] = str(exc)
        job["log"].append(f"安装失败：{exc}")
        attach_failure_hint(job)
    finally:
        with INSTALL_JOB_LOCK:
            INSTALL_PROCESSES.pop(job_id, None)
        if job.get("status") == "success":
            invalidate_runtime_caches()
        persist_job_stores(force=True)


def sync_comfy_ready_url(timeout: float = 120.0) -> str | None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        for url in common_comfy_urls():
            try:
                response = httpx.get(f"{url}/system_stats", timeout=2.0)
                if response.status_code == 200:
                    discovered = set_current_comfy_url(url)
                    with COMFY_STATE_LOCK:
                        COMFY_DISCOVERY_CACHE.update(
                            {"url": discovered, "checked_at": time.time(), "errors": []}
                        )
                    return discovered
            except Exception:
                pass
        time.sleep(1.0)
    return None


def comfy_start_command() -> list[str]:
    runtime = comfy_runtime_info()
    main_py = Path(str(runtime["main_py"]))
    python = Path(str(runtime["python"]))
    if not main_py.exists():
        raise RuntimeError(f"ComfyUI 未安装：{main_py}")
    if not python.exists():
        raise RuntimeError(f"ComfyUI Python 未就绪：{python}")
    runtime_base = Path(str(runtime.get("base_dir") or BASE_DIR)).expanduser().resolve()
    runtime_input = runtime_base / "input"
    runtime_output = runtime_base / "output"
    runtime_user = runtime_base / "user"
    runtime_database = runtime_user / "comfyui.db"
    for directory in (runtime_input, runtime_output, runtime_user):
        directory.mkdir(parents=True, exist_ok=True)
    return [
        str(python),
        str(main_py),
        "--listen",
        comfy_listen_host(),
        "--port",
        str(comfy_port()),
        "--base-directory",
        str(runtime_base),
        "--input-directory",
        str(runtime_input),
        "--output-directory",
        str(runtime_output),
        "--user-directory",
        str(runtime_user),
        "--database-url",
        f"sqlite:///{runtime_database.resolve().as_posix()}",
    ]


def comfy_start_cwd() -> Path:
    runtime = comfy_runtime_info()
    main_py = Path(str(runtime.get("main_py") or COMFY_INSTALL_DIR / "main.py"))
    if main_py.exists():
        return main_py.parent
    return COMFY_INSTALL_DIR


def monitor_comfyui_process(
    job_id: str,
    process: subprocess.Popen[str],
    *,
    update_terminal_status: bool,
    log_path: Path | None = None,
    log_offset: int = 0,
) -> None:
    job = INSTALL_JOBS.get(job_id)
    try:
        if process.stdout is not None:
            for line in process.stdout:
                if job:
                    append_job_log(job, line)
        elif log_path is not None:
            with log_path.open("r", encoding="utf-8", errors="replace") as log_stream:
                log_stream.seek(log_offset)
                while True:
                    line = log_stream.readline()
                    if line:
                        if job:
                            append_job_log(job, line)
                        continue
                    if process.poll() is not None:
                        for remaining_line in log_stream:
                            if job:
                                append_job_log(job, remaining_line)
                        break
                    time.sleep(0.25)
        return_code = process.wait()
        if not job:
            return
        job["return_code"] = return_code
        append_job_log(job, f"ComfyUI 已退出，退出码：{return_code}")
        if update_terminal_status or not job.get("completed"):
            job["status"] = "stopped" if return_code == 0 else "failed"
            job["completed"] = True
            job["finished_at"] = now_ms()
            attach_failure_hint(job)
    except Exception as exc:
        if job and (update_terminal_status or not job.get("completed")):
            job["status"] = "failed"
            job["completed"] = True
            job["finished_at"] = now_ms()
            job["error"] = str(exc)
            append_job_log(job, f"ComfyUI 日志监控失败：{exc}")
            attach_failure_hint(job)


def launch_comfyui_background(job_id: str, command: list[str], cwd: Path | None = None) -> None:
    global COMFY_PROCESS
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    with COMFY_LOG_PATH.open("a", encoding="utf-8", newline="") as log_stream:
        log_stream.write(f"\n--- ComfyUI start {time.strftime('%Y-%m-%dT%H:%M:%S')} ---\n")
        log_stream.flush()
        log_offset = log_stream.tell()
        COMFY_PROCESS = subprocess.Popen(
            command,
            cwd=str(cwd or comfy_start_cwd()),
            stdout=log_stream,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            **_hidden_popen_options(new_process_group=True),
        )
    job = INSTALL_JOBS.get(job_id)
    if job is not None:
        job["comfy_log_path"] = str(COMFY_LOG_PATH)
        append_job_log(job, f"ComfyUI 持久日志：{COMFY_LOG_PATH}")
    thread = threading.Thread(
        target=monitor_comfyui_process,
        args=(job_id, COMFY_PROCESS),
        kwargs={
            "update_terminal_status": False,
            "log_path": COMFY_LOG_PATH,
            "log_offset": log_offset,
        },
        daemon=True,
    )
    thread.start()


def launch_comfy_desktop_background(job_id: str, executable: Path) -> None:
    job = INSTALL_JOBS[job_id]
    command = [str(executable)]
    cwd = executable.parent if executable.is_file() else executable
    if platform.system() == "Darwin" and executable.suffix == ".app":
        command = ["open", str(executable)]
        cwd = executable.parent
    append_job_log(job, f"检测到 ComfyUI Desktop：{executable}")
    append_job_log(job, "已尝试启动 Desktop，正在等待 /system_stats。")
    process = subprocess.Popen(
        command,
        cwd=str(cwd),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **_hidden_popen_options(),
    )
    job["desktop_process_id"] = process.pid
    thread = threading.Thread(target=wait_for_comfyui_ready_worker, args=(job_id,), daemon=True)
    thread.start()


def mark_job_success(job: dict[str, Any], message: str) -> None:
    append_job_log(job, message)
    job["status"] = "success"
    job["completed"] = True
    job["finished_at"] = now_ms()
    persist_job_stores(force=True)


DOWNLOAD_HOST_LABELS = {
    "github.com": "GitHub",
    "huggingface.co": "Hugging Face",
    "pypi.org": "PyPI",
    "download.pytorch.org": "PyTorch 下载源",
}


def host_label(host: str) -> str:
    return DOWNLOAD_HOST_LABELS.get(host, host)


def effective_preflight_host(host: str) -> str:
    if host == "huggingface.co":
        endpoint = effective_hf_endpoint()
        if endpoint:
            return urlparse(endpoint).hostname or host
    if host == "pypi.org":
        pip_index = effective_pip_index_url()
        if pip_index:
            return urlparse(pip_index).hostname or host
    return host


def effective_comfy_install_backend(backend: str) -> str:
    normalized = (backend or "auto").strip().lower()
    if normalized != "auto":
        return normalized
    if COMFYUI_EFFECTIVE_BACKEND:
        try:
            return str(COMFYUI_EFFECTIVE_BACKEND(normalized)).strip().lower()
        except Exception:
            pass
    if platform.system() == "Darwin":
        return "mps"
    if shutil.which("nvidia-smi"):
        return "cuda"
    return "cpu"


def comfy_install_uses_pytorch_host(backend: str) -> bool:
    return effective_comfy_install_backend(backend) in {"cuda", "cpu"}


def required_download_hosts_for_full_setup(
    *,
    profile: str,
    base_dir: Path,
    backend: str,
    skip_comfy_install: bool,
    use_local_comfy_python: bool,
    custom_nodes_base_dir: Path | None = None,
) -> set[str]:
    hosts: set[str] = set()
    if not skip_comfy_install:
        hosts.update({"github.com", "pypi.org"})
        if comfy_install_uses_pytorch_host(backend):
            hosts.add("download.pytorch.org")

    selected_assets = filter_assets_for_install_profile(collect_asset_checks(base_dir), profile)
    selected_nodes = filter_custom_nodes_for_install_profile(
        collect_custom_node_checks(custom_nodes_base_dir or base_dir), profile
    )
    missing_assets = [item for item in selected_assets if not item.get("ok")]
    for item in missing_assets:
        if item.get("local_available"):
            continue
        host = str(item.get("download_host") or "")
        if host:
            hosts.add(host)
    missing_nodes = [item for item in selected_nodes if not item.get("ok")]
    for item in missing_nodes:
        host = str(item.get("download_host") or "")
        if host:
            hosts.add(host)
    if use_local_comfy_python and (missing_nodes or (selected_nodes and not skip_comfy_install)):
        hosts.add("pypi.org")
    return hosts


def required_download_hosts_for_workflow_assets(
    *,
    profile: str,
    base_dir: Path,
    use_local_comfy_python: bool,
    custom_nodes_base_dir: Path | None = None,
    repair_needed: bool = False,
    include_post: bool = True,
) -> set[str]:
    hosts: set[str] = set()
    selected_assets = filter_assets_for_install_profile(collect_asset_checks(base_dir), profile, include_post=include_post)
    selected_nodes = filter_custom_nodes_for_install_profile(
        collect_custom_node_checks(custom_nodes_base_dir or base_dir), profile, include_post=include_post
    )
    missing_assets = [item for item in selected_assets if not item.get("ok")]
    for item in missing_assets:
        if item.get("local_available"):
            continue
        host = str(item.get("download_host") or "")
        if host:
            hosts.add(host)
    missing_nodes = [item for item in selected_nodes if not item.get("ok")]
    for item in missing_nodes:
        host = str(item.get("download_host") or "")
        if host:
            hosts.add(host)
    if use_local_comfy_python and selected_nodes and (missing_assets or missing_nodes or repair_needed):
        hosts.add("pypi.org")
    return hosts


def run_download_network_preflight(job: dict[str, Any], required_hosts: set[str]) -> None:
    required_hosts = {effective_preflight_host(host) for host in required_hosts if host}
    if not required_hosts:
        append_job_log(job, "步骤 0/3：没有需要访问外网的缺失下载项，跳过下载网络预检。")
        job["network_preflight"] = {"status": "skipped", "required_hosts": []}
        return
    if not BUILD_PREREQUISITE_REPORT:
        append_job_log(job, "下载网络预检模块不可用，跳过网络预检。")
        return
    required_labels = ", ".join(host_label(host) for host in sorted(required_hosts))
    append_job_log(job, f"步骤 0/3：检查本次需要的下载源：{required_labels}。")
    report = call_with_download_env(BUILD_PREREQUISITE_REPORT, WORKSPACE_DIR, BASE_DIR, COMFY_INSTALL_DIR, include_network=True)
    network_check = next((item for item in report.get("checks", []) if item.get("id") == "network"), None)
    job["network_preflight"] = network_check or {"status": "unknown", "message": "未返回网络检查结果"}
    job["network_preflight"]["required_hosts"] = sorted(required_hosts)
    if not network_check:
        append_job_log(job, "下载网络预检未返回结果，继续安装。")
        return
    append_job_log(job, str(network_check.get("message") or "下载网络预检完成。"))
    reachable = network_check.get("reachable") or {}
    missing_required = [host for host in sorted(required_hosts) if reachable.get(host) is not True]
    job["network_preflight"]["missing_required_hosts"] = missing_required
    if missing_required:
        action = str(network_check.get("action") or "请检查网络后重试。")
        append_job_log(job, action)
        missing_labels = ", ".join(host_label(host) for host in missing_required)
        raise RuntimeError(f"下载网络预检未通过：本次需要的下载源不可达：{missing_labels}")


def required_download_hosts_for_comfy_install(backend: str) -> set[str]:
    hosts = {"github.com", "pypi.org"}
    if comfy_install_uses_pytorch_host(backend):
        hosts.add("download.pytorch.org")
    return hosts


def wait_for_comfyui_ready_worker(job_id: str, timeout: float = 180.0) -> None:
    global COMFY_START_JOB_ID
    job = INSTALL_JOBS[job_id]
    job["status"] = "running"
    job["started_at"] = job.get("started_at") or now_ms()
    try:
        ready_url = sync_comfy_ready_url(timeout=timeout)
        if ready_url:
            job["ready_url"] = ready_url
            mark_job_success(job, f"ComfyUI 已就绪：{ready_url}")
            return
        if job.get("completed"):
            return
        raise RuntimeError(f"ComfyUI 正在启动，但 {int(timeout)} 秒内没有响应 /system_stats。")
    except Exception as exc:
        if not job.get("completed"):
            job["status"] = "failed"
            job["completed"] = True
            job["finished_at"] = now_ms()
            job["error"] = str(exc)
            append_job_log(job, f"ComfyUI 启动失败：{exc}")
            attach_failure_hint(job)
    finally:
        if job.get("completed") and COMFY_START_JOB_ID == job_id:
            COMFY_START_JOB_ID = None
        if job.get("status") == "success":
            invalidate_runtime_caches()
        persist_job_stores(force=True)


def run_full_setup_worker(
    job_id: str,
    *,
    backend: str,
    profile: str,
    base_dir: Path,
    dry_run: bool,
    model_base_dir: Path | None = None,
    skip_comfy_install: bool = False,
    use_local_comfy_python: bool = True,
) -> None:
    job = INSTALL_JOBS[job_id]
    model_base_dir = model_base_dir or base_dir
    job["status"] = "running"
    job["started_at"] = now_ms()
    try:
        install_script = WORKSPACE_DIR / "scripts" / "install_comfyui.py"
        assets_script = WORKSPACE_DIR / "scripts" / "install_workflow_assets.py"
        if not install_script.exists():
            raise RuntimeError(f"安装脚本不存在：{install_script}")
        if not assets_script.exists():
            raise RuntimeError(f"安装脚本不存在：{assets_script}")

        resolved_profile = normalize_install_profile(profile)
        if resolved_profile == "auto":
            hardware_profile = install_profile_for_hardware(build_hardware_summary(None))
            resolved_profile = install_profile_for_selected_model(hardware_profile)
        if not INSTALL_PROFILE_INFO.get(resolved_profile, {}).get("installable", True):
            raise RuntimeError("当前目标模型需要手动接入，没有可执行的一键准备档位")
        job["install_profile"] = resolved_profile
        job["download_settings"] = download_settings_payload()

        if not dry_run:
            required_hosts = required_download_hosts_for_full_setup(
                profile=resolved_profile,
                base_dir=model_base_dir,
                backend=backend,
                skip_comfy_install=skip_comfy_install,
                use_local_comfy_python=use_local_comfy_python,
                custom_nodes_base_dir=base_dir,
            )
            run_download_network_preflight(job, required_hosts)

        if skip_comfy_install:
            job["source_install_skipped"] = True
            if (job.get("paths") or {}).get("source") == "running_comfyui":
                append_job_log(job, "步骤 1/3：检测到 ComfyUI 已在运行，跳过源码版 ComfyUI 安装/更新。")
                append_job_log(job, "将使用当前运行中 ComfyUI 的 active base 安装模型和节点，避免额外创建一份源码版 ComfyUI。")
            else:
                append_job_log(job, f"步骤 1/3：检测到可启动的 {job.get('runtime_label') or 'ComfyUI runtime'}，跳过额外源码安装。")
                append_job_log(job, "将直接复用该 runtime 的 Python 安装节点依赖，并在最后启动 ComfyUI。")
        else:
            install_command = [
                sys.executable,
                "-u",
                str(install_script),
                "--base-dir",
                str(base_dir),
                "--install-dir",
                str(COMFY_INSTALL_DIR),
                "--backend",
                backend,
            ]
            if dry_run:
                install_command.append("--dry-run")
            append_job_log(job, "步骤 1/3：安装或更新 ComfyUI。")
            return_code = run_logged_command(job, install_command, label="ComfyUI 安装", env=download_subprocess_env())
            if return_code != 0:
                raise RuntimeError(f"ComfyUI 安装失败，退出码：{return_code}")

        if model_base_dir != base_dir and job.get("extra_model_paths_deferred"):
            runtime_after_install = comfy_runtime_info()
            runtime_paths = dict(job.get("paths") or {})
            runtime_paths["base_dir"] = str(base_dir)
            runtime_paths["main_py"] = str(runtime_after_install.get("main_py") or runtime_paths.get("main_py") or "")
            config_path = register_comfy_extra_model_path(model_base_dir, runtime_paths)
            job["extra_model_paths_config"] = config_path
            job["extra_model_paths_deferred"] = False
            append_job_log(job, f"已把自定义模型目录注册到 ComfyUI：{config_path}")

        assets_command = [
            sys.executable,
            "-u",
            str(assets_script),
            "--base-dir",
            str(model_base_dir),
            "--profile",
            resolved_profile,
        ]
        if model_base_dir != base_dir:
            assets_command.extend(["--custom-nodes-base-dir", str(base_dir)])
        python = comfy_venv_python()
        if use_local_comfy_python and python.exists():
            assets_command.extend(["--comfy-python", str(python)])
        elif not use_local_comfy_python:
            append_job_log(job, "检测到运行中的 ComfyUI 可能来自 Desktop 或外部目录；不会把本项目 venv 当作节点 Python。")
            append_job_log(job, "如果节点下载后未加载，请在 ComfyUI Desktop/管理器里安装节点依赖并重启 ComfyUI。")
        if dry_run:
            assets_command.append("--dry-run")
        append_job_log(job, f"步骤 2/3：安装当前档位资源：{resolved_profile}。")
        return_code = run_logged_command(job, assets_command, label="模型/节点安装", env=download_subprocess_env())
        if return_code != 0:
            raise RuntimeError(f"模型/节点安装失败，退出码：{return_code}")

        if dry_run:
            append_job_log(job, "dry-run 完成：没有下载模型，也没有写入 ComfyUI。")
            job["status"] = "success"
            job["completed"] = True
            job["finished_at"] = now_ms()
            finish_install_progress(job, success=True)
            return

        append_job_log(job, "步骤 3/3：启动 ComfyUI 并等待服务就绪。")
        ready_url = sync_comfy_ready_url(timeout=3.0)
        if ready_url:
            job["restart_required"] = True
            append_job_log(job, f"检测到 ComfyUI 已在运行：{ready_url}")
            append_job_log(job, "如果本次刚安装了新节点或新模型，请重启 ComfyUI 后再运行生成链路测试。")
            job["status"] = "success"
            job["completed"] = True
            job["finished_at"] = now_ms()
            finish_install_progress(job, success=True)
            return

        command = comfy_start_command()
        job["start_command"] = install_command_text(command)
        launch_comfyui_background(job_id, command)
        ready_url = sync_comfy_ready_url(timeout=180.0)
        if not ready_url:
            raise RuntimeError("ComfyUI 已尝试启动，但 180 秒内没有响应 /system_stats。")

        append_job_log(job, f"ComfyUI 已启动：{ready_url}")
        append_job_log(job, "一键准备完成。下一步点击“生成链路测试”，确认真实视频生成链路。")
        job["status"] = "success"
        job["completed"] = True
        job["finished_at"] = now_ms()
        finish_install_progress(job, success=True)
    except Exception as exc:
        job["status"] = "failed"
        job["completed"] = True
        job["finished_at"] = now_ms()
        job["error"] = str(exc)
        append_job_log(job, f"一键准备失败：{exc}")
        finish_install_progress(job, success=False)
        attach_failure_hint(job)
    finally:
        if job.get("status") == "success":
            invalidate_runtime_caches()
        persist_job_stores(force=True)


def run_json_command(command: list[str], timeout: int = 180, env: dict[str, str] | None = None) -> dict[str, Any]:
    result = subprocess.run(
        command,
        cwd=str(WORKSPACE_DIR),
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout,
        **_hidden_popen_options(),
    )
    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()
    parsed: dict[str, Any] | None = None
    if stdout:
        try:
            parsed = json.loads(stdout)
        except json.JSONDecodeError:
            parsed = None
    return {
        "command": install_command_text(command),
        "return_code": result.returncode,
        "ok": bool(parsed.get("ok")) if isinstance(parsed, dict) and "ok" in parsed else result.returncode == 0,
        "json": parsed,
        "stdout_tail": stdout[-2000:],
        "stderr_tail": stderr[-2000:],
    }


def run_self_test_worker(job_id: str) -> None:
    job = INSTALL_JOBS[job_id]
    job["status"] = "running"
    job["started_at"] = now_ms()
    job["log"].append("开始本机自检：不会下载模型，也不会启动真实生成。")
    commands = [
        [
            sys.executable,
            str(WORKSPACE_DIR / "scripts" / "prerequisite_doctor.py"),
            "--json",
            "--base-dir",
            str(BASE_DIR),
            "--install-dir",
            str(COMFY_INSTALL_DIR),
        ],
        [sys.executable, str(WORKSPACE_DIR / "scripts" / "self_check.py"), "--json"],
    ]
    command_env = download_subprocess_env()
    command_env.pop("COMFY_URL", None)
    command_env["PYTHONDONTWRITEBYTECODE"] = "1"
    results: list[dict[str, Any]] = []
    try:
        for command in commands:
            job["log"].append(f"运行：{install_command_text(command)}")
            result = run_json_command(command, env=command_env)
            results.append(result)
            status_text = "通过" if result["ok"] else "未通过"
            job["log"].append(f"{Path(command[1]).name}：{status_text}，退出码 {result['return_code']}")
            if result.get("stderr_tail"):
                job["log"].append(str(result["stderr_tail"])[-1000:])
            if not result["ok"] and result.get("stdout_tail"):
                job["log"].append(str(result["stdout_tail"])[-1000:])
            if len(job["log"]) > 600:
                job["log"] = job["log"][-600:]
        job["self_test"] = {
            "ok": all(item["ok"] for item in results),
            "results": results,
        }
        job["status"] = "success" if job["self_test"]["ok"] else "failed"
        job["completed"] = True
        job["finished_at"] = now_ms()
        if job["status"] == "success":
            job["log"].append("本机自检通过。")
        else:
            job["log"].append("本机自检发现问题；请点击“复制诊断信息”保存结果。")
            attach_failure_hint(job)
    except Exception as exc:
        job["status"] = "failed"
        job["completed"] = True
        job["finished_at"] = now_ms()
        job["error"] = str(exc)
        job["log"].append(f"本机自检失败：{exc}")
        attach_failure_hint(job)
    finally:
        persist_job_stores(force=True)


def venv_python_for(venv_root: Path) -> Path:
    if platform.system() == "Windows":
        return venv_root / "Scripts" / "python.exe"
    return venv_root / "bin" / "python"


def source_comfy_python() -> Path:
    return venv_python_for(COMFY_INSTALL_DIR / ".venv")


def base_comfy_python() -> Path:
    return venv_python_for(BASE_DIR / ".venv")


def path_exists(path: Path | None) -> bool:
    return bool(path and path.exists())


def unique_existing_paths(paths: list[Path]) -> list[Path]:
    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        try:
            resolved = path.expanduser().resolve()
        except Exception:
            continue
        key = str(resolved).lower() if platform.system() == "Windows" else str(resolved)
        if key in seen:
            continue
        seen.add(key)
        unique.append(resolved)
    return unique


def comfy_desktop_roots() -> list[Path]:
    candidates: list[Path] = []
    for env_name in ("COMFY_DESKTOP_DIR", "COMFY_DESKTOP_ROOT"):
        configured = os.environ.get(env_name)
        if configured:
            candidates.append(Path(configured))
    for env_name in ("COMFY_DESKTOP_EXE", "COMFY_DESKTOP_APP"):
        configured = os.environ.get(env_name)
        if configured:
            path = Path(configured)
            candidates.append(path if path.is_dir() else path.parent)
    candidates.extend(
        [
            BASE_DIR / "ComfyUI",
            WORKSPACE_DIR.parent / "ComfyUI",
            COMFY_INSTALL_DIR,
            WORKSPACE_DIR / "ComfyUI",
        ]
    )
    if platform.system() == "Windows":
        local_app_data = os.environ.get("LOCALAPPDATA")
        program_files = os.environ.get("ProgramFiles")
        program_files_x86 = os.environ.get("ProgramFiles(x86)")
        if local_app_data:
            candidates.extend(
                [
                    Path(local_app_data) / "Comfy-Desktop",
                    Path(local_app_data) / "Programs" / "Comfy Desktop",
                    Path(local_app_data) / "Programs" / "ComfyUI",
                ]
            )
        if program_files:
            candidates.append(Path(program_files) / "Comfy Desktop")
        if program_files_x86:
            candidates.append(Path(program_files_x86) / "Comfy Desktop")
    if platform.system() == "Darwin":
        candidates.extend(
            [
                Path("/Applications/ComfyUI.app"),
                BASE_DIR / "ComfyUI.app",
                WORKSPACE_DIR.parent / "ComfyUI.app",
            ]
        )
    return unique_existing_paths(candidates)


def comfy_desktop_executable() -> Path | None:
    env_path = os.environ.get("COMFY_DESKTOP_EXE") or os.environ.get("COMFY_DESKTOP_APP")
    if env_path:
        candidate = Path(env_path).expanduser()
        if candidate.exists():
            return candidate.resolve()
    names = ["Comfy Desktop.exe", "ComfyUI.exe", "ComfyUI"]
    if platform.system() == "Darwin":
        names = ["ComfyUI.app", "ComfyUI"]
    for root in comfy_desktop_roots():
        for name in names:
            candidate = root / name
            if candidate.exists():
                return candidate.resolve()
        if root.name.endswith(".app") and root.exists():
            return root.resolve()
    return None


def bundled_comfy_main_py() -> Path | None:
    candidates: list[Path] = []
    for root in comfy_desktop_roots():
        candidates.extend(
            [
                root / "resources" / "ComfyUI" / "main.py",
                root / "Contents" / "Resources" / "ComfyUI" / "main.py",
                root / "Comfy Desktop" / "resources" / "ComfyUI" / "main.py",
                root / "ComfyUI-Installs" / "ComfyUI" / "ComfyUI" / "main.py",
            ]
        )
    configured_runtime = os.environ.get("COMFY_DESKTOP_RUNTIME_DIR")
    if configured_runtime:
        candidates.append(Path(configured_runtime) / "main.py")
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidates.append(
            Path(local_app_data)
            / "Comfy-Desktop"
            / "ComfyUI-Installs"
            / "ComfyUI"
            / "ComfyUI"
            / "main.py"
        )
    for candidate in unique_existing_paths(candidates):
        if candidate.exists():
            return candidate
    return None


def comfy_runtime_info() -> dict[str, Any]:
    source_main = (COMFY_INSTALL_DIR / "main.py").expanduser().resolve()
    source_python = source_comfy_python().expanduser().resolve()
    bundled_main = bundled_comfy_main_py()
    desktop_python = None
    if bundled_main:
        desktop_python = next(
            (
                candidate.resolve()
                for candidate in (
                    venv_python_for(bundled_main.parent / ".venv"),
                    base_comfy_python(),
                )
                if candidate.exists()
            ),
            venv_python_for(bundled_main.parent / ".venv").resolve(),
        )
    desktop_shared = detected_comfy_desktop_shared_dir()
    desktop_exe = comfy_desktop_executable()
    runtime_preference = str(os.environ.get("COMFY_RUNTIME") or "").strip().lower()

    if bundled_main and desktop_python and desktop_python.exists() and runtime_preference != "source":
        return {
            "kind": "desktop_runtime",
            "label": "ComfyUI Desktop 共享运行时",
            "main_py": bundled_main,
            "python": desktop_python,
            "cwd": bundled_main.parent,
            "base_dir": desktop_shared or BASE_DIR,
            "source_ready": True,
            "desktop_available": bool(desktop_exe),
            "desktop_exe": str(desktop_exe or ""),
            "bundled_main": str(bundled_main),
        }

    if source_main.exists() and source_python.exists():
        return {
            "kind": "source",
            "label": "源码版 ComfyUI",
            "main_py": source_main,
            "python": source_python,
            "cwd": source_main.parent,
            "base_dir": BASE_DIR,
            "source_ready": True,
            "desktop_available": bool(desktop_exe),
            "desktop_exe": str(desktop_exe or ""),
            "bundled_main": str(bundled_main or ""),
        }
    if bundled_main:
        return {
            "kind": "desktop_runtime_missing_python",
            "label": "ComfyUI Desktop 共享运行时",
            "main_py": bundled_main,
            "python": desktop_python or base_comfy_python().expanduser().resolve(),
            "cwd": bundled_main.parent,
            "base_dir": desktop_shared or BASE_DIR,
            "source_ready": False,
            "desktop_available": bool(desktop_exe),
            "desktop_exe": str(desktop_exe or ""),
            "bundled_main": str(bundled_main),
        }
    return {
        "kind": "missing",
        "label": "源码版 ComfyUI",
        "main_py": source_main,
        "python": source_python,
        "cwd": COMFY_INSTALL_DIR,
        "base_dir": BASE_DIR,
        "source_ready": False,
        "desktop_available": bool(desktop_exe),
        "desktop_exe": str(desktop_exe or ""),
        "bundled_main": "",
    }


def comfy_venv_python() -> Path:
    runtime = comfy_runtime_info()
    return Path(str(runtime["python"]))


def comfy_port() -> int:
    parsed = urlparse(current_comfy_url())
    if parsed.port:
        return int(parsed.port)
    return 8000


def comfy_listen_host() -> str:
    parsed = urlparse(current_comfy_url())
    return parsed.hostname or "127.0.0.1"


def bootstrap_status_payload(
    comfy_connected: bool,
    comfy_error: str = "",
    paths: dict[str, Any] | None = None,
    request: Request | None = None,
) -> dict[str, Any]:
    runtime = comfy_runtime_info()
    main_py = Path(str(runtime["main_py"]))
    python = Path(str(runtime["python"]))
    paths = paths or configured_comfy_paths()
    if COMFYUI_DISK_PLAN:
        try:
            install_disk = COMFYUI_DISK_PLAN(COMFY_INSTALL_DIR, "auto")
            install_disk["message"] = "安装空间充足。" if install_disk.get("ok") else "安装空间不足，建议清理磁盘或调整 COMFY_INSTALL_DIR。"
        except Exception as exc:
            install_disk = {"ok": None, "message": f"安装空间预检失败：{exc}", "path": str(COMFY_INSTALL_DIR)}
    else:
        install_disk = {"ok": None, "message": "安装空间预检不可用。", "path": str(COMFY_INSTALL_DIR)}
    prerequisites = (
        call_with_download_env(BUILD_PREREQUISITE_REPORT, WORKSPACE_DIR, BASE_DIR, COMFY_INSTALL_DIR, include_network=False)
        if BUILD_PREREQUISITE_REPORT
        else {
            "ok": None,
            "blocked_count": 0,
            "warning_count": 0,
            "checks": [],
            "network_checked": False,
        }
    )
    return {
        "base_dir": str(BASE_DIR),
        "active_base_dir": str(paths["base_dir"]),
        "paths": serializable_comfy_paths(paths),
        "install_dir": str(COMFY_INSTALL_DIR),
        "install_disk": install_disk,
        "prerequisites": prerequisites,
        "download_settings": download_settings_payload(),
        "service": service_config_payload(request, include_sensitive=is_loopback_request(request)),
        "comfy_url": current_comfy_url(),
        "comfy_url_configured": COMFY_URL_CONFIGURED,
        "comfy_candidate_urls": common_comfy_urls(),
        "comfy_connected": comfy_connected,
        "comfy_error": comfy_error,
        "comfy_repo_exists": main_py.exists(),
        "comfy_main": str(main_py),
        "runtime_kind": runtime.get("kind"),
        "runtime_label": runtime.get("label"),
        "runtime_source_ready": bool(runtime.get("source_ready")),
        "desktop_available": bool(runtime.get("desktop_available")),
        "desktop_exe": str(runtime.get("desktop_exe") or ""),
        "bundled_main": str(runtime.get("bundled_main") or ""),
        "venv_python": str(python),
        "venv_ready": python.exists(),
        "git_ready": bool(shutil.which("git")),
        "python": sys.version.split()[0],
        "platform": platform.system(),
        "can_install_comfyui": True,
        "can_start_comfyui": bool(runtime.get("source_ready") or runtime.get("desktop_available")),
        "running_from_launcher": True,
        "nsfw_playbook": playbook_payload(read_local_config()),
        "character_box": character_box_payload(read_local_config()),
    }


def run_comfyui_worker(job_id: str, command: list[str]) -> None:
    global COMFY_START_JOB_ID
    job = INSTALL_JOBS[job_id]
    job["status"] = "running"
    job["started_at"] = now_ms()
    job["log"].append(f"启动 ComfyUI：{install_command_text(command)}")
    try:
        launch_comfyui_background(job_id, command)
        wait_for_comfyui_ready_worker(job_id)
    except Exception as exc:
        if not job.get("completed"):
            job["status"] = "failed"
            job["completed"] = True
            job["finished_at"] = now_ms()
            job["error"] = str(exc)
            job["log"].append(f"ComfyUI 启动失败：{exc}")
            attach_failure_hint(job)
    finally:
        if job.get("completed"):
            COMFY_START_JOB_ID = None
            invalidate_runtime_caches()
        persist_job_stores(force=True)


def report_local_progress(callback: Any, value: int, note: str) -> None:
    if callback:
        callback(clamp_int(value, 0, 100), note)


def ffprobe_path(ffmpeg_path: str | None = None) -> str | None:
    ffmpeg = Path(ffmpeg_path or find_ffmpeg())
    sibling = ffmpeg.with_name("ffprobe.exe" if platform.system() == "Windows" else "ffprobe")
    if sibling.is_file():
        return str(sibling)
    return shutil.which("ffprobe")


def probe_video_duration_seconds(source: Path, ffmpeg_path: str | None = None) -> float | None:
    probe = ffprobe_path(ffmpeg_path)
    if not probe:
        return None
    result = subprocess.run(
        [
            probe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(source),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        **_hidden_popen_options(),
    )
    try:
        duration = float(result.stdout.strip())
    except (TypeError, ValueError):
        return None
    return duration if duration > 0 else None


def probe_h3_media(source: Path) -> dict[str, Any]:
    """Inspect uploads with ffprobe only; never decode on the GPU."""
    probe = ffprobe_path()
    if not probe:
        raise HTTPException(status_code=400, detail="H3 控制素材检查需要 ffprobe，请先安装 FFmpeg。")
    try:
        result = subprocess.run(
            [probe, "-v", "error", "-show_entries", "stream=codec_type,width,height,duration:format=duration",
             "-of", "json", str(source)], capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=20, **_hidden_popen_options(),
        )
        data = json.loads(result.stdout)
        streams = data.get("streams", [])
        video = next(stream for stream in streams if stream.get("codec_type") == "video")
        duration = video.get("duration")
        if duration in (None, "", "N/A"):
            duration = data.get("format", {}).get("duration") or 0
        return {"width": int(video["width"]), "height": int(video["height"]),
                "duration": float(duration) if duration != "N/A" else 0,
                "audio": any(stream.get("codec_type") == "audio" for stream in streams)}
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, StopIteration) as exc:
        raise HTTPException(status_code=400, detail=f"无法读取 H3 素材：{source.name}；请换用可播放的 MP4 / PNG。") from exc


async def prepare_h3_uploads(mode: str, adv: AdvancedParams, length: int, paths: dict,
                             control: UploadFile | None, source: UploadFile | None,
                             mask: UploadFile | None) -> dict[str, Any]:
    if mode not in h3_workflows.H3_MODES:
        return {}
    task = adv["h3_task"]
    names: dict[str, Any] = {}
    metadata = {}
    selected = {"control": control} if task == "control" else ({"source": source, "mask": mask} if task == "inpaint" else {})
    for key, upload in selected.items():
        if not upload or not upload.filename:
            raise HTTPException(status_code=400, detail="缺少 H3 控制 / 重绘素材，请重新选择文件。")
        allowed = VIDEO_EXTENSIONS | IMAGE_EXTENSIONS if key == "mask" else VIDEO_EXTENSIONS
        name = await save_upload(upload, allowed, paths)
        media_path = input_media_path(name, paths)
        info = await asyncio.to_thread(probe_h3_media, media_path)
        is_video = media_path.suffix.lower() in VIDEO_EXTENSIONS
        if is_video and info["duration"] + 0.01 < length / 24:
            raise HTTPException(status_code=400, detail=f"{upload.filename} 只有 {info['duration']:.2f} 秒，当前 H3 对齐后需要 {length / 24:.2f} 秒；请缩短时长或提供更长素材。")
        names[f"{key}_name"] = name
        metadata[key] = info
        if key == "mask":
            names["mask_is_video"] = is_video
        if key == "source":
            names["source_has_audio"] = info["audio"]
    if task == "inpaint":
        original, matte = metadata["source"], metadata["mask"]
        if (original["width"], original["height"]) != (matte["width"], matte["height"]):
            raise HTTPException(status_code=400, detail="原视频与遮罩必须同宽高，避免遮罩错位。两者会一起缩放到目标尺寸。")
    return names


def format_video_progress_time(seconds: float) -> str:
    value = max(0, int(seconds))
    hours, remainder = divmod(value, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def run_ffmpeg_with_progress(
    command: list[str],
    *,
    progress_callback: Any = None,
    start: int = 30,
    end: int = 95,
    duration_seconds: float | None = None,
    job_id: str | None = None,
) -> tuple[int, str]:
    if not progress_callback:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            **_hidden_popen_options(),
        )
        return result.returncode, result.stderr

    if job_id:
        with JOB_STORE_LOCK:
            if JOBS.get(job_id, {}).get("cancel_requested"):
                return 130, "本地视频处理已由用户中断"

    progress_command = [*command[:-1], "-progress", "pipe:1", "-nostats", command[-1]]
    process = subprocess.Popen(
        progress_command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        **_hidden_popen_options(),
    )
    if job_id:
        with LOCAL_VIDEO_PROCESS_LOCK:
            LOCAL_VIDEO_PROCESSES[job_id] = process
        with JOB_STORE_LOCK:
            cancel_requested = bool(JOBS.get(job_id, {}).get("cancel_requested"))
        if cancel_requested and process.poll() is None:
            process.terminate()
    current = start
    output_tail: list[str] = []
    report_local_progress(progress_callback, current, "ffmpeg 正在处理视频")
    try:
        if process.stdout:
            for line in process.stdout:
                key, separator, raw_value = line.strip().partition("=")
                if separator and key in {"out_time_us", "out_time_ms"} and duration_seconds:
                    try:
                        elapsed = max(0.0, float(raw_value) / 1_000_000.0)
                    except ValueError:
                        elapsed = 0.0
                    ratio = min(1.0, elapsed / duration_seconds)
                    next_value = min(end, max(start, round(start + (end - start) * ratio)))
                    if next_value != current:
                        current = next_value
                        report_local_progress(
                            progress_callback,
                            current,
                            f"已处理 {format_video_progress_time(elapsed)} / {format_video_progress_time(duration_seconds)}",
                        )
                elif not line.startswith(("frame=", "fps=", "stream_", "bitrate=", "total_size=", "out_time", "dup_frames=", "drop_frames=", "speed=", "progress=")):
                    output_tail.append(line)
                    del output_tail[:-200]
        return_code = process.wait()
    finally:
        if job_id:
            with LOCAL_VIDEO_PROCESS_LOCK:
                if LOCAL_VIDEO_PROCESSES.get(job_id) is process:
                    LOCAL_VIDEO_PROCESSES.pop(job_id, None)
    if return_code == 0:
        report_local_progress(progress_callback, end, "正在整理输出文件")
    return return_code, "".join(output_tail)


def run_deflicker(
    source: Path,
    paths: dict[str, Any] | None = None,
    *,
    progress_callback: Any = None,
    job_id: str | None = None,
) -> dict[str, Any]:
    if source.suffix.lower() not in VIDEO_EXTENSIONS:
        raise HTTPException(status_code=400, detail="闪烁修复只支持视频文件")

    paths = paths or configured_comfy_paths()
    output_dir = platform_output_dir(paths)
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"Deflicker_{time.strftime('%Y-%m-%d_%H%M%S')}_{uuid.uuid4().hex[:6]}.mp4"

    filter_chain = "deflicker=s=8:m=pm,hqdn3d=1.2:1.2:4:4,format=yuv420p"
    command = [
        find_ffmpeg(),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(source),
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-vf",
        filter_chain,
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        str(output),
    ]

    report_local_progress(progress_callback, 10, "已校验源视频，准备去闪烁")
    duration = probe_video_duration_seconds(source, command[0])
    return_code, stderr = run_ffmpeg_with_progress(
        command,
        progress_callback=progress_callback,
        start=20,
        end=95,
        duration_seconds=duration,
        job_id=job_id,
    )
    if return_code != 0:
        if output.exists():
            output.unlink()
        detail = stderr.strip()[-2000:] or "ffmpeg 闪烁修复失败"
        raise HTTPException(status_code=500, detail=detail)

    report_local_progress(progress_callback, 100, "闪烁修复完成")
    return output_media_item(output, paths)


def run_video_tune(
    source: Path,
    *,
    flicker_preset: str = "balanced",
    brightness: float = 0.0,
    contrast: float = 1.0,
    saturation: float = 1.0,
    sharpness: float = 0.0,
    paths: dict[str, Any] | None = None,
    progress_callback: Any = None,
    job_id: str | None = None,
) -> dict[str, Any]:
    if source.suffix.lower() not in VIDEO_EXTENSIONS:
        raise HTTPException(status_code=400, detail="视频微调只支持视频文件")

    paths = paths or configured_comfy_paths()
    output_dir = platform_output_dir(paths)
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"VideoTune_{time.strftime('%Y-%m-%d_%H%M%S')}_{uuid.uuid4().hex[:6]}.mp4"
    flicker_filters = {
        "off": [],
        "light": ["deflicker=s=5:m=pm", "hqdn3d=0.6:0.6:2:2"],
        "balanced": ["deflicker=s=8:m=pm", "hqdn3d=1.2:1.2:4:4"],
        "strong": ["deflicker=s=12:m=pm", "hqdn3d=1.8:1.8:6:6"],
    }
    preset = flicker_preset if flicker_preset in flicker_filters else "balanced"
    brightness = clamp_float(brightness, -0.2, 0.2)
    contrast = clamp_float(contrast, 0.5, 1.5)
    saturation = clamp_float(saturation, 0.0, 2.0)
    sharpness = clamp_float(sharpness, 0.0, 1.5)
    filters = [*flicker_filters[preset]]
    if brightness or contrast != 1.0 or saturation != 1.0:
        filters.append(f"eq=brightness={brightness:.4f}:contrast={contrast:.4f}:saturation={saturation:.4f}")
    if sharpness:
        filters.append(f"unsharp=5:5:{sharpness:.4f}:5:5:0")
    filters.append("format=yuv420p")

    command = [
        find_ffmpeg(),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(source),
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-vf",
        ",".join(filters),
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        str(output),
    ]
    report_local_progress(progress_callback, 8, "已校验源视频和微调参数")
    duration = probe_video_duration_seconds(source, command[0])
    return_code, stderr = run_ffmpeg_with_progress(
        command,
        progress_callback=progress_callback,
        start=15,
        end=96,
        duration_seconds=duration,
        job_id=job_id,
    )
    if return_code != 0:
        output.unlink(missing_ok=True)
        detail = stderr.strip()[-2000:] or "ffmpeg 视频微调失败"
        raise HTTPException(status_code=500, detail=detail)
    report_local_progress(progress_callback, 100, "视频微调完成")
    return output_media_item(output, paths)


def video_has_audio(source: Path, ffmpeg_path: str | None = None) -> bool:
    result = subprocess.run(
        [ffmpeg_path or find_ffmpeg(), "-hide_banner", "-i", str(source)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        **_hidden_popen_options(),
    )
    return bool(re.search(r"Stream #\d+:\d+(?:\[[^]]+\])?.*?: Audio:", result.stderr))


def run_stitch(
    sources: list[Path],
    *,
    width: int,
    height: int,
    fps: int,
    paths: dict[str, Any] | None = None,
    progress_callback: Any = None,
    job_id: str | None = None,
    project: str = "",
) -> dict[str, Any]:
    if len(sources) < 2:
        raise HTTPException(status_code=400, detail="多镜头拼接至少需要 2 个视频片段")
    if len(sources) > 24:
        raise HTTPException(status_code=400, detail="单次最多拼接 24 个视频片段")
    for source in sources:
        if source.suffix.lower() not in VIDEO_EXTENSIONS or not source.is_file():
            raise HTTPException(status_code=400, detail=f"无效的视频片段：{source.name}")

    paths = paths or configured_comfy_paths()
    output_dir = platform_output_dir(paths)
    project = sanitize_project_tag(project)
    if project:
        output_dir = output_dir / project
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"Stitched_{time.strftime('%Y-%m-%d_%H%M%S')}_{uuid.uuid4().hex[:6]}.mp4"
    width = normalize_dimension(width)
    height = normalize_dimension(height)
    fps = clamp_int(fps, 1, 60)

    report_local_progress(progress_callback, 5, "已校验视频片段")
    ffmpeg_path = find_ffmpeg()
    audio_checks: list[bool] = []
    durations: list[float] = []
    for index, source in enumerate(sources):
        audio_checks.append(video_has_audio(source, ffmpeg_path))
        duration = probe_video_duration_seconds(source, ffmpeg_path)
        if duration:
            durations.append(duration)
        report_local_progress(
            progress_callback,
            5 + round((index + 1) / len(sources) * 20),
            f"正在分析第 {index + 1}/{len(sources)} 个片段",
        )
    preserve_audio = all(audio_checks)
    command = [ffmpeg_path, "-y", "-hide_banner", "-loglevel", "error"]
    for source in sources:
        command.extend(["-i", str(source)])

    filters = [
        (
            f"[{index}:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,"
            f"fps={fps},setsar=1,format=yuv420p,setpts=PTS-STARTPTS[v{index}]"
        )
        for index in range(len(sources))
    ]
    if preserve_audio:
        filters.extend(
            f"[{index}:a]aresample=48000:async=1:first_pts=0,"
            f"aformat=sample_fmts=fltp:channel_layouts=stereo,asetpts=PTS-STARTPTS[a{index}]"
            for index in range(len(sources))
        )
        concat_inputs = "".join(f"[v{index}][a{index}]" for index in range(len(sources)))
        filters.append(f"{concat_inputs}concat=n={len(sources)}:v=1:a=1[outv][outa]")
    else:
        concat_inputs = "".join(f"[v{index}]" for index in range(len(sources)))
        filters.append(f"{concat_inputs}concat=n={len(sources)}:v=1:a=0[outv]")

    command.extend(["-filter_complex", ";".join(filters), "-map", "[outv]"])
    if preserve_audio:
        command.extend(["-map", "[outa]", "-c:a", "aac", "-b:a", "192k"])
    command.extend(
        [
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-movflags",
            "+faststart",
            str(output),
        ]
    )

    return_code, stderr = run_ffmpeg_with_progress(
        command,
        progress_callback=progress_callback,
        start=30,
        end=95,
        duration_seconds=sum(durations) if len(durations) == len(sources) else None,
        job_id=job_id,
    )
    if return_code != 0:
        output.unlink(missing_ok=True)
        detail = stderr.strip()[-3000:] or "ffmpeg 多镜头拼接失败"
        raise HTTPException(status_code=500, detail=detail)
    report_local_progress(progress_callback, 100, "多镜头拼接完成")
    return output_media_item(output, paths)


def run_local_video_worker(job_id: str, operation: str, kwargs: dict[str, Any]) -> None:
    with JOB_STORE_LOCK:
        job = JOBS[job_id]
        if job.get("cancel_requested"):
            job.update(
                {
                    "status": "canceled",
                    "completed": True,
                    "finished_at": now_ms(),
                    "status_note": "本地处理已中断",
                    "error": "本地视频处理已由用户中断",
                }
            )
            job.pop("cancel_requested", None)
            persist_job_stores(force=True)
            return
        job.update(
            {
                "status": "running",
                "completed": False,
                "started_at": now_ms(),
                "progress": {
                    "percent": 1.0,
                    "label": "本地处理已启动",
                    "source": "local_worker",
                    "accurate": False,
                },
                "status_note": "本地处理已启动",
            }
        )
    persist_job_stores(force=True)

    def progress(value: int, note: str) -> None:
        with JOB_STORE_LOCK:
            job["progress"] = {
                "percent": float(value),
                "label": note,
                "source": "ffmpeg_timestamp",
                "accurate": True,
            }
            job["status_note"] = note
            job["last_progress_at"] = now_ms()
        persist_job_stores()

    try:
        if operation == "deflicker":
            media = run_deflicker(progress_callback=progress, job_id=job_id, **kwargs)
        elif operation == "tune":
            media = run_video_tune(progress_callback=progress, job_id=job_id, **kwargs)
        elif operation == "stitch":
            media = run_stitch(progress_callback=progress, job_id=job_id, **kwargs)
        else:
            raise RuntimeError(f"未知本地处理操作：{operation}")
        with JOB_STORE_LOCK:
            if job.get("cancel_requested"):
                raise RuntimeError("本地视频处理已由用户中断")
            job.update(
                {
                    "status": "success",
                    "completed": True,
                    "finished_at": now_ms(),
                    "progress": {
                        "percent": 100.0,
                        "label": "本地处理完成",
                        "source": "ffmpeg_timestamp",
                        "accurate": True,
                    },
                    "status_note": "本地处理完成",
                    "media": [media],
                }
            )
    except Exception as exc:
        detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
        if isinstance(detail, (dict, list)):
            detail = json.dumps(detail, ensure_ascii=False)
        with JOB_STORE_LOCK:
            canceled = bool(job.get("cancel_requested"))
            job.update(
                {
                    "status": "canceled" if canceled else "failed",
                    "completed": True,
                    "finished_at": now_ms(),
                    "error": "本地视频处理已由用户中断" if canceled else str(detail or "本地视频处理失败"),
                    "status_note": "本地处理已中断" if canceled else "本地处理失败",
                }
            )
            job.pop("cancel_requested", None)
    finally:
        persist_job_stores(force=True)


def queue_local_video_job(
    job: dict[str, Any],
    *,
    operation: str,
    kwargs: dict[str, Any],
) -> dict[str, Any]:
    store_generation_job(job)
    threading.Thread(
        target=run_local_video_worker,
        args=(str(job["id"]), operation, kwargs),
        daemon=True,
    ).start()
    return job


@app.get("/")
async def index() -> Response:
    # Fingerprint content too: static-only updates must invalidate immutable caches.
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")

    def versioned_asset(match: re.Match[str]) -> str:
        asset = STATIC_DIR / match.group(1).removeprefix("/static/")
        try:
            digest = hashlib.sha256(asset.read_bytes()).hexdigest()[:12]
        except OSError:
            digest = "missing"
        return f"{match.group(1)}?v={APP_VERSION}-{digest}"

    html = re.sub(r'(/static/[^"?]+)\?(?:v|build)=[^"]*', versioned_asset, html)
    return Response(
        content=html,
        media_type="text/html; charset=utf-8",
        headers={
            "Cache-Control": "no-store, max-age=0",
            "Pragma": "no-cache",
        },
    )


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> Response:
    return Response(status_code=204)


def health_payload(request: Request | None = None) -> dict[str, Any]:
    return {
        "ok": True,
        "app_version": APP_VERSION,
        "workspace_dir": str(WORKSPACE_DIR),
        "base_dir": str(BASE_DIR),
        "service": service_config_payload(request),
        "comfy_url": current_comfy_url(),
        "comfy_url_configured": COMFY_URL_CONFIGURED,
        "comfy_candidate_urls": common_comfy_urls(),
        "process_id": os.getpid(),
        "started_at": STARTED_AT,
        "uptime_seconds": round(time.time() - STARTED_AT, 1),
    }


@app.get("/api/health")
async def health(request: Request) -> dict[str, Any]:
    return health_payload(request)


@app.get("/api/client-config")
async def client_config(request: Request) -> dict[str, Any]:
    return {
        "ok": True,
        "service": service_config_payload(request, include_sensitive=is_loopback_request(request)),
    }


@app.post("/api/service-config")
async def save_service_config(request: Request, payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    data = payload.get("service") if isinstance(payload.get("service"), dict) else payload
    mode = normalize_service_mode(str(data.get("mode") or ""))
    if not mode:
        raise HTTPException(status_code=400, detail="请选择服务端、客户端或双模式。")
    try:
        server_url = normalize_server_url(str(data.get("server_url") or ""))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    access_token = str(data.get("access_token") or "").strip()
    previous_mode = service_config_payload(request, include_sensitive=is_loopback_request(request))
    with CONFIG_LOCK:
        config = read_local_config()
        if mode == "client" and not server_url:
            raise HTTPException(status_code=400, detail="客户端模式需要填写服务端地址。")
        if mode in {"server", "both"} and not access_token:
            access_token = str(config.get("access_token") or "") or uuid.uuid4().hex

        config["node_mode"] = mode
        config["bind_host"] = "0.0.0.0" if mode in {"server", "both"} else "127.0.0.1"
        if server_url:
            config["server_url"] = server_url
        else:
            config.pop("server_url", None)
        if access_token:
            config["access_token"] = access_token
        else:
            config.pop("access_token", None)
        write_local_config(config)

    current = service_config_payload(request, include_sensitive=is_loopback_request(request))
    restart_required = previous_mode.get("mode") != current.get("mode") or previous_mode.get("bind_host") != current.get("bind_host")
    return {
        "ok": True,
        "service": current,
        "restart_required": restart_required,
        "message": "服务模式已保存。" + (" 重启 start.bat 后监听地址会生效。" if restart_required else ""),
    }


@app.get("/api/status")
async def status() -> dict[str, Any]:
    system_result, queue_result = await asyncio.gather(
        comfy_get("/system_stats"), comfy_get("/queue"), return_exceptions=True
    )
    if isinstance(system_result, Exception):
        return {
            "connected": False,
            "comfy_url": current_comfy_url(),
            "comfy_url_configured": COMFY_URL_CONFIGURED,
            "comfy_candidate_urls": common_comfy_urls(),
            "error": comfy_connection_error_text(system_result),
            "queue_running": None,
            "queue_pending": None,
        }
    system_stats = system_result if isinstance(system_result, dict) else {}
    queue = queue_result if isinstance(queue_result, dict) else {}
    device = (system_stats.get("devices") or [{}])[0]
    return {
        "connected": True,
        "comfy_url": current_comfy_url(),
        "comfy_url_configured": COMFY_URL_CONFIGURED,
        "comfy_candidate_urls": common_comfy_urls(),
        "comfyui_version": system_stats.get("system", {}).get("comfyui_version"),
        "pytorch_version": system_stats.get("system", {}).get("pytorch_version"),
        "device_name": device.get("name"),
        "vram_total_gb": round((device.get("vram_total") or 0) / 1024**3, 1),
        "vram_free_gb": round((device.get("vram_free") or 0) / 1024**3, 1),
        "queue_running": len(queue.get("queue_running") or []),
        "queue_pending": len(queue.get("queue_pending") or []),
        "queue_error": comfy_connection_error_text(queue_result) if isinstance(queue_result, Exception) else "",
    }


async def build_environment_payload(*, refresh: bool = False) -> dict[str, Any]:
    os_info = {
        "name": platform.system(),
        "release": os_release_label(),
        "version": platform.version(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python": sys.version.split()[0],
        "python_executable": sys.executable,
    }

    system_stats: dict[str, Any] | None = None
    object_info: dict[str, Any] | None = None
    comfy_error = ""
    queue_error = ""
    queue_info: dict[str, Any] = {"running": None, "pending": None}

    system_result, object_result, queue_result = await asyncio.gather(
        comfy_get("/system_stats"),
        get_comfy_object_info(force=refresh),
        comfy_get("/queue"),
        return_exceptions=True,
    )
    if isinstance(system_result, Exception):
        comfy_error = comfy_connection_error_text(system_result)
    elif isinstance(system_result, dict):
        system_stats = system_result

    if isinstance(object_result, Exception):
        if not comfy_error:
            comfy_error = comfy_connection_error_text(object_result)
    elif isinstance(object_result, dict):
        object_info = object_result

    if isinstance(queue_result, dict):
        queue = queue_result
        queue_info = {
            "running": len(queue.get("queue_running") or []),
            "pending": len(queue.get("queue_pending") or []),
        }
    elif isinstance(queue_result, Exception):
        queue_error = comfy_connection_error_text(queue_result)

    comfy_paths = comfy_paths_from_system_stats(system_stats)
    active_base_dir = Path(comfy_paths["base_dir"])
    assets, custom_nodes, tool_checks, hardware = await asyncio.gather(
        asyncio.to_thread(collect_asset_checks, active_base_dir),
        asyncio.to_thread(collect_custom_node_checks, active_base_dir),
        asyncio.to_thread(ffmpeg_tool_checks),
        asyncio.to_thread(build_hardware_summary, system_stats, force_probe=refresh),
    )
    node_checks = collect_node_checks(object_info)
    registry_checks = collect_model_registry_checks(object_info)

    selected_catalog_id = saved_model_catalog_id() or catalog_model_for_hardware(hardware)
    model_sync = catalog_model_sync(
        base_dir=active_base_dir,
        assets=assets,
        selected_model_id=selected_catalog_id,
    )
    hardware_install_profile = install_profile_for_hardware(hardware)
    install_profile = install_profile_for_selected_model(hardware_install_profile, selected_catalog_id)
    install_assets = filter_assets_for_install_profile(assets, install_profile)
    install_custom_nodes = filter_custom_nodes_for_install_profile(custom_nodes, install_profile)
    install_registry_checks = filter_registry_for_install_profile(registry_checks, install_profile)
    diagnostics = build_load_diagnostics(
        paths=comfy_paths,
        assets=install_assets,
        custom_nodes=install_custom_nodes,
        node_checks=node_checks,
        registry_checks=install_registry_checks,
        object_info=object_info,
    )
    diagnostics = list(model_sync.get("diagnostics") or []) + diagnostics
    comfy_system = (system_stats or {}).get("system", {})
    current_comfy_version = str(comfy_system.get("comfyui_version") or "")
    required_comfy_version = str(
        INSTALL_PROFILE_INFO.get(install_profile, {}).get("required_comfy_version") or ""
    )
    comfy_upgrade_required = bool(
        system_stats is not None
        and required_comfy_version
        and not version_at_least(current_comfy_version, required_comfy_version)
    )
    if comfy_upgrade_required:
        diagnostics.insert(
            0,
            {
                "level": "blocked",
                "title": "ComfyUI 版本不满足当前模型",
                "message": (
                    f"当前为 {current_comfy_version or '未知版本'}，{install_profile} 至少需要 "
                    f"ComfyUI {required_comfy_version}。请先在环境页更新 ComfyUI，再重启并刷新检测。"
                ),
            },
        )
    mac_info = hardware.get("mac") or {}
    if mac_info.get("is_macos") and mac_info.get("apple_silicon"):
        if not (hardware.get("torch") or {}).get("available"):
            diagnostics.insert(
                0,
                {
                    "level": "warn",
                    "title": "前端 Python 未安装 torch",
                    "message": "这不代表 ComfyUI 不能使用 MPS。系统会单独检测 ComfyUI venv 的 torch.backends.mps 状态。",
                },
            )
        if not (hardware.get("comfy_torch") or {}).get("exists"):
            diagnostics.insert(
                0,
                {
                    "level": "warn",
                    "title": "ComfyUI Python 尚未确认",
                    "message": "未找到前端配置的 ComfyUI venv；若使用 ComfyUI Desktop，请先启动后刷新，系统会从 /system_stats 和 /object_info 继续预检。",
                },
            )
    comfy_info = {
        "url": current_comfy_url(),
        "url_configured": COMFY_URL_CONFIGURED,
        "candidate_urls": common_comfy_urls(),
        "connected": system_stats is not None,
        "error": comfy_error,
        "queue_error": queue_error,
        "queue": queue_info,
        "comfyui_version": comfy_system.get("comfyui_version"),
        "pytorch_version": comfy_system.get("pytorch_version"),
        "python_version": comfy_system.get("python_version"),
    }
    recommendations = model_recommendations(
        os_info=os_info,
        hardware=hardware,
        assets=assets,
        custom_nodes=custom_nodes,
        tool_checks=tool_checks,
        node_checks=node_checks,
        base_dir=active_base_dir,
        selected_model_id=selected_catalog_id,
    )
    model_options = workflow_model_options(
        os_info=os_info,
        hardware=hardware,
        assets=assets,
        custom_nodes=custom_nodes,
        tool_checks=tool_checks,
        node_checks=node_checks,
        base_dir=active_base_dir,
        selected_model_id=selected_catalog_id,
    )
    missing_installable = installable_missing_items(install_assets, install_custom_nodes)
    repair_needed = any(item.get("level") == "blocked" for item in diagnostics)
    if repair_needed and not missing_installable:
        missing_installable.append(
            {
                "id": "repair_loaded_assets",
                "label": "修复已下载但未加载的节点/模型",
                "item_type": "repair",
                "path": str(active_base_dir),
                "download_host": "",
                "reason": "重新校验文件、安装自定义节点 requirements，并提示重启 ComfyUI。",
            }
        )
    core_steps = {"视频生成", "闪烁修复", "插帧", "清晰度增强"}
    blocked = [
        item
        for item in recommendations
        if item["step"] in core_steps and item["status"] == "blocked"
    ]
    selected_generation_target = catalog_generation_target(catalog_item_by_id(selected_catalog_id))
    cloud_generation_ready = selected_generation_target == "cloud_api" and bool(fal_api_key())

    return {
        "ok": bool(comfy_info["connected"] and not blocked),
        "generation_ready": bool(cloud_generation_ready or (comfy_info["connected"] and not any(item["step"] == "视频生成" for item in blocked))),
        "base_dir": str(active_base_dir),
        "configured_base_dir": str(BASE_DIR),
        "workspace_dir": str(WORKSPACE_DIR),
        "paths": serializable_comfy_paths(comfy_paths),
        "service": service_config_payload(),
        "os": os_info,
        "comfy": comfy_info,
        "fal_h3_max": fal_h3_max_config_payload(),
        "hardware": hardware,
        "install_profile": install_profile,
        "recommended_install_profile": install_profile,
        "hardware_install_profile": hardware_install_profile,
        "install_profiles": install_profile_options(install_profile),
        "download_settings": download_settings_payload(),
        "model_catalog": model_catalog_payload_with_selection(selected_catalog_id, base_dir=active_base_dir),
        "model_sync": model_sync,
        "assets": assets,
        "custom_nodes": custom_nodes,
        "nodes": node_checks,
        "model_registry": registry_checks,
        "diagnostics": diagnostics,
        "tools": tool_checks,
        "recommendations": recommendations,
        "model_options": model_options,
        "missing_installable": missing_installable,
        "install_plan": install_plan_payload(
            profile=install_profile,
            assets=assets,
            custom_nodes=custom_nodes,
            missing=missing_installable,
            base_dir=active_base_dir,
        ),
        "needs_install": bool(missing_installable),
        "repair_needed": repair_needed,
        "comfy_upgrade_required": comfy_upgrade_required,
        "required_comfyui_version": required_comfy_version,
        "blocked": blocked,
        "install_note": (
            "H3 Max 当前不下载本地权重；配置 FAL_KEY 后走 fal 云端 API，不需要启动 ComfyUI。"
            if selected_generation_target == "cloud_api"
            else
            f"当前档位至少需要 ComfyUI {required_comfy_version}；请先更新并重启 ComfyUI。"
            if comfy_upgrade_required
            else f"一键安装将按 {install_profile} 档位下载缺失文件；安装后需要重启 ComfyUI，让模型列表重新加载。"
        ),
        "nsfw_playbook": playbook_payload(read_local_config()),
        "character_box": character_box_payload(read_local_config()),
    }


@app.get("/api/environment")
async def environment(refresh: bool = False) -> dict[str, Any]:
    def cached_payload() -> dict[str, Any] | None:
        with COMFY_STATE_LOCK:
            value = ENVIRONMENT_CACHE.get("value")
            checked_at = float(ENVIRONMENT_CACHE.get("checked_at") or 0)
        if not refresh and isinstance(value, dict) and time.time() - checked_at < ENVIRONMENT_CACHE_TTL:
            return value
        return None

    cached = cached_payload()
    if cached is not None:
        return cached
    async with environment_async_lock():
        cached = cached_payload()
        if cached is not None:
            return cached
        if refresh:
            invalidate_runtime_caches(include_hardware=True)
        payload = await build_environment_payload(refresh=refresh)
        with COMFY_STATE_LOCK:
            ENVIRONMENT_CACHE.update({"value": payload, "checked_at": time.time()})
        return payload


@app.get("/api/diagnostics")
async def diagnostics() -> dict[str, Any]:
    health_data = health_payload()
    status_payload = await status()
    bootstrap_payload = await build_bootstrap_status()
    environment_payload = await environment()
    return {
        "ok": True,
        "diagnostic_version": 1,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "health": health_data,
        "status": status_payload,
        "bootstrap": bootstrap_payload,
        "prerequisites": bootstrap_payload.get("prerequisites"),
        "download_settings": download_settings_payload(),
        "model_catalog": model_catalog_payload_with_selection(),
        "recent_jobs": recent_jobs_payload(),
        "environment": {
            "base_dir": environment_payload.get("base_dir"),
            "configured_base_dir": environment_payload.get("configured_base_dir"),
            "workspace_dir": environment_payload.get("workspace_dir"),
            "paths": environment_payload.get("paths"),
            "os": environment_payload.get("os"),
            "comfy": environment_payload.get("comfy"),
            "fal_h3_max": environment_payload.get("fal_h3_max"),
            "hardware": environment_payload.get("hardware"),
            "generation_ready": environment_payload.get("generation_ready"),
            "install_profile": environment_payload.get("install_profile"),
            "recommended_install_profile": environment_payload.get("recommended_install_profile"),
            "install_profiles": environment_payload.get("install_profiles"),
            "install_plan": environment_payload.get("install_plan"),
            "download_settings": environment_payload.get("download_settings"),
            "model_catalog": environment_payload.get("model_catalog"),
            "model_sync": environment_payload.get("model_sync"),
            "missing_installable": environment_payload.get("missing_installable"),
            "diagnostics": environment_payload.get("diagnostics"),
            "tools": environment_payload.get("tools"),
            "blocked": environment_payload.get("blocked"),
        },
    }


async def build_bootstrap_status(request: Request | None = None) -> dict[str, Any]:
    try:
        system_stats = await comfy_get("/system_stats")
        return bootstrap_status_payload(True, paths=comfy_paths_from_system_stats(system_stats), request=request)
    except HTTPException as exc:
        return bootstrap_status_payload(False, str(exc.detail), request=request)


@app.get("/api/bootstrap")
async def bootstrap_status(request: Request) -> dict[str, Any]:
    return await build_bootstrap_status(request)


@app.get("/api/prerequisites")
async def prerequisites(network: bool = False) -> dict[str, Any]:
    if not BUILD_PREREQUISITE_REPORT:
        raise HTTPException(status_code=503, detail="前置条件检测模块不可用")
    return call_with_download_env(BUILD_PREREQUISITE_REPORT, WORKSPACE_DIR, BASE_DIR, COMFY_INSTALL_DIR, include_network=network)


@app.get("/api/settings")
async def get_settings(request: Request) -> dict[str, Any]:
    return {
        "download": download_settings_payload(include_sensitive=is_loopback_request(request)),
        "model_catalog": model_catalog_payload_with_selection(),
    }


@app.get("/api/storage-locations")
async def storage_locations() -> dict[str, Any]:
    comfy_paths = await active_comfy_paths()
    active_base_dir = Path(comfy_paths["base_dir"])
    return {
        "ok": True,
        "active_base_dir": str(active_base_dir),
        "selected_path": saved_model_download_dir() or str(active_base_dir),
        "locations": model_storage_candidates(active_base_dir),
        "note": "自定义目录会自动写入 ComfyUI extra_model_paths.yaml，重启 ComfyUI 后生效。",
    }


@app.post("/api/settings")
async def save_settings(request: Request, payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    download = payload.get("download") if isinstance(payload.get("download"), dict) else payload
    region = str((download or {}).get("download_region") or "").strip()
    preset_by_id = {str(item.get("id") or ""): item for item in DOWNLOAD_SOURCE_PRESETS}
    if region and region not in preset_by_id:
        raise HTTPException(status_code=400, detail="未知下载源区域")
    try:
        hf_endpoint = normalize_hf_endpoint(str((download or {}).get("hf_endpoint") or ""))
        proxy_url = normalize_proxy_url(str((download or {}).get("proxy_url") or ""))
        pip_index_url = normalize_pip_index_url(str((download or {}).get("pip_index_url") or ""))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    with CONFIG_LOCK:
        config = read_local_config()
        if hf_endpoint:
            config["hf_endpoint"] = hf_endpoint
        else:
            config.pop("hf_endpoint", None)
        if proxy_url:
            config["proxy_url"] = proxy_url
        else:
            config.pop("proxy_url", None)
        if pip_index_url:
            config["pip_index_url"] = pip_index_url
        else:
            config.pop("pip_index_url", None)
        if region:
            config["download_region"] = region
        else:
            config.pop("download_region", None)
        write_local_config(config)
    invalidate_runtime_caches()
    return {
        "ok": True,
        "download": download_settings_payload(include_sensitive=is_loopback_request(request)),
        "model_catalog": model_catalog_payload_with_selection(),
    }


@app.get("/api/model-catalog")
async def model_catalog() -> dict[str, Any]:
    return model_catalog_payload_with_selection()


@app.post("/api/model-catalog/selection")
async def save_model_catalog_selection(payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    selected_id = str(payload.get("selected_model_id") or "").strip()
    selected = catalog_item_by_id(selected_id)
    if not selected:
        raise HTTPException(status_code=400, detail="未知模型目录项")
    with CONFIG_LOCK:
        config = read_local_config()
        config["selected_model_catalog_id"] = selected_id
        write_local_config(config)
    invalidate_runtime_caches()
    return {
        "ok": True,
        "model_catalog": model_catalog_payload_with_selection(),
        "install_profile": selected.get("default_install_profile") or "manual",
        "platform_support": selected.get("platform_support") or "manual",
        "workflow_modes": selected.get("workflow_modes") or {},
    }


# ---- 在线搜索新模型（Hugging Face / Civitai）并入库 ----
MODEL_WEIGHT_SUFFIXES = (".safetensors", ".gguf", ".ckpt", ".pt", ".pth", ".bin")


async def external_api_get(url: str, params: dict[str, Any] | None = None) -> Any:
    proxy = effective_proxy_url() or None
    try:
        async with httpx.AsyncClient(
            proxy=proxy,
            timeout=15.0,
            follow_redirects=True,
            headers={"User-Agent": "local-ai-workbench/1.0"},
        ) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status in {401, 403}:
            raise HTTPException(status_code=502, detail="该模型需要登录授权（gated），请在网页上申请权限后手动下载。") from exc
        if status == 451:
            raise HTTPException(
                status_code=502,
                detail="该在线源对当前网络地区不可用（HTTP 451）。请在「配置下载/数据源」里设置可用代理后重试。",
            ) from exc
        raise HTTPException(status_code=502, detail=f"在线源返回 HTTP {status}，稍后重试或换关键词。") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail="连接在线模型源失败。国内网络请在「配置下载/数据源」里设置 HF 镜像或代理后重试。",
        ) from exc


def hf_api_base() -> str:
    endpoint = effective_hf_endpoint() or "https://huggingface.co"
    return endpoint.rstrip("/")


def weight_files_only(names_and_sizes: list[tuple[str, int]]) -> list[dict[str, Any]]:
    files = [
        {"name": Path(name).name, "rel": name, "size_bytes": int(size or 0)}
        for name, size in names_and_sizes
        if name.lower().endswith(MODEL_WEIGHT_SUFFIXES)
    ]
    files.sort(key=lambda item: item["size_bytes"], reverse=True)
    return files[:24]


@app.get("/api/model-search")
async def model_search(source: str = "hf", q: str = "", limit: int = 12) -> dict[str, Any]:
    query = str(q or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="请输入搜索关键词")
    limit = clamp_int(limit, 1, 30)
    results: list[dict[str, Any]] = []
    if source == "civitai":
        data = await external_api_get(
            "https://civitai.com/api/v1/models",
            params={"query": query, "limit": limit, "nsfw": "false"},
        )
        for item in data.get("items") or []:
            versions = item.get("modelVersions") or []
            version = versions[0] if versions else {}
            files = weight_files_only(
                [
                    (str(f.get("name") or ""), int(float(f.get("sizeKB") or 0) * 1024))
                    for f in (version.get("files") or [])
                ]
            )
            for f, raw in zip(files, [x for x in (version.get("files") or []) if str(x.get("name") or "").lower().endswith(MODEL_WEIGHT_SUFFIXES)]):
                f["url"] = str(raw.get("downloadUrl") or "")
            results.append(
                {
                    "source": "civitai",
                    "id": str(item.get("id") or ""),
                    "name": str(item.get("name") or ""),
                    "author": str(((item.get("creator") or {}).get("username")) or ""),
                    "type": str(item.get("type") or ""),
                    "downloads": int((item.get("stats") or {}).get("downloadCount") or 0),
                    "likes": int((item.get("stats") or {}).get("thumbsUpCount") or 0),
                    "updated": str(version.get("updatedAt") or version.get("createdAt") or "")[:10],
                    "version": str(version.get("name") or ""),
                    "page_url": f"https://civitai.com/models/{item.get('id')}",
                    "files": files,
                }
            )
    elif source == "hf":
        data = await external_api_get(
            f"{hf_api_base()}/api/models",
            params={"search": query, "limit": limit, "sort": "downloads", "direction": "-1"},
        )
        for item in data if isinstance(data, list) else []:
            repo_id = str(item.get("id") or item.get("modelId") or "")
            results.append(
                {
                    "source": "hf",
                    "id": repo_id,
                    "name": repo_id,
                    "author": repo_id.split("/")[0] if "/" in repo_id else "",
                    "type": str(item.get("pipeline_tag") or ""),
                    "downloads": int(item.get("downloads") or 0),
                    "likes": int(item.get("likes") or 0),
                    "updated": str(item.get("lastModified") or "")[:10],
                    "gated": bool(item.get("gated")),
                    "page_url": f"https://huggingface.co/{repo_id}",
                    "files": [],
                }
            )
    else:
        raise HTTPException(status_code=400, detail="未知在线模型源")
    return {"ok": True, "source": source, "query": query, "results": results}


@app.get("/api/model-search/files")
async def model_search_files(source: str = "hf", id: str = "") -> dict[str, Any]:
    repo_id = str(id or "").strip()
    if source != "hf" or not repo_id or ".." in repo_id:
        raise HTTPException(status_code=400, detail="只支持查询 Hugging Face 仓库文件")
    data = await external_api_get(f"{hf_api_base()}/api/models/{repo_id}", params={"blobs": "true"})
    siblings = data.get("siblings") or []
    files = weight_files_only([(str(s.get("rfilename") or ""), int(s.get("size") or 0)) for s in siblings])
    for f in files:
        f["url"] = f"https://huggingface.co/{repo_id}/resolve/main/{quote(f['rel'])}"
    return {"ok": True, "id": repo_id, "gated": bool(data.get("gated")), "files": files}


def sanitize_user_model_entry(payload: dict[str, Any]) -> dict[str, Any]:
    source = str(payload.get("source") or "").strip()
    if source not in {"hf", "civitai"}:
        raise HTTPException(status_code=400, detail="未知在线模型源")
    label = clean_label(str(payload.get("label") or "")) or "未命名导入模型"
    target_subdir = str(payload.get("target_subdir") or "").strip()
    if target_subdir not in USER_MODEL_TARGET_SUBDIRS:
        raise HTTPException(status_code=400, detail="目标目录不在允许列表内")
    raw_files = payload.get("files")
    if not isinstance(raw_files, list) or not raw_files:
        raise HTTPException(status_code=400, detail="请至少选择一个模型文件")
    download_files: list[dict[str, Any]] = []
    for raw in raw_files[:12]:
        if not isinstance(raw, dict):
            continue
        # 保留原始文件名（仅清洗非法字符），模型文件名需与来源一致才能被工作流引用。
        raw_name = Path(str(raw.get("name") or "")).name
        suffix = Path(raw_name).suffix.lower()
        stem = re.sub(r'[\\/<>:"|?*\x00-\x1f]+', "_", Path(raw_name).stem).strip(". ") or "model"
        name = f"{stem}{suffix}"
        url = str(raw.get("url") or "").strip()
        parsed = urlparse(url)
        if not name or not name.lower().endswith(MODEL_WEIGHT_SUFFIXES):
            raise HTTPException(status_code=400, detail=f"不支持的文件类型：{raw.get('name')}")
        if parsed.scheme != "https" or (parsed.hostname or "") not in MODEL_SEARCH_ALLOWED_HOSTS:
            raise HTTPException(status_code=400, detail=f"下载地址不在允许的站点内：{parsed.hostname or url}")
        download_files.append({"name": name, "url": url, "size_bytes": int(raw.get("size_bytes") or 0)})
    if not download_files:
        raise HTTPException(status_code=400, detail="请至少选择一个模型文件")
    source_model_id = re.sub(r"[^A-Za-z0-9._-]+", "_", str(payload.get("model_id") or "")).strip("_")[:80]
    entry_id = f"user_{source}_{source_model_id or uuid.uuid4().hex[:8]}"
    total_gb = round(sum(int(f["size_bytes"]) for f in download_files) / 1024**3, 2)
    page_url = str(payload.get("page_url") or "").strip()
    page_parsed = urlparse(page_url)
    if page_url and (page_parsed.scheme != "https" or (page_parsed.hostname or "") not in MODEL_SEARCH_ALLOWED_HOSTS):
        page_url = ""
    return {
        "id": entry_id,
        "label": label,
        "family": "用户导入",
        "quantization": clean_label(str(payload.get("quantization") or "")) or "未标注",
        "task": clean_label(str(payload.get("task") or "")) or ("Civitai 模型" if source == "civitai" else "Hugging Face 模型"),
        "vram_hint": f"共 {total_gb} GB · {len(download_files)} 个文件" if total_gb else f"{len(download_files)} 个文件",
        "platform_support": "manual",
        "status": "community",
        "files": [f["name"] for f in download_files],
        "sources": [page_url] if page_url else [],
        "recommended_for": f"来自{'Civitai' if source == 'civitai' else 'Hugging Face'}在线搜索导入；下载到 models/{target_subdir}/ 后在 ComfyUI 工作流中使用。",
        "workflow_support": "用户导入模型：平台不生成专用工作流，请在 ComfyUI 中按模型说明接入。",
        "capability_labels": ["用户导入"],
        "user_import": True,
        "import_source": source,
        "target_subdir": target_subdir,
        "download_files": download_files,
        "released": time.strftime("%Y-%m-%d"),
    }


async def start_user_model_download(entry: dict[str, Any]) -> dict[str, Any]:
    comfy_paths = await active_comfy_paths()
    active_base_dir = Path(str(comfy_paths.get("base_dir") or BASE_DIR))
    download_base = normalize_model_download_dir(saved_model_download_dir(), active_base_dir)
    target_dir = download_base / "models" / str(entry.get("target_subdir") or "checkpoints")
    missing_like: list[dict[str, Any]] = []
    files_spec: list[dict[str, Any]] = []
    for index, item in enumerate(entry.get("download_files") or []):
        dest = target_dir / str(item["name"])
        expected = int(item.get("size_bytes") or 0)
        if dest.is_file() and (not expected or dest.stat().st_size == expected):
            continue
        files_spec.append({"name": item["name"], "url": item["url"], "dest": str(dest), "expected_bytes": expected})
        missing_like.append(
            {
                "id": f"{entry['id']}_{index}",
                "label": item["name"],
                "name": item["name"],
                "item_type": "asset",
                "path": f"models/{entry.get('target_subdir')}/{item['name']}",
                "primary_path": f"models/{entry.get('target_subdir')}/{item['name']}",
                "download_host": urlparse(str(item["url"])).hostname or "",
                "expected_bytes": expected,
            }
        )
    job_id = uuid.uuid4().hex
    job = {
        "id": job_id,
        "kind": "install_workflow_assets",
        "status": "queued",
        "completed": False,
        "created_at": now_ms(),
        "base_dir": str(download_base),
        "active_base_dir": str(active_base_dir),
        "install_profile": "user-import",
        "user_model_id": str(entry.get("id") or ""),
        "title": f"下载导入模型 · {entry.get('label')}",
        "catalog_model_id": str(entry.get("id") or ""),
        "generation_target": "catalog_only",
        "can_generate_here": False,
        "missing": missing_like,
        "download_settings": download_settings_payload(),
        "progress": initialize_install_progress(missing_like),
        "control_action": "",
        "log": [f"导入模型：{entry.get('label')}", f"下载目录：{target_dir}"],
    }
    store_install_job(job, exclusive=True)
    if not files_spec:
        job.update({"status": "success", "completed": True, "finished_at": now_ms(), "skipped": True})
        finish_install_progress(job, success=True)
        job["log"].append("所选文件都已存在，无需下载。")
        return job
    try:
        hosts = {str(item.get("download_host") or "") for item in missing_like if item.get("download_host")}
        run_download_network_preflight(job, hosts)
    except Exception as exc:
        job.update({"status": "failed", "completed": True, "finished_at": now_ms()})
        job["log"].append(f"下载前网络预检失败：{exc}")
        attach_failure_hint(job)
        return job
    spec_dir = WORKSPACE_DIR / ".user_downloads"
    spec_dir.mkdir(parents=True, exist_ok=True)
    spec_path = spec_dir / f"{job_id}.json"
    spec_path.write_text(json.dumps({"files": files_spec}, ensure_ascii=False, indent=2), encoding="utf-8")
    script = WORKSPACE_DIR / "scripts" / "install_workflow_assets.py"
    command = [sys.executable, "-u", str(script), "--direct-download", str(spec_path)]
    job["command"] = install_command_text(command)
    job["command_args"] = command
    thread = threading.Thread(target=run_install_worker, args=(job_id, command, download_subprocess_env()), daemon=True)
    thread.start()
    return job


@app.post("/api/model-search/import")
async def model_search_import(payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    entry = sanitize_user_model_entry(payload or {})
    items = [item for item in read_user_model_catalog() if str(item.get("id")) != entry["id"]]
    items.append(entry)
    write_user_model_catalog(items)
    invalidate_runtime_caches()
    job = None
    if bool((payload or {}).get("download")):
        job = await start_user_model_download(entry)
    return {"ok": True, "entry": entry, "job": job, "model_catalog": model_catalog_payload_with_selection()}


@app.post("/api/model-search/remove")
async def model_search_remove(payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    entry_id = str((payload or {}).get("id") or "").strip()
    items = read_user_model_catalog()
    remaining = [item for item in items if str(item.get("id")) != entry_id]
    if len(remaining) == len(items):
        raise HTTPException(status_code=404, detail="导入模型不存在")
    write_user_model_catalog(remaining)
    if str(read_local_config().get("selected_model_catalog_id") or "") == entry_id:
        with CONFIG_LOCK:
            config = read_local_config()
            config.pop("selected_model_catalog_id", None)
            write_local_config(config)
    invalidate_runtime_caches()
    return {"ok": True, "removed": entry_id, "model_catalog": model_catalog_payload_with_selection()}


@app.post("/api/model-search/download")
async def model_search_download(payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    entry_id = str((payload or {}).get("id") or "").strip()
    entry = user_catalog_item_by_id(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="导入模型不存在")
    job = await start_user_model_download(entry)
    return {"ok": True, "job": job}


@app.post("/api/self-test")
async def start_self_test() -> dict[str, Any]:
    job_id = uuid.uuid4().hex
    job = {
        "id": job_id,
        "kind": "self_test",
        "status": "queued",
        "completed": False,
        "created_at": now_ms(),
        "log": [],
    }
    store_install_job(job)
    thread = threading.Thread(target=run_self_test_worker, args=(job_id,), daemon=True)
    thread.start()
    return job


@app.post("/api/bootstrap/full-setup")
async def full_setup(
    backend: str = "auto",
    profile: str = "auto",
    dry_run: bool = False,
    target_dir: str = "",
) -> dict[str, Any]:
    if backend not in {"auto", "cuda", "cpu", "mps", "skip"}:
        raise HTTPException(status_code=400, detail="未知 PyTorch 后端")
    normalized_profile = normalize_install_profile(profile)
    if normalized_profile != "auto" and not INSTALL_PROFILE_INFO.get(normalized_profile, {}).get("installable", True):
        raise HTTPException(status_code=400, detail="当前模型属于手动接入目录项，没有可执行的一键准备档位")
    if normalized_profile == "auto":
        selected_profile = install_profile_for_selected_model("post-only")
        if not INSTALL_PROFILE_INFO.get(selected_profile, {}).get("installable", True):
            raise HTTPException(status_code=400, detail="当前目标模型需要手动接入，请先查看模型目录中的来源与工作流说明")
    comfy_paths = await active_comfy_paths()
    active_base_dir = Path(comfy_paths["base_dir"])
    resolved_profile = normalized_profile
    if resolved_profile == "auto":
        resolved_profile = install_profile_for_selected_model(
            install_profile_for_hardware(build_hardware_summary(None))
        )
    try:
        model_base_dir = normalize_model_download_dir(target_dir or saved_model_download_dir(), active_base_dir)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    custom_target = os.path.normcase(str(model_base_dir)) != os.path.normcase(str(active_base_dir))
    extra_paths_config = ""
    if custom_target:
        try:
            model_base_dir.mkdir(parents=True, exist_ok=True)
            extra_paths_config = register_comfy_extra_model_path(model_base_dir, comfy_paths)
            extra_paths_deferred = False
        except ValueError as exc:
            if "main.py" not in str(exc):
                raise HTTPException(status_code=400, detail=f"无法注册自定义模型目录：{exc}") from exc
            extra_paths_config = "等待 ComfyUI 安装完成后自动注册"
            extra_paths_deferred = True
        except (OSError, yaml.YAMLError) as exc:
            raise HTTPException(status_code=400, detail=f"无法注册自定义模型目录：{exc}") from exc
        with CONFIG_LOCK:
            config = read_local_config()
            config["model_download_dir"] = str(model_base_dir)
            write_local_config(config)
    plan_assets = filter_assets_for_install_profile(collect_asset_checks(model_base_dir), resolved_profile)
    plan_nodes = filter_custom_nodes_for_install_profile(collect_custom_node_checks(active_base_dir), resolved_profile)
    plan_missing = installable_missing_items(plan_assets, plan_nodes)
    runtime = comfy_runtime_info()
    skip_comfy_install = comfy_paths.get("source") == "running_comfyui" or bool(runtime.get("source_ready"))
    running_main_py = Path(str(comfy_paths.get("main_py") or "")).resolve() if comfy_paths.get("main_py") else None
    local_main_py = Path(str(runtime.get("main_py") or COMFY_INSTALL_DIR / "main.py")).resolve()
    use_local_comfy_python = bool(runtime.get("source_ready")) or not skip_comfy_install or running_main_py == local_main_py
    job_id = uuid.uuid4().hex
    job = {
        "id": job_id,
        "kind": "full_setup",
        "status": "queued",
        "completed": False,
        "created_at": now_ms(),
        "backend": backend,
        "requested_profile": normalized_profile,
        "base_dir": str(active_base_dir),
        "model_base_dir": str(model_base_dir),
        "custom_target": custom_target,
        "extra_model_paths_config": extra_paths_config,
        "extra_model_paths_deferred": bool(custom_target and extra_paths_deferred),
        "paths": serializable_comfy_paths(comfy_paths),
        "dry_run": dry_run,
        "skip_comfy_install": skip_comfy_install,
        "use_local_comfy_python": use_local_comfy_python,
        "runtime_kind": runtime.get("kind"),
        "runtime_label": runtime.get("label"),
        "progress": initialize_install_progress(plan_missing),
        "log": [
            "一键准备会按顺序安装/更新 ComfyUI、安装当前档位模型和节点，然后尝试启动 ComfyUI。",
            "模型文件很大，首次真实运行可能需要较长时间；dry-run 模式不会下载或写入。",
        ],
    }
    store_install_job(job, exclusive=True)
    thread = threading.Thread(
        target=run_full_setup_worker,
        args=(job_id,),
        kwargs={
            "backend": backend,
            "profile": normalized_profile,
            "base_dir": active_base_dir,
            "model_base_dir": model_base_dir,
            "dry_run": dry_run,
            "skip_comfy_install": skip_comfy_install,
            "use_local_comfy_python": use_local_comfy_python,
        },
        daemon=True,
    )
    thread.start()
    return job


@app.post("/api/bootstrap/install-comfyui")
async def install_comfyui(backend: str = "auto") -> dict[str, Any]:
    if backend not in {"auto", "cuda", "cpu", "mps", "skip"}:
        raise HTTPException(status_code=400, detail="未知 PyTorch 后端")
    job_id = uuid.uuid4().hex
    job = {
        "id": job_id,
        "kind": "install_comfyui",
        "status": "queued",
        "completed": False,
        "created_at": now_ms(),
        "log": [],
    }
    store_install_job(job, exclusive=True)
    if COMFYUI_DISK_PLAN:
        disk_plan = COMFYUI_DISK_PLAN(COMFY_INSTALL_DIR, backend)
        job["install_disk"] = disk_plan
        if disk_plan.get("ok") is False:
            job["status"] = "failed"
            job["completed"] = True
            job["finished_at"] = now_ms()
            job["log"].append("ComfyUI 安装磁盘空间不足，已停止安装。")
            job["log"].append(
                f"当前剩余 {disk_plan.get('free_gb')} GB；"
                f"建议至少预留 {disk_plan.get('recommended_free_gb')} GB；"
                f"目标路径：{disk_plan.get('path')}"
            )
            attach_failure_hint(job)
            return job
    script = WORKSPACE_DIR / "scripts" / "install_comfyui.py"
    if not script.exists():
        job["status"] = "failed"
        job["completed"] = True
        job["finished_at"] = now_ms()
        job["log"].append(f"安装脚本不存在：{script}")
        attach_failure_hint(job)
        return job
    try:
        run_download_network_preflight(job, required_download_hosts_for_comfy_install(backend))
    except Exception as exc:
        job["status"] = "failed"
        job["completed"] = True
        job["finished_at"] = now_ms()
        job["log"].append(f"ComfyUI 安装前网络预检失败：{exc}")
        attach_failure_hint(job)
        return job
    command = [
        sys.executable,
        "-u",
        str(script),
        "--base-dir",
        str(BASE_DIR),
        "--install-dir",
        str(COMFY_INSTALL_DIR),
        "--backend",
        backend,
    ]
    job["command"] = install_command_text(command)
    thread = threading.Thread(target=run_install_worker, args=(job_id, command, download_subprocess_env()), daemon=True)
    thread.start()
    return job


@app.post("/api/bootstrap/start-comfyui")
async def start_comfyui() -> dict[str, Any]:
    global COMFY_PROCESS, COMFY_START_JOB_ID
    try:
        await comfy_get("/system_stats")
        job_id = uuid.uuid4().hex
        job = {
            "id": job_id,
            "kind": "start_comfyui",
            "status": "success",
            "completed": True,
            "created_at": now_ms(),
            "finished_at": now_ms(),
            "log": [f"ComfyUI 已在运行：{current_comfy_url()}"],
        }
        store_install_job(job)
        return job
    except HTTPException:
        pass

    runtime = comfy_runtime_info()
    main_py = Path(str(runtime["main_py"]))
    python = Path(str(runtime["python"]))
    if COMFY_PROCESS and COMFY_PROCESS.poll() is None:
        if COMFY_START_JOB_ID:
            existing_job = INSTALL_JOBS.get(COMFY_START_JOB_ID)
            if existing_job and not existing_job.get("completed"):
                return existing_job
        job_id = uuid.uuid4().hex
        job = {
            "id": job_id,
            "kind": "start_comfyui",
            "status": "running",
            "completed": False,
            "created_at": now_ms(),
            "log": ["ComfyUI 启动进程已经在运行，正在等待服务就绪。"],
        }
        store_install_job(job)
        COMFY_START_JOB_ID = job_id
        thread = threading.Thread(target=wait_for_comfyui_ready_worker, args=(job_id,), daemon=True)
        thread.start()
        return job

    job_id = uuid.uuid4().hex
    if not runtime.get("source_ready"):
        desktop_exe = Path(str(runtime.get("desktop_exe") or ""))
        if not runtime.get("desktop_available") or not desktop_exe.exists():
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "ComfyUI 未安装或 Python 未就绪",
                    "errors": [
                        f"未找到可启动 main.py + Python：{main_py} / {python}",
                        "也未找到可启动的 ComfyUI Desktop 应用。",
                    ],
                    "actions": [
                        "点击“安装/更新 ComfyUI”安装源码版 ComfyUI。",
                        "或设置 COMFY_INSTALL_DIR 指向源码版 ComfyUI，设置 COMFY_DESKTOP_EXE 指向 Desktop 应用。",
                    ],
                },
            )
        job = {
            "id": job_id,
            "kind": "start_comfyui_desktop",
            "status": "queued",
            "completed": False,
            "created_at": now_ms(),
            "log": [],
            "runtime_kind": runtime.get("kind"),
        }
        store_install_job(job)
        COMFY_START_JOB_ID = job_id
        launch_comfy_desktop_background(job_id, desktop_exe)
        return job

    command = comfy_start_command()
    job = {
        "id": job_id,
        "kind": "start_comfyui",
        "status": "queued",
        "completed": False,
        "created_at": now_ms(),
        "log": [],
        "command": install_command_text(command),
        "runtime_kind": runtime.get("kind"),
        "runtime_label": runtime.get("label"),
    }
    store_install_job(job)
    COMFY_START_JOB_ID = job_id
    thread = threading.Thread(target=run_comfyui_worker, args=(job_id, command), daemon=True)
    thread.start()
    return job


@app.post("/api/install")
async def install_workflow_assets(
    profile: str = "auto",
    target_dir: str = "",
    asset_id: str = "",
    include_post: bool = True,
    confirm_requirement: bool = False,
    model_id: str = "",
) -> dict[str, Any]:
    comfy_paths = await active_comfy_paths()
    active_base_dir = Path(comfy_paths["base_dir"])
    normalized_profile = normalize_install_profile(profile)
    target_asset_id = str(asset_id or "").strip()
    requested_model_id = str(model_id or "").strip()
    if normalized_profile != "auto" and not INSTALL_PROFILE_INFO.get(normalized_profile, {}).get("installable", True):
        raise HTTPException(status_code=400, detail="当前模型属于手动接入目录项，没有可执行的一键安装档位")
    try:
        system_stats_for_profile = await comfy_get("/system_stats")
    except HTTPException:
        system_stats_for_profile = None
    hardware = build_hardware_summary(system_stats_for_profile)
    if normalized_profile == "auto":
        normalized_profile = install_profile_for_selected_model(install_profile_for_hardware(hardware), requested_model_id or None)
    if not INSTALL_PROFILE_INFO.get(normalized_profile, {}).get("installable", True):
        raise HTTPException(status_code=400, detail="当前目标模型需要手动接入，没有可执行的一键安装档位")
    required_comfy_version = str(INSTALL_PROFILE_INFO.get(normalized_profile, {}).get("required_comfy_version") or "")
    current_comfy_version = str(((system_stats_for_profile or {}).get("system") or {}).get("comfyui_version") or "")
    if required_comfy_version and system_stats_for_profile is not None and not version_at_least(current_comfy_version, required_comfy_version):
        raise HTTPException(
            status_code=400,
            detail=(
                f"当前 ComfyUI 为 {current_comfy_version or '未知版本'}，该模型至少需要 {required_comfy_version}。"
                "请先更新并重启 ComfyUI，再下载模型。"
            ),
        )
    external_requirement = str(INSTALL_PROFILE_INFO.get(normalized_profile, {}).get("external_requirement") or "")
    if external_requirement and not confirm_requirement:
        raise HTTPException(status_code=400, detail=f"{external_requirement} 确认后再下载。")
    if target_asset_id and target_asset_id not in INSTALL_PROFILE_ASSETS.get(normalized_profile, set()):
        raise HTTPException(status_code=400, detail="目标断点文件不属于当前安装档位")
    install_base_dir = install_base_dir_for_profile(normalized_profile, target_dir, active_base_dir)
    custom_target = os.path.normcase(str(install_base_dir)) != os.path.normcase(str(active_base_dir))
    try:
        install_base_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"无法创建模型下载目录：{exc}") from exc
    extra_paths_config = ""
    if custom_target:
        try:
            extra_paths_config = register_comfy_extra_model_path(install_base_dir, comfy_paths)
        except (OSError, ValueError, yaml.YAMLError) as exc:
            raise HTTPException(status_code=400, detail=f"无法注册自定义模型目录：{exc}") from exc
        with CONFIG_LOCK:
            config = read_local_config()
            config["model_download_dir"] = str(install_base_dir)
            write_local_config(config)
    assets = collect_asset_checks(install_base_dir)
    custom_nodes = collect_custom_node_checks(active_base_dir)
    install_assets = filter_assets_for_install_profile(assets, normalized_profile, include_post=include_post)
    install_custom_nodes = filter_custom_nodes_for_install_profile(custom_nodes, normalized_profile, include_post=include_post)
    if target_asset_id:
        install_assets = [item for item in install_assets if str(item.get("id") or "") == target_asset_id]
        install_custom_nodes = []
        if not install_assets:
            raise HTTPException(status_code=404, detail="没有在资源清单中找到要续传的模型文件")
    missing = installable_missing_items(install_assets, install_custom_nodes)
    repair_needed = False
    if not target_asset_id:
        object_info: dict[str, Any] | None = None
        try:
            object_info = await get_comfy_object_info()
        except HTTPException:
            object_info = None
        diagnostics = build_load_diagnostics(
            paths=comfy_paths,
            assets=install_assets,
            custom_nodes=install_custom_nodes,
            node_checks=collect_node_checks(object_info),
            registry_checks=filter_registry_for_install_profile(
                collect_model_registry_checks(object_info),
                normalized_profile,
                include_post=include_post,
            ),
            object_info=object_info,
        )
        repair_needed = any(item.get("level") == "blocked" for item in diagnostics)
    install_plan = install_plan_payload(
        profile=normalized_profile,
        assets=assets,
        custom_nodes=custom_nodes,
        missing=missing,
        base_dir=install_base_dir,
        include_post=include_post,
    )
    disk_plan = install_plan.get("disk") or {}
    catalog_item = catalog_item_by_id(requested_model_id) or catalog_item_by_id(saved_model_catalog_id()) or {}
    generation_target = catalog_generation_target(catalog_item)
    job_id = uuid.uuid4().hex
    job = {
        "id": job_id,
        "kind": "install_workflow_assets",
        "status": "queued",
        "completed": False,
        "created_at": now_ms(),
        "base_dir": str(install_base_dir),
        "active_base_dir": str(active_base_dir),
        "custom_target": custom_target,
        "extra_model_paths_config": extra_paths_config,
        "paths": {**serializable_comfy_paths(comfy_paths), "download_base_dir": str(install_base_dir)},
        "install_profile": normalized_profile,
        "include_post": include_post,
        "catalog_model_id": requested_model_id or str(catalog_item.get("id") or ""),
        "generation_target": generation_target,
        "can_generate_here": generation_target in {"native", "cloud_api"},
        "asset_id": target_asset_id,
        "asset_label": str((install_assets[0] if install_assets else {}).get("label") or "") if target_asset_id else "",
        "missing": missing,
        "install_plan": install_plan,
        "repair_needed": repair_needed,
        "download_settings": download_settings_payload(),
        "progress": initialize_install_progress(missing),
        "control_action": "",
        "log": [],
    }
    store_install_job(job, exclusive=True)

    if not missing and not repair_needed:
        job["status"] = "success"
        job["completed"] = True
        job["finished_at"] = now_ms()
        job["skipped"] = True
        finish_install_progress(job, success=True)
        job["log"].append(f"安装目标目录：{install_base_dir}")
        job["log"].append("所有可一键安装的模型、权重和自定义节点都已存在，无需下载。")
        return job

    if missing and disk_plan.get("ok") is False:
        job["status"] = "failed"
        job["completed"] = True
        job["finished_at"] = now_ms()
        job["log"].append(f"安装目标目录：{install_base_dir}")
        job["log"].append("磁盘空间不足，已停止一键安装。")
        job["log"].append(
            f"当前剩余 {disk_plan.get('free_gb')} GB；"
            f"预计还需下载 {disk_plan.get('required_gb')} GB；"
            f"建议至少预留 {disk_plan.get('recommended_free_gb')} GB。"
        )
        job["log"].append("请清理磁盘空间，或把 COMFY_BASE_DIR 指向空间更大的磁盘后重新启动前端。")
        finish_install_progress(job, success=False)
        attach_failure_hint(job)
        return job

    script = WORKSPACE_DIR / "scripts" / "install_workflow_assets.py"
    if not script.exists():
        job["status"] = "failed"
        job["completed"] = True
        job["finished_at"] = now_ms()
        job["log"].append(f"安装脚本不存在：{script}")
        attach_failure_hint(job)
        return job

    python = comfy_venv_python()
    try:
        if target_asset_id:
            required_hosts = {
                str(item.get("download_host") or "")
                for item in install_assets
                if not item.get("ok") and not item.get("local_available") and item.get("download_host")
            }
        else:
            required_hosts = required_download_hosts_for_workflow_assets(
                profile=normalized_profile,
                base_dir=install_base_dir,
                use_local_comfy_python=python.exists(),
                custom_nodes_base_dir=active_base_dir,
                repair_needed=repair_needed,
                include_post=include_post,
            )
        run_download_network_preflight(job, required_hosts)
    except Exception as exc:
        job["status"] = "failed"
        job["completed"] = True
        job["finished_at"] = now_ms()
        job["log"].append(f"模型/节点安装前网络预检失败：{exc}")
        attach_failure_hint(job)
        return job

    command = [
        sys.executable,
        "-u",
        str(script),
        "--base-dir",
        str(install_base_dir),
        "--profile",
        normalized_profile,
    ]
    if python.exists():
        command.extend(["--comfy-python", str(python)])
    if custom_target:
        command.extend(["--custom-nodes-base-dir", str(active_base_dir)])
    if target_asset_id:
        command.extend(["--asset-id", target_asset_id, "--no-custom-nodes"])
    if not include_post:
        command.append("--skip-post")
    job["command"] = install_command_text(command)
    job["command_args"] = command
    if custom_target:
        job["log"].append(f"模型将下载到自定义目录：{install_base_dir}；自定义节点仍安装到：{active_base_dir}")
        job["log"].append(f"已注册到 ComfyUI：{extra_paths_config}；安装完成后请重启 8188 再生效。")
    elif comfy_paths.get("base_dir_mismatch"):
        job["log"].append(f"检测到 ComfyUI 正在使用 {active_base_dir}，本次安装会写入该目录。")
        job["log"].append(f"前端默认目录是 {BASE_DIR}，如之前下载到默认目录，当前 ComfyUI 不会自动扫描。")
    if repair_needed and not missing:
        job["log"].append("未发现缺失文件，但发现已下载未加载的问题；将重新安装自定义节点依赖并校验文件。")
    if not include_post:
        job["log"].append("本次只安装该模型核心权重和必要节点，不含 RIFE/超分后期包。")
    thread = threading.Thread(target=run_install_worker, args=(job_id, command, download_subprocess_env()), daemon=True)
    thread.start()
    return job


@app.get("/api/install-plan")
async def install_plan(profile: str = "auto", target_dir: str = "") -> dict[str, Any]:
    return await install_profile_plan_payload(profile, target_dir)


@app.get("/api/install/{job_id}")
async def get_install_job(job_id: str) -> dict[str, Any]:
    job = INSTALL_JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="安装任务不存在")
    reconcile_install_progress_from_disk(job)
    persist_job_stores(force=job_is_terminal(job))
    return job


@app.post("/api/install/{job_id}/pause")
async def pause_install_job(job_id: str) -> dict[str, Any]:
    job = INSTALL_JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="安装任务不存在")
    status = str(job.get("status") or "").lower()
    if status == "paused":
        return job
    if job_is_terminal(job):
        raise HTTPException(status_code=409, detail="已结束的安装任务不能暂停")
    if not job.get("command_args"):
        raise HTTPException(status_code=409, detail="当前任务不支持暂停")
    job["control_action"] = "pause"
    job["status"] = "pausing"
    job["completed"] = False
    if isinstance(job.get("progress"), dict):
        job["progress"]["state"] = "pausing"
    append_job_log(job, "正在暂停下载；当前分块写入完成后会保留 .part 文件。")
    if not terminate_install_process(job_id):
        job["status"] = "paused"
        if isinstance(job.get("progress"), dict):
            job["progress"]["state"] = "paused"
    persist_job_stores(force=True)
    return job


@app.post("/api/install/{job_id}/resume")
async def resume_install_job(job_id: str) -> dict[str, Any]:
    job = INSTALL_JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="安装任务不存在")
    status = str(job.get("status") or "").lower()
    if status not in {"paused", "interrupted"}:
        raise HTTPException(status_code=409, detail="只有已暂停或因前端重启中断的下载可以继续")
    command = job.get("command_args")
    if not isinstance(command, list) or not command:
        raise HTTPException(status_code=409, detail="任务缺少可恢复的安装命令，请重新发起安装")
    reconcile_install_progress_from_disk(job)
    with INSTALL_JOB_LOCK:
        running = INSTALL_PROCESSES.get(job_id)
        if running and running.poll() is None:
            raise HTTPException(status_code=409, detail="安装进程仍在运行")
    job.update(
        {
            "status": "queued",
            "completed": False,
            "control_action": "",
            "error": "",
            "return_code": None,
            "resumed_at": now_ms(),
        }
    )
    job.pop("finished_at", None)
    if isinstance(job.get("progress"), dict):
        job["progress"]["state"] = "queued"
        job["progress"]["speed_mb_s"] = None
        job["progress"]["eta_seconds"] = None
    append_job_log(job, "继续下载；安装器会复用完整文件并从现有 .part 继续。")
    thread = threading.Thread(
        target=run_install_worker,
        args=(job_id, [str(part) for part in command], download_subprocess_env()),
        daemon=True,
    )
    thread.start()
    return job


@app.post("/api/install/{job_id}/cancel")
async def cancel_install_job(job_id: str) -> dict[str, Any]:
    job = INSTALL_JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="安装任务不存在")
    if job_is_terminal(job):
        return job
    job["control_action"] = "cancel"
    job["status"] = "canceling"
    if isinstance(job.get("progress"), dict):
        job["progress"]["state"] = "canceling"
    append_job_log(job, "正在取消安装；已下载的 .part 文件会保留。")
    if not terminate_install_process(job_id):
        job.update({"status": "canceled", "completed": True, "finished_at": now_ms()})
        finish_install_progress(job, success=False)
    persist_job_stores(force=True)
    return job


@app.get("/api/validate")
async def validate() -> dict[str, Any]:
    comfy_paths = await active_comfy_paths()
    active_base_dir = Path(comfy_paths["base_dir"])
    try:
        system_stats = await comfy_get("/system_stats")
    except HTTPException:
        system_stats = None
    install_profile = install_profile_for_selected_model(
        install_profile_for_hardware(build_hardware_summary(system_stats))
    )
    object_info = await get_comfy_object_info()

    all_assets = collect_runtime_asset_checks(active_base_dir)
    assets = filter_assets_for_install_profile(all_assets, install_profile)
    custom_nodes = filter_custom_nodes_for_install_profile(collect_custom_node_checks(active_base_dir), install_profile)
    file_checks = [
        {
            "path": item.get("relative_path") or item.get("path"),
            "ok": bool(item.get("ok")),
            "size_gb": item.get("size_gb"),
        }
        for item in assets
    ] + [
        {
            "path": item.get("relative_path") or item.get("path"),
            "ok": bool(item.get("ok")),
            "size_gb": None,
        }
        for item in custom_nodes
    ]

    graph_checks: list[dict[str, Any]] = []
    sample_params = {
        "prompt": DEFAULT_PROMPT,
        "negative": DEFAULT_NEGATIVE,
        "image_name": KEYFRAME_UPLOAD_PLACEHOLDER,
        "width": 1280,
        "height": 704,
        "length": 81,
        "fps": 24,
        "seed": 1,
        "steps": 4,
        "cfg": 1.0,
    }
    graphs: dict[str, dict[str, Any]] = {}
    if install_profile in {"cuda-full", "cuda-a14b"}:
        graphs.update(
            {
                "I2V A14B": build_a14b_i2v_prompt(**sample_params),
                "T2V A14B": build_a14b_t2v_prompt(
                    **{k: v for k, v in sample_params.items() if k != "image_name"}
                ),
            }
        )
    if install_profile == "cuda-full":
        graphs["TI2V 5B"] = build_ti2v_prompt(**{**sample_params, "steps": 20, "cfg": 5.0})
    if install_profile == "cuda-wan5b":
        graphs["TI2V 5B"] = build_ti2v_prompt(
            **{**sample_params, "width": 832, "height": 480, "length": 49, "steps": 20, "cfg": 5.0}
        )
    if install_profile in {"mac-low", "mac-balanced", "mac-wan5b"}:
        graphs.update(
            {
                "Mac LTX I2V": build_ltx_i2v_prompt(
                    **{**sample_params, "width": 512, "height": 320, "length": 25, "steps": 12, "cfg": 3.0}
                ),
                "Mac LTX T2V": build_ltx_t2v_prompt(
                    **{
                        k: v
                        for k, v in {
                            **sample_params,
                            "width": 512,
                            "height": 320,
                            "length": 25,
                            "steps": 12,
                            "cfg": 3.0,
                        }.items()
                        if k != "image_name"
                    }
                ),
            }
        )
    if install_profile == "mac-wan5b":
        graphs["Mac Wan5B TI2V"] = build_ti2v_prompt(**{**sample_params, "width": 832, "height": 480, "length": 49, "steps": 20, "cfg": 5.0})
    if install_profile in {"ltx23-fp8-dev", "ltx23-nvfp4-dev"}:
        ltx23_checkpoint = LTX23_NVFP4_CHECKPOINT if install_profile == "ltx23-nvfp4-dev" else LTX23_DEV_CHECKPOINT
        ltx23_label = "NVFP4" if install_profile == "ltx23-nvfp4-dev" else "FP8"
        graphs[f"LTX 2.3 Dev {ltx23_label} T2V"] = build_ltx23_t2v_prompt(
            **{
                k: v
                for k, v in {**sample_params, "width": 512, "height": 320, "length": 25, "fps": 25, "steps": 11}.items()
                if k != "image_name"
            },
            checkpoint_name=ltx23_checkpoint,
        )
        graphs[f"LTX 2.3 Dev {ltx23_label} I2V"] = build_ltx23_i2v_prompt(
            **{**sample_params, "width": 512, "height": 320, "length": 25, "fps": 25, "steps": 11},
            checkpoint_name=ltx23_checkpoint,
        )
    if install_profile in {"ltx25-distilled-int8", "ltx25-distilled-nvfp4"}:
        ltx25_model = (
            LTX25_DISTILLED_NVFP4_MODEL
            if install_profile == "ltx25-distilled-nvfp4"
            else LTX25_DISTILLED_INT8_MODEL
        )
        ltx25_label = "NVFP4" if install_profile == "ltx25-distilled-nvfp4" else "INT8"
        graphs[f"LTX 2.5 Distilled {ltx25_label} T2V"] = build_ltx25_t2v_prompt(
            prompt=sample_params["prompt"],
            negative=sample_params["negative"],
            width=640,
            height=352,
            length=25,
            fps=24,
            seed=sample_params["seed"],
            steps=11,
            cfg=1.0,
            model_name=ltx25_model,
        )
        graphs[f"LTX 2.5 Distilled {ltx25_label} I2V"] = build_ltx25_i2v_prompt(
            prompt=sample_params["prompt"],
            negative=sample_params["negative"],
            image_name=sample_params["image_name"],
            width=640,
            height=352,
            length=25,
            fps=24,
            seed=sample_params["seed"],
            steps=11,
            cfg=1.0,
            model_name=ltx25_model,
        )
        graphs[f"LTX 2.5 Distilled {ltx25_label} 首尾帧"] = build_ltx25_i2v_prompt(
            prompt=sample_params["prompt"],
            negative=sample_params["negative"],
            image_name=sample_params["image_name"],
            end_image_name=sample_params["image_name"],
            width=640,
            height=352,
            length=25,
            fps=24,
            seed=sample_params["seed"],
            steps=8,
            cfg=1.0,
            model_name=ltx25_model,
        )
    hunyuan15_profiles = {
        "hunyuan15-t2v-480-fp8": (HUNYUAN15_T2V_480_MODEL, False, True),
        "hunyuan15-i2v-480-fp8": (HUNYUAN15_I2V_480_MODEL, True, True),
        "hunyuan15-t2v-720-fp16": (HUNYUAN15_T2V_720_MODEL, False, False),
        "hunyuan15-i2v-720-fp16": (HUNYUAN15_I2V_720_MODEL, True, False),
    }
    if install_profile in hunyuan15_profiles:
        model_name, uses_image, distilled = hunyuan15_profiles[install_profile]
        graphs[f"HunyuanVideo 1.5 / {install_profile}"] = build_hunyuan15_prompt(
            prompt=sample_params["prompt"],
            negative=sample_params["negative"],
            image_name=sample_params["image_name"] if uses_image else "",
            width=832 if distilled else 1280,
            height=480 if distilled else 704,
            length=49,
            fps=24,
            seed=sample_params["seed"],
            steps=8 if distilled else 20,
            cfg=1.0 if distilled else 6.0,
            model_name=model_name,
            distilled=distilled,
        )
    if install_profile == "minimax-h3-fl2va-int8":
        graphs["MiniMax H3 FL2VA INT8 T2V"] = build_minimax_h3_prompt(
            prompt=sample_params["prompt"],
            negative=sample_params["negative"],
            image_name="",
            width=864,
            height=480,
            length=73,
            fps=24,
            seed=sample_params["seed"],
            steps=20,
            cfg=1.0,
        )
        graphs["MiniMax H3 FL2VA INT8 I2V"] = build_minimax_h3_prompt(
            prompt=sample_params["prompt"],
            negative=sample_params["negative"],
            image_name=sample_params["image_name"],
            end_image_name=sample_params["image_name"],
            width=864,
            height=480,
            length=73,
            fps=24,
            seed=sample_params["seed"],
            steps=20,
            cfg=1.0,
        )
    if install_profile in {
        "cuda-full",
        "cuda-wan5b",
        "mac-low",
        "mac-balanced",
        "mac-wan5b",
        "ltx23-fp8-dev",
        "ltx23-fp8-distilled",
        "ltx23-nvfp4-dev",
        "ltx25-distilled-int8",
        "ltx25-distilled-nvfp4",
        "hunyuan15-t2v-480-fp8",
        "hunyuan15-i2v-480-fp8",
        "hunyuan15-t2v-720-fp16",
        "hunyuan15-i2v-720-fp16",
        "minimax-h3-fl2va-int8",
        "post-only",
    }:
        graphs.update(
            {
                "RIFE 2x": build_rife_prompt(video_name="sample.mp4", fps=24, multiplier=2),
                "Upscale 2x": build_video_upscale_prompt(video_name="sample.mp4", fps=24),
            }
        )
    asset_by_id = {str(item.get("id") or ""): item for item in all_assets}
    image_asset_checks = [item for item in all_assets if item.get("id") in set(IMAGE_ASSET_IDS)]
    ready_image_profiles: list[dict[str, Any]] = []
    for image_profile_item in IMAGE_PROFILES:
        required_ids = list(image_profile_item.get("required_asset_ids") or [])
        if (
            image_profile_item.get("generation_supported") is not False
            and required_ids
            and all(asset_by_id.get(item_id, {}).get("ok") for item_id in required_ids)
        ):
            ready_image_profiles.append(image_profile_item)
            graphs[f"文生图 / {image_profile_item['label']}"] = build_image_prompt(
                prompt=DEFAULT_IMAGE_PROMPT,
                negative=DEFAULT_IMAGE_NEGATIVE,
                width=1328,
                height=1328,
                seed=1,
                profile_id=str(image_profile_item["id"]),
                steps=int(image_profile_item["default_steps"]),
                cfg=float(image_profile_item["default_cfg"]),
                sampler=str(image_profile_item["default_sampler"]),
                scheduler=str(image_profile_item["default_scheduler"]),
            )
    graphs = {name: resolve_graph_model_option_names(graph, object_info) for name, graph in graphs.items()}
    required_nodes = sorted({class_type for graph in graphs.values() for class_type in graph_class_types(graph)})
    node_checks = [{"name": name, "ok": name in object_info} for name in required_nodes]
    for name, graph in graphs.items():
        errors = validate_graph(graph)
        errors.extend(graph_model_registry_errors(graph, object_info))
        errors.extend(graph_node_schema_errors(graph, object_info))
        graph_checks.append({"name": name, "ok": not errors, "errors": errors})

    tool_checks = ffmpeg_tool_checks()

    ok = all(item["ok"] for item in node_checks + file_checks + graph_checks) and all(
        item["ok"] for item in tool_checks if item.get("required", True)
    )
    return {
        "ok": ok,
        "paths": serializable_comfy_paths(comfy_paths),
        "nodes": node_checks,
        "files": file_checks,
        "graphs": graph_checks,
        "tools": tool_checks,
        "image_studio": {
            "installed": bool(ready_image_profiles),
            "install_profile": QWEN_IMAGE_INSTALL_PROFILE,
            "asset_count": len(image_asset_checks),
            "missing_count": len([item for item in image_asset_checks if not item.get("ok")]),
            "ready_profiles": [item["id"] for item in ready_image_profiles],
            "validated_graphs": [item["name"] for item in graph_checks if item["name"].startswith("文生图 / ")],
        },
    }


def image_studio_graph_errors(graph: dict[str, Any], object_info: dict[str, Any] | None) -> list[str]:
    errors = validate_graph(graph)
    errors.extend(graph_model_registry_errors(graph, object_info))
    errors.extend(graph_node_schema_errors(graph, object_info))
    if object_info is not None:
        missing_nodes = [name for name in graph_class_types(graph) if name not in object_info]
        if missing_nodes:
            errors.append(f"ComfyUI 缺少节点：{', '.join(missing_nodes)}")
    return list(dict.fromkeys(str(item) for item in errors if item))


def preferred_node_option(options: list[Any], preferred: tuple[str, ...], fallback: Any = "") -> Any:
    if not options:
        return fallback
    normalized = [(item, str(item).replace("\\", "/").lower()) for item in options]
    for expected in preferred:
        expected_norm = expected.replace("\\", "/").lower()
        match = next(
            (
                item
                for item, value in normalized
                if value == expected_norm or value.endswith(f"/{expected_norm}") or Path(value).name == Path(expected_norm).name
            ),
            None,
        )
        if match is not None:
            return match
    return options[0]


def face_swap_weight_option(object_info: dict[str, Any], requested: float) -> Any:
    options = node_input_option_values(object_info, "ReActorSetWeight", "faceswap_weight")
    if not options:
        raise ValueError("ReActorSetWeight 没有返回可用的换脸强度选项")

    def numeric(option: Any) -> float:
        match = re.search(r"\d+(?:\.\d+)?", str(option))
        return float(match.group(0)) if match else 100.0

    target = max(0.0, min(100.0, float(requested)))
    return min(options, key=lambda option: abs(numeric(option) - target))


def face_swap_capability_payload(
    object_info: dict[str, Any] | None,
    active_base_dir: Path,
    connection_error: str = "",
) -> dict[str, Any]:
    required_nodes = ("ReActorSetWeight", "ReActorFaceSwap")
    node_status = {name: bool(object_info and name in object_info) for name in required_nodes}
    swap_models = [
        str(item)
        for item in node_input_option_values(object_info, "ReActorFaceSwap", "swap_model")
        if str(item).strip().lower() not in {"", "none"}
    ]
    detectors = [str(item) for item in node_input_option_values(object_info, "ReActorFaceSwap", "facedetection")]
    restore_models = [str(item) for item in node_input_option_values(object_info, "ReActorFaceSwap", "face_restore_model")]
    weights = [str(item) for item in node_input_option_values(object_info, "ReActorSetWeight", "faceswap_weight")]
    active_assets = collect_asset_checks(active_base_dir)
    active_nodes = collect_custom_node_checks(active_base_dir)
    selected_assets = filter_assets_for_install_profile(active_assets, FACE_SWAP_INSTALL_PROFILE)
    selected_nodes = filter_custom_nodes_for_install_profile(active_nodes, FACE_SWAP_INSTALL_PROFILE)
    missing = installable_missing_items(selected_assets, selected_nodes)
    plan = install_plan_payload(
        profile=FACE_SWAP_INSTALL_PROFILE,
        assets=active_assets,
        custom_nodes=active_nodes,
        missing=missing,
        base_dir=active_base_dir,
    )
    errors: list[str] = []
    if connection_error:
        errors.append(connection_error)
    missing_nodes = [name for name, ready in node_status.items() if not ready]
    if missing_nodes:
        errors.append(f"ComfyUI 尚未加载换脸节点：{', '.join(missing_nodes)}")
    if all(node_status.values()) and not swap_models:
        errors.append("ReActor 已加载，但没有识别到可用换脸模型；请检查 models/insightface 后重启 ComfyUI。")
    if missing and not missing_nodes:
        errors.append("换脸组件文件不完整；请补齐后重启 ComfyUI。")
    ready = object_info is not None and all(node_status.values()) and bool(swap_models) and not missing
    return {
        "supported": True,
        "ready": ready,
        "engine": "ComfyUI-ReActor",
        "install_profile": FACE_SWAP_INSTALL_PROFILE,
        "install_base_dir": str(active_base_dir),
        "install_plan": plan,
        "required_active_base": True,
        "nodes": node_status,
        "swap_models": swap_models,
        "detectors": detectors,
        "restore_models": restore_models,
        "strength_options": weights or ["0%", "12.5%", "25%", "37.5%", "50%", "62.5%", "75%", "87.5%", "100%"],
        "default_strength": "100%",
        "default_restore_model": "none",
        "errors": errors,
        "missing": missing,
        "authorization_required": True,
        "local_only": True,
        "target_preservation": "只替换选中的目标脸；完整目标图直接进入换脸节点，不经过扩散重绘。",
        "identity_source": "身份参考使用本机检测后选中的面部裁切；完整原图仅用于授权与候选确认。",
        "content_filter": "ReActor 自带内容检测，命中时会拒绝处理；平台不绕过该检测。",
        "license_note": "ReActor 为 GPL-3.0；其 InsightFace 预训练权重仅限非商业研究，商用需更换具有相应授权的模型。",
        "source_url": "https://github.com/Gourieff/ComfyUI-ReActor",
    }


def extracted_input_name(item: dict[str, Any]) -> str:
    filename = str(item.get("filename") or "").strip()
    subfolder = str(item.get("subfolder") or "").strip().strip("/\\")
    if not filename:
        raise ValueError("面部提取记录缺少图片文件")
    return f"{subfolder}/{filename}" if subfolder else filename


def build_face_swap_prompt(
    *,
    object_info: dict[str, Any],
    target_image: str,
    target_face_image: str,
    identity_face_image: str,
    target_face_index: int,
    strength: float,
    restore_model: str = "none",
    restore_visibility: float = 0.8,
    filename_prefix: str = "image_studio/FaceSwap",
) -> tuple[dict[str, Any], dict[str, Any]]:
    missing_nodes = [name for name in ("ReActorSetWeight", "ReActorFaceSwap") if name not in object_info]
    if missing_nodes:
        raise ValueError(f"ComfyUI 缺少换脸节点：{', '.join(missing_nodes)}")
    swap_options = node_input_option_values(object_info, "ReActorFaceSwap", "swap_model")
    swap_options = [item for item in swap_options if str(item).strip().lower() not in {"", "none"}]
    if not swap_options:
        raise ValueError("ReActor 没有识别到可用换脸模型")
    swap_model = preferred_node_option(swap_options, ("inswapper_128.onnx", "inswapper_128_fp16.onnx"))
    detector_options = node_input_option_values(object_info, "ReActorFaceSwap", "facedetection")
    detector = preferred_node_option(detector_options, ("retinaface_resnet50", "retinaface_mobile0.25"))
    restore_options = node_input_option_values(object_info, "ReActorFaceSwap", "face_restore_model")
    requested_restore = str(restore_model or "none")
    selected_restore = next((item for item in restore_options if str(item) == requested_restore), None)
    if selected_restore is None:
        selected_restore = preferred_node_option(restore_options, ("none",), "none")
    weight = face_swap_weight_option(object_info, strength)
    console_options = node_input_option_values(object_info, "ReActorFaceSwap", "console_log_level")
    console_level = preferred_node_option(console_options, ("1",), 1)
    swap_inputs: dict[str, Any] = {
        "enabled": True,
        "input_image": ["1", 0],
        "face_model": ["4", 1],
        "swap_model": swap_model,
        "facedetection": detector,
        "face_restore_model": selected_restore,
        "face_restore_visibility": max(0.1, min(1.0, float(restore_visibility))),
        "codeformer_weight": 0.5,
        "detect_gender_input": "no",
        "detect_gender_source": "no",
        "input_faces_index": str(max(0, int(target_face_index))),
        "source_faces_index": "0",
        "console_log_level": console_level,
    }
    nsfw_detection_options = node_input_option_values(object_info, "ReActorFaceSwap", "nsfw_detection")
    if nsfw_detection_options:
        swap_inputs["nsfw_detection"] = preferred_node_option(
            nsfw_detection_options,
            ("false", "False", "disable", "no", "off", False, 0, "0"),
            False,
        )
    input_order_options = node_input_option_values(object_info, "ReActorFaceSwap", "input_faces_order")
    if input_order_options:
        swap_inputs["input_faces_order"] = preferred_node_option(
            input_order_options,
            ("large-small", "large to small"),
        )
    source_order_options = node_input_option_values(object_info, "ReActorFaceSwap", "source_faces_order")
    if source_order_options:
        swap_inputs["source_faces_order"] = preferred_node_option(
            source_order_options,
            ("large-small", "large to small"),
        )
    graph = {
        "1": node("LoadImage", {"image": target_image}),
        "2": node("LoadImage", {"image": target_face_image}),
        "3": node("LoadImage", {"image": identity_face_image}),
        "4": node(
            "ReActorSetWeight",
            {
                "input_image": ["2", 0],
                "source_image": ["3", 0],
                "faceswap_weight": weight,
            },
        ),
        "5": node("ReActorFaceSwap", swap_inputs),
        "6": node("SaveImage", {"images": ["5", 0], "filename_prefix": filename_prefix}),
    }
    return graph, {
        "swap_model": str(swap_model),
        "detector": str(detector),
        "restore_model": str(selected_restore),
        "strength": str(weight),
        "target_face_index": max(0, int(target_face_index)),
    }


def image_studio_job_records() -> list[dict[str, Any]]:
    with JOB_STORE_LOCK:
        jobs = [
            dict(item)
            for item in JOBS.values()
            if item.get("kind") == "image_generation" or str(item.get("mode") or "").startswith("image_t2i")
        ]
    jobs.sort(key=lambda item: int(item.get("created_at") or 0), reverse=True)
    return jobs


def image_studio_job_history(limit: int = 20) -> list[dict[str, Any]]:
    return image_studio_job_records()[: max(1, min(MAX_COMPLETED_JOBS, int(limit)))]


def image_studio_history_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for job in image_studio_job_records():
        image_media = [item for item in job.get("media") or [] if item.get("kind") == "image"]
        if not image_media:
            entry = dict(job)
            entry["history_entry_id"] = f"{job.get('id')}:pending"
            entry["media"] = []
            records.append(entry)
            continue
        for media_index, media in enumerate(image_media):
            entry = dict(job)
            entry["history_entry_id"] = f"{job.get('id')}:image:{media_index}"
            entry["history_media_index"] = media_index
            entry["media"] = [dict(media)]
            records.append(entry)
    return records


def image_studio_job_history_page(page: int = 1, page_size: int = 20) -> dict[str, Any]:
    records = image_studio_history_records()
    normalized_page_size = clamp_int(page_size, 1, 48)
    total = len(records)
    total_pages = max(1, math.ceil(total / normalized_page_size))
    normalized_page = max(1, min(total_pages, int(page)))
    start = (normalized_page - 1) * normalized_page_size
    return {
        "items": records[start : start + normalized_page_size],
        "page": normalized_page,
        "page_size": normalized_page_size,
        "total": total,
        "total_pages": total_pages,
    }


def saved_image_output_subdir() -> str:
    return str(read_local_config().get("image_output_subdir") or "").strip()


def normalize_image_output_subdir(value: str = "") -> str:
    return normalize_relative_output_subdir(value, IMAGE_STUDIO_OUTPUT_SUBDIR)


def image_studio_output_dir(paths: dict[str, Any] | None = None, subdir: str = "") -> Path:
    paths = paths or configured_comfy_paths()
    return Path(paths["output_dir"]) / normalize_image_output_subdir(subdir or saved_image_output_subdir())


def image_studio_output_payload(paths: dict[str, Any] | None = None) -> dict[str, Any]:
    paths = paths or configured_comfy_paths()
    subdir = normalize_image_output_subdir(saved_image_output_subdir())
    output_dir = image_studio_output_dir(paths, subdir)
    system = platform.system()
    open_supported = system in {"Windows", "Darwin"} or bool(shutil.which("xdg-open"))
    return {
        "ok": True,
        "subdir": subdir,
        "dir": str(output_dir),
        "output_root": str(paths["output_dir"]),
        "open_supported": open_supported,
    }


def open_system_directory(path: Path) -> None:
    if platform.system() == "Windows":
        os.startfile(str(path))  # type: ignore[attr-defined]
        return
    command = ["open", str(path)] if platform.system() == "Darwin" else [str(shutil.which("xdg-open") or ""), str(path)]
    if not command[0]:
        raise RuntimeError("当前系统未找到可用的文件管理器")
    subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **_hidden_popen_options(),
    )


@app.get("/api/download-center")
async def get_download_center(refresh: bool = False) -> dict[str, Any]:
    comfy_paths = await active_comfy_paths()
    active_base_dir = Path(str(comfy_paths.get("base_dir") or BASE_DIR)).expanduser().resolve()
    roots = download_center_storage_roots(active_base_dir)
    transfers, path_jobs = download_center_transfer_payloads()
    resources = await asyncio.to_thread(scan_download_center_resources, roots, force=refresh)
    resources = overlay_download_job_state(resources, path_jobs)
    resources = annotate_partial_resume_actions(resources)
    resources.sort(key=lambda item: (int(item.get("modified_at") or 0), str(item.get("label") or "")), reverse=True)

    settings = download_settings_payload()
    preset_labels = {
        str(item.get("id") or ""): str(item.get("label") or item.get("id") or "")
        for item in settings.get("source_presets") or []
        if isinstance(item, dict)
    }
    selected_root = next((item for item in roots if item.get("role") == "saved"), roots[0] if roots else {})
    active_statuses = {"queued", "running", "pausing", "canceling"}
    paused_statuses = {"paused", "interrupted"}
    installed = [item for item in resources if item.get("status") == "installed"]
    partials = [item for item in resources if item.get("resource_type") == "partial"]
    model_resources = [item for item in installed if item.get("kind") == "model"]
    node_resources = [item for item in installed if item.get("kind") == "custom_node"]
    return {
        "ok": True,
        "app_version": APP_VERSION,
        "updated_at": now_ms(),
        "summary": {
            "transfer_count": len(transfers),
            "active_count": sum(1 for item in transfers if item.get("status") in active_statuses),
            "paused_count": sum(1 for item in transfers if item.get("status") in paused_statuses),
            "installed_count": len(installed),
            "model_count": len(model_resources),
            "custom_node_count": len(node_resources),
            "partial_count": len(partials),
            "model_bytes": sum(int(item.get("size_bytes") or 0) for item in model_resources),
            "partial_bytes": sum(int(item.get("size_bytes") or 0) for item in partials),
        },
        "source": {
            "region": str(settings.get("download_region") or "international"),
            "region_label": preset_labels.get(str(settings.get("download_region") or ""), "自定义"),
            "hf_endpoint": str(settings.get("hf_endpoint") or settings.get("official_hf_endpoint") or ""),
            "pip_index_url": str(settings.get("pip_index_url") or settings.get("official_pip_index_url") or ""),
        },
        "selected_root": selected_root,
        "roots": roots,
        "open_supported": platform.system() in {"Windows", "Darwin"} or bool(shutil.which("xdg-open")),
        "transfers": transfers,
        "resources": resources,
    }


@app.post("/api/download-center/resume")
async def resume_download_center_partial(payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    resource_id = str((payload or {}).get("resource_id") or "").strip()
    if not resource_id:
        raise HTTPException(status_code=400, detail="请选择要续传的断点文件")

    comfy_paths = await active_comfy_paths()
    active_base_dir = Path(str(comfy_paths.get("base_dir") or BASE_DIR)).expanduser().resolve()
    roots = download_center_storage_roots(active_base_dir)
    _transfers, path_jobs = download_center_transfer_payloads()
    resources = await asyncio.to_thread(scan_download_center_resources, roots, force=True)
    resources = annotate_partial_resume_actions(overlay_download_job_state(resources, path_jobs))
    resource = next((item for item in resources if str(item.get("id") or "") == resource_id), None)
    if not resource or resource.get("resource_type") != "partial":
        raise HTTPException(status_code=404, detail="断点文件不存在，请刷新下载中心")
    if not resource.get("can_resume"):
        raise HTTPException(status_code=409, detail=str(resource.get("resume_note") or "该断点当前不能自动续传"))

    job_id = str(resource.get("download_job_id") or "").strip()
    if resource.get("resume_mode") == "job" and job_id:
        job = await resume_install_job(job_id)
        return {"ok": True, "mode": "job", "job": job, "resource_id": resource_id}

    asset_id = str(resource.get("catalog_id") or "").strip()
    profile = str(resource.get("resume_profile") or "").strip()
    storage_root = str(resource.get("storage_root") or "").strip()
    if not asset_id or not profile or not storage_root:
        raise HTTPException(status_code=409, detail="断点缺少资源编号、安装档位或存储目录，无法自动续传")

    job = await install_workflow_assets(profile=profile, target_dir=storage_root, asset_id=asset_id)
    label = str(resource.get("label") or resource.get("name") or "模型文件")
    job["title"] = f"续传 · {label}"
    job["resume_resource_id"] = resource_id
    job["resume_from_bytes"] = int(resource.get("size_bytes") or 0)
    job["resume_partial_path"] = str(resource.get("path") or "")
    persist_job_stores(force=True)
    return {"ok": True, "mode": "asset", "job": job, "resource_id": resource_id}


@app.post("/api/download-center/open")
async def open_download_center_path(payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    comfy_paths = await active_comfy_paths()
    active_base_dir = Path(str(comfy_paths.get("base_dir") or BASE_DIR)).expanduser().resolve()
    roots = download_center_storage_roots(active_base_dir)
    allowed_roots = [Path(str(item["path"])).expanduser().resolve() for item in roots]
    selected_root = next((path for item, path in zip(roots, allowed_roots) if item.get("role") == "saved"), None)
    raw_path = str((payload or {}).get("path") or "").strip()
    candidate = Path(raw_path).expanduser().resolve() if raw_path else (selected_root or active_base_dir) / "models"
    target = candidate.parent if candidate.is_file() else candidate
    if not any(target == root or root in target.parents for root in allowed_roots):
        raise HTTPException(status_code=400, detail="只能打开当前 ComfyUI 或已登记模型目录中的路径")
    if not target.is_dir():
        raise HTTPException(status_code=404, detail=f"目录不存在：{target}")
    try:
        await asyncio.to_thread(open_system_directory, target)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"打开目录失败：{exc}") from exc
    return {"ok": True, "path": str(target)}


def image_studio_output_prefix(profile_id: str = "", subdir: str = "") -> str:
    profile_slug = re.sub(r"[^A-Za-z0-9_-]+", "_", profile_id or "image").strip("_") or "image"
    output_subdir = normalize_image_output_subdir(subdir)
    return f"{output_subdir}/{profile_slug}_{time.strftime('%Y-%m-%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"




@app.get("/api/nsfw-playbook")
async def get_nsfw_playbook() -> dict[str, Any]:
    return playbook_payload(read_local_config())


@app.post("/api/nsfw-playbook")
async def save_nsfw_playbook(payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    reset = bool((payload or {}).get("reset"))
    with CONFIG_LOCK:
        config = read_local_config()
        if reset:
            config.pop(PLAYBOOK_CONFIG_KEY, None)
        else:
            incoming = (payload or {}).get("playbook")
            if not isinstance(incoming, dict):
                raise HTTPException(status_code=400, detail="playbook 必须是对象")
            config[PLAYBOOK_CONFIG_KEY] = incoming
        write_local_config(config)
    result = playbook_payload(read_local_config())
    result["message"] = "玩法配置已恢复默认。" if reset else "玩法配置已保存。"
    return result


@app.get("/api/nsfw-extensions/capabilities")
async def get_nsfw_extension_capabilities() -> dict[str, Any]:
    comfy_paths = await active_comfy_paths()
    base_dir = Path(comfy_paths["base_dir"])
    try:
        object_info = await get_comfy_object_info()
    except HTTPException as exc:
        return {
            "ok": False,
            "connected": False,
            "error": comfy_connection_error_text(exc),
            "capabilities": capability_payload(None, base_dir),
        }
    return {
        "ok": True,
        "connected": True,
        "capabilities": capability_payload(object_info, base_dir),
    }


@app.post("/api/video/extract-frame")
async def video_extract_frame(
    position: float = Form(0.5),
    source_video_filename: str = Form(""),
    source_video_subfolder: str = Form(""),
    source_video_type: str = Form("output"),
    video: UploadFile | None = File(None),
) -> dict[str, Any]:
    comfy_paths = await active_comfy_paths()
    if video and video.filename:
        video_name = await save_upload(video, VIDEO_EXTENSIONS, comfy_paths)
        source_path = input_media_path(video_name, comfy_paths)
        source_filename = Path(video_name.replace("\\", "/")).name
        source_subfolder = "beginner_frontend"
        source_type = "input"
    elif source_video_filename:
        source_path = safe_media_path(
            source_video_filename,
            source_video_subfolder,
            source_video_type or "output",
            comfy_paths,
        )
        source_filename = source_video_filename
        source_subfolder = source_video_subfolder
        source_type = source_video_type or "output"
    else:
        raise HTTPException(status_code=400, detail="请上传视频或指定 source_video_filename。")
    if source_path.suffix.lower() not in VIDEO_EXTENSIONS:
        raise HTTPException(status_code=400, detail="所选文件不是支持的视频格式。")
    input_name, meta = await asyncio.to_thread(
        video_frame_extract_path,
        source_path,
        position=position,
        paths=comfy_paths,
    )
    return {
        "ok": True,
        "input_name": input_name,
        "preview_url": meta["preview_url"],
        "width": meta["width"],
        "height": meta["height"],
        "position": meta["position"],
        "timestamp_seconds": meta["timestamp_seconds"],
        "source_video": {
            "filename": source_filename,
            "subfolder": source_subfolder,
            "type": source_type,
        },
        "message": "已从视频抽帧并复制到 ComfyUI input，可送入图片工作室。",
    }


@app.post("/api/video/tune")
async def video_tune(
    source_video_filename: str = Form(""),
    source_video_subfolder: str = Form(""),
    source_video_type: str = Form("output"),
    flicker_preset: str = Form("balanced"),
    brightness: float = Form(0.0),
    contrast: float = Form(1.0),
    saturation: float = Form(1.0),
    sharpness: float = Form(0.0),
    video: UploadFile | None = File(None),
) -> JSONResponse:
    comfy_paths = await active_comfy_paths()
    if video and video.filename:
        video_name = await save_upload(video, VIDEO_EXTENSIONS, comfy_paths)
        source_path = input_media_path(video_name, comfy_paths)
    elif source_video_filename:
        source_path = safe_media_path(
            source_video_filename,
            source_video_subfolder,
            source_video_type or "output",
            comfy_paths,
        )
    else:
        raise HTTPException(status_code=400, detail="请上传待微调视频或选择一个已有视频输出。")
    if source_path.suffix.lower() not in VIDEO_EXTENSIONS:
        raise HTTPException(status_code=400, detail="视频微调只支持常见视频文件。")

    preset = flicker_preset if flicker_preset in {"off", "light", "balanced", "strong"} else "balanced"
    brightness_value = clamp_float(brightness, -0.2, 0.2)
    contrast_value = clamp_float(contrast, 0.5, 1.5)
    saturation_value = clamp_float(saturation, 0.0, 2.0)
    sharpness_value = clamp_float(sharpness, 0.0, 1.5)
    job = {
        "id": uuid.uuid4().hex,
        "prompt_id": None,
        "kind": "video_postprocess",
        "mode": "video_tune",
        "title": "视频微调与闪烁修复",
        "status": "queued",
        "completed": False,
        "local": True,
        "created_at": now_ms(),
        "progress": {
            "percent": 0.0,
            "label": "等待本地处理线程",
            "source": "local_queue",
            "accurate": False,
        },
        "status_note": "等待本地处理线程",
        "media": [],
        "model_profile": "ffmpeg_video_tune",
        "video_tune": {
            "flicker_preset": preset,
            "brightness": brightness_value,
            "contrast": contrast_value,
            "saturation": saturation_value,
            "sharpness": sharpness_value,
        },
    }
    queue_local_video_job(
        job,
        operation="tune",
        kwargs={
            "source": source_path,
            "flicker_preset": preset,
            "brightness": brightness_value,
            "contrast": contrast_value,
            "saturation": saturation_value,
            "sharpness": sharpness_value,
            "paths": comfy_paths,
        },
    )
    return JSONResponse(job)


@app.post("/api/video/face-swap")
async def video_face_swap(
    authorization_confirmed: bool = Form(False),
    face_authorization_token: str = Form(""),
    source_video_filename: str = Form(""),
    source_video_subfolder: str = Form(""),
    source_video_type: str = Form("output"),
    identity_image_filename: str = Form(""),
    identity_image_subfolder: str = Form(""),
    identity_image_type: str = Form("input"),
    faceswap_weight: float = Form(0.85),
    fps: int = Form(24),
    video: UploadFile | None = File(None),
    identity_image: UploadFile | None = File(None),
) -> JSONResponse:
    authorized, auth_token = resolve_face_authorization(
        confirmed=authorization_confirmed,
        token=face_authorization_token,
        statement=FACE_SWAP_AUTHORIZATION_STATEMENT,
    )
    if not authorized:
        raise HTTPException(status_code=403, detail="视频换脸前必须确认已取得相关人员的明确授权。")

    comfy_paths = await active_comfy_paths()
    if video and video.filename:
        video_name = await save_upload(video, VIDEO_EXTENSIONS, comfy_paths)
    elif source_video_filename:
        source_path = safe_media_path(
            source_video_filename,
            source_video_subfolder,
            source_video_type or "output",
            comfy_paths,
        )
        if source_path.suffix.lower() not in VIDEO_EXTENSIONS:
            raise HTTPException(status_code=400, detail="source_video_filename 不是支持的视频。")
        video_name = copy_media_to_input(
            source_video_filename,
            source_video_subfolder,
            source_video_type or "output",
            comfy_paths,
        )
    else:
        raise HTTPException(status_code=400, detail="请上传视频或指定 source_video_filename。")

    if identity_image and identity_image.filename:
        identity_name = await save_upload(identity_image, IMAGE_EXTENSIONS, comfy_paths)
    elif identity_image_filename:
        identity_name = copy_image_to_input(
            identity_image_filename,
            identity_image_subfolder,
            identity_image_type or "input",
            comfy_paths,
        )
    else:
        raise HTTPException(status_code=400, detail="请上传身份参考图或指定 identity_image_filename。")

    try:
        object_info = await get_comfy_object_info()
    except HTTPException as exc:
        raise HTTPException(
            status_code=503,
            detail=comfy_not_connected_detail("提交视频换脸 workflow", exc.detail),
        ) from exc
    caps = capability_payload(object_info, Path(comfy_paths["base_dir"]))
    if not caps["video_face_swap"]["ready"]:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "视频换脸组件尚未就绪。",
                "capabilities": caps["video_face_swap"],
                "install_profile": FACE_SWAP_INSTALL_PROFILE,
            },
        )

    fps = clamp_int(fps, 1, 60)
    prefix = output_prefix("VideoFaceSwap")
    try:
        graph, resolved = build_video_face_swap_prompt(
            video_name,
            identity_name,
            object_info,
            faceswap_weight=faceswap_weight,
            fps=fps,
            filename_prefix=prefix,
            pick_option=preferred_node_option,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    graph = resolve_graph_model_option_names(graph, object_info)
    errors = image_studio_graph_errors(graph, object_info)
    if errors:
        raise HTTPException(status_code=400, detail={"message": "视频换脸工作流无效", "errors": errors})

    progress_stream_connected = await ensure_comfy_progress_listener()
    await reconcile_heavy_generation_jobs_before_submit()
    job_id = uuid.uuid4().hex
    created_at = now_ms()
    reserve_generation_job_slot(
        job_id=job_id,
        kind="video_face_swap",
        mode="video_face_swap",
        title="ReActor · 视频换脸",
        created_at=created_at,
    )
    try:
        response = await comfy_post("/prompt", {"prompt": graph, "client_id": CLIENT_ID})
        prompt_id = str(response.get("prompt_id") or "")
        if not prompt_id:
            raise HTTPException(status_code=500, detail=response)
    except Exception as exc:
        fail_generation_job_slot(job_id, f"提交到 ComfyUI 失败：{exc}")
        raise
    job = {
        "id": job_id,
        "prompt_id": prompt_id,
        "prompt_ids": [prompt_id],
        "kind": "video_face_swap",
        "mode": "video_face_swap",
        "title": "ReActor · 视频换脸",
        "status": "queued",
        "completed": False,
        "created_at": created_at,
        "fps": fps,
        "media": [],
        "raw": [response],
        "model_profile": "video_face_swap_reactor",
        "face_authorization_confirmed": True,
        "face_authorization_token": auth_token,
        "face_authorization_statement": FACE_SWAP_AUTHORIZATION_STATEMENT,
        "video_face_swap": {
            **resolved,
            "video_input": video_name,
            "identity_input": identity_name,
            "faceswap_weight": faceswap_weight,
        },
        "progress_stream_connected": progress_stream_connected,
    }
    job["progress"] = generation_progress_payload(job)
    finalize_generation_job_slot(job)
    return JSONResponse(job)


@app.get("/api/character-box")
async def get_character_box() -> dict[str, Any]:
    return character_box_payload(read_local_config())


@app.post("/api/character-box")
async def save_character_box(payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    action = str((payload or {}).get("action") or "upsert").strip().lower()
    with CONFIG_LOCK:
        config = read_local_config()
        items = normalize_character_box(config.get(CHARACTER_BOX_CONFIG_KEY) or [])
        if action == "clear":
            items = []
        elif action == "delete":
            target = str((payload or {}).get("id") or "").strip()
            items = [item for item in items if item.get("id") != target]
        else:
            entry = (payload or {}).get("item") if isinstance((payload or {}).get("item"), dict) else payload
            identity = str((entry or {}).get("identity_filename") or "").strip()
            if not identity:
                raise HTTPException(status_code=400, detail="角色盒需要身份脸文件名")
            item_id = str((entry or {}).get("id") or "")
            updated = False
            for item in items:
                if item_id and item.get("id") == item_id:
                    item.update(
                        {
                            "label": str((entry or {}).get("label") or item.get("label") or identity)[:80],
                            "identity_filename": identity,
                            "identity_subfolder": str((entry or {}).get("identity_subfolder") or ""),
                            "identity_type": str((entry or {}).get("identity_type") or "input"),
                            "preview_url": str((entry or {}).get("preview_url") or item.get("preview_url") or ""),
                            "notes": str((entry or {}).get("notes") or "")[:200],
                        }
                    )
                    updated = True
                    break
            if not updated:
                items = normalize_character_box([*(items), entry or {}])
        config[CHARACTER_BOX_CONFIG_KEY] = items
        write_local_config(config)
    result = character_box_payload(read_local_config())
    result["message"] = "角色盒已更新。"
    return result


@app.get("/api/image-studio")
async def image_studio_bootstrap(
    limit: int = 20,
    refresh: bool = False,
    profile: str = "",
    target_dir: str = "",
) -> dict[str, Any]:
    comfy_paths = await active_comfy_paths()
    active_base_dir = Path(comfy_paths["base_dir"])
    try:
        install_base_dir = normalize_model_download_dir(target_dir or saved_model_download_dir(), active_base_dir)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    all_assets = collect_asset_checks(install_base_dir)
    asset_by_id = {str(item.get("id") or ""): item for item in all_assets}
    image_assets = [asset_by_id[item_id] for item_id in IMAGE_ASSET_IDS if item_id in asset_by_id]

    object_info: dict[str, Any] | None = None
    connection_error = ""
    try:
        object_info = await get_comfy_object_info(force=refresh)
    except HTTPException as exc:
        connection_error = comfy_connection_error_text(exc)

    profiles: list[dict[str, Any]] = []
    for profile_item in IMAGE_PROFILES:
        edit_capability = image_edit_capability(str(profile_item["id"]))
        generation_supported = profile_item.get("generation_supported") is not False
        graph: dict[str, Any] = {}
        graph_errors: list[str] = []
        if generation_supported:
            graph = build_image_prompt(
                prompt=DEFAULT_IMAGE_PROMPT,
                negative=DEFAULT_IMAGE_NEGATIVE,
                width=1328,
                height=1328,
                seed=1,
                profile_id=str(profile_item["id"]),
                steps=int(profile_item["default_steps"]),
                cfg=float(profile_item["default_cfg"]),
                sampler=str(profile_item["default_sampler"]),
                scheduler=str(profile_item["default_scheduler"]),
            )
            if object_info is not None:
                graph = resolve_graph_model_option_names(graph, object_info)
            graph_errors = image_studio_graph_errors(graph, object_info)
        else:
            graph_errors = ["该模型仅支持已有图片微调，请切换到图片微调模式。"]
        required_ids = set(profile_item.get("required_asset_ids") or [])
        optional_ids = set(profile_item.get("optional_asset_ids") or [])
        profile_missing = [item for item in image_assets if item.get("id") in required_ids and not item.get("ok")]
        optional_missing = [item for item in image_assets if item.get("id") in optional_ids and not item.get("ok")]
        if connection_error:
            graph_errors.append(connection_error)
        edit_graph_errors: list[str] = []
        edit_node_count = 0
        if edit_capability.get("supported"):
            reference_placeholders = (
                ["__qwen_image_21_reference_2__.png"]
                if int(edit_capability.get("max_reference_images") or 1) > 1
                else []
            )
            edit_graph = build_image_prompt(
                prompt="把背景调整为柔和的影棚环境，保留主体特征和构图",
                negative=DEFAULT_IMAGE_NEGATIVE,
                width=1328,
                height=1328,
                seed=1,
                profile_id=str(profile_item["id"]),
                steps=int(profile_item["default_steps"]),
                cfg=float(profile_item["default_cfg"]),
                sampler=str(profile_item["default_sampler"]),
                scheduler=str(profile_item["default_scheduler"]),
                source_image=IMAGE_EDIT_SOURCE_PLACEHOLDER,
                reference_images=reference_placeholders,
                edit_strength=float(edit_capability.get("strength_default") or 0.35),
            )
            if object_info is not None:
                edit_graph = resolve_graph_model_option_names(edit_graph, object_info)
            edit_graph_errors = image_studio_graph_errors(edit_graph, object_info)
            if connection_error:
                edit_graph_errors.append(connection_error)
            edit_node_count = len(edit_graph)
        install_profile_id = str(profile_item.get("install_profile") or QWEN_IMAGE_INSTALL_PROFILE)
        install_assets = filter_assets_for_install_profile(all_assets, install_profile_id)
        install_missing = installable_missing_items(install_assets, [])
        plan = install_plan_payload(
            profile=install_profile_id,
            assets=all_assets,
            custom_nodes=[],
            missing=install_missing,
            base_dir=install_base_dir,
        )
        nsfw_config = dict(profile_item.get("nsfw") or {})
        addon_asset_id = str(nsfw_config.get("asset_id") or "")
        addon_asset = asset_by_id.get(addon_asset_id) if addon_asset_id else None
        nsfw_config["addon_ready"] = bool(addon_asset and addon_asset.get("ok"))
        required_addon_nodes = list(nsfw_config.get("required_nodes") or [])
        if required_addon_nodes:
            addon_profile = CATALOG_INSTALL_PROFILES[str(nsfw_config["addon_profile"])]
            addon_repos = [repo for repo in CATALOG_CUSTOM_NODE_REPOS if repo["id"] in addon_profile["custom_node_ids"]]
            nsfw_config["addon_installed"] = nsfw_config["addon_ready"] and all(
                (active_base_dir / str(repo["dest"]) / "__init__.py").is_file() for repo in addon_repos
            )
            nsfw_config["missing_nodes"] = [name for name in required_addon_nodes if name not in (object_info or {})]
            registry_node = str(nsfw_config.get("model_loader") or "UnetLoaderGGUF")
            registry_field = "unet_name"
            registry_name = str(nsfw_config.get("model_override") or "")
            if nsfw_config.get("lora_name"):
                registry_node, registry_field = "LoraLoaderModelOnly", "lora_name"
                registry_name = str(nsfw_config["lora_name"])
            model_registered = model_option_matches(
                node_input_options(object_info or {}, registry_node, registry_field), registry_name
            )
            nsfw_config["addon_ready"] = bool(nsfw_config["addon_installed"] and not nsfw_config["missing_nodes"] and model_registered)
            nsfw_config["readiness_note"] = (
                "文件已就绪，请连接 ComfyUI 后复检。" if object_info is None
                else "文件已就绪，请重启 ComfyUI 加载扩展所需节点。" if nsfw_config["missing_nodes"]
                else "扩展模型尚未出现在节点列表，请检查模型目录并刷新。" if not model_registered
                else ""
            ) if nsfw_config["addon_installed"] else ""
        profiles.append(
            {
                **profile_item,
                "install_profile": install_profile_id,
                "ready": generation_supported and not profile_missing and not graph_errors,
                "missing": [
                    {
                        "id": item.get("id"),
                        "label": item.get("label"),
                        "expected_gb": item.get("expected_gb"),
                        "remaining_gb": item.get("remaining_gb"),
                        "reason": item.get("reason"),
                    }
                    for item in profile_missing
                ],
                "optional_missing": [
                    {
                        "id": item.get("id"),
                        "label": item.get("label"),
                        "expected_gb": item.get("expected_gb"),
                        "remaining_gb": item.get("remaining_gb"),
                        "reason": item.get("reason"),
                    }
                    for item in optional_missing
                ],
                "graph_errors": graph_errors,
                "node_count": len(graph),
                "image_edit": {
                    **edit_capability,
                    "ready": bool(edit_capability.get("supported")) and not profile_missing and not edit_graph_errors,
                    "graph_errors": edit_graph_errors,
                    "node_count": edit_node_count,
                },
                "install_plan": plan,
                "nsfw": nsfw_config,
            }
        )
    selected_profile = next((item for item in profiles if item["id"] == profile), profiles[0])
    selected_missing = selected_profile.get("missing") or []
    face_swap = face_swap_capability_payload(object_info, active_base_dir, connection_error)
    history_page = image_studio_job_history_page(1, limit)
    return {
        **image_studio_static_payload(),
        "ok": object_info is not None,
        "comfy": {
            "connected": object_info is not None,
            "url": current_comfy_url(),
            "error": connection_error,
        },
        "paths": serializable_comfy_paths(comfy_paths),
        "base_dir": str(install_base_dir),
        "active_base_dir": str(active_base_dir),
        "custom_target": os.path.normcase(str(install_base_dir)) != os.path.normcase(str(active_base_dir)),
        "storage_locations": model_storage_candidates(active_base_dir),
        "profiles": profiles,
        "assets": [
            {
                "id": item.get("id"),
                "label": item.get("label"),
                "ok": bool(item.get("ok")),
                "expected_gb": item.get("expected_gb"),
                "remaining_gb": item.get("remaining_gb"),
                "reason": item.get("reason"),
                "relative_path": item.get("relative_path"),
            }
            for item in image_assets
        ],
        "ready": any(item.get("ready") for item in profiles),
        "selected_profile": selected_profile["id"],
        "missing_count": len(selected_missing),
        "install_plan": selected_profile["install_plan"],
        "download_settings": download_settings_payload(),
        "nsfw_playbook": playbook_payload(read_local_config()),
        "character_box": character_box_payload(read_local_config()),
        "style_presets": merged_style_presets(),
        "face_extraction": face_extraction_capability_payload(),
        "face_swap": face_swap,
        "output": image_studio_output_payload(comfy_paths),
        "history": history_page["items"],
        "history_pagination": {key: value for key, value in history_page.items() if key != "items"},
    }


@app.get("/api/image-studio/history")
async def get_image_studio_history(page: int = 1, page_size: int = 20) -> dict[str, Any]:
    return {"ok": True, **image_studio_job_history_page(page, page_size)}


@app.get("/api/image-studio/output")
async def get_image_studio_output() -> dict[str, Any]:
    return image_studio_output_payload(await active_comfy_paths())


@app.post("/api/image-studio/handoff")
async def image_studio_handoff(payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    filename = str((payload or {}).get("filename") or "").strip()
    subfolder = str((payload or {}).get("subfolder") or "").strip()
    file_type = str((payload or {}).get("type") or "output").strip() or "output"
    if not filename:
        raise HTTPException(status_code=400, detail="请选择要送入视频工作流的图片")

    paths = await active_comfy_paths()
    input_name = copy_image_to_input(filename, subfolder, file_type, paths)
    input_path = input_media_path(input_name, paths)
    preview_item = {
        "filename": input_path.name,
        "subfolder": "beginner_frontend",
        "type": "input",
    }
    source_prompt = re.sub(r"\s+", " ", str((payload or {}).get("source_prompt") or "").strip())[:500]
    carry_nsfw = bool((payload or {}).get("nsfw"))
    nsfw_strength = (payload or {}).get("nsfw_lora_strength")
    try:
        nsfw_strength_value = float(nsfw_strength) if nsfw_strength is not None else None
    except (TypeError, ValueError):
        nsfw_strength_value = None
    character_id = str((payload or {}).get("character_id") or "").strip()
    return {
        "ok": True,
        "input_name": input_name,
        "preview_url": media_url(preview_item),
        "source_filename": filename,
        "source_profile": clean_label(str((payload or {}).get("model_profile") or "")),
        "source_label": clean_label(str((payload or {}).get("model_label") or "")),
        "source_prompt": source_prompt,
        "nsfw": carry_nsfw,
        "nsfw_lora_strength": nsfw_strength_value,
        "nsfw_intensity": str((payload or {}).get("nsfw_intensity") or ""),
        "character_id": character_id,
        "identity_filename": str((payload or {}).get("identity_filename") or ""),
        "face_authorization_confirmed": bool((payload or {}).get("face_authorization_confirmed")),
        "wizard_id": str((payload or {}).get("wizard_id") or "").strip(),
        "message": "图片已复制到 ComfyUI input，并设为视频关键帧。",
    }


@app.post("/api/image-studio/face-extract")
async def image_studio_face_extract(
    authorization_confirmed: bool = Form(False),
    face_authorization_token: str = Form(""),
    crop_mode: str = Form("face"),
    source_image_filename: str = Form(""),
    source_image_subfolder: str = Form(""),
    source_image_type: str = Form(""),
    source_image: UploadFile | None = File(None),
) -> dict[str, Any]:
    authorized, _ = resolve_face_authorization(
        confirmed=authorization_confirmed,
        token=face_authorization_token,
        statement=FACE_AUTHORIZATION_STATEMENT,
    )
    if not authorized:
        raise HTTPException(status_code=403, detail="提取面部前必须确认已取得照片中相关人员的明确授权。")
    capability = face_extraction_capability_payload()
    if not capability["available"]:
        raise HTTPException(status_code=503, detail=capability["error"])

    comfy_paths = await active_comfy_paths()
    if source_image and source_image.filename:
        source_name = await save_upload(source_image, IMAGE_EXTENSIONS, comfy_paths)
        source_origin = "upload"
    elif source_image_filename:
        source_name = copy_image_to_input(
            source_image_filename,
            source_image_subfolder,
            source_image_type or "output",
            comfy_paths,
        )
        source_origin = "history"
    else:
        raise HTTPException(status_code=400, detail="请先导入一张照片，再提取面部。")

    source_path = input_media_path(source_name, comfy_paths)
    extraction_id = uuid.uuid4().hex
    crop_mode = normalize_face_crop_mode(crop_mode)
    faces = await asyncio.to_thread(
        extract_faces_to_input,
        source_path,
        comfy_paths,
        extraction_id=extraction_id,
        crop_mode=crop_mode,
    )
    source_relative = Path(source_name.replace("\\", "/"))
    original = {
        "filename": source_relative.name,
        "subfolder": source_relative.parent.as_posix() if source_relative.parent.as_posix() != "." else "",
        "type": "input",
        "origin": source_origin,
        "width": 0,
        "height": 0,
    }
    try:
        with Image.open(source_path) as opened:
            oriented = ImageOps.exif_transpose(opened)
            original["width"], original["height"] = oriented.size
    except (OSError, ValueError):
        pass
    original["url"] = media_url(original)
    record = {
        "id": extraction_id,
        "created_at": now_ms(),
        "crop_mode": crop_mode,
        "authorization_confirmed": True,
        "authorization_statement": FACE_AUTHORIZATION_STATEMENT,
        "original": original,
        "faces": faces,
    }
    register_face_extraction(record)
    auth_token = issue_face_authorization_token(statement=FACE_AUTHORIZATION_STATEMENT)
    return {
        "ok": True,
        "id": extraction_id,
        "method": capability["method"],
        "local_only": True,
        "identity_recognition": False,
        "authorization": {
            "confirmed": True,
            "statement": FACE_AUTHORIZATION_STATEMENT,
            "token": auth_token,
        },
        "crop_mode": crop_mode,
        "original": original,
        "faces": faces,
        "selected_index": int(faces[0]["index"]),
        "message": f"已在本机检测到 {len(faces)} 张面部，请选择要作为参考的面部。",
    }


@app.post("/api/image-studio/face-swap")
async def image_studio_face_swap(
    authorization_confirmed: bool = Form(False),
    face_authorization_token: str = Form(""),
    target_face_extract_id: str = Form(""),
    target_face_index: int = Form(-1),
    identity_face_extract_id: str = Form(""),
    identity_face_index: int = Form(-1),
    face_swap_strength: float = Form(100.0),
    face_restore_model: str = Form("none"),
    face_restore_visibility: float = Form(0.8),
) -> JSONResponse:
    authorized, auth_token = resolve_face_authorization(
        confirmed=authorization_confirmed,
        token=face_authorization_token,
        statement=FACE_SWAP_AUTHORIZATION_STATEMENT,
    )
    if not authorized:
        raise HTTPException(status_code=403, detail="换脸前必须确认目标图与身份参考图均已取得明确授权。")
    if not target_face_extract_id or target_face_index < 0:
        raise HTTPException(status_code=400, detail="请先检测目标图并选择要替换的面部。")
    if not identity_face_extract_id or identity_face_index < 0:
        raise HTTPException(status_code=400, detail="请先检测身份参考图并选择要使用的面部。")
    if not math.isfinite(face_swap_strength) or not 0.0 <= face_swap_strength <= 100.0:
        raise HTTPException(status_code=400, detail="身份替换强度必须在 0 到 100 之间。")
    if not math.isfinite(face_restore_visibility) or not 0.1 <= face_restore_visibility <= 1.0:
        raise HTTPException(status_code=400, detail="面部修复融合度必须在 0.1 到 1.0 之间。")

    target_face, target_record = validated_face_extraction(target_face_extract_id, target_face_index)
    identity_face, identity_record = validated_face_extraction(identity_face_extract_id, identity_face_index)
    comfy_paths = await active_comfy_paths()
    active_base_dir = Path(comfy_paths["base_dir"])
    try:
        object_info = await get_comfy_object_info()
    except HTTPException as exc:
        raise HTTPException(
            status_code=503,
            detail=comfy_not_connected_detail("提交 ReActor 换脸 workflow", exc.detail),
        ) from exc
    capability = face_swap_capability_payload(object_info, active_base_dir)
    if not capability["ready"]:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "本地换脸组件尚未就绪。",
                "errors": capability.get("errors") or [],
                "actions": ["在图片微调的换脸面板中点击“准备换脸组件”，完成后重启 ComfyUI 8188。"],
                "install_profile": FACE_SWAP_INSTALL_PROFILE,
            },
        )

    target_original = dict(target_record.get("original") or {})
    identity_original = dict(identity_record.get("original") or {})
    try:
        target_image_name = extracted_input_name(target_original)
        target_face_name = extracted_input_name(target_face)
        identity_face_name = extracted_input_name(identity_face)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    for input_name in (target_image_name, target_face_name, identity_face_name):
        input_media_path(input_name, comfy_paths)

    output_subdir = normalize_image_output_subdir(saved_image_output_subdir())
    output_dir = image_studio_output_dir(comfy_paths, output_subdir)
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"无法创建图片输出目录：{exc}") from exc
    try:
        graph, resolved = build_face_swap_prompt(
            object_info=object_info,
            target_image=target_image_name,
            target_face_image=target_face_name,
            identity_face_image=identity_face_name,
            target_face_index=target_face_index,
            strength=face_swap_strength,
            restore_model=face_restore_model,
            restore_visibility=face_restore_visibility,
            filename_prefix=image_studio_output_prefix("face_swap_reactor", output_subdir),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    errors = image_studio_graph_errors(graph, object_info)
    if errors:
        raise HTTPException(status_code=400, detail={"message": "换脸工作流无效", "errors": errors})

    progress_stream_connected = await ensure_comfy_progress_listener()
    response = await comfy_post("/prompt", {"prompt": graph, "client_id": CLIENT_ID})
    prompt_id = str(response.get("prompt_id") or "")
    if not prompt_id:
        raise HTTPException(status_code=500, detail=response)
    width = int(target_original.get("width") or 0)
    height = int(target_original.get("height") or 0)
    source_label = f"目标面部 {target_face_index + 1} ← 身份参考面部 {identity_face_index + 1}"
    job = {
        "id": uuid.uuid4().hex,
        "prompt_id": prompt_id,
        "prompt_ids": [prompt_id],
        "prompt_seeds": [],
        "kind": "image_generation",
        "mode": "image_face_swap",
        "title": "ReActor · 换脸微调",
        "status": "queued",
        "completed": False,
        "created_at": now_ms(),
        "seed": None,
        "width": width,
        "height": height,
        "aspect": "source",
        "steps": None,
        "cfg": None,
        "sampler": "ReActor",
        "scheduler": "face_swap",
        "batch_size": 1,
        "graph_batch_size": 1,
        "generation_mode": "batch",
        "generation_mode_requested": "batch",
        "generation_mode_adjusted": False,
        "prompt_mode": "none",
        "style_preset": "source",
        "style_label": "保留目标图",
        "source_prompt": source_label,
        "effective_prompt": source_label,
        "exact_text": "",
        "negative": "",
        "media": [],
        "raw": [response],
        "model_profile": "face_swap_reactor",
        "model_family": "ReActor",
        "nsfw": False,
        "edit_mode": True,
        "edit_operation": "face_swap",
        "edit_method": "identity_face_swap",
        "edit_label": "换脸",
        "source_adherence": 1.0,
        "source_adherence_mode": "target_pixels_except_selected_face",
        "edit_strength": None,
        "edit_resize_mode": None,
        "source_processing": "target_full_image",
        "face_authorization_confirmed": True,
        "face_authorization_token": auth_token,
        "face_authorization_statement": FACE_SWAP_AUTHORIZATION_STATEMENT,
        "face_swap": {
            **resolved,
            "target_extraction_id": target_face_extract_id,
            "identity_extraction_id": identity_face_extract_id,
            "identity_face_index": identity_face_index,
            "restore_visibility": max(0.1, min(1.0, float(face_restore_visibility))),
            "local_only": True,
        },
        "source_image": {
            **target_original,
            "input_name": target_image_name,
            "processing": "target_full_image",
            "selected_face": target_face,
        },
        "identity_source_image": {
            **identity_original,
            "processing": "selected_face_identity",
            "selected_face": identity_face,
        },
        "output_subdir": output_subdir,
        "output_dir": str(output_dir),
        "completed_prompt_ids": [],
        "failed_prompt_ids": [],
        "prompt_progress": {},
        "progress_stream_connected": progress_stream_connected,
    }
    job["progress"] = generation_progress_payload(job)
    store_generation_job(job)
    return JSONResponse(job)


@app.post("/api/image-studio/output")
async def save_image_studio_output(payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    subdir = normalize_image_output_subdir(str((payload or {}).get("subdir") or ""))
    paths = await active_comfy_paths()
    output_dir = image_studio_output_dir(paths, subdir)
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"无法创建图片输出目录：{exc}") from exc
    config = read_local_config()
    config["image_output_subdir"] = "" if subdir == IMAGE_STUDIO_OUTPUT_SUBDIR else subdir
    write_local_config(config)
    return image_studio_output_payload(paths)


@app.post("/api/image-studio/output/open")
async def open_image_studio_output() -> dict[str, Any]:
    paths = await active_comfy_paths()
    output = image_studio_output_payload(paths)
    if not output["open_supported"]:
        raise HTTPException(status_code=501, detail="当前系统未找到可用的文件管理器")
    output_dir = Path(str(output["dir"]))
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(open_system_directory, output_dir)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"无法打开图片输出目录：{exc}") from exc
    return {**output, "opened": True}


@app.post("/api/image-studio/history/delete")
async def delete_image_studio_history(payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    requested = (payload or {}).get("items")
    if not isinstance(requested, list) or not requested:
        raise HTTPException(status_code=400, detail="请选择要删除的图片")

    paths = await active_comfy_paths()
    matches: list[tuple[str, tuple[str, str, str]]] = []
    errors: list[str] = []
    seen: set[tuple[str, str, str, str]] = set()
    with JOB_STORE_LOCK:
        for raw in requested[:500]:
            if not isinstance(raw, dict):
                continue
            job_id = str(raw.get("job_id") or "").strip()
            filename = str(raw.get("filename") or "").strip()
            subfolder = str(raw.get("subfolder") or "").strip()
            file_type = str(raw.get("type") or "output").strip() or "output"
            request_key = (job_id, filename, subfolder, file_type)
            if not job_id or not filename or request_key in seen:
                continue
            seen.add(request_key)
            job = JOBS.get(job_id)
            if not job or job.get("kind") != "image_generation":
                errors.append(f"{filename}: 任务记录不存在")
                continue
            if not job_is_terminal(job):
                errors.append(f"{filename}: 正在生成的任务不能从历史中删除，请先取消任务")
                continue
            media_key = (filename, subfolder, file_type)
            belongs_to_job = any(
                item.get("kind") == "image"
                and (
                    str(item.get("filename") or ""),
                    str(item.get("subfolder") or ""),
                    str(item.get("type") or "output"),
                )
                == media_key
                for item in job.get("media") or []
            )
            if not belongs_to_job:
                errors.append(f"{filename}: 图片不属于该任务")
                continue
            if file_type != "output":
                errors.append(f"{filename}: 只允许删除文生图输出文件")
                continue
            matches.append((job_id, media_key))

    removed_keys: dict[str, set[tuple[str, str, str]]] = {}
    deleted: list[str] = []
    for job_id, media_key in matches:
        filename, subfolder, file_type = media_key
        try:
            candidate = safe_media_path(filename, subfolder, file_type, paths)
            if not candidate.is_file():
                raise HTTPException(status_code=400, detail="目标不是文件")
            candidate.unlink()
            deleted.append(filename)
            removed_keys.setdefault(job_id, set()).add(media_key)
        except HTTPException as exc:
            if exc.status_code == 404:
                removed_keys.setdefault(job_id, set()).add(media_key)
                deleted.append(filename)
            else:
                errors.append(f"{filename}: {exc.detail}")
        except OSError as exc:
            errors.append(f"{filename}: {exc}")

    with JOB_STORE_LOCK:
        for job_id, keys in removed_keys.items():
            job = JOBS.get(job_id)
            if not job:
                continue
            job["media"] = [
                item
                for item in job.get("media") or []
                if (
                    str(item.get("filename") or ""),
                    str(item.get("subfolder") or ""),
                    str(item.get("type") or "output"),
                )
                not in keys
            ]
            if not any(item.get("kind") == "image" for item in job.get("media") or []):
                JOBS.pop(job_id, None)
    persist_job_stores(force=True)
    try:
        history_limit = int((payload or {}).get("limit") or 20)
    except (TypeError, ValueError):
        history_limit = 20
    return {
        "ok": not errors,
        "removed": sum(len(keys) for keys in removed_keys.values()),
        "deleted": deleted,
        "errors": errors,
        "history": image_studio_job_history(clamp_int(history_limit, 1, MAX_COMPLETED_JOBS)),
    }


@app.post("/api/image-studio/prompt-preview")
async def image_studio_prompt_preview(payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    profile_id = str(payload.get("profile") or "")
    try:
        source_adherence = float(payload.get("source_adherence") if payload.get("source_adherence") is not None else 0.65)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="原图遵循度必须是数字。") from exc
    if not math.isfinite(source_adherence):
        raise HTTPException(status_code=400, detail="原图遵循度必须是有效数字。")
    nsfw = bool(payload.get("nsfw") and (image_profile(profile_id).get("nsfw") or {}).get("toggle_enabled"))
    return build_effective_prompt(
        str(payload.get("prompt") or ""),
        prompt_mode=str(payload.get("prompt_mode") or "structured"),
        style_preset=str(payload.get("style_preset") or "photo"),
        exact_text=str(payload.get("exact_text") or ""),
        profile_id=profile_id,
        nsfw=nsfw,
        edit_mode=bool(payload.get("edit_mode")),
        source_adherence=source_adherence,
        auto_inject_trigger=bool(payload.get("auto_inject_trigger", True)),
        trigger_override=str(payload.get("custom_trigger") or ""),
        style_presets=merged_style_presets(),
    )


@app.get("/api/image-studio/workflow")
async def image_studio_workflow(
    profile: str = "qwen2512_lightning_fp8",
    width: int = 1664,
    height: int = 928,
    aspect: str = "landscape",
    steps: int = 4,
    cfg: float = 1.0,
    sampler: str = "euler",
    scheduler: str = "simple",
    batch_size: int = 1,
    edit_mode: bool = False,
    edit_strength: float = 0.35,
    source_adherence: float = -1.0,
    edit_resize_mode: str = "crop",
    reference_count: int = 0,
    nsfw: bool = False,
    nsfw_lora_strength: float = 1.0,
    include_graph: bool = False,
) -> dict[str, Any]:
    width, height, aspect = normalize_image_dimensions(width, height, aspect, profile)
    selected_profile = image_profile(profile)
    if not edit_mode and selected_profile.get("generation_supported") is False:
        raise HTTPException(status_code=400, detail=f"{selected_profile['label']} 仅支持已有图片微调")
    edit_capability = image_edit_capability(profile)
    if edit_mode and not edit_capability.get("supported"):
        raise HTTPException(status_code=400, detail=f"{image_profile(profile)['label']} 暂不支持已有图片微调")
    edit_controls = normalize_image_edit_controls(
        profile,
        source_adherence=source_adherence,
        edit_strength=edit_strength,
    )
    source_adherence = float(edit_controls["source_adherence"])
    edit_strength = float(edit_controls["edit_strength"])
    edit_resize_mode = "stretch" if edit_resize_mode == "stretch" else "crop"
    max_reference_images = int(edit_capability.get("max_reference_images") or 1)
    reference_count = max(0, min(max_reference_images - 1, int(reference_count))) if edit_mode else 0
    settings = normalized_generation_settings(
        profile,
        steps=steps,
        cfg=cfg,
        sampler=sampler,
        scheduler=scheduler,
        batch_size=batch_size,
    )
    graph = build_image_prompt(
        prompt=DEFAULT_IMAGE_PROMPT,
        negative=DEFAULT_IMAGE_NEGATIVE,
        width=width,
        height=height,
        seed=1,
        profile_id=str(settings["profile"]["id"]),
        steps=int(settings["steps"]),
        cfg=float(settings["cfg"]),
        sampler=str(settings["sampler"]),
        scheduler=str(settings["scheduler"]),
        batch_size=int(settings["batch_size"]),
        nsfw=nsfw,
        nsfw_lora_strength=nsfw_lora_strength,
        source_image=IMAGE_EDIT_SOURCE_PLACEHOLDER if edit_mode else "",
        reference_images=[f"__qwen_image_21_reference_{index + 2}__.png" for index in range(reference_count)],
        edit_strength=edit_strength,
        edit_resize_mode=edit_resize_mode,
    )
    object_info: dict[str, Any] | None = None
    object_error = ""
    try:
        object_info = await get_comfy_object_info()
        graph = resolve_graph_model_option_names(graph, object_info)
    except HTTPException as exc:
        object_error = comfy_connection_error_text(exc)
    errors = image_studio_graph_errors(graph, object_info)
    if object_error:
        errors.append(object_error)
    variant = settings["profile"].get("nsfw") or {}
    variant_label = variant.get("model_label") if nsfw and variant.get("toggle_enabled") else None
    result: dict[str, Any] = {
        "ok": not errors,
        "profile": settings["profile"]["id"],
        "label": variant_label or settings["profile"]["label"],
        "family": settings["profile"]["family"],
        "node_count": len(graph),
        "class_types": graph_class_types(graph),
        "output_nodes": [node_id for node_id, item in graph.items() if item.get("class_type") == "SaveImage"],
        "errors": list(dict.fromkeys(errors)),
        "parameters": {
            "width": width,
            "height": height,
            "aspect": aspect,
            "steps": settings["steps"],
            "cfg": settings["cfg"],
            "sampler": settings["sampler"],
            "scheduler": settings["scheduler"],
            "batch_size": settings["batch_size"],
            "nsfw": bool(nsfw and settings["profile"].get("nsfw", {}).get("toggle_enabled")),
            "edit_mode": bool(edit_mode),
            "edit_method": edit_capability.get("method") if edit_mode else "text_to_image",
            "edit_strength": edit_strength if edit_mode and edit_capability.get("strength_supported") else None,
            "source_adherence": source_adherence if edit_mode else None,
            "source_adherence_mode": edit_controls.get("adherence_mode") if edit_mode else None,
            "source_adherence_numeric": bool(edit_controls.get("numeric")) if edit_mode else None,
            "edit_resize_mode": edit_resize_mode if edit_mode and edit_capability.get("resize_supported") else None,
            "reference_count": reference_count if edit_mode else 0,
            "max_reference_images": max_reference_images if edit_mode else 0,
        },
        "message": (
            "图片微调 workflow 已创建并预检通过。"
            if edit_mode and not errors
            else "图片微调 workflow 预检未通过。"
            if edit_mode
            else "文生图 workflow 已创建并预检通过。"
            if not errors
            else "文生图 workflow 预检未通过。"
        ),
    }
    if include_graph:
        result["graph"] = graph
    return result


@app.post("/api/image-studio/generate")
async def image_studio_generate(
    prompt: str = Form(...),
    negative: str = Form(DEFAULT_IMAGE_NEGATIVE),
    prompt_mode: str = Form("structured"),
    style_preset: str = Form("photo"),
    exact_text: str = Form(""),
    profile: str = Form("qwen2512_lightning_fp8"),
    aspect: str = Form("landscape"),
    width: int = Form(1664),
    height: int = Form(928),
    steps: int = Form(4),
    cfg: float = Form(1.0),
    sampler: str = Form("euler"),
    scheduler: str = Form("simple"),
    batch_size: int = Form(1),
    generation_mode: str = Form("batch"),
    seed: str = Form("-1"),
    edit_mode: bool = Form(False),
    edit_operation: str = Form("instruction"),
    edit_strength: float = Form(0.35),
    source_adherence: float = Form(-1.0),
    edit_resize_mode: str = Form("crop"),
    source_image_filename: str = Form(""),
    source_image_subfolder: str = Form(""),
    source_image_type: str = Form(""),
    source_processing: str = Form("full"),
    face_authorization_confirmed: bool = Form(False),
    face_extract_id: str = Form(""),
    face_index: int = Form(-1),
    face_crop_mode: str = Form("face"),
    nsfw: bool = Form(False),
    nsfw_lora_strength: float = Form(1.0),
    auto_inject_trigger: bool = Form(True),
    auto_strip_negative: bool = Form(True),
    custom_trigger: str = Form(""),
    nsfw_intensity: str = Form(""),
    character_id: str = Form(""),
    secondary_lora_name: str = Form(""),
    secondary_lora_strength: float = Form(0.8),
    regional_face_prompt: str = Form(""),
    regional_body_prompt: str = Form(""),
    pose_map_filename: str = Form(""),
    controlnet_name: str = Form(""),
    controlnet_strength: float = Form(0.7),
    edit_strength_preset: str = Form(""),
    advanced_modules: str = Form(""),
    triple_compare: bool = Form(False),
    prompt_expand: bool = Form(False),
    face_authorization_token: str = Form(""),
    source_image: UploadFile | None = File(None),
    reference_images: list[UploadFile] | None = File(None),
) -> JSONResponse:
    regional_face_prompt = text_or_default(regional_face_prompt, "")
    regional_body_prompt = text_or_default(regional_body_prompt, "")
    pose_map_filename = text_or_default(pose_map_filename, "")
    controlnet_name = text_or_default(controlnet_name, "")
    secondary_lora_name = text_or_default(secondary_lora_name, "")
    edit_strength_preset = text_or_default(edit_strength_preset, "")
    advanced_modules = text_or_default(advanced_modules, "")
    custom_trigger = text_or_default(custom_trigger, "")
    nsfw_intensity = text_or_default(nsfw_intensity, "")
    character_id = text_or_default(character_id, "")
    triple_compare = triple_compare if isinstance(triple_compare, bool) else False
    prompt_expand = prompt_expand if isinstance(prompt_expand, bool) else False
    if edit_operation == "face_swap":
        raise HTTPException(status_code=400, detail="换脸任务请使用专用换脸提交接口。")
    source_prompt = (prompt or "").strip()
    if not source_prompt:
        raise HTTPException(status_code=400, detail="请输入画面描述")
    selected_profile = image_profile(profile)
    edit_capability = image_edit_capability(profile)
    reference_uploads = reference_images if isinstance(reference_images, (list, tuple)) else []
    uploaded_reference_images = [item for item in reference_uploads if item and item.filename]
    if not edit_mode and selected_profile.get("generation_supported") is False:
        raise HTTPException(status_code=400, detail=f"{selected_profile['label']} 仅支持已有图片微调")
    if edit_mode and not edit_capability.get("supported"):
        raise HTTPException(status_code=400, detail=f"{selected_profile['label']} 暂不支持已有图片微调")
    max_reference_images = int(edit_capability.get("max_reference_images") or 1)
    if uploaded_reference_images and not edit_mode:
        raise HTTPException(status_code=400, detail="附加参考图只能在图片微调模式中使用")
    if uploaded_reference_images and max_reference_images <= 1:
        raise HTTPException(status_code=400, detail=f"{selected_profile['label']} 暂不支持附加参考图")
    if len(uploaded_reference_images) > max_reference_images - 1:
        raise HTTPException(
            status_code=400,
            detail=f"当前模型最多支持 {max_reference_images} 张参考图（含 1 张目标图）",
        )
    source_processing = "face" if edit_mode and source_processing == "face" else "full"
    face_crop_mode = normalize_face_crop_mode(face_crop_mode)
    edit_controls = normalize_image_edit_controls(
        profile,
        source_adherence=source_adherence,
        edit_strength=edit_strength,
    )
    source_adherence = float(edit_controls["source_adherence"])
    edit_strength = float(edit_controls["edit_strength"])
    preset_key = str(edit_strength_preset or "").strip().lower()
    if preset_key and preset_key in EDIT_STRENGTH_PRESETS:
        edit_strength = float(EDIT_STRENGTH_PRESETS[preset_key])
    edit_resize_mode = "stretch" if edit_resize_mode == "stretch" else "crop"
    enabled_modules = parse_advanced_module_ids(advanced_modules)
    use_regional = bool(regional_face_prompt or regional_body_prompt) and (
        not enabled_modules or "regional_prompt" in enabled_modules
    )
    use_controlnet = bool(pose_map_filename and controlnet_name) and (
        not enabled_modules or "openpose_control" in enabled_modules
    )
    use_secondary_lora = bool(str(secondary_lora_name or "").strip()) and (
        not enabled_modules or "dual_lora" in enabled_modules
    )
    effective_prompt_source = source_prompt
    if prompt_expand:
        effective_prompt_source = expand_prompt_from_style(
            source_prompt,
            style_preset,
            style_map={item["id"]: item for item in merged_style_presets()},
        )
    requested_unrestricted = bool(nsfw and (selected_profile.get("nsfw") or {}).get("toggle_enabled"))
    width, height, aspect = normalize_image_dimensions(width, height, aspect, profile)
    prompt_data = build_effective_prompt(
        effective_prompt_source,
        prompt_mode=prompt_mode,
        style_preset=style_preset,
        exact_text=exact_text,
        profile_id=profile,
        nsfw=nsfw,
        edit_mode=bool(edit_mode),
        source_adherence=source_adherence,
        auto_inject_trigger=bool(auto_inject_trigger),
        trigger_override=str(custom_trigger or ""),
        style_presets=merged_style_presets(),
    )
    effective_negative = str(negative or DEFAULT_IMAGE_NEGATIVE).strip() or DEFAULT_IMAGE_NEGATIVE
    if requested_unrestricted and auto_strip_negative:
        _, effective_negative = apply_unrestricted_prompt_text(
            "",
            effective_negative,
            enabled=True,
            auto_inject_trigger=False,
            auto_strip_negative=True,
        )
    if (nsfw_intensity and requested_unrestricted and str(nsfw_intensity).strip()):
        mapped = intensity_strength(
            selected_profile.get("nsfw") or {},
            str(nsfw_intensity),
            current_nsfw_playbook(),
        )
        if mapped is not None:
            nsfw_lora_strength = float(mapped)
    requested_count = clamp_int(batch_size, 1, 20)
    profile_settings = normalized_generation_settings(
        profile,
        steps=steps,
        cfg=cfg,
        sampler=sampler,
        scheduler=scheduler,
        batch_size=1,
    )
    profile_max_batch = max(1, int(profile_settings["profile"].get("max_batch") or 1))
    requested_generation_mode = "sequential" if generation_mode == "sequential" else "batch"
    effective_generation_mode = (
        "sequential"
        if requested_generation_mode == "sequential" or requested_count > profile_max_batch
        else "batch"
    )
    graph_batch_size = 1 if effective_generation_mode == "sequential" else requested_count
    settings = normalized_generation_settings(
        profile,
        steps=steps,
        cfg=cfg,
        sampler=sampler,
        scheduler=scheduler,
        batch_size=graph_batch_size,
    )
    seed_value = normalize_seed(seed)
    comfy_paths = await active_comfy_paths()
    pose_map_name = ""
    if use_controlnet and pose_map_filename.strip():
        pose_map_name = copy_image_to_input(
            pose_map_filename.strip(),
            "",
            "input",
            comfy_paths,
        )
    face_auth_ok, face_auth_token_value = resolve_face_authorization(
        confirmed=face_authorization_confirmed,
        token=face_authorization_token,
        statement=FACE_AUTHORIZATION_STATEMENT,
    )
    source_image_name = ""
    source_image_payload: dict[str, Any] | None = None
    reference_image_names: list[str] = []
    reference_image_payloads: list[dict[str, Any]] = []
    selected_face: dict[str, Any] | None = None
    face_record: dict[str, Any] | None = None
    if edit_mode:
        if source_processing == "face":
            if not face_auth_ok:
                raise HTTPException(status_code=403, detail="面部参考微调前必须确认已取得照片中相关人员的明确授权。")
            if source_image and source_image.filename:
                raise HTTPException(status_code=400, detail="请先完成面部检测并选择一个候选面部，再提交微调任务。")
            if not face_extract_id or face_index < 0 or not source_image_filename:
                raise HTTPException(status_code=400, detail="请先提取并选择要使用的面部。")
            selected_face, face_record = validated_face_extraction_candidate(
                face_extract_id,
                face_index,
                source_image_filename,
                source_image_subfolder,
                source_image_type or "input",
            )
            if str(face_record.get("crop_mode") or "face") != face_crop_mode:
                raise HTTPException(status_code=400, detail="面部裁切范围已变化，请重新检测后再提交。")
            source_image_name = copy_image_to_input(
                source_image_filename,
                source_image_subfolder,
                source_image_type or "input",
                comfy_paths,
            )
            source_origin = "face_extract"
        elif source_image and source_image.filename:
            source_image_name = await save_upload(source_image, IMAGE_EXTENSIONS, comfy_paths)
            source_origin = "upload"
        elif source_image_filename:
            source_image_name = copy_image_to_input(
                source_image_filename,
                source_image_subfolder,
                source_image_type or "output",
                comfy_paths,
            )
            source_origin = "history"
        else:
            raise HTTPException(status_code=400, detail="图片微调需要上传一张源图片，或从最近生成中选择“微调”。")
        source_path = input_media_path(source_image_name, comfy_paths)
        source_relative = Path(source_image_name.replace("\\", "/"))
        source_item = {
            "filename": source_relative.name,
            "subfolder": source_relative.parent.as_posix() if source_relative.parent.as_posix() != "." else "",
            "type": "input",
        }
        source_image_payload = {
            **source_item,
            "url": media_url(source_item),
            "origin": source_origin,
            "input_name": source_image_name,
            "path": str(source_path),
            "processing": source_processing,
        }
        if selected_face is not None and face_record is not None:
            source_image_payload["face"] = {
                "extraction_id": face_extract_id,
                "index": int(selected_face["index"]),
                "label": selected_face.get("label"),
                "crop_mode": face_record.get("crop_mode"),
                "face_box": selected_face.get("face_box"),
                "crop_box": selected_face.get("crop_box"),
                "original": face_record.get("original"),
                "authorization_confirmed": True,
                "authorization_statement": FACE_AUTHORIZATION_STATEMENT,
                "local_detection": True,
                "identity_recognition": False,
            }
        for position, reference_upload in enumerate(uploaded_reference_images, start=2):
            reference_name = await save_upload(reference_upload, IMAGE_EXTENSIONS, comfy_paths)
            reference_path = input_media_path(reference_name, comfy_paths)
            reference_relative = Path(reference_name.replace("\\", "/"))
            reference_item = {
                "filename": reference_relative.name,
                "subfolder": reference_relative.parent.as_posix() if reference_relative.parent.as_posix() != "." else "",
                "type": "input",
            }
            reference_image_names.append(reference_name)
            reference_image_payloads.append(
                {
                    **reference_item,
                    "url": media_url(reference_item),
                    "input_name": reference_name,
                    "path": str(reference_path),
                    "position": position,
                    "prompt_token": f"<image{position}>",
                }
            )
    output_subdir = normalize_image_output_subdir(saved_image_output_subdir())
    output_dir = image_studio_output_dir(comfy_paths, output_subdir)
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"无法创建图片输出目录：{exc}") from exc
    try:
        object_info = await get_comfy_object_info()
    except HTTPException as exc:
        raise HTTPException(
            status_code=503,
            detail=comfy_not_connected_detail("提交图片微调 workflow" if edit_mode else "提交文生图 workflow", exc.detail),
        ) from exc
    graph_count = 3 if triple_compare else (requested_count if effective_generation_mode == "sequential" else 1)
    graphs: list[dict[str, Any]] = []
    prompt_seeds: list[int] = []
    for index in range(graph_count):
        prompt_seed = seed_value + index
        graph = build_image_prompt(
            prompt=prompt_data["effective"],
            negative=effective_negative,
            width=width,
            height=height,
            seed=prompt_seed,
            profile_id=str(settings["profile"]["id"]),
            steps=int(settings["steps"]),
            cfg=float(settings["cfg"]),
            sampler=str(settings["sampler"]),
            scheduler=str(settings["scheduler"]),
            batch_size=int(settings["batch_size"]),
            filename_prefix=image_studio_output_prefix(str(settings["profile"]["id"]), output_subdir),
            nsfw=bool(prompt_data["nsfw"]),
            nsfw_lora_strength=nsfw_lora_strength,
            secondary_lora_name=secondary_lora_name if use_secondary_lora else "",
            secondary_lora_strength=secondary_lora_strength,
            regional_face_prompt=regional_face_prompt if use_regional else "",
            regional_body_prompt=regional_body_prompt if use_regional else "",
            pose_map_filename=pose_map_name if use_controlnet else "",
            controlnet_name=controlnet_name if use_controlnet else "",
            controlnet_strength=controlnet_strength,
            source_image=source_image_name,
            reference_images=reference_image_names,
            edit_strength=edit_strength,
            edit_resize_mode=edit_resize_mode,
        )
        if "detailer" in enabled_modules:
            save_node = next(
                (
                    node_id
                    for node_id, item in graph.items()
                    if item.get("class_type") == "SaveImage"
                ),
                "",
            )
            image_ref = ((graph.get(save_node) or {}).get("inputs") or {}).get("images") if save_node else None
            if save_node and isinstance(image_ref, list) and image_ref:
                graph = apply_face_detailer(
                    graph,
                    object_info,
                    image_node=str(image_ref[0]),
                    save_node=save_node,
                )
        graph = resolve_graph_model_option_names(graph, object_info)
        errors = image_studio_graph_errors(graph, object_info)
        if errors:
            raise HTTPException(
                status_code=400,
                detail={"message": "图片微调工作流无效" if edit_mode else "文生图工作流无效", "errors": errors},
            )
        graphs.append(graph)
        prompt_seeds.append(prompt_seed)

    progress_stream_connected = await ensure_comfy_progress_listener()
    responses: list[dict[str, Any]] = []
    prompt_ids: list[str] = []
    for graph in graphs:
        response = await comfy_post("/prompt", {"prompt": graph, "client_id": CLIENT_ID})
        prompt_id = str(response.get("prompt_id") or "")
        if not prompt_id:
            raise HTTPException(status_code=500, detail=response)
        responses.append(response)
        prompt_ids.append(prompt_id)
    variant = settings["profile"].get("nsfw") or {}
    model_label = (
        variant.get("model_label") if prompt_data["nsfw"] and variant.get("toggle_enabled") else None
    ) or settings["profile"]["label"]
    job = {
        "id": uuid.uuid4().hex,
        "prompt_id": prompt_ids[0],
        "prompt_ids": prompt_ids,
        "prompt_seeds": prompt_seeds,
        "kind": "image_generation",
        "mode": "image_edit" if edit_mode else "image_t2i",
        "title": (
            f"{model_label} · 面部参考微调"
            if edit_mode and source_processing == "face"
            else f"{model_label} · 图片微调"
            if edit_mode
            else str(model_label)
        ),
        "status": "queued",
        "completed": False,
        "created_at": now_ms(),
        "seed": seed_value,
        "width": width,
        "height": height,
        "aspect": aspect,
        "steps": settings["steps"],
        "cfg": settings["cfg"],
        "sampler": settings["sampler"],
        "scheduler": settings["scheduler"],
        "batch_size": 3 if triple_compare else requested_count,
        "graph_batch_size": settings["batch_size"],
        "generation_mode": effective_generation_mode,
        "generation_mode_requested": requested_generation_mode,
        "generation_mode_adjusted": effective_generation_mode != requested_generation_mode,
        "prompt_mode": prompt_data["mode"],
        "style_preset": prompt_data["style_preset"],
        "style_label": prompt_data["style_label"],
        "source_prompt": prompt_data["source"],
        "effective_prompt": prompt_data["effective"],
        "exact_text": prompt_data["exact_text"],
        "negative": (negative or "").strip() or DEFAULT_IMAGE_NEGATIVE,
        "media": [],
        "raw": responses,
        "model_profile": settings["profile"]["id"],
        "model_family": settings["profile"]["family"],
        "model_label": model_label,
        "nsfw": bool(prompt_data["nsfw"]),
        "character_id": str(character_id or "").strip(),
        "edit_mode": bool(edit_mode),
        "edit_operation": "instruction" if edit_mode else "text_to_image",
        "edit_method": edit_capability.get("method") if edit_mode else "text_to_image",
        "edit_label": edit_capability.get("label") if edit_mode else "文字生成",
        "edit_strength": edit_strength if edit_mode and edit_capability.get("strength_supported") else None,
        "source_adherence": source_adherence if edit_mode else None,
        "source_adherence_mode": edit_controls.get("adherence_mode") if edit_mode else None,
        "source_adherence_numeric": bool(edit_controls.get("numeric")) if edit_mode else None,
        "edit_resize_mode": edit_resize_mode if edit_mode and edit_capability.get("resize_supported") else None,
        "source_processing": source_processing if edit_mode else "none",
        "face_authorization_confirmed": bool(face_auth_ok and edit_mode and source_processing == "face"),
        "face_authorization_token": face_auth_token_value if face_auth_ok else "",
        "face_extract_id": face_extract_id if edit_mode and source_processing == "face" else "",
        "face_index": face_index if edit_mode and source_processing == "face" else None,
        "face_crop_mode": face_crop_mode if edit_mode and source_processing == "face" else None,
        "triple_compare": bool(triple_compare),
        "prompt_expand": bool(prompt_expand),
        "advanced_modules": sorted(enabled_modules),
        "secondary_lora": {
            "name": secondary_lora_name if use_secondary_lora else "",
            "strength": secondary_lora_strength if use_secondary_lora else None,
        },
        "regional_prompts": {
            "face": regional_face_prompt if use_regional else "",
            "body": regional_body_prompt if use_regional else "",
        },
        "controlnet": {
            "name": controlnet_name if use_controlnet else "",
            "strength": controlnet_strength if use_controlnet else None,
            "pose_map": pose_map_name if use_controlnet else "",
        },
        "edit_strength_preset": preset_key or None,
        "source_image": source_image_payload,
        "reference_images": reference_image_payloads,
        "output_subdir": output_subdir,
        "output_dir": str(output_dir),
        "completed_prompt_ids": [],
        "failed_prompt_ids": [],
        "prompt_progress": {},
        "progress_stream_connected": progress_stream_connected,
    }
    job["progress"] = generation_progress_payload(job)
    store_generation_job(job)
    return JSONResponse(job)


@app.get("/api/video-params")
def video_param_schemas() -> dict[str, Any]:
    """按 mode 列出全部可调参数。

    /api/status 只有在 ComfyUI 连得上时才会下发完整的模型选项，但高级参数 schema
    本身只跟 mode 有关，所以单独开一个不依赖 ComfyUI 的端点，前端在任何情况下
    都能把面板渲染出来。
    """
    return {
        "groups": video_params.GROUP_LABELS,
        "modes": {mode: video_params.param_schema(mode) for mode in video_params.MODE_PARAMS},
        "capabilities": {mode: video_params.mode_capabilities(mode) for mode in video_params.MODE_CAPABILITIES},
        "end_image_modes": sorted(video_params.END_IMAGE_MODES),
    }


@app.get("/api/social-presets")
def social_preset_catalog() -> dict[str, Any]:
    """Return CPU-only publishing targets and model-native generation recipes."""
    return social_presets_payload()


@app.get("/api/workflow")
async def workflow_preview(
    mode: str = "",
    model_profile: str = "",
    model_label: str = "",
    width: int = 1280,
    height: int = 704,
    length: int = 81,
    fps: int = 24,
    seed: str = "1",
    steps: int = 4,
    cfg: float = 1.0,
    upscale_model: str = "RealESRGAN_x2plus.pth",
    upscale_scale: float = 2.0,
    rife_multiplier: int = 2,
    has_image: bool = False,
    has_end_image: bool = False,
    has_reference_media: bool = False,
    has_h3_control_video: bool = False,
    has_h3_source_video: bool = False,
    has_h3_mask: bool = False,
    h3_mask_is_video: bool = False,
    unrestricted: bool = False,
    adult_content_ack: bool = False,
    unrestricted_strength: float = 0.8,
    auto_inject_trigger: bool = True,
    auto_strip_negative: bool = True,
    custom_trigger: str = "",
    video_auto_inject_trigger: bool | None = None,
    video_auto_strip_negative: bool | None = None,
    video_custom_trigger: str | None = None,
    video_motion: str = "medium",
    advanced: str = "",
    social_target: str = "tiktok",
    social_quality: str = "balanced",
    include_graph: bool = False,
) -> dict[str, Any]:
    if video_auto_inject_trigger is not None:
        auto_inject_trigger = bool(video_auto_inject_trigger)
    if video_auto_strip_negative is not None:
        auto_strip_negative = bool(video_auto_strip_negative)
    if video_custom_trigger is not None and str(video_custom_trigger).strip():
        custom_trigger = str(video_custom_trigger)
    width = normalize_dimension(width, 2048)
    height = normalize_dimension(height, 2048)
    length = clamp_int(length, 9, MAX_VIDEO_FRAMES)
    fps = clamp_int(fps, 1, 60)
    seed_value = normalize_seed(seed)
    steps = clamp_int(steps, 1, 80)
    cfg = clamp_float(cfg, 0.1, 20.0)
    upscale_model = upscale_model if upscale_model in {*SEEDVR2_MODELS, "RealESRGAN_x2plus.pth", "4x-UltraSharp.pth"} else "RealESRGAN_x2plus.pth"
    upscale_scale = clamp_float(upscale_scale, 1.0, 4.0)
    rife_multiplier = clamp_int(rife_multiplier, 2, 4)
    unrestricted_strength = clamp_float(unrestricted_strength, 0.0, 1.2)
    resolved = resolve_workflow_profile(
        model_profile=model_profile,
        mode=mode,
        model_label=model_label,
        upscale_model=upscale_model,
        rife_multiplier=rife_multiplier,
    )
    mode = resolved["mode"]
    width, height = normalize_mode_dimensions(mode, width, height)
    unrestricted = bool(unrestricted and video_mode_allows_unrestricted(mode))
    upscale_model = resolved["upscale_model"]
    upscale_scale = clamp_float(resolved["scale"] if resolved["scale"] is not None else upscale_scale, 1.0, 4.0)
    rife_multiplier = resolved["rife_multiplier"]
    default_trigger = "nsfwsks" if mode == "i2v_a14b" else ""
    video_knobs = {
        "trigger": str(custom_trigger or default_trigger).strip(),
        "length": length,
        "cfg": cfg,
        "unrestricted_strength": unrestricted_strength,
    }
    if mode in {"ltx_i2v", "ltx_t2v"}:
        length = normalize_ltx_frames(length)
    elif mode in {"ltx23_t2v", "ltx23_i2v", "ltx25_t2v", "ltx25_i2v"}:
        length = normalize_ltx_frames(length)
        steps = clamp_int(steps, 5, 40)
    elif mode in {"minimax_h3_t2v", "minimax_h3_i2v", "minimax_h3_r2v"}:
        length = normalize_minimax_h3_frames(length)
        fps = 24
        steps = clamp_int(steps, 4, 40)
    elif mode in {"i2v_a14b", "t2v_a14b", "ti2v_5b", "hunyuan15_t2v", "hunyuan15_i2v"}:
        length = normalize_frames(length)

    if mode == "":
        return {
            "ok": True,
            "mode": mode,
            "profile": resolved["profile"],
            "label": resolved["label"],
            "local": False,
            "node_count": 0,
            "class_types": [],
            "output_nodes": [],
            "errors": [],
            "message": "当前步骤不需要创建 ComfyUI 视频工作流。",
        }
    if mode == "unsupported":
        return {
            "ok": False,
            "mode": mode,
            "profile": resolved["profile"],
            "label": resolved["label"] or "当前硬件不建议本地生视频",
            "local": False,
            "node_count": 0,
            "class_types": [],
            "output_nodes": [],
            "errors": ["当前环境属于后期处理路线：没有检测到适合本地视频生成的 CUDA 或 Apple Silicon MPS 后端。"],
            "message": "当前硬件不建议本地生视频。",
        }
    if mode == "external_workflow":
        detail = external_workflow_detail()
        return {
            "ok": False,
            "mode": mode,
            "profile": resolved["profile"],
            "label": resolved["label"],
            "local": False,
            "node_count": 0,
            "class_types": [],
            "output_nodes": [],
            "errors": detail["errors"] + detail["actions"],
            "message": detail["message"],
        }

    if mode == "deflicker":
        ffmpeg_tools = ffmpeg_tool_checks()
        ffmpeg_probe_item = ffmpeg_tools[0]
        filters_ok = all(item.get("ok") for item in ffmpeg_tools)
        errors = [item.get("message") or item["name"] for item in ffmpeg_tools if not item.get("ok")]
        return {
            "ok": bool(filters_ok),
            "mode": mode,
            "profile": resolved["profile"],
            "label": resolved["label"] or "ffmpeg deflicker + hqdn3d",
            "local": True,
            "node_count": 0,
            "class_types": [],
            "output_nodes": [],
            "errors": [] if filters_ok else errors,
            "tool": {"ffmpeg": ffmpeg_probe_item.get("path", ""), "source": ffmpeg_probe_item.get("source", ""), "filters_ok": filters_ok},
            "message": "本步骤使用本地 ffmpeg，不需要 ComfyUI 图。" if filters_ok else "本地 ffmpeg 预检未通过。",
        }

    social_recipe = resolve_social_recipe(
        mode=mode,
        target_id=social_target,
        quality_id=social_quality,
    )
    adv = video_params.resolve(mode, advanced)
    h3_errors = h3_workflows.requirement_errors(mode, adv, control=has_h3_control_video,
                                              source=has_h3_source_video, mask=has_h3_mask)
    if h3_errors:
        return {"ok": False, "mode": mode, "errors": h3_errors, "message": "H3 创作参数预检未通过。"}
    graph = build_preview_workflow_graph(
        mode=mode,
        model_profile=resolved["profile"],
        prompt=text_or_default("", DEFAULT_PROMPT),
        negative=text_or_default("", DEFAULT_NEGATIVE),
        width=width,
        height=height,
        length=length,
        fps=fps,
        seed=seed_value,
        steps=steps,
        cfg=cfg,
        upscale_model=upscale_model,
        upscale_scale=upscale_scale,
        rife_multiplier=rife_multiplier,
        has_image=has_image,
        has_end_image=bool(has_end_image and video_params.supports_end_image(mode)),
        has_reference_media=has_reference_media,
        unrestricted=unrestricted,
        unrestricted_strength=unrestricted_strength,
        trigger=str(video_knobs.get("trigger") or ""),
        auto_inject_trigger=bool(auto_inject_trigger),
        auto_strip_negative=bool(auto_strip_negative),
        adv=video_params.resolve(mode, advanced),
    )
    if graph is None:
        raise HTTPException(status_code=400, detail="未知模式，无法创建 ComfyUI 工作流")

    graph = h3_workflows.apply_extensions(
        graph, mode, adv, control_name="__h3_control.mp4" if has_h3_control_video else "",
        source_name="__h3_source.mp4" if has_h3_source_video else "",
        mask_name=("__h3_mask.mp4" if h3_mask_is_video else "__h3_mask.png") if has_h3_mask else "",
        mask_is_video=h3_mask_is_video,
    )

    comfy_paths = await active_comfy_paths()
    object_info: dict[str, Any] | None = None
    object_error = ""
    try:
        object_info = await get_comfy_object_info()
        graph = resolve_graph_model_option_names(graph, object_info)
    except HTTPException as exc:
        object_error = str(exc.detail)
    graph_errors = validate_graph(graph)
    availability = await comfy_node_availability(graph)
    model_errors = graph_model_registry_errors(graph, object_info)
    model_errors.extend(graph_node_schema_errors(graph, object_info))
    try:
        system_stats = await comfy_get("/system_stats")
    except HTTPException:
        system_stats = None
    risk_checks = workflow_risk_checks(
        mode=mode,
        hardware=build_hardware_summary(system_stats),
        width=width,
        height=height,
        length=length,
    )
    output_nodes = [
        node_id
        for node_id, item in graph.items()
        if item.get("class_type") in {"SaveVideo", "VHS_VideoCombine", "SaveImage"}
    ]
    errors = list(graph_errors)
    errors.extend(keyframe_requirement_errors(mode=mode, has_upload=has_image))
    if mode == "minimax_h3_r2v" and not has_reference_media:
        errors.append("MiniMax H3 多参考模式至少需要上传 1 个参考图片、视频或音频。")
    if unrestricted and not adult_content_ack:
        errors.append("开启成人内容模式前，请确认所有人物均为明确成年且自愿，并且你拥有素材与肖像授权。")
    errors.extend(model_errors)
    errors.extend(item["message"] for item in risk_checks if item.get("level") == "blocked")
    if availability["missing"]:
        errors.append(f"ComfyUI 缺少节点：{', '.join(availability['missing'])}")
    if availability["error"]:
        errors.append(availability["error"])
    if object_error and object_error not in errors:
        errors.append(object_error)
    response: dict[str, Any] = {
        "ok": not errors,
        "mode": mode,
        "profile": resolved["profile"],
        "label": resolved["label"],
        "local": False,
        "node_count": len(graph),
        "class_types": graph_class_types(graph),
        "output_nodes": output_nodes,
        "errors": errors,
        "risk_checks": risk_checks,
        "comfy": availability,
        "parameters": {
            "width": width,
            "height": height,
            "length": length,
            "fps": fps,
            "steps": steps,
            "cfg": cfg,
            "upscale_model": upscale_model,
            "rife_multiplier": rife_multiplier,
            "unrestricted": unrestricted,
            "unrestricted_strength": unrestricted_strength,
            "adult_content_ack": bool(adult_content_ack),
            "social_target": social_recipe["target_id"],
            "social_quality": social_recipe["quality_id"],
        },
        "social_recipe": social_recipe,
        "message": "ComfyUI workflow 已创建并预检通过。" if not errors else "ComfyUI workflow 预检未通过。",
    }
    if mode in {"minimax_h3_t2v", "minimax_h3_i2v", "minimax_h3_r2v"}:
        runtime = minimax_h3_runtime_settings(video_params.resolve(mode, advanced), steps)
        response["parameters"]["steps"] = runtime["steps"]
        response["parameters"]["h3_runtime"] = runtime
        response["parameters"]["h3_task"] = adv["h3_task"]
        response["parameters"]["h3_attention_backend"] = adv["h3_attention_backend"]
        if adv["h3_latent_upscale"]:
            response["parameters"]["h3_upscale"] = h3_workflows.dimensions(width, height, adv["h3_upscale_factor"])
    if include_graph:
        response["graph"] = graph
    return response


@app.post("/api/video-smoke-test")
async def video_smoke_test(payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    try:
        system_stats = await comfy_get("/system_stats")
        object_info = await get_comfy_object_info()
    except HTTPException as exc:
        raise HTTPException(status_code=503, detail=comfy_not_connected_detail("运行生成链路测试", exc.detail)) from exc

    comfy_paths = comfy_paths_from_system_stats(system_stats)
    active_base_dir = Path(comfy_paths["base_dir"])
    os_info = {
        "name": platform.system(),
        "release": os_release_label(),
        "version": platform.version(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python": sys.version.split()[0],
        "python_executable": sys.executable,
    }
    hardware = build_hardware_summary(system_stats)
    assets = collect_runtime_asset_checks(active_base_dir)
    custom_nodes = collect_custom_node_checks(active_base_dir)
    tool_checks = ffmpeg_tool_checks()
    node_checks = collect_node_checks(object_info)
    model_options = workflow_model_options(
        os_info=os_info,
        hardware=hardware,
        assets=assets,
        custom_nodes=custom_nodes,
        tool_checks=tool_checks,
        node_checks=node_checks,
        base_dir=active_base_dir,
    )
    option = choose_video_smoke_option(model_options)
    if not option:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "没有可用于生成链路测试的视频模型",
                "errors": [
                    "请先在环境侦测里安装推荐档位，并确认 ComfyUI 已重启加载节点和模型。",
                    "无 CUDA/MPS 的后期路线不会运行本地视频生成测试。",
                ],
            },
        )

    mode = str(option["mode"])
    params = video_smoke_parameters(option)
    smoke_seed = normalize_seed(payload.get("seed"))
    graph = build_preview_workflow_graph(
        mode=mode,
        model_profile=str(option.get("id") or ""),
        prompt=SMOKE_TEST_PROMPT,
        negative=DEFAULT_NEGATIVE,
        width=params["width"],
        height=params["height"],
        length=params["length"],
        fps=params["fps"],
        seed=smoke_seed,
        steps=params["steps"],
        cfg=params["cfg"],
        upscale_model="RealESRGAN_x2plus.pth",
        rife_multiplier=2,
    )
    if graph is None:
        raise HTTPException(status_code=400, detail="无法创建生成链路测试 workflow")

    graph = resolve_graph_model_option_names(graph, object_info)
    graph_errors = validate_graph(graph)
    graph_errors.extend(graph_model_registry_errors(graph, object_info))
    graph_errors.extend(graph_node_schema_errors(graph, object_info))
    missing_nodes = [name for name in graph_class_types(graph) if name not in object_info]
    if missing_nodes:
        graph_errors.append(f"ComfyUI 缺少节点：{', '.join(missing_nodes)}")
    graph_errors.extend(
        item["message"]
        for item in workflow_risk_checks(mode=mode, hardware=hardware, width=params["width"], height=params["height"], length=params["length"])
        if item.get("level") == "blocked"
    )
    if graph_errors:
        raise HTTPException(status_code=400, detail={"message": "生成链路测试预检未通过", "errors": graph_errors})

    job_id = uuid.uuid4().hex
    created_at = now_ms()
    title = f"生成链路测试 - {option.get('label') or option.get('model_label') or mode}"
    progress_stream_connected = await ensure_comfy_progress_listener()
    await reconcile_heavy_generation_jobs_before_submit()
    reserve_generation_job_slot(
        job_id=job_id,
        kind="video_smoke_test",
        mode=mode,
        title=title,
        created_at=created_at,
    )
    try:
        response = await comfy_post("/prompt", {"prompt": graph, "client_id": CLIENT_ID})
        prompt_id = str(response.get("prompt_id") or "")
        if not prompt_id:
            raise HTTPException(status_code=500, detail=response)
    except Exception as exc:
        fail_generation_job_slot(job_id, f"提交到 ComfyUI 失败：{exc}")
        raise

    job = {
        "id": job_id,
        "prompt_id": prompt_id,
        "prompt_ids": [prompt_id],
        "kind": "video_smoke_test",
        "mode": mode,
        "title": title,
        "status": "queued",
        "completed": False,
        "created_at": created_at,
        "seed": smoke_seed,
        "width": params["width"],
        "height": params["height"],
        "length": params["length"],
        "fps": params["fps"],
        "media": [],
        "raw": response,
        "model_profile": option.get("id"),
        "smoke_test": True,
        "parameters": params,
        "prompt_progress": {},
        "progress_stream_connected": progress_stream_connected,
    }
    job["progress"] = generation_progress_payload(job)
    return finalize_generation_job_slot(job)


@app.post("/api/generate")
async def generate(
    mode: str = Form(...),
    prompt: str = Form(""),
    negative: str = Form(""),
    width: int = Form(1280),
    height: int = Form(704),
    length: int = Form(81),
    fps: int = Form(24),
    seed: str = Form("-1"),
    steps: int = Form(4),
    cfg: float = Form(1.0),
    model_label: str = Form(""),
    model_profile: str = Form(""),
    upscale_model: str = Form("RealESRGAN_x2plus.pth"),
    upscale_scale: float = Form(2.0),
    rife_multiplier: int = Form(2),
    source_video_filename: str = Form(""),
    source_video_subfolder: str = Form(""),
    source_video_type: str = Form(""),
    source_image_filename: str = Form(""),
    unrestricted: bool = Form(False),
    adult_content_ack: bool = Form(False),
    unrestricted_strength: float = Form(0.8),
    video_auto_inject_trigger: bool = Form(True),
    video_auto_strip_negative: bool = Form(True),
    video_custom_trigger: str = Form(""),
    video_motion: str = Form("medium"),
    motion_lora_high: str = Form(""),
    motion_lora_low: str = Form(""),
    video_motion_lora_pack: str = Form(""),
    temporal_stability: bool = Form(True),
    social_target: str = Form("tiktok"),
    social_quality: str = Form("balanced"),
    character_id: str = Form(""),
    project: str = Form(""),
    # 高级参数走一个 JSON 串，新增引擎只要往 video_params 里加条目，不用改这里的签名。
    advanced: str = Form(""),
    image: UploadFile | None = File(None),
    end_image: UploadFile | None = File(None),
    video: UploadFile | None = File(None),
    clips: list[UploadFile] | None = File(None),
    reference_media: list[UploadFile] | None = File(None),
    h3_control_video: UploadFile | None = File(None),
    h3_source_video: UploadFile | None = File(None),
    h3_mask: UploadFile | None = File(None),
) -> JSONResponse:
    project_tag = sanitize_project_tag(project)
    CURRENT_PROJECT_TAG.set(project_tag)
    prompt_text = text_or_default(prompt, DEFAULT_PROMPT)
    negative_text = text_or_default(negative, DEFAULT_NEGATIVE)
    width = normalize_dimension(width, 2048)
    height = normalize_dimension(height, 2048)
    length = clamp_int(length, 9, MAX_VIDEO_FRAMES)
    fps = clamp_int(fps, 1, 60)
    seed_value = normalize_seed(seed)
    steps = clamp_int(steps, 1, 80)
    cfg = clamp_float(cfg, 0.1, 20.0)
    selected_label = clean_label(model_label)
    upscale_model = upscale_model if upscale_model in {*SEEDVR2_MODELS, "RealESRGAN_x2plus.pth", "4x-UltraSharp.pth"} else "RealESRGAN_x2plus.pth"
    upscale_scale = clamp_float(upscale_scale, 1.0, 4.0)
    rife_multiplier = clamp_int(rife_multiplier, 2, 4)
    unrestricted_strength = clamp_float(unrestricted_strength, 0.0, 1.2)
    resolved = resolve_workflow_profile(
        model_profile=model_profile,
        mode=mode,
        model_label=selected_label,
        upscale_model=upscale_model,
        rife_multiplier=rife_multiplier,
    )
    motion_high, motion_low = resolve_motion_lora_names(
        motion_lora_high=motion_lora_high,
        motion_lora_low=motion_lora_low,
        pack_id=video_motion_lora_pack,
        config=read_local_config(),
    )
    mode = resolved["mode"]
    width, height = normalize_mode_dimensions(mode, width, height)
    unrestricted = bool(unrestricted and video_mode_allows_unrestricted(mode))
    if unrestricted and not adult_content_ack:
        raise HTTPException(
            status_code=400,
            detail=(
                "开启成人内容模式前，请确认所有人物均为明确成年且自愿，"
                "且你拥有参考素材与肖像使用授权。"
            ),
        )
    social_recipe = resolve_social_recipe(
        mode=mode,
        target_id=social_target,
        quality_id=social_quality,
    )
    selected_label = resolved["label"]
    upscale_model = resolved["upscale_model"]
    upscale_scale = clamp_float(resolved["scale"] if resolved["scale"] is not None else upscale_scale, 1.0, 4.0)
    rife_multiplier = clamp_int(resolved["rife_multiplier"], 2, 4)
    default_trigger = "nsfwsks" if mode == "i2v_a14b" else ""
    # length/cfg/prompt motion linkage is applied client-side to avoid double scaling;
    # server uses the submitted knobs plus trigger/strip options.
    video_knobs = {
        "trigger": str(video_custom_trigger or default_trigger).strip(),
        "motion_id": str(video_motion or "medium"),
        "length": length,
        "cfg": cfg,
        "unrestricted_strength": unrestricted_strength,
    }
    if mode in {"ltx_i2v", "ltx_t2v"}:
        length = normalize_ltx_frames(length)
    elif mode in {"ltx23_t2v", "ltx23_i2v", "ltx25_t2v", "ltx25_i2v"}:
        length = normalize_ltx_frames(length)
        steps = clamp_int(steps, 5, 40)
    elif mode in {"minimax_h3_t2v", "minimax_h3_i2v", "minimax_h3_r2v"}:
        length = normalize_minimax_h3_frames(length)
        fps = 24
        steps = clamp_int(steps, 4, 40)
    elif mode in {"fal_h3_max_t2v", "fal_h3_max_i2v"}:
        length = clamp_int(length, 120, 360)
        fps = 24
    elif mode in {"i2v_a14b", "t2v_a14b", "ti2v_5b", "hunyuan15_t2v", "hunyuan15_i2v"}:
        length = normalize_frames(length)
    adv = video_params.resolve(mode, advanced)
    h3_errors = h3_workflows.requirement_errors(
        mode, adv, control=bool(h3_control_video and h3_control_video.filename),
        source=bool(h3_source_video and h3_source_video.filename), mask=bool(h3_mask and h3_mask.filename),
    )
    if h3_errors:
        raise HTTPException(status_code=400, detail={"message": "H3 创作参数无效", "errors": h3_errors})
    if mode == "unsupported":
        raise HTTPException(
            status_code=400,
            detail={
                "message": "当前硬件不建议本地生视频",
                "errors": ["可以上传已有视频继续做去闪烁、插帧和清晰度增强，或换 CUDA / Apple Silicon MPS 环境后再生成。"],
            },
        )
    if mode == "external_workflow":
        raise HTTPException(status_code=400, detail=external_workflow_detail())

    if mode in {"fal_h3_max_t2v", "fal_h3_max_i2v"}:
        fal_auth_headers()
        explicit_prompt = str(prompt or "").strip()
        if not explicit_prompt:
            raise HTTPException(status_code=400, detail="请填写 H3 Max 视频提示词；云端计费任务不会使用内置示例词代替。")
        request_payload: dict[str, Any] = {
            "prompt": explicit_prompt,
            "duration": fal_h3_max_duration(length, 24),
            "resolution": fal_h3_max_resolution(width, height),
            "seed": seed_value,
            "enable_safety_checker": bool(adv["fal_safety_checker"]),
            "prompt_expansion_mode": str(adv["fal_prompt_expansion_mode"]),
        }
        endpoint = FAL_H3_MAX_T2V_ENDPOINT
        if mode == "fal_h3_max_t2v":
            request_payload["aspect_ratio"] = closest_fal_aspect_ratio(width, height)
        else:
            if image and image.filename:
                request_payload["image_url"] = await fal_upload_data_uri(image)
            elif source_image_filename.strip():
                linked_path = input_media_path(source_image_filename.strip(), configured_comfy_paths())
                if linked_path.suffix.lower() not in IMAGE_EXTENSIONS:
                    raise HTTPException(status_code=400, detail="H3 Max 首帧不是支持的图片格式")
                request_payload["image_url"] = fal_path_data_uri(linked_path)
            else:
                raise HTTPException(status_code=400, detail="H3 Max 图生视频需要上传首帧，或切换到文字生视频。")
            if end_image and end_image.filename:
                request_payload["end_image_url"] = await fal_upload_data_uri(end_image)
            endpoint = FAL_H3_MAX_I2V_ENDPOINT

        response = await fal_queue_submit(endpoint, request_payload)
        job_id = uuid.uuid4().hex
        output_relative = f"{output_prefix('Fal_H3_Max')}.mp4"
        job = {
            "id": job_id,
            "prompt_id": None,
            "prompt_ids": [],
            "provider": "fal",
            "kind": "video_generation",
            "mode": mode,
            "title": selected_label or (
                "H3 Max（fal）首帧 / 首尾帧音视频"
                if mode == "fal_h3_max_i2v"
                else "H3 Max（fal）文字生音视频"
            ),
            "status": "queued",
            "completed": False,
            "created_at": now_ms(),
            "seed": seed_value,
            "width": width,
            "height": height,
            "length": length,
            "duration": request_payload["duration"],
            "fps": 24,
            "media": [],
            "fal_endpoint": endpoint,
            "fal_request_id": response["request_id"],
            "fal_status_url": response["status_url"],
            "fal_response_url": response["response_url"],
            "fal_cancel_url": response["cancel_url"],
            "output_relative_path": output_relative,
            "raw": {
                "request_id": response["request_id"],
                "endpoint": endpoint,
                "resolution": request_payload["resolution"],
                "duration": request_payload["duration"],
                "aspect_ratio": request_payload.get("aspect_ratio"),
                "has_first_frame": bool(request_payload.get("image_url")),
                "has_last_frame": bool(request_payload.get("end_image_url")),
            },
            "model_profile": resolved["profile"],
            "advanced": dict(adv),
            "advanced_overrides": video_params.non_default_items(mode, adv),
            "project": project_tag,
            "source_prompt": explicit_prompt,
            "social_target": social_recipe["target_id"],
            "social_quality": social_recipe["quality_id"],
            "delivery_target": social_recipe["delivery"],
            "safe_zone": social_recipe["safe_zone"],
            "uses_comfyui": False,
            "uses_local_gpu": False,
        }
        job["progress"] = {
            "percent": 0.0,
            "label": "已提交到 fal，等待云端开始",
            "source": "fal_queue",
            "accurate": False,
        }
        store_generation_job(job)
        return JSONResponse(job)

    # Only local generation and post-processing need to discover ComfyUI paths.
    # The fal route above exits before this line and therefore never touches ComfyUI.
    comfy_paths = await active_comfy_paths()
    h3_inputs = await prepare_h3_uploads(mode, adv, length, comfy_paths, h3_control_video, h3_source_video, h3_mask)

    if mode == "stitch":
        sources: list[Path] = []
        if source_video_filename:
            sources.append(
                safe_media_path(
                    source_video_filename,
                    source_video_subfolder,
                    source_video_type or "output",
                    comfy_paths,
                )
            )
        for clip in clips or []:
            if not clip.filename:
                continue
            clip_name = await save_upload(clip, VIDEO_EXTENSIONS, comfy_paths)
            sources.append(input_media_path(clip_name, comfy_paths))
        if video and video.filename:
            video_name = await save_upload(video, VIDEO_EXTENSIONS, comfy_paths)
            sources.append(input_media_path(video_name, comfy_paths))

        job_id = uuid.uuid4().hex
        job = {
            "id": job_id,
            "prompt_id": None,
            "kind": "video_postprocess",
            "mode": mode,
            "title": "多镜头顺序拼接",
            "status": "queued",
            "completed": False,
            "local": True,
            "created_at": now_ms(),
            "progress": {
                "percent": 0.0,
                "label": "等待本地处理线程",
                "source": "local_queue",
                "accurate": False,
            },
            "status_note": "等待本地处理线程",
            "width": width,
            "height": height,
            "fps": fps,
            "clip_count": len(sources),
            "media": [],
            "raw": {"processor": "ffmpeg", "operation": "concat", "clip_count": len(sources)},
            "model_profile": "ffmpeg_stitch",
            "project": project_tag,
        }
        queue_local_video_job(
            job,
            operation="stitch",
            kwargs={
                "sources": sources,
                "width": width,
                "height": height,
                "fps": fps,
                "paths": comfy_paths,
                "project": project_tag,
            },
        )
        return JSONResponse(job)

    reference_image_names: list[str] = []
    reference_video_names: list[str] = []
    reference_audio_names: list[str] = []
    if mode == "minimax_h3_r2v":
        for upload in reference_media or []:
            if not upload.filename:
                continue
            suffix = Path(upload.filename).suffix.lower()
            if suffix in IMAGE_EXTENSIONS:
                if len(reference_image_names) >= 9:
                    raise HTTPException(status_code=400, detail="H3 多参考最多上传 9 张参考图片。")
                reference_image_names.append(await save_upload(upload, IMAGE_EXTENSIONS, comfy_paths))
            elif suffix in VIDEO_EXTENSIONS:
                if len(reference_video_names) >= 3:
                    raise HTTPException(status_code=400, detail="H3 多参考最多上传 3 段参考视频。")
                reference_video_names.append(await save_upload(upload, VIDEO_EXTENSIONS, comfy_paths))
            elif suffix in AUDIO_EXTENSIONS:
                if len(reference_audio_names) >= 3:
                    raise HTTPException(status_code=400, detail="H3 多参考最多上传 3 条参考音频。")
                reference_audio_names.append(await save_upload(upload, AUDIO_EXTENSIONS, comfy_paths))
            else:
                raise HTTPException(status_code=400, detail=f"不支持的参考素材格式：{suffix or '无扩展名'}")
        if not (reference_image_names or reference_video_names or reference_audio_names):
            raise HTTPException(
                status_code=400,
                detail="MiniMax H3 多参考模式至少需要上传 1 个参考图片、视频或音频。",
            )

    linked_image_name = source_image_filename.strip().replace("\\", "/")
    has_linked_image = bool(linked_image_name)
    if mode in REQUIRED_IMAGE_WORKFLOW_MODES:
        keyframe_errors = keyframe_requirement_errors(
            mode=mode,
            has_upload=bool((image and image.filename) or has_linked_image),
        )
        if keyframe_errors:
            raise HTTPException(status_code=400, detail={"message": "当前模型需要关键帧", "errors": keyframe_errors})
        if image and image.filename:
            image_name = await save_upload(image, IMAGE_EXTENSIONS, comfy_paths)
        else:
            linked_path = input_media_path(linked_image_name, comfy_paths)
            if linked_path.suffix.lower() not in IMAGE_EXTENSIONS:
                raise HTTPException(status_code=400, detail="文生图交接文件不是支持的关键帧图片")
            image_name = linked_image_name
    elif mode == "ti2v_5b" and image and image.filename:
        image_name = await save_upload(image, IMAGE_EXTENSIONS, comfy_paths)
    elif mode == "ti2v_5b" and has_linked_image:
        linked_path = input_media_path(linked_image_name, comfy_paths)
        if linked_path.suffix.lower() not in IMAGE_EXTENSIONS:
            raise HTTPException(status_code=400, detail="文生图交接文件不是支持的关键帧图片")
        image_name = linked_image_name
    else:
        image_name = ""

    # Wan A14B 与 MiniMax H3 FL2VA 支持尾帧；TI2V-5B 不支持。
    end_image_name = ""
    if video_params.supports_end_image(mode) and end_image and end_image.filename:
        end_image_name = await save_upload(end_image, IMAGE_EXTENSIONS, comfy_paths)

    if mode in VIDEO_GENERATION_MODES and not prompt_text:
        raise HTTPException(status_code=400, detail="请填写视频画面与镜头提示词；平台不会再自动注入任何场景。")
    if mode in VIDEO_GENERATION_MODES and temporal_stability:
        negative_text = append_consistency_negative(negative_text, enabled=True)

    if mode == "i2v_a14b":
        graph = build_a14b_i2v_prompt(
            prompt=prompt_text,
            negative=negative_text,
            image_name=image_name,
            end_image_name=end_image_name,
            width=width,
            height=height,
            length=length,
            fps=fps,
            seed=seed_value,
            steps=steps,
            cfg=cfg,
            unrestricted=unrestricted,
            unrestricted_strength=unrestricted_strength,
            trigger=str(video_knobs.get("trigger") or "nsfwsks"),
            auto_inject_trigger=bool(video_auto_inject_trigger),
            auto_strip_negative=bool(video_auto_strip_negative),
            motion_lora_high=motion_high,
            motion_lora_low=motion_low,
            adv=adv,
        )
        title = selected_label or "I2V A14B 视频生成"
    elif mode == "t2v_a14b":
        graph = build_a14b_t2v_prompt(
            prompt=prompt_text,
            negative=negative_text,
            width=width,
            height=height,
            length=length,
            fps=fps,
            seed=seed_value,
            steps=steps,
            cfg=cfg,
            unrestricted=unrestricted,
            unrestricted_strength=unrestricted_strength,
            trigger=str(video_knobs.get("trigger") or ""),
            auto_inject_trigger=bool(video_auto_inject_trigger),
            auto_strip_negative=bool(video_auto_strip_negative),
            motion_lora_high=motion_high,
            motion_lora_low=motion_low,
            adv=adv,
        )
        title = selected_label or "T2V A14B 文生视频"
    elif mode == "ti2v_5b":
        graph = build_ti2v_prompt(
            prompt=prompt_text,
            negative=negative_text,
            image_name=image_name,
            width=width,
            height=height,
            length=length,
            fps=fps,
            seed=seed_value,
            steps=steps,
            cfg=cfg,
            adv=adv,
        )
        title = selected_label or "TI2V 5B 视频生成"
    elif mode == "ltx_i2v":
        graph = build_ltx_i2v_prompt(
            prompt=prompt_text,
            negative=negative_text,
            image_name=image_name,
            width=width,
            height=height,
            length=length,
            fps=fps,
            seed=seed_value,
            steps=steps,
            cfg=cfg,
            adv=adv,
        )
        title = selected_label or "LTXV 0.9.8 I2V"
    elif mode == "ltx_t2v":
        graph = build_ltx_t2v_prompt(
            prompt=prompt_text,
            negative=negative_text,
            width=width,
            height=height,
            length=length,
            fps=fps,
            seed=seed_value,
            steps=steps,
            cfg=cfg,
            adv=adv,
        )
        title = selected_label or "LTXV 0.9.8 T2V"
    elif mode == "ltx23_t2v":
        graph = build_ltx23_t2v_prompt(
            prompt=prompt_text,
            negative=negative_text,
            width=width,
            height=height,
            length=length,
            fps=fps,
            seed=seed_value,
            steps=steps,
            cfg=cfg,
            checkpoint_name=resolved["checkpoint"] or LTX23_DEV_CHECKPOINT,
            adv=adv,
        )
        title = selected_label or "LTX-Video 2.3 22B Dev T2V"
    elif mode == "ltx23_i2v":
        graph = build_ltx23_i2v_prompt(
            prompt=prompt_text,
            negative=negative_text,
            image_name=image_name,
            width=width,
            height=height,
            length=length,
            fps=fps,
            seed=seed_value,
            steps=steps,
            cfg=cfg,
            checkpoint_name=resolved["checkpoint"] or LTX23_DEV_CHECKPOINT,
            adv=adv,
        )
        title = selected_label or "LTX-Video 2.3 22B Dev I2V"
    elif mode == "ltx25_t2v":
        graph = build_ltx25_t2v_prompt(
            prompt=prompt_text,
            negative=negative_text,
            width=width,
            height=height,
            length=length,
            fps=fps,
            seed=seed_value,
            steps=steps,
            cfg=cfg,
            model_name=resolved["model_name"] or LTX25_DISTILLED_INT8_MODEL,
            text_encoder_name=resolved["text_encoder"] or LTX25_TEXT_ENCODER,
            video_vae_diff_name=resolved["video_vae_diff"] or LTX25_VIDEO_VAE_DIFF,
            video_vae_conv_name=resolved["video_vae_conv"] or LTX25_VIDEO_VAE_CONV,
            audio_vae_name=resolved["audio_vae"] or LTX25_AUDIO_VAE,
            spatial_upscaler_name=resolved["spatial_upscaler"] or LTX25_SPATIAL_UPSCALER,
            duration_head_name=resolved["duration_head"] or LTX25_DURATION_HEAD,
            adv=adv,
            unrestricted=unrestricted,
            trigger=str(video_knobs.get("trigger") or ""),
            auto_inject_trigger=bool(video_auto_inject_trigger),
            auto_strip_negative=bool(video_auto_strip_negative),
        )
        title = selected_label or "LTX-Video 2.5 22B Distilled T2V"
    elif mode == "ltx25_i2v":
        graph = build_ltx25_i2v_prompt(
            prompt=prompt_text,
            negative=negative_text,
            image_name=image_name,
            end_image_name=end_image_name,
            width=width,
            height=height,
            length=length,
            fps=fps,
            seed=seed_value,
            steps=steps,
            cfg=cfg,
            model_name=resolved["model_name"] or LTX25_DISTILLED_INT8_MODEL,
            text_encoder_name=resolved["text_encoder"] or LTX25_TEXT_ENCODER,
            video_vae_diff_name=resolved["video_vae_diff"] or LTX25_VIDEO_VAE_DIFF,
            video_vae_conv_name=resolved["video_vae_conv"] or LTX25_VIDEO_VAE_CONV,
            audio_vae_name=resolved["audio_vae"] or LTX25_AUDIO_VAE,
            spatial_upscaler_name=resolved["spatial_upscaler"] or LTX25_SPATIAL_UPSCALER,
            duration_head_name=resolved["duration_head"] or LTX25_DURATION_HEAD,
            adv=adv,
            unrestricted=unrestricted,
            trigger=str(video_knobs.get("trigger") or ""),
            auto_inject_trigger=bool(video_auto_inject_trigger),
            auto_strip_negative=bool(video_auto_strip_negative),
        )
        title = selected_label or ("LTX-Video 2.5 首尾帧" if end_image_name else "LTX-Video 2.5 I2V")
    elif mode in {"hunyuan15_t2v", "hunyuan15_i2v"}:
        default_model = HUNYUAN15_I2V_480_MODEL if mode == "hunyuan15_i2v" else HUNYUAN15_T2V_480_MODEL
        graph = build_hunyuan15_prompt(
            prompt=prompt_text,
            negative=negative_text,
            image_name=image_name if mode == "hunyuan15_i2v" else "",
            width=width,
            height=height,
            length=length,
            fps=fps,
            seed=seed_value,
            steps=steps,
            cfg=cfg,
            model_name=resolved["model_name"] or default_model,
            distilled=bool(resolved["distilled"]),
            adv=adv,
        )
        title = selected_label or ("HunyuanVideo 1.5 I2V" if mode == "hunyuan15_i2v" else "HunyuanVideo 1.5 T2V")
    elif mode == "minimax_h3_r2v":
        graph = build_minimax_h3_reference_prompt(
            prompt=prompt_text,
            negative=negative_text,
            reference_images=reference_image_names,
            reference_videos=reference_video_names,
            reference_audios=reference_audio_names,
            width=width,
            height=height,
            length=length,
            fps=24,
            seed=seed_value,
            steps=steps,
            cfg=cfg,
            adv=adv,
            unrestricted=unrestricted,
            trigger=str(video_knobs.get("trigger") or ""),
            auto_inject_trigger=bool(video_auto_inject_trigger),
            auto_strip_negative=bool(video_auto_strip_negative),
        )
        title = selected_label or "MiniMax H3 Ref2VA 多参考音视频"
    elif mode in {"minimax_h3_t2v", "minimax_h3_i2v"}:
        graph = build_minimax_h3_prompt(
            prompt=prompt_text,
            negative=negative_text,
            image_name=image_name if mode == "minimax_h3_i2v" else "",
            end_image_name=end_image_name if mode == "minimax_h3_i2v" else "",
            width=width,
            height=height,
            length=length,
            fps=24,
            seed=seed_value,
            steps=steps,
            cfg=cfg,
            adv=adv,
            unrestricted=unrestricted,
            trigger=str(video_knobs.get("trigger") or ""),
            auto_inject_trigger=bool(video_auto_inject_trigger),
            auto_strip_negative=bool(video_auto_strip_negative),
        )
        title = selected_label or (
            "MiniMax H3 FL2VA 首帧/首尾帧音视频"
            if mode == "minimax_h3_i2v"
            else "MiniMax H3 FL2VA 文字生音视频"
        )
    elif mode == "rife_2x":
        if source_video_filename:
            video_name = copy_media_to_input(
                source_video_filename,
                source_video_subfolder,
                source_video_type or "output",
                comfy_paths,
            )
        elif video and video.filename:
            video_name = await save_upload(video, VIDEO_EXTENSIONS, comfy_paths)
        else:
            raise HTTPException(status_code=400, detail="RIFE 模式需要上传视频，或先完成上一阶段视频生成")
        graph = build_rife_prompt(
            video_name=video_name,
            fps=fps,
            multiplier=rife_multiplier,
            adv=adv,
            **rife_runtime_options(),
        )
        title = selected_label or f"RIFE {rife_multiplier}x 插帧"
    elif mode == "deflicker":
        if source_video_filename:
            source_path = safe_media_path(
                source_video_filename,
                source_video_subfolder,
                source_video_type or "output",
                comfy_paths,
            )
        elif video and video.filename:
            video_name = await save_upload(video, VIDEO_EXTENSIONS, comfy_paths)
            source_path = input_media_path(video_name, comfy_paths)
        else:
            raise HTTPException(status_code=400, detail="闪烁修复需要上传视频，或先完成上一阶段视频生成")

        job_id = uuid.uuid4().hex
        job = {
            "id": job_id,
            "prompt_id": None,
            "kind": "video_postprocess",
            "mode": mode,
            "title": selected_label or "画面闪烁修复",
            "status": "queued",
            "completed": False,
            "local": True,
            "created_at": now_ms(),
            "progress": {
                "percent": 0.0,
                "label": "等待本地处理线程",
                "source": "local_queue",
                "accurate": False,
            },
            "status_note": "等待本地处理线程",
            "seed": seed_value,
            "width": width,
            "height": height,
            "length": length,
            "fps": fps,
            "media": [],
            "raw": {"processor": "ffmpeg", "filters": "deflicker,hqdn3d"},
            "model_profile": resolved["profile"],
        }
        queue_local_video_job(
            job,
            operation="deflicker",
            kwargs={"source": source_path, "paths": comfy_paths},
        )
        return JSONResponse(job)
    elif mode in {"upscale_2x", "upscale_seedvr2"}:
        if source_video_filename:
            video_name = copy_media_to_input(
                source_video_filename,
                source_video_subfolder,
                source_video_type or "output",
                comfy_paths,
            )
        elif video and video.filename:
            video_name = await save_upload(video, VIDEO_EXTENSIONS, comfy_paths)
        else:
            raise HTTPException(status_code=400, detail="清晰度增强需要上传视频，或先完成上一阶段视频生成")
        if mode == "upscale_seedvr2":
            graph = build_seedvr2_upscale_prompt(
                video_name=video_name,
                fps=fps,
                seed=seed_value,
                model_name=upscale_model,
                scale=upscale_scale,
                adv=adv,
            )
            title = selected_label or {
                SEEDVR2_7B_MODEL: "SeedVR2 7B NVFP4 时序视频超分",
                SEEDVR2_7B_SHARP_MODEL: "SeedVR2 7B Sharp NVFP4 时序视频超分",
            }.get(upscale_model, "SeedVR2 3B INT8 时序视频超分")
        else:
            graph = build_video_upscale_prompt(video_name=video_name, fps=fps, model_name=upscale_model, adv=adv)
            title = selected_label or (
                "4x-UltraSharp 清晰度增强"
                if upscale_model == "4x-UltraSharp.pth"
                else "RealESRGAN 快速兼容 2x"
            )
    else:
        raise HTTPException(status_code=400, detail="未知模式")

    graph = h3_workflows.apply_extensions(graph, mode, adv, **h3_inputs)
    try:
        object_info = await get_comfy_object_info()
    except HTTPException as exc:
        raise HTTPException(status_code=503, detail=comfy_not_connected_detail("提交 workflow", exc.detail)) from exc
    graph = resolve_graph_model_option_names(graph, object_info)
    graph_errors = validate_graph(graph)
    graph_errors.extend(graph_model_registry_errors(graph, object_info))
    graph_errors.extend(graph_node_schema_errors(graph, object_info))
    missing_nodes = [name for name in graph_class_types(graph) if name not in object_info]
    if missing_nodes:
        graph_errors.append(f"ComfyUI 缺少节点：{', '.join(missing_nodes)}")
    try:
        system_stats = await comfy_get("/system_stats")
    except HTTPException:
        system_stats = None
    graph_errors.extend(
        item["message"]
        for item in workflow_risk_checks(
            mode=mode,
            hardware=build_hardware_summary(system_stats),
            width=width,
            height=height,
            length=length,
        )
        if item.get("level") == "blocked"
    )
    if graph_errors:
        raise HTTPException(status_code=400, detail={"message": "工作流图无效", "errors": graph_errors})

    job_id = uuid.uuid4().hex
    created_at = now_ms()
    job_kind = "video_generation" if mode in VIDEO_GENERATION_MODES else "video_postprocess"
    progress_stream_connected = await ensure_comfy_progress_listener()
    await reconcile_heavy_generation_jobs_before_submit()
    reserve_generation_job_slot(
        job_id=job_id,
        kind=job_kind,
        mode=mode,
        title=title,
        created_at=created_at,
    )
    try:
        response = await comfy_post("/prompt", {"prompt": graph, "client_id": CLIENT_ID})
        prompt_id = str(response.get("prompt_id") or "")
        if not prompt_id:
            raise HTTPException(status_code=500, detail=response)
    except Exception as exc:
        fail_generation_job_slot(job_id, f"提交到 ComfyUI 失败：{exc}")
        raise

    job = {
        "id": job_id,
        "prompt_id": prompt_id,
        "prompt_ids": [prompt_id],
        "kind": job_kind,
        "mode": mode,
        "title": title,
        "status": "queued",
        "completed": False,
        "created_at": created_at,
        "seed": seed_value,
        "width": width,
        "height": height,
        "length": length,
        "fps": fps,
        "media": [],
        "raw": response,
        "model_profile": resolved["profile"],
        "upscale_scale": upscale_scale,
        "rife_multiplier": rife_multiplier,
        "source_video_filename": source_video_filename or (video_name if mode in {"rife_2x", "upscale_2x", "upscale_seedvr2"} else ""),
        "source_video_subfolder": source_video_subfolder,
        "source_video_type": source_video_type,
        "source_image_filename": image_name
        if mode in {
            "i2v_a14b",
            "ti2v_5b",
            "ltx_i2v",
            "ltx23_i2v",
            "ltx25_i2v",
            "hunyuan15_i2v",
            "minimax_h3_i2v",
        }
        else "",
        "source_end_image_filename": end_image_name,
        "h3_inputs": h3_inputs if mode in h3_workflows.H3_MODES else None,
        "reference_media": {
            "images": reference_image_names,
            "videos": reference_video_names,
            "audios": reference_audio_names,
        }
        if mode == "minimax_h3_r2v"
        else None,
        "unrestricted": unrestricted,
        "adult_content_ack": bool(adult_content_ack) if unrestricted else None,
        "unrestricted_strength": unrestricted_strength if unrestricted else None,
        "video_motion": str(video_motion or "medium"),
        "character_id": str(character_id or "").strip(),
        "video_auto_inject_trigger": bool(video_auto_inject_trigger) if unrestricted else None,
        "video_auto_strip_negative": bool(video_auto_strip_negative) if unrestricted else None,
        "advanced": dict(adv),
        "advanced_overrides": video_params.non_default_items(mode, adv),
        "prompt_progress": {},
        "progress_stream_connected": progress_stream_connected,
        "project": project_tag,
        "social_target": social_recipe["target_id"],
        "social_quality": social_recipe["quality_id"],
        "delivery_target": social_recipe["delivery"],
        "safe_zone": social_recipe["safe_zone"],
    }
    job["progress"] = generation_progress_payload(job)
    finalize_generation_job_slot(job)
    return JSONResponse(job)


try:
    JOB_LOST_AFTER_MS = max(300_000, int(os.environ.get("BEGINNER_FRONTEND_JOB_LOST_MS", "1800000")))
except ValueError:
    JOB_LOST_AFTER_MS = 1_800_000

try:
    RECOVERED_JOB_MISSING_AFTER_MS = max(
        5_000,
        int(os.environ.get("BEGINNER_FRONTEND_RECOVERED_JOB_MISSING_MS", "30000")),
    )
except ValueError:
    RECOVERED_JOB_MISSING_AFTER_MS = 30_000


def normalize_comfy_history_status(status_info: dict[str, Any]) -> tuple[str, bool]:
    raw_status = str(status_info.get("status_str") or "").strip().lower()
    completed = bool(status_info.get("completed"))
    if raw_status == "success":
        return "success", True
    if raw_status in {"error", "failed", "failure"}:
        return "failed", True
    if completed:
        return "failed", True
    return raw_status or "running", False


def friendly_comfy_messages(messages: Any) -> list[str]:
    if not isinstance(messages, list):
        return []
    friendly: list[str] = []
    for item in messages[-8:]:
        if isinstance(item, str):
            friendly.append(item)
        elif isinstance(item, (list, tuple)) and item:
            friendly.append(" ".join(str(part) for part in item if part is not None))
        elif isinstance(item, dict):
            friendly.append(json.dumps(item, ensure_ascii=False))
    return friendly


def queue_prompt_ids(queue: dict[str, Any], key: str) -> set[str]:
    return {
        str(item[1])
        for item in queue.get(key) or []
        if isinstance(item, (list, tuple)) and len(item) > 1
    }


def generation_job_prompt_ids(job: dict[str, Any]) -> list[str]:
    values = job.get("prompt_ids")
    if not isinstance(values, list):
        values = [job.get("prompt_id")]
    prompt_ids: list[str] = []
    for value in values:
        prompt_id = str(value or "").strip()
        if prompt_id and prompt_id not in prompt_ids:
            prompt_ids.append(prompt_id)
    return prompt_ids


def deduplicate_media(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in items:
        key = (
            str(item.get("filename") or item.get("url") or ""),
            str(item.get("subfolder") or ""),
            str(item.get("type") or "output"),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def video_generation_progress_payload(job: dict[str, Any]) -> dict[str, Any]:
    prompt_ids = generation_job_prompt_ids(job)
    prompt_id = str(job.get("active_prompt_id") or (prompt_ids[0] if prompt_ids else ""))
    progress_by_prompt = job.get("prompt_progress") if isinstance(job.get("prompt_progress"), dict) else {}
    info = progress_by_prompt.get(prompt_id) or {}
    value = float(info.get("value") or 0)
    maximum = float(info.get("max") or 0)
    sampler_ratio = max(0.0, min(1.0, value / maximum)) if maximum > 0 else 0.0
    status = str(job.get("status") or "queued").lower()
    video_count = len([item for item in job.get("media") or [] if item.get("kind") == "video"])
    active_node = str(job.get("active_node") or info.get("node") or "")
    kind = str(job.get("kind") or "video_generation")

    if status == "success":
        percent = 100.0
        label = "视频已保存"
    elif status in TERMINAL_JOB_STATUSES:
        percent = min(99.0, 5.0 + sampler_ratio * 87.0) if maximum > 0 else 0.0
        label = "任务已中断" if status in {"canceled", "cancelled", "interrupted", "stopped"} else "视频生成未完成"
    elif status == "reconnecting":
        percent = min(92.0, 5.0 + sampler_ratio * 87.0) if maximum > 0 else 0.0
        label = "正在恢复 ComfyUI 连接"
    elif maximum > 0:
        percent = min(92.0, (20.0 + sampler_ratio * 72.0) if kind == "video_face_swap" else (5.0 + sampler_ratio * 87.0))
        label = f"逐帧换脸 {value:g}/{maximum:g}" if kind == "video_face_swap" else f"采样 {value:g}/{maximum:g}"
        if str(info.get("state") or "") == "saving" or sampler_ratio >= 1.0:
            label = "处理完成，正在编码并写入视频" if kind == "video_face_swap" else "采样完成，正在解码并写入视频"
    elif status == "running":
        face_swap_stages = {
            "1": (8.0, "正在读取视频帧"),
            "2": (14.0, "正在读取身份参考图"),
            "3": (45.0, "正在逐帧换脸"),
            "4": (20.0, "正在准备身份特征权重"),
            "5": (94.0, "正在编码换脸视频"),
        }
        stage_percent, stage_label = face_swap_stages.get(active_node, (0.0, ""))
        percent = stage_percent if kind == "video_face_swap" else 0.0
        label = stage_label or ("正在加载换脸模型" if kind == "video_face_swap" else "正在加载模型或准备采样")
    else:
        percent = 0.0
        label = "等待 ComfyUI 开始处理"

    accurate = bool(status == "success" or status in TERMINAL_JOB_STATUSES or maximum > 0 or (kind == "video_face_swap" and percent > 0))
    return {
        "percent": round(max(0.0, min(100.0, percent)), 1),
        "completed": video_count,
        "total": 1,
        "current": 1 if status in {"running", "success"} else 0,
        "current_percent": round(sampler_ratio * 100.0, 1) if maximum > 0 else None,
        "value": value if maximum > 0 else None,
        "max": maximum if maximum > 0 else None,
        "label": label,
        "source": "comfy_websocket" if maximum > 0 else ("history" if status in TERMINAL_JOB_STATUSES else "queue"),
        "accurate": accurate,
    }


def generation_progress_payload(job: dict[str, Any]) -> dict[str, Any]:
    if job.get("kind") != "image_generation" and not str(job.get("mode") or "").startswith("image_"):
        return video_generation_progress_payload(job)
    prompt_ids = generation_job_prompt_ids(job)
    successful = {str(value) for value in job.get("completed_prompt_ids") or []}
    failed = {str(value) for value in job.get("failed_prompt_ids") or []}
    terminal = successful | failed
    progress_by_prompt = job.get("prompt_progress") if isinstance(job.get("prompt_progress"), dict) else {}
    generation_mode = "sequential" if job.get("generation_mode") == "sequential" else "batch"
    total_images = max(1, int(job.get("batch_size") or len(prompt_ids) or 1))
    image_count = len([item for item in job.get("media") or [] if item.get("kind") == "image"])

    def ratio_for(prompt_id: str) -> float:
        if prompt_id in terminal:
            return 1.0
        info = progress_by_prompt.get(prompt_id) or {}
        maximum = float(info.get("max") or 0)
        value = float(info.get("value") or 0)
        return max(0.0, min(1.0, value / maximum)) if maximum > 0 else 0.0

    if generation_mode == "sequential" and prompt_ids:
        raw_ratio = sum(ratio_for(prompt_id) for prompt_id in prompt_ids) / len(prompt_ids)
    elif prompt_ids:
        raw_ratio = ratio_for(prompt_ids[0])
    else:
        raw_ratio = 0.0

    status = str(job.get("status") or "queued").lower()
    face_swap_mode = str(job.get("mode") or "") == "image_face_swap"
    face_swap_stage = ""
    if face_swap_mode:
        face_swap_stages = {
            "1": (0.08, "正在读取完整目标图"),
            "2": (0.16, "正在读取目标脸"),
            "3": (0.24, "正在读取身份参考脸"),
            "4": (0.38, "正在混合身份特征"),
            "5": (0.72, "正在替换目标脸并融合"),
            "6": (0.94, "正在保存换脸结果"),
        }
        stage_ratio, face_swap_stage = face_swap_stages.get(str(job.get("active_node") or ""), (0.0, ""))
        raw_ratio = max(raw_ratio, stage_ratio)
    if status == "success":
        percent = 100.0
    else:
        percent = min(99.5, max(0.0, raw_ratio * 100.0))

    active_prompt_id = str(job.get("active_prompt_id") or "")
    if active_prompt_id not in prompt_ids or active_prompt_id in terminal:
        active_prompt_id = next((prompt_id for prompt_id in prompt_ids if prompt_id not in terminal), "")
    active_index = prompt_ids.index(active_prompt_id) + 1 if active_prompt_id in prompt_ids else len(terminal)
    active_info = progress_by_prompt.get(active_prompt_id) or {}
    value = float(active_info.get("value") or 0)
    maximum = float(active_info.get("max") or 0)
    has_sampler_progress = maximum > 0

    if status == "success":
        label = f"已完成 {image_count}/{total_images} 张"
    elif status in {"failed", "error", "lost", "canceled", "cancelled", "interrupted"}:
        label = f"已保存 {image_count}/{total_images} 张，任务未完成"
    elif status == "reconnecting":
        label = "正在恢复 ComfyUI 连接"
    elif face_swap_mode and status == "running":
        label = face_swap_stage or "正在加载本地换脸模型"
    elif face_swap_mode:
        label = "等待 ComfyUI 开始换脸"
    elif has_sampler_progress:
        step_text = f"采样 {value:g}/{maximum:g}"
        label = (
            f"第 {max(1, active_index)}/{total_images} 张 · {step_text}"
            if generation_mode == "sequential"
            else f"整批 {total_images} 张 · {step_text}"
        )
    elif status == "running":
        label = (
            f"第 {max(1, active_index)}/{total_images} 张 · 正在加载或编码"
            if generation_mode == "sequential"
            else "正在加载模型或编码提示词"
        )
    else:
        label = "等待 ComfyUI 开始采样"

    return {
        "percent": round(percent, 1),
        "completed": image_count,
        "total": total_images,
        "current": max(0, active_index),
        "current_percent": round(max(0.0, min(100.0, (value / maximum) * 100.0)), 1) if has_sampler_progress else None,
        "value": value if has_sampler_progress else None,
        "max": maximum if has_sampler_progress else None,
        "label": label,
        "source": "comfy_websocket" if has_sampler_progress else ("history" if terminal else "queue"),
        "accurate": bool(has_sampler_progress or terminal or status in TERMINAL_JOB_STATUSES),
    }


def apply_comfy_progress_event(message: Any) -> None:
    if not isinstance(message, dict):
        return
    event_type = str(message.get("type") or "")
    data = message.get("data") if isinstance(message.get("data"), dict) else {}
    prompt_id = str(data.get("prompt_id") or "")
    if not prompt_id:
        return

    changed = False
    with JOB_STORE_LOCK:
        target = next(
            (
                job
                for job in JOBS.values()
                if not job.get("local")
                and prompt_id in generation_job_prompt_ids(job)
                and not job_is_terminal(job)
                and not job.get("cancel_requested")
            ),
            None,
        )
        if target is None:
            return

        progress_info: dict[str, Any] | None = None
        if event_type == "progress":
            progress_info = {
                "value": float(data.get("value") or 0),
                "max": float(data.get("max") or 0),
                "node": str(data.get("node") or ""),
                "state": "running",
                "updated_at": now_ms(),
            }
        elif event_type == "progress_state":
            nodes = data.get("nodes") if isinstance(data.get("nodes"), dict) else {}
            candidates = [item for item in nodes.values() if isinstance(item, dict) and item.get("state") == "running"]
            if candidates:
                node = candidates[-1]
                progress_info = {
                    "value": float(node.get("value") or 0),
                    "max": float(node.get("max") or 0),
                    "node": str(node.get("display_node_id") or node.get("node_id") or ""),
                    "state": "running",
                    "updated_at": now_ms(),
                }
        elif event_type == "execution_success":
            previous = (target.get("prompt_progress") or {}).get(prompt_id) or {}
            progress_info = {
                **previous,
                "value": float(previous.get("max") or 1),
                "max": float(previous.get("max") or 1),
                "state": "saving",
                "updated_at": now_ms(),
            }
        elif event_type == "execution_error":
            errors = target.setdefault("websocket_errors", {})
            errors[prompt_id] = str(data.get("exception_message") or data.get("exception_type") or "ComfyUI 执行失败")
            changed = True

        if progress_info is not None:
            target.setdefault("prompt_progress", {})[prompt_id] = progress_info
            target["active_prompt_id"] = prompt_id
            target["status"] = "running"
            target["completed"] = False
            target.pop("connection_error", None)
            changed = True
        elif event_type in {"execution_start", "executing"}:
            target["active_prompt_id"] = prompt_id
            target["active_node"] = str(data.get("display_node") or data.get("node") or "")
            target["status"] = "running"
            target["completed"] = False
            changed = True

        if changed:
            target["last_progress_at"] = now_ms()
            target["progress"] = generation_progress_payload(target)
    if changed:
        persist_job_stores()
        try:
            signal_key = (asyncio.get_running_loop(), str(target["id"]))
        except RuntimeError:
            return
        with JOB_STORE_LOCK:
            signal = JOB_PROGRESS_SIGNALS.get(signal_key)
        if signal is not None:
            signal.set()


def unload_models_after_job_enabled() -> bool:
    env_value = str(os.environ.get("BEGINNER_FRONTEND_UNLOAD_AFTER_JOB") or "").strip().lower()
    if env_value:
        return env_value not in {"0", "false", "no", "off"}
    config = read_local_config()
    if "unload_models_after_job" in config:
        return bool(config.get("unload_models_after_job"))
    return False


def job_holds_comfy_models(job: dict[str, Any] | None) -> bool:
    if not job or job.get("local"):
        return False
    if job_is_terminal(job):
        return False
    if generation_job_prompt_ids(job):
        return True
    return str(job.get("kind") or "") in {
        "image_generation",
        "video_generation",
        "video_face_swap",
        "video_smoke_test",
        "video_postprocess",
    }


def other_comfy_jobs_in_flight(exclude_job_id: str | None = None) -> bool:
    excluded = str(exclude_job_id or "")
    with JOB_STORE_LOCK:
        jobs = list(JOBS.values())
    return any(str(job.get("id") or "") != excluded and job_holds_comfy_models(job) for job in jobs)


def record_vram_cleanup(job: dict[str, Any], *, status: str, reason: str) -> None:
    job["vram_cleanup"] = {
        "status": status,
        "reason": reason,
        "at": now_ms(),
    }


async def maybe_release_comfy_vram_for_completed_job(job: dict[str, Any] | None) -> dict[str, Any] | None:
    if not job or job.get("local") or not job_is_terminal(job):
        return job
    job_id = str(job.get("id") or "")
    with JOB_STORE_LOCK:
        if job.get("vram_cleanup"):
            return job
        record_vram_cleanup(job, status="pending", reason="checking")
    if not unload_models_after_job_enabled():
        record_vram_cleanup(job, status="skipped", reason="disabled")
        persist_job_stores()
        return job
    if other_comfy_jobs_in_flight(job_id):
        record_vram_cleanup(job, status="skipped", reason="other_jobs_running")
        persist_job_stores()
        return job
    try:
        queue = await comfy_get("/queue")
    except HTTPException as exc:
        record_vram_cleanup(job, status="failed", reason=comfy_connection_error_text(exc))
        persist_job_stores()
        return job
    busy_ids = queue_prompt_ids(queue, "queue_running") | queue_prompt_ids(queue, "queue_pending")
    if busy_ids:
        record_vram_cleanup(job, status="skipped", reason="comfy_queue_busy")
        persist_job_stores()
        return job
    try:
        await comfy_post("/free", {"unload_models": True, "free_memory": True})
    except HTTPException as exc:
        record_vram_cleanup(job, status="failed", reason=comfy_connection_error_text(exc))
        persist_job_stores()
        return job
    record_vram_cleanup(job, status="requested", reason="unload_models")
    persist_job_stores()
    return job


async def refresh_multi_prompt_image_job(job: dict[str, Any]) -> dict[str, Any]:
    prompt_ids = generation_job_prompt_ids(job)
    successful_set = {str(value) for value in job.get("completed_prompt_ids") or []}
    failed_set = {str(value) for value in job.get("failed_prompt_ids") or []}
    terminal = successful_set | failed_set
    unresolved = [prompt_id for prompt_id in prompt_ids if prompt_id not in terminal]
    media = list(job.get("media") or [])
    messages = list(job.get("messages") or [])
    prompt_statuses = dict(job.get("prompt_statuses") or {})
    running_ids: set[str] = set()
    pending_ids: set[str] = set()

    if unresolved:
        try:
            queue = await comfy_get("/queue")
        except HTTPException as exc:
            job.update(
                {
                    "status": "reconnecting",
                    "completed": False,
                    "connection_error": comfy_connection_error_text(exc),
                    "last_poll_at": now_ms(),
                }
            )
            job["progress"] = generation_progress_payload(job)
            persist_job_stores()
            return job
        running_ids = queue_prompt_ids(queue, "queue_running")
        pending_ids = queue_prompt_ids(queue, "queue_pending")

        history_candidates = [
            prompt_id
            for prompt_id in unresolved
            if prompt_id not in running_ids and prompt_id not in pending_ids
        ]
        if history_candidates:
            results = await asyncio.gather(
                *(comfy_get(f"/history/{prompt_id}") for prompt_id in history_candidates),
                return_exceptions=True,
            )
            for prompt_id, result in zip(history_candidates, results):
                history_item = result.get(prompt_id) if isinstance(result, dict) else None
                if not history_item:
                    continue
                status_info = history_item.get("status", {})
                status, completed = normalize_comfy_history_status(status_info)
                prompt_statuses[prompt_id] = status
                if completed and status == "success":
                    successful_set.add(prompt_id)
                elif completed:
                    failed_set.add(prompt_id)
                media.extend(extract_media(history_item))
                messages.extend(status_info.get("messages", []) or [])

    successful = [prompt_id for prompt_id in prompt_ids if prompt_id in successful_set]
    failed = [prompt_id for prompt_id in prompt_ids if prompt_id in failed_set]
    terminal = set(successful) | set(failed)
    unresolved = [prompt_id for prompt_id in prompt_ids if prompt_id not in terminal]

    timestamp = now_ms()
    job.update(
        {
            "completed_prompt_ids": successful,
            "failed_prompt_ids": failed,
            "prompt_statuses": prompt_statuses,
            "media": deduplicate_media(media),
            "messages": messages[-16:],
            "friendly_messages": friendly_comfy_messages(messages),
            "last_poll_at": timestamp,
        }
    )
    if len(terminal) == len(prompt_ids):
        job["status"] = "failed" if failed else "success"
        job["completed"] = True
        job["finished_at"] = job.get("finished_at") or timestamp
        job.pop("recovered", None)
        if failed:
            job["error"] = f"{len(failed)} 个单图任务执行失败；已成功保存 {len(successful)} 张。"
    elif any(prompt_id in running_ids for prompt_id in unresolved):
        job["status"] = "running"
        job["completed"] = False
        job["last_seen_at"] = timestamp
        job.pop("missing_seen_at", None)
        job.pop("recovered", None)
    elif any(prompt_id in pending_ids for prompt_id in unresolved):
        job["status"] = "queued" if not successful else "running"
        job["completed"] = False
        job["last_seen_at"] = timestamp
        job.pop("missing_seen_at", None)
        job.pop("recovered", None)
    else:
        missing_seen_at = int(job.setdefault("missing_seen_at", timestamp))
        recovered = bool(job.get("recovered"))
        missing_after_ms = RECOVERED_JOB_MISSING_AFTER_MS if recovered else JOB_LOST_AFTER_MS
        if recovered or timestamp - missing_seen_at > missing_after_ms:
            job["status"] = "interrupted" if recovered else "lost"
            job["completed"] = True
            job["finished_at"] = job.get("finished_at") or timestamp
            job["error"] = (
                "ComfyUI 重启或队列被清空，剩余单图任务已中断；已生成图片仍然保留。"
                if recovered
                else "ComfyUI 队列和历史持续找不到剩余单图任务。"
            )
        else:
            job["status"] = "running" if successful else "queued"
            job["completed"] = False
            job["status_note"] = (
                "前端已重启，正在核对 ComfyUI 队列与历史。"
                if recovered
                else "ComfyUI 暂未返回部分任务，平台会继续等待。"
            )
    if terminal or running_ids or pending_ids:
        job.pop("connection_error", None)
    job["progress"] = generation_progress_payload(job)
    persist_job_stores(force=bool(job.get("completed")))
    return job


def fal_queue_logs(payload: dict[str, Any]) -> list[str]:
    messages: list[str] = []
    for entry in payload.get("logs") or []:
        if isinstance(entry, dict):
            message = str(entry.get("message") or "").strip()
        else:
            message = str(entry or "").strip()
        if message:
            messages.append(message[:500])
    return messages[-8:]


async def refresh_fal_generation_job(job: dict[str, Any]) -> dict[str, Any]:
    """Refresh an H3 Max cloud job without touching ComfyUI or the local GPU."""
    try:
        status_payload = await fal_request_json("GET", str(job.get("fal_status_url") or ""))
    except HTTPException as exc:
        job["status"] = "reconnecting"
        job["completed"] = False
        job["connection_error"] = str(exc.detail)
        job["last_poll_at"] = now_ms()
        job["progress"] = {
            "percent": float((job.get("progress") or {}).get("percent") or 0),
            "label": "fal 暂时无法连接，稍后自动重试",
            "source": "fal_queue",
            "accurate": False,
        }
        persist_job_stores()
        return job

    status = str(status_payload.get("status") or "").strip().upper()
    logs = fal_queue_logs(status_payload)
    job["last_poll_at"] = now_ms()
    job["fal_status"] = status
    job["friendly_messages"] = logs
    job.pop("connection_error", None)
    job.pop("recovered", None)

    if status in {"IN_QUEUE", "QUEUED", "PENDING"}:
        position = status_payload.get("queue_position")
        suffix = f"（前方 {position} 个任务）" if isinstance(position, int) and position > 0 else ""
        job["status"] = "queued"
        job["completed"] = False
        job["progress"] = {
            "percent": 2.0,
            "label": f"fal 云端排队中{suffix}",
            "source": "fal_queue",
            "accurate": False,
        }
    elif status in {"IN_PROGRESS", "RUNNING", "PROCESSING"}:
        job["status"] = "running"
        job["completed"] = False
        job["progress"] = {
            "percent": 50.0,
            "label": logs[-1] if logs else "fal 云端正在生成 H3 Max 音视频",
            "source": "fal_queue",
            "accurate": False,
        }
    elif status in {"COMPLETED", "SUCCESS", "SUCCEEDED"}:
        try:
            result = await fal_request_json("GET", str(job.get("fal_response_url") or ""))
            data = result.get("data") if isinstance(result.get("data"), dict) else result
            video_info = data.get("video") if isinstance(data, dict) else None
            video_url = str((video_info or {}).get("url") or "").strip()
            if not video_url:
                raise HTTPException(status_code=502, detail="fal 已完成任务，但没有返回视频地址")
            destination, media = fal_output_destination(str(job.get("output_relative_path") or ""))
            if not destination.is_file() or destination.stat().st_size <= 0:
                await download_fal_video(video_url, destination)
            job["status"] = "success"
            job["completed"] = True
            job["finished_at"] = job.get("finished_at") or now_ms()
            job["media"] = [media]
            job["expanded_prompt"] = data.get("expanded_prompt") if isinstance(data, dict) else None
            job["timings"] = data.get("timings") if isinstance(data, dict) else None
            job["fal_file"] = {
                "file_name": str((video_info or {}).get("file_name") or destination.name),
                "file_size": int((video_info or {}).get("file_size") or destination.stat().st_size),
                "content_type": str((video_info or {}).get("content_type") or "video/mp4"),
            }
            job["progress"] = {
                "percent": 100.0,
                "label": "H3 Max 成片已下载到本地",
                "source": "fal_result",
                "accurate": True,
            }
        except HTTPException as exc:
            job["status"] = "reconnecting"
            job["completed"] = False
            job["connection_error"] = str(exc.detail)
            job["progress"] = {
                "percent": 95.0,
                "label": "fal 已生成，正在重试下载成片",
                "source": "fal_result",
                "accurate": False,
            }
    elif status in {"FAILED", "ERROR", "CANCELLED", "CANCELED"}:
        canceled = status in {"CANCELLED", "CANCELED"}
        detail = status_payload.get("error") or status_payload.get("detail") or "fal 云端任务失败"
        job["status"] = "canceled" if canceled else "failed"
        job["completed"] = True
        job["finished_at"] = job.get("finished_at") or now_ms()
        job["error"] = str(detail)[:800]
        job["progress"] = {
            "percent": 0.0,
            "label": "fal 任务已取消" if canceled else "fal 任务未完成",
            "source": "fal_queue",
            "accurate": True,
        }
    else:
        job["status"] = "queued"
        job["completed"] = False
        job["status_note"] = f"fal 返回状态：{status or 'UNKNOWN'}"
        job["progress"] = {
            "percent": float((job.get("progress") or {}).get("percent") or 0),
            "label": "等待 fal 更新任务状态",
            "source": "fal_queue",
            "accurate": False,
        }

    persist_job_stores(force=bool(job.get("completed")))
    signal_generation_job(str(job.get("id") or ""))
    return job


async def refresh_generation_job(job_id: str) -> dict[str, Any]:
    async with job_refresh_async_lock(job_id):
        async def finish(current: dict[str, Any]) -> dict[str, Any]:
            if current.get("status") == "success" and not current.get("metadata_checked"):
                from beginner_frontend.media_metadata import read_video_metadata
                for media in current.get("media", []):
                    if media.get("kind") != "video":
                        continue
                    try:
                        path = safe_media_path(media["filename"], media.get("subfolder", ""), media.get("type", "output"))
                        metadata = await asyncio.to_thread(read_video_metadata, path, ffprobe_path(), _hidden_popen_options())
                        if metadata:
                            media["metadata"] = metadata
                            current["output_metadata"] = metadata
                    except (HTTPException, OSError):
                        pass
                current["metadata_checked"] = True
                persist_job_stores()
            if not current.get("local") and current.get("provider") != "fal":
                await maybe_release_comfy_vram_for_completed_job(current)
            return current

        with JOB_STORE_LOCK:
            job = JOBS.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="任务不存在")
        if job.get("provider") == "fal":
            if job_is_terminal(job):
                return job
            return await refresh_fal_generation_job(job)
        if job.get("local") or job.get("reservation") or job_is_terminal(job):
            return await finish(job)

        prompt_ids = generation_job_prompt_ids(job)
        if not prompt_ids:
            job.update(
                {
                    "status": "failed",
                    "completed": True,
                    "finished_at": now_ms(),
                    "error": "任务没有 ComfyUI prompt_id，无法继续跟踪。",
                }
            )
            persist_job_stores(force=True)
            return await finish(job)

        if job.get("kind") == "image_generation" and len(prompt_ids) > 1:
            return await finish(await refresh_multi_prompt_image_job(job))

        prompt_id = prompt_ids[0]

        try:
            history = await comfy_get(f"/history/{prompt_id}")
        except HTTPException as exc:
            job["status"] = "reconnecting"
            job["completed"] = False
            job["connection_error"] = comfy_connection_error_text(exc)
            job["last_poll_at"] = now_ms()
            job["progress"] = generation_progress_payload(job)
            persist_job_stores()
            return await finish(job)

        history_item = history.get(prompt_id) if isinstance(history, dict) else None
        if history_item:
            status_info = history_item.get("status", {})
            job["status"], job["completed"] = normalize_comfy_history_status(status_info)
            job["media"] = extract_media(history_item)
            job["messages"] = status_info.get("messages", [])
            job["friendly_messages"] = friendly_comfy_messages(job["messages"])
            job["last_seen_at"] = now_ms()
            job["last_poll_at"] = now_ms()
            job.pop("missing_seen_at", None)
            job.pop("connection_error", None)
            job.pop("recovered", None)
            if job["status"] == "failed" and not job.get("error"):
                job["error"] = "ComfyUI 执行失败。请查看下方节点日志，通常是缺模型、缺节点、显存不足或 dtype 不兼容。"
            if job["completed"]:
                job["finished_at"] = job.get("finished_at") or now_ms()
            job["completed_prompt_ids"] = [prompt_id] if job["status"] == "success" else []
            job["failed_prompt_ids"] = [prompt_id] if job["status"] == "failed" else []
            job["progress"] = generation_progress_payload(job)
            persist_job_stores(force=bool(job["completed"]))
            return await finish(job)

        try:
            queue = await comfy_get("/queue")
        except HTTPException as exc:
            job["status"] = "reconnecting"
            job["completed"] = False
            job["connection_error"] = comfy_connection_error_text(exc)
            job["last_poll_at"] = now_ms()
            job["progress"] = generation_progress_payload(job)
            persist_job_stores()
            return await finish(job)

        running_ids = queue_prompt_ids(queue, "queue_running")
        pending_ids = queue_prompt_ids(queue, "queue_pending")
        timestamp = now_ms()
        if prompt_id in running_ids or prompt_id in pending_ids:
            job["status"] = "running" if prompt_id in running_ids else "queued"
            job["completed"] = False
            job["last_seen_at"] = timestamp
            job["last_poll_at"] = timestamp
            job.pop("missing_seen_at", None)
            job.pop("connection_error", None)
            job.pop("recovered", None)
        else:
            missing_seen_at = int(job.setdefault("missing_seen_at", timestamp))
            job["last_poll_at"] = timestamp
            recovered = bool(job.get("recovered"))
            missing_after_ms = RECOVERED_JOB_MISSING_AFTER_MS if recovered else JOB_LOST_AFTER_MS
            if recovered or timestamp - missing_seen_at > missing_after_ms:
                job["status"] = "interrupted" if recovered else "lost"
                job["completed"] = True
                job["finished_at"] = job.get("finished_at") or timestamp
                job["error"] = (
                    "ComfyUI 重启或队列被清空，任务已中断；此前生成的输出仍然保留。"
                    if recovered
                    else (
                        f"ComfyUI 队列和历史持续 {max(1, JOB_LOST_AFTER_MS // 60_000)} 分钟都找不到这个任务，"
                        "可能是 ComfyUI 重启、任务被清队或任务提交到了另一个实例。"
                    )
                )
            else:
                job["status"] = "reconnecting" if recovered else "queued"
                job["completed"] = False
                job["status_note"] = (
                    "前端已重启，正在核对 ComfyUI 队列与历史。"
                    if recovered
                    else "ComfyUI 暂未返回队列或历史记录，平台会继续等待。"
                )
        job["progress"] = generation_progress_payload(job)
        persist_job_stores(force=bool(job.get("completed")))
        return await finish(job)


# ============================================================
# 历史输出管理：平台输出子目录 + 文件列表/删除/清空
# ============================================================

def saved_output_subdir() -> str:
    return str(read_local_config().get("output_subdir") or "").strip()


def normalize_relative_output_subdir(value: str, default: str) -> str:
    """Normalize a ComfyUI output subdirectory while preserving nested folders."""
    raw = str(value or "").strip().replace("\\", "/")
    if not raw:
        return default
    if re.match(r"^[A-Za-z]:", raw) or raw.startswith("/"):
        raise HTTPException(status_code=400, detail="输出目录必须是 ComfyUI 输出根目录下的子目录")
    text = raw.strip("/")
    parts = [part for part in text.split("/") if part not in ("", ".")]
    if not parts or any(part == ".." or re.search(r'[<>:"|?*]', part) for part in parts):
        raise HTTPException(status_code=400, detail="输出目录不安全")
    safe = "/".join(parts)
    if len(safe) > 120:
        raise HTTPException(status_code=400, detail="输出目录过长")
    return safe


def normalize_output_subdir(value: str) -> str:
    """输出子目录只允许相对安全名。"""
    return normalize_relative_output_subdir(value, VIDEO_OUTPUT_SUBDIR)


def platform_output_dir(paths: dict[str, Any] | None = None) -> Path:
    paths = paths or configured_comfy_paths()
    subdir = normalize_output_subdir(saved_output_subdir())
    return Path(paths["output_dir"]) / subdir


async def list_platform_outputs(limit: int = 60) -> dict[str, Any]:
    paths = await active_comfy_paths()
    output_dir = platform_output_dir(paths)
    subdir = normalize_output_subdir(saved_output_subdir())
    items: list[dict[str, Any]] = []
    if output_dir.is_dir():
        for path in output_dir.rglob("*"):
            if not path.is_file():
                continue
            suffix = path.suffix.lower()
            if suffix not in IMAGE_EXTENSIONS and suffix not in VIDEO_EXTENSIONS:
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            relative = path.relative_to(output_dir)
            if OUTPUT_TRASH_DIRNAME in relative.parts:
                continue
            subfolder = "" if relative.parent == Path(".") else str(relative.parent).replace("\\", "/")
            full_subfolder = "/".join(part for part in (subdir, subfolder) if part)
            kind = "video" if suffix in VIDEO_EXTENSIONS else "image"
            items.append(
                {
                    "filename": path.name,
                    "subfolder": subfolder,
                    "media_subfolder": full_subfolder,
                    "type": "output",
                    "rel": str(relative).replace("\\", "/"),
                    "kind": kind,
                    "size": int(stat.st_size),
                    "modified_at": int(stat.st_mtime),
                    "url": media_url({"filename": path.name, "subfolder": full_subfolder, "type": "output"}),
                }
            )
    items.sort(key=lambda item: item.get("modified_at") or 0, reverse=True)
    total = len(items)
    return {
        "ok": True,
        "subdir": subdir,
        "dir": str(output_dir),
        "count": total,
        "items": items[:limit],
    }


@app.get("/api/outputs")
async def list_outputs(limit: int = 60) -> dict[str, Any]:
    limit = clamp_int(limit, 1, 200)
    return await list_platform_outputs(limit)


@app.get("/api/outputs/config")
async def get_output_config() -> dict[str, Any]:
    paths = await active_comfy_paths()
    return {
        "ok": True,
        "subdir": normalize_output_subdir(saved_output_subdir()),
        "dir": str(platform_output_dir(paths)),
        "output_root": str(paths["output_dir"]),
    }


@app.post("/api/outputs/config")
async def save_output_config(payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    subdir = normalize_output_subdir(str((payload or {}).get("subdir") or ""))
    config = read_local_config()
    config["output_subdir"] = "" if subdir == VIDEO_OUTPUT_SUBDIR else subdir
    write_local_config(config)
    paths = await active_comfy_paths()
    output_dir = platform_output_dir(paths)
    output_dir.mkdir(parents=True, exist_ok=True)
    return {"ok": True, "subdir": subdir, "dir": str(output_dir)}


OUTPUT_TRASH_DIRNAME = "_trash"
OUTPUT_TRASH_KEEP_SECONDS = 7 * 24 * 3600


def _purge_expired_trash(trash_dir: Path) -> None:
    if not trash_dir.is_dir():
        return
    cutoff = time.time() - OUTPUT_TRASH_KEEP_SECONDS
    for path in trash_dir.rglob("*"):
        try:
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink()
        except OSError:
            continue


def discard_output_file(candidate: Path, output_dir: Path) -> None:
    """把输出文件移入回收目录而不是直接永久删除，误删可在 _trash 里找回。"""
    trash_dir = output_dir / OUTPUT_TRASH_DIRNAME
    trash_dir.mkdir(parents=True, exist_ok=True)
    target = trash_dir / candidate.name
    if target.exists():
        target = trash_dir / f"{target.stem}_{uuid.uuid4().hex[:6]}{target.suffix}"
    shutil.move(str(candidate), str(target))
    _purge_expired_trash(trash_dir)


def _resolve_output_file(rel: str) -> Path:
    output_dir = platform_output_dir()
    base = output_dir.resolve()
    candidate = (output_dir / str(rel or "")).resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        raise HTTPException(status_code=400, detail="文件路径不安全")
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return candidate


@app.post("/api/outputs/delete")
async def delete_output(payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    rel = str((payload or {}).get("rel") or "").strip()
    if not rel:
        raise HTTPException(status_code=400, detail="缺少文件标识")
    candidate = _resolve_output_file(rel)
    output_dir = platform_output_dir()
    if OUTPUT_TRASH_DIRNAME in candidate.relative_to(output_dir.resolve()).parts:
        raise HTTPException(status_code=400, detail="回收目录中的文件请直接在文件管理器里处理")
    name = candidate.name
    discard_output_file(candidate, output_dir)
    return {"ok": True, "deleted": name, "trash": OUTPUT_TRASH_DIRNAME}


@app.post("/api/outputs/delete-batch")
async def delete_outputs_batch(payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    rels = (payload or {}).get("rels")
    if not isinstance(rels, list) or not rels:
        raise HTTPException(status_code=400, detail="缺少要删除的文件列表")
    deleted: list[str] = []
    errors: list[str] = []
    output_dir = platform_output_dir()
    for raw in rels[:500]:
        rel = str(raw or "").strip()
        if not rel:
            continue
        try:
            candidate = _resolve_output_file(rel)
            if OUTPUT_TRASH_DIRNAME in candidate.relative_to(output_dir.resolve()).parts:
                continue
            discard_output_file(candidate, output_dir)
            deleted.append(candidate.name)
        except HTTPException as exc:
            errors.append(f"{rel}: {exc.detail}")
        except OSError as exc:
            errors.append(f"{rel}: {exc}")
    return {"ok": not errors, "deleted": deleted, "removed": len(deleted), "errors": errors, "trash": OUTPUT_TRASH_DIRNAME}


@app.post("/api/outputs/clear")
async def clear_outputs() -> dict[str, Any]:
    output_dir = platform_output_dir()
    removed = 0
    if output_dir.is_dir():
        base = output_dir.resolve()
        for path in sorted(output_dir.rglob("*"), reverse=True):
            try:
                if OUTPUT_TRASH_DIRNAME in path.resolve().relative_to(base).parts:
                    continue
                if path.is_file() and path.suffix.lower() in (IMAGE_EXTENSIONS | VIDEO_EXTENSIONS):
                    discard_output_file(path, output_dir)
                    removed += 1
                elif path.is_dir():
                    path.rmdir()
            except (OSError, ValueError):
                continue
    output_dir.mkdir(parents=True, exist_ok=True)
    return {"ok": True, "removed": removed, "trash": OUTPUT_TRASH_DIRNAME}


@app.get("/api/jobs")
async def list_generation_jobs(limit: int = 20, offset: int = 0, status: str = "all", project: str = "") -> dict[str, Any]:
    from beginner_frontend.job_queries import query_jobs
    with JOB_STORE_LOCK:
        return query_jobs(JOBS.values(), limit=limit, offset=offset, status=status, project=project)


@app.post("/api/jobs/{job_id}/cancel")
async def cancel_generation_job(job_id: str) -> dict[str, Any]:
    job = await refresh_generation_job(job_id)
    if job_is_terminal(job):
        return {**job, "already_terminal": True}

    if job.get("provider") == "fal":
        await fal_request_json("PUT", str(job.get("fal_cancel_url") or ""))
        with JOB_STORE_LOCK:
            target = JOBS.get(job_id)
            if not target:
                raise HTTPException(status_code=404, detail="任务不存在")
            target.update(
                {
                    "status": "canceled",
                    "completed": True,
                    "finished_at": now_ms(),
                    "status_note": "已向 fal 提交取消请求。",
                    "progress": {
                        "percent": 0.0,
                        "label": "fal 任务已取消",
                        "source": "fal_queue",
                        "accurate": True,
                    },
                }
            )
            result = dict(target)
        persist_job_stores(force=True)
        signal_generation_job(job_id)
        return result

    if job.get("local"):
        with JOB_STORE_LOCK:
            target = JOBS.get(job_id)
            if not target:
                raise HTTPException(status_code=404, detail="任务不存在")
            target["cancel_requested"] = True
            target["status"] = "canceling"
            target["status_note"] = "正在中断本地视频处理。"
            target["progress"] = {
                "percent": float((target.get("progress") or {}).get("percent") or 0)
                if isinstance(target.get("progress"), dict)
                else float(target.get("progress") or 0),
                "label": "正在中断本地视频处理",
                "source": "local_worker",
                "accurate": False,
            }
            result = dict(target)
        with LOCAL_VIDEO_PROCESS_LOCK:
            process = LOCAL_VIDEO_PROCESSES.get(job_id)
        if process and process.poll() is None:
            try:
                process.terminate()
            except OSError:
                pass
        persist_job_stores(force=True)
        signal_generation_job(job_id)
        return result

    prompt_ids = generation_job_prompt_ids(job)
    if not prompt_ids:
        raise HTTPException(status_code=400, detail="任务没有可取消的 ComfyUI prompt_id")

    with JOB_STORE_LOCK:
        target = JOBS.get(job_id)
        if not target:
            raise HTTPException(status_code=404, detail="任务不存在")
        target["cancel_requested"] = True
        target["status"] = "canceling"
        target["status_note"] = "正在从 ComfyUI 队列中移除该任务。"
    persist_job_stores()
    signal_generation_job(job_id)

    prompt_id_set = set(prompt_ids)
    deleted_pending: set[str] = set()
    interrupted_running: set[str] = set()
    try:
        for _attempt in range(2):
            queue = await comfy_get("/queue")
            pending_targets = queue_prompt_ids(queue, "queue_pending") & prompt_id_set
            if pending_targets:
                await comfy_post("/queue", {"delete": sorted(pending_targets)})
                deleted_pending.update(pending_targets)

            queue = await comfy_get("/queue")
            running_targets = queue_prompt_ids(queue, "queue_running") & prompt_id_set
            if running_targets:
                await comfy_post("/interrupt", {})
                interrupted_running.update(running_targets)

            queue = await comfy_get("/queue")
            if not (
                (queue_prompt_ids(queue, "queue_pending") | queue_prompt_ids(queue, "queue_running"))
                & prompt_id_set
            ):
                break
    except HTTPException as exc:
        with JOB_STORE_LOCK:
            target = JOBS.get(job_id)
            if target:
                target.pop("cancel_requested", None)
                target["status_note"] = f"取消失败：{comfy_connection_error_text(exc)}"
        persist_job_stores(force=True)
        signal_generation_job(job_id)
        raise HTTPException(status_code=503, detail=f"无法取消任务：{comfy_connection_error_text(exc)}") from exc

    history_results = await asyncio.gather(
        *(comfy_get(f"/history/{prompt_id}") for prompt_id in prompt_ids),
        return_exceptions=True,
    )
    recovered_media = list(job.get("media") or [])
    completed_prompt_ids = {str(value) for value in job.get("completed_prompt_ids") or []}
    for prompt_id, history in zip(prompt_ids, history_results):
        history_item = history.get(prompt_id) if isinstance(history, dict) else None
        if not history_item:
            continue
        recovered_media.extend(extract_media(history_item))
        status, completed = normalize_comfy_history_status(history_item.get("status", {}))
        if completed and status == "success":
            completed_prompt_ids.add(prompt_id)

    timestamp = now_ms()
    with JOB_STORE_LOCK:
        target = JOBS.get(job_id)
        if not target:
            raise HTTPException(status_code=404, detail="任务不存在")
        target.update(
            {
                "status": "canceled",
                "completed": True,
                "finished_at": timestamp,
                "canceled_at": timestamp,
                "completed_prompt_ids": [prompt_id for prompt_id in prompt_ids if prompt_id in completed_prompt_ids],
                "canceled_prompt_ids": [prompt_id for prompt_id in prompt_ids if prompt_id not in completed_prompt_ids],
                "deleted_pending_prompt_ids": sorted(deleted_pending),
                "interrupted_prompt_ids": sorted(interrupted_running),
                "media": deduplicate_media(recovered_media),
                "status_note": "任务已由用户中断；已经生成并保存的图片仍然保留。",
            }
        )
        target.pop("cancel_requested", None)
        target.pop("connection_error", None)
        target.pop("active_prompt_id", None)
        target["progress"] = generation_progress_payload(target)
        result = dict(target)
    persist_job_stores(force=True)
    signal_generation_job(job_id)
    with JOB_STORE_LOCK:
        live = JOBS.get(job_id)
    if live:
        await maybe_release_comfy_vram_for_completed_job(live)
        with JOB_STORE_LOCK:
            live = JOBS.get(job_id)
            if live:
                result = dict(live)
    return result


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str, refresh: bool = True) -> dict[str, Any]:
    if not refresh:
        from copy import deepcopy
        with JOB_STORE_LOCK:
            job = JOBS.get(job_id)
            if job is None:
                raise HTTPException(status_code=404, detail="任务不存在")
            return deepcopy(job)
    return await refresh_generation_job(job_id)


@app.get("/api/jobs/{job_id}/events")
async def generation_job_events(job_id: str, request: Request) -> StreamingResponse:
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="任务不存在")

    async def event_stream():
        last_signature = ""
        heartbeat_at = time.monotonic()
        loop = asyncio.get_running_loop()
        signal_key = (loop, job_id)
        with JOB_STORE_LOCK:
            progress_signal = JOB_PROGRESS_SIGNALS.setdefault(signal_key, asyncio.Event())
        next_refresh_at = 0.0
        yield "retry: 2500\n\n"
        try:
            while not await request.is_disconnected():
                progress_signal.clear()
                timestamp = time.monotonic()
                if timestamp >= next_refresh_at:
                    job = await refresh_generation_job(job_id)
                    next_refresh_at = time.monotonic() + 1.5
                else:
                    with JOB_STORE_LOCK:
                        job = JOBS.get(job_id)
                    if not job:
                        break
                payload = json.dumps(job, ensure_ascii=False, separators=(",", ":"), default=str)
                signature_data = dict(job)
                signature_data.pop("last_poll_at", None)
                signature_data.pop("last_seen_at", None)
                signature = json.dumps(signature_data, ensure_ascii=False, separators=(",", ":"), default=str)
                if signature != last_signature:
                    yield f"data: {payload}\n\n"
                    last_signature = signature
                    heartbeat_at = time.monotonic()
                elif time.monotonic() - heartbeat_at >= 15:
                    yield ": keepalive\n\n"
                    heartbeat_at = time.monotonic()
                if job_is_terminal(job):
                    break
                timeout = max(0.05, next_refresh_at - time.monotonic())
                try:
                    await asyncio.wait_for(progress_signal.wait(), timeout=timeout)
                except TimeoutError:
                    pass
        finally:
            with JOB_STORE_LOCK:
                if JOB_PROGRESS_SIGNALS.get(signal_key) is progress_signal:
                    JOB_PROGRESS_SIGNALS.pop(signal_key, None)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/media/metadata")
async def media_metadata(filename: str, subfolder: str = "", type: str = "output") -> dict[str, Any]:
    from beginner_frontend.media_metadata import read_video_metadata
    path = safe_media_path(filename, subfolder, type)
    if path.suffix.lower() not in VIDEO_EXTENSIONS:
        raise HTTPException(status_code=400, detail="仅支持视频文件")
    try:
        metadata = await asyncio.to_thread(read_video_metadata, path, ffprobe_path(), _hidden_popen_options())
    except HTTPException:
        metadata = {}
    return {"ok": bool(metadata), "metadata": metadata}


@app.get("/api/view")
async def view(filename: str, subfolder: str = "", type: str = "output") -> FileResponse:
    path = safe_media_path(filename, subfolder, type, await active_comfy_paths())
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return FileResponse(path, media_type=media_type, filename=path.name)


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Any, exc: HTTPException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
