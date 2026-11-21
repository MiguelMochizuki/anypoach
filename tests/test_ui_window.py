"""The Qt window and the area overlay, run offscreen."""
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

import numpy as np
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QIcon
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton, QSystemTrayIcon

from anypoach.capture.backend import Frame
from anypoach.capture.windows import WindowInfo
from anypoach.pointer.trace import Rect
from anypoach.ui.app import MainWindow, hide_from_capture, recording_icon
from anypoach.ui.frozen_selection import FrozenSelection
from anypoach.ui.selection import SelectionOverlay


class FakeController:
    supports_preview = False
    ready_to_record = True
    screen_access = True

    def __init__(self):
        self.state, self.message, self.calls = "idle", "", []
        self.palette, self.result, self.listed = [], None, []

    def windows(self):
        return self.listed

    def close(self):
        self.calls.append("close")

    def check_screen_access(self):
        return self.screen_access

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
    assert len(buttons) == 12 and all(b.accessibleName() for b in buttons)
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


def test_recording_icon_is_never_null(app, monkeypatch):
    monkeypatch.setattr(QIcon, "fromTheme", staticmethod(lambda name: QIcon()))  # macOS and Windows have no theme
    icon = recording_icon()
    assert not icon.isNull() and not icon.pixmap(22, 22).isNull()


class PreviewController(FakeController):
    """A controller whose backend needs a preview frame, like the Wayland portal."""
    supports_preview = True

    def __init__(self, failure=""):
        super().__init__()
        self.failure, self.closed = failure, 0

    def preview(self, window=False):
        self.calls.append(("preview", window))
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


def test_a_denied_permission_keeps_the_window_where_it_is_and_says_why(app):
    controller = FakeController()
    controller.screen_access = False
    controller.message = "AnyPoach needs Screen Recording permission."
    window = MainWindow(controller)
    window.show()
    window.record_button.click()
    QTest.qWait(300)
    assert controller.calls == [] and window.isVisible() and not window.isMinimized()
    assert "Screen Recording" in window.status.text()


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


class FakeBridge:
    """Stands in for BridgeController: a code, a status, and calls to record."""

    def __init__(self, status="listening"):
        self.code, self.status, self.calls = "AAAA-1111", status, []

    def rotate(self):
        self.code = "BBBB-2222"
        self.calls.append("rotate")
        return self.code

    def stop(self):
        self.calls.append("stop")


def test_the_chrome_section_shows_the_code_and_every_control_is_named(app):
    window = MainWindow(FakeController(), FakeBridge())
    assert window.code_field.text() == "AAAA-1111" and window.code_field.isReadOnly()
    names = {b.accessibleName() for b in window.findChildren(QPushButton)}
    assert {"Copy pairing code", "Create a new pairing code", "Open the extension folder"} <= names
    assert window.code_field.accessibleName() == "Pairing code" and window.chrome_status.accessibleName() == "Chrome status"


def test_copy_and_rotate_the_pairing_code(app):
    bridge = FakeBridge()
    window = MainWindow(FakeController(), bridge)
    window.copy_code_button.click()
    assert QApplication.clipboard().text() == "AAAA-1111"
    window.new_code_button.click()
    assert window.code_field.text() == "BBBB-2222" and bridge.calls == ["rotate"]


def test_a_port_error_is_visible_and_recording_still_works(app):
    controller = FakeController()
    window = MainWindow(controller, FakeBridge("error: Port 47832 is already in use"))
    assert "47832" in window.chrome_status.text()
    assert window.record_button.isEnabled()


def test_open_the_extension_folder(app, monkeypatch, tmp_path):
    opened = []
    monkeypatch.setattr("anypoach.ui.app.extension_dir", lambda: tmp_path)
    monkeypatch.setattr("anypoach.ui.app.QDesktopServices.openUrl", lambda url: opened.append(Path(url.toLocalFile())) or True)
    window = MainWindow(FakeController(), FakeBridge())
    window.open_extension_button.click()
    assert opened == [tmp_path]
    monkeypatch.setattr("anypoach.ui.app.extension_dir", lambda: tmp_path / "missing")
    window.open_extension_button.click()
    assert "not found" in window.chrome_status.text() and len(opened) == 1


def test_closing_the_window_stops_the_bridge(app):
    bridge = FakeBridge()
    window = MainWindow(FakeController(), bridge)
    window.close()
    assert "stop" in bridge.calls


def test_without_a_bridge_there_is_no_chrome_section(app):
    window = MainWindow(FakeController())
    assert not hasattr(window, "code_field")


class ReviewController(FakeController):
    """A controller whose stop returns a real analysis, with the comment methods the review panel uses."""

    def __init__(self, result):
        super().__init__()
        self.result, self.context, self._comments = result, "", []

    @property
    def comments(self):
        return list(self._comments)

    def add_comment(self, time_ms, text):
        self._comments.append({"timeMs": time_ms, "text": text})
        return True

    def remove_comment(self, index):
        del self._comments[index]

    def stop(self):
        super().stop()
        return self.result


@pytest.fixture
def endless(monkeypatch):
    """Decoding that never finishes on its own, so a test can check that it is stopped."""
    import time

    from anypoach.analysis.proxy import FrameProxy

    def build(path, *, cancel, on_frame=None, **_):
        while not cancel.is_set():
            time.sleep(0.01)
        return FrameProxy(2000)

    monkeypatch.setattr("anypoach.ui.review.build_proxy", build)


@pytest.fixture(scope="module")
def clip_result(clips, tmp_path_factory):
    from anypoach.analysis.inspect import inspect_video
    return inspect_video(clips["motion"], output_dir=tmp_path_factory.mktemp("window-frames"))


def test_the_review_panel_appears_after_a_stop_with_a_result(app, clip_result, endless):
    window = MainWindow(ReviewController(clip_result))
    window.record_button.click()
    QTest.qWait(200)
    window.stop_button.click()
    assert window.review is not None and window.review.isAncestorOf(window.review.timeline)
    assert window.review.timeline.accessibleName() == "Timeline"
    window.close()


def test_starting_a_new_recording_stops_the_decoding_and_clears_the_panel(app, clip_result, endless):
    window = MainWindow(ReviewController(clip_result))
    window.record_button.click()
    QTest.qWait(200)
    window.stop_button.click()
    worker = window.review._thread
    assert worker.is_alive()
    window.record_button.click()
    assert window.review is None and not worker.is_alive()
    window.close()


def test_closing_the_window_stops_the_decoding(app, clip_result, endless):
    window = MainWindow(ReviewController(clip_result))
    window.record_button.click()
    QTest.qWait(200)
    window.stop_button.click()
    worker = window.review._thread
    window.close()
    assert window.review is None and not worker.is_alive()


def test_copying_the_prompt_works_while_the_frames_are_still_being_prepared(app, clip_result, endless):
    controller = ReviewController(clip_result)
    window = MainWindow(controller)
    window.record_button.click()
    QTest.qWait(200)
    window.stop_button.click()
    assert window.review is not None and not window.review.proxy.frames
    window.copy_button.click()
    assert controller.calls[-1] == "copy" and "copied" in window.status.text().lower()
    window.close()


def test_full_screen_selects_the_whole_screen_in_physical_pixels(app):
    controller = FakeController()
    window = MainWindow(controller)
    window.full_screen.click()
    screen = app.primaryScreen()
    geometry, dpr = screen.geometry(), screen.devicePixelRatio()
    name, region, scale = controller.calls[-1]
    assert (name, scale) == ("choose", dpr)
    assert (region.width, region.height) == (geometry.width() * dpr, geometry.height() * dpr)


def test_full_screen_on_a_preview_backend_uses_the_whole_frame_and_no_scale(app):
    controller = PreviewController()
    window = MainWindow(controller)
    window.full_screen.click()
    assert controller.calls[-1] == ("choose", Rect(0, 0, 20, 10), None)


def test_a_failed_preview_keeps_full_screen_unselected(app):
    controller = PreviewController("Screen sharing was cancelled.")
    window = MainWindow(controller)
    window.full_screen.click()
    assert not [c for c in controller.calls if c[0] == "choose"] and "cancelled" in window.status.text()


def test_the_tray_menu_records_the_full_screen_and_swaps_menus_while_recording(app, monkeypatch):
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", lambda: True)
    controller = FakeController()
    window = MainWindow(controller)
    assert window._tray is not None and window._tray.contextMenu() is window._tray_idle_menu
    window._record_full_screen()
    assert controller.calls[0][0] == "choose"
    window._tray_state(True)
    assert window._tray.contextMenu() is window._tray_recording_menu
    window._return_to_screen()
    assert window._tray.contextMenu() is window._tray_idle_menu


def test_without_a_tray_there_is_no_tray_object(app, monkeypatch):
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", lambda: False)
    assert MainWindow(FakeController())._tray is None


def test_window_on_a_preview_backend_asks_for_a_window_and_takes_the_whole_stream(app):
    controller = PreviewController()
    window = MainWindow(controller)
    window.window_button.click()
    assert ("preview", True) in controller.calls and controller.calls[-1] == ("choose", Rect(0, 0, 20, 10), None)


def test_window_lists_the_windows_but_not_anypoach_and_selects_the_picked_bounds(app, monkeypatch):
    controller = FakeController()
    controller.listed = [WindowInfo("AnyPoach", Rect(0, 0, 300, 200)), WindowInfo("Editor", Rect(50, 60, 800, 600))]
    seen = {}
    monkeypatch.setattr("anypoach.ui.app.QInputDialog.getItem",
                        lambda parent, title, label, items, *a: seen.update(items=items) or ("Editor", True))
    window = MainWindow(controller)
    window.window_button.click()
    assert seen["items"] == ["Editor"] and controller.calls[-1][:2] == ("choose", Rect(50, 60, 800, 600))


def test_window_with_nothing_to_list_leaves_the_selection_alone(app):
    controller = FakeController()
    window = MainWindow(controller)
    window.window_button.click()
    assert not [c for c in controller.calls if c[0] == "choose"]
