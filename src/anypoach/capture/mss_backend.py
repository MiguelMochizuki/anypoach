"""Portable capture through `mss` (X11, Windows, macOS). Wayland needs the portal and is not covered here."""
from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

import numpy as np

from anypoach.pointer.trace import Rect

from .backend import Frame, Screen


class MssBackend:
    """Captures the screen with `mss` (X11, Windows, macOS).

    `mss` handles belong to one thread, so each thread that grabs gets its own. Wayland sessions need the
    desktop portal and are not supported here.

    Args:
        sct: An `mss`-like object to use instead of creating one; meant for tests.
        clock: Monotonic clock stamped on every frame.
    """
    def __init__(self, *, sct: Any = None, clock: Callable[[], float] = time.perf_counter) -> None:
        self._injected, self._clock, self._local = sct, clock, threading.local()

    def _sct(self) -> Any:
        if self._injected is not None:
            return self._injected
        if not hasattr(self._local, "sct"):  # mss handles are per-thread: the capture thread makes its own
            import mss
            self._local.sct = mss.mss()
        return self._local.sct

    def screens(self) -> list[Screen]:
        """List the physical monitors (the virtual union of all monitors is left out). `scale` is always 1.0."""
        monitors = self._sct().monitors[1:]  # [0] is the virtual union of all monitors
        return [Screen(i, Rect(m["left"], m["top"], m["width"], m["height"]), 1.0) for i, m in enumerate(monitors, 1)]

    def grab(self, region: Rect) -> Frame:
        """Grab `region`, rounded to whole pixels, and stamp it with the clock's current reading."""
        box = {"left": round(region.x), "top": round(region.y), "width": round(region.width), "height": round(region.height)}
        shot = self._sct().grab(box)
        pixels = np.frombuffer(shot.bgra, np.uint8).reshape(shot.height, shot.width, 4)
        return Frame(pixels, self._clock())
