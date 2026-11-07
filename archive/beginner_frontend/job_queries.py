"""Read-only task queries, separate from inference lifecycle refresh."""
from copy import deepcopy

TERMINAL = {"success", "failed", "error", "canceled", "cancelled", "interrupted", "stopped", "lost"}


def query_jobs(records, *, limit=20, offset=0, status="all", project=""):
    jobs = sorted(records, key=lambda item: int(item.get("created_at") or 0), reverse=True)
    projects = sorted({str(item.get("project")) for item in jobs if item.get("project")})
    active = sum(not item.get("completed") and item.get("status") not in TERMINAL for item in jobs)
    if project:
        jobs = [item for item in jobs if item.get("project") == project]
    if status == "active":
        jobs = [item for item in jobs if not item.get("completed") and item.get("status") not in TERMINAL]
    elif status == "success":
        jobs = [item for item in jobs if item.get("status") == "success"]
    elif status == "failed":
        jobs = [item for item in jobs if item.get("status") in TERMINAL - {"success"}]
    elif status == "video":
        jobs = [item for item in jobs if str(item.get("kind", "")).startswith("video")
                or any(media.get("kind") == "video" for media in item.get("media", []))]
    offset = max(0, int(offset))
    limit = max(1, min(100, int(limit)))
    return {"items": deepcopy(jobs[offset:offset + limit]), "count": len(jobs),
            "offset": offset, "limit": limit, "active_count": active, "projects": projects}
