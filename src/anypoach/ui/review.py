"""The review panel: watch the recording frame by frame, pin comments to moments, write general instructions."""
from __future__ import annotations

import threading
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QFont, QKeyEvent, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from anypoach.analysis.proxy import PROXY_RATE, FrameProxy, ProxyFrame, build_proxy
from anypoach.analysis.source import VideoSource

from .timeline import TimelineWidget


class _Frames(QObject):
    """Carries frames from the decoding thread to the GUI thread (Qt queues the signal across threads)."""
    ready = Signal(object)
    finished = Signal(bool)


class ReviewPanel(QWidget):
    """Shows the frames of a recording, plays them, and keeps comments and instructions in the controller.

    The frames come from `build_proxy` on a background thread, so the panel opens at once and fills in. Every
    comment is pinned to the time of a frame, which `anypoach_read_moment` resolves to that same frame.

    Args:
        controller: Holds the comments (`add_comment`, `remove_comment`, `comments`) and `context`.
        result: The analysis of the recording; its `source_path` is decoded and its `segments` drawn.
        start: Begin decoding at once; tests pass False to control when frames arrive.
        frame_interval_ms: Time between frames while playing.
        highlight_ms: How long a visited comment stays highlighted.

    Attributes:
        proxy: The frames received so far.
        playhead_ms: Time of the frame being shown.
    """
    def __init__(self, controller: Any, result: Any, *, start: bool = True, frame_interval_ms: int = round(1000 / PROXY_RATE),
                 highlight_ms: int = 3000) -> None:
        super().__init__()
        self._controller, self._path, self._highlight_ms = controller, result.source_path, highlight_ms
        with VideoSource(self._path) as source:
            duration_ms = round(source.duration_s * 1000)
        self.proxy = FrameProxy(duration_ms)
        self.playhead_ms = 0
        self._cancel, self._thread, self._frames = threading.Event(), None, _Frames()
        self._frames.ready.connect(self._on_frame)
        self._frames.finished.connect(self._on_finished)
        self._highlighted = -1

        self.frame_label = QLabel("Preparing frames…")
        self.frame_label.setAccessibleName("Recording frame")
        self.frame_label.setMinimumSize(320, 180)
        self.timeline = TimelineWidget()
        self.timeline.set_duration(duration_ms)
        self.timeline.set_segments([(s.start_ms, s.end_ms) for s in (result.segments or [])])
        self.timeline.position_requested.connect(self.seek)
        self.timeline.marker_activated.connect(lambda indices: self.visit(indices[0]))
        self.play_button = self._button("Play", self.toggle_play)
        self.comment_field = QLineEdit()
        self.comment_field.setAccessibleName("Comment")
        self.comment_field.setPlaceholderText("What happens at this moment?")
        self.comment_field.returnPressed.connect(self.add_comment)
        self.add_button = self._button("Comment at this moment", self.add_comment)
        self.add_button.setEnabled(False)
        self.remove_button = self._button("Remove comment", self.remove_comment)
        self.comment_list = QListWidget()
        self.comment_list.setAccessibleName("Comments")
        self.comment_list.itemActivated.connect(lambda item: self.visit(self.comment_list.row(item)))
        self.comment_list.itemClicked.connect(lambda item: self.visit(self.comment_list.row(item)))
        self.instructions = QPlainTextEdit(controller.context)
        self.instructions.setAccessibleName("General instructions")
        self.instructions.setPlaceholderText("General instructions for the whole capture")
        self.instructions.textChanged.connect(self._instructions_changed)
        self.note = QLabel()
        self.note.setAccessibleName("Review status")

        controls = QHBoxLayout()
        controls.addWidget(self.play_button)
        controls.addWidget(self.comment_field, 1)
        controls.addWidget(self.add_button)
        side = QVBoxLayout()
        side.addWidget(self.comment_list, 1)
        side.addWidget(self.remove_button)
        side.addWidget(self.instructions)
        top = QHBoxLayout()
        top.addWidget(self.frame_label, 2)
        top.addLayout(side, 1)
        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.timeline)
        layout.addLayout(controls)
        layout.addWidget(self.note)

        self._player = QTimer(self, interval=frame_interval_ms)
        self._player.timeout.connect(self._advance)
        self._refresh_comments()
        if start:
            self.begin()

    def _button(self, text: str, slot) -> QPushButton:
        button = QPushButton(text)
        button.setAccessibleName(text)
        button.clicked.connect(slot)
        return button

    def begin(self) -> None:
        """Start decoding the recording on a background thread."""
        if self._thread is None:
            self._thread = threading.Thread(target=self._work, name="anypoach-proxy", daemon=True)
            self._thread.start()

    def _work(self) -> None:
        try:
            proxy = build_proxy(self._path, cancel=self._cancel, on_frame=self._frames.ready.emit)
        except ValueError:
            return  # the panel keeps saying frames are being prepared; the keyframes and the prompt still work
        self._frames.finished.emit(proxy.done)

    def shutdown(self) -> None:
        """Stop decoding and playing; call before the panel is dropped. Safe to call more than once."""
        if self._cancel.is_set():
            return
        self._cancel.set()
        self._player.stop()
        for signal, slot in ((self._frames.ready, self._on_frame), (self._frames.finished, self._on_finished)):
            try:
                signal.disconnect(slot)
            except (RuntimeError, TypeError):
                pass
        if self._thread is not None:
            self._thread.join(timeout=3)

    def _on_frame(self, frame: ProxyFrame) -> None:
        first = not self.proxy.frames
        self.proxy.add(frame)
        if first:
            self.add_button.setEnabled(True)
            self.note.clear()
            self.seek(0)

    def _on_finished(self, done: bool) -> None:
        self.proxy.done = done

    def seek(self, time_ms: int) -> None:
        """Show the frame closest to `time_ms` and move the playhead onto it."""
        frame = self.proxy.nearest(time_ms)
        if frame is None:
            return
        pixmap = QPixmap()
        pixmap.loadFromData(frame.jpeg, "JPG")
        self.frame_label.setPixmap(pixmap)
        self.playhead_ms = frame.time_ms
        self.timeline.set_position(frame.time_ms)

    def toggle_play(self) -> None:
        """Play from the playhead, or pause."""
        if self._player.isActive():
            self._pause()
        elif self.proxy.frames:
            self._player.start()
            self.play_button.setText("Pause")
            self.play_button.setAccessibleName("Pause")

    def _pause(self) -> None:
        self._player.stop()
        self.play_button.setText("Play")
        self.play_button.setAccessibleName("Play")

    def _advance(self) -> None:
        following = self.proxy.step(self.playhead_ms, 1)
        if following is not None:
            self.seek(following.time_ms)
        elif self.proxy.done:
            self._pause()  # the end of the recording

    def add_comment(self) -> None:
        """Pin the text of the comment field to the frame being shown."""
        if self._controller.add_comment(self.playhead_ms, self.comment_field.text()):
            self.comment_field.clear()
            self.note.clear()
        else:
            self.note.setText(self._controller.message)
        self._refresh_comments()

    def remove_comment(self) -> None:
        """Remove the selected comment."""
        row = self.comment_list.currentRow()
        if row >= 0:
            self._controller.remove_comment(row)
            self._highlighted = -1
            self._refresh_comments()

    def visit(self, row: int) -> None:
        """Pause, show the frame of comment `row`, and highlight it for a few seconds."""
        comments = self._controller.comments
        if not 0 <= row < len(comments):
            return
        self._pause()
        self.seek(comments[row]["timeMs"])
        self._highlighted = row
        self._style_rows()
        QTimer.singleShot(self._highlight_ms, self._clear_highlight)

    def _clear_highlight(self) -> None:
        self._highlighted = -1
        self._style_rows()

    def _style_rows(self) -> None:
        for row in range(self.comment_list.count()):
            font = QFont(self.comment_list.font())
            font.setBold(row == self._highlighted)
            self.comment_list.item(row).setFont(font)

    def _refresh_comments(self) -> None:
        comments = self._controller.comments
        self.comment_list.clear()
        for note in comments:
            self.comment_list.addItem(f"{note['timeMs'] / 1000:.2f} s  {note['text']}")
        self.timeline.set_comments([note["timeMs"] for note in comments])
        self.remove_button.setEnabled(bool(comments))
        self._style_rows()

    def _instructions_changed(self) -> None:
        self._controller.context = self.instructions.toPlainText()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == 0x20:  # Space, when the timeline or a button without its own use for it has focus
            self.toggle_play()
        else:
            super().keyPressEvent(event)
