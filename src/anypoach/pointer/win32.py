"""Windows pointer source: GetCursorPos + GetAsyncKeyState (polling only, no hooks)."""
from __future__ import annotations

import ctypes
from ctypes import wintypes

from .trace import Button, PointerSample

_VK = {"left": 0x01, "right": 0x02, "other": 0x04}  # VK_LBUTTON, VK_RBUTTON, VK_MBUTTON


class Win32PointerSource:
    """The process must be per-monitor DPI aware, or GetCursorPos reports scaled (logical) coordinates."""

    def __init__(self) -> None:
        self._user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        self._winmm = ctypes.windll.winmm  # type: ignore[attr-defined]

    def open(self) -> None:
        """Ask Windows for 1 ms timer resolution; the default (about 15 ms) cannot sustain 120 Hz. Pair with `close`."""
        self._winmm.timeBeginPeriod(1)  # default timer granularity (~15 ms) cannot reach 120 Hz

    def close(self) -> None:
        """Release the 1 ms timer resolution requested by `open`."""
        self._winmm.timeEndPeriod(1)

    def sample(self) -> PointerSample:
        """Read the cursor position and which of the left, right, and middle buttons are down (physical pixels)."""
        point = wintypes.POINT()
        self._user32.GetCursorPos(ctypes.byref(point))
        held = frozenset(name for name, code in _VK.items() if self._user32.GetAsyncKeyState(code) & 0x8000)
        return PointerSample(point.x, point.y, held)  # type: ignore[arg-type]


__all__ = ["Button", "Win32PointerSource"]
