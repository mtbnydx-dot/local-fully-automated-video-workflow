from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


HF_API = "https://huggingface.co/api/models"
WEIGHT_SUFFIXES = (".safetensors", ".ckpt", ".pt", ".pth", ".bin", ".gguf")


def is_official_h3_max_repo(repo_id: str) -> bool:
    owner, separator, name = str(repo_id or "").partition("/")
    if not separator or owner.lower() != "fal":
        return False
    normalized = name.lower().replace("_", "-").replace(".", "-")
    compact = normalized.replace("-", "")
    return "h3max" in compact or "minimaxh3max" in compact


def query_official_repositories(timeout: float) -> list[dict]:
    query = urlencode({"author": "fal", "search": "H3 Max", "limit": 100, "full": "true"})
    request = Request(
        f"{HF_API}?{query}",
        headers={"Accept": "application/json", "User-Agent": "local-ai-video-workbench/1.0"},
    )
    with urlopen(request, timeout=timeout) as response:
        payload = json.load(response)
    return payload if isinstance(payload, list) else []


def repository_summary(item: dict) -> dict:
    repo_id = str(item.get("modelId") or item.get("id") or "")
    siblings = item.get("siblings") if isinstance(item.get("siblings"), list) else []
    files = [str(entry.get("rfilename") or "") for entry in siblings if isinstance(entry, dict)]
    weights = [name for name in files if name.lower().endswith(WEIGHT_SUFFIXES)]
    return {
        "repo_id": repo_id,
        "url": f"https://huggingface.co/{repo_id}" if repo_id else "",
        "private": bool(item.get("private")),
        "gated": item.get("gated", False),
        "last_modified": item.get("lastModified") or "",
        "weight_files": weights,
        "weight_file_count": len(weights),
    }


def download_repository(repo: dict, target: Path) -> dict:
    hf = shutil.which("hf")
    if not hf:
        raise RuntimeError("The Hugging Face `hf` CLI is not installed or not on PATH.")
    repo_id = str(repo["repo_id"])
    local_dir = target / repo_id.split("/", 1)[-1]
    local_dir.mkdir(parents=True, exist_ok=True)
    command = [hf, "download", repo_id, "--local-dir", str(local_dir)]
    completed = subprocess.run(command, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"hf download failed with exit code {completed.returncode}")
    return {"repo_id": repo_id, "local_dir": str(local_dir.resolve())}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check whether fal has published official downloadable H3 Max weights."
    )
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON only.")
    parser.add_argument("--state-file", type=Path, help="Optionally save the result as JSON.")
    parser.add_argument("--download-if-available", action="store_true")
    parser.add_argument(
        "--target",
        type=Path,
        default=Path("models") / "diffusion_models" / "FalH3Max",
        help="Download root used only with --download-if-available.",
    )
    args = parser.parse_args()

    try:
        items = query_official_repositories(args.timeout)
        repositories = [
            repository_summary(item)
            for item in items
            if is_official_h3_max_repo(str(item.get("modelId") or item.get("id") or ""))
        ]
        downloadable = [repo for repo in repositories if repo["weight_file_count"] > 0]
        result = {
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "source": "https://huggingface.co/fal",
            "official_repo_found": bool(repositories),
            "weights_available": bool(downloadable),
            "repositories": repositories,
            "downloaded": [],
            "policy": "Only repositories owned by the exact Hugging Face organization `fal` are accepted.",
        }
        if args.download_if_available:
            result["downloaded"] = [download_repository(repo, args.target) for repo in downloadable]
    except Exception as exc:
        result = {
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "source": "https://huggingface.co/fal",
            "official_repo_found": False,
            "weights_available": False,
            "repositories": [],
            "downloaded": [],
            "error": str(exc),
        }

    serialized = json.dumps(result, ensure_ascii=False, indent=2)
    if args.state_file:
        args.state_file.parent.mkdir(parents=True, exist_ok=True)
        args.state_file.write_text(serialized + "\n", encoding="utf-8")
    if args.json:
        print(serialized)
    else:
        if result.get("error"):
            print(f"Check failed: {result['error']}", file=sys.stderr)
        elif result["weights_available"]:
            print("Official fal H3 Max weights are available.")
            for repo in result["repositories"]:
                print(f"- {repo['repo_id']}: {repo['weight_file_count']} weight files")
        else:
            print("No official downloadable fal H3 Max weights were found. API-only configuration remains active.")
    return 2 if result.get("error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
