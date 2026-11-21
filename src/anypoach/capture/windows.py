"""List the visible application windows (X11 and Windows) so one can be recorded by its bounds.

Wayland goes through the portal's own window picker instead.
"""
from __future__ import annotations

import ctypes
import ctypes.util
import sys
from typing import NamedTuple, Protocol

from anypoach.pointer.trace import Rect

MIN_SIZE = 50  # smaller windows are tooltips, handles and other furniture


class WindowInfo(NamedTuple):
    """A window the user can pick. `rect` is its content area in global physical pixels."""
    title: str
    rect: Rect


class WindowLister(Protocol):
    """Something that lists the visible windows, topmost first."""
    def windows(self) -> list[WindowInfo]:
        """The visible, titled windows of at least 50x50 pixels."""


class X11Windows:
    """Lists windows from the window manager's `_NET_CLIENT_LIST` over libX11.

    Raises:
        OSError: On construction, if libX11 is missing or the display cannot be opened.
    """
    def __init__(self) -> None:
        library = ctypes.util.find_library("X11")
        if library is None:
            raise OSError("libX11 is not available")
        x = self._x = ctypes.CDLL(library)
        x.XOpenDisplay.restype, x.XOpenDisplay.argtypes = ctypes.c_void_p, [ctypes.c_char_p]
        x.XDefaultRootWindow.restype, x.XDefaultRootWindow.argtypes = ctypes.c_ulong, [ctypes.c_void_p]
        x.XInternAtom.restype, x.XInternAtom.argtypes = ctypes.c_ulong, [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
        x.XFree.argtypes = [ctypes.c_void_p]
        x.XGetWindowProperty.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_long, ctypes.c_long, ctypes.c_int, ctypes.c_ulong,
            ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_ulong),
            ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_void_p)]
        x.XGetGeometry.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong),
                                   *[ctypes.POINTER(ctypes.c_int)] * 2, *[ctypes.POINTER(ctypes.c_uint)] * 4]
        x.XTranslateCoordinates.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_int, ctypes.c_int,
                                            ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
                                            ctypes.POINTER(ctypes.c_ulong)]
        self._display = x.XOpenDisplay(None)
        if not self._display:
            raise OSError("Could not open the X display")
        self._root = x.XDefaultRootWindow(self._display)

    def _property(self, window: int, name: bytes, kind: int):
        """The raw items of a window property, as `(address, count, item_size_in_bytes)`, or None when absent."""
        x = self._x
        atom = x.XInternAtom(self._display, name, True)
        if not atom:
            return None
        actual, fmt, count, after, data = ctypes.c_ulong(), ctypes.c_int(), ctypes.c_ulong(), ctypes.c_ulong(), ctypes.c_void_p()
        status = x.XGetWindowProperty(self._display, window, atom, 0, 4096, 0, kind, ctypes.byref(actual), ctypes.byref(fmt),
                                      ctypes.byref(count), ctypes.byref(after), ctypes.byref(data))
        if status != 0 or not data.value or count.value == 0:
            return None
        return data.value, count.value, fmt.value

    def _title(self, window: int) -> str:
        utf8 = self._x.XInternAtom(self._display, b"UTF8_STRING", False)
        found = self._property(window, b"_NET_WM_NAME", utf8)
        if found is None:
            return ""
        address, count, _ = found
        try:
            return ctypes.string_at(address, count).decode("utf-8", "replace").strip()
        finally:
            self._x.XFree(address)

    def windows(self) -> list[WindowInfo]:
        """Visible client windows, topmost first (`_NET_CLIENT_LIST` is bottom to top)."""
        found = self._property(self._root, b"_NET_CLIENT_LIST", 33)  # XA_WINDOW
        if found is None:
            return []
        address, count, _ = found
        try:
            ids = list((ctypes.c_ulong * count).from_address(address))
        finally:
            self._x.XFree(address)
        result = []
        for window in reversed(ids):
            title = self._title(window)
            root, x, y, w, h, border, depth = (ctypes.c_ulong(), ctypes.c_int(), ctypes.c_int(), ctypes.c_uint(),
                                               ctypes.c_uint(), ctypes.c_uint(), ctypes.c_uint())
            if not self._x.XGetGeometry(self._display, window, ctypes.byref(root), ctypes.byref(x), ctypes.byref(y),
                                        ctypes.byref(w), ctypes.byref(h), ctypes.byref(border), ctypes.byref(depth)):
                continue
            abs_x, abs_y, child = ctypes.c_int(), ctypes.c_int(), ctypes.c_ulong()
            self._x.XTranslateCoordinates(self._display, window, self._root, 0, 0, ctypes.byref(abs_x), ctypes.byref(abs_y),
                                          ctypes.byref(child))
            if title and w.value >= MIN_SIZE and h.value >= MIN_SIZE:
                result.append(WindowInfo(title, Rect(abs_x.value, abs_y.value, w.value, h.value)))
        return result


class Win32Windows:
    """Lists top-level windows with `EnumWindows`, using the DWM frame bounds so shadows are not included."""
    def windows(self) -> list[WindowInfo]:
        """Visible, non-minimized, non-cloaked, titled windows, topmost first."""
        user32, dwm = ctypes.windll.user32, ctypes.windll.dwmapi  # type: ignore[attr-defined]
        from ctypes import wintypes
        found: list[WindowInfo] = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def visit(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
                return True
            cloaked = wintypes.DWORD()
            dwm.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(cloaked), ctypes.sizeof(cloaked))  # DWMWA_CLOAKED
            length = user32.GetWindowTextLengthW(hwnd)
            if cloaked.value or length == 0:
                return True
            title = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, title, length + 1)
            box = wintypes.RECT()
            if dwm.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(box), ctypes.sizeof(box)) != 0:  # EXTENDED_FRAME_BOUNDS
                return True
            width, height = box.right - box.left, box.bottom - box.top
            if width >= MIN_SIZE and height >= MIN_SIZE:
                found.append(WindowInfo(title.value, Rect(box.left, box.top, width, height)))
            return True

        user32.EnumWindows(visit, 0)  # z-order, topmost first
        return found


class MacWindows:
    """Lists on-screen application windows with `CGWindowListCopyWindowInfo` (ordinary windows, layer 0).

    CoreGraphics speaks points; `rect` is converted to physical pixels with the scale of the display the window is
    on. Without Screen Recording permission macOS hides window names, so the title falls back to the app's name.

    Raises:
        OSError: On construction, if the system libraries cannot be loaded.
    """
    _ON_SCREEN_ONLY, _NO_DESKTOP = 1, 16  # kCGWindowListOptionOnScreenOnly, kCGWindowListExcludeDesktopElements

    def __init__(self, cg=None) -> None:
        from anypoach.macos import CoreGraphics, _load
        self._cg = cg or CoreGraphics()
        c = self._lib = self._cg._lib
        cf = self._cf = _load("CoreFoundation")
        c.CGWindowListCopyWindowInfo.restype, c.CGWindowListCopyWindowInfo.argtypes = ctypes.c_void_p, [ctypes.c_uint32, ctypes.c_uint32]
        c.CGRectMakeWithDictionaryRepresentation.restype = ctypes.c_bool
        c.CGRectMakeWithDictionaryRepresentation.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        cf.CFArrayGetCount.restype, cf.CFArrayGetCount.argtypes = ctypes.c_long, [ctypes.c_void_p]
        cf.CFArrayGetValueAtIndex.restype, cf.CFArrayGetValueAtIndex.argtypes = ctypes.c_void_p, [ctypes.c_void_p, ctypes.c_long]
        cf.CFDictionaryGetValue.restype, cf.CFDictionaryGetValue.argtypes = ctypes.c_void_p, [ctypes.c_void_p, ctypes.c_void_p]
        cf.CFStringCreateWithCString.restype = ctypes.c_void_p
        cf.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
        cf.CFStringGetCString.restype = ctypes.c_bool
        cf.CFStringGetCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_uint32]
        cf.CFNumberGetValue.restype = ctypes.c_bool
        cf.CFNumberGetValue.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
        cf.CFRelease.argtypes = [ctypes.c_void_p]

    def _key(self, name: bytes):
        return self._cf.CFStringCreateWithCString(None, name, 0x08000100)  # kCFStringEncodingUTF8

    def _string(self, dictionary, key: bytes) -> str:
        k = self._key(key)
        try:
            value = self._cf.CFDictionaryGetValue(dictionary, k)
        finally:
            self._cf.CFRelease(k)
        if not value:
            return ""
        buffer = ctypes.create_string_buffer(1024)
        return buffer.value.decode("utf-8", "replace") if self._cf.CFStringGetCString(value, buffer, 1024, 0x08000100) else ""

    def _layer(self, dictionary) -> int:
        k = self._key(b"kCGWindowLayer")
        try:
            value = self._cf.CFDictionaryGetValue(dictionary, k)
        finally:
            self._cf.CFRelease(k)
        number = ctypes.c_int(-1)
        if value:
            self._cf.CFNumberGetValue(value, 9, ctypes.byref(number))  # kCFNumberIntType
        return number.value

    def windows(self) -> list[WindowInfo]:
        """Ordinary on-screen windows of at least 50x50 points, topmost first."""
        from anypoach.macos import CGRect
        displays = self._cg.displays()
        listing = self._lib.CGWindowListCopyWindowInfo(self._ON_SCREEN_ONLY | self._NO_DESKTOP, 0)
        if not listing:
            return []
        found = []
        try:
            for index in range(self._cf.CFArrayGetCount(listing)):
                entry = self._cf.CFArrayGetValueAtIndex(listing, index)
                if self._layer(entry) != 0:
                    continue
                key = self._key(b"kCGWindowBounds")
                try:
                    bounds = self._cf.CFDictionaryGetValue(entry, key)
                finally:
                    self._cf.CFRelease(key)
                box = CGRect()
                if not bounds or not self._lib.CGRectMakeWithDictionaryRepresentation(bounds, ctypes.byref(box)):
                    continue
                if box.size.width < MIN_SIZE or box.size.height < MIN_SIZE:
                    continue
                owner, name = self._string(entry, b"kCGWindowOwnerName"), self._string(entry, b"kCGWindowName")
                title = f"{owner} — {name}" if owner and name else owner or name
                scale = next((d.scale for d in displays if d.bounds.x <= box.origin.x < d.bounds.x + d.bounds.width
                              and d.bounds.y <= box.origin.y < d.bounds.y + d.bounds.height), 1.0)
                if title:
                    found.append(WindowInfo(title, Rect(box.origin.x * scale, box.origin.y * scale,
                                                        box.size.width * scale, box.size.height * scale)))
        finally:
            self._cf.CFRelease(listing)
        return found


def default_windows() -> WindowLister | None:
    """The window lister for this platform, or None where there is none (Wayland, no X display)."""
    try:
        if sys.platform == "darwin":
            return MacWindows()
        if sys.platform == "win32":
            return Win32Windows()
        if sys.platform.startswith("linux"):
            return X11Windows()
    except OSError:
        return None
    return None
