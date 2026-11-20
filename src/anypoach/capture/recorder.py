"""Records a screen region to H.264 with real presentation times, drawing the cursor and click ring from the trace."""
from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import av
import numpy as np

from anypoach.pointer.recorder import PointerTraceRecorder
from anypoach.pointer.trace import PointerTrace, Rect

from .backend import CaptureBackend
from .overlay import draw_click_ring, draw_cursor

MAX_SIDE = 1920
FPS = 30
TIME_BASE = Fraction(1, 1000)


@dataclass(frozen=True)
class Recording:
    path: Path
    trace: PointerTrace
    epoch_range_ms: tuple[int, int]


def output_size(width: float, height: float) -> tuple[int, int]:
    """Even dimensions (H.264 4:2:0), longest side capped at MAX_SIDE; a 1 px region becomes 2x2."""
    scale = min(1.0, MAX_SIDE / max(width, height))
    return max(2, round(width * scale) // 2 * 2), max(2, round(height * scale) // 2 * 2)


class Recorder:
    def __init__(self, backend: CaptureBackend, pointer: PointerTraceRecorder | None, out_dir: Path, *,
                 clock: Callable[[], float] = time.perf_counter, wall_clock: Callable[[], float] = time.time,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self._backend, self._pointer, self._out_dir = backend, pointer, Path(out_dir)
        self._clock, self._wall_clock, self._sleep = clock, wall_clock, sleep
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._error: Exception | None = None
        self._container: av.container.OutputContainer | None = None
        self._region = Rect(0, 0, 0, 0)

    def start(self, region: Rect, *, spawn: bool = True) -> None:
        self._region = Rect(*region)
        self._size = output_size(region.width, region.height)
        self._ui_scale = max(1.0, max(region.width, region.height) / MAX_SIDE)  # keep the cursor's size after downscaling
        self._out_dir.mkdir(parents=True, exist_ok=True)
        self.path = self._out_dir / f"capture-{str(uuid.uuid4()).upper()}.mov"
        self._container = av.open(str(self.path), "w", format="mov")
        self._stream = self._container.add_stream("libx264", rate=FPS, options={"preset": "veryfast", "crf": "20", "bf": "0"})
        self._stream.width, self._stream.height, self._stream.pix_fmt = *self._size, "yuv420p"
        self._stream.codec_context.time_base = TIME_BASE
        self._first_time: float | None = None
        self._last_pts = -1
        self._frames = 0
        self._started_wall = self._wall_clock()
        self._started_at = self._clock()
        if self._pointer is not None and not self._pointer.started:
            self._pointer.start(spawn=spawn)
        if spawn:
            self._thread = threading.Thread(target=self._guarded_run, name="anypoach-capture", daemon=True)
            self._thread.start()

    def request_stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        """Blocking capture loop at FPS, scheduled by tick so lateness does not accumulate; stalls skip ahead."""
        interval, tick = 1 / FPS, 0
        while not self._stop.is_set():
            self.capture_once()
            tick += 1
            now = self._clock()
            if now > self._started_at + (tick + 2) * interval:
                tick = int((now - self._started_at) / interval) + 1
            delay = self._started_at + tick * interval - now
            if delay > 0:
                self._sleep(delay)

    def _guarded_run(self) -> None:
        try:
            self.run()
        except Exception as error:  # noqa: BLE001 - surfaced by stop(); a dead thread must not look like a clean recording
            self._error = error

    def capture_once(self) -> None:
        frame = self._backend.grab(self._region)
        pixels = frame.pixels
        if self._pointer is not None and (latest := self._pointer.latest()) is not None:
            sample, down_at = latest
            if not pixels.flags.writeable:
                pixels = pixels.copy()
            px, py = sample.x - self._region.x, sample.y - self._region.y
            if down_at is not None:
                draw_click_ring(pixels, px, py, frame.time_s - down_at, self._ui_scale)
            draw_cursor(pixels, px, py, self._ui_scale)
        if self._first_time is None:
            self._first_time = frame.time_s
        pts = max(self._last_pts + 1, round((frame.time_s - self._first_time) * 1000))  # strictly increasing
        video = av.VideoFrame.from_ndarray(np.ascontiguousarray(pixels), format="bgra")
        video = video.reformat(width=self._size[0], height=self._size[1], format="yuv420p")
        video.pts, video.time_base = pts, TIME_BASE
        self._last_pts = pts
        self._frames += 1
        assert self._container is not None
        self._container.mux(self._stream.encode(video))

    def stop(self) -> Recording:
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
            self._thread = None
        ended_wall = self._wall_clock()
        trace = self._pointer.stop() if self._pointer is not None else PointerTrace.unavailable(self._region)
        container, self._container = self._container, None
        assert container is not None
        if self._frames:
            container.mux(self._stream.encode())
        container.close()
        if self._error is not None:
            raise self._error
        if not self._frames:
            self.path.unlink(missing_ok=True)
            raise ValueError("The capture produced no frames")
        return Recording(self.path, trace, (round(self._started_wall * 1000), round(ended_wall * 1000)))
