"""Decode a short MP4/MOV with presentation-time seeking (single process, no ffmpeg CLI)."""
from __future__ import annotations

import bisect
from collections.abc import Callable, Sequence
from fractions import Fraction
from pathlib import Path
from typing import Self, TypeVar

import av
import numpy as np

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
    frame = av.VideoFrame.from_ndarray(np.ascontiguousarray(rgb), format="rgb24")
    codec = av.CodecContext.create("png", "w")
    codec.width, codec.height, codec.pix_fmt = frame.width, frame.height, "rgb24"
    codec.time_base = Fraction(1, 1)
    return b"".join(bytes(p) for p in [*codec.encode(frame), *codec.encode(None)])


class VideoSource:
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

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        if not self.closed:
            self._container.close()
            self.closed = True

    @property
    def presentation_times(self) -> list[float]:
        if self._times is None:
            base = self._stream.time_base
            self._container.seek(0)
            found = {float(p.pts * base) - self._start for p in self._container.demux(self._stream) if p.pts is not None}
            if not found:
                raise ValueError("Recording has no timestamped video frames")
            self._times = sorted(found)
        return self._times

    def seek_for_moment(self, seconds: float) -> float:
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
        """RGB uint8 samples scaled with the area filter to `width`, height kept even like `scale=W:-2`."""
        def convert(frame: av.VideoFrame) -> np.ndarray:
            height = max(2, round(frame.height * width / frame.width / 2) * 2)
            return frame.reformat(width=width, height=height, format="rgb24", interpolation="AREA").to_ndarray()
        return self._collect(seeks, convert)

    def png_at(self, seek: float, max_size: int = 1280) -> bytes:
        def convert(frame: av.VideoFrame) -> bytes:
            ratio = min(1.0, max_size / frame.width, max_size / frame.height)
            w, h = max(1, round(frame.width * ratio)), max(1, round(frame.height * ratio))
            return encode_png(frame.reformat(width=w, height=h, format="rgb24", interpolation="BICUBIC").to_ndarray())
        return self._collect([seek], convert)[0]
