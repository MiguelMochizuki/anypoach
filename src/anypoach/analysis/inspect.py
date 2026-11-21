"""Video and image inspection, decoding in a single process."""
from __future__ import annotations

import math
import re
from collections.abc import Callable
from fractions import Fraction
from pathlib import Path

import av

from ..tempdirs import make_temp_dir
from .keyframes import choose_keyframes
from .motion import MotionTiming, approximate_timing, pixel_difference
from .palette import extract_palette
from .source import MAX_VIDEO_BYTES, VideoSource, read_still, scaled_png, scaled_rgb, seek_for_moment
from .types import DragFrame, DragFrames, InspectionResult, Keyframe

MAX_DURATION_SECONDS = 30
DEFAULT_SAMPLE_WIDTH = 96
DEFAULT_SAMPLES_PER_SECOND = 12
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp")
Progress = Callable[[str], None]


def _round(value: float) -> int:
    return math.floor(value + 0.5)  # round half up; Python's round() rounds half to even


def _clamp(value: float, low: int, high: int) -> int:
    return max(low, min(high, _round(value)))


def _safe_base(path: Path, fallback: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", path.stem)[:48] or fallback


def _output_dir(output_dir: str | Path | None) -> Path:
    if output_dir is None:
        return make_temp_dir("anypoach-")
    path = Path(output_dir).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def inspect_video(path: str | Path, *, output_dir: str | Path | None = None, sample_width: float = DEFAULT_SAMPLE_WIDTH,
                  samples_per_second: float = DEFAULT_SAMPLES_PER_SECOND, palette_size: int = 6,
                  on_progress: Progress | None = None) -> InspectionResult:
    """Analyze a video: keyframes, palette, and motion timing.

    Samples frames at `samples_per_second`, then keeps up to three of them as PNGs: where movement begins
    (`start`), the sample before the biggest change (`peak`), and the first calm sample after it
    (`settled`, or the last frame if it never calms down).

    Args:
        path: A `.mp4` or `.mov` file, at most 512 MiB and 30 s long.
        output_dir: Where the keyframe PNGs go; a private temporary folder when omitted.
        sample_width: Width in pixels of the downscaled frames used for analysis (clamped to 48-256).
        samples_per_second: Sampling rate (clamped to 2-24; never more than 720 samples in total).
        palette_size: Number of palette colors, 1 to 12.
        on_progress: Called with the stage name (`"motion"`, `"frames"`) as the analysis advances.

    Returns:
        The keyframes, palette, and estimated easing of the clip.

    Raises:
        ValueError: If the file is missing, unsupported, too large, too long, or has no readable frames.
    """
    progress = on_progress or (lambda _stage: None)
    with VideoSource(path) as source:
        duration = source.duration_s
        if duration > MAX_DURATION_SECONDS:
            raise ValueError(f"Video is longer than the {MAX_DURATION_SECONDS}-second limit")
        width = _clamp(sample_width, 48, 256)
        rate = _clamp(samples_per_second, 2, 24)
        count = max(2, min(720, math.ceil(duration * rate)))
        progress("motion")
        times_ms = [_round(max(0.0, min(duration - 0.001, i / (count - 1) * duration)) * 1000) for i in range(count)]
        seeks = [source.seek_for_moment(t / 1000) for t in times_ms]
        unique = sorted(set(seeks))  # a held frame is decoded once however many samples fall on it
        decoded = dict(zip(unique, source.frames_at(unique, width), strict=True))
        frames = [decoded[s] for s in seeks]
        deltas = [pixel_difference(frames[i], frames[i + 1]) for i in range(count - 1)]
        keys = choose_keyframes(deltas, count)
        progress("frames")
        out = _output_dir(output_dir)
        base = _safe_base(source.path, "capture")
        keyframes: list[Keyframe] = []
        for kind, index in keys:
            image = out / f"{base}-{kind}-{times_ms[index]}ms.png"
            image.write_bytes(source.png_at(seeks[index]))
            keyframes.append(Keyframe(kind, times_ms[index], str(image), 0 if index == 0 else deltas[index - 1]))
        motion_start = times_ms[keys[0][1]]
        settled = next((index for kind, index in keys if kind == "settled"), None)
        settled_ms = times_ms[settled] if settled is not None else _round(duration * 1000)
        duration_ms = 0 if len(keys) == 1 else max(0, settled_ms - motion_start)
        timing = approximate_timing(times_ms, deltas, motion_start, duration_ms)
        progress("palette")
        palette = extract_palette(frames[settled if settled is not None else count - 1], palette_size)
        return InspectionResult("video", str(source.path), duration_ms, keyframes, palette, timing)


def inspect_recording(path: str | Path, **options) -> InspectionResult:
    """Normalize recorder shutdown latency without relaxing the imported-video limit."""
    source_path = Path(path).resolve()
    if source_path.suffix.lower() not in (".mov", ".mp4"):
        raise ValueError("Recording must be an MP4 or MOV file")
    if not source_path.is_file() or source_path.stat().st_size > MAX_VIDEO_BYTES:
        raise ValueError("Recording exceeds the 512 MiB limit")
    with VideoSource(source_path) as source:
        duration = source.duration_s
    if duration <= MAX_DURATION_SECONDS:
        return inspect_video(source_path, **options)
    clipped = make_temp_dir("anypoach-recording-") / "recording.mp4"
    _clip(source_path, clipped, MAX_DURATION_SECONDS)
    return inspect_video(clipped, **options)


def _clip(source_path: Path, target: Path, seconds: int, fps: int = 30) -> None:
    """Re-encode the boundary (stream copy may keep packets past the limit), video only, constant frame rate."""
    with av.open(str(source_path)) as src, av.open(str(target), "w") as dst:
        in_stream = src.streams.video[0]
        out_stream = dst.add_stream("mpeg4", rate=fps, options={"qmin": "2", "qmax": "2"})  # -q:v 2
        out_stream.width, out_stream.height, out_stream.pix_fmt = in_stream.codec_context.width, in_stream.codec_context.height, "yuv420p"
        start = float(src.start_time or 0) / av.time_base
        decoded = ((float(f.pts * in_stream.time_base) - start, f) for f in src.decode(in_stream) if f.pts is not None)
        pending = next(decoded, None)
        current = None
        for tick in range(seconds * fps):
            at = tick / fps
            while pending is not None and pending[0] <= at + 0.5 / fps:  # nearest frame, like the fps filter
                current, pending = pending[1], next(decoded, None)
            if current is None:
                continue
            frame = current.reformat(format="yuv420p")  # stays in YUV: no lossy RGB round trip
            frame.pts, frame.time_base = tick, Fraction(1, fps)
            dst.mux(out_stream.encode(frame))
        dst.mux(out_stream.encode(None))


def inspect_image(path: str | Path, *, output_dir: str | Path | None = None, sample_width: float = DEFAULT_SAMPLE_WIDTH,
                  palette_size: int = 6, on_progress: Progress | None = None, **_ignored) -> InspectionResult:
    """Analyze a still image: its palette and a copy of it as the single keyframe.

    Args:
        path: A PNG, JPEG, WebP, TIFF, or BMP file, at most 512 MiB.
        output_dir: Where the keyframe PNG goes; a private temporary folder when omitted.
        sample_width: Width in pixels of the downscaled copy used for the palette (clamped to 48-256).
        palette_size: Number of palette colors, 1 to 12.
        on_progress: Called with the stage name as the analysis advances.

    Returns:
        An image result with one `start` keyframe and no measurable motion.

    Raises:
        ValueError: If the file is missing, unsupported, too large, or cannot be decoded.
    """
    progress = on_progress or (lambda _stage: None)
    source_path = Path(path).resolve()
    if source_path.suffix.lower() not in IMAGE_EXTENSIONS:
        raise ValueError("Supported still images are PNG, JPEG, WebP, TIFF, and BMP")
    if not source_path.is_file():
        raise ValueError("Image path must point to a file")
    if source_path.stat().st_size > MAX_VIDEO_BYTES:
        raise ValueError("Image file exceeds the 512 MiB limit")
    frame = read_still(source_path)
    sample = scaled_rgb(frame, _clamp(sample_width, 48, 256))
    progress("frames")
    out = _output_dir(output_dir)
    image = out / f"{_safe_base(source_path, 'image')}-image.png"
    image.write_bytes(scaled_png(frame, 1280))
    progress("palette")
    return InspectionResult("image", str(source_path), 0, [Keyframe("start", 0, str(image), 0)],
                            extract_palette(sample, palette_size),
                            MotionTiming(0, None, "Still image · no motion duration"))


def _probe_moment_source(path: str | Path) -> tuple[Path, float]:
    source_path = Path(path).resolve()
    if source_path.suffix.lower() not in (".mp4", ".mov"):
        raise ValueError("Expected an MP4 or MOV recording")
    if not source_path.is_file() or source_path.stat().st_size > MAX_VIDEO_BYTES:
        raise ValueError("Recording must be a file no larger than 512 MiB")
    with VideoSource(source_path) as source:
        if source.duration_s > MAX_DURATION_SECONDS:
            raise ValueError(f"Video is longer than the {MAX_DURATION_SECONDS}-second limit")
        return source_path, source.duration_s * 1000


def read_video_moment(path: str | Path, time_ms: float) -> bytes:
    """A precise visual reference from a bounded local recording."""
    if not math.isfinite(time_ms) or time_ms < 0:
        raise ValueError("Timestamp must be a nonnegative number of milliseconds")
    source_path, duration_ms = _probe_moment_source(path)
    if time_ms >= duration_ms:
        raise ValueError("Timestamp must be before the end of the recording")
    with VideoSource(source_path) as source:
        return source.png_at(source.seek_for_moment(time_ms / 1000))


def read_drag_release_frames(path: str | Path, release_ms: float, next_drag_ms: float | None = None) -> DragFrames:
    """A short sequence around a release, ending before the next recorded drag."""
    source_path, duration_ms = _probe_moment_source(path)
    end = min(30_000, math.ceil(duration_ms) - 1, (math.inf if next_drag_ms is None else next_drag_ms) - 1)
    if release_ms > end:
        return DragFrames(end, [])
    sample_times = dict.fromkeys(max(0, min(release_ms + offset, end)) for offset in (-80, 150, 800, 2_000, 4_000))
    sample_times[end] = None
    with VideoSource(source_path) as source:
        return DragFrames(end, [DragFrame(t, source.png_at(source.seek_for_moment(t / 1000), 768)) for t in sample_times])


__all__ = [
    "inspect_image",
    "inspect_recording",
    "inspect_video",
    "read_drag_release_frames",
    "read_video_moment",
    "seek_for_moment",
]
