"""The CoreGraphics wrapper, against a fake library (the real calls run only on macOS)."""
import ctypes
import sys
from types import SimpleNamespace

import pytest

from anypoach import macos
from anypoach.macos import CGPoint, CGRect, CoreGraphics, Display
from anypoach.pointer.trace import Rect


class Fn:
    """A stand-in for a C function: accepts `restype`/`argtypes`, and is callable."""

    def __init__(self, call):
        self.call, self.restype, self.argtypes = call, None, None

    def __call__(self, *args):
        return self.call(*args)


def fake_lib(displays=(), pointer=(0.0, 0.0), down=(), preflight=True, symbols=True):
    """`displays` is `[(id, (x, y, w, h) in points, pixel_width)]`; `down` holds the CG button numbers held."""
    by_id = {d[0]: d for d in displays}
    released = []

    def active(_max, ids, count):
        for i, display in enumerate(displays):
            ids[i] = display[0]
        count.contents.value = len(displays)
        return 0

    def bounds(display_id):
        x, y, w, h = by_id[display_id][1]
        return CGRect(CGPoint(x, y), macos.CGSize(w, h))

    lib = SimpleNamespace(
        CGEventCreate=Fn(lambda source: 1),
        CGEventGetLocation=Fn(lambda event: CGPoint(*pointer)),
        CGEventSourceButtonState=Fn(lambda state, button: button in down),
        CGGetActiveDisplayList=Fn(active),
        CGDisplayBounds=Fn(bounds),
        CGDisplayCopyDisplayMode=Fn(lambda display_id: display_id),  # the "mode" is just the id
        CGDisplayModeGetPixelWidth=Fn(lambda mode: by_id[mode][2]),
        CGDisplayModeRelease=Fn(lambda mode: None),
    )
    if symbols:
        lib.CGPreflightScreenCaptureAccess = Fn(lambda: preflight)
        lib.CGRequestScreenCaptureAccess = Fn(lambda: preflight)
    return lib, SimpleNamespace(CFRelease=Fn(released.append)), released


def test_displays_scale_is_pixels_over_points():
    lib, cf, _ = fake_lib(displays=[(1, (0, 0, 1512, 982), 3024), (2, (1512, 0, 1920, 1080), 1920)])
    assert CoreGraphics(lib, cf).displays() == [
        Display(1, Rect(0, 0, 1512, 982), 2.0), Display(2, Rect(1512, 0, 1920, 1080), 1.0)]


def test_displays_keep_a_negative_origin():
    lib, cf, _ = fake_lib(displays=[(1, (0, 0, 1512, 982), 3024), (2, (-1920, 0, 1920, 1080), 1920)])
    assert CoreGraphics(lib, cf).displays()[1].bounds == Rect(-1920, 0, 1920, 1080)


def test_pointer_returns_points_and_releases_the_event():
    lib, cf, released = fake_lib(pointer=(120.5, 40.25))
    assert CoreGraphics(lib, cf).pointer() == (120.5, 40.25)
    assert released == [1]


def test_button_down_maps_left_right_other_to_0_1_2():
    lib, cf, _ = fake_lib(down={0, 2})
    cg = CoreGraphics(lib, cf)
    assert (cg.button_down("left"), cg.button_down("right"), cg.button_down("other")) == (True, False, True)


def test_screen_recording_allowed_follows_the_preflight():
    lib, cf, _ = fake_lib(preflight=False)
    cg = CoreGraphics(lib, cf)
    assert cg.screen_recording_allowed() is False
    assert cg.request_screen_recording() is False


def test_screen_recording_allowed_is_none_when_the_symbol_is_missing():
    lib, cf, _ = fake_lib(symbols=False)
    cg = CoreGraphics(lib, cf)
    assert cg.screen_recording_allowed() is None and cg.request_screen_recording() is None


def test_a_missing_library_is_an_oserror(monkeypatch):
    monkeypatch.setattr(ctypes.util, "find_library", lambda name: None)
    with pytest.raises(OSError):
        CoreGraphics()


@pytest.mark.skipif(sys.platform != "darwin", reason="needs CoreGraphics")
def test_real_displays_have_a_positive_scale():
    displays = CoreGraphics().displays()
    assert displays and all(display.scale >= 1.0 for display in displays)
