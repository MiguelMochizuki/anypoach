"""Pointer sampling. `default_source()` returns None where position cannot be read."""
from __future__ import annotations

import os
import sys

from .trace import PointerSource


def default_source() -> PointerSource | None:
    """Windows, macOS and X11 sessions. Wayland (no global pointer position) gives None, and so does a platform
    whose library cannot be loaded; the recorder turns None into a trace with `available: false`."""
    try:
        if sys.platform == "win32":
            from .win32 import Win32PointerSource
            return Win32PointerSource()
        if sys.platform == "darwin":
            from .macos import MacPointerSource
            return MacPointerSource()
        if sys.platform.startswith("linux") and os.environ.get("DISPLAY") and os.environ.get("XDG_SESSION_TYPE") != "wayland":
            from .x11 import X11PointerSource
            return X11PointerSource()
    except OSError:
        return None
    return None
