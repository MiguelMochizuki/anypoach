"""The Qt window and the area overlay, run offscreen."""
import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton

from anypoach.pointer.trace import Rect
from anypoach.ui.app import MainWindow, hide_from_capture
from anypoach.ui.selection import SelectionOverlay


class FakeController:
    def __init__(self):
        self.state, self.message, self.calls = "idle", "", []

    def choose_region(self, region):
        self.calls.append(("choose", region))

    def start(self):
        self.calls.append("start")
        self.state = "recording"

    def stop(self):
        self.calls.append("stop")
        self.state = "ready"

    def copy_handoff(self):
        self.calls.append("copy")
        return "the prompt"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_every_button_has_an_accessible_name_and_state_follows_the_controller(app):
    controller = FakeController()
    window = MainWindow(controller)
    buttons = window.findChildren(QPushButton)
    assert len(buttons) == 4 and all(b.accessibleName() for b in buttons)
    assert (window.stop_button.isEnabled(), window.copy_button.isEnabled()) == (False, False)
    window.record_button.click()
    assert controller.calls == ["start"] and window.stop_button.isEnabled() and not window.record_button.isEnabled()
    window.stop_button.click()
    assert controller.calls[-1] == "stop" and window.copy_button.isEnabled()
    window.copy_button.click()
    assert app.clipboard().text() == "the prompt"


def test_enter_activates_the_focused_button(app):
    controller = FakeController()
    window = MainWindow(controller)
    window.show()
    window.record_button.setFocus()
    QTest.keyClick(window, Qt.Key.Key_Return)
    assert controller.calls == ["start"]


def test_overlay_reports_the_dragged_area_in_physical_pixels_and_esc_cancels(app):
    screen = app.primaryScreen()
    overlay, chosen, cancelled = SelectionOverlay(screen), [], []
    overlay.selected.connect(chosen.append)
    overlay.cancelled.connect(lambda: cancelled.append(True))
    overlay.show()
    QTest.mousePress(overlay, Qt.MouseButton.LeftButton, pos=QPoint(10, 20))
    QTest.mouseMove(overlay, QPoint(60, 50))
    QTest.mouseRelease(overlay, Qt.MouseButton.LeftButton, pos=QPoint(60, 50))
    dpr, origin = screen.devicePixelRatio(), screen.geometry().topLeft()
    assert chosen == [Rect((origin.x() + 10) * dpr, (origin.y() + 20) * dpr, 50 * dpr, 30 * dpr)]
    second = SelectionOverlay(screen)
    second.cancelled.connect(lambda: cancelled.append(True))
    second.show()
    QTest.keyClick(second, Qt.Key.Key_Escape)
    assert cancelled == [True]


@pytest.mark.skipif(sys.platform == "win32", reason="the exclusion flag exists only on Windows")
def test_hide_from_capture_is_a_no_op_outside_windows(app):
    assert hide_from_capture(MainWindow(FakeController())) is False
