"""The editor's timeline: where the playhead is, where things moved, and where the comments are."""
from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent, QMouseEvent, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QWidget

MARGIN_PX = 8
STEP_MS = round(1000 / 15)  # one frame of the editor's proxy, for the arrow keys
HIT_PX = 8  # how close a click must be to a marker to count as hitting it


def group_markers(times_ms: Sequence[int], duration_ms: int, width_px: int, min_gap_px: int = 24) -> list[tuple[int, list[int]]]:
    """Group the markers that would be drawn closer than `min_gap_px`.

    Args:
        times_ms: Moment of every marker.
        duration_ms: Length of the track in milliseconds (zero puts everything at the left edge).
        width_px: Width of the track in pixels.
        min_gap_px: Markers closer than this, measured from the first marker of a group, join it.

    Returns:
        `(x_px, [indices into times_ms])` for each group, left to right; the indices are in time order and `x_px`
        is the first marker's position.
    """
    order = sorted(range(len(times_ms)), key=times_ms.__getitem__)
    groups: list[tuple[int, list[int]]] = []
    for index in order:
        x = round(times_ms[index] / duration_ms * width_px) if duration_ms > 0 else 0
        if groups and x - groups[-1][0] < min_gap_px:
            groups[-1][1].append(index)
        else:
            groups.append((x, [index]))
    return groups


class TimelineWidget(QWidget):
    """A track with the playhead, bands where the video moves, and grouped comment markers.

    Signals:
        position_requested(int): A time in milliseconds the person asked for (click, drag, or arrow key); the
            host snaps it to a frame and calls `set_position`.
        marker_activated(list): The indices (into the list given to `set_comments`) of a clicked marker group.
    """
    position_requested = Signal(int)
    marker_activated = Signal(list)

    def __init__(self) -> None:
        super().__init__()
        self._duration, self._position = 0, 0
        self._segments: list[tuple[int, int]] = []
        self._comments: list[int] = []
        self._dragging = False
        self.setAccessibleName("Timeline")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumHeight(40)

    def set_duration(self, duration_ms: int) -> None:
        """Set the length of the video in milliseconds."""
        self._duration = max(0, duration_ms)
        self.update()

    def set_segments(self, spans: list[tuple[int, int]]) -> None:
        """Set the `(start_ms, end_ms)` bands where the video moves."""
        self._segments = list(spans)
        self.update()

    def set_comments(self, times_ms: list[int]) -> None:
        """Set the moment of every comment."""
        self._comments = list(times_ms)
        self.update()

    def set_position(self, time_ms: int) -> None:
        """Move the playhead."""
        self._position = time_ms
        self.update()

    def _track_width(self) -> int:
        return max(1, self.width() - 2 * MARGIN_PX)

    def _time_at(self, x: float) -> int:
        fraction = min(1.0, max(0.0, (x - MARGIN_PX) / self._track_width()))
        return round(fraction * self._duration)

    def _x_at(self, time_ms: float) -> int:
        return MARGIN_PX + (round(time_ms / self._duration * self._track_width()) if self._duration > 0 else 0)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        x, y = event.position().x(), event.position().y()
        if y >= self.height() / 2:
            for track_x, indices in group_markers(self._comments, self._duration, self._track_width()):
                if abs(MARGIN_PX + track_x - x) <= HIT_PX:
                    self.marker_activated.emit(indices)
                    return
        self._dragging = True
        self.position_requested.emit(self._time_at(x))

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._dragging:
            self.position_requested.emit(self._time_at(event.position().x()))

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._dragging = False

    def keyPressEvent(self, event: QKeyEvent) -> None:
        step = {Qt.Key.Key_Right: STEP_MS, Qt.Key.Key_Left: -STEP_MS}.get(event.key())
        if step is None:
            super().keyPressEvent(event)
            return
        self.position_requested.emit(min(self._duration, max(0, self._position + step)))

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        palette = self.palette()
        middle = self.height() // 2
        painter.fillRect(QRect(MARGIN_PX, middle - 3, self._track_width(), 6), palette.mid())
        for start, end in self._segments:
            left, right = self._x_at(start), self._x_at(end)
            painter.fillRect(QRect(left, middle - 7, max(2, right - left), 14), QColor(229, 50, 45, 90))
        for x, indices in group_markers(self._comments, self._duration, self._track_width()):
            painter.setBrush(palette.highlight())
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(MARGIN_PX + x - 5, self.height() - 14, 10, 10)
            if len(indices) > 1:
                painter.setPen(palette.highlightedText().color())
                painter.drawText(QRect(MARGIN_PX + x - 8, self.height() - 16, 16, 14), Qt.AlignmentFlag.AlignCenter, str(len(indices)))
        painter.setPen(QPen(palette.text().color(), 2))
        x = self._x_at(self._position)
        painter.drawLine(x, 2, x, self.height() - 2)
        if self.hasFocus():
            painter.setPen(QPen(palette.highlight().color(), 1))
            painter.drawRect(0, 0, self.width() - 1, self.height() - 1)
        painter.end()
