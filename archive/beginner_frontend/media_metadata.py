"""Read container metadata with ffprobe; no frame decoding or GPU access."""
import json
import math
import subprocess
from fractions import Fraction


def parse_video_metadata(payload):
    stream = next((item for item in payload.get("streams", []) if item.get("codec_type") == "video"), {})
    width, height = int(stream.get("width") or 0), int(stream.get("height") or 0)
    if width <= 0 or height <= 0:
        return {}
    result = {"width": width, "height": height}
    for key in ("avg_frame_rate", "r_frame_rate"):
        try:
            fps = float(Fraction(str(stream.get(key) or "0")))
            if 0 < fps <= 1000 and math.isfinite(fps):
                result["fps"] = fps
                break
        except (ValueError, ZeroDivisionError):
            pass
    return result


def read_video_metadata(source, probe, popen_options=None):
    if not probe:
        return {}
    try:
        result = subprocess.run(
            [str(probe), "-v", "error", "-protocol_whitelist", "file,pipe",
             "-show_entries", "stream=codec_type,width,height,avg_frame_rate,r_frame_rate",
             "-of", "json", str(source)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10,
            **(popen_options or {}),
        )
        return parse_video_metadata(json.loads(result.stdout)) if result.returncode == 0 else {}
    except (OSError, subprocess.SubprocessError, ValueError, TypeError):
        return {}
