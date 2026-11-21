"""CoreGraphics through `ctypes`: displays and their scale, the pointer, and the Screen Recording permission.

Everything here speaks points (what CoreGraphics speaks); converting to physical pixels is left to the callers
that need it. Polling only: no event taps, no hooks, and no permission beyond Screen Recording itself.
"""
from __future__ import annotations

import ctypes
import ctypes.util
from typing import Any, NamedTuple

from anypoach.pointer.trace import Button, Rect

_MAX_DISPLAYS = 16
_BUTTONS: dict[Button, int] = {"left": 0, "right": 1, "other": 2}  # kCGMouseButtonLeft, Right, Center
_COMBINED_SESSION_STATE = 0  # kCGEventSourceStateCombinedSessionState


class CGPoint(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]


class CGSize(ctypes.Structure):
    _fields_ = [("width", ctypes.c_double), ("height", ctypes.c_double)]


class CGRect(ctypes.Structure):
    _fields_ = [("origin", CGPoint), ("size", CGSize)]


class Display(NamedTuple):
    """An active display.

    Attributes:
        id: The CoreGraphics display id.
        bounds: Position and size in points, top-left origin, primary display at (0, 0).
        scale: Pixels per point (2.0 on a Retina display in its default mode).
    """
    id: int
    bounds: Rect
    scale: float


class CoreGraphics:
    """The handful of CoreGraphics calls AnyPoach needs.

    Args:
        lib: A handle with the CoreGraphics functions (`ApplicationServices` re-exports them); meant for tests.
        cf: A handle with `CFRelease` (CoreFoundation); meant for tests.

    Raises:
        OSError: If a library cannot be found or loaded.
    """
    def __init__(self, lib: Any = None, cf: Any = None) -> None:
        self._lib = lib if lib is not None else _load("ApplicationServices")
        self._cf = cf if cf is not None else _load("CoreFoundation")
        lib_ = self._lib
        lib_.CGEventCreate.restype, lib_.CGEventCreate.argtypes = ctypes.c_void_p, [ctypes.c_void_p]
        lib_.CGEventGetLocation.restype, lib_.CGEventGetLocation.argtypes = CGPoint, [ctypes.c_void_p]
        lib_.CGEventSourceButtonState.restype = ctypes.c_bool
        lib_.CGEventSourceButtonState.argtypes = [ctypes.c_int32, ctypes.c_uint32]
        lib_.CGGetActiveDisplayList.restype = ctypes.c_int32
        lib_.CGGetActiveDisplayList.argtypes = [ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32),
                                                ctypes.POINTER(ctypes.c_uint32)]
        lib_.CGDisplayBounds.restype, lib_.CGDisplayBounds.argtypes = CGRect, [ctypes.c_uint32]
        lib_.CGDisplayCopyDisplayMode.restype = ctypes.c_void_p
        lib_.CGDisplayCopyDisplayMode.argtypes = [ctypes.c_uint32]
        lib_.CGDisplayModeGetPixelWidth.restype = ctypes.c_size_t
        lib_.CGDisplayModeGetPixelWidth.argtypes = [ctypes.c_void_p]
        lib_.CGDisplayModeRelease.argtypes = [ctypes.c_void_p]
        self._cf.CFRelease.argtypes = [ctypes.c_void_p]
        for name in ("CGPreflightScreenCaptureAccess", "CGRequestScreenCaptureAccess"):
            function = getattr(lib_, name, None)  # macOS 11+; absent on older systems
            if function is not None:
                function.restype, function.argtypes = ctypes.c_bool, []

    def displays(self) -> list[Display]:
        """List the active displays with their bounds in points and their pixels-per-point scale."""
        ids, count = (ctypes.c_uint32 * _MAX_DISPLAYS)(), ctypes.c_uint32(0)
        if self._lib.CGGetActiveDisplayList(_MAX_DISPLAYS, ids, ctypes.pointer(count)) != 0:
            return []
        result = []
        for display_id in list(ids)[: count.value]:
            box = self._lib.CGDisplayBounds(display_id)
            mode = self._lib.CGDisplayCopyDisplayMode(display_id)
            try:
                pixels = self._lib.CGDisplayModeGetPixelWidth(mode) if mode else 0
            finally:
                if mode:
                    self._lib.CGDisplayModeRelease(mode)
            scale = pixels / box.size.width if pixels and box.size.width else 1.0
            result.append(Display(display_id, Rect(box.origin.x, box.origin.y, box.size.width, box.size.height),
                                  max(1.0, scale)))
        return result

    def pointer(self) -> tuple[float, float]:
        """The pointer position in points, global, top-left origin."""
        event = self._lib.CGEventCreate(None)
        try:
            point = self._lib.CGEventGetLocation(event)
        finally:
            self._cf.CFRelease(event)
        return point.x, point.y

    def button_down(self, button: Button) -> bool:
        """Whether the mouse button is held, as the combined session sees it."""
        return bool(self._lib.CGEventSourceButtonState(_COMBINED_SESSION_STATE, _BUTTONS[button]))

    def screen_recording_allowed(self) -> bool | None:
        """Whether Screen Recording is allowed, or None where the system cannot say (before macOS 11)."""
        function = getattr(self._lib, "CGPreflightScreenCaptureAccess", None)
        return None if function is None else bool(function())

    def request_screen_recording(self) -> bool | None:
        """Ask macOS to show its Screen Recording prompt; returns the current state, or None before macOS 11."""
        function = getattr(self._lib, "CGRequestScreenCaptureAccess", None)
        return None if function is None else bool(function())


def _load(name: str) -> ctypes.CDLL:
    path = ctypes.util.find_library(name)
    if path is None:
        raise OSError(f"{name} is not available")
    return ctypes.CDLL(path)
