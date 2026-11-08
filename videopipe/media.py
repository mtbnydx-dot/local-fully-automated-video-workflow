import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

import imageio_ffmpeg

from .models import MediaConfig


@dataclass(frozen=True)
class MediaInfo:
    duration: float
    width: int
    height: int
    fps: float
    has_audio: bool


def run_ffmpeg(arguments: list[str]) -> subprocess.CompletedProcess:
    command = [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-nostdin", "-y", *arguments]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f"FFmpeg failed:\n{result.stderr[-6000:]}")
    return result


def inspect_video(path: Path) -> MediaInfo:
    result = run_ffmpeg(["-i", str(path), "-map", "0:v:0", "-frames:v", "1", "-f", "null", "-"])
    # FFmpeg reports input metadata before its Output section; no ffprobe binary is needed.
    metadata = result.stderr.split("Output #", 1)[0]
    video = next(line for line in metadata.splitlines() if "Video:" in line)
    duration = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", metadata)
    dimensions = re.search(r", (\d+)x(\d+)\b", video)
    rate = re.search(r"([\d.]+) (?:fps|tbr)\b", video)
    if not duration or not dimensions or not rate:
        raise ValueError(f"Cannot read video duration, dimensions or frame rate: {path}")
    hours, minutes, seconds = map(float, duration.groups())
    return MediaInfo(
        duration=hours * 3600 + minutes * 60 + seconds,
        width=int(dimensions[1]),
        height=int(dimensions[2]),
        fps=float(rate[1]),
        has_audio="Audio:" in metadata,
    )


def sample_frames(video: Path, output_dir: Path, count: int = 8, max_size: int = 640) -> list[Path]:
    """Sample each equal-duration interval at its midpoint, in chronological order."""
    info = inspect_video(video)
    output_dir.mkdir(parents=True, exist_ok=True)
    scale = min(1, max_size / max(info.width, info.height))
    size = f"{max(1, round(info.width * scale))}:{max(1, round(info.height * scale))}"
    frames = []
    for index in range(count):
        timestamp = info.duration * (index + 0.5) / count
        target = output_dir / f"frame-{index:03d}-{timestamp:.3f}s.jpg"
        run_ffmpeg([
            "-loglevel", "error", "-i", str(video), "-ss", f"{timestamp:.6f}",
            "-frames:v", "1", "-vf", f"tpad=stop_mode=clone:stop_duration=1,scale={size}",
            "-q:v", "2", str(target),
        ])
        frames.append(target)
    return frames


def normalize_clip(source: Path, target: Path, *, duration: float | None = None, config: MediaConfig) -> Path:
    """Normalize a selected clip, retaining its measured duration unless an explicit trim is requested."""
    info = inspect_video(source)
    duration = info.duration if duration is None else duration
    target.parent.mkdir(parents=True, exist_ok=True)
    inputs = ["-i", str(source)]
    if not info.has_audio:
        inputs += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
    video_filter = (
        f"scale={config.width}:{config.height}:force_original_aspect_ratio=decrease,"
        f"pad={config.width}:{config.height}:(ow-iw)/2:(oh-ih)/2,setsar=1,"
        f"fps={config.fps},tpad=stop_mode=clone:stop_duration={duration},"
        f"trim=duration={duration},setpts=PTS-STARTPTS"
    )
    run_ffmpeg([
        "-loglevel", "error", *inputs, "-map", "0:v:0", "-map", "0:a:0" if info.has_audio else "1:a:0",
        "-vf", video_filter, "-af", f"aresample=48000,apad,atrim=duration={duration},asetpts=PTS-STARTPTS",
        "-t", str(duration), "-c:v", "libx264", "-preset", "fast", "-crf", str(config.crf),
        "-pix_fmt", "yuv420p", "-r", str(config.fps), "-threads", "2", "-c:a", "aac", "-ac", "2", "-ar", "48000",
        "-movflags", "+faststart", str(target),
    ])
    return target


def assemble(clips: list[Path], target: Path, config: MediaConfig) -> Path:
    """Join clips already normalized to the common production format."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="videopipe-concat-") as temporary:
        manifest = Path(temporary) / "clips.txt"
        manifest.write_text("".join("file '" + str(clip.resolve()).replace("'", "'\\''") + "'\n" for clip in clips))
        run_ffmpeg([
            "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(manifest),
            "-map", "0:v:0", "-map", "0:a:0", "-c", "copy", "-movflags", "+faststart", str(target),
        ])
    return target


def finalize(source: Path, target: Path, config: MediaConfig, *, subtitles: Path | None = None,
             fonts: Path | None = None) -> Path:
    """Encode the delivery on the CPU, optionally burning an ASS subtitle file rendered with fonts from a directory."""
    target.parent.mkdir(parents=True, exist_ok=True)
    filters = []
    if config.upscale == "lanczos":
        filters.append(f"scale=iw*{config.upscale_factor}:ih*{config.upscale_factor}:flags=lanczos")
    if subtitles is not None:
        filters.append(f"ass={_filter_path(subtitles)}:fontsdir={_filter_path(fonts)}")
    # A ComfyUI upscale is performed before this encoding step by production control.
    run_ffmpeg([
        "-loglevel", "error", "-i", str(source), "-map", "0:v:0", "-map", "0:a:0?",
        *(["-vf", ",".join(filters)] if filters else []),
        "-c:v", "libx264", "-preset", "fast", "-crf", str(config.crf), "-pix_fmt", "yuv420p",
        "-r", str(config.fps), "-threads", str(config.finalize_threads), "-c:a", "aac", "-movflags", "+faststart",
        str(target),
    ])
    return target


def _filter_path(path: Path) -> str:
    # Filter arguments are unescaped twice: the quotes keep spaces and the escaped colon keeps a drive letter.
    return "'" + path.resolve().as_posix().replace(":", "\\:") + "'"
