from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


GB = 1024**3
REQUIRED_FRONTEND_MODULES = {
    "fastapi": "fastapi",
    "uvicorn": "uvicorn",
    "httpx": "httpx",
    "python-multipart": "multipart",
    "Pillow": "PIL",
    "OpenCV": "cv2",
}
OPTIONAL_FRONTEND_MODULES = {
    "imageio-ffmpeg": "imageio_ffmpeg",
}
DOWNLOAD_HOSTS = {
    "github.com": "GitHub",
    "huggingface.co": "Hugging Face",
    "pypi.org": "PyPI",
    "download.pytorch.org": "PyTorch 下载源",
}
DOWNLOAD_URLS = {
    "github.com": "https://github.com/",
    "huggingface.co": "https://huggingface.co/",
    "pypi.org": "https://pypi.org/",
    "download.pytorch.org": "https://download.pytorch.org/",
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
HF_ENDPOINT_ENV_NAMES = ("LOCAL_AI_HF_ENDPOINT", "WAN22_HF_ENDPOINT", "HF_ENDPOINT")
PROXY_ENV_NAMES = ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "https_proxy", "http_proxy", "all_proxy")
PIP_INDEX_ENV_NAMES = ("PIP_INDEX_URL", "pip_index_url")
USER_AGENT = "local-ai-video-workbench/2026"
WORKSPACE_DIR = Path(__file__).resolve().parents[1]


def bytes_to_gb(value: int | float) -> float:
    return round(float(value) / GB, 2)


def nearest_existing_path(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if resolved.exists():
        return resolved
    for parent in resolved.parents:
        if parent.exists():
            return parent
    return Path.cwd()


def command_exists(command: str) -> bool:
    return bool(shutil.which(command))


def looks_like_comfy_base(path: Path) -> bool:
    return all((path / name).exists() for name in ("models", "input", "output", "custom_nodes"))


def default_base_dir(workspace: Path) -> Path:
    configured = os.environ.get("COMFY_BASE_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    parent = workspace.parent
    if looks_like_comfy_base(parent):
        return parent.resolve()
    return workspace.resolve()


def default_install_dir(base_dir: Path) -> Path:
    configured = os.environ.get("COMFY_INSTALL_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    return (base_dir / "ComfyUI").expanduser().resolve()


def desktop_comfy_main_candidates(install_dir: Path) -> list[Path]:
    return [
        install_dir / "resources" / "ComfyUI" / "main.py",
        install_dir / "Contents" / "Resources" / "ComfyUI" / "main.py",
        install_dir / "Comfy Desktop" / "resources" / "ComfyUI" / "main.py",
    ]


def desktop_comfy_executable_candidates(install_dir: Path) -> list[Path]:
    return [
        install_dir / "ComfyUI.exe",
        install_dir / "ComfyUI",
        install_dir / "ComfyUI.app",
    ]


def looks_like_comfy_desktop_runtime(install_dir: Path) -> bool:
    return any(path.exists() for path in desktop_comfy_main_candidates(install_dir)) or any(
        path.exists() for path in desktop_comfy_executable_candidates(install_dir)
    )


def command_version(command: list[str], timeout: int = 8) -> str:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            **hidden_process_options(),
        )
    except Exception as exc:
        return str(exc)
    text = (result.stdout or result.stderr or "").strip().splitlines()
    return text[0] if text else f"exit {result.returncode}"


def url_reachable(url: str, timeout: float = 5.0) -> bool:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout):
            return True
    except urllib.error.HTTPError as exc:
        return 100 <= int(exc.code) < 500
    except Exception:
        return False


def normalize_hf_endpoint(value: str | None) -> str:
    value = (value or "").strip().rstrip("/")
    if not value:
        return ""
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", "", ""))


def normalize_proxy_url(value: str | None) -> str:
    value = (value or "").strip().rstrip("/")
    if not value:
        return ""
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", "", ""))


def normalize_pip_index_url(value: str | None) -> str:
    value = (value or "").strip().rstrip("/")
    if not value:
        return ""
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", "", ""))


def redact_url(value: str | None) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    parsed = urlparse(value)
    if not parsed.netloc:
        return value
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    netloc = f"***:***@{host}{port}" if parsed.username or parsed.password else parsed.netloc
    return urlunparse((parsed.scheme, netloc, parsed.path, "", parsed.query, ""))


def configured_hf_endpoint() -> str:
    for name in HF_ENDPOINT_ENV_NAMES:
        endpoint = normalize_hf_endpoint(os.environ.get(name))
        if endpoint:
            return endpoint
    return ""


def configured_proxy_url() -> str:
    for name in PROXY_ENV_NAMES:
        proxy_url = normalize_proxy_url(os.environ.get(name))
        if proxy_url:
            return proxy_url
    return ""


def configured_pip_index_url() -> str:
    for name in PIP_INDEX_ENV_NAMES:
        pip_index = normalize_pip_index_url(os.environ.get(name))
        if pip_index:
            return pip_index
    return ""


def download_targets() -> dict[str, dict[str, str]]:
    targets = {
        host: {"label": DOWNLOAD_HOSTS[host], "url": DOWNLOAD_URLS[host]}
        for host in DOWNLOAD_HOSTS
    }
    endpoint = configured_hf_endpoint()
    if endpoint:
        parsed = urlparse(endpoint)
        host = parsed.hostname or "huggingface.co"
        targets.pop("huggingface.co", None)
        targets[host] = {"label": f"Hugging Face 镜像 ({host})", "url": endpoint + "/"}
    pip_index = configured_pip_index_url()
    if pip_index:
        parsed = urlparse(pip_index)
        host = parsed.hostname or "pypi.org"
        targets.pop("pypi.org", None)
        targets[host] = {"label": f"pip 镜像 ({host})", "url": pip_index + "/"}
    return targets


def missing_modules_from_current(modules: dict[str, str]) -> list[str]:
    missing: list[str] = []
    for label, module in modules.items():
        if importlib.util.find_spec(module) is None:
            missing.append(label)
    return missing


def venv_python(venv: Path) -> Path:
    if platform.system() == "Windows":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def missing_modules_from_python(python: Path, modules: dict[str, str]) -> list[str] | None:
    payload = json.dumps(modules)
    code = (
        "import importlib.util, json, sys\n"
        "modules=json.loads(sys.argv[1])\n"
        "missing=[label for label, module in modules.items() if importlib.util.find_spec(module) is None]\n"
        "print(json.dumps(missing, ensure_ascii=False))\n"
    )
    try:
        result = subprocess.run(
            [str(python), "-c", code, payload],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
            **hidden_process_options(),
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    try:
        missing = json.loads(result.stdout)
    except Exception:
        return None
    return missing if isinstance(missing, list) else None


def frontend_dependency_context() -> dict[str, Any]:
    project_python = venv_python(WORKSPACE_DIR / ".venv")
    if project_python.exists():
        missing = missing_modules_from_python(project_python, REQUIRED_FRONTEND_MODULES)
        optional_missing = missing_modules_from_python(project_python, OPTIONAL_FRONTEND_MODULES)
        if missing is not None and optional_missing is not None:
            return {
                "source": "project_venv",
                "python": str(project_python),
                "missing": missing,
                "optional_missing": optional_missing,
            }
    return {
        "source": "current_python",
        "python": sys.executable,
        "missing": missing_modules_from_current(REQUIRED_FRONTEND_MODULES),
        "optional_missing": missing_modules_from_current(OPTIONAL_FRONTEND_MODULES),
    }


def install_commands() -> dict[str, list[str]]:
    system = platform.system()
    if system == "Windows":
        winget_accept = "--accept-package-agreements --accept-source-agreements"
        return {
            "python": [
                f"winget install -e --id Python.Python.3.12 {winget_accept}",
                "start https://www.python.org/downloads/windows/",
            ],
            "git": [f"winget install -e --id Git.Git {winget_accept}"],
            "ffmpeg": [f"winget install -e --id Gyan.FFmpeg {winget_accept}"],
            "frontend": [
                r".\.venv\Scripts\python -m ensurepip --upgrade",
                r".\.venv\Scripts\python -m pip install -U pip",
                r".\.venv\Scripts\python -m pip install -r requirements.txt",
            ],
        }
    if system == "Darwin":
        return {
            "python": ["brew install python@3.12", "open https://www.python.org/downloads/macos/"],
            "git": ["xcode-select --install", "或 brew install git"],
            "ffmpeg": ["brew install ffmpeg"],
            "frontend": [
                "./.venv/bin/python -m ensurepip --upgrade",
                "./.venv/bin/python -m pip install -U pip",
                "./.venv/bin/python -m pip install -r requirements.txt",
            ],
        }
    return {
        "python": ["安装 Python 3.10-3.12"],
        "git": ["用系统包管理器安装 git"],
        "ffmpeg": ["用系统包管理器安装 ffmpeg"],
        "frontend": [
            "./.venv/bin/python -m ensurepip --upgrade",
            "./.venv/bin/python -m pip install -U pip",
            "./.venv/bin/python -m pip install -r requirements.txt",
        ],
    }


def check_python() -> dict[str, Any]:
    version = sys.version_info
    ok = (3, 10) <= version[:2] <= (3, 12)
    return {
        "id": "python",
        "label": "Python 3.10-3.12",
        "status": "ok" if ok else "blocked",
        "blocking": not ok,
        "message": f"当前 Python {version.major}.{version.minor}.{version.micro}。" if ok else f"当前 Python {version.major}.{version.minor}.{version.micro} 不适合 ComfyUI/PyTorch。",
        "action": "" if ok else "安装 Python 3.12 后重新运行启动器。",
    }


def check_frontend_modules() -> dict[str, Any]:
    context = frontend_dependency_context()
    missing = list(context["missing"])
    optional_missing = list(context["optional_missing"])
    ok = not missing
    optional_text = f" 可选兜底缺少：{', '.join(optional_missing)}。" if optional_missing else ""
    source_text = "项目 .venv" if context["source"] == "project_venv" else "当前 Python"
    return {
        "id": "frontend_modules",
        "label": "前端依赖",
        "status": "ok" if ok else "blocked",
        "blocking": not ok,
        "message": (f"{source_text} 的 FastAPI/uvicorn 等前端必需依赖已就绪。" + optional_text) if ok else f"{source_text} 缺少：" + ", ".join(missing),
        "action": "" if ok else "重新运行 START_WORKFLOW 启动器，或执行 ensurepip 后再 pip install -r requirements.txt。",
        "python": context["python"],
        "source": context["source"],
    }


def check_git() -> dict[str, Any]:
    git = shutil.which("git")
    return {
        "id": "git",
        "label": "Git",
        "status": "ok" if git else "warn",
        "blocking": False,
        "message": command_version([git, "--version"]) if git else "未检测到 Git；安装器会改用 GitHub ZIP 兜底下载源码。",
        "action": "" if git else "建议安装 Git，更新 ComfyUI 和自定义节点会更稳定。",
    }


def check_ffmpeg() -> dict[str, Any]:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        return {
            "id": "ffmpeg",
            "label": "ffmpeg",
            "status": "ok",
            "blocking": False,
            "message": command_version([ffmpeg, "-version"]),
            "action": "",
        }
    try:
        from imageio_ffmpeg import get_ffmpeg_exe

        path = get_ffmpeg_exe()
        return {
            "id": "ffmpeg",
            "label": "ffmpeg",
            "status": "ok",
            "blocking": False,
            "message": f"已通过 imageio-ffmpeg 找到内置 ffmpeg：{path}",
            "action": "",
        }
    except Exception as exc:
        return {
            "id": "ffmpeg",
            "label": "ffmpeg",
            "status": "warn",
            "blocking": False,
            "message": f"未找到可执行 ffmpeg，闪烁修复和部分后期会受限：{exc}",
            "action": "安装 ffmpeg，或重新安装前端依赖中的 imageio-ffmpeg。",
        }


def check_shell() -> dict[str, Any]:
    system = platform.system()
    if system == "Windows":
        ok = command_exists("powershell.exe")
        return {
            "id": "shell",
            "label": "启动外壳",
            "status": "ok" if ok else "warn",
            "blocking": False,
            "message": "PowerShell 可用，双击 START_WORKFLOW.bat 可启动。" if ok else "未检测到 PowerShell，可改用 python START_WORKFLOW.py。",
            "action": "" if ok else "安装 PowerShell，或手动运行 Python 启动器。",
        }
    ok = command_exists("bash") or command_exists("zsh")
    return {
        "id": "shell",
        "label": "启动外壳",
        "status": "ok" if ok else "warn",
        "blocking": False,
        "message": "shell 可用，可运行 START_WORKFLOW.command。" if ok else "未检测到 bash/zsh，请用 python START_WORKFLOW.py。",
        "action": "",
    }


def check_disk(path: Path) -> dict[str, Any]:
    usage_path = nearest_existing_path(path)
    usage = shutil.disk_usage(usage_path)
    free_gb = bytes_to_gb(usage.free)
    status = "ok" if free_gb >= 30 else "warn" if free_gb >= 5 else "blocked"
    return {
        "id": "disk",
        "label": "磁盘空间",
        "status": status,
        "blocking": status == "blocked",
        "message": f"{usage_path} 剩余 {free_gb} GB。视频模型通常需要 15GB-80GB+，请以当前模型安装计划显示的精确容量为准。",
        "action": "" if status != "blocked" else "清理磁盘，或把 COMFY_BASE_DIR/COMFY_INSTALL_DIR 指到更大的磁盘。",
        "free_gb": free_gb,
        "path": str(usage_path),
    }


def check_writable(path: Path) -> dict[str, Any]:
    target = nearest_existing_path(path)
    ok = os.access(target, os.W_OK)
    return {
        "id": "writable",
        "label": "目录权限",
        "status": "ok" if ok else "blocked",
        "blocking": not ok,
        "message": f"{target} 可写。" if ok else f"{target} 不可写，无法创建 venv、模型或输出文件。",
        "action": "" if ok else "换到可写目录，或调整目录权限。",
        "path": str(target),
    }


def check_comfy_install_dir(install_dir: Path) -> dict[str, Any]:
    main_py = install_dir / "main.py"
    git_dir = install_dir / ".git"
    desktop_main = next((path for path in desktop_comfy_main_candidates(install_dir) if path.exists()), None)
    if not install_dir.exists() or not any(install_dir.iterdir()):
        return {
            "id": "comfy_install_dir",
            "label": "ComfyUI 安装目录",
            "status": "ok",
            "blocking": False,
            "message": f"{install_dir} 可用于全新安装。",
            "action": "",
            "path": str(install_dir),
        }
    if looks_like_comfy_desktop_runtime(install_dir):
        return {
            "id": "comfy_install_dir",
            "label": "ComfyUI 安装目录",
            "status": "ok",
            "blocking": False,
            "message": f"已检测到 ComfyUI Desktop/runtime：{install_dir}",
            "action": "",
            "path": str(install_dir),
            "runtime": "desktop",
            "main_py": str(desktop_main or ""),
        }
    if main_py.exists() or git_dir.exists():
        return {
            "id": "comfy_install_dir",
            "label": "ComfyUI 安装目录",
            "status": "ok",
            "blocking": False,
            "message": f"已检测到现有 ComfyUI：{install_dir}",
            "action": "",
            "path": str(install_dir),
        }
    return {
        "id": "comfy_install_dir",
        "label": "ComfyUI 安装目录",
        "status": "blocked",
        "blocking": True,
        "message": f"{install_dir} 非空，但不像 ComfyUI 源码目录。",
        "action": "换一个空目录作为 COMFY_INSTALL_DIR，或手动清理该目录。",
        "path": str(install_dir),
    }


def check_network() -> dict[str, Any]:
    targets = download_targets()
    reachable = {host: url_reachable(item["url"]) for host, item in targets.items()}
    ok = all(reachable.values())
    missing = [targets[host]["label"] for host, value in reachable.items() if not value]
    source_text = "、".join(item["label"] for item in targets.values())
    proxy_url = configured_proxy_url()
    proxy_text = f"；代理：{redact_url(proxy_url)}" if proxy_url else ""
    pip_index = configured_pip_index_url()
    return {
        "id": "network",
        "label": "下载网络",
        "status": "ok" if ok else "warn",
        "blocking": False,
        "message": (f"{source_text} 可连接。" if ok else "部分下载站点不可连接：" + ", ".join(missing)) + proxy_text,
        "action": "" if ok else "检查代理、DNS、防火墙或稍后重试；已下载的完整文件会复用，.part 文件可断点续传。",
        "reachable": reachable,
        "targets": targets,
        "hf_endpoint": configured_hf_endpoint(),
        "proxy_url": redact_url(proxy_url),
        "pip_index_url": pip_index,
    }


def build_prerequisite_report(
    workspace_dir: Path,
    base_dir: Path,
    install_dir: Path,
    include_network: bool = False,
) -> dict[str, Any]:
    checks = [
        check_python(),
        check_frontend_modules(),
        check_shell(),
        check_git(),
        check_ffmpeg(),
        check_disk(base_dir),
        check_writable(workspace_dir),
        check_comfy_install_dir(install_dir),
    ]
    if include_network:
        checks.append(check_network())
    blocked = [item for item in checks if item.get("blocking")]
    warnings = [item for item in checks if item.get("status") == "warn"]
    return {
        "ok": not blocked,
        "blocked_count": len(blocked),
        "warning_count": len(warnings),
        "checks": checks,
        "install_commands": install_commands(),
        "workspace_dir": str(workspace_dir),
        "base_dir": str(base_dir),
        "install_dir": str(install_dir),
        "network_checked": include_network,
        "platform": {
            "system": platform.system(),
            "machine": platform.machine(),
            "python": sys.version.split()[0],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check first-run prerequisites for the local video workflow.")
    parser.add_argument("--workspace-dir", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--base-dir", type=Path, default=None)
    parser.add_argument("--install-dir", type=Path, default=None)
    parser.add_argument("--network", action="store_true", help="Also test GitHub/Hugging Face reachability.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()

    workspace = args.workspace_dir.expanduser().resolve()
    base = (args.base_dir.expanduser().resolve() if args.base_dir else default_base_dir(workspace))
    install = (args.install_dir.expanduser().resolve() if args.install_dir else default_install_dir(base))
    report = build_prerequisite_report(workspace, base, install, include_network=args.network)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["ok"] else 1

    print("PREREQUISITES OK" if report["ok"] else "PREREQUISITES NEED ATTENTION")
    for item in report["checks"]:
        print(f"- [{item['status']}] {item['label']}: {item['message']}")
        if item.get("action"):
            print(f"  next: {item['action']}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
