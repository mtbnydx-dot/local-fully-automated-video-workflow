"""Always deliver script subtitles, refining their timing with usable ASR."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from itertools import count, groupby
import re
import struct
import unicodedata

from PIL import ImageFont

from videopipe.models import Shot, SubtitleConfig
from videopipe.records import write_json


_WIDE = "\u2e80-\u9fff\uac00-\ud7af\uf900-\ufaff\ufe30-\ufe4f\uff00-\uffef"
_OPENING = "“‘（《「『【〈〔〖［｛"
_CLOSING = "”’，。、；：？！…—）》」』】〉〕〗］｝"
# Lines break between these units: a word, or one wide character together with the punctuation that
# must stay beside it (no closing mark starts a line, no opening mark ends one), plus a following space.
_ATOM = re.compile(f"[{_OPENING}]*(?:[^\\s{_WIDE}]+|[{_WIDE}])[{_CLOSING}]* ?")
_PHRASE = re.compile(f".+?(?:[{_CLOSING}]+|[,.!?;:]+(?= |$)|$) *")
_SRT_CUE = re.compile(r"^(\S+) --> (\S+)\n(.*?)(?=\n\n|\n?\Z)", re.MULTILINE | re.DOTALL)
# WrapStyle 2 keeps the lines laid out here; libass itself only wraps at spaces.
_ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{family},{size:.1f},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,{weight},0,0,0,100,100,0,0,1,{outline:.1f},{shadow:.1f},2,{margin},{margin},{bottom},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


@dataclass(frozen=True)
class SubtitleFont:
    family: str
    weight: int
    line_height: float  # libass font size per em
    face: ImageFont.FreeTypeFont  # 1000 px per em, for measuring advances


def extract_dialogue(shots: list[Shot]) -> list[dict]:
    """Read dialogue only; never infer spoken words from scene descriptions."""
    dialogue = []
    offset = 0.0
    for shot in shots:
        for index, match in enumerate(re.finditer(r"<d>(.*?)</d>", shot.prompt, re.DOTALL), start=1):
            content = match.group(1).strip()
            language_match = re.match(r"^\[([^\]]+)\]\s*", content)
            language = language_match.group(1) if language_match else None
            text = content[language_match.end():] if language_match else content
            # These H3 continuity markers are instructions, not spoken words.
            text = re.sub(r"</?(?:scenetrans|cutoff)>", "", text).strip()
            if text:
                dialogue.append({"shot_id": shot.id, "dialogue_index": index,
                                 "language": language, "text": text,
                                 "shot_start": offset, "shot_end": offset + shot.duration})
        offset += shot.duration
    return dialogue


def create_subtitles(shots: list[Shot], transcript: dict, output_dir: Path) -> dict:
    """ASR supplies timing, not permission to include a scripted line."""
    dialogue = extract_dialogue(shots)
    units = _timestamped_units(transcript.get("segments", [])) if transcript.get("status") == "complete" else []
    lines = []
    for _, group in groupby(dialogue, key=lambda line: line["shot_id"]):
        lines.extend(_time_shot(list(group), units))
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "episode.srt"
    cues = [f"{index}\n{_srt_time(line['start'])} --> {_srt_time(line['end'])}\n{line['text']}\n"
            for index, line in enumerate(lines, start=1)]
    path.write_text("\n".join(cues), encoding="utf-8")
    matched = [line for line in lines if line["timing"] == "asr"]
    fallback = [line for line in lines if line["timing"] == "script"]
    result = {"status": "complete" if lines else "no_dialogue", "path": str(path),
              "timing": ("mixed" if matched else "script") if fallback else ("asr" if matched else "none"),
              "matched": matched, "fallback": fallback}
    write_json(output_dir / "subtitles.json", result)
    return result


def subtitle_font(config: SubtitleConfig) -> SubtitleFont:
    """Select the configured face; a collection file holds one face per family."""
    for index in count():
        try:
            face = ImageFont.truetype(str(config.font_file), 1000, index=index)
        except OSError:
            raise ValueError(f"{config.font_file} has no font family {config.font!r}") from None
        if config.font in (None, face.getname()[0]):
            line_height, weight = _libass_metrics(config.font_file, index)
            return SubtitleFont(face.getname()[0], weight, line_height, face)


def write_ass(srt: Path, target: Path, config: SubtitleConfig, width: int, height: int) -> Path:
    """Lay SRT cues out for burning: large, centred, inside the lower third, at most max_lines lines each."""
    font = subtitle_font(config)
    em = config.size * height
    margin = round(width * 0.1)
    events = []
    for start, end, text in _read_srt(srt):
        cues = _wrap(text, lambda line: font.face.getlength(line) * em / 1000, width - 2 * margin, config.max_lines)
        weights = [len("".join(lines).replace(" ", "")) for lines in cues]
        elapsed = 0
        for lines, weight in zip(cues, weights):
            cue_start = start + (end - start) * elapsed / sum(weights)
            elapsed += weight
            cue_end = start + (end - start) * elapsed / sum(weights)
            body = r"\N".join(lines)
            events.append(f"Dialogue: 0,{_ass_time(cue_start)},{_ass_time(cue_end)},Default,,0,0,0,,{body}\n")
    size = em * font.line_height
    # Lines stack upward from the bottom margin; a full max_lines block reaches the top of the lower third.
    header = _ASS_HEADER.format(width=width, height=height, family=font.family, size=size, weight=font.weight,
                                outline=em * 0.08, shadow=em * 0.03, margin=margin,
                                bottom=round(height / 3 - config.max_lines * size))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(header + "".join(events), encoding="utf-8")
    return target


def _time_shot(lines: list[dict], units: list[dict]) -> list[dict]:
    timed, cursor = [], lines[0]["shot_start"]
    for line in lines:
        match = _find_match(line, units, cursor)
        if match:
            start, end = match
            timed.append({**line, "start": start, "end": end, "timing": "asr"})
            cursor = end
        else:
            timed.append(dict(line))
    anchors = [-1, *(i for i, line in enumerate(timed) if "start" in line), len(timed)]
    for left, right in zip(anchors, anchors[1:]):
        if right == left + 1:
            continue
        start = timed[left]["end"] if left >= 0 else lines[0]["shot_start"]
        end = timed[right]["start"] if right < len(timed) else lines[-1]["shot_end"]
        if end - start < 0.001 * (right - left - 1):
            # If an observed line fills the shot, use one coherent coarse timeline.
            return _script_times(lines, lines[0]["shot_start"], lines[-1]["shot_end"])
        timed[left + 1:right] = _script_times(lines[left + 1:right], start, end)
    return timed


def _script_times(lines: list[dict], start: float, end: float) -> list[dict]:
    weights = [max(1, len(_normalized(line["text"]))) for line in lines]
    total, elapsed, timed = sum(weights), 0, []
    for line, weight in zip(lines, weights):
        timed.append({**line, "start": start + (end - start) * elapsed / total,
                      "end": start + (end - start) * (elapsed + weight) / total, "timing": "script"})
        elapsed += weight
    return timed


def _normalized(text: str) -> tuple[str, ...]:
    text = unicodedata.normalize("NFKC", text).casefold()
    # Chinese ASR word boundaries vary; compare ideographs individually while
    # preserving word boundaries in alphabetic languages ("a part" != "apart").
    cjk = "\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
    return tuple(re.findall(f"[{cjk}]|[^\\W_{cjk}]+", text))


def _timestamped_units(segments: list[dict]) -> list[dict]:
    # ASR validates text and timestamp fields once at its subprocess boundary.
    units = []
    for segment in segments:
        items = segment.get("words") or [segment]
        for item in items:
            text = item.get("word", item.get("text", ""))
            normalized = _normalized(text)
            if not normalized:
                continue
            units.append({"start": item["start"], "end": item["end"],
                          "text": normalized})
    return sorted(units, key=lambda item: (item["start"], item["end"]))


def _find_match(line: dict, units: list[dict], cursor: float) -> tuple[float, float] | None:
    target = _normalized(line["text"])
    if not target or re.search(r"\n\s*\n", line["text"]):
        return None
    eligible = [item for item in units if item["end"] > max(line["shot_start"], cursor)
                and item["start"] < line["shot_end"]]
    for index, first in enumerate(eligible):
        combined = ()
        previous_end = first["start"]
        for item in eligible[index:]:
            if item["start"] < previous_end:
                break
            combined += item["text"]
            previous_end = item["end"]
            if combined == target:
                return max(first["start"], line["shot_start"], cursor), min(item["end"], line["shot_end"])
            if target[:len(combined)] != combined:
                break
    return None


def _srt_time(seconds: float) -> str:
    milliseconds = round(seconds * 1000)
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    seconds, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"


def _read_srt(path: Path) -> list[tuple[float, float, str]]:
    return [(_srt_seconds(start), _srt_seconds(end), text)
            for start, end, text in _SRT_CUE.findall(path.read_text(encoding="utf-8"))]


def _srt_seconds(stamp: str) -> float:
    hours, minutes, seconds = stamp.replace(",", ".").split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def _ass_time(seconds: float) -> str:
    centiseconds = round(seconds * 100)
    return f"{centiseconds // 360000}:{centiseconds // 6000 % 60:02}:{centiseconds // 100 % 60:02}.{centiseconds % 100:02}"


def _wrap(text: str, measure, width: float, max_lines: int) -> list[list[str]]:
    """Pack whole phrases into cues of at most max_lines lines; split a phrase only when it alone is longer."""
    cues, current = [], ""
    for phrase in _PHRASE.findall(" ".join(text.split())):
        if current and len(_lines(current + phrase, measure, width)) > max_lines:
            cues.append(current)
            current = ""
        current += phrase
    cues.append(current)
    groups = []
    for cue in cues:
        lines = _lines(cue, measure, width)
        parts, start = -(-len(lines) // max_lines), 0
        for index in range(parts):
            size = len(lines) // parts + (index < len(lines) % parts)
            groups.append(lines[start:start + size])
            start += size
    return groups


def _lines(text: str, measure, width: float) -> list[str]:
    """Use the fewest lines, then keep them even and break after punctuation."""
    atoms = _ATOM.findall(text)
    # best[end] = (line count, cost, start of the last line) for the first `end` atoms.
    best = [(0, 0.0, 0)] + [None] * len(atoms)
    for end in range(1, len(atoms) + 1):
        for start in range(end - 1, -1, -1):
            line = "".join(atoms[start:end]).rstrip()
            used = measure(line)
            if used > width and end - start > 1:
                break
            pause = end == len(atoms) or atoms[end - 1].endswith(" ") or line[-1] in _CLOSING
            # Uneven lines cost the squared slack; a break inside a phrase costs as much as 40% of a line.
            cost = best[start][1] + (width - used) ** 2 + (0 if pause else (0.4 * width) ** 2)
            if best[end] is None or (best[start][0] + 1, cost) < best[end][:2]:
                best[end] = (best[start][0] + 1, cost, start)
    lines, end = [], len(atoms)
    while end:
        lines.insert(0, "".join(atoms[best[end][2]:end]).rstrip())
        end = best[end][2]
    return lines


def _libass_metrics(path: Path, index: int) -> tuple[float, int]:
    """libass sizes text by the OS/2 Windows ascent plus descent rather than the em; Pillow reads hhea."""
    data = path.read_bytes()
    base = struct.unpack_from(">I", data, 12 + 4 * index)[0] if data[:4] == b"ttcf" else 0
    entries = struct.unpack_from(">H", data, base + 4)[0]
    tables = {tag: offset for tag, _, offset, _ in struct.iter_unpack(">4sIII", data[base + 12:base + 12 + 16 * entries])}
    units_per_em = struct.unpack_from(">H", data, tables[b"head"] + 18)[0]
    weight = struct.unpack_from(">H", data, tables[b"OS/2"] + 4)[0]
    ascent, descent = struct.unpack_from(">HH", data, tables[b"OS/2"] + 74)
    return (ascent + descent) / units_per_em, weight
