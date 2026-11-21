"""A thin frame drawn just outside the area being recorded, so it never appears in the video."""
from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

MARGIN = 3  # logical pixels of frame around the area


def outline_geometry(area: QRect) -> QRect:
    """The window that surrounds `area` with `MARGIN` pixels on every side."""
    return area.adjusted(-MARGIN, -MARGIN, MARGIN, MARGIN)


class AreaOutline(QWidget):
    """A click-through frame around `area` (logical pixels, global). The area itself is left untouched: the frame
    lives only in the margin, which the recording does not include.

    Args:
        area: The recorded area in logical screen pixels.
    """
    def __init__(self, area: QRect) -> None:
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool | Qt.WindowType.WindowTransparentForInput)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setGeometry(outline_geometry(area))

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setPen(QPen(QColor(255, 80, 80, 220), MARGIN))
        painter.drawRect(QRect(MARGIN // 2, MARGIN // 2, self.width() - MARGIN, self.height() - MARGIN))
