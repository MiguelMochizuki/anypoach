"""macOS pointer source: CoreGraphics position and button state, polled (no event taps, no permission prompt)."""
from __future__ import annotations

import time

from anypoach import macos
from anypoach.macos import CoreGraphics, Display

from .trace import Button, PointerSample

_BUTTONS: tuple[Button, ...] = ("left", "right", "other")
_REFRESH_S = 1.0


class MacPointerSource:
    """Reads the pointer in points and reports it in global physical pixels, top-left origin.

    The scale is that of the display under the pointer. The display list is read once and read again, at most
    once a second, when the pointer is outside every known display (a display was plugged in, or the pointer is
    in a gap of the layout); until a display matches, the nearest one is used.

    Args:
        cg: The CoreGraphics wrapper; created when omitted. Meant to be replaced in tests.

    Raises:
        OSError: On construction, if CoreGraphics cannot be loaded.
    """
    # ponytail: the global origin is scaled like `physical_rect` scales it, so absolute pixels are exact only
    # while the chosen area and the pointer share one display; mixed-scale layouts need a per-display space.
    def __init__(self, cg: CoreGraphics | None = None) -> None:
        self._cg = cg if cg is not None else macos.CoreGraphics()
        self._displays = self._cg.displays()
        self._refreshed_at = float("-inf")

    def sample(self) -> PointerSample:
        """Read the pointer position (physical pixels) and which buttons are held."""
        x, y = self._cg.pointer()
        display = self._find(x, y)
        scale = display.scale if display else 1.0
        held = frozenset(button for button in _BUTTONS if self._cg.button_down(button))
        return PointerSample(x * scale, y * scale, held)

    def _find(self, x: float, y: float) -> Display | None:
        for display in self._displays:
            if display.bounds.contains(x, y):
                return display
        now = time.monotonic()
        if now - self._refreshed_at >= _REFRESH_S:
            self._refreshed_at, self._displays = now, self._cg.displays()
            for display in self._displays:
                if display.bounds.contains(x, y):
                    return display
        return min(self._displays, key=lambda d: _distance(d, x, y), default=None)


def _distance(display: Display, x: float, y: float) -> float:
    box = display.bounds
    dx = max(box.x - x, 0, x - (box.x + box.width))
    dy = max(box.y - y, 0, y - (box.y + box.height))
    return dx * dx + dy * dy
