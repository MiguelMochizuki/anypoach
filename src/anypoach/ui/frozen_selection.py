"""Full-screen selection on a frozen frame, for sessions where an overlay cannot be placed over the screen."""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QImage, QKeyEvent, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QWidget

from anypoach.capture.backend import Frame
from anypoach.pointer.trace import Rect


def frame_rect(start: tuple[float, float], end: tuple[float, float], *, widget_size: tuple[float, float],
               frame_size: tuple[int, int]) -> Rect:
    """Convert two dragged corners in widget coordinates into a rectangle in frame pixels.

    Args:
        start: First corner, in widget coordinates.
        end: Opposite corner, in the same coordinates.
        widget_size: Width and height of the widget showing the frame.
        frame_size: Width and height of the frame, in pixels.

    Returns:
        A rectangle clamped to the frame, with non-negative width and height whichever way the drag went.
    """
    scale_x, scale_y = frame_size[0] / widget_size[0], frame_size[1] / widget_size[1]
    left, right = (min(max(v * scale_x, 0), frame_size[0]) for v in sorted((start[0], end[0])))
    top, bottom = (min(max(v * scale_y, 0), frame_size[1]) for v in sorted((start[1], end[1])))
    return Rect(left, top, right - left, bottom - top)


class FrozenSelection(QWidget):
    """Shows one captured frame stretched over the whole window and lets the user drag an area on it.

    Emits `selected` with a `Rect` in frame pixels when a drag of at least 2 pixels ends, or `cancelled` on
    Escape. A shorter drag is ignored.

    Args:
        frame: The frame to show; its pixel size is the coordinate space of `selected`.
    """
    selected = Signal(object)  # Rect in frame pixels
    cancelled = Signal()

    def __init__(self, frame: Frame) -> None:
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        pixels = np.ascontiguousarray(frame.pixels)
        height, width = pixels.shape[:2]
        self._frame_size = (width, height)
        self._image = QImage(pixels.data, width, height, width * 4, QImage.Format.Format_ARGB32).copy()
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setAccessibleName("Area selection. Drag to choose the area to record, Escape to cancel.")
        self._anchor: QPoint | None = None
        self._current: QPoint | None = None

    def _drag_rect(self) -> QRect:
        return QRect(self._anchor, self._current).normalized() if self._anchor and self._current else QRect()

    def paintEvent(self, _event) -> None:
        """Draw the frame dimmed, with the dragged area at full brightness and outlined in white."""
        painter = QPainter(self)
        painter.drawImage(self.rect(), self._image)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 110))
        area = self._drag_rect()
        if not area.isNull():
            source = frame_rect((area.left(), area.top()), (area.right() + 1, area.bottom() + 1),
                                widget_size=(self.width(), self.height()), frame_size=self._frame_size)
            painter.drawImage(area, self._image, QRect(round(source.x), round(source.y), round(source.width),
                                                       round(source.height)))
            painter.setPen(QPen(QColor(255, 255, 255), 2))
            painter.drawRect(area)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Anchor the selection at the pressed point."""
        self._anchor = self._current = event.position().toPoint()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Grow the selection to the pointer."""
        self._current = event.position().toPoint()
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Finish the drag: close the widget and emit `selected`, unless the drag was under 2 frame pixels."""
        if self._anchor is None:
            return
        area = frame_rect((self._anchor.x(), self._anchor.y()), (event.position().x(), event.position().y()),
                          widget_size=(self.width(), self.height()), frame_size=self._frame_size)
        self._anchor = self._current = None
        self.update()
        if area.width < 2 or area.height < 2:
            return
        self.close()
        self.selected.emit(area)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Close the widget and emit `cancelled` when Escape is pressed."""
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            self.cancelled.emit()
