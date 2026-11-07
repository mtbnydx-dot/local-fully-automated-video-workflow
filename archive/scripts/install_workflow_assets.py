from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from urllib.parse import urlparse, urlunparse

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

from beginner_frontend.model_catalog import CUSTOM_NODE_REPOS, INSTALL_PROFILES, MODEL_ASSETS, OPTIONAL_POST_NODE_IDS, POST_ASSET_IDS


USER_AGENT = "local-ai-video-workbench/1.0"
SAFETY_BUFFER_BYTES = 10 * 1024**3
HF_ENDPOINT_ENV_NAMES = ("LOCAL_AI_HF_ENDPOINT", "WAN22_HF_ENDPOINT", "HF_ENDPOINT")
HF_TOKEN_ENV_NAMES = ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN")
LOCAL_ASSET_ENV_NAMES = ("WAN22_LOCAL_ASSET_DIRS", "WAN22_MODEL_CACHE_DIRS")

MODEL_FILES = MODEL_ASSETS


def hidden_process_options() -> dict[str, object]:
    if os.name != "nt":
        return {}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 0)
    startupinfo.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
    return {
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0),
        "startupinfo": startupinfo,
    }


def normalize_hf_endpoint(value: str | None) -> str:
    value = (value or "").strip().rstrip("/")
    if not value:
        return ""
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("HF endpoint must be an http(s) URL, for example https://huggingface.co")
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", "", ""))


def configured_hf_endpoint() -> str:
    for name in HF_ENDPOINT_ENV_NAMES:
        endpoint = normalize_hf_endpoint(os.environ.get(name))
        if endpoint:
            return endpoint
    return ""


def configured_hf_token() -> str:
    for name in HF_TOKEN_ENV_NAMES:
        token = (os.environ.get(name) or "").strip()
        if token:
            return token
    try:
        from huggingface_hub import get_token

        return (get_token() or "").strip()
    except (ImportError, OSError, RuntimeError, ValueError):
        return ""


def is_huggingface_host(url: str) -> bool:
    hostname = (urlparse(url).hostname or "").lower()
    return hostname == "huggingface.co" or hostname.endswith(".huggingface.co")


def request_headers(url: str, *, existing_bytes: int = 0) -> dict[str, str]:
    headers = {"User-Agent": USER_AGENT}
    if existing_bytes:
        headers["Range"] = f"bytes={existing_bytes}-"
    return headers


def authenticated_request(
    url: str,
    *,
    existing_bytes: int = 0,
    hf_token: str = "",
    method: str | None = None,
) -> urllib.request.Request:
    request = urllib.request.Request(
        url,
        headers=request_headers(url, existing_bytes=existing_bytes),
        method=method,
    )
    if hf_token and is_huggingface_host(url):
        # unredirected headers are not copied to the signed object-storage URL.
        request.add_unredirected_header("Authorization", f"Bearer {hf_token}")
    return request


def effective_download_url(url: str, hf_endpoint: str | None = None) -> str:
    endpoint = normalize_hf_endpoint(hf_endpoint) if hf_endpoint is not None else configured_hf_endpoint()
    if not endpoint:
        return url
    parsed = urlparse(url)
    if parsed.hostname != "huggingface.co":
        return url
    mirror = urlparse(endpoint)
    mirror_path = mirror.path.rstrip("/")
    path = f"{mirror_path}{parsed.path}" if mirror_path else parsed.path
    return urlunparse((mirror.scheme, mirror.netloc, path, "", parsed.query, parsed.fragment))


def log(message: str) -> None:
    print(message, flush=True)


def should_skip(item: dict[str, object], profile: str, skip_t2v: bool, skip_loras: bool, skip_post: bool = False) -> bool:
    group = str(item["group"])
    profile_spec = INSTALL_PROFILES.get(profile, INSTALL_PROFILES["cuda-full"])
    allowed_ids = set(profile_spec.get("asset_ids") or [])
    return (
        str(item.get("id") or "") not in allowed_ids
        or (skip_t2v and group == "t2v")
        or (skip_loras and group == "lora")
        or (skip_post and str(item.get("id") or "") in POST_ASSET_IDS)
    )


def selected_model_items(
    profile: str,
    skip_t2v: bool = False,
    skip_loras: bool = False,
    skip_post: bool = False,
) -> list[dict[str, object]]:
    return [
        item
        for item in MODEL_FILES
        if not should_skip(item, profile, skip_t2v=skip_t2v, skip_loras=skip_loras, skip_post=skip_post)
    ]


def file_state(path: Path, expected_bytes: int) -> str:
    if not path.exists():
        return "missing"
    size = path.stat().st_size
    if size == expected_bytes:
        return "complete"
    if size > expected_bytes:
        return "too_large"
    return "partial"


def response_total_bytes(response: object, *, existing_bytes: int = 0) -> int | None:
    """Read the authoritative object size from a download response when available."""
    headers = getattr(response, "headers", None)

    def header(name: str) -> str:
        if headers is None:
            return ""
        try:
            return str(headers.get(name) or "").strip()
        except (AttributeError, TypeError):
            return ""

    content_range = header("Content-Range")
    range_match = re.search(r"/(\d+)\s*$", content_range)
    if range_match:
        return int(range_match.group(1))

    linked_size = header("X-Linked-Size")
    if linked_size.isdigit():
        return int(linked_size)

    content_length = header("Content-Length")
    if not content_length.isdigit():
        return None
    length = int(content_length)
    status = int(getattr(response, "status", 200) or 200)
    return existing_bytes + length if status == 206 else length


def probe_remote_file_size(url: str, hf_token: str = "") -> int | None:
    request = authenticated_request(url, hf_token=hf_token, method="HEAD")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response_total_bytes(response)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None


def installed_alternative_asset(base_dir: Path, item: dict[str, object]) -> Path | None:
    for alternative in item.get("alternatives") or []:
        if not isinstance(alternative, dict):
            continue
        relative = str(alternative.get("dest") or alternative.get("name") or "")
        if not relative:
            continue
        candidate = (base_dir / relative).expanduser().resolve()
        expected = int(alternative.get("bytes") or 0)
        if candidate.is_file() and (not expected or candidate.stat().st_size == expected):
            return candidate
    return None


def looks_like_asset_root(path: Path) -> bool:
    return path.exists() and path.is_dir() and any((path / name).exists() for name in ("models", "custom_nodes", "input"))


def unique_paths(paths: list[Path]) -> list[Path]:
    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        try:
            resolved = path.expanduser().resolve()
        except Exception:
            continue
        key = str(resolved).lower() if os.name == "nt" else str(resolved)
        if key in seen:
            continue
        seen.add(key)
        unique.append(resolved)
    return unique


def env_local_asset_roots() -> list[Path]:
    roots: list[Path] = []
    for name in LOCAL_ASSET_ENV_NAMES:
        value = os.environ.get(name) or ""
        for part in value.split(os.pathsep):
            part = part.strip().strip('"')
            if part:
                roots.append(Path(part))
    return roots


def local_asset_roots(base_dir: Path) -> list[Path]:
    script_root = Path(__file__).resolve().parents[1]
    candidates = env_local_asset_roots()
    for candidate in (script_root.parent, Path.cwd().parent, base_dir.parent):
        if candidate != base_dir and looks_like_asset_root(candidate):
            candidates.append(candidate)
    return unique_paths(candidates)


def candidate_paths_for_item(root: Path, item: dict[str, object]) -> list[Path]:
    dest = Path(str(item["dest"]))
    paths = [root / dest]
    parts = dest.parts
    if parts and parts[0] in {"models", "custom_nodes", "input"}:
        paths.append(root / Path(*parts[1:]))
    paths.append(root / str(item["name"]))
    return unique_paths(paths)


def find_local_asset_candidate(
    item: dict[str, object],
    dest: Path | None = None,
    base_dir: Path | None = None,
    *, recursive: bool = True,
) -> Path | None:
    expected = int(item["bytes"])
    name = str(item["name"])
    base_dir = (base_dir or Path.cwd()).expanduser().resolve()
    dest_resolved = dest.expanduser().resolve() if dest else None
    for root in local_asset_roots(base_dir):
        for candidate in candidate_paths_for_item(root, item):
            if dest_resolved and candidate == dest_resolved:
                continue
            if candidate.is_file() and candidate.stat().st_size == expected:
                return candidate
        if not recursive:
            continue
        try:
            matches = root.rglob(name)
            for candidate in matches:
                if dest_resolved and candidate.resolve() == dest_resolved:
                    continue
                if candidate.is_file() and candidate.stat().st_size == expected:
                    return candidate.resolve()
        except (OSError, PermissionError):
            continue
    return None


def install_from_local_asset(item: dict[str, object], dest: Path, expected_bytes: int, base_dir: Path) -> bool:
    candidate = find_local_asset_candidate(item, dest=dest, base_dir=base_dir)
    if not candidate:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_name(dest.name + ".part")
    partial.unlink(missing_ok=True)
    if dest.exists():
        state = file_state(dest, expected_bytes)
        if state == "complete":
            log(f"[skip] {dest.name}")
            return True
        dest.unlink()
    log(f"[local] {dest.name} <- {candidate}")
    force_copy = os.environ.get("WAN22_COPY_LOCAL_ASSETS") == "1"
    if not force_copy:
        try:
            os.link(candidate, dest)
        except OSError:
            shutil.copy2(candidate, dest)
    else:
        shutil.copy2(candidate, dest)
    actual = dest.stat().st_size
    if actual != expected_bytes:
        raise RuntimeError(f"Local asset size check failed for {dest.name}: got {actual}, expected {expected_bytes}")
    return True


def nearest_existing_path(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if resolved.exists():
        return resolved
    for parent in resolved.parents:
        if parent.exists():
            return parent
    return Path.cwd()


def remaining_bytes_for_item(base_dir: Path, item: dict[str, object]) -> int:
    expected = int(item["bytes"])
    dest = base_dir / str(item["dest"])
    if installed_alternative_asset(base_dir, item):
        return 0
    if dest.exists():
        size = dest.stat().st_size
        if size >= expected:
            return 0
        return expected - size
    if find_local_asset_candidate(item, dest=dest, base_dir=base_dir):
        return 0

    partial = dest.with_name(dest.name + ".part")
    if partial.exists():
        size = min(partial.stat().st_size, expected)
        return expected - size
    return expected


def planned_download_bytes(base_dir: Path, items: list[dict[str, object]]) -> int:
    return sum(remaining_bytes_for_item(base_dir, item) for item in items)


def bytes_to_gb(value: int | float) -> float:
    return round(float(value) / 1024**3, 2)


def gb_to_bytes(value: float) -> int:
    return int(float(value) * 1024**3)


def disk_space_plan(base_dir: Path, required_bytes: int, buffer_bytes: int = SAFETY_BUFFER_BYTES) -> dict[str, object]:
    usage_path = nearest_existing_path(base_dir)
    usage = shutil.disk_usage(usage_path)
    required_with_buffer = required_bytes + (buffer_bytes if required_bytes > 0 else 0)
    return {
        "path": str(usage_path),
        "required_bytes": int(required_bytes),
        "required_gb": bytes_to_gb(required_bytes),
        "buffer_bytes": int(buffer_bytes if required_bytes > 0 else 0),
        "buffer_gb": bytes_to_gb(buffer_bytes if required_bytes > 0 else 0),
        "recommended_free_bytes": int(required_with_buffer),
        "recommended_free_gb": bytes_to_gb(required_with_buffer),
        "free_bytes": int(usage.free),
        "free_gb": bytes_to_gb(usage.free),
        "total_bytes": int(usage.total),
        "total_gb": bytes_to_gb(usage.total),
        "ok": bool(required_bytes == 0 or usage.free >= required_with_buffer),
    }


def log_disk_plan(plan: dict[str, object]) -> None:
    log(
        "[disk] "
        f"free {plan['free_gb']} GB, "
        f"required {plan['required_gb']} GB, "
        f"recommended free {plan['recommended_free_gb']} GB at {plan['path']}"
    )


def download_file(
    url: str,
    dest: Path,
    expected_bytes: int,
    retries: int = 8,
    *,
    hf_token: str = "",
    gated: bool = False,
) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_name(dest.name + ".part")

    def adopt_remote_size(remote_bytes: int | None) -> None:
        nonlocal expected_bytes
        if remote_bytes and remote_bytes > 0 and remote_bytes != expected_bytes:
            previous = expected_bytes
            expected_bytes = remote_bytes
            log(f"[size-update] {dest.name} ({previous} -> {remote_bytes} bytes; using server value)")

    state = file_state(dest, expected_bytes)
    if state == "too_large":
        adopt_remote_size(probe_remote_file_size(url, hf_token))
        state = file_state(dest, expected_bytes)
    if state == "complete":
        partial.unlink(missing_ok=True)
        log(f"[skip] {dest.name}")
        return
    if state == "too_large":
        raise RuntimeError(f"Existing file is larger than expected: {dest}")
    if state == "partial":
        if partial.exists():
            dest.unlink()
        else:
            dest.replace(partial)
    if partial.exists():
        partial_size = partial.stat().st_size
        if partial_size > expected_bytes:
            adopt_remote_size(probe_remote_file_size(url, hf_token))
        if partial_size == expected_bytes:
            partial.replace(dest)
            log(f"[ok] {dest.name} (finalized existing .part)")
            return
        if partial_size > expected_bytes:
            raise RuntimeError(
                f"Partial file is larger than the verified remote size; retained for inspection: "
                f"{partial_size} > {expected_bytes} ({partial})"
            )

    for attempt in range(1, retries + 1):
        existing = partial.stat().st_size if partial.exists() else 0
        mode = "ab" if existing else "wb"
        if existing:
            log(f"[resume] {dest.name} ({existing} / {expected_bytes} bytes)")
        else:
            log(f"[download] {dest.name}")

        request = authenticated_request(
            url,
            existing_bytes=existing,
            hf_token=hf_token,
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                if existing and response.status == 200:
                    log(f"[restart] server ignored resume for {dest.name}")
                    existing = 0
                    mode = "wb"
                adopt_remote_size(response_total_bytes(response, existing_bytes=existing))
                if existing > expected_bytes:
                    raise RuntimeError(
                        f"Partial file exceeds the remote object size; retained for inspection: "
                        f"{existing} > {expected_bytes} ({partial})"
                    )
                last_report = time.time()
                with partial.open(mode) as output:
                    while True:
                        chunk = response.read(1024 * 1024 * 8)
                        if not chunk:
                            break
                        output.write(chunk)
                        now = time.time()
                        if now - last_report > 20:
                            size = partial.stat().st_size
                            pct = min(100.0, size / expected_bytes * 100)
                            log(f"[progress] {dest.name}: {pct:.1f}%")
                            last_report = now
        except urllib.error.HTTPError as exc:
            if gated and exc.code in {401, 403}:
                raise RuntimeError(
                    "LTX 2.5 files require Hugging Face authorization. "
                    "Open https://huggingface.co/Lightricks/LTX-2.5, click Agree and Access, "
                    "then run `hf auth login` or set HF_TOKEN before retrying."
                ) from exc
            if attempt == retries:
                raise
            wait = min(30, 3 * attempt)
            log(f"[retry] {dest.name}: HTTP {exc.code} (wait {wait}s)")
            time.sleep(wait)
            continue
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == retries:
                raise
            wait = min(30, 3 * attempt)
            log(f"[retry] {dest.name}: {exc} (wait {wait}s)")
            time.sleep(wait)
            continue

        actual = partial.stat().st_size if partial.exists() else 0
        if actual == expected_bytes:
            partial.replace(dest)
            log(f"[ok] {dest.name}")
            return
        if actual > expected_bytes:
            raise RuntimeError(
                f"Downloaded file exceeds the verified remote size; .part retained: "
                f"{actual} > {expected_bytes} ({partial})"
            )
        log(f"[retry] incomplete {dest.name}: got {actual}, expected {expected_bytes}")

    raise RuntimeError(f"Could not complete download: {dest.name}")


def run(command: list[str], cwd: Path) -> None:
    log(f"[run] {' '.join(command)}")
    subprocess.run(command, cwd=str(cwd), check=True, **hidden_process_options())


def run_optional(command: list[str], cwd: Path) -> None:
    log(f"[run] {' '.join(command)}")
    result = subprocess.run(command, cwd=str(cwd), **hidden_process_options())
    if result.returncode != 0:
        log(f"[warn] command failed with {result.returncode}; continuing")


def ensure_pip_available(python: Path, cwd: Path) -> None:
    try:
        subprocess.run(
            [str(python), "-m", "pip", "--version"],
            cwd=str(cwd),
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
            **hidden_process_options(),
        )
        return
    except Exception:
        log("[pip] pip is not ready in the ComfyUI environment; running ensurepip")
    run([str(python), "-m", "ensurepip", "--upgrade"], cwd)
    subprocess.run(
        [str(python), "-m", "pip", "--version"],
        cwd=str(cwd),
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=30,
        **hidden_process_options(),
    )


def run_pip(command: list[str], cwd: Path, attempts: int = 3) -> None:
    last_error: subprocess.CalledProcessError | None = None
    for attempt in range(1, attempts + 1):
        try:
            run(command, cwd)
            return
        except subprocess.CalledProcessError as exc:
            last_error = exc
            if attempt >= attempts:
                break
            wait = min(20, 3 * attempt)
            log(f"[retry] pip command failed with {exc.returncode}; wait {wait}s")
            time.sleep(wait)
    assert last_error is not None
    raise last_error


def github_zip_candidates(repo_url: str, ref: str = "") -> list[str]:
    base = repo_url.removesuffix(".git")
    if ref:
        return [f"{base}/archive/{ref}.zip"]
    return [
        f"{base}/archive/refs/heads/main.zip",
        f"{base}/archive/refs/heads/master.zip",
    ]


def download_zip(urls: list[str], dest: Path, retries: int = 3) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_name(dest.name + ".part")
    last_error: Exception | None = None
    for url in urls:
        for attempt in range(1, retries + 1):
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            try:
                log(f"[download] {url}")
                with urllib.request.urlopen(request, timeout=90) as response, partial.open("wb") as output:
                    shutil.copyfileobj(response, output)
                partial.replace(dest)
                return
            except (urllib.error.URLError, TimeoutError) as exc:
                last_error = exc
                partial.unlink(missing_ok=True)
                if attempt == retries:
                    log(f"[warn] zip download failed: {exc}")
                    break
                wait = min(15, 2 * attempt)
                log(f"[retry] zip download failed: {exc} (wait {wait}s)")
                time.sleep(wait)
    raise RuntimeError(f"Could not download custom node zip: {last_error}")


def extract_single_root_zip(zip_path: Path, dest: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="comfy_node_zip_") as temp_name:
        temp_dir = Path(temp_name)
        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(temp_dir)
        roots = [item for item in temp_dir.iterdir() if item.is_dir()]
        if len(roots) != 1:
            raise RuntimeError(f"Unexpected zip layout in {zip_path}")
        dest = dest.expanduser().resolve()
        if dest.exists():
            if not dest.is_dir():
                raise RuntimeError(f"Custom node target exists and is not a directory: {dest}")
            if any(dest.iterdir()):
                raise RuntimeError(f"Custom node target is not empty; refusing to replace it: {dest}")
            dest.rmdir()
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(roots[0]), str(dest))


def install_node_from_zip(repo_url: str, dest: Path, ref: str = "") -> None:
    with tempfile.TemporaryDirectory(prefix="comfy_node_download_") as temp_name:
        zip_path = Path(temp_name) / "node.zip"
        download_zip(github_zip_candidates(repo_url, ref), zip_path)
        extract_single_root_zip(zip_path, dest)
    log(f"[ok] installed {dest.name} from zip")


def install_node_requirements(requirements: Path, comfy_python: Path | None) -> None:
    if comfy_python and comfy_python.exists():
        ensure_pip_available(comfy_python, requirements.parent)
        run_pip([str(comfy_python), "-m", "pip", "install", "-r", str(requirements)], requirements.parent)
        return
    log(
        f"[warn] {requirements.parent.name} has requirements.txt, but ComfyUI Python was not found. "
        "Install these requirements in the ComfyUI Python environment, then restart ComfyUI."
    )


def python_imports_ready(python: Path | None, imports: list[str], cwd: Path) -> bool:
    if not python or not python.exists() or not imports:
        return False
    command = [str(python), "-c", "; ".join(f"import {name}" for name in imports)]
    result = subprocess.run(
        command,
        cwd=str(cwd),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **hidden_process_options(),
    )
    return result.returncode == 0


def install_node_dependencies(repo: dict[str, object], dest: Path, comfy_python: Path | None) -> None:
    install_script = str(repo.get("install_script") or "").strip()
    if install_script:
        script = dest / install_script
        if not script.is_file():
            raise RuntimeError(f"Custom node install script is missing: {script}")
        if not comfy_python or not comfy_python.exists():
            log(
                f"[warn] {dest.name} requires {install_script}, but ComfyUI Python was not found. "
                "Run the script with the ComfyUI Python environment, then restart ComfyUI."
            )
            return
        ensure_pip_available(comfy_python, dest)
        installer_packages = [str(item).strip() for item in repo.get("installer_packages") or [] if str(item).strip()]
        if installer_packages:
            log(f"[bootstrap] {dest.name} installer packages: {', '.join(installer_packages)}")
            run_pip(
                [str(comfy_python), "-m", "pip", "install", "--disable-pip-version-check", *installer_packages],
                dest,
            )
        run([str(comfy_python), str(script)], dest)
        requirements = dest / "requirements.txt"
        checked_packages = [str(item).strip() for item in repo.get("checked_packages") or [] if str(item).strip()]
        no_deps_packages = [str(item).strip() for item in repo.get("no_deps_packages") or [] if str(item).strip()]
        if checked_packages:
            log(f"[verify] {dest.name} checked packages: {', '.join(checked_packages)}")
            run_pip([str(comfy_python), "-m", "pip", "install", *checked_packages], dest)
        if no_deps_packages:
            log(f"[verify] {dest.name} packages reusing ComfyUI dependencies: {', '.join(no_deps_packages)}")
            run_pip([str(comfy_python), "-m", "pip", "install", "--no-deps", *no_deps_packages], dest)
        if requirements.is_file() and not checked_packages and not no_deps_packages:
            log(f"[verify] installing {dest.name} requirements with checked exit status")
            install_node_requirements(requirements, comfy_python)
        verify_imports = [str(item).strip() for item in repo.get("verify_imports") or [] if str(item).strip()]
        if verify_imports:
            import_check = "; ".join(f"import {name}" for name in verify_imports)
            log(f"[verify] {dest.name} imports: {', '.join(verify_imports)}")
            run([str(comfy_python), "-c", import_check], dest)
        return
    requirements = dest / "requirements.txt"
    verify_imports = [str(item).strip() for item in repo.get("verify_imports") or [] if str(item).strip()]
    if requirements.exists():
        if python_imports_ready(comfy_python, verify_imports, dest):
            log(f"[skip] {dest.name} Python imports already available: {', '.join(verify_imports)}")
        else:
            install_node_requirements(requirements, comfy_python)
    if verify_imports and comfy_python:
        import_check = "; ".join(f"import {name}" for name in verify_imports)
        log(f"[verify] {dest.name} imports: {', '.join(verify_imports)}")
        run([str(comfy_python), "-c", import_check], dest)


def checkout_repo_ref(git: str, dest: Path, ref: str) -> None:
    if not ref:
        return
    run([git, "fetch", "--depth", "1", "origin", ref], dest)
    run([git, "checkout", "--detach", ref], dest)


QWEN21_GGUF_NORM_ANCHOR = (
    "        # 1D tensors shouldn't be quantized, this is a fix for BF16\n"
    "        if len(shape) <= 1 and tensor.tensor_type == gguf.GGMLQuantizationType.BF16:\n"
    "            state_dict[sd_key] = dequantize_tensor(state_dict[sd_key], dtype=torch.float32)\n"
)
QWEN21_GGUF_NORM_PATCH = (
    "\n"
    "        # Qwen 2.1 fused RMS/RoPE reads norm weights without GGUF operations.\n"
    "        if arch_str == \"qwen_image21\" and len(shape) <= 1:\n"
    "            state_dict[sd_key] = dequantize_tensor(\n"
    "                state_dict[sd_key], dtype=torch.float32, dequant_dtype=torch.float32,\n"
    "            ).as_subclass(torch.Tensor)\n"
)


def apply_custom_node_compatibility(repo: dict[str, object], dest: Path) -> bool:
    if repo.get("id") != "gguf_qwen21":
        return False
    loader = dest / "loader.py"
    original = loader.read_bytes()
    newline = "\r\n" if b"\r\n" in original else "\n"
    source = original.decode("utf-8").replace("\r\n", "\n")
    if QWEN21_GGUF_NORM_PATCH in source:
        log("[skip] Qwen 2.1 GGUF norm compatibility fix already installed")
        return False
    if source.count(QWEN21_GGUF_NORM_ANCHOR) != 1:
        raise RuntimeError("GGUF loader differs from the pinned version; refusing to apply the Qwen 2.1 norm fix")
    updated = source.replace(QWEN21_GGUF_NORM_ANCHOR, QWEN21_GGUF_NORM_ANCHOR + QWEN21_GGUF_NORM_PATCH, 1)
    compile(updated, str(loader), "exec")
    backup = loader.with_name("loader.py.before-qwen21-norm-fix")
    if not backup.exists():
        shutil.copy2(loader, backup)
    loader.write_bytes(updated.replace("\n", newline).encode("utf-8"))
    log("[compat] Qwen 2.1 GGUF norm vectors decoded on CPU; restart ComfyUI to apply")
    return True


def ensure_custom_nodes(
    base_dir: Path,
    *,
    profile: str = "cuda-full",
    comfy_python: Path | None = None,
    install_requirements: bool = True,
    skip_post: bool = False,
) -> None:
    custom_nodes_dir = base_dir / "custom_nodes"
    custom_nodes_dir.mkdir(parents=True, exist_ok=True)
    git = shutil.which("git")

    profile_spec = INSTALL_PROFILES.get(profile, INSTALL_PROFILES["cuda-full"])
    allowed_ids = set(profile_spec.get("custom_node_ids") or [])
    if skip_post:
        allowed_ids -= set(OPTIONAL_POST_NODE_IDS)
    for repo in CUSTOM_NODE_REPOS:
        if str(repo.get("id") or "") not in allowed_ids:
            continue
        dest = base_dir / str(repo["dest"])
        ref = str(repo.get("ref") or "").strip()
        if dest.exists() and str(repo.get("id")) in profile_spec.get("preserve_existing_node_ids", []):
            log(f"[keep] {repo['name']}: preserving existing shared node and dependencies")
            continue
        if dest.exists():
            if git and (dest / ".git").exists():
                if ref:
                    log(f"[pin] {repo['name']} -> {ref[:12]}")
                    checkout_repo_ref(git, dest, ref)
                else:
                    log(f"[update] {repo['name']}")
                    run_optional([git, "pull", "--ff-only"], dest)
            else:
                log(f"[skip] {repo['name']}")
        else:
            if not git:
                log(f"[warn] git not found; downloading {repo['name']} source zip instead.")
                install_node_from_zip(str(repo["url"]), dest, ref)
            else:
                try:
                    run([git, "clone", "--depth", "1", str(repo["url"]), str(dest)], custom_nodes_dir)
                    checkout_repo_ref(git, dest, ref)
                except subprocess.CalledProcessError as exc:
                    log(f"[warn] git clone failed with {exc.returncode}; downloading {repo['name']} source zip instead.")
                    if dest.exists():
                        log(f"[cleanup] removing incomplete clone target: {dest}")
                        shutil.rmtree(dest)
                    install_node_from_zip(str(repo["url"]), dest, ref)
        apply_custom_node_compatibility(repo, dest)
        if install_requirements:
            install_node_dependencies(repo, dest, comfy_python)


def required_asset_paths(base_dir: Path, item: dict[str, object]) -> list[Path]:
    return [base_dir / str(relative) for relative in item.get("required_paths") or [] if str(relative)]


def required_asset_paths_ready(base_dir: Path, item: dict[str, object]) -> bool:
    required = required_asset_paths(base_dir, item)
    return not required or all(path.is_file() and path.stat().st_size > 0 for path in required)


def extract_zip_asset(archive_path: Path, target_dir: Path, *, strip_single_root: bool = False) -> None:
    with tempfile.TemporaryDirectory(prefix="workflow_asset_extract_") as temp_name:
        temp_dir = Path(temp_name).resolve()
        with zipfile.ZipFile(archive_path) as archive:
            for member in archive.infolist():
                candidate = (temp_dir / member.filename).resolve()
                if temp_dir != candidate and temp_dir not in candidate.parents:
                    raise RuntimeError(f"Unsafe archive path in {archive_path.name}: {member.filename}")
            archive.extractall(temp_dir)
        source_dir = temp_dir
        entries = [item for item in temp_dir.iterdir() if item.name != "__MACOSX"]
        if strip_single_root and len(entries) == 1 and entries[0].is_dir():
            source_dir = entries[0]
        target_dir.mkdir(parents=True, exist_ok=True)
        for source in source_dir.iterdir():
            destination = target_dir / source.name
            if source.is_dir():
                shutil.copytree(source, destination, dirs_exist_ok=True)
            else:
                shutil.copy2(source, destination)


def finalize_model_asset(base_dir: Path, item: dict[str, object], archive_path: Path) -> None:
    archive_type = str(item.get("archive") or "").strip().lower()
    if not archive_type:
        return
    if required_asset_paths_ready(base_dir, item):
        log(f"[skip] extracted files for {archive_path.name}")
        return
    if archive_type != "zip":
        raise RuntimeError(f"Unsupported asset archive type: {archive_type}")
    extract_to = str(item.get("extract_to") or "").strip()
    if not extract_to:
        raise RuntimeError(f"Archive asset has no extract_to path: {archive_path.name}")
    log(f"[extract] {archive_path.name} -> {extract_to}")
    extract_zip_asset(
        archive_path,
        base_dir / extract_to,
        strip_single_root=bool(item.get("strip_single_root")),
    )
    missing = [str(path) for path in required_asset_paths(base_dir, item) if not path.is_file()]
    if missing:
        raise RuntimeError(f"Archive extraction did not create required files: {', '.join(missing)}")
    log(f"[ok] extracted {archive_path.name}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Install or check local AI video workflow assets.")
    parser.add_argument("--base-dir", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument(
        "--custom-nodes-base-dir",
        type=Path,
        default=None,
        help="Optional active ComfyUI base used for custom_nodes while model assets use --base-dir.",
    )
    parser.add_argument(
        "--profile",
        choices=sorted(profile_id for profile_id, item in INSTALL_PROFILES.items() if item.get("installable")),
        default="cuda-full",
        help="Canonical model/install profile to prepare.",
    )
    parser.add_argument(
        "--asset-id",
        action="append",
        choices=sorted(str(item.get("id") or "") for item in MODEL_FILES if item.get("id")),
        default=[],
        help="Install or resume only this registered asset. May be repeated.",
    )
    parser.add_argument("--comfy-python", type=Path, default=None, help="Python executable used by ComfyUI for custom node requirements.")
    parser.add_argument("--skip-t2v", action="store_true", help="Skip optional T2V A14B files.")
    parser.add_argument("--skip-loras", action="store_true", help="Skip 4-step acceleration LoRAs.")
    parser.add_argument("--skip-post", action="store_true", help="Skip RIFE/upscale post-pack weights and interpolation nodes.")
    parser.add_argument("--no-custom-nodes", action="store_true", help="Do not clone missing ComfyUI custom node repos.")
    parser.add_argument("--no-node-requirements", action="store_true", help="Do not install custom node requirements.")
    parser.add_argument("--dry-run", action="store_true", help="Print the install and disk-space plan without downloading.")
    parser.add_argument("--min-free-gb", type=float, default=10.0, help="Extra free disk space to keep after model downloads.")
    parser.add_argument(
        "--direct-download",
        type=Path,
        default=None,
        help="JSON file describing arbitrary files to download: {\"files\": [{name, url, dest, expected_bytes}]}. Skips profile/manifest logic.",
    )
    return parser.parse_args()


def run_direct_download(spec_path: Path) -> int:
    """用户从 Hugging Face / Civitai 在线导入的模型走这里：清单外的任意 URL 下载。

    复用 download_file 的 .part 断点续传、重试与 HF 镜像/令牌逻辑，
    日志格式与清单安装一致，前端进度解析无需改动。
    """
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    files = spec.get("files") or []
    if not files:
        raise RuntimeError("Direct download spec has no files")
    hf_token = configured_hf_token()
    failures: list[str] = []
    for item in files:
        name = str(item.get("name") or "").strip()
        url = str(item.get("url") or "").strip()
        dest = Path(str(item.get("dest") or "")).expanduser()
        expected_bytes = int(item.get("expected_bytes") or 0)
        if not name or not url or not str(dest):
            failures.append(f"invalid entry: {item}")
            continue
        if dest.is_file() and (not expected_bytes or dest.stat().st_size == expected_bytes):
            log(f"[skip] {name} already exists")
            continue
        log(f"[download] {name}")
        try:
            download_file(effective_download_url(url), dest, expected_bytes, hf_token=hf_token)
        except Exception as exc:  # noqa: BLE001 - 单文件失败不阻断其余文件
            failures.append(f"{name}: {exc}")
            log(f"[error] {name}: {exc}")
    if failures:
        raise RuntimeError("Direct download failed for: " + "; ".join(failures[:5]))
    log("[done] direct download complete")
    return 0


def main() -> int:
    args = parse_args()
    if args.direct_download:
        return run_direct_download(args.direct_download.resolve())
    base_dir = args.base_dir.resolve()
    custom_nodes_base_dir = args.custom_nodes_base_dir.resolve() if args.custom_nodes_base_dir else base_dir
    log(f"[base] {base_dir}")
    if custom_nodes_base_dir != base_dir:
        log(f"[custom-nodes-base] {custom_nodes_base_dir}")
    log(f"[profile] {args.profile}")
    hf_endpoint = configured_hf_endpoint()
    hf_token = configured_hf_token()
    if hf_endpoint:
        log(f"[download-source] Hugging Face endpoint: {hf_endpoint}")
    local_roots = local_asset_roots(base_dir)
    if local_roots:
        log("[local-assets] " + "; ".join(str(path) for path in local_roots))

    comfy_python = args.comfy_python.resolve() if args.comfy_python else None
    if comfy_python:
        log(f"[comfy-python] {comfy_python}")

    profile_items = selected_model_items(
        args.profile,
        skip_t2v=args.skip_t2v,
        skip_loras=args.skip_loras,
        skip_post=args.skip_post,
    )
    requested_asset_ids = {str(item) for item in args.asset_id or []}
    available_asset_ids = {str(item.get("id") or "") for item in profile_items}
    unavailable_asset_ids = requested_asset_ids - available_asset_ids
    if unavailable_asset_ids:
        raise RuntimeError(
            f"Assets are not part of profile {args.profile}: {', '.join(sorted(unavailable_asset_ids))}"
        )
    model_items = [item for item in profile_items if not requested_asset_ids or str(item.get("id") or "") in requested_asset_ids]
    gated_items = [item for item in model_items if bool(item.get("gated"))]
    if gated_items:
        if hf_token:
            log("[hugging-face] authentication token detected")
        else:
            log(
                "[hugging-face] gated files selected; accept the model license and run "
                "`hf auth login` or set HF_TOKEN before downloading"
            )
    if args.skip_post:
        log("[skip-post] excluding RIFE/upscale weights and interpolation nodes")
    if requested_asset_ids:
        log(f"[asset-resume] targeted assets: {', '.join(sorted(requested_asset_ids))}")
    required_bytes = planned_download_bytes(base_dir, model_items)
    disk_plan = disk_space_plan(base_dir, required_bytes, gb_to_bytes(args.min_free_gb))
    log(f"[plan] model files in profile: {len(model_items)}")
    log_disk_plan(disk_plan)
    if args.dry_run:
        log("[dry-run] no files were downloaded or changed.")
        return 0
    if not disk_plan["ok"]:
        raise RuntimeError(
            "Not enough free disk space. "
            f"Need about {disk_plan['recommended_free_gb']} GB free, "
            f"but only {disk_plan['free_gb']} GB is available at {disk_plan['path']}."
        )

    for item in model_items:
        dest = base_dir / str(item["dest"])
        expected_bytes = int(item["bytes"])
        alternative = installed_alternative_asset(base_dir, item)
        if alternative:
            log(f"[skip] compatible asset already installed: {alternative.name}")
            continue
        if not install_from_local_asset(item, dest, expected_bytes, base_dir):
            download_file(
                effective_download_url(str(item["url"]), hf_endpoint),
                dest,
                expected_bytes,
                hf_token=hf_token,
                gated=bool(item.get("gated")),
            )
        finalize_model_asset(base_dir, item, dest)

    profile_nodes = INSTALL_PROFILES.get(args.profile, {}).get("custom_node_ids") or []
    if requested_asset_ids:
        log("[skip] targeted asset resume does not reinstall custom nodes")
    elif not args.no_custom_nodes and profile_nodes:
        ensure_custom_nodes(
            custom_nodes_base_dir,
            profile=args.profile,
            comfy_python=comfy_python,
            install_requirements=not args.no_node_requirements,
            skip_post=args.skip_post,
        )
    elif not profile_nodes:
        log(f"[skip] custom nodes are not required for profile {args.profile}")

    log("Workflow assets are installed and verified.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        log("Interrupted.")
        raise
    except Exception as exc:
        log(f"[error] {exc}")
        raise SystemExit(1)
