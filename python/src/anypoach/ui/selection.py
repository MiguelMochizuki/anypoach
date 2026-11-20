"""Translucent full-screen overlay to drag a capture area. Esc cancels."""
from __future__ import annotations

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QWidget

from anypoach.pointer.trace import Rect

from .controller import physical_rect


class SelectionOverlay(QWidget):
    selected = Signal(object)  # Rect in global physical pixels
    cancelled = Signal()

    def __init__(self, screen) -> None:
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setAccessibleName("Area selection. Drag to choose the area to record, Escape to cancel.")
        self.setGeometry(screen.geometry())
        self._screen, self._anchor, self._current = screen, None, None

    def _drag_rect(self) -> QRect:
        return QRect(self._anchor, self._current).normalized() if self._anchor and self._current else QRect()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 90))
        area = self._drag_rect()
        if not area.isNull():
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(area, Qt.GlobalColor.transparent)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            painter.setPen(QPen(QColor(255, 255, 255), 2))
            painter.drawRect(area)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self._anchor = self._current = event.position().toPoint()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        self._current = event.position().toPoint()
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._anchor is None:
            return
        geometry = self._screen.geometry()
        rect = physical_rect((self._anchor.x(), self._anchor.y()), (event.position().x(), event.position().y()),
                             origin=(geometry.x(), geometry.y()), dpr=self._screen.devicePixelRatio())
        self.close()
        self.selected.emit(Rect(*rect))

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            self.cancelled.emit()

