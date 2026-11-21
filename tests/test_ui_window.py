"""The Qt window and the area overlay, run offscreen."""
import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

import numpy as np
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton, QSystemTrayIcon

from anypoach.capture.backend import Frame
from anypoach.pointer.trace import Rect
from anypoach.ui.app import MainWindow, hide_from_capture
from anypoach.ui.frozen_selection import FrozenSelection
from anypoach.ui.selection import SelectionOverlay


class FakeController:
    supports_preview = False
    ready_to_record = True

    def __init__(self):
        self.state, self.message, self.calls = "idle", "", []

    def close(self):
        self.calls.append("close")

    def choose_region(self, region, device_scale=None):
        self.calls.append(("choose", region, device_scale))

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


@pytest.fixture(autouse=True)
def short_leave_delay(monkeypatch):
    monkeypatch.setattr("anypoach.ui.app.LEAVE_SCREEN_MS", 60)


def test_every_button_has_an_accessible_name_and_state_follows_the_controller(app):
    controller = FakeController()
    window = MainWindow(controller)
    buttons = window.findChildren(QPushButton)
    assert len(buttons) == 4 and all(b.accessibleName() for b in buttons)
    assert (window.stop_button.isEnabled(), window.copy_button.isEnabled()) == (False, False)
    window.record_button.click()
    QTest.qWait(300)
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
    QTest.qWait(300)
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


class PreviewController(FakeController):
    """A controller whose backend needs a preview frame, like the Wayland portal."""
    supports_preview = True

    def __init__(self, failure=""):
        super().__init__()
        self.failure, self.closed = failure, 0

    def preview(self):
        if self.failure:
            self.message = self.failure
            return None
        return Frame(np.zeros((10, 20, 4), np.uint8), 0.0)

    def close(self):
        self.closed += 1


def test_choosing_an_area_on_a_preview_backend_shows_the_frozen_selection(app):
    window = MainWindow(PreviewController())
    window._choose()
    assert isinstance(window._overlay, FrozenSelection)
    window._overlay.close()


def test_a_failed_preview_shows_the_message_and_keeps_the_window(app):
    window = MainWindow(PreviewController("Screen sharing was cancelled."))
    window.show()
    window._choose()
    assert window.isVisible() and "cancelled" in window.status.text()


def test_cancelling_the_frozen_selection_closes_the_portal_session(app):
    controller = PreviewController()
    window = MainWindow(controller)
    window.show()
    window._choose()
    window._overlay.cancelled.emit()
    assert controller.closed == 1 and window.isVisible()


@pytest.mark.skipif(sys.platform == "win32", reason="Windows excludes the window from capture instead")
def test_without_a_tray_the_window_minimizes_while_recording(app, monkeypatch):
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", lambda: False)
    window = MainWindow(FakeController())
    window.show()
    window._leave_the_screen()
    assert window.isMinimized()


def test_closing_the_window_releases_the_backend(app):
    controller = PreviewController()
    window = MainWindow(controller)
    window.show()
    window.close()
    assert controller.closed >= 1


@pytest.mark.skipif(sys.platform == "win32", reason="Windows excludes the window from capture and starts at once")
def test_recording_starts_only_after_the_window_has_left_the_screen(app, monkeypatch):
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", lambda: False)
    controller = FakeController()
    window = MainWindow(controller)
    window.show()
    window.record_button.click()
    assert controller.calls == [] and window.isMinimized()  # the window goes first, so it is not in the video
    QTest.qWait(300)
    assert controller.calls == ["start"]


def test_record_without_an_area_keeps_the_window_where_it_is(app):
    controller = FakeController()
    controller.ready_to_record = False
    window = MainWindow(controller)
    window.show()
    window.record_button.click()
    assert controller.calls == ["start"] and window.isVisible() and not window.isMinimized()


def test_a_start_that_fails_brings_the_window_back(app, monkeypatch):
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", lambda: False)
    controller = FakeController()
    controller.start = lambda: setattr(controller, "message", "Could not start recording: gone")
    window = MainWindow(controller)
    window.show()
    window.record_button.click()
    QTest.qWait(300)
    assert not window.isMinimized() and "Could not start" in window.status.text()


def test_the_overlay_screen_scale_is_passed_to_the_controller(app):
    controller = FakeController()
    window = MainWindow(controller)
    window._choose()
    window._overlay.close()
    window._chosen(Rect(0, 0, 40, 40))
    assert controller.calls[-1] == ("choose", Rect(0, 0, 40, 40), app.primaryScreen().devicePixelRatio())


def test_a_preview_backend_passes_no_scale(app):
    controller = PreviewController()
    window = MainWindow(controller)
    window._choose()
    window._overlay.close()
    window._chosen(Rect(0, 0, 40, 40))
    assert controller.calls[-1] == ("choose", Rect(0, 0, 40, 40), None)
