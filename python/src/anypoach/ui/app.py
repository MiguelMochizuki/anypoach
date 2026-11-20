"""Minimal Poach window: choose an area, record, stop, see the keyframes, copy the assistant prompt."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QIcon, QKeyEvent
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QPushButton,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from anypoach.brief.paths import cache_dir
from anypoach.capture.mss_backend import MssBackend
from anypoach.pointer import default_source
from anypoach.tempdirs import make_temp_dir

from .controller import Controller
from .selection import SelectionOverlay

MAX_RECORDING_MS = 30_000  # the analysis only reads the first 30 s


def hide_from_capture(window: QWidget) -> bool:
    """Windows: ask the OS to leave the window out of any screen capture. Elsewhere there is no such flag; the
    caller hides the window while recording instead. Returns whether the OS-level exclusion was applied."""
    if sys.platform != "win32":
        return False
    import ctypes
    WDA_EXCLUDEFROMCAPTURE = 0x11  # Windows 10 2004+; older builds reject it and the window stays capturable
    return bool(ctypes.windll.user32.SetWindowDisplayAffinity(int(window.winId()), WDA_EXCLUDEFROMCAPTURE))  # type: ignore[attr-defined]


class MainWindow(QMainWindow):
    def __init__(self, controller: Controller) -> None:
        super().__init__()
        self.controller = controller
        self.setWindowTitle("AnyPoach")
        self._tray: QSystemTrayIcon | None = None
        self._limit = QTimer(self, singleShot=True, interval=MAX_RECORDING_MS)
        self._limit.timeout.connect(self._stop)
        self.area, self.record_button = self._button("Choose area", self._choose), self._button("Record", self._record)
        self.stop_button, self.copy_button = self._button("Stop", self._stop), self._button("Copy prompt for assistant", self._copy)
        self.status = QLabel("Choose an area, then record.")
        self.status.setAccessibleName("Status")
        self.frames = QListWidget()
        self.frames.setViewMode(QListWidget.ViewMode.IconMode)
        self.frames.setIconSize(QSize(160, 100))
        self.frames.setAccessibleName("Keyframes")
        buttons = QHBoxLayout()
        for button in (self.area, self.record_button, self.stop_button, self.copy_button):
            buttons.addWidget(button)
        body = QVBoxLayout()
        body.addLayout(buttons)
        body.addWidget(self.status)
        body.addWidget(self.frames)
        root = QWidget()
        root.setLayout(body)
        self.setCentralWidget(root)
        self._refresh()
        hide_from_capture(self)

    def _button(self, text: str, slot) -> QPushButton:
        button = QPushButton(text)
        button.setAccessibleName(text)
        button.clicked.connect(slot)
        return button

    def keyPressEvent(self, event: QKeyEvent) -> None:  # Enter activates the focused button; Tab moves between them
        focus = self.focusWidget()
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and isinstance(focus, QPushButton):
            focus.click()
        else:
            super().keyPressEvent(event)

    def _refresh(self) -> None:
        state = self.controller.state
        self.area.setEnabled(state != "recording")
        self.record_button.setEnabled(state != "recording")
        self.stop_button.setEnabled(state == "recording")
        self.copy_button.setEnabled(state == "ready")
        if self.controller.message:
            self.status.setText(self.controller.message)

    def _choose(self) -> None:
        self.hide()
        overlay = SelectionOverlay(QApplication.screenAt(self.pos()) or QApplication.primaryScreen())
        overlay.selected.connect(self._chosen)
        overlay.cancelled.connect(self.show)
        self._overlay = overlay
        overlay.showFullScreen()
        overlay.setFocus()

    def _chosen(self, region) -> None:
        self.controller.choose_region(region)
        self.status.setText("Area selected." if not self.controller.message else self.controller.message)
        self.show()
        self._refresh()

    def _record(self) -> None:
        self.controller.start()
        if self.controller.state == "recording":
            self.status.setText("Recording…")
            self._limit.start()
            self._leave_the_screen()
        self._refresh()

    def _leave_the_screen(self) -> None:
        # Without an OS-level exclusion the window would show up in the video, so hide it; a tray menu stops the recording.
        if sys.platform == "win32" or not QSystemTrayIcon.isSystemTrayAvailable():
            return
        tray = QSystemTrayIcon(QIcon.fromTheme("media-record"), self)
        menu = QMenu()
        menu.addAction("Stop recording", self._stop)
        tray.setContextMenu(menu)
        tray.setToolTip("Poach is recording")
        tray.show()
        self._tray = tray
        self.hide()

    def _stop(self) -> None:
        self._limit.stop()
        if self._tray is not None:
            self._tray.hide()
            self._tray = None
        result = self.controller.stop()
        self.show()
        self.frames.clear()
        if result is not None:
            for key in result.keyframes:
                item = QListWidgetItem(QIcon(key.image_path), f"{key.kind} · {key.time_ms} ms")
                self.frames.addItem(item)
            self.status.setText(f"Recorded {result.duration_ms} ms. Copy the prompt and paste it to your assistant.")
        self._refresh()

    def _copy(self) -> None:
        prompt = self.controller.copy_handoff()
        if prompt:
            QApplication.clipboard().setText(prompt)
            self.status.setText("Prompt copied. Paste it to your assistant.")
        self._refresh()


def main() -> int:
    app = QApplication(sys.argv)
    work = make_temp_dir("Poach-")
    controller = Controller(MssBackend(), default_source(), Path(work), cache=cache_dir())
    window = MainWindow(controller)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
