"""Small JPEG frames of a recording for the editor, decoded once, in memory only.

Each frame carries the time (milliseconds from the start of the video) of the moment it shows, the same axis that
`anypoach_read_moment` uses, so a comment pinned to a frame resolves to that frame for the assistant.
"""
from __future__ import annotations

import bisect
import threading
from collections.abc import Callable
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import av
import numpy as np

from .source import VideoSource

PROXY_RATE = 15
PROXY_MAX_SIDE = 640


@dataclass(frozen=True)
class ProxyFrame:
    """One reduced frame.

    Attributes:
        time_ms: Moment of the video it shows, in milliseconds from its start.
        jpeg: The frame as JPEG bytes.
    """
    time_ms: int
    jpeg: bytes


class FrameProxy:
    """The frames decoded so far, in time order.

    Args:
        duration_ms: Length of the recording in milliseconds.

    Attributes:
        frames: The frames, earliest first.
        done: Whether every frame was decoded (False when decoding was cancelled).
        duration_ms: Length of the recording in milliseconds.
    """
    def __init__(self, duration_ms: int) -> None:
        self.frames: list[ProxyFrame] = []
        self.done = False
        self.duration_ms = duration_ms
        self._times: list[int] = []

    def add(self, frame: ProxyFrame) -> None:
        """Append a frame; frames must arrive in time order."""
        self.frames.append(frame)
        self._times.append(frame.time_ms)

    def _index(self, time_ms: int) -> int | None:
        if not self._times:
            return None
        after = bisect.bisect_left(self._times, time_ms)
        if after == 0:
            return 0
        if after == len(self._times):
            return after - 1
        return after - 1 if time_ms - self._times[after - 1] <= self._times[after] - time_ms else after

    def nearest(self, time_ms: int) -> ProxyFrame | None:
        """The frame closest to `time_ms` (the earlier one on a tie), or None while there are no frames."""
        index = self._index(time_ms)
        return None if index is None else self.frames[index]

    def step(self, from_ms: int, direction: int) -> ProxyFrame | None:
        """The frame after (`direction` 1) or before (-1) the one closest to `from_ms`; None past either end."""
        index = self._index(from_ms)
        if index is None or not 0 <= index + direction < len(self.frames):
            return None
        return self.frames[index + direction]


def _jpeg_encoder(width: int, height: int) -> av.CodecContext:
    context = av.CodecContext.create("mjpeg", "w")
    context.width, context.height, context.pix_fmt = width, height, "yuvj420p"
    context.time_base = Fraction(1, PROXY_RATE)
    context.options = {"qscale": "4"}
    return context


def _encode(context: av.CodecContext, rgb: np.ndarray) -> bytes:
    frame = av.VideoFrame.from_ndarray(np.ascontiguousarray(rgb), format="rgb24").reformat(format="yuvj420p")
    return b"".join(bytes(packet) for packet in context.encode(frame))


def build_proxy(path: str | Path, *, cancel: threading.Event, on_frame: Callable[[ProxyFrame], None] | None = None,
                rate: float = PROXY_RATE, max_side: int = PROXY_MAX_SIDE) -> FrameProxy:
    """Decode a recording into reduced JPEG frames, `rate` per second, calling `on_frame` as each is ready.

    Args:
        path: A `.mp4` or `.mov` file.
        cancel: Checked before every frame; when set, decoding ends and the partial proxy is returned.
        on_frame: Called with each frame in time order, on the calling thread.
        rate: Frames per second.
        max_side: Longest side in pixels; smaller videos are never enlarged.

    Returns:
        The frames; `done` is False when `cancel` ended the work.

    Raises:
        ValueError: If the file is missing, unsupported, or cannot be decoded.
    """
    with VideoSource(path) as source:
        proxy = FrameProxy(round(source.duration_s * 1000))
        native_w, native_h = source.size
        width = max(2, min(native_w, round(native_w * max_side / max(native_w, native_h))))
        times_s = [i / rate for i in range(int(source.duration_s * rate + 1e-9) + 1) if i / rate < source.duration_s]
        seeks = [source.seek_for_moment(t) for t in times_s]
        encoders: list[av.CodecContext] = []

        def deliver(index: int, rgb: np.ndarray) -> None:
            if not encoders:
                encoders.append(_jpeg_encoder(rgb.shape[1], rgb.shape[0]))
            frame = ProxyFrame(round(times_s[index] * 1000), _encode(encoders[0], rgb))
            proxy.add(frame)
            if on_frame is not None:
                on_frame(frame)

        proxy.done = source.stream_frames(seeks, width, deliver, stop=cancel.is_set)
        return proxy
