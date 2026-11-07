"""CPU-only workbench contract regressions. No model/service startup."""
import asyncio
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("BEGINNER_FRONTEND_DISABLE_GPU_PROBES", "1")
os.environ.setdefault("BEGINNER_FRONTEND_DISABLE_JOB_PERSISTENCE", "1")


def check_job_queries():
    from beginner_frontend.job_queries import query_jobs
    records = [{"id": str(i), "created_at": i, "status": "success", "project": "new"} for i in range(150)]
    records.append({"id": "old-failure", "created_at": 0, "status": "failed", "project": "old"})
    records.append({"id": "active", "status": "running", "created_at": 151})
    result = query_jobs(records, limit=5, status="failed")
    assert result["count"] == 1 and result["items"][0]["id"] == "old-failure"
    assert result["projects"] == ["new", "old"] and result["active_count"] == 1
    assert query_jobs(records, status="active")["items"][0]["id"] == "active"
    assert len(query_jobs(records, offset=150)["items"]) == 2
    result["items"][0]["status"] = "changed"
    assert records[-2]["status"] == "failed"


def check_readonly_job_preview():
    from beginner_frontend import app
    refresh = AsyncMock(side_effect=AssertionError("preview must not refresh inference lifecycle"))
    with patch.object(app, "JOBS", {"one": {"id": "one", "status": "success"}}), \
            patch.object(app, "refresh_generation_job", refresh):
        assert asyncio.run(app.get_job("one", refresh=False))["id"] == "one"
        refresh.assert_not_called()


def check_metadata():
    from beginner_frontend.media_metadata import parse_video_metadata
    data = {"streams": [{"codec_type": "audio"}, {"codec_type": "video", "width": 1920,
            "height": 1080, "avg_frame_rate": "30000/1001"}]}
    result = parse_video_metadata(data)
    assert result["height"] == 1080 and 29.9 < result["fps"] < 30
    data["streams"][1]["avg_frame_rate"] = "0/0"
    data["streams"][1]["r_frame_rate"] = "24/1"
    assert parse_video_metadata(data)["fps"] == 24
    assert parse_video_metadata({}) == {}


def check_readonly_http():
    from fastapi.testclient import TestClient
    from beginner_frontend import app
    with patch.object(app, "JOBS", {"one": {"id": "one", "status": "failed", "created_at": 1}}), \
            patch.object(app, "is_loopback_request", return_value=True), \
            patch.object(app, "refresh_generation_job", side_effect=AssertionError("no lifecycle refresh")), \
            patch.object(app, "comfy_get", side_effect=AssertionError("no ComfyUI request")):
        client = TestClient(app.app)
        assert client.get("/api/jobs?status=failed").json()["count"] == 1
        assert client.get("/api/jobs/one?refresh=false").json()["id"] == "one"
        assert client.get("/api/jobs/missing?refresh=false").status_code == 404
    assert app.is_protected_read_path("/api/media/metadata")


def check_static_cache_versions():
    from beginner_frontend import app
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        (root / "index.html").write_text('<script src="/static/app.js?v=placeholder"></script>', encoding="utf-8")
        script = root / "app.js"
        script.write_text("const version = 1;", encoding="utf-8")
        with patch.object(app, "STATIC_DIR", root):
            first = asyncio.run(app.index())
            assert b"placeholder" not in first.body
            assert first.headers["cache-control"].startswith("no-store")
            script.write_text("const version = 2;", encoding="utf-8")
            second = asyncio.run(app.index())
            assert first.body != second.body, "same backend version must still pick up changed assets"
            assert second.body == asyncio.run(app.index()).body
            (root / "index.html").write_text('<script src="/static/app.js?build=placeholder"></script>', encoding="utf-8")
            assert second.body == asyncio.run(app.index()).body, "legacy-safe build URLs must also be fingerprinted"


def check_bounded_asset_detection():
    from scripts import install_workflow_assets as installer
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        item = {"name": "missing.safetensors", "dest": "models/missing.safetensors", "bytes": 5}
        with patch.object(installer, "local_asset_roots", return_value=[root]), \
                patch.object(Path, "rglob", side_effect=AssertionError("UI detection must not recursively scan")):
            assert installer.find_local_asset_candidate(item, base_dir=root, recursive=False) is None


CHECKS = [check_job_queries, check_readonly_job_preview, check_metadata, check_readonly_http, check_static_cache_versions, check_bounded_asset_detection]


def run_all():
    for check in CHECKS:
        check()
    assert "torch" not in sys.modules, "CPU tests must not import torch"
    return [check.__name__ for check in CHECKS]


if __name__ == "__main__":
    print(run_all())
