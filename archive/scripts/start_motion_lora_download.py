"""Restart uvicorn if needed and queue wan22-motion-lora-pack download."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / ".local_ai_workbench_config.json"
LEGACY_CONFIG = ROOT / ".wan22_workflow_config.json"
API = str(os.environ.get("BEGINNER_FRONTEND_URL") or "http://127.0.0.1:7860").rstrip("/")
PROFILE = "wan22-motion-lora-pack"


def token() -> str:
    source = CONFIG if CONFIG.exists() else LEGACY_CONFIG
    if not source.exists():
        return ""
    return str(json.loads(source.read_text(encoding="utf-8")).get("access_token") or "").strip()


def api(method: str, path: str, timeout: float = 120) -> dict:
    req = urllib.request.Request(f"{API}{path}", method=method)
    tok = token()
    if tok:
        req.add_header("Authorization", f"Bearer {tok}")
        req.add_header("X-Local-AI-Token", tok)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", errors="replace")
        return json.loads(body) if body else {}


def listening_pid(port: int = 7860) -> str | None:
    out = subprocess.check_output(["netstat", "-ano", "-p", "tcp"], text=True, errors="replace")
    for line in out.splitlines():
        if f":{port}" in line and "LISTENING" in line.upper():
            return line.split()[-1]
    return None


def restart_frontend() -> None:
    pid = listening_pid(7860)
    if pid and pid != "0":
        print(f"[restart] kill {pid}")
        subprocess.run(["taskkill", "/PID", pid, "/F"], check=False)
        time.sleep(2)
    print("[restart] start uvicorn")
    popen_options = {}
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        popen_options = {
            "startupinfo": startupinfo,
            "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0),
        }
    subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "beginner_frontend.app:app",
            "--host",
            "0.0.0.0",
            "--port",
            "7860",
        ],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **popen_options,
    )
    for _ in range(20):
        try:
            api("GET", "/api/health", timeout=5)
            print("[restart] ready")
            return
        except Exception:
            time.sleep(1)
    raise RuntimeError("frontend did not become ready")


def main() -> int:
    # Always restart so new catalog profile is loaded.
    restart_frontend()
    qs = urllib.parse.urlencode({"profile": PROFILE})
    print(f"[start] {PROFILE}")
    while True:
        try:
            job = api("POST", f"/api/install?{qs}", timeout=180)
            break
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            if exc.code == 409:
                print("  installer busy, wait 8s")
                time.sleep(8)
                continue
            print("[fail]", exc.code, detail[:300])
            return 1
        except Exception as exc:
            print("[fail]", exc)
            return 1
    job_id = str(job.get("id") or "")
    print(f"[job] {job_id} status={job.get('status')}")
    # Wait a bit and print first progress
    for _ in range(8):
        time.sleep(3)
        try:
            cur = api("GET", f"/api/install/{job_id}", timeout=30)
        except Exception as exc:
            print("[wait]", exc)
            continue
        prog = cur.get("progress") or {}
        print(
            f"  [{cur.get('status')}] {prog.get('percent')}% {prog.get('current_file') or ''} "
            f"{prog.get('speed_mb_s') or ''} MB/s"
        )
        if cur.get("completed") or cur.get("status") in {"success", "failed", "cancelled", "stopped"}:
            print("[done]", cur.get("status"))
            return 0 if cur.get("status") == "success" else 2
    print("[queued] download continues in background; check environment install progress")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
