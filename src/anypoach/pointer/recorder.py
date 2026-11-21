"""Polls a PointerSource at 120 Hz while a capture is active."""
from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable

from .trace import (
    SAMPLE_INTERVAL_MS,
    Button,
    Kind,
    PointerSample,
    PointerSource,
    PointerTrace,
    PointerTraceBuffer,
    PointerTraceEvent,
    Rect,
)

_ORDER: tuple[Button, ...] = ("left", "right", "other")


class PointerTraceRecorder:
    """Polls a pointer source at 120 Hz and turns it into a bounded trace of moves, presses, releases, and drags.

    Only position and button state are read. Positions are normalized to `bounds` (top-left origin, 0 to 1).
    Moves are recorded only inside the bounds; button edges are always recorded and flagged when outside.

    Args:
        bounds: Capture area in global physical pixels.
        source: Where samples come from, or None, which makes `start()` fail and the trace unavailable.
        clock: Monotonic clock.
        sleep: Function used to wait between samples.
        interval_s: Time between samples.
    """
    def __init__(self, bounds: Rect, source: PointerSource | None, *, clock: Callable[[], float] = time.perf_counter,
                 sleep: Callable[[float], None] = time.sleep, interval_s: float = SAMPLE_INTERVAL_MS / 1000) -> None:
        self.bounds = Rect(*bounds)
        self._source, self._clock, self._sleep, self._interval = source, clock, sleep, interval_s
        self._buffer = PointerTraceBuffer()
        self._started_at: float | None = None
        self._last: tuple[float, float] | None = None
        self._pressed: frozenset[Button] = frozenset()
        self._latest: PointerSample | None = None
        self._last_down_at: float | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self, *, spawn: bool = True) -> bool:
        """Open the source and begin sampling.

        Args:
            spawn: Sample on a background thread. Pass False to drive it with `poll`.

        Returns:
            False, without sampling, when there is no source or the bounds are empty.
        """
        if self._source is None or self.bounds.width <= 0 or self.bounds.height <= 0:
            return False
        getattr(self._source, "open", lambda: None)()
        self._started_at = self._clock()
        if spawn:
            self._thread = threading.Thread(target=self.run, name="anypoach-pointer", daemon=True)
            self._thread.start()
        return True

    @property
    def started(self) -> bool:
        """Whether `start()` succeeded."""
        return self._started_at is not None

    def latest(self) -> tuple[PointerSample, float | None] | None:
        """Last sample and the clock time of the last button press (None until each exists); used to draw the cursor."""
        return None if self._latest is None else (self._latest, self._last_down_at)

    def request_stop(self) -> None:
        """Ask the sampling loop to end; `stop()` waits for it."""
        self._stop.set()

    def stop(self) -> PointerTrace:
        """End sampling, close the source, and return the trace (`available` is False if sampling never started). Safe to call twice."""
        self.request_stop()
        if self._thread is not None:
            self._thread.join(timeout=1)
            self._thread = None
        if self._started_at is not None and self._source is not None:
            getattr(self._source, "close", lambda: None)()
        b = self._buffer
        return PointerTrace(self._started_at is not None, self.bounds, self._interval * 1000, b.sample_count,
                            b.inside_sample_count, b.button_sample_count, b.truncated, list(b.events))

    def run(self) -> None:
        """Blocking loop. Ticks are scheduled from the start time, so lateness does not accumulate."""
        assert self._started_at is not None
        tick = 0
        while not self._stop.is_set():
            self.poll()
            tick += 1
            now = self._clock()
            if now > self._started_at + (tick + 2) * self._interval:  # stalled: skip ahead, no catch-up burst
                tick = int((now - self._started_at) / self._interval) + 1
            delay = self._started_at + tick * self._interval - now
            if delay > 0:
                self._sleep(delay)

    def poll(self) -> None:
        """Take one sample and record the events it implies (press, release, move, or drag)."""
        assert self._source is not None and self._started_at is not None
        sample: PointerSample = self._source.sample()
        point = (sample.x, sample.y)
        inside = self.bounds.contains(*point)
        buttons = frozenset(sample.buttons)
        self._buffer.record_sample(inside=inside, button_held=bool(buttons))
        self._latest = sample
        if buttons - self._pressed:
            self._last_down_at = self._clock()
        # Button edges can happen outside a selected region; flag them instead of leaving a sequence unfinished.
        for button in (b for b in _ORDER if b in buttons - self._pressed):
            self._append("down", button, point, inside)
        for button in (b for b in _ORDER if b in self._pressed - buttons):
            self._append("up", button, point, inside)
        if not buttons and inside and self._last != point:
            self._append("move", None, point, True)
        if buttons and self._last != point:
            for button in (b for b in _ORDER if b in buttons):
                self._append("drag", button, point, inside)
        self._pressed, self._last = buttons, point

    def _append(self, kind: Kind, button: Button | None, point: tuple[float, float], within: bool) -> None:
        b = self.bounds
        x = min(1.0, max(0.0, (point[0] - b.x) / b.width))
        y = min(1.0, max(0.0, (point[1] - b.y) / b.height))
        elapsed = max(0.0, (self._clock() - (self._started_at or 0)) * 1000)
        self._buffer.append(PointerTraceEvent(math.floor(elapsed + 0.5), kind, x, y, button, within))
