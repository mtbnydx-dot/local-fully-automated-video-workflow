from __future__ import annotations

import argparse
import asyncio
import json
import math
from pathlib import Path

from .llm import DEFAULT_CONCURRENCY, DEFAULT_ENDPOINT, DEFAULT_KEY_NAME, DEFAULT_MAX_TOKENS, DEFAULT_MODEL, GLMClient, load_key
from .long_pipeline import run_long


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate drama packages using an Ark language model")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--env", type=Path, default=Path(".env"))
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--key-name", help="Default: DEEPSEEK-KEY; GLMKEY for glm models")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--episodes", type=int, default=8, help="Number of episodes (default: 8)")
    parser.add_argument("--long-form", "--long", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--long-review", choices=("off", "report"), default="off",
                        help="Long-form: optional one-pass LLM reports, without automatic rewriting (default: off)")
    parser.add_argument("--episode-minutes", type=float, default=5,
                        help="Long-form runtime target per episode; scene/shot counts follow the story (default: 5)")
    parser.add_argument("--delivery", type=Path, help="Long-form handoff directory, e.g. /data/season")
    parser.add_argument("--stop-after", choices=("season", "openings", "plans", "drafts", "review"), help="Save the selected long-form stage and exit")
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY,
                        help=f"Maximum simultaneous model requests (default: {DEFAULT_CONCURRENCY})")
    parser.add_argument("--reasoning-effort", choices=("low", "high", "max"), default="high")
    parser.add_argument("--review-reasoning-effort", choices=("low", "high", "max"),
                        help="Defaults to --reasoning-effort")
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS,
                        help=f"Per-call budget shared by thinking and final output (default: {DEFAULT_MAX_TOKENS})")
    parser.add_argument("--production-config", type=Path)
    parser.add_argument("--notes", type=Path, help="Optional source-specific editorial notes")
    args = parser.parse_args()
    if args.episodes < 1 or args.concurrency < 1:
        parser.error("episodes/concurrency must be positive")
    if not math.isfinite(args.episode_minutes) or args.episode_minutes <= 0 or args.max_tokens < 1:
        parser.error("episode-minutes must be finite and positive; max-tokens must be positive")
    key_name = args.key_name or ("GLMKEY" if args.model.startswith("glm") else DEFAULT_KEY_NAME)

    async def execute() -> None:
        client = GLMClient(load_key(args.env, key_name), args.output / "api", args.endpoint,
                           args.model, args.concurrency, args.reasoning_effort,
                           max_tokens=args.max_tokens)
        try:
            result = await run_long(
                args.source, args.output, client, episode_count=args.episodes, episode_minutes=args.episode_minutes,
                production_config=args.production_config, notes_path=args.notes, delivery=args.delivery,
                stop_after=args.stop_after, review_reasoning_effort=args.review_reasoning_effort,
                long_review=args.long_review,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
        finally:
            await client.close()

    asyncio.run(execute())
