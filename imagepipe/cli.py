"""Command line entry point for unattended image production."""

import argparse
import asyncio
import json
import sys
import time
from collections import Counter
from pathlib import Path

import yaml

from scriptpipe.batch import export_batch, parse_episode_range

from .models import ImageConfig
from .pipeline import load_run, run
from .plan import compile_plan
from .tool_bridge import accept_image, pending_requests


def main() -> int:
    parser = argparse.ArgumentParser(prog="imagepipe")
    commands = parser.add_subparsers(dest="command", required=True)
    start = commands.add_parser("run", help="Fill an episode or season's image slots")
    start.add_argument("package", type=Path)
    start.add_argument("--provider", choices=["gpt", "qwen", "codex"], help="Image backend (default: gpt)")
    start.add_argument("--config", type=Path, help="Override the selected provider's YAML config")
    start.add_argument("--output", type=Path)
    start.add_argument("--episodes", type=parse_episode_range, help="Episode range, for example ep01-ep10 or 1-10")
    start.add_argument("--delivery", type=Path, help="Export the selected episodes as a video-ready package after images complete")
    for name in ("resume", "status", "pending"):
        commands.add_parser(name).add_argument("run_dir", type=Path)
    accept = commands.add_parser("accept", help="Supply a Codex tool-generated image to its pending task")
    accept.add_argument("run_dir", type=Path)
    accept.add_argument("asset_id")
    accept.add_argument("image_path", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "pending":
            print(json.dumps(pending_requests(args.run_dir.resolve()), ensure_ascii=False, indent=2))
            return 0
        if args.command == "accept":
            print(json.dumps(accept_image(args.run_dir.resolve(), args.asset_id, args.image_path),
                             ensure_ascii=False))
            return 0
        if args.command == "status":
            state = json.loads((args.run_dir / "state.json").read_text())
            print(json.dumps({
                "run_dir": str(args.run_dir),
                "elapsed_seconds": round(time.time() - state["started_at"], 1),
                "counts": dict(Counter(item["status"] for item in state["tasks"].values())),
                "errors": {key: item["error"] for key, item in state["tasks"].items() if item.get("error")},
            }, ensure_ascii=False, indent=2))
            return 0
        if args.command == "resume":
            output = args.run_dir.resolve()
            plan, config = load_run(output)
            batch_path = output / "batch.json"
            batch = json.loads(batch_path.read_text()) if batch_path.exists() else {}
        else:
            if args.delivery and not args.episodes:
                raise ValueError("--delivery requires --episodes")
            config = _load_config(args.config, args.provider)
            config.api.env_file = str(Path(config.api.env_file).resolve())
            default_output = Path("runs/imagepipe") / args.package.name / config.provider
            if args.episodes:
                default_output /= f"{args.episodes[0]}-{args.episodes[-1]}"
            output = (args.output or default_output).resolve()
            batch_path = output / "batch.json"
            batch = json.loads(batch_path.read_text()) if batch_path.exists() else {}
            if (output / "tasks.json").exists():
                plan, saved_config = load_run(output)
                if saved_config.provider != config.provider:
                    raise ValueError(f"{output} uses {saved_config.provider}; use resume or choose a different --output")
                config = saved_config
                if Path(plan.package_root) != args.package.resolve():
                    raise ValueError(f"{output} belongs to {plan.package_root}; choose a different --output")
                if batch.get("episode_ids") != args.episodes:
                    raise ValueError(f"{output} has a different episode selection; choose a different --output")
            else:
                plan = compile_plan(args.package.resolve(), config, args.episodes)
                batch = {"episode_ids": args.episodes}
            if args.delivery:
                batch["delivery"] = str(args.delivery.resolve())
            output.mkdir(parents=True, exist_ok=True)
            batch_path.write_text(json.dumps(batch, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        report = asyncio.run(run(plan, config, output))
        if report["success"] and batch.get("delivery"):
            report["delivery"] = export_batch(
                Path(plan.package_root), Path(batch["delivery"]), batch["episode_ids"],
                [task.asset_id for task in plan.tasks],
            )
            (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["success"] else 1
    except KeyboardInterrupt:
        print("Interrupted. Saved images are retained; use imagepipe resume with the run directory.", file=sys.stderr)
        return 130
    except (OSError, ValueError, KeyError) as error:
        print(f"imagepipe: {error}", file=sys.stderr)
        return 1


def _load_config(path: Path | None, provider: str | None) -> ImageConfig:
    profiles = {"qwen": "imagepipe_qwen.yaml", "codex": "imagepipe_codex.yaml"}
    path = path or Path("configs") / profiles.get(provider, "imagepipe.yaml")
    config = ImageConfig.model_validate(yaml.safe_load(path.read_text()) or {})
    if provider and config.provider != provider:
        raise ValueError(f"{path} selects {config.provider}; choose a config for --provider {provider}")
    return config


if __name__ == "__main__":
    raise SystemExit(main())
