"""Queue NSFW/unrestricted + related optional model downloads.

Prefers China HF mirror (hf-mirror.com), falls back to official huggingface.co.
Quant preference is handled by catalog profiles (nvfp4 assets listed before fp8 where both exist).
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / ".local_ai_workbench_config.json"
LEGACY_CONFIG = ROOT / ".wan22_workflow_config.json"
STATE = ROOT / ".runtime_nsfw_download_state.json"

# Order: video NSFW stack first, then image uncensor addons, then face-swap for character box.
PROFILES = [
    "cuda-full",  # Wan2.2 A14B I2V/T2V fp8 base + LoRA + encoders (video NSFW prerequisite)
    "wan22-i2v-unrestricted-addon",  # video NSFW High/Low LoRA pair
    "flux2-klein-uncensored-te-addon",  # nvfp4 + fp8 heretic TE
    "flux2-uncensored-te-addon",  # FLUX.2 abliterated TE fp8
    "qwen-image-2512-nsfw-addon",
    "z-image-nsfw-addon",
    "face-swap-reactor",
]

API = os.environ.get("LOCAL_AI_API", os.environ.get("WAN22_API", "http://127.0.0.1:7860")).rstrip("/")


def load_config() -> dict:
    source = CONFIG if CONFIG.exists() else LEGACY_CONFIG
    if not source.exists():
        return {}
    return json.loads(source.read_text(encoding="utf-8"))


def ensure_china_source(cfg: dict) -> dict:
    changed = False
    if cfg.get("download_region") != "china":
        cfg["download_region"] = "china"
        changed = True
    if cfg.get("hf_endpoint") != "https://hf-mirror.com":
        cfg["hf_endpoint"] = "https://hf-mirror.com"
        changed = True
    if not cfg.get("pip_index_url"):
        cfg["pip_index_url"] = "https://pypi.tuna.tsinghua.edu.cn/simple"
        changed = True
    if changed:
        CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("[config] set download_region=china, hf_endpoint=https://hf-mirror.com")
    else:
        print("[config] china download source already set")
    return cfg


def api(method: str, path: str, timeout: float = 60) -> dict:
    url = f"{API}{path}"
    req = urllib.request.Request(url, method=method)
    token = ""
    cfg = load_config()
    token = str(cfg.get("access_token") or "").strip()
    if token:
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("X-Local-AI-Token", token)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} -> {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"{method} {path} failed: {exc}") from exc


def save_state(data: dict) -> None:
    STATE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def wait_job(job_id: str, profile: str) -> dict:
    print(f"[wait] {profile} job={job_id}")
    while True:
        job = api("GET", f"/api/install/{job_id}", timeout=30)
        status = str(job.get("status") or "")
        log = job.get("log") or []
        if log:
            line = str(log[-1])
            print(f"  [{status}] {line[:200]}")
        save_state({"current_profile": profile, "job": job})
        if job.get("completed") or status in {"success", "failed", "stopped", "cancelled"}:
            return job
        time.sleep(4)


def start_profile(profile: str) -> dict:
    qs = urllib.parse.urlencode({"profile": profile})
    print(f"[start] {profile}")
    while True:
        try:
            return api("POST", f"/api/install?{qs}", timeout=120)
        except RuntimeError as exc:
            if "409" not in str(exc):
                raise
            print("  installer busy, waiting 8s…")
            time.sleep(8)


def main() -> int:
    cfg = ensure_china_source(load_config())
    os.environ.setdefault("HF_ENDPOINT", str(cfg.get("hf_endpoint") or "https://hf-mirror.com"))
    os.environ.setdefault("HUGGINGFACE_HUB_ENDPOINT", os.environ["HF_ENDPOINT"])

    try:
        health = api("GET", "/api/health", timeout=10)
        print("[api]", health.get("ok", health))
    except Exception as exc:
        print(f"[error] frontend not reachable at {API}: {exc}")
        print("Start the beginner frontend first (START_WORKFLOW / 7860), then re-run this script.")
        return 1

    results = []
    for profile in PROFILES:
        try:
            job = start_profile(profile)
            job_id = str(job.get("id") or "")
            if not job_id:
                raise RuntimeError(f"no job id: {job}")
            finished = wait_job(job_id, profile)
            status = str(finished.get("status") or "unknown")
            results.append({"profile": profile, "status": status, "id": job_id})
            print(f"[done] {profile} -> {status}")
            if status == "failed":
                print(f"  error: {finished.get('error') or finished.get('message')}")
                # continue remaining profiles; user asked to start downloads broadly
        except Exception as exc:
            print(f"[fail] {profile}: {exc}")
            results.append({"profile": profile, "status": "error", "error": str(exc)})

    save_state({"finished_at": time.strftime("%Y-%m-%d %H:%M:%S"), "results": results})
    print("[summary]")
    for item in results:
        print(f"  - {item['profile']}: {item.get('status')}")
    return 0 if all(item.get("status") == "success" for item in results) else 2


if __name__ == "__main__":
    sys.exit(main())
