from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path


COMFY_REPO = "https://github.com/Comfy-Org/ComfyUI.git"
COMFY_ZIP_CANDIDATES = [
    "https://github.com/Comfy-Org/ComfyUI/archive/refs/heads/master.zip",
    "https://github.com/Comfy-Org/ComfyUI/archive/refs/heads/main.zip",
]
USER_AGENT = "local-ai-video-workbench/1.0"
GB = 1024**3
BACKEND_MIN_FREE_GB = {
    "cuda": 20.0,
    "mps": 8.0,
    "cpu": 8.0,
    "skip": 3.0,
}


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


def log(message: str) -> None:
    print(message, flush=True)


def effective_backend(backend: str) -> str:
    if backend != "auto":
        return backend
    if platform.system() == "Darwin":
        return "mps"
    if has_nvidia_gpu():
        return "cuda"
    return "cpu"


def has_nvidia_gpu() -> bool:
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return False
    try:
        result = subprocess.run(
            [nvidia_smi, "-L"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
            **hidden_process_options(),
        )
    except Exception:
        return False
    text = f"{result.stdout}\n{result.stderr}".lower()
    return result.returncode == 0 and ("gpu " in text or "nvidia" in text)


def nearest_existing_path(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if resolved.exists():
        return resolved
    for parent in resolved.parents:
        if parent.exists():
            return parent
    return Path.cwd()


def bytes_to_gb(value: int | float) -> float:
    return round(float(value) / GB, 2)


def comfyui_disk_plan(install_dir: Path, backend: str = "auto", min_free_gb: float | None = None) -> dict[str, object]:
    resolved_backend = effective_backend(backend)
    required_gb = float(min_free_gb if min_free_gb is not None else BACKEND_MIN_FREE_GB.get(resolved_backend, 10.0))
    usage_path = nearest_existing_path(install_dir)
    usage = shutil.disk_usage(usage_path)
    required_bytes = int(required_gb * GB)
    return {
        "path": str(usage_path),
        "backend": resolved_backend,
        "recommended_free_gb": round(required_gb, 2),
        "recommended_free_bytes": required_bytes,
        "free_gb": bytes_to_gb(usage.free),
        "free_bytes": int(usage.free),
        "total_gb": bytes_to_gb(usage.total),
        "total_bytes": int(usage.total),
        "ok": bool(usage.free >= required_bytes),
    }


def log_disk_plan(plan: dict[str, object]) -> None:
    log(
        "[disk] "
        f"free {plan['free_gb']} GB, "
        f"recommended free {plan['recommended_free_gb']} GB, "
        f"backend {plan['backend']} at {plan['path']}"
    )


def run(command: list[str], cwd: Path | None = None) -> None:
    log(f"[run] {' '.join(command)}")
    subprocess.run(command, cwd=str(cwd) if cwd else None, check=True, **hidden_process_options())


def run_optional(command: list[str], cwd: Path | None = None) -> bool:
    log(f"[run] {' '.join(command)}")
    result = subprocess.run(command, cwd=str(cwd) if cwd else None, check=False, **hidden_process_options())
    if result.returncode != 0:
        log(f"[warn] command failed with {result.returncode}; continuing")
        return False
    return True


def ensure_pip_available(python: Path, cwd: Path | None = None) -> None:
    try:
        subprocess.run(
            [str(python), "-m", "pip", "--version"],
            cwd=str(cwd) if cwd else None,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
            **hidden_process_options(),
        )
        return
    except Exception:
        log("[pip] pip is not ready; running ensurepip")
    run([str(python), "-m", "ensurepip", "--upgrade"], cwd)
    subprocess.run(
        [str(python), "-m", "pip", "--version"],
        cwd=str(cwd) if cwd else None,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=30,
        **hidden_process_options(),
    )


def run_pip(command: list[str], cwd: Path | None = None, attempts: int = 3) -> None:
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
    raise RuntimeError(f"Could not download ComfyUI zip: {last_error}")


def extract_single_root_zip(zip_path: Path, dest: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="comfyui_zip_") as temp_name:
        temp_dir = Path(temp_name)
        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(temp_dir)
        roots = [item for item in temp_dir.iterdir() if item.is_dir()]
        if len(roots) != 1:
            raise RuntimeError(f"Unexpected zip layout in {zip_path}")
        dest = dest.expanduser().resolve()
        if dest.exists():
            if not dest.is_dir():
                raise RuntimeError(f"Install target exists and is not a directory: {dest}")
            if any(dest.iterdir()):
                raise RuntimeError(f"Install target is not empty; refusing to replace it: {dest}")
            dest.rmdir()
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(roots[0]), str(dest))


def install_repo_from_zip(install_dir: Path) -> None:
    install_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="comfyui_download_") as temp_name:
        zip_path = Path(temp_name) / "comfyui.zip"
        download_zip(COMFY_ZIP_CANDIDATES, zip_path)
        extract_single_root_zip(zip_path, install_dir)
    log(f"[ok] ComfyUI zip installed at {install_dir}")


def venv_python(venv: Path) -> Path:
    if platform.system() == "Windows":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def install_torch_command(python: Path, backend: str) -> list[str] | None:
    if backend == "skip":
        return None
    backend = effective_backend(backend)
    if backend == "cuda":
        return [
            str(python),
            "-m",
            "pip",
            "install",
            "torch",
            "torchvision",
            "torchaudio",
            "--index-url",
            "https://download.pytorch.org/whl/cu130",
        ]
    if backend == "cpu":
        return [
            str(python),
            "-m",
            "pip",
            "install",
            "torch",
            "torchvision",
            "torchaudio",
            "--index-url",
            "https://download.pytorch.org/whl/cpu",
        ]
    if backend == "mps":
        return [str(python), "-m", "pip", "install", "torch", "torchvision", "torchaudio"]
    raise ValueError(f"Unknown backend: {backend}")


def ensure_repo(install_dir: Path) -> None:
    git = shutil.which("git")
    if (install_dir / ".git").exists():
        if not git:
            log(f"[warn] git not found; using existing ComfyUI repo without updating: {install_dir}")
            return
        log(f"[update] {install_dir}")
        if not run_optional([git, "pull", "--ff-only"], install_dir):
            log("[warn] git pull failed; using the existing ComfyUI source already on disk.")
        return

    if (install_dir / "main.py").exists():
        log(f"[reuse] existing ComfyUI source without git metadata: {install_dir}")
        return

    if install_dir.exists() and any(install_dir.iterdir()):
        raise RuntimeError(f"Install directory is not empty and is not a git repo: {install_dir}")

    install_dir.parent.mkdir(parents=True, exist_ok=True)
    if not git:
        log("[warn] git not found; downloading ComfyUI source zip instead.")
        install_repo_from_zip(install_dir)
        return

    log(f"[clone] {COMFY_REPO} -> {install_dir}")
    try:
        run([git, "clone", "--depth", "1", COMFY_REPO, str(install_dir)])
    except subprocess.CalledProcessError as exc:
        log(f"[warn] git clone failed with {exc.returncode}; downloading ComfyUI source zip instead.")
        if install_dir.exists():
            log(f"[cleanup] removing incomplete clone target: {install_dir}")
            shutil.rmtree(install_dir)
        install_repo_from_zip(install_dir)


def ensure_venv(install_dir: Path) -> Path:
    venv = install_dir / ".venv"
    python = venv_python(venv)
    if not python.exists():
        log(f"[venv] creating {venv}")
        run([sys.executable, "-m", "venv", str(venv)])
    return python


def ensure_base_dirs(base_dir: Path) -> None:
    for name in ("models", "input", "output", "temp", "custom_nodes", "user"):
        (base_dir / name).mkdir(parents=True, exist_ok=True)


def ensure_supported_python() -> None:
    if not ((3, 10) <= sys.version_info[:2] <= (3, 12)):
        version = ".".join(str(part) for part in sys.version_info[:3])
        raise RuntimeError(
            f"Python {version} is not supported for this installer. "
            "Use Python 3.10, 3.11, or 3.12 for ComfyUI/PyTorch."
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Install or update ComfyUI for the local video workflow.")
    parser.add_argument("--base-dir", type=Path, required=True)
    parser.add_argument("--install-dir", type=Path, required=True)
    parser.add_argument(
        "--backend",
        choices=["auto", "cuda", "cpu", "mps", "skip"],
        default="auto",
        help="PyTorch backend to install. Use skip if your ComfyUI venv already has torch.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print the install and disk-space plan without changing files.")
    parser.add_argument("--min-free-gb", type=float, default=None, help="Override the recommended free space check.")
    return parser.parse_args()


def main() -> int:
    ensure_supported_python()
    args = parse_args()
    base_dir = args.base_dir.expanduser().resolve()
    install_dir = args.install_dir.expanduser().resolve()

    log(f"[base] {base_dir}")
    log(f"[install] {install_dir}")
    log(f"[backend] {args.backend}")

    disk_plan = comfyui_disk_plan(install_dir, args.backend, args.min_free_gb)
    log_disk_plan(disk_plan)
    if args.dry_run:
        log("[dry-run] no files were changed.")
        return 0
    if not disk_plan["ok"]:
        raise RuntimeError(
            "Not enough free disk space for ComfyUI/PyTorch install. "
            f"Need about {disk_plan['recommended_free_gb']} GB free, "
            f"but only {disk_plan['free_gb']} GB is available at {disk_plan['path']}."
        )

    ensure_base_dirs(base_dir)
    ensure_repo(install_dir)
    python = ensure_venv(install_dir)

    ensure_pip_available(python)
    run_pip([str(python), "-m", "pip", "install", "-U", "pip"])
    torch_command = install_torch_command(python, args.backend)
    if torch_command:
        run_pip(torch_command)
    else:
        log("[torch] skipped")

    requirements = install_dir / "requirements.txt"
    if not requirements.exists():
        raise RuntimeError(f"ComfyUI requirements.txt not found: {requirements}")
    run_pip([str(python), "-m", "pip", "install", "-r", str(requirements)], install_dir)

    log("ComfyUI install/update complete.")
    log("Next: start ComfyUI from the frontend, then install workflow assets.")
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
