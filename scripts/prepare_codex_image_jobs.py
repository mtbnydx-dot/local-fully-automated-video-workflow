"""Prepare fixed, sequential Codex image workers from an imagepipe handoff."""

import argparse
import json
import shlex
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("handoff", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--episodes", nargs="+")
    parser.add_argument("--jobs-per-worker", type=int, default=5, choices=range(1, 6))
    parser.add_argument("--model", default="gpt-6.1-sol")
    parser.add_argument("--effort", default="high")
    args = parser.parse_args()
    repository = Path(__file__).resolve().parents[1]
    handoff = json.loads(args.handoff.read_text())
    run_dir = Path(handoff["run_dir"]).resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    index_path = output / "jobs.json"
    index = json.loads(index_path.read_text()) if index_path.exists() else {
        "run_dir": str(run_dir), "workers": [], "assignments": {},
    }
    pending = _unassigned_requests(handoff, run_dir, set(index["assignments"]), args.episodes)
    new_workers = []
    for start in range(0, len(pending), args.jobs_per_worker):
        worker_id = f"worker_{len(index['workers']) + 1:02d}"
        directory = output / worker_id
        directory.mkdir()
        jobs = pending[start:start + args.jobs_per_worker]
        manifest = {
            "worker_id": worker_id,
            "run_dir": str(run_dir),
            "repository": str(repository),
            "model": args.model,
            "reasoning_effort": args.effort,
            "quality_requested": "high",
            "observed_image_tool": "image_gen.imagegen",
            "observed_quality_parameter_available": False,
            "quality_note": "The observed native image_gen.imagegen schema has no quality parameter. Inspect the worker's native tool schema; pass quality=high only if that field is actually exposed, and record the result.",
            "jobs": jobs,
        }
        (directory / "jobs.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        (directory / "prompt.md").write_text(_worker_prompt(directory, repository, run_dir))
        command = _worker_command(directory, repository, args.model, args.effort)
        command_path = directory / "command.sh"
        command_path.write_text(command)
        command_path.chmod(0o755)
        worker = {
            "worker_id": worker_id,
            "asset_ids": [job["asset_id"] for job in jobs],
            "jobs_path": str(directory / "jobs.json"),
            "prompt_path": str(directory / "prompt.md"),
            "command_path": str(command_path),
        }
        index["workers"].append(worker)
        index["assignments"].update({job["asset_id"]: worker_id for job in jobs})
        new_workers.append(worker)
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"index": str(index_path), "new_workers": new_workers}, ensure_ascii=False, indent=2))


def _unassigned_requests(handoff: dict, run_dir: Path, assigned: set[str], episodes: list[str] | None) -> list[dict]:
    requests = []
    for asset_id in handoff["remaining_asset_ids"]:
        if asset_id in assigned or (episodes and asset_id.split("-")[2] not in episodes):
            continue
        path = run_dir / "requests" / f"{asset_id}.json"
        request = json.loads(path.read_text())
        response_path = run_dir / "responses" / path.name
        if response_path.exists() or Path(request["target_path"]).is_file():
            continue
        requests.append({**request, "request_path": str(path), "response_path": str(response_path)})
        assigned.add(asset_id)
    return requests


def _worker_command(directory: Path, repository: Path, model: str, effort: str) -> str:
    arguments = [
        "codex", "exec", "--model", model, "--enable", "image_generation",
        "-c", f'model_reasoning_effort="{effort}"',
        "-c", 'approval_policy="never"',
        "--sandbox", "danger-full-access", "--cd", str(repository),
        "--json", "-o", str(directory / "result.md"), "-",
    ]
    return (
        "#!/usr/bin/env bash\nset -euo pipefail\nexec " + shlex.join(arguments)
        + " < " + shlex.quote(str(directory / "prompt.md"))
        + " > " + shlex.quote(str(directory / "events.jsonl"))
        + " 2> " + shlex.quote(str(directory / "stderr.log")) + "\n"
    )


def _worker_prompt(directory: Path, repository: Path, run_dir: Path) -> str:
    accept = shlex.join([str(repository / ".venv/bin/imagepipe"), "accept", str(run_dir)])
    return f"""执行当前 worker 的固定图片任务，按顺序完成后退出。

任务文件：{directory / 'jobs.json'}
运行状态文件：{directory / 'worker_status.json'}
Python 调用统一使用仓库解释器：{repository / '.venv/bin/python'}。需要读取 JSON、复制文件或写入运行状态时也使用该绝对路径。
跨 functions.exec 保存内容时，store() 中仅保存 JSON 可序列化的数据；函数对象保留为当前 cell 内的局部变量。

用户已授权原生 ChatGPT/Codex 生图。生图上下文由 imagepipe 提供。本进程每次仅一张图片在途，任务范围仅为 jobs.json 的 jobs，最多五张。保持当前任务清单，不派生代理、CLI 或其他生图进程。

流程：
1. 读取 jobs.json，检查当前原生 imagegen/ChatGPT 生图工具的实际 schema。记录 quality_requested=high 和 quality_parameter_available。若原生工具暴露 quality 字段，调用时设为 high；若没有该字段，记录 quality_parameter_available=false，保留工具默认值，不添加未知参数。若本会话没有原生生图工具，立即记录 tool_unavailable 并退出。
2. 按清单顺序处理。每张发起前检查 target_path 或 response_path，任一已存在就记录 skipped_completed 并继续。仅处理当前 assignment 内的未完成资产。
3. 每张使用 jobs.json 中系统生成的完整 tool_args。prompt、全部 referenced_image_paths、transparent_background 等原值逐项传递。除实际 schema 支持的 quality=high 外，保持 tool_args 原样，不改写提示词、不删参考图、不自行拼图。request_path 保留了系统来源。
4. 使用 view_image 先查看本张本地参考图，当前进程里已查看过的相同路径可复用；每次查看一至两张，避免图像输出超过 IPC 大小限制。查看用于读取输入上下文。
5. 调用一次原生 imagegen/ChatGPT 生图工具，并等待它完成，再处理下一张。仅使用该原生能力；HTTP API、SDK、curl、浏览器生图和其他 API 生图命令均不在本任务范围。若通过 functions 执行原生工具，遵循其 yield 和 generatedImage 返回要求，日志仅输出简短元数据，保留 base64 在工具结果中。
6. 成功后取得工具返回的本地原图路径，原图保持完整。调用现有系统回填：
   {accept} ASSET_ID /absolute/generated-image.png
   由 imagepipe 管理复制、原图保留、项目资源及元数据。接收成功后把 asset_id、generated_path、status=accepted、实际 quality 能力写入 worker_status.json，再继续下一张。
7. 每张只发起一次生图调用。遇到运行错误，保存已生成图片及错误细节，记录当前 asset_id 和尚未开始的任务，停止发起新图并退出。已存在的图片和接收回执用于续跑跳过。

本任务仅执行并记录运行状态；零审美评审、零成品质量打分、零创意改写、零基于观感的重试。无需查看或评价生成结果，也不修改项目脚本、notes、原始 request 或产品元数据。

完成后简短报告 accepted、skipped、failed 数量，给出 worker_status.json 路径；有错误时附准确错误信息。现在开始执行。
"""


if __name__ == "__main__":
    main()
