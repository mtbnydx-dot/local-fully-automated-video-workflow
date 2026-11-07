"""Execute image dependencies through image services or a local tool bridge."""

from __future__ import annotations

import asyncio
import base64
import json
import shutil
import time
from collections import Counter
from contextlib import AsyncExitStack
from dataclasses import asdict
from pathlib import Path

import httpx

from .client import ImageClient
from .delivery import deliver_original
from .models import CopyTask, ImageConfig, ImagePlan, ImageTask
from .tool_bridge import prepare_tool_args


async def run(plan: ImagePlan, config: ImageConfig, run_dir: Path) -> dict:
    pipeline = ImagePipeline(plan, config, run_dir)
    return await pipeline.run()


class ImagePipeline:
    def __init__(self, plan: ImagePlan, config: ImageConfig, run_dir: Path):
        self.plan, self.config, self.run_dir = plan, config, run_dir.resolve()
        self.tasks = {task.asset_id: task for task in plan.tasks}
        self.run_dir.mkdir(parents=True, exist_ok=True)
        state_path = self.run_dir / "state.json"
        self.state = json.loads(state_path.read_text()) if state_path.exists() else {
            "started_at": time.time(), "tasks": {},
        }
        for task in plan.tasks:
            self.state["tasks"].setdefault(task.asset_id, {"status": "pending", "attempts": 0})
        self.window = asyncio.Semaphore(config.scheduler.max_active_jobs)
        self.workers: dict[str, asyncio.Task] = {}

    async def run(self) -> dict:
        _write_json(self.run_dir / "tasks.json", {**asdict(self.plan), "config": self.config.model_dump()})
        self._event("run_started", tasks=len(self.tasks), copies=len(self.plan.copies))
        async with AsyncExitStack() as stack:
            if self.config.provider != "codex":
                self.client = await stack.enter_async_context(ImageClient(self.config))
            for task in self.plan.tasks:
                self.workers[task.asset_id] = asyncio.create_task(self._run_task(task))
            await asyncio.gather(*self.workers.values())
        copies, missing = self._copy_references()
        report = self._report()
        report.update(copies_completed=copies, copies_total=len(self.plan.copies), copies_missing=missing)
        report["success"] = report["counts"].get("completed", 0) == len(self.tasks) and not missing
        report["finished_at"] = time.time()
        _write_json(self.run_dir / "report.json", report)
        self._event("run_finished", success=report["success"], copies_completed=copies)
        return report

    async def _run_task(self, task: ImageTask) -> None:
        record = self.state["tasks"][task.asset_id]
        target = Path(task.target_path)
        if target.is_file():
            original = self.run_dir / "originals" / f"{task.asset_id}.png"
            if original.is_file():
                record.update(await asyncio.to_thread(deliver_original, original, target))
            record.update(status="completed", reused=not bool(record.get("completed_at") or record.get("job_id")),
                          path=str(target))
            self._event("reused", task.asset_id)
            return
        await asyncio.gather(*(self.workers[ref] for ref in task.reference_ids))
        failed = [ref for ref in task.reference_ids if self.state["tasks"][ref]["status"] != "completed"]
        if failed:
            record.update(status="blocked", error=f"References failed: {', '.join(failed)}")
            self._event("blocked", task.asset_id, references=failed)
            return
        async with self.window:
            try:
                await self._generate(task, record)
            except (httpx.HTTPError, OSError, ValueError, KeyError, RuntimeError) as error:
                record.update(status="failed", error=str(error))
                self._event("failed", task.asset_id, error=str(error))

    async def _generate(self, task: ImageTask, record: dict) -> None:
        original = self.run_dir / "originals" / f"{task.asset_id}.png"
        record.setdefault("submitted_at", time.time())
        if self.config.provider == "gpt":
            await self._generate_gpt(task, record, original)
        elif self.config.provider == "codex":
            await self._generate_codex(task, record, original)
        else:
            await self._generate_qwen(task, record, original)
        delivery_started = time.time()
        dimensions = await asyncio.to_thread(
            deliver_original, original, Path(task.target_path),
        )
        finished = time.time()
        record.update(
            status="completed", completed_at=finished, original=str(original), path=task.target_path, reused=False,
            delivery_seconds=round(finished - delivery_started, 3),
            job_wall_seconds=round(finished - record["submitted_at"], 3), **dimensions,
        )
        record.pop("error", None)
        self._event("completed", task.asset_id, job_id=record.get("job_id"), request_id=record.get("request_id"),
                    job_wall_seconds=record["job_wall_seconds"], **dimensions)

    async def _generate_gpt(self, task: ImageTask, record: dict, original: Path) -> None:
        # An already saved original can be delivered again without another paid request.
        if original.is_file():
            return
        references = []
        for ref in task.reference_ids:
            native = self.run_dir / "originals" / f"{ref}.png"
            references.append(native if native.is_file() else Path(self.tasks[ref].target_path))
        record.update(status="submitting", attempts=record["attempts"] + 1, submitted_at=time.time())
        self._event("submitting", task.asset_id, provider="gpt", mode=task.mode)
        result = await self.client.submit(task, references)
        original.parent.mkdir(parents=True, exist_ok=True)
        original.write_bytes(base64.b64decode(result["data"][0]["b64_json"]))
        record.update(status="delivering", original=str(original), request_id=result["request_id"],
                      usage=result.get("usage", {}), model=self.config.generation.model,
                      quality=result.get("quality", self.config.generation.quality),
                      api_seconds=round(time.time() - record["submitted_at"], 3))
        self._event("generated", task.asset_id, request_id=record["request_id"], usage=record["usage"])

    async def _generate_codex(self, task: ImageTask, record: dict, original: Path) -> None:
        if original.is_file():
            return
        references = []
        for ref in task.reference_ids:
            native = self.run_dir / "originals" / f"{ref}.png"
            references.append(native if native.is_file() else Path(self.tasks[ref].target_path))
        tool_args = await asyncio.to_thread(
            prepare_tool_args, task.prompt, references, self.run_dir / "reference_sheets" / task.asset_id,
        )
        request_path = self.run_dir / "requests" / f"{task.asset_id}.json"
        response_path = self.run_dir / "responses" / f"{task.asset_id}.json"
        if not request_path.exists():
            record["attempts"] += 1
        request_path.parent.mkdir(parents=True, exist_ok=True)
        _write_json(request_path, {
            "asset_id": task.asset_id, "tool": "image_gen.imagegen", "tool_args": tool_args,
            "target_path": task.target_path,
        })
        record.update(status="waiting_for_tool", request_path=str(request_path))
        self._event("tool_requested", task.asset_id, request_path=str(request_path))
        while not response_path.is_file():
            await asyncio.sleep(self.config.scheduler.poll_interval_seconds)
        response = json.loads(response_path.read_text())
        original.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(shutil.copy2, response["image_path"], original)
        record.update(status="delivering", original=str(original), tool="image_gen.imagegen",
                      tool_image_path=response["image_path"])
        self._event("generated", task.asset_id, tool=record["tool"])

    async def _generate_qwen(self, task: ImageTask, record: dict, original: Path) -> None:
        references = [Path(self.tasks[ref].target_path) for ref in task.reference_ids]
        while True:
            if not record.get("job_id"):
                record.update(status="submitting", attempts=record["attempts"] + 1)
                submitted_at = time.time()
                submission = await self.client.submit(task, references)
                record.update(job_id=submission["id"], submitted_at=submitted_at, status=submission["status"])
                record.pop("error", None)
                self._event("submitted", task.asset_id, job_id=record["job_id"], mode=task.mode)
            job_id = record["job_id"]
            while True:
                remote = await self._read(self.client.status, job_id)
                status = remote["status"]
                local_status = "downloading" if status == "completed" else status
                if local_status != record["status"]:
                    record["status"] = local_status
                    self._event("remote_status", task.asset_id, job_id=job_id, status=status)
                if status in {"completed", "failed", "cancelled"}:
                    break
                await asyncio.sleep(self.config.scheduler.poll_interval_seconds)
            if status == "completed":
                break
            error = remote.get("error") or f"Remote job {status}"
            self._event("remote_failed", task.asset_id, job_id=job_id, error=error)
            record["job_id"] = None
            if record["attempts"] >= self.config.scheduler.max_attempts:
                raise RuntimeError(str(error))
            await asyncio.sleep(self.config.scheduler.poll_interval_seconds)

        record.update(status="downloading", remote_completed_at=time.time())
        results = await self._read(self.client.results, job_id)
        download_started = time.time()
        await self._read(self.client.download, results["data"][0]["url"], original)
        record["download_seconds"] = round(time.time() - download_started, 3)

    async def _read(self, operation, *args):
        for attempt in range(self.config.scheduler.max_attempts):
            try:
                return await operation(*args)
            except httpx.HTTPError as error:
                if isinstance(error, httpx.HTTPStatusError) and error.response.status_code < 500 and error.response.status_code != 429:
                    raise
                if attempt + 1 == self.config.scheduler.max_attempts:
                    raise
                await asyncio.sleep(self.config.scheduler.poll_interval_seconds * (attempt + 1))

    def _copy_references(self) -> tuple[int, list[str]]:
        copied, missing = 0, []
        for item in self.plan.copies:
            source, target = Path(item.source_path), Path(item.target_path)
            if not source.is_file():
                missing.append(str(target))
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            if source != target:
                shutil.copy2(source, target)
            copied += 1
        return copied, missing

    def _event(self, event: str, asset_id: str | None = None, **fields) -> None:
        self.state["updated_at"] = time.time()
        _write_json(self.run_dir / "state.json", self.state)
        counts = dict(Counter(item["status"] for item in self.state["tasks"].values()))
        entry = {"time": self.state["updated_at"], "event": event, "asset_id": asset_id, **fields, "counts": counts}
        line = json.dumps(entry, ensure_ascii=False)
        with (self.run_dir / "events.jsonl").open("a") as stream:
            stream.write(line + "\n")
        print(line, flush=True)

    def _report(self) -> dict:
        records = self.state["tasks"]
        elapsed = time.time() - self.state["started_at"]
        generated = [item for item in records.values() if item["status"] == "completed" and not item.get("reused")]
        return {
            "package_root": self.plan.package_root, "run_dir": str(self.run_dir),
            "started_at": self.state["started_at"], "elapsed_seconds": round(elapsed, 3),
            "provider": self.config.provider,
            "generation": self.config.generation.model_dump(), "scheduler": self.config.scheduler.model_dump(),
            "counts": dict(Counter(item["status"] for item in records.values())),
            "generated": len(generated), "reused": sum(bool(item.get("reused")) for item in records.values()),
            "images_per_minute": round(len(generated) * 60 / elapsed, 3) if elapsed else 0,
            "errors": {key: item["error"] for key, item in records.items() if item.get("error")},
        }


def load_run(run_dir: Path) -> tuple[ImagePlan, ImageConfig]:
    data = json.loads((run_dir / "tasks.json").read_text())
    data["config"].setdefault("provider", "qwen")
    return ImagePlan(
        package_root=data["package_root"],
        tasks=[ImageTask(**task) for task in data["tasks"]],
        copies=[CopyTask(**item) for item in data["copies"]],
    ), ImageConfig.model_validate(data["config"])


def _write_json(path: Path, value: dict) -> None:
    pending = path.with_suffix(".json.tmp")
    pending.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    pending.replace(path)
