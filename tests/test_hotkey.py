"""The global shortcut: its saved choice, the window wiring (with a fake registrar) and X11 against a display."""
import os
import sys

import pytest
from PySide6.QtWidgets import QApplication, QCheckBox

from anypoach.hotkey import X11Hotkey, remember_shortcut, shortcut_enabled
from anypoach.ui.app import MainWindow
from anypoach.ui.settings import SettingsDialog
from tests.test_ui_window import FakeController


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def data(tmp_path, monkeypatch):
    monkeypatch.setenv("ANYPOACH_DATA_DIR", str(tmp_path / "data"))


class FakeHotkey:
    def __init__(self, ok=True):
        self.ok, self.started, self.stopped, self.callback = ok, 0, 0, None

    def start(self, callback):
        self.started, self.callback = self.started + 1, callback
        return self.ok

    def stop(self):
        self.stopped += 1


def test_the_choice_is_off_by_default_and_remembered():
    assert not shortcut_enabled()
    remember_shortcut(True)
    assert shortcut_enabled()
    remember_shortcut(False)
    assert not shortcut_enabled()


def test_enabling_registers_once_and_the_chord_toggles_recording(app):
    hotkey, controller = FakeHotkey(), FakeController()
    window = MainWindow(controller, hotkey_factory=lambda: hotkey)
    assert window.set_global_shortcut(True) and shortcut_enabled() and hotkey.started == 1
    hotkey.callback()  # the registrar's thread calls this; Qt delivers it on the main thread
    app.processEvents()
    assert controller.calls[0][0] == "choose"  # not recording: it starts a full-screen recording
    controller.state = "recording"
    hotkey.callback()
    app.processEvents()
    assert controller.calls[-1] == "stop"
    assert window.set_global_shortcut(False) is False and hotkey.stopped >= 1 and not shortcut_enabled()


def test_a_refused_chord_stays_off_and_is_not_remembered(app):
    hotkey = FakeHotkey(ok=False)
    window = MainWindow(FakeController(), hotkey_factory=lambda: hotkey)
    assert window.set_global_shortcut(True) is False and hotkey.stopped == 1 and not shortcut_enabled()


def test_no_registrar_means_no_shortcut_and_no_checkbox(app, tmp_path):
    window = MainWindow(FakeController(), hotkey_factory=lambda: None)
    assert window.shortcut_available is False and window.set_global_shortcut(True) is False
    assert SettingsDialog(list, temp=tmp_path, cache=tmp_path).shortcut_box is None


def test_the_checkbox_reverts_when_the_shortcut_is_refused(app, tmp_path):
    dialog = SettingsDialog(list, temp=tmp_path, cache=tmp_path, shortcut=(False, lambda enabled: False))
    box = dialog.findChild(QCheckBox)
    box.setChecked(True)
    assert not box.isChecked() and "could not be registered" in dialog.update_label.text()


@pytest.mark.live
@pytest.mark.skipif(not os.environ.get("DISPLAY") or sys.platform != "linux", reason="needs an X display")
def test_x11_grabs_the_chord_and_releases_it_cleanly():
    first, second = X11Hotkey(), X11Hotkey()
    assert first.start(lambda: None) is True
    assert second.start(lambda: None) is False  # the chord is taken: refused, not a crash
    second.stop()
    first.stop()
    first.stop()
