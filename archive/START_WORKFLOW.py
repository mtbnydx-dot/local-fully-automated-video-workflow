from __future__ import annotations

import http.client
import json
import os
import platform
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from urllib.parse import urlparse, urlunparse


WORKSPACE_DIR = Path(__file__).resolve().parent
APP_VERSION = "2026.10.23.2"


def looks_like_comfy_base(path: Path) -> bool:
    return all((path / name).exists() for name in ("models", "input", "output", "custom_nodes"))


def default_comfy_base_dir() -> Path:
    configured = os.environ.get("COMFY_BASE_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    parent = WORKSPACE_DIR.parent
    if looks_like_comfy_base(parent):
        return parent.resolve()
    return WORKSPACE_DIR.resolve()


BASE_DIR = default_comfy_base_dir()
FRONTEND_URL = os.environ.get("BEGINNER_FRONTEND_URL", "http://127.0.0.1:7860")
COMFY_URL_CONFIGURED = bool(os.environ.get("COMFY_URL"))
COMFY_URL = os.environ.get("COMFY_URL", "http://127.0.0.1:8188").rstrip("/")
REQUIREMENTS = WORKSPACE_DIR / "requirements.txt"
REQUIREMENTS_LOCK = WORKSPACE_DIR / "requirements.lock"
FRONTEND_REQUIRED_MODULES = ("uvicorn", "fastapi", "cv2", "PIL")
LOCAL_CONFIG_FILE = WORKSPACE_DIR / ".local_ai_workbench_config.json"
LEGACY_LOCAL_CONFIG_FILES = (WORKSPACE_DIR / ".wan22_workflow_config.json",)
DOWNLOAD_CONFIG_FIELDS = {
    "hf_endpoint": "Hugging Face endpoint",
    "pip_index_url": "pip index URL",
    "proxy_url": "HTTP proxy",
}
SERVICE_MODES = {"server", "client", "both"}


def hidden_process_options() -> dict[str, object]:
    if platform.system() != "Windows":
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


def read_local_config() -> dict:
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


def saved_service_mode() -> str:
    mode = str(read_local_config().get("node_mode") or "").strip().lower()
    return mode if mode in SERVICE_MODES else ""


def effective_service_mode() -> str:
    mode = str(os.environ.get("WAN22_NODE_MODE") or "").strip().lower()
    if mode in SERVICE_MODES:
        return mode
    return saved_service_mode() or "both"


def service_mode_configured() -> bool:
    mode = str(os.environ.get("WAN22_NODE_MODE") or "").strip().lower()
    return mode in SERVICE_MODES or bool(saved_service_mode())


def frontend_bind_host() -> str:
    configured = os.environ.get("BEGINNER_FRONTEND_HOST") or os.environ.get("BEGINNER_FRONTEND_BIND_HOST")
    if configured:
        return configured.strip()
    mode = effective_service_mode()
    if service_mode_configured() and mode in {"server", "both"}:
        return "0.0.0.0"
    return "127.0.0.1"


def write_local_config(config: dict) -> None:
    cleaned = {key: value for key, value in config.items() if value not in ("", None)}
    LOCAL_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = LOCAL_CONFIG_FILE.with_name(f"{LOCAL_CONFIG_FILE.name}.tmp")
    try:
        temporary.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, LOCAL_CONFIG_FILE)
    finally:
        temporary.unlink(missing_ok=True)


def normalize_http_url(value: str | None, label: str) -> str:
    value = (value or "").strip().rstrip("/")
    if not value:
        return ""
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{label} must be an http(s) URL.")
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
    if parsed.username or parsed.password:
        netloc = f"***:***@{host}{port}"
    else:
        netloc = parsed.netloc
    return urlunparse((parsed.scheme, netloc, parsed.path, "", "", ""))


def print_download_settings() -> None:
    config = read_local_config()
    log(f"Download settings file: {LOCAL_CONFIG_FILE}")
    for key, label in DOWNLOAD_CONFIG_FIELDS.items():
        value = str(config.get(key) or "")
        if key == "proxy_url":
            value = redact_url(value)
        log(f"{label}: {value or '(official/default)'}")


def handle_download_settings_cli(argv: list[str]) -> int | None:
    if not any(arg in {"--set-hf-endpoint", "--set-pip-index", "--set-proxy", "--clear-download-settings", "--show-download-settings"} for arg in argv):
        return None

    config = read_local_config()
    index = 0
    changed = False
    while index < len(argv):
        arg = argv[index]
        key = ""
        label = ""
        if arg == "--set-hf-endpoint":
            key, label = "hf_endpoint", "Hugging Face endpoint"
        elif arg == "--set-pip-index":
            key, label = "pip_index_url", "pip index URL"
        elif arg == "--set-proxy":
            key, label = "proxy_url", "HTTP proxy"
        elif arg == "--clear-download-settings":
            for field in DOWNLOAD_CONFIG_FIELDS:
                config.pop(field, None)
            changed = True
            index += 1
            continue
        elif arg == "--show-download-settings":
            index += 1
            continue
        else:
            log(f"Unknown download setting argument: {arg}")
            log("Run python START_WORKFLOW.py --help for examples.")
            return 2

        if index + 1 >= len(argv):
            log(f"Missing value for {arg}")
            return 2
        try:
            value = normalize_http_url(argv[index + 1], label)
        except ValueError as exc:
            log(str(exc))
            return 2
        if value:
            config[key] = value
        else:
            config.pop(key, None)
        changed = True
        index += 2

    if changed:
        write_local_config(config)
        log("Download settings saved. Run the launcher again to use them.")
    print_download_settings()
    return 0


def bootstrap_subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    config = read_local_config()
    proxy_url = str(config.get("proxy_url") or "").strip()
    if proxy_url and not any(env.get(name) for name in ("HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy")):
        for name in ("HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy"):
            env[name] = proxy_url
    pip_index_url = str(config.get("pip_index_url") or "").strip()
    if pip_index_url and not env.get("PIP_INDEX_URL"):
        env["PIP_INDEX_URL"] = pip_index_url
    return env


def get_json(url: str, timeout: float = 3.0) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (
        urllib.error.URLError,
        TimeoutError,
        ConnectionError,
        http.client.HTTPException,
        json.JSONDecodeError,
        UnicodeDecodeError,
    ):
        return None


def common_comfy_urls() -> list[str]:
    urls = [COMFY_URL]
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


def discover_comfy_url() -> tuple[str, dict | None]:
    for url in common_comfy_urls():
        stats = get_json(f"{url}/system_stats", timeout=1.5)
        if stats:
            return url, stats
    return COMFY_URL, None


def venv_python(venv_root: Path) -> Path:
    if platform.system() == "Windows":
        return venv_root / "Scripts" / "python.exe"
    return venv_root / "bin" / "python"


def python_version(python: Path) -> tuple[int, int, int] | None:
    try:
        result = subprocess.run(
            [
                str(python),
                "-c",
                "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')",
            ],
            capture_output=True,
            check=True,
            text=True,
            timeout=10,
            **hidden_process_options(),
        )
    except Exception:
        return None
    try:
        major, minor, micro = result.stdout.strip().split(".")
        return int(major), int(minor), int(micro)
    except ValueError:
        return None


def python_cmd_version(command: list[str]) -> tuple[int, int, int] | None:
    try:
        result = subprocess.run(
            command
            + [
                "-c",
                "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')",
            ],
            capture_output=True,
            check=True,
            text=True,
            timeout=10,
            **hidden_process_options(),
        )
    except Exception:
        return None
    try:
        major, minor, micro = result.stdout.strip().split(".")
        return int(major), int(minor), int(micro)
    except ValueError:
        return None


def python_cmd_supported(command: list[str]) -> bool:
    version = python_cmd_version(command)
    return bool(version and (3, 10, 0) <= version < (3, 13, 0))


def python_has_module(python: Path, module: str) -> bool:
    result = subprocess.run(
        [str(python), "-c", f"import {module}"],
        capture_output=True,
        text=True,
        timeout=10,
        **hidden_process_options(),
    )
    return result.returncode == 0


def frontend_python_ready(python: Path) -> bool:
    return all(python_has_module(python, module) for module in FRONTEND_REQUIRED_MODULES)


def python_supported(python: Path) -> bool:
    version = python_version(python)
    return bool(version and (3, 10, 0) <= version < (3, 13, 0))


def common_windows_python_paths() -> list[Path]:
    if platform.system() != "Windows":
        return []
    candidates: list[Path] = []
    version_dirs = ("Python312", "Python311", "Python310")
    local_app_data = os.environ.get("LOCALAPPDATA")
    program_files = os.environ.get("ProgramFiles")
    program_files_x86 = os.environ.get("ProgramFiles(x86)")
    for version_dir in version_dirs:
        if local_app_data:
            candidates.append(Path(local_app_data) / "Programs" / "Python" / version_dir / "python.exe")
        if program_files:
            candidates.append(Path(program_files) / version_dir / "python.exe")
        if program_files_x86:
            candidates.append(Path(program_files_x86) / version_dir / "python.exe")
    return candidates


def discover_base_python() -> list[str] | None:
    commands: list[list[str]] = []
    if platform.system() == "Windows":
        commands.extend([["py", "-3.12"], ["py", "-3.11"], ["py", "-3.10"]])
        commands.extend([[str(path)] for path in common_windows_python_paths()])
    commands.extend(
        [
            [str(Path(sys.executable))],
            ["python3.12"],
            ["python3.11"],
            ["python3.10"],
            ["python3"],
            ["python"],
        ]
    )
    seen: set[str] = set()
    for command in commands:
        executable = command[0]
        executable_path = Path(executable)
        is_direct_path = executable_path.is_absolute() or "\\" in executable or "/" in executable
        if is_direct_path:
            if not executable_path.exists():
                continue
        elif executable not in {"py", str(Path(sys.executable))} and not shutil.which(executable):
            continue
        key = " ".join(command)
        if key in seen:
            continue
        seen.add(key)
        if python_cmd_supported(command):
            return command
    return None


def install_frontend_requirements(python: Path) -> None:
    requirements_file = REQUIREMENTS_LOCK if REQUIREMENTS_LOCK.exists() else REQUIREMENTS
    if not requirements_file.exists():
        raise RuntimeError(f"frontend requirements not found: {requirements_file}")
    log("Python:    installing frontend requirements")
    env = bootstrap_subprocess_env()
    ensure_pip_available(python, env)
    run_pip([str(python), "-m", "pip", "install", "-U", "pip"], env=env)
    run_pip([str(python), "-m", "pip", "install", "-r", str(requirements_file)], env=env)


def ensure_pip_available(python: Path, env: dict[str, str]) -> None:
    try:
        subprocess.run(
            [str(python), "-m", "pip", "--version"],
            check=True,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
            **hidden_process_options(),
        )
        return
    except Exception:
        log("Python:    pip is not ready; running ensurepip")
    subprocess.run(
        [str(python), "-m", "ensurepip", "--upgrade"],
        check=True,
        env=env,
        **hidden_process_options(),
    )
    subprocess.run(
        [str(python), "-m", "pip", "--version"],
        check=True,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=30,
        **hidden_process_options(),
    )


def run_pip(command: list[str], *, env: dict[str, str], attempts: int = 3) -> None:
    last_error: subprocess.CalledProcessError | None = None
    for attempt in range(1, attempts + 1):
        try:
            subprocess.run(command, check=True, env=env, **hidden_process_options())
            return
        except subprocess.CalledProcessError as exc:
            last_error = exc
            if attempt >= attempts:
                break
            wait = min(20, 3 * attempt)
            log(f"Python:    pip command failed with {exc.returncode}; retrying in {wait}s")
            time.sleep(wait)
    assert last_error is not None
    raise last_error


def ensure_project_venv() -> Path | None:
    venv = WORKSPACE_DIR / ".venv"
    python = venv_python(venv)
    if not python.exists() or not python_supported(python):
        base_python = discover_base_python()
        if base_python is None:
            return None
        log(f"Python:    creating frontend venv at {venv}")
        subprocess.run(base_python + ["-m", "venv", str(venv)], check=True, **hidden_process_options())
    if not python_supported(python):
        return None
    if not frontend_python_ready(python):
        install_frontend_requirements(python)
    return python


def find_python() -> Path | None:
    project_python = ensure_project_venv()
    if project_python:
        return project_python
    candidates = [
        venv_python(BASE_DIR / ".venv"),
        Path(sys.executable),
    ]
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        if candidate.exists() and python_supported(candidate) and frontend_python_ready(candidate):
            return candidate
    return None


def print_python_help() -> None:
    log("Python:    not ready")
    log("Need Python 3.10-3.12. The launcher can create .venv automatically once Python is installed.")
    if platform.system() == "Windows":
        log("Run:")
        log(r"  winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements")
        log(r"  start https://www.python.org/downloads/windows/")
        log(r"  .\START_WORKFLOW.bat")
    else:
        log("Run:")
        log("  Install Python 3.10-3.12 from python.org or Homebrew, then run:")
        log("  open https://www.python.org/downloads/macos/")
        log("  brew install python@3.12")
        log("  ./START_WORKFLOW.command")


def print_usage() -> None:
    log("Local AI video workflow")
    log("")
    log("Usage:")
    log("  python START_WORKFLOW.py")
    log("  python START_WORKFLOW.py --check")
    log("  python START_WORKFLOW.py --help")
    log("  python START_WORKFLOW.py --no-browser")
    log("  python START_WORKFLOW.py --show-download-settings")
    log("  python START_WORKFLOW.py --set-hf-endpoint https://huggingface.co")
    log("  python START_WORKFLOW.py --set-pip-index https://pypi.org/simple")
    log("  python START_WORKFLOW.py --set-proxy http://127.0.0.1:7890")
    log("  python START_WORKFLOW.py --clear-download-settings")
    log("")
    log("Beginner path:")
    log("  1. Start this launcher.")
    log("  2. Open step 1: Environment detection.")
    log("  3. Click the one-click environment setup button.")
    log("  4. Run the generation smoke test before real shots.")
    if platform.system() == "Windows":
        log("")
        log(r"Windows: double-click START_WORKFLOW.bat")
    else:
        log("")
        log("macOS/Linux: chmod +x ./START_WORKFLOW.command && ./START_WORKFLOW.command")


def print_frontend_dependency_help(exc: Exception) -> None:
    log("Python:    frontend dependency setup failed")
    log(f"Reason:    {exc}")
    log("Try:")
    log("  1. Check your network/proxy, then run the launcher again.")
    log("     You can save launcher-level network settings before the frontend opens:")
    log("       python START_WORKFLOW.py --set-pip-index https://pypi.org/simple")
    log("       python START_WORKFLOW.py --set-proxy http://127.0.0.1:7890")
    log("     Advanced fallback: set HTTPS_PROXY and/or PIP_INDEX_URL before launching.")
    if platform.system() == "Windows":
        log(r"  2. Or run: .\.venv\Scripts\python -m ensurepip --upgrade")
        log(r"            .\.venv\Scripts\python -m pip install -r requirements.txt")
    else:
        log("  2. Or run: ./.venv/bin/python -m ensurepip --upgrade")
        log("            ./.venv/bin/python -m pip install -r requirements.txt")
    log("After the frontend opens, use self-test and copy diagnostics for troubleshooting.")


def stdin_is_interactive() -> bool:
    try:
        return bool(sys.stdin.isatty())
    except Exception:
        return False


def prompt_download_url(prompt: str, label: str) -> str | None:
    while True:
        try:
            value = input(prompt).strip()
        except EOFError:
            return None
        if not value:
            return ""
        try:
            return normalize_http_url(value, label)
        except ValueError as exc:
            log(str(exc))
            log("Press Enter to skip this field, or enter a valid http(s) URL.")


def offer_frontend_dependency_retry(exc: Exception) -> bool:
    if os.environ.get("WAN22_NO_INTERACTIVE_RETRY") == "1" or not stdin_is_interactive():
        return False

    log("")
    log("浏览器前端依赖没有安装成功，常见原因是 pip/PyPI 或代理网络不可达。")
    log("你可以先在这里保存 pip 镜像或 HTTP 代理；前端还没打开也能生效，保存后会自动重试。")
    try:
        answer = input("要现在保存网络设置并立即重试吗？输入 Y 继续：").strip()
    except EOFError:
        return False
    if not answer or answer[0].lower() != "y":
        return False

    pip_index_url = prompt_download_url(
        "pip 镜像地址，或直接回车使用官方源（例：https://pypi.org/simple）：",
        "pip index URL",
    )
    if pip_index_url is None:
        return False
    proxy_url = prompt_download_url(
        "HTTP 代理地址，或直接回车不设置额外代理（例：http://127.0.0.1:7890）：",
        "HTTP proxy",
    )
    if proxy_url is None:
        return False

    config = read_local_config()
    if pip_index_url:
        config["pip_index_url"] = pip_index_url
    if proxy_url:
        config["proxy_url"] = proxy_url
    write_local_config(config)

    log("网络设置已保存，正在重试前端依赖安装。")
    print_download_settings()
    return True


def parsed_frontend_url(url: str) -> tuple[str, int]:
    parsed = urlparse(url)
    return parsed.hostname or "127.0.0.1", parsed.port or 7860


def frontend_url_for_port(port: int) -> str:
    parsed = urlparse(FRONTEND_URL)
    return urlunparse((parsed.scheme or "http", f"{parsed.hostname or '127.0.0.1'}:{port}", "", "", "", ""))


def port_is_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) != 0


FRONTEND_STOP_MARKERS = (
    "beginner_frontend.app:app",
    "START_WORKFLOW.py",
    "START_WORKFLOW.ps1",
    "START_WORKFLOW.command",
)
PROTECTED_PROCESS_MARKERS = (
    "comfyui\\main.py",
    "comfyui/main.py",
    "\\comfyui\\resources\\comfyui\\main.py",
)


def local_addr_uses_port(local: str, port: int) -> bool:
    local = local.strip().strip("[]")
    if local.startswith("["):
        return local.endswith(f"]:{port}")
    return local.rsplit(":", 1)[-1] == str(port)


def pids_listening_on_port(port: int) -> set[int]:
    pids: set[int] = set()
    try:
        if platform.system() == "Windows":
            try:
                output = subprocess.check_output(
                    ["netstat", "-ano", "-p", "tcp"],
                    text=True,
                    errors="replace",
                    timeout=8,
                    **hidden_process_options(),
                )
            except Exception:
                output = subprocess.check_output(
                    ["netstat", "-ano"],
                    text=True,
                    errors="replace",
                    timeout=8,
                    **hidden_process_options(),
                )
        else:
            output = subprocess.check_output(
                ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"],
                text=True,
                errors="replace",
                timeout=8,
            )
    except Exception:
        return pids
    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        if platform.system() == "Windows":
            if "LISTENING" not in line.upper() or len(parts) < 5:
                continue
            if not local_addr_uses_port(parts[1], port):
                continue
            raw_pid = parts[-1]
        else:
            if parts[0].lower() == "command" or "LISTEN" not in line.upper():
                continue
            raw_pid = parts[1]
        try:
            pid = int(raw_pid)
        except ValueError:
            continue
        if pid > 0:
            pids.add(pid)
    return pids


def process_command_line(pid: int) -> str:
    if pid <= 0:
        return ""
    try:
        if platform.system() == "Windows":
            output = subprocess.check_output(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-Command",
                    f"(Get-CimInstance Win32_Process -Filter 'ProcessId={int(pid)}').CommandLine",
                ],
                text=True,
                errors="replace",
                timeout=8,
                **hidden_process_options(),
            )
            return output.strip()
        output = subprocess.check_output(["ps", "-p", str(pid), "-o", "args="], text=True, errors="replace", timeout=8)
        return output.strip()
    except Exception:
        return ""


def is_protected_process(command_line: str) -> bool:
    lowered = command_line.lower().replace("/", "\\")
    if "beginner_frontend" in lowered:
        return False
    return any(marker in lowered for marker in PROTECTED_PROCESS_MARKERS) or "comfyui\\main.py" in lowered


def should_stop_process(pid: int, command_line: str, *, occupying_frontend_port: bool) -> bool:
    if pid <= 0 or pid == os.getpid():
        return False
    if is_protected_process(command_line):
        return False
    lowered = command_line.lower()
    if any(marker.lower() in lowered for marker in FRONTEND_STOP_MARKERS):
        return True
    return False


def stop_pid(pid: int) -> None:
    if pid <= 0 or pid == os.getpid():
        return
    try:
        if platform.system() == "Windows":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=8,
                **hidden_process_options(),
            )
            return
        os.kill(pid, signal.SIGTERM)
    except Exception:
        return


def stop_stale_frontend(url: str, timeout: float = 15.0) -> bool:
    host, port = parsed_frontend_url(url)
    if matching_frontend_health(url) or port_is_free(host, port):
        return True
    health = get_json(f"{url}/api/health", timeout=2) or {}
    pids: set[int] = set(pids_listening_on_port(port))
    try:
        health_pid = int(health.get("process_id") or 0)
    except (TypeError, ValueError):
        health_pid = 0
    if health_pid:
        pids.add(health_pid)
    listeners = set(pids)
    to_stop: list[int] = []
    for pid in sorted(pids):
        command_line = process_command_line(pid)
        occupying = pid in listeners
        if should_stop_process(pid, command_line, occupying_frontend_port=occupying):
            to_stop.append(pid)
    if not to_stop and pids:
        log(f"Frontend:  {url} is occupied, but the process is not a previous workbench instance.")
        return False
    other_dir = str(health.get("workspace_dir") or "").strip()
    other_ver = str(health.get("app_version") or "").strip()
    detail = " · ".join(part for part in (other_ver, other_dir) if part)
    log(f"Frontend:  stopping old instance on {url}{f' ({detail})' if detail else ''}")
    for pid in to_stop:
        log(f"Frontend:  stopping PID {pid}")
        stop_pid(pid)
    deadline = time.time() + timeout
    while time.time() < deadline:
        if port_is_free(host, port):
            log("Frontend:  old instance stopped")
            return True
        time.sleep(0.4)
    return port_is_free(host, port)


def choose_frontend_url() -> str:
    return FRONTEND_URL


def matching_frontend_health(url: str) -> bool:
    health = get_json(f"{url}/api/health", timeout=2)
    if not health:
        return False
    return (
        health.get("app_version") == APP_VERSION
        and Path(str(health.get("workspace_dir", ""))).resolve() == WORKSPACE_DIR
    )


def wait_for_frontend(url: str, seconds: int = 30) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if matching_frontend_health(url) or get_json(f"{url}/api/environment", timeout=2):
            return True
        time.sleep(0.5)
    return False


def build_frontend_env(comfy_detected: bool) -> dict[str, str]:
    env = os.environ.copy()
    if COMFY_URL_CONFIGURED or comfy_detected:
        env["COMFY_URL"] = COMFY_URL
    else:
        env.pop("COMFY_URL", None)
    env["COMFY_BASE_DIR"] = str(BASE_DIR)
    env["BEGINNER_FRONTEND_APP_VERSION"] = APP_VERSION
    env["BEGINNER_FRONTEND_BIND_HOST"] = frontend_bind_host()
    if service_mode_configured():
        env["WAN22_NODE_MODE"] = effective_service_mode()
    return env


def main() -> int:
    global COMFY_URL
    argv = sys.argv[1:]
    no_browser = "--no-browser" in argv
    argv = [arg for arg in argv if arg != "--no-browser"]
    if len(argv) > 0 and argv[0] in {"--help", "-h", "/?"}:
        print_usage()
        return 0
    if len(argv) > 0 and argv[0] == "--check":
        log("START_WORKFLOW.py OK")
        return 0
    download_settings_result = handle_download_settings_cli(argv)
    if download_settings_result is not None:
        return download_settings_result

    log("Local AI video workflow")
    log(f"Workspace: {WORKSPACE_DIR}")
    log(f"Base dir:  {BASE_DIR}")
    log(f"Service:   {effective_service_mode()} ({'configured' if service_mode_configured() else 'first-run selection pending'})")

    COMFY_URL, comfy_stats = discover_comfy_url()
    if comfy_stats:
        version = comfy_stats.get("system", {}).get("comfyui_version", "unknown")
        log(f"ComfyUI:   connected ({version})")
    else:
        tried = ", ".join(common_comfy_urls())
        log(f"ComfyUI:   not connected. Tried: {tried}")
        log("           You can still open the workflow; the first step will show what is missing.")

    if matching_frontend_health(FRONTEND_URL):
        log(f"Frontend:  already running at {FRONTEND_URL}")
        if not no_browser:
            webbrowser.open(FRONTEND_URL)
        return 0

    host, fixed_port = parsed_frontend_url(FRONTEND_URL)
    if not port_is_free(host, fixed_port) or get_json(f"{FRONTEND_URL}/api/health", timeout=2):
        if not stop_stale_frontend(FRONTEND_URL):
            log(f"Frontend:  {FRONTEND_URL} is still occupied after stopping the old instance.")
            return 1

    try:
        python = find_python()
    except Exception as exc:
        print_frontend_dependency_help(exc)
        if offer_frontend_dependency_retry(exc):
            try:
                python = find_python()
            except Exception as retry_exc:
                print_frontend_dependency_help(retry_exc)
                return 1
        else:
            return 1
    if python is None:
        print_python_help()
        return 1
    if not port_is_free(host, fixed_port) and not stop_stale_frontend(FRONTEND_URL):
        log(f"Frontend:  {FRONTEND_URL} is still occupied after stopping the old instance.")
        return 1

    launch_url = choose_frontend_url()
    _, port = parsed_frontend_url(launch_url)
    bind_host = frontend_bind_host()
    command = [
        str(python),
        "-m",
        "uvicorn",
        "beginner_frontend.app:app",
        "--host",
        bind_host,
        "--port",
        str(port),
    ]
    env = build_frontend_env(comfy_detected=bool(comfy_stats))
    log(f"Python:    {python}")
    log(f"Frontend:  starting {launch_url} (bind {bind_host})")

    process = subprocess.Popen(
        command,
        cwd=str(WORKSPACE_DIR),
        env=env,
        **hidden_process_options(),
    )
    if not wait_for_frontend(launch_url):
        log("Frontend did not become ready. Check the terminal output above.")
        return process.poll() or 1

    if no_browser:
        log(f"Ready:     {launch_url}")
    else:
        webbrowser.open(launch_url)
        log(f"Opened:    {launch_url}")
    log("Keep this window open while using the workflow. Press Ctrl+C to stop the frontend.")
    try:
        return process.wait()
    except KeyboardInterrupt:
        log("Stopping frontend...")
        process.terminate()
        try:
            return process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            return process.wait()


if __name__ == "__main__":
    raise SystemExit(main())
