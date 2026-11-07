"""Download/verify pinned additions without importing torch or starting services."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sys
from urllib.parse import urlparse

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from beginner_frontend.qwen21_updates import ASSETS


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-dir", type=Path, required=True)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    base = args.base_dir.resolve(strict=True)
    missing_bytes = sum(item["bytes"] for item in ASSETS if not (base / item["dest"]).is_file())
    if not args.verify_only and shutil.disk_usage(base).free < missing_bytes + 10 * 1024**3:
        raise RuntimeError("Insufficient disk space, including 10 GiB reserve")
    os.environ.setdefault("HF_XET_CACHE", str(base / ".cache" / "hf_xet"))
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    for asset in ASSETS:
        destination = (base / asset["dest"]).resolve()
        destination.relative_to(base)
        if not destination.is_file() and not args.verify_only:
            from huggingface_hub import hf_hub_download

            parts = urlparse(asset["url"]).path.strip("/").split("/")
            repo, revision, filename = "/".join(parts[:2]), parts[3], "/".join(parts[4:])
            local_dir = destination.parents[len(PurePosixPath(filename).parts) - 1]
            print(f"DOWNLOAD {asset['id']} ({asset['bytes'] / 1024**3:.2f} GiB)", flush=True)
            downloaded = hf_hub_download(repo_id=repo, filename=filename, revision=revision, local_dir=local_dir)
            if Path(downloaded).resolve() != destination:
                raise RuntimeError(f"Unexpected download location: {downloaded}")
        if not destination.is_file() or destination.stat().st_size != asset["bytes"]:
            raise RuntimeError(f"Missing/incomplete file (preserved): {destination}")
        with destination.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if digest != asset["sha256"]:
            raise RuntimeError(f"SHA256 mismatch (file preserved): {destination}")
        print(json.dumps({"id": asset["id"], "bytes": asset["bytes"], "sha256": digest,
                          "path": str(destination), "verified": True}), flush=True)
    if "torch" in sys.modules:
        raise RuntimeError("Unexpected torch import in CPU-only deployment")
    print("PASS: 6 additions verified; no torch import or service startup", flush=True)


if __name__ == "__main__":
    main()
