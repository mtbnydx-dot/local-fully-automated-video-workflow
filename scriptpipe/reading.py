"""Prepare a bounded, paragraph-addressable source for long-form season planning."""

import asyncio
import json
import re
from bisect import bisect_right
from pathlib import Path

from .llm import write_json


CONTEXT_TOKENS = 1_000_000
READER_CHARACTERS = 200_000
READER_BYTES = 3 * READER_CHARACTERS
CHAPTER = re.compile(r"^\s*(?:#{1,6}\s*)?(?:第[零〇一二三四五六七八九十百千万两\d]+[章回节]|chapter\s+\w+)", re.I)


def _size(value):
    return len(json.dumps(value, ensure_ascii=False).encode("utf-8"))


def _batches(weights, chapter_starts, limit):
    """Prefer the last complete chapter that fits, then fall back to paragraphs."""
    start = 0
    while start < len(weights):
        end, used = start, 0
        while end < len(weights) and used + weights[end] <= limit:
            used += weights[end]
            end += 1
        if end == start:
            raise ValueError("A single reading item exceeds the source budget")
        if end < len(weights):
            boundary = bisect_right(chapter_starts, end) - 1
            if boundary >= 0 and chapter_starts[boundary] > start:
                end = chapter_starts[boundary]
        yield start, end
        start = end


def _source_index(path, out, paragraph_limit):
    text = re.sub(r"\.mw-parser-output[^{}]*\{[^{}]*\}", "", path.read_text(encoding="utf-8"))
    (out / "source.cleaned.txt").write_text(text, encoding="utf-8")
    paragraphs, starts = [], []
    for line in text.splitlines():
        if not line.strip():
            continue
        if CHAPTER.match(line):
            starts.append(len(paragraphs))
        for offset in range(0, len(line), paragraph_limit):
            paragraphs.append({"id": len(paragraphs) + 1, "text": line[offset:offset + paragraph_limit]})
    if not paragraphs:
        raise ValueError("Source contains no story paragraphs")
    if starts:
        starts[0] = 0  # Include any front matter with the first chapter.
    write_json(out / "source.paragraphs.json", paragraphs)
    return paragraphs, starts or [0]


async def prepare_source(path: Path, out: Path, client, prompt, planning_input: dict, *,
                         chapters, whole_book_season, context_tokens, max_tokens):
    """Return original numbered paragraphs and the selected season's P1 input."""
    directory = out / "reading"
    planner = prompt("long_season_plan_zh")
    reader = prompt("long_reader_zh")
    seasons = prompt("long_season_map_zh")
    # UTF-8 byte size conservatively bounds text tokens without a model-specific tokenizer.
    budget = (context_tokens - max_tokens - _size(planning_input) - 512
              - max(len(s.encode("utf-8")) for s in (planner, reader, seasons)))
    if budget < 256:
        raise ValueError("Increase --context-tokens or reduce --max-tokens to leave room for the source")
    paragraph_limit = (min(READER_BYTES, budget) - 64) // 6
    paragraphs, starts = _source_index(path, out, paragraph_limit)
    weights = [_size(p) + 2 for p in paragraphs]
    first, last = 0, len(paragraphs)
    if chapters:
        low, high = chapters
        if not 1 <= low <= high <= len(starts):
            raise ValueError(f"Chapter range must be within 1–{len(starts)}")
        first, last = starts[low - 1], (starts + [last])[high]
    elif whole_book_season is None:
        first, last = next(_batches(weights, starts, budget))

    async def read(name, payload):
        dest = directory / f"{name}.json"
        if dest.exists():
            return json.loads(dest.read_text(encoding="utf-8"))
        result = await client.complete(name, reader, payload)
        summary = result.get("material_map")
        if not isinstance(summary, str) or not summary.strip():
            raise ValueError(f"{name}: expected a nonempty material_map")
        write_json(dest, result)
        return result

    context = {}
    if whole_book_season is not None:
        season_path = directory / "seasons.json"
        if season_path.exists():
            season_map = json.loads(season_path.read_text(encoding="utf-8"))
        else:
            material = await _material(paragraphs, starts, weights, budget, read)
            season_map = await client.complete("seasons", seasons, {**planning_input, **material})
            _season_bounds(season_map, len(paragraphs))
            write_json(season_path, season_map)
        ends = [s["end_paragraph"] for s in season_map["seasons"]]
        if not 1 <= whole_book_season <= len(ends):
            raise ValueError(f"Choose a season within 1–{len(ends)}; see {directory / 'seasons.json'}")
        first, last = ([0] + ends)[whole_book_season - 1], ends[whole_book_season - 1]
        context = {"season_number": whole_book_season, "season_count": len(ends),
                   "season_logline": season_map["seasons"][whole_book_season - 1]["logline"]}
        budget -= _size(context)
    scope = {"source_range": [first + 1, last], **context}
    write_json(directory / "scope.json", scope)
    relative_starts = [index - first for index in starts if first <= index < last]
    material = await _material(paragraphs[first:last], relative_starts, weights[first:last], budget, read)
    return paragraphs, {"source_scope": scope, **material}


async def _material(paragraphs, starts, weights, budget, read):
    if sum(weights) <= budget:
        return {"source_paragraphs": paragraphs}

    async def merge(group):
        if len(group) == 1:
            return group[0]
        return await summarize(group, "source_maps", group[0]["source_range"][0], group[-1]["source_range"][1])

    async def summarize(items, field, first, last):
        result = await read(f"{field}_{first}_{last}", {field: items})
        return {"source_range": [first, last], "material_map": result["material_map"]}

    # Bound raw characters as well as serialized size when packing reader requests.
    reader_weights = [max(weight, 3 * len(p["text"])) for weight, p in zip(weights, paragraphs)]
    batches = _batches(reader_weights, starts, min(budget, READER_BYTES))
    maps = await asyncio.gather(*(summarize(paragraphs[a:b], "source_paragraphs", paragraphs[a]["id"],
                                            paragraphs[b - 1]["id"]) for a, b in batches))
    while _size(maps) > budget:
        groups = list(_batches([_size(m) + 2 for m in maps], [], budget))
        if len(groups) == len(maps):
            raise ValueError("Reading summaries exceed the planning budget; increase --context-tokens")
        maps = await asyncio.gather(*(merge(maps[a:b]) for a, b in groups))
    return {"source_maps": maps}


def _season_bounds(result, last):
    ends = [season["end_paragraph"] for season in result["seasons"]]
    if (not ends or ends[-1] != last or any(type(end) is not int or start >= end
                                            for start, end in zip([0] + ends, ends))
            or any(not isinstance(s.get("logline"), str) for s in result["seasons"])):
        raise ValueError("Expected ordered season endpoints covering the book and a logline for each season")
