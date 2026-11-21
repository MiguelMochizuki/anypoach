"""The window lister's contract, and the X11 one against a real display when there is one."""
import os
import sys

import pytest

from anypoach.capture.windows import MIN_SIZE, WindowInfo, X11Windows, default_windows
from anypoach.pointer.trace import Rect


def test_a_window_is_a_title_and_bounds():
    assert WindowInfo("Editor", Rect(1, 2, 3, 4)).rect.width == 3 and MIN_SIZE == 50


def test_no_lister_without_an_x_display_or_libx11(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr("ctypes.util.find_library", lambda name: None)
    assert default_windows() is None


@pytest.mark.live
@pytest.mark.skipif(not os.environ.get("DISPLAY") or sys.platform != "linux", reason="needs an X display")
def test_x11_lists_without_failing_and_every_window_is_big_enough_and_titled():
    for window in X11Windows().windows():
        assert window.title and window.rect.width >= MIN_SIZE and window.rect.height >= MIN_SIZE
