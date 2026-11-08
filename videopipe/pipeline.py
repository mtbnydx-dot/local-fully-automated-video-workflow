import hashlib
import json
import random
import shutil
from collections import deque
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path
from queue import Queue

from .inputs import load_config, load_package, snapshot_inputs, validate_plan
from .models import PipelineConfig, ScriptPackage, Shot
from .records import Events, now, write_json


class Production:
    def __init__(self, run_dir: Path):
        self.root = run_dir.resolve()
        self.package = load_package(self.root / "package.json")
        self.config = load_config(self.root / "config.json")
        self.state = json.loads((self.root / "state.json").read_text(encoding="utf-8"))
        if self.state["version"] != 2:
            raise ValueError("This run uses the old workflow. Keep it with dev-jz; create a new run for this workflow.")
        self.events = Events(self.root)
        self.generators, self.reviewer = self._backends()

    @classmethod
    def create(cls, package: ScriptPackage, config: PipelineConfig, run_dir: Path):
        validate_plan(package, config)
        root = run_dir.resolve()
        root.mkdir(parents=True, exist_ok=False)
        snapshot_inputs(root, package, config)
        write_json(root / "state.json", {
            "version": 2, "title": package.title, "created_at": now(),
            "status": "pending", "assembly_version": 0,
            "shots": {shot.id: {"status": "pending", "attempts": 0, "budget_used": 0,
                                "round": 0, "takes": []} for shot in package.shots},
        })
        return cls(root)

    def run(self, *, auto_approve: bool = False) -> dict:
        try:
            return self._run(auto_approve=auto_approve)
        except (Exception, KeyboardInterrupt) as exc:
            self.state.update(status="failed", error=str(exc) or "Interrupted")
            self.events.emit("run_failed", error=self.state["error"])
            self._save()
            raise
        finally:
            self.events.close()

    def _run(self, *, auto_approve: bool) -> dict:
        if self.state["status"] == "complete":
            return self.state
        if self.state.get("approval"):
            return self._deliver()
        if self.state["status"] == "awaiting_approval":
            if auto_approve:
                self.state["approval"] = {"time": now(), "method": "automatic"}
                return self._deliver()
            return self.state
        self.state.update(status="running", error=None)
        self.events.emit("run_started", generator=self.config.generator, reviewer=self.config.review.backend)
        self._save()
        self._produce_clips()
        if not all(record["status"] == "ready" for record in self.state["shots"].values()):
            self.state["status"] = "needs_attention"
            self._save()
            return self.state
        if not self.state.get("draft"):
            self._assemble()
        if not self.state.get("audio"):
            self._process_audio()
        if auto_approve or not self.config.human_approval:
            self.state["approval"] = {"time": now(), "method": "automatic"}
            return self._deliver()
        self.state["status"] = "awaiting_approval"
        self._save()
        return self.state

    def approve(self) -> dict:
        if self.state["status"] != "awaiting_approval":
            self.events.close()
            raise ValueError("Run must be awaiting_approval before approval")
        self.state["approval"] = {"time": now(), "method": "cli"}
        self._save()
        return self.run()

    def retry(self, shot_ids: list[str], *, feedback: str = "", new_round: bool = False) -> None:
        unknown = set(shot_ids) - self.state["shots"].keys()
        if unknown:
            raise ValueError(f"Unknown shot IDs: {', '.join(sorted(unknown))}")
        exhausted = [key for key in shot_ids if self.state["shots"][key]["budget_used"] >= self.config.max_attempts]
        if exhausted and not new_round:
            raise ValueError("Generation budget exhausted for " + ", ".join(exhausted) +
                             ". An explicitly requested new production round requires --new-round.")
        for shot_id in shot_ids:
            record = self.state["shots"][shot_id]
            if new_round:
                record["round"] += 1
                record["budget_used"] = 0
            record.update(status="pending", feedback=feedback)
            for key in ("selection", "clip", "duration", "error"):
                record.pop(key, None)
        for key in ("approval", "final", "delivery", "error", "draft", "manifest", "audio"):
            self.state.pop(key, None)
        self.state["status"] = "pending"
        self.events.emit("retry_requested", shots=shot_ids, feedback=feedback, new_round=new_round)
        self._save()

    def _produce_clips(self) -> None:
        generation_jobs, review_jobs = self._pending_jobs()
        futures = {}
        with ThreadPoolExecutor(max_workers=self.config.workers) as gpu_pool, \
                ThreadPoolExecutor(max_workers=self.config.review.workers) as review_pool:
            while generation_jobs or review_jobs or futures:
                gpu_busy = sum(stage != "review" for stage, _, _ in futures.values())
                while generation_jobs and gpu_busy < self.config.workers:
                    stage, shot, take = generation_jobs.popleft()
                    if stage == "generate" and take is None:
                        take = self._new_take(shot)
                    operation = self._generate if stage == "generate" else self._upscale
                    futures[gpu_pool.submit(operation, shot, take)] = (stage, shot, take)
                    gpu_busy += 1
                review_busy = sum(stage == "review" for stage, _, _ in futures.values())
                while review_jobs and review_busy < self.config.review.workers:
                    shot, take = review_jobs.popleft()
                    take["status"] = "reviewing"
                    self._save()
                    futures[review_pool.submit(self._review, shot, take)] = ("review", shot, take)
                    review_busy += 1
                if not futures:
                    break
                completed, _ = wait(futures, return_when=FIRST_COMPLETED)
                for future in completed:
                    stage, shot, take = futures.pop(future)
                    record = self.state["shots"][shot.id]
                    try:
                        result = future.result()
                    except Exception as exc:
                        record.update(status="failed", error=str(exc))
                        take["error"] = str(exc)
                        # A ComfyUI timeout leaves its job running; resume the same take.
                        take["status"] = "generating" if stage == "generate" and isinstance(exc, TimeoutError) else "failed"
                        self.events.emit("job_failed", shot=shot.id, take=take["id"], stage=stage, error=str(exc))
                        if stage == "generate" and not isinstance(exc, TimeoutError):
                            if record["budget_used"] < self.config.max_attempts:
                                generation_jobs.append(("generate", shot, None))
                            else:
                                self._select_random(shot, "budget_exhausted")
                                if record.get("selection"):
                                    generation_jobs.appendleft(("upscale", shot, self._selected_take(record)))
                        self._save()
                        continue
                    if stage == "generate":
                        take.update(status="generated", source=result)
                        review_jobs.append((shot, take))
                    elif stage == "review":
                        take.update(status="reviewed", review=result.model_dump(mode="json"))
                        self.events.emit("shot_reviewed", shot=shot.id, take=take["id"],
                                         passed=result.passed, available=result.available, summary=result.summary)
                        if result.available and result.passed:
                            self._select(shot, take, "review_pass")
                        elif not result.available:
                            self._select_random(shot, "review_unavailable")
                        elif record["budget_used"] >= self.config.max_attempts:
                            self._select_random(shot, "budget_exhausted")
                        else:
                            record["status"] = "pending"
                            generation_jobs.append(("generate", shot, None))
                        if record.get("selection"):
                            selected = self._selected_take(record)
                            generation_jobs.appendleft(("upscale", shot, selected))
                    else:
                        record.update(status="ready", clip=result["clip"], duration=result["duration"], error=None)
                    self._save()

    def _pending_jobs(self):
        generation_jobs, review_jobs = deque(), deque()
        for shot in self.package.shots:
            record = self.state["shots"][shot.id]
            if record["status"] == "ready":
                continue
            if record.get("selection"):
                generation_jobs.append(("upscale", shot, self._selected_take(record)))
                continue
            current = [take for take in record["takes"] if take["round"] == record["round"]]
            last = current[-1] if current else None
            if last and last["status"] == "generating":
                generation_jobs.append(("generate", shot, last))
            elif last and last["status"] in {"generated", "reviewing"}:
                review_jobs.append((shot, last))
            elif record["budget_used"] < self.config.max_attempts:
                generation_jobs.append(("generate", shot, None))
            else:
                self._select_random(shot, "budget_exhausted")
                if record.get("selection"):
                    generation_jobs.append(("upscale", shot, self._selected_take(record)))
        return generation_jobs, review_jobs

    def _new_take(self, shot: Shot) -> dict:
        record = self.state["shots"][shot.id]
        record["attempts"] += 1
        record["budget_used"] += 1
        take = {"id": record["attempts"], "round": record["round"],
                "seed": shot.seed + record["attempts"] - 1, "status": "generating",
                "prompt_hash": hashlib.sha256(shot.prompt.encode("utf-8")).hexdigest()}
        record["takes"].append(take)
        record["status"] = "generating"
        # Persist the generation allowance before starting GPU work.
        self._save()
        return take

    def _generate(self, shot: Shot, take: dict) -> str:
        from .media import inspect_video

        folder = self._take_folder(shot, take)
        folder.mkdir(parents=True, exist_ok=True)
        current = shot.model_copy(update={"seed": take["seed"]})
        write_json(folder / "shot.json", current.model_dump(mode="json"))
        generator = self.generators.get()
        try:
            with self.events.stage("generate", shot=shot.id, take=take["id"], seed=take["seed"]):
                source = generator.generate(current, folder, attempt=take["id"])
                inspect_video(source)
        finally:
            self.generators.put(generator)
        return str(source.relative_to(self.root))

    def _review(self, shot: Shot, take: dict):
        folder = self._take_folder(shot, take) / "review"
        with self.events.stage("shot_review", shot=shot.id, take=take["id"]):
            result = self.reviewer.review(self.root / take["source"], shots=[shot], scope="shot", output_dir=folder)
        write_json(folder / "result.json", result.model_dump(mode="json"))
        return result

    def _select_random(self, shot: Shot, reason: str) -> None:
        record = self.state["shots"][shot.id]
        candidates = [take for take in record["takes"] if take["round"] == record["round"] and take.get("source")]
        if not candidates:
            record.update(status="missing", error="No usable generated take")
            self._save()
            return
        selection_seed = random.getrandbits(64)
        take = random.Random(selection_seed).choice(candidates)
        self._select(shot, take, reason, candidates=[candidate["id"] for candidate in candidates],
                     selection_seed=selection_seed)

    def _select(self, shot: Shot, take: dict, reason: str, **details) -> None:
        record = self.state["shots"][shot.id]
        flags = [] if reason == "review_pass" else [reason, "selected_take_random"]
        record.update(status="selected", selection={"take_id": take["id"], "reason": reason,
                                                    "flags": flags, **details})
        write_json(self.root / "shots" / shot.id / "selection.json", record["selection"])
        self.events.emit("take_selected", shot=shot.id, **record["selection"])
        self._save()

    def _selected_take(self, record: dict) -> dict:
        return next(take for take in record["takes"] if take["id"] == record["selection"]["take_id"])

    def _take_folder(self, shot: Shot, take: dict) -> Path:
        return self.root / "shots" / shot.id / f"attempt-{take['id']:03d}"

    def _output_config(self):
        factor = self.config.media.upscale_factor if self.config.media.upscale != "none" else 1
        return self.config.media.model_copy(update={"upscale": "none", "width": self.config.media.width * factor,
                                                    "height": self.config.media.height * factor})

    def _upscale(self, shot: Shot, take: dict) -> dict:
        from .media import inspect_video, normalize_clip

        folder = self._take_folder(shot, take)
        source = self.root / take["source"]
        with self.events.stage("upscale", shot=shot.id, take=take["id"]):
            if self.config.media.upscale == "comfyui":
                generator = self.generators.get()
                try:
                    source = generator.upscale(source, folder / "upscale", factor=self.config.media.upscale_factor)
                finally:
                    self.generators.put(generator)
            clip = normalize_clip(source, folder / "clip.mp4", config=self._output_config())
        info = inspect_video(clip)
        return {"clip": str(clip.relative_to(self.root)), "duration": info.duration}

    def _assemble(self) -> None:
        from .media import assemble

        self.state["assembly_version"] += 1
        folder = self.root / "film" / f"version-{self.state['assembly_version']:03d}"
        clips, manifest, offset = [], [], 0.0
        for shot in self.package.shots:
            record = self.state["shots"][shot.id]
            clips.append(self.root / record["clip"])
            manifest.append({"shot_id": shot.id, "clip": record["clip"], "start": offset,
                             "duration": record["duration"], **record["selection"]})
            offset += record["duration"]
        with self.events.stage("assemble", version=self.state["assembly_version"]):
            draft = assemble(clips, folder / "draft.mp4", self._output_config())
        write_json(folder / "manifest.json", manifest)
        self.state.update(draft=str(draft.relative_to(self.root)), manifest=str((folder / "manifest.json").relative_to(self.root)))
        self._save()

    def _process_audio(self) -> None:
        from .backends.asr import transcribe
        from .subtitles import create_subtitles, extract_dialogue

        folder = (self.root / self.state["draft"]).parent / "audio"
        with self.events.stage("asr"):
            transcript = transcribe(self.root / self.state["draft"], self.config.asr, folder)
        timed_shots = [shot.model_copy(update={"duration": self.state["shots"][shot.id]["duration"]})
                       for shot in self.package.shots]
        subtitles = create_subtitles(timed_shots, transcript, folder / "subtitles")
        consistency = self.reviewer.compare_transcript(
            extract_dialogue(timed_shots), transcript, folder / "comparison")
        write_json(folder / "consistency.json", consistency)
        self.state["audio"] = {"transcript": transcript, "consistency": consistency, "subtitles": subtitles}
        self.events.emit("audio_reported", asr_status=transcript["status"], consistency=consistency,
                         subtitle_status=subtitles["status"])
        self._save()

    def _deliver(self) -> dict:
        from .media import finalize, inspect_video
        from .subtitles import write_ass

        self.state["status"] = "delivering"
        self._save()
        folder = self.root / "delivery" / f"version-{self.state['assembly_version']:03d}"
        output = self._output_config()
        subtitles = self.state["audio"]["subtitles"]
        style = self.config.subtitles
        burn = style.burn and subtitles["status"] == "complete"
        with self.events.stage("finalize", version=self.state["assembly_version"], burn_subtitles=burn):
            ass = write_ass(Path(subtitles["path"]), folder / "episode.ass", style, output.width, output.height) if burn else None
            final = finalize(self.root / self.state["draft"], folder / "final.mp4", output,
                             subtitles=ass, fonts=style.font_path.parent if burn else None)
        if subtitles.get("path"):
            shutil.copy2(subtitles["path"], folder / "episode.srt")
        info = inspect_video(final)
        self.state.update(status="complete", final=str(final.relative_to(self.root)), completed_at=now(),
                          delivery={"width": info.width, "height": info.height, "duration": info.duration,
                                    "fps": info.fps, "has_audio": info.has_audio, "burned_subtitles": burn})
        report = {"video": self.state["final"], "delivery": self.state["delivery"],
                  "shots": self.state["shots"], "audio": self.state["audio"],
                  "manifest": self.state["manifest"], "approval": self.state["approval"]}
        write_json(folder / "production_report.json", report)
        self.events.emit("run_completed", final=self.state["final"], **self.state["delivery"])
        self._save()
        return self.state

    def _backends(self):
        from .backends.cpu import CPUGenerator
        from .backends.review import CPUReviewer, VLLMReviewer

        generators = Queue()
        if self.config.generator == "cpu":
            for _ in range(self.config.workers):
                generators.put(CPUGenerator())
        else:
            from .backends.comfyui import ComfyGenerator
            for url in self.config.comfyui.urls:
                generators.put(ComfyGenerator(self.config.comfyui, url=url))
        reviewer_type = CPUReviewer if self.config.review.backend == "cpu" else VLLMReviewer
        reviewer = reviewer_type(self.config.review, script=self.package.script.read_text(encoding="utf-8"))
        return generators, reviewer

    def _save(self) -> None:
        self.state["updated_at"] = now()
        write_json(self.root / "state.json", self.state)
