"""Minimal AnyPoach window: choose an area, record, stop, see the keyframes, copy the assistant prompt."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QKeyEvent, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QPushButton,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from anypoach.bridge.control import BridgeController, extension_dir
from anypoach.bridge.evidence import EvidenceStore
from anypoach.brief.paths import cache_dir
from anypoach.capture.default import default_backend
from anypoach.macos import macos_screen_access
from anypoach.pointer import default_source
from anypoach.pointer.trace import Rect
from anypoach.tempdirs import make_temp_dir

from .controller import Controller, physical_rect
from .frozen_selection import FrozenSelection
from .review import ReviewPanel
from .selection import SelectionOverlay

MAX_RECORDING_MS = 30_000  # the analysis only reads the first 30 s
LEAVE_SCREEN_MS = 500  # time for the compositor to take the window off the screen before capture starts


def recording_icon() -> QIcon:
    """The tray icon while recording: the theme's `media-record`, or a red dot where the theme has none (macOS,
    Windows), because a blank menu-bar item leaves no visible way to stop the recording."""
    icon = QIcon.fromTheme("media-record")
    if not icon.isNull():
        return icon
    pixmap = QPixmap(44, 44)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor("#e5322d"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(6, 6, 32, 32)
    painter.end()
    return QIcon(pixmap)


def hide_from_capture(window: QWidget) -> bool:
    """Windows: ask the OS to leave the window out of any screen capture. Elsewhere there is no such flag; the
    caller hides the window while recording instead. Returns whether the OS-level exclusion was applied."""
    if sys.platform != "win32":
        return False
    import ctypes
    WDA_EXCLUDEFROMCAPTURE = 0x11  # Windows 10 2004+; older builds reject it and the window stays capturable
    return bool(ctypes.windll.user32.SetWindowDisplayAffinity(int(window.winId()), WDA_EXCLUDEFROMCAPTURE))  # type: ignore[attr-defined]


class MainWindow(QMainWindow):
    """The AnyPoach window: choose an area, record, stop, see the keyframes, copy the assistant prompt.

    It only presents state and forwards clicks; the flow itself lives in `Controller`. Enter activates the
    focused button, and every control has an accessible name.

    Args:
        controller: The flow this window drives.
    """
    def __init__(self, controller: Controller, bridge: BridgeController | None = None) -> None:
        super().__init__()
        self.controller = controller
        self._bridge = bridge
        self._device_scale: float | None = None
        self.setWindowTitle("AnyPoach")
        self._tray: QSystemTrayIcon | None = None
        self._limit = QTimer(self, singleShot=True, interval=MAX_RECORDING_MS)
        self._limit.timeout.connect(self._stop)
        self.area, self.record_button = self._button("Choose area", self._choose), self._button("Record", self._record)
        self.full_screen = self._button("Full screen", self._choose_full_screen)
        self.stop_button, self.copy_button = self._button("Stop", self._stop), self._button("Copy prompt for assistant", self._copy)
        self.status = QLabel("Choose an area, then record.")
        self.status.setAccessibleName("Status")
        self.frames = QListWidget()
        self.frames.setViewMode(QListWidget.ViewMode.IconMode)
        self.frames.setIconSize(QSize(160, 100))
        self.frames.setAccessibleName("Keyframes")
        buttons = QHBoxLayout()
        for button in (self.area, self.full_screen, self.record_button, self.stop_button, self.copy_button):
            buttons.addWidget(button)
        body = QVBoxLayout()
        body.addLayout(buttons)
        body.addWidget(self.status)
        body.addWidget(self.frames)
        self._body, self.review = body, None
        if bridge is not None:
            body.addWidget(self._chrome_group(bridge))
        root = QWidget()
        root.setLayout(body)
        self.setCentralWidget(root)
        self._refresh()
        hide_from_capture(self)

    def _chrome_group(self, bridge: BridgeController) -> QGroupBox:
        group = QGroupBox("Chrome")
        group.setAccessibleName("Chrome companion")
        self.code_field = QLineEdit(bridge.code)
        self.code_field.setReadOnly(True)
        self.code_field.setAccessibleName("Pairing code")
        self.copy_code_button = self._button("Copy pairing code", self._copy_code)
        self.new_code_button = self._button("Create a new pairing code", self._new_code)
        self.open_extension_button = self._button("Open the extension folder", self._open_extension)
        self.chrome_status = QLabel()
        self.chrome_status.setAccessibleName("Chrome status")
        row = QHBoxLayout()
        for widget in (self.code_field, self.copy_code_button, self.new_code_button, self.open_extension_button):
            row.addWidget(widget)
        layout = QVBoxLayout(group)
        layout.addLayout(row)
        layout.addWidget(self.chrome_status)
        self._chrome_note, self._note_ticks = "", 0
        self._chrome_timer = QTimer(self, interval=1000)
        self._chrome_timer.timeout.connect(self._tick_chrome)
        self._chrome_timer.start()
        self._refresh_chrome()
        return group

    def _tick_chrome(self) -> None:
        """Refresh once a second and let a one-off note (copied, new code) fade after about five seconds."""
        self._note_ticks += 1
        if self._note_ticks >= 5:
            self._chrome_note = ""
        self._refresh_chrome()

    def _refresh_chrome(self) -> None:
        status = self._bridge.status
        text = {"listening": "Waiting for Chrome. Pair the extension with this code.",
                "stopped": "The Chrome connection is off."}.get(status, status)
        browser = getattr(self.controller, "browser_status", "off")
        if status == "listening" and browser == "receiving":
            text = "Receiving a session from Chrome."
        elif status == "listening" and browser == "attached":
            text = "A Chrome session matches this recording and will be included."
        self.chrome_status.setText(self._chrome_note or text)

    def _copy_code(self) -> None:
        QApplication.clipboard().setText(self._bridge.code)
        self._chrome_note, self._note_ticks = "Pairing code copied.", 0
        self._refresh_chrome()

    def _new_code(self) -> None:
        self.code_field.setText(self._bridge.rotate())
        self._chrome_note, self._note_ticks = "New pairing code. Pair the extension again.", 0
        self._refresh_chrome()

    def _open_extension(self) -> None:
        folder = extension_dir()
        if not folder.is_dir():
            self._chrome_note, self._note_ticks = "The extension folder was not found in this installation.", 0
        elif QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder))):
            self._chrome_note, self._note_ticks = "Load this folder in Chrome from chrome://extensions with Developer mode on.", 0
        else:
            self._chrome_note, self._note_ticks = f"Could not open the folder. It is at {folder}.", 0
        self._refresh_chrome()

    def _button(self, text: str, slot) -> QPushButton:
        button = QPushButton(text)
        button.setAccessibleName(text)
        button.clicked.connect(slot)
        return button

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Let Enter or Return click the focused button (Tab already moves between them); other keys behave as usual."""
        focus = self.focusWidget()
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and isinstance(focus, QPushButton):
            focus.click()
        else:
            super().keyPressEvent(event)

    def _refresh(self) -> None:
        state = self.controller.state
        self.area.setEnabled(state != "recording")
        self.full_screen.setEnabled(state != "recording")
        self.record_button.setEnabled(state != "recording")
        self.stop_button.setEnabled(state == "recording")
        self.copy_button.setEnabled(state == "ready")
        if self.controller.message:
            self.status.setText(self.controller.message)

    def _choose(self) -> None:
        self.hide()
        if self.controller.supports_preview:  # Wayland: no overlay can sit over the screen, so pick on a frozen frame
            frame = self.controller.preview()
            if frame is None:
                self.show()
                self._refresh()
                return
            self._device_scale = None  # the portal reports the stream size only, not the screen scale
            overlay = FrozenSelection(frame)
            overlay.cancelled.connect(self._selection_cancelled)
        else:
            screen = QApplication.screenAt(self.pos()) or QApplication.primaryScreen()
            self._device_scale = screen.devicePixelRatio()
            overlay = SelectionOverlay(screen)
            overlay.cancelled.connect(self.show)
        overlay.selected.connect(self._chosen)
        self._overlay = overlay
        overlay.showFullScreen()
        overlay.setFocus()

    def _choose_full_screen(self) -> None:
        """Select the whole screen the window is on (on a portal session, the whole shared stream)."""
        if self.controller.supports_preview:
            frame = self.controller.preview()
            if frame is None:
                self._refresh()
                return
            self._device_scale = None
            height, width = frame.pixels.shape[:2]
            self._chosen(Rect(0, 0, width, height))
            return
        screen = QApplication.screenAt(self.pos()) or QApplication.primaryScreen()
        self._device_scale, geometry = screen.devicePixelRatio(), screen.geometry()
        self._chosen(Rect(*physical_rect((0, 0), (geometry.width(), geometry.height()),
                                         origin=(geometry.x(), geometry.y()), dpr=self._device_scale)))

    def _selection_cancelled(self) -> None:
        self.controller.close()  # ends the portal session so the compositor stops showing that it is sharing
        self.show()

    def closeEvent(self, event) -> None:
        """Release the capture backend (closing any portal session) and the Chrome server before the window goes away."""
        self._close_review()
        self.controller.close()
        if self._bridge is not None:
            self._bridge.stop()
        super().closeEvent(event)

    def _chosen(self, region) -> None:
        self.controller.choose_region(region, self._device_scale)
        self.status.setText("Area selected." if not self.controller.message else self.controller.message)
        self.show()
        self._refresh()

    def _record(self) -> None:
        if not self.controller.ready_to_record:
            self.controller.start()  # only sets the reason (no area chosen, already recording); nothing to hide
            self._refresh()
            return
        if not self.controller.check_screen_access():  # before the window hides: nothing to bring back
            self._refresh()
            return
        self._close_review()  # stops decoding the previous recording before a new one starts
        self.record_button.setEnabled(False)
        self._leave_the_screen()  # first, so the window is not in the first frames of the video
        QTimer.singleShot(0 if sys.platform == "win32" else LEAVE_SCREEN_MS, self._begin_recording)

    def _begin_recording(self) -> None:
        self.controller.start()
        if self.controller.state == "recording":
            self.status.setText("Recording…")
            self._limit.start()
        else:
            self._return_to_screen()
        self._refresh()

    def _return_to_screen(self) -> None:
        if self._tray is not None:
            self._tray.hide()
            self._tray = None
        self.showNormal()

    def _leave_the_screen(self) -> None:
        # Without an OS-level exclusion the window would show up in the video, so hide it; a tray menu stops the recording.
        if sys.platform == "win32":
            return
        if not QSystemTrayIcon.isSystemTrayAvailable():  # e.g. GNOME: minimize, and restore the window to stop
            self.showMinimized()
            return
        tray = QSystemTrayIcon(recording_icon(), self)
        menu = QMenu()
        menu.addAction("Stop recording", self._stop)
        tray.setContextMenu(menu)
        tray.setToolTip("AnyPoach is recording")
        tray.show()
        self._tray = tray
        self.hide()

    def _stop(self) -> None:
        self._limit.stop()
        result = self.controller.stop()
        self._return_to_screen()
        self.frames.clear()
        if result is not None:
            for key in result.keyframes:
                item = QListWidgetItem(QIcon(key.image_path), f"{key.kind} · {key.time_ms} ms")
                self.frames.addItem(item)
            self.status.setText(f"Recorded {result.duration_ms} ms. Copy the prompt and paste it to your assistant.")
            self._show_review(result)
        self._refresh()

    def _show_review(self, result) -> None:
        """Open the review panel for a video result; the keyframes stay as they are if the video cannot be read."""
        self._close_review()
        if result.media_type != "video" or not result.source_path:
            return
        try:
            panel = ReviewPanel(self.controller, result)
        except (ValueError, OSError):
            return
        self._body.insertWidget(self._body.indexOf(self.frames) + 1, panel)
        self.review = panel

    def _close_review(self) -> None:
        if self.review is not None:
            self.review.shutdown()
            self._body.removeWidget(self.review)
            self.review.deleteLater()
            self.review = None

    def _copy(self) -> None:
        prompt = self.controller.copy_handoff()
        if prompt:
            QApplication.clipboard().setText(prompt)
            self.status.setText("Prompt copied. Paste it to your assistant.")
        self._refresh()


def main() -> int:
    """Start the AnyPoach window and return the Qt exit code. This is the `anypoach` command."""
    app = QApplication(sys.argv)
    work = make_temp_dir()
    store = EvidenceStore()
    bridge = BridgeController(store, cache=cache_dir())
    bridge.start()
    screen_access = macos_screen_access() if sys.platform == "darwin" else None
    controller = Controller(default_backend(), default_source(), Path(work), cache=cache_dir(), store=store,
                            screen_access=screen_access)
    window = MainWindow(controller, bridge)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
