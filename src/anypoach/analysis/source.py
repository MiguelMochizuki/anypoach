"""Decode a short MP4/MOV with presentation-time seeking (single process, no ffmpeg CLI)."""
from __future__ import annotations

import bisect
from collections.abc import Callable, Sequence
from fractions import Fraction
from pathlib import Path
from typing import Self, TypeVar

import av
import numpy as np

IMAGE_MAX_SIZE = 1280
MAX_VIDEO_BYTES = 512 * 1024 * 1024
T = TypeVar("T")


def seek_for_moment(times: Sequence[float], seconds: float) -> float:
    """Seek point that makes a decoder land on the frame held on screen at `seconds`.

    ScreenCaptureKit may store one frame for several seconds of unchanged pixels, so
    resolve the frame already shown, then aim between its PTS and its predecessor's.
    """
    low = bisect.bisect_right(times, seconds)
    return 0.0 if low < 2 else max(0.0, (times[low - 1] + times[low - 2]) / 2)


def encode_png(rgb: np.ndarray) -> bytes:
    """Encode an RGB uint8 array of shape `(height, width, 3)` as PNG bytes."""
    frame = av.VideoFrame.from_ndarray(np.ascontiguousarray(rgb), format="rgb24")
    codec = av.CodecContext.create("png", "w")
    codec.width, codec.height, codec.pix_fmt = frame.width, frame.height, "rgb24"
    codec.time_base = Fraction(1, 1)
    return b"".join(bytes(p) for p in [*codec.encode(frame), *codec.encode(None)])


def scaled_rgb(frame: av.VideoFrame, width: int) -> np.ndarray:
    """RGB uint8 scaled with the area filter to `width`, height kept even like `scale=W:-2`."""
    height = max(2, round(frame.height * width / frame.width / 2) * 2)
    return frame.reformat(width=width, height=height, format="rgb24", interpolation="AREA").to_ndarray()


def scaled_png(frame: av.VideoFrame, max_size: int) -> bytes:
    """PNG that fits inside a max_size box, never enlarging (like force_original_aspect_ratio=decrease)."""
    ratio = min(1.0, max_size / frame.width, max_size / frame.height)
    w, h = max(1, round(frame.width * ratio)), max(1, round(frame.height * ratio))
    return encode_png(frame.reformat(width=w, height=h, format="rgb24", interpolation="BICUBIC").to_ndarray())


def cropped_png(frame: av.VideoFrame, max_size: int, crop: tuple[int, int, int, int]) -> bytes:
    """PNG of a rectangle of the native frame, reduced afterwards to fit `max_size` if it is larger.

    Args:
        frame: The decoded frame at its native size.
        max_size: Longest allowed side of the result in pixels.
        crop: `(x, y, width, height)` in native pixels.

    Raises:
        ValueError: If the rectangle is empty or reaches outside the frame.
    """
    x, y, width, height = crop
    if x < 0 or y < 0 or width < 1 or height < 1 or x + width > frame.width or y + height > frame.height:
        raise ValueError(f"Crop must fit inside the {frame.width}x{frame.height} frame")
    rgb = frame.reformat(format="rgb24").to_ndarray()[y:y + height, x:x + width]
    return scaled_png(av.VideoFrame.from_ndarray(np.ascontiguousarray(rgb), format="rgb24"), max_size)


def read_still(path: str | Path) -> av.VideoFrame:
    """Decode the first frame of a still image file.

    Raises:
        ValueError: If the file has no decodable pixels.
    """
    with av.open(str(path)) as container:
        for frame in container.decode(video=0):
            return frame
    raise ValueError("Image has no decodable pixel dimensions")


class VideoSource:
    """A video file opened for sampling frames by presentation time.

    Decoding happens in this process, so a whole analysis is one pass instead of one external process per
    sample. Use it as a context manager so the file is closed even when analysis fails.

    Attributes:
        path: Resolved path of the file.
        duration_s: Container duration in seconds (always positive).
        closed: Whether `close()` has been called.

    Raises:
        ValueError: On construction, if the file is missing, not `.mp4`/`.mov`, over 512 MiB, or has no video stream or duration.
    """
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).resolve()
        if self.path.suffix.lower() not in (".mp4", ".mov"):
            raise ValueError("Only .mp4 and .mov video files are supported")
        if not self.path.is_file():
            raise ValueError("Video path must point to a file")
        if self.path.stat().st_size > MAX_VIDEO_BYTES:
            raise ValueError("Video file exceeds the 512 MiB limit")
        self.closed = False
        self._container = av.open(str(self.path))
        try:
            self._stream = self._container.streams.video[0]
        except IndexError:
            self.close()
            raise ValueError("File has no video stream") from None
        self._start = (self._container.start_time or 0) / av.time_base
        self.duration_s = (self._container.duration or 0) / av.time_base
        if not self.duration_s > 0:
            self.close()
            raise ValueError("Video has no valid duration")
        self._times: list[float] | None = None

    @property
    def size(self) -> tuple[int, int]:
        """Native `(width, height)` of the video frames in pixels."""
        context = self._stream.codec_context
        return context.width, context.height

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the file. Safe to call more than once."""
        if not self.closed:
            self._container.close()
            self.closed = True

    @property
    def presentation_times(self) -> list[float]:
        """Presentation time of every stored frame in seconds, sorted and starting near zero.

        Read once from the container's packets and cached. A frame held for several seconds appears once.

        Raises:
            ValueError: If the video has no timestamped frames.
        """
        if self._times is None:
            base = self._stream.time_base
            self._container.seek(0)
            found = {float(p.pts * base) - self._start for p in self._container.demux(self._stream) if p.pts is not None}
            if not found:
                raise ValueError("Recording has no timestamped video frames")
            self._times = sorted(found)
        return self._times

    def seek_for_moment(self, seconds: float) -> float:
        """Return the time to seek to so the frame on screen at `seconds` is the one decoded.

        Args:
            seconds: Moment in the recording, relative to its first frame.

        Returns:
            A time between the shown frame's timestamp and its predecessor's, or 0 near the start.
        """
        return seek_for_moment(self.presentation_times, seconds)

    def _collect(self, seeks: Sequence[float], convert: Callable[[av.VideoFrame], T]) -> list[T]:
        """For each seek, convert the first frame whose PTS is at or after it (one decode pass)."""
        order = sorted(range(len(seeks)), key=seeks.__getitem__)
        out: dict[int, T] = {}
        cursor = 0
        self._container.seek(0)
        for frame in self._container.decode(self._stream):
            shown = float(frame.pts * self._stream.time_base) - self._start if frame.pts is not None else None
            if shown is None:
                continue
            while cursor < len(order) and shown >= seeks[order[cursor]] - 1e-6:
                out[order[cursor]] = convert(frame)
                cursor += 1
            if cursor == len(order):
                break
        if cursor < len(order):
            raise ValueError(f"Could not decode frame at {round(seeks[order[cursor]] * 1000)} ms")
        return [out[i] for i in range(len(seeks))]

    def frames_at(self, seeks: Sequence[float], width: int) -> list[np.ndarray]:
        """Decode the frame shown at each seek time, scaled for analysis.

        Args:
            seeks: Times from `seek_for_moment`, in any order.
            width: Output width in pixels; height keeps the aspect ratio and stays even.

        Returns:
            One RGB uint8 array per seek, in the order of `seeks`.

        Raises:
            ValueError: If a frame at or after a seek time cannot be decoded.
        """
        return self._collect(seeks, lambda frame: scaled_rgb(frame, width))

    def png_at(self, seek: float, max_size: int = IMAGE_MAX_SIZE, crop: tuple[int, int, int, int] | None = None) -> bytes:
        """Decode the frame shown at `seek` and return it as PNG bytes.

        Args:
            seek: Time from `seek_for_moment`.
            max_size: Longest allowed side in pixels; smaller frames are never enlarged.
            crop: Optional `(x, y, width, height)` in native pixels, cut out before any reduction.

        Raises:
            ValueError: If `crop` is empty or reaches outside the frame.
        """
        convert = (lambda frame: scaled_png(frame, max_size)) if crop is None else (lambda frame: cropped_png(frame, max_size, crop))
        return self._collect([seek], convert)[0]
