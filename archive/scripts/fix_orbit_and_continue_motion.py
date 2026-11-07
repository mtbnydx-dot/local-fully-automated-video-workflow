"""Fix stuck orbit LoRA download then continue wan22-motion-lora-pack."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / ".local_ai_workbench_config.json"
LEGACY_CONFIG = ROOT / ".wan22_workflow_config.json"


def default_comfy_base() -> Path:
    configured = str(os.environ.get("COMFY_BASE_DIR") or "").strip()
    if configured:
        return Path(configured).expanduser()
    local_app_data = str(os.environ.get("LOCALAPPDATA") or "").strip()
    if local_app_data:
        desktop_base = Path(local_app_data) / "Comfy-Desktop" / "ComfyUI-Shared"
        if desktop_base.exists():
            return desktop_base
    return ROOT


MOTION = default_comfy_base() / "models" / "loras" / "Wan2.2" / "Motion"
API = str(os.environ.get("BEGINNER_FRONTEND_URL") or "http://127.0.0.1:7860").rstrip("/")
JOB = str(os.environ.get("WAN22_STUCK_JOB_ID") or "").strip()

FILES = [
    (
        "orbit_shot_high.safetensors",
        "https://huggingface.co/ostris/wan22_i2v_14b_orbit_shot_lora/resolve/main/wan22_14b_i2v_orbit_high_noise.safetensors",
        153468928,
    ),
    (
        "orbit_shot_low.safetensors",
        "https://huggingface.co/ostris/wan22_i2v_14b_orbit_shot_lora/resolve/main/wan22_14b_i2v_orbit_low_noise.safetensors",
        153468928,
    ),
]


def token() -> str:
    source = CONFIG if CONFIG.exists() else LEGACY_CONFIG
    if not source.exists():
        return ""
    return str(json.loads(source.read_text(encoding="utf-8")).get("access_token") or "").strip()


def api(method: str, path: str, timeout: float = 60) -> dict:
    req = urllib.request.Request(f"{API}{path}", method=method)
    tok = token()
    if tok:
        req.add_header("Authorization", f"Bearer {tok}")
        req.add_header("X-Local-AI-Token", tok)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", errors="replace")
        return json.loads(body) if body else {}


def download(url: str, dest: Path, expected: int) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    for suffix in (".part", ""):
        stale = Path(str(dest) + suffix) if suffix else dest
        if stale.exists() and stale.stat().st_size != expected:
            stale.unlink(missing_ok=True)
    if dest.exists() and dest.stat().st_size == expected:
        print(f"[skip] {dest.name}")
        return
    # Prefer China mirror first, then official.
    urls = []
    if "huggingface.co/" in url:
        urls.append(url.replace("https://huggingface.co/", "https://hf-mirror.com/"))
    urls.append(url)
    last_error: Exception | None = None
    for candidate in urls:
        try:
            print(f"[get] {dest.name} via {candidate.split('/')[2]}")
            req = urllib.request.Request(candidate, headers={"User-Agent": "local-ai-video-workbench-motion-fetch/1.0"})
            with urllib.request.urlopen(req, timeout=120) as resp, open(dest, "wb") as out:
                while True:
                    chunk = resp.read(1024 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
            size = dest.stat().st_size
            print(f"[ok] {dest.name} {size}")
            if expected and size != expected:
                print(f"[warn] size {size} != expected {expected}")
            return
        except Exception as exc:
            last_error = exc
            dest.unlink(missing_ok=True)
            print(f"[fail] {candidate.split('/')[2]}: {exc}")
    raise RuntimeError(last_error)


def main() -> int:
    if JOB:
        try:
            api("POST", f"/api/install/{JOB}/cancel")
            print("[cancel] old job")
            time.sleep(2)
        except Exception as exc:
            print("[cancel]", exc)

    for name, url, expected in FILES:
        download(url, MOTION / name, expected)

    print("[start] wan22-motion-lora-pack")
    while True:
        try:
            job = api("POST", "/api/install?profile=wan22-motion-lora-pack", timeout=180)
            break
        except urllib.error.HTTPError as exc:
            if exc.code == 409:
                print(" busy, wait")
                time.sleep(5)
                continue
            raise
    print("[job]", job.get("id"), job.get("status"))
    jid = str(job.get("id") or "")
    for _ in range(10):
        time.sleep(4)
        cur = api("GET", f"/api/install/{jid}")
        prog = cur.get("progress") or {}
        print(cur.get("status"), prog.get("percent"), prog.get("current_file"), prog.get("speed_mb_s"))
        if cur.get("completed") or cur.get("status") in {"success", "failed", "cancelled", "stopped"}:
            return 0 if cur.get("status") == "success" else 2
    print("[bg] continuing")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
