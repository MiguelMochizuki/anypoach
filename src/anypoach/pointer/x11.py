"""X11 pointer source: XQueryPointer through ctypes (polling only, no XInput grabs or record extension)."""
from __future__ import annotations

import ctypes
import ctypes.util

from .trace import PointerSample

_BUTTON_MASKS = (("left", 1 << 8), ("other", 1 << 9), ("right", 1 << 10))  # Button1/2/3Mask; middle counts as other


class X11PointerSource:
    """Reads the pointer from an X11 display with `XQueryPointer`, by polling.

    Raises:
        OSError: On construction, if libX11 is missing or the display cannot be opened.
    """
    def __init__(self) -> None:
        library = ctypes.util.find_library("X11")
        if library is None:
            raise OSError("libX11 is not available")
        self._x11 = ctypes.CDLL(library)
        self._x11.XOpenDisplay.restype = ctypes.c_void_p
        self._x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
        self._x11.XDefaultRootWindow.restype = ctypes.c_ulong
        self._x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        self._x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
        self._display = self._x11.XOpenDisplay(None)
        if not self._display:
            raise OSError("Could not open the X display")
        self._root = self._x11.XDefaultRootWindow(self._display)

    def sample(self) -> PointerSample:
        """Read the pointer position on the root window and which buttons are down; the middle button counts as `other`."""
        root, child = ctypes.c_ulong(), ctypes.c_ulong()
        root_x, root_y, win_x, win_y = (ctypes.c_int() for _ in range(4))
        mask = ctypes.c_uint()
        self._x11.XQueryPointer(ctypes.c_void_p(self._display), ctypes.c_ulong(self._root), ctypes.byref(root),
                                ctypes.byref(child), ctypes.byref(root_x), ctypes.byref(root_y), ctypes.byref(win_x),
                                ctypes.byref(win_y), ctypes.byref(mask))
        held = frozenset(name for name, bit in _BUTTON_MASKS if mask.value & bit)
        return PointerSample(root_x.value, root_y.value, held)  # type: ignore[arg-type]

    def close(self) -> None:
        """Close the display connection. Safe to call more than once."""
        if self._display:
            self._x11.XCloseDisplay(ctypes.c_void_p(self._display))
            self._display = None
