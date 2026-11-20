"""Pointer sampling. `default_source()` returns None where position cannot be read."""
from __future__ import annotations

import os
import sys

from .trace import PointerSource


def default_source() -> PointerSource | None:
    """Windows and X11 sessions only. Wayland (no global pointer position) and macOS (not yet ported) give None,
    which the recorder turns into a trace with `available: false`."""
    try:
        if sys.platform == "win32":
            from .win32 import Win32PointerSource
            return Win32PointerSource()
        if sys.platform.startswith("linux") and os.environ.get("DISPLAY") and os.environ.get("XDG_SESSION_TYPE") != "wayland":
            from .x11 import X11PointerSource
            return X11PointerSource()
    except OSError:
        return None
    return None
