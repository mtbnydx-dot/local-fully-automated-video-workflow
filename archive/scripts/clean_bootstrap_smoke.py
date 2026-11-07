from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PACKAGE = ROOT / "github_upload" / "wan22-local-video-workflow"


def package_source() -> Path:
    return DEFAULT_PACKAGE if DEFAULT_PACKAGE.exists() else ROOT


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def ignore_names(_: str, names: list[str]) -> set[str]:
    blocked = {
        ".git",
        ".venv",
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
    suffixes = (
        ".pyc",
        ".pyo",
        ".log",
        ".safetensors",
        ".pth",
        ".pt",
        ".ckpt",
        ".gguf",
        ".bin",
        ".onnx",
        ".zip",
        ".tar",
        ".tar.gz",
        ".tgz",
        ".7z",
        ".rar",
        ".mp4",
        ".mov",
        ".mkv",
        ".webm",
        ".avi",
        ".part",
    )
    return {name for name in names if name in blocked or name.lower().endswith(suffixes)}


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def get_json(url: str, timeout: float = 5.0) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def wait_for_json(url: str, seconds: int) -> dict[str, Any]:
    deadline = time.time() + seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            return get_json(url, timeout=3)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            time.sleep(1)
    raise RuntimeError(f"Timed out waiting for {url}: {last_error}")


def venv_python(venv: Path) -> Path:
    if os.name == "nt":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def tail(path: Path, limit: int = 8000) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    return text[-limit:]


def terminate_process(process: subprocess.Popen[Any]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=15)
        return
    process.terminate()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=15)


def smoke(source: Path, keep_temp: bool = False, timeout: int = 300) -> dict[str, Any]:
    source = source.resolve()
    if not source.exists():
        raise RuntimeError(f"Source package does not exist: {source}")

    temp_root = Path(tempfile.mkdtemp(prefix="wan22_clean_bootstrap_"))
    copied = temp_root / "package"
    log_path = temp_root / "START_WORKFLOW.log"
    process: subprocess.Popen[Any] | None = None
    try:
        shutil.copytree(source, copied, ignore=ignore_names)
        if (copied / ".venv").exists():
            raise RuntimeError("Clean package copy unexpectedly contains .venv")

        frontend_port = free_port()
        comfy_port = free_port()
        env = os.environ.copy()
        env.update(
            {
                "PYTHONDONTWRITEBYTECODE": "1",
                "WAN22_NO_INTERACTIVE_RETRY": "1",
                "COMFY_BASE_DIR": str(temp_root / "comfy_base"),
                "COMFY_INSTALL_DIR": str(temp_root / "ComfyUI"),
                "COMFY_URL": f"http://127.0.0.1:{comfy_port}",
                "BEGINNER_FRONTEND_URL": f"http://127.0.0.1:{frontend_port}",
            }
        )
        command = [sys.executable, "START_WORKFLOW.py", "--no-browser"]
        log(f"[clean-bootstrap] {' '.join(command)}")
        with log_path.open("w", encoding="utf-8", errors="replace") as log_file:
            process = subprocess.Popen(
                command,
                cwd=str(copied),
                env=env,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

            base_url = f"http://127.0.0.1:{frontend_port}"
            health = wait_for_json(f"{base_url}/api/health", seconds=timeout)
            bootstrap = get_json(f"{base_url}/api/bootstrap", timeout=30)
            environment = get_json(f"{base_url}/api/environment", timeout=30)
            if not health.get("ok"):
                raise RuntimeError(f"Health endpoint did not report ok: {health}")
            if not (copied / ".venv").exists():
                raise RuntimeError("Launcher did not create .venv in the clean package copy")
            python = venv_python(copied / ".venv")
            if not python.exists():
                raise RuntimeError(f"Launcher created .venv but Python is missing: {python}")
            log_file.flush()
            result = {
                "ok": True,
                "source": str(source),
                "temp_package": str(copied),
                "frontend_url": base_url,
                "created_venv": True,
                "venv_python": str(python),
                "app_version": health.get("app_version"),
                "workspace_dir": health.get("workspace_dir"),
                "bootstrap_connected": bool(bootstrap.get("connected")),
                "install_profile": environment.get("install_profile"),
                "platform_strategy": (environment.get("hardware") or {}).get("platform_strategy"),
                "log_tail": tail(log_path),
            }
            return result
    except Exception as exc:
        if process is not None:
            terminate_process(process)
        raise RuntimeError(f"{exc}\nLauncher log tail:\n{tail(log_path)}") from exc
    finally:
        if process is not None:
            terminate_process(process)
        if keep_temp:
            log(f"[keep] {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify that a clean release package with no .venv can bootstrap and start the frontend."
    )
    parser.add_argument("--source", type=Path, default=package_source(), help="Release package directory to test.")
    parser.add_argument("--timeout", type=int, default=300, help="Seconds to wait for the frontend to become ready.")
    parser.add_argument("--keep-temp", action="store_true", help="Keep the temporary package and venv for debugging.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()
    try:
        result = smoke(args.source, keep_temp=args.keep_temp, timeout=args.timeout)
    except Exception as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        else:
            print(f"CLEAN BOOTSTRAP SMOKE FAILED: {exc}")
        return 1
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("CLEAN BOOTSTRAP SMOKE OK")
        print(f"- package: {result['source']}")
        print(f"- frontend: {result['frontend_url']}")
        print(f"- venv python: {result['venv_python']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
