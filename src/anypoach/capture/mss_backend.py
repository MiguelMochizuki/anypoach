"""Portable capture through `mss` (X11, Windows, macOS). Wayland needs the portal and is not covered here."""
from __future__ import annotations

import math
import sys
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
        platform: Value of `sys.platform`. On `darwin`, `mss` speaks points and Retina frames come back in pixels,
            so regions are converted with each display's scale (see `anypoach.macos`).
        cg: The CoreGraphics wrapper used on `darwin`; created on first use when omitted.
    """
    def __init__(self, *, sct: Any = None, clock: Callable[[], float] = time.perf_counter,
                 platform: str = sys.platform, cg: Any = None) -> None:
        self._injected, self._clock, self._local = sct, clock, threading.local()
        self._mac, self._cg = platform == "darwin", cg

    def _displays(self) -> list[Any]:
        if self._cg is None:
            from anypoach import macos
            self._cg = macos.CoreGraphics()
        return self._cg.displays()

    def _sct(self) -> Any:
        if self._injected is not None:
            return self._injected
        if not hasattr(self._local, "sct"):  # mss handles are per-thread: the capture thread makes its own
            import mss
            self._local.sct = mss.mss()
        return self._local.sct

    def screens(self) -> list[Screen]:
        """List the physical monitors (the virtual union of all monitors is left out). `scale` is 1.0 except on macOS,
        where bounds are in physical pixels and `scale` is the display's pixels per point."""
        if self._mac:
            return [Screen(d.id, Rect(d.bounds.x * d.scale, d.bounds.y * d.scale, d.bounds.width * d.scale,
                                      d.bounds.height * d.scale), d.scale) for d in self._displays()]
        monitors = self._sct().monitors[1:]  # [0] is the virtual union of all monitors
        return [Screen(i, Rect(m["left"], m["top"], m["width"], m["height"]), 1.0) for i, m in enumerate(monitors, 1)]

    def grab(self, region: Rect) -> Frame:
        """Grab `region` (global physical pixels), rounded to whole pixels, and stamp it with the clock's reading."""
        if self._mac:
            return self._grab_in_points(region)
        box = {"left": round(region.x), "top": round(region.y), "width": round(region.width), "height": round(region.height)}
        shot = self._sct().grab(box)
        pixels = np.frombuffer(shot.bgra, np.uint8).reshape(shot.height, shot.width, 4)
        return Frame(pixels, self._clock())

    def _grab_in_points(self, region: Rect) -> Frame:
        """macOS: grab the whole points that cover `region`, then cut out exactly its pixels."""
        displays = self._displays()
        scale = next((d.scale for d in displays if d.bounds.contains(region.x / d.scale, region.y / d.scale)), 1.0)
        left, top = math.floor(region.x / scale), math.floor(region.y / scale)
        right, bottom = math.ceil((region.x + region.width) / scale), math.ceil((region.y + region.height) / scale)
        shot = self._sct().grab({"left": left, "top": top, "width": right - left, "height": bottom - top})
        pixels = np.frombuffer(shot.bgra, np.uint8).reshape(shot.height, shot.width, 4)
        x0, y0 = round(region.x - left * scale), round(region.y - top * scale)
        width, height = round(region.width), round(region.height)
        out = np.zeros((height, width, 4), np.uint8)  # a short frame is padded rather than handed over mis-sized
        cut = pixels[y0:y0 + height, x0:x0 + width]
        out[:cut.shape[0], :cut.shape[1]] = cut
        return Frame(out, self._clock())
