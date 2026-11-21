"""One global shortcut that toggles recording, registered as a chord (not a keyboard hook).

Only the chord is delivered: `RegisterHotKey` on Windows and `XGrabKey` on X11. No other key press is seen. Wayland
(the portal's GlobalShortcuts is not offered by every desktop) and macOS are not covered.
"""
from __future__ import annotations

import ctypes
import ctypes.util
import select
import sys
import threading
from collections.abc import Callable
from typing import Protocol

from anypoach.favorites import data_dir

CHORD = "Ctrl+Alt+Shift+P"


class Hotkey(Protocol):
    """Something that calls a function whenever the chord is pressed."""
    def start(self, callback: Callable[[], None]) -> bool:
        """Register the chord; False when the system refused (another program owns it, say). Safe to call once."""

    def stop(self) -> None:
        """Release the chord and end the listening thread. Safe to call more than once."""


def _marker():
    return data_dir().parent / "global-shortcut"


def shortcut_enabled() -> bool:
    """Whether the user turned the shortcut on (off until they do)."""
    return _marker().exists()


def remember_shortcut(enabled: bool) -> None:
    """Keep the user's choice; a failure to write only means it is forgotten at the next start."""
    path = _marker()
    try:
        if enabled:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
        else:
            path.unlink(missing_ok=True)
    except OSError:
        pass


_errors: list[int] = []


@ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)
def _on_x_error(_display, _event):  # a refused grab is BadAccess: note it instead of letting Xlib exit the process
    _errors.append(1)
    return 0


class _Thread:
    """Shared plumbing: a thread that registers on its own side and reports whether that worked."""
    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def _run(self, callback: Callable[[], None], ready: list) -> None:
        raise NotImplementedError

    def start(self, callback: Callable[[], None]) -> bool:
        ready: list = []
        done = threading.Event()
        self._thread = threading.Thread(target=lambda: self._run(callback, (ready, done)), daemon=True)
        self._thread.start()
        done.wait(2)
        return bool(ready and ready[0])

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(2)
            self._thread = None


class X11Hotkey(_Thread):
    """`XGrabKey` on the root window for Ctrl+Alt+Shift+P, with and without Caps Lock and Num Lock."""
    def _run(self, callback, signal) -> None:
        ready, done = signal
        library = ctypes.util.find_library("X11")
        if library is None:
            ready.append(False)
            done.set()
            return
        x = ctypes.CDLL(library)
        x.XOpenDisplay.restype, x.XOpenDisplay.argtypes = ctypes.c_void_p, [ctypes.c_char_p]
        x.XDefaultRootWindow.restype, x.XDefaultRootWindow.argtypes = ctypes.c_ulong, [ctypes.c_void_p]
        x.XStringToKeysym.restype, x.XStringToKeysym.argtypes = ctypes.c_ulong, [ctypes.c_char_p]
        x.XKeysymToKeycode.restype, x.XKeysymToKeycode.argtypes = ctypes.c_ubyte, [ctypes.c_void_p, ctypes.c_ulong]
        x.XConnectionNumber.argtypes = [ctypes.c_void_p]
        x.XGrabKey.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_uint, ctypes.c_ulong, ctypes.c_int, ctypes.c_int,
                               ctypes.c_int]
        x.XUngrabKey.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_uint, ctypes.c_ulong]
        x.XPending.argtypes = [ctypes.c_void_p]
        x.XNextEvent.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        x.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
        x.XCloseDisplay.argtypes = [ctypes.c_void_p]
        x.XSetErrorHandler.argtypes = [ctypes.c_void_p]
        x.XSetErrorHandler(_on_x_error)  # module-level, so it outlives every thread that installed it
        display = x.XOpenDisplay(None)
        if not display:
            ready.append(False)
            done.set()
            return
        root = x.XDefaultRootWindow(display)
        keycode = x.XKeysymToKeycode(display, x.XStringToKeysym(b"p"))
        base = 1 | 4 | 8  # Shift, Control, Alt (Mod1)
        before = len(_errors)
        for extra in (0, 2, 16, 2 | 16):  # Caps Lock, Num Lock (Mod2)
            x.XGrabKey(display, keycode, base | extra, root, 1, 1, 1)
        x.XSync(display, 0)
        refused = len(_errors) > before
        ready.append(not refused)
        done.set()
        event, fd = ctypes.create_string_buffer(192), x.XConnectionNumber(display)
        while not self._stop.is_set() and not refused:
            if select.select([fd], [], [], 0.1)[0]:
                while x.XPending(display):
                    x.XNextEvent(display, event)
                    if ctypes.c_int.from_buffer(event).value == 2:  # KeyPress
                        callback()
        for extra in (0, 2, 16, 2 | 16):
            x.XUngrabKey(display, keycode, base | extra, root)
        x.XCloseDisplay(display)


class Win32Hotkey(_Thread):
    """`RegisterHotKey` for Ctrl+Alt+Shift+P with a message loop on its own thread."""
    def _run(self, callback, signal) -> None:
        ready, done = signal
        from ctypes import wintypes
        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        mods = 0x0002 | 0x0001 | 0x0004 | 0x4000  # MOD_CONTROL | MOD_ALT | MOD_SHIFT | MOD_NOREPEAT
        ok = bool(user32.RegisterHotKey(None, 1, mods, ord("P")))
        ready.append(ok)
        done.set()
        if not ok:
            return
        message = wintypes.MSG()
        while not self._stop.is_set():
            if user32.PeekMessageW(ctypes.byref(message), None, 0, 0, 1):  # PM_REMOVE
                if message.message == 0x0312:  # WM_HOTKEY
                    callback()
            else:
                self._stop.wait(0.05)
        user32.UnregisterHotKey(None, 1)


def default_hotkey() -> Hotkey | None:
    """The shortcut registrar for this system, or None (Wayland, macOS, no X display library)."""
    if sys.platform == "win32":
        return Win32Hotkey()
    if sys.platform.startswith("linux") and ctypes.util.find_library("X11"):
        import os
        if os.environ.get("XDG_SESSION_TYPE") != "wayland" and os.environ.get("DISPLAY"):
            return X11Hotkey()
    return None
