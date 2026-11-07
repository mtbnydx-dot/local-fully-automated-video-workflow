from __future__ import annotations

import argparse
import json
import os
import platform
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


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def package_source() -> Path:
    return DEFAULT_PACKAGE if DEFAULT_PACKAGE.exists() else ROOT


def ignore_names(_: str, names: list[str]) -> set[str]:
    blocked = {
        ".git",
        ".venv",
        ".local_ai_workbench_config.json",
        ".wan22_workflow_config.json",
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
        "ComfyUI",
        "github_upload",
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


def run_command(command: list[str], cwd: Path, env: dict[str, str] | None = None) -> dict[str, Any]:
    log(f"[run] {' '.join(command)}")
    result = subprocess.run(
        command,
        cwd=str(cwd),
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=120,
    )
    if result.stdout.strip():
        log(result.stdout.strip())
    if result.stderr.strip():
        log(result.stderr.strip())
    if result.returncode != 0:
        raise RuntimeError(f"Command failed with {result.returncode}: {' '.join(command)}")
    return {
        "command": command,
        "return_code": result.returncode,
        "stdout_tail": result.stdout.strip()[-1000:],
        "stderr_tail": result.stderr.strip()[-1000:],
    }


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def get_json(url: str, timeout: float = 5.0) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def wait_for_json(url: str, seconds: int = 30) -> dict[str, Any]:
    deadline = time.time() + seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            return get_json(url, timeout=2)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            time.sleep(0.5)
    raise RuntimeError(f"Timed out waiting for {url}: {last_error}")


def api_check(base_url: str, path: str) -> dict[str, Any]:
    payload = get_json(f"{base_url}{path}", timeout=20)
    log(f"[api] {path} ok")
    return payload


def post_json(url: str, payload: dict[str, Any] | None = None, timeout: float = 20.0) -> dict[str, Any]:
    data = json.dumps(payload or {}).encode("utf-8") if payload is not None else b""
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def post_json_expect_error(url: str, expected_status: int, timeout: float = 20.0) -> dict[str, Any]:
    request = urllib.request.Request(url, data=b"", method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
            raise RuntimeError(f"Expected HTTP {expected_status} from {url}, got {response.status}: {payload}")
    except urllib.error.HTTPError as exc:
        payload = json.loads(exc.read().decode("utf-8"))
        if exc.code != expected_status:
            raise RuntimeError(f"Expected HTTP {expected_status} from {url}, got {exc.code}: {payload}") from exc
        return payload


def poll_job(base_url: str, job_id: str, seconds: int = 60) -> dict[str, Any]:
    deadline = time.time() + seconds
    last_payload: dict[str, Any] | None = None
    while time.time() < deadline:
        last_payload = get_json(f"{base_url}/api/install/{job_id}", timeout=10)
        if last_payload.get("completed"):
            return last_payload
        time.sleep(0.5)
    raise RuntimeError(f"Timed out waiting for job {job_id}: {last_payload}")


def plan_item_ids(plan: dict[str, Any]) -> set[str]:
    return {str(item.get("id")) for item in (plan.get("install_plan") or {}).get("items") or []}


def run_install_profile_matrix(base_url: str) -> dict[str, Any]:
    profiles = [
        "post-only",
        "seedvr2-upscale",
        "cuda-wan5b",
        "cuda-full",
        "ltx098",
        "ltx25-distilled-int8",
        "ltx25-distilled-nvfp4",
        "ltx23-fp8-distilled",
        "ltx23-fp8-dev",
        "ltx23-nvfp4-dev",
        "mac-low",
        "mac-balanced",
        "mac-wan5b",
        "manual",
    ]
    plans = {profile: api_check(base_url, f"/api/install-plan?profile={profile}") for profile in profiles}
    ids = {profile: plan_item_ids(plan) for profile, plan in plans.items()}
    checks = {
        "post_only_is_small": ids["post-only"] <= {"rife49", "realesrgan_x2", "ultrasharp_x4", "video_helper_suite", "frame_interpolation"},
        "seedvr2_is_native_temporal_upscale": {"seedvr2_3b_int8", "seedvr2_vae_fp16", "video_helper_suite"}
        <= ids["seedvr2-upscale"],
        "cuda_wan5b_has_5b": {"ti2v_5b", "umt5", "wan22_vae"} <= ids["cuda-wan5b"],
        "cuda_wan5b_excludes_a14b": not ({"i2v_high", "i2v_low", "t2v_high", "t2v_low"} & ids["cuda-wan5b"]),
        "cuda_full_has_a14b": {"i2v_high", "i2v_low", "t2v_high", "t2v_low"} <= ids["cuda-full"],
        "ltx098_is_native_profile": {"ltx_2b_098", "t5xxl_fp16"} <= ids["ltx098"],
        "ltx25_int8_has_native_av_assets": {
            "ltx25_distilled_int8",
            "ltx25_text_int8",
            "ltx25_video_vae_diff",
            "ltx25_video_vae_conv",
            "ltx25_audio_vae",
            "ltx25_spatial_upscaler",
            "ltx25_duration_head",
            "ltxvideo",
        }
        <= ids["ltx25-distilled-int8"],
        "ltx25_nvfp4_keeps_shared_assets": {
            "ltx25_distilled_nvfp4",
            "ltx25_text_int8",
            "ltx25_video_vae_diff",
            "ltx25_audio_vae",
            "ltxvideo",
        }
        <= ids["ltx25-distilled-nvfp4"]
        and "ltx25_distilled_int8" not in ids["ltx25-distilled-nvfp4"],
        "ltx23_distilled_has_official_assets": {"ltx23_fp8_distilled", "ltxvideo"} <= ids["ltx23-fp8-distilled"],
        "ltx23_dev_has_official_assets": {"ltx23_fp8_dev", "ltxvideo"} <= ids["ltx23-fp8-dev"],
        "ltx23_nvfp4_is_not_fp8": {"ltx23_nvfp4_dev", "ltxvideo"} <= ids["ltx23-nvfp4-dev"]
        and not ({"ltx23_fp8_distilled", "ltx23_fp8_dev"} & ids["ltx23-nvfp4-dev"]),
        "mac_low_has_ltx": {"ltx_2b_098", "t5xxl_fp16"} <= ids["mac-low"],
        "mac_low_excludes_wan": not ({"ti2v_5b", "i2v_high", "t2v_high"} & ids["mac-low"]),
        "mac_wan5b_has_ltx_and_5b": {"ltx_2b_098", "t5xxl_fp16", "ti2v_5b", "umt5", "wan22_vae"} <= ids["mac-wan5b"],
        "mac_wan5b_excludes_a14b": not ({"i2v_high", "i2v_low", "t2v_high", "t2v_low"} & ids["mac-wan5b"]),
        "manual_profile_is_not_installable": (plans["manual"].get("install_plan") or {}).get("installable") is False,
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise RuntimeError(f"Install profile matrix checks failed: {', '.join(failed)}")
    return {
        "profiles": {
            profile: {
                "asset_count": (plans[profile].get("install_plan") or {}).get("asset_count"),
                "custom_node_count": (plans[profile].get("install_plan") or {}).get("custom_node_count"),
                "item_ids": sorted(ids[profile]),
            }
            for profile in profiles
        },
        "checks": checks,
    }


def run_api_smoke(cwd: Path, env: dict[str, str]) -> dict[str, Any]:
    port = free_port()
    base_url = f"http://127.0.0.1:{port}"
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "beginner_frontend.app:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
    ]
    log(f"[server] starting {base_url}")
    process = subprocess.Popen(
        command,
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        health = wait_for_json(f"{base_url}/api/health", seconds=30)
        prerequisites = api_check(base_url, "/api/prerequisites")
        network_prerequisites = api_check(base_url, "/api/prerequisites?network=true")
        bootstrap = api_check(base_url, "/api/bootstrap")
        settings_before = api_check(base_url, "/api/settings")
        settings_save = post_json(
            f"{base_url}/api/settings",
            {
                "download": {
                    "hf_endpoint": "https://hf-mirror.example",
                    "pip_index_url": "https://pypi.org/simple",
                    "proxy_url": "http://user:secret@127.0.0.1:7890",
                }
            },
        )
        settings_after = api_check(base_url, "/api/settings")
        environment = api_check(base_url, "/api/environment")
        post_plan = api_check(base_url, "/api/install-plan?profile=post-only")
        wan5b_plan = api_check(base_url, "/api/install-plan?profile=cuda-wan5b")
        profile_matrix = run_install_profile_matrix(base_url)
        self_test_start = post_json(f"{base_url}/api/self-test")
        self_test = poll_job(base_url, str(self_test_start["id"]), seconds=90)
        log("[api] /api/self-test ok")
        full_setup_start = post_json(f"{base_url}/api/bootstrap/full-setup?backend=skip&profile=post-only&dry_run=true")
        full_setup = poll_job(base_url, str(full_setup_start["id"]), seconds=90)
        log("[api] /api/bootstrap/full-setup dry-run ok")
        smoke_error = post_json_expect_error(f"{base_url}/api/video-smoke-test", 503)
        log("[api] /api/video-smoke-test disconnected guidance ok")
        diagnostics = api_check(base_url, "/api/diagnostics")
        install_commands = prerequisites.get("install_commands") or {}
        python_commands = install_commands.get("python") or []
        smoke_detail = smoke_error.get("detail") or {}
        missing_installable = environment.get("missing_installable") or []
        install_plan_items = (environment.get("install_plan") or {}).get("items") or []
        environment_profile_ids = {
            str(item.get("id") or "") for item in (environment.get("install_profiles") or [])
        }
        full_setup_log = "\n".join(full_setup.get("log") or [])
        checks = {
            "health_ok": bool(health.get("ok")),
            "prerequisites_have_checks": len(prerequisites.get("checks") or []) >= 6,
            "network_prerequisites_have_reachability": bool(network_prerequisites.get("network_checked"))
            and any((item.get("id") == "network" and "reachable" in item) for item in (network_prerequisites.get("checks") or [])),
            "prerequisites_have_python_commands": bool(python_commands),
            "prerequisites_have_python_download_fallback": any("python.org" in str(command) for command in python_commands),
            "bootstrap_has_disk": "install_disk" in bootstrap,
            "bootstrap_has_prerequisites": "prerequisites" in bootstrap,
            "settings_have_download_source": "download" in settings_before,
            "settings_save_hf_endpoint": (settings_save.get("download") or {}).get("saved_hf_endpoint") == "https://hf-mirror.example",
            "settings_save_pip_index": (settings_save.get("download") or {}).get("saved_pip_index_url") == "https://pypi.org/simple",
            "settings_save_proxy_endpoint": (settings_save.get("download") or {}).get("saved_proxy_url") == "http://user:secret@127.0.0.1:7890",
            "environment_has_download_settings": (environment.get("download_settings") or {}).get("hf_endpoint") == "https://hf-mirror.example",
            "environment_has_pip_index_settings": (environment.get("download_settings") or {}).get("pip_index_url") == "https://pypi.org/simple",
            "environment_redacts_proxy_credentials": "secret" not in json.dumps(environment.get("download_settings") or {}, ensure_ascii=False),
            "environment_profiles_are_beginner_scoped": {"auto", "post-only"} <= environment_profile_ids
            and len(environment_profile_ids) <= 3
            and str(environment.get("install_profile") or "") in environment_profile_ids,
            "environment_missing_items_have_download_metadata": bool(missing_installable)
            and all("item_type" in item and "download_host" in item for item in missing_installable),
            "environment_install_plan_items_have_download_metadata": bool(install_plan_items)
            and all("item_type" in item and "download_host" in item for item in install_plan_items),
            "post_only_profile": post_plan.get("profile") == "post-only",
            "wan5b_profile": wan5b_plan.get("profile") == "cuda-wan5b",
            "profile_matrix_ok": all(profile_matrix["checks"].values()),
            "self_test_ok": bool((self_test.get("self_test") or {}).get("ok")),
            "full_setup_dry_run_ok": full_setup.get("status") == "success" and bool(full_setup.get("dry_run")),
            "full_setup_runs_installers": "模型/节点安装" in full_setup_log
            and (
                "ComfyUI 安装" in full_setup_log
                or (bool(full_setup.get("skip_comfy_install")) and "跳过" in full_setup_log)
            ),
            "full_setup_tracks_running_comfyui_policy": "skip_comfy_install" in full_setup and "use_local_comfy_python" in full_setup,
            "video_smoke_disconnected_guidance": "ComfyUI 未连接" in str(smoke_detail.get("message")) and any("一键准备环境" in str(item) for item in (smoke_detail.get("actions") or [])),
            "diagnostics_ok": bool(diagnostics.get("ok")),
            "diagnostics_have_prerequisites": "prerequisites" in diagnostics,
            "diagnostics_have_version": diagnostics.get("diagnostic_version") == 1,
            "diagnostics_have_download_settings": (diagnostics.get("download_settings") or {}).get("hf_endpoint") == "https://hf-mirror.example",
            "diagnostics_have_pip_index_settings": (diagnostics.get("download_settings") or {}).get("pip_index_url") == "https://pypi.org/simple",
            "diagnostics_redact_proxy_credentials": "secret" not in json.dumps(diagnostics.get("download_settings") or {}, ensure_ascii=False),
            "diagnostics_have_recent_jobs": bool(diagnostics.get("recent_jobs")),
        }
        failed = [name for name, ok in checks.items() if not ok]
        if failed:
            raise RuntimeError(f"API smoke checks failed: {', '.join(failed)}")
        return {
            "url": base_url,
            "app_version": health.get("app_version"),
            "install_backend": (bootstrap.get("install_disk") or {}).get("backend"),
            "install_profiles": len(environment.get("install_profiles") or []),
            "download_settings": settings_after.get("download"),
            "checks": checks,
            "profile_matrix": profile_matrix,
            "full_setup": {
                "status": full_setup.get("status"),
                "dry_run": full_setup.get("dry_run"),
                "install_profile": full_setup.get("install_profile"),
                "skip_comfy_install": full_setup.get("skip_comfy_install"),
                "use_local_comfy_python": full_setup.get("use_local_comfy_python"),
            },
            "video_smoke_disconnected": {
                "message": smoke_detail.get("message"),
                "actions": smoke_detail.get("actions"),
            },
        }
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


def smoke(source: Path, keep_temp: bool = False) -> dict[str, Any]:
    source = source.resolve()
    if not source.exists():
        raise RuntimeError(f"Source package does not exist: {source}")

    temp_root = Path(tempfile.mkdtemp(prefix="wan22_release_smoke_"))
    copied = temp_root / "package"
    try:
        shutil.copytree(source, copied, ignore=ignore_names)
        smoke_base = temp_root / "comfy_base"
        smoke_install = temp_root / "ComfyUI"
        smoke_base.mkdir(parents=True, exist_ok=True)
        command_env = os.environ.copy()
        command_env.pop("COMFY_URL", None)
        command_env.update(
            {
                "PYTHONDONTWRITEBYTECODE": "1",
                "COMFY_BASE_DIR": str(smoke_base),
                "COMFY_INSTALL_DIR": str(smoke_install),
                "BEGINNER_FRONTEND_URL": f"http://127.0.0.1:{free_port()}",
            }
        )
        api_env = command_env.copy()
        api_env["COMFY_URL"] = f"http://127.0.0.1:{free_port()}"
        commands = [
            run_command([sys.executable, "START_WORKFLOW.py", "--check"], copied, env=command_env),
            run_command([sys.executable, "START_WORKFLOW.py", "--help"], copied, env=command_env),
            run_command([sys.executable, "START_WORKFLOW.py", "--show-download-settings"], copied, env=command_env),
            run_command([sys.executable, "scripts/self_check.py", "--json"], copied, env=command_env),
            run_command(
                [
                    sys.executable,
                    "scripts/install_comfyui.py",
                    "--base-dir",
                    str(smoke_base),
                    "--install-dir",
                    str(smoke_install),
                    "--backend",
                    "skip",
                    "--dry-run",
                ],
                copied,
                env=command_env,
            ),
            run_command(
                [
                    sys.executable,
                    "scripts/install_workflow_assets.py",
                    "--base-dir",
                    str(smoke_base),
                    "--profile",
                    "post-only",
                    "--dry-run",
                    "--no-custom-nodes",
                    "--no-node-requirements",
                ],
                copied,
                env=command_env,
            ),
            run_command(
                [
                    sys.executable,
                    "scripts/install_workflow_assets.py",
                    "--base-dir",
                    str(smoke_base),
                    "--profile",
                    "cuda-wan5b",
                    "--dry-run",
                    "--no-custom-nodes",
                    "--no-node-requirements",
                ],
                copied,
                env=command_env,
            ),
        ]
        if platform.system() == "Windows":
            commands.extend(
                [
                    run_command(
                        [
                            "powershell.exe",
                            "-NoProfile",
                            "-ExecutionPolicy",
                            "Bypass",
                            "-File",
                            str(copied / "START_WORKFLOW.ps1"),
                            "--check",
                        ],
                        copied,
                        env=command_env,
                    ),
                    run_command(
                        [
                            "powershell.exe",
                            "-NoProfile",
                            "-ExecutionPolicy",
                            "Bypass",
                            "-File",
                            str(copied / "START_WORKFLOW.ps1"),
                            "--help",
                        ],
                        copied,
                        env=command_env,
                    ),
                    # 新版 Windows（如 26200+ build）的 cmd 不再从当前目录解析裸 .bat 名，必须用绝对路径。
                    run_command(["cmd", "/c", str(copied / "START_WORKFLOW.bat"), "--check"], copied, env=command_env),
                    run_command(["cmd", "/c", str(copied / "START_WORKFLOW.bat"), "--help"], copied, env=command_env),
                    run_command(
                        [
                            "powershell.exe",
                            "-NoProfile",
                            "-ExecutionPolicy",
                            "Bypass",
                            "-File",
                            str(copied / "scripts" / "start_beginner_frontend.ps1"),
                            "--check",
                        ],
                        copied,
                        env=command_env,
                    ),
                ]
            )
        elif shutil.which("bash"):
            commands.append(run_command(["bash", "START_WORKFLOW.command", "--check"], copied, env=command_env))
            commands.append(run_command(["bash", "START_WORKFLOW.command", "--help"], copied, env=command_env))
        api = run_api_smoke(copied, api_env)
        result = {
            "ok": True,
            "source": str(source),
            "temp_package": str(copied),
            "commands": commands,
            "api": api,
        }
        return result
    finally:
        if keep_temp:
            log(f"[keep] {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a no-download release smoke test in a temporary package copy.")
    parser.add_argument("--source", type=Path, default=package_source(), help="Release package directory to test.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument("--keep-temp", action="store_true", help="Keep the temporary copied package for debugging.")
    args = parser.parse_args()
    try:
        result = smoke(args.source, keep_temp=args.keep_temp)
    except Exception as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        else:
            print(f"RELEASE SMOKE FAILED: {exc}")
        return 1
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("RELEASE SMOKE OK")
        print(f"- package: {result['source']}")
        print(f"- api: {result['api']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
