"""The font matching dialog: drag over one line of a screenshot, say what it reads, pick the closest font."""
from __future__ import annotations

from collections.abc import Callable, Iterable

import numpy as np
from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QFontMetrics, QImage, QMouseEvent, QPainter, QPixmap
from PySide6.QtWidgets import QDialog, QLabel, QLineEdit, QListWidget, QPushButton, QVBoxLayout

from anypoach.fontmatch import FontMatch, rank

from .controller import Controller

PREVIEW_WIDTH = 760
RENDER_PIXELS = 64


def render_text(family: str, text: str) -> np.ndarray:
    """`text` in `family`, black on white at 64 px, as a grayscale array.

    Raises:
        ValueError: If nothing could be drawn.
    """
    font = QFont(family)
    font.setPixelSize(RENDER_PIXELS)
    metrics = QFontMetrics(font)
    width, height = max(1, metrics.horizontalAdvance(text) + 16), metrics.height() + 16
    image = QImage(width, height, QImage.Format.Format_Grayscale8)
    image.fill(QColor("white"))
    painter = QPainter(image)
    painter.setFont(font)
    painter.setPen(QColor("black"))
    painter.drawText(8, 8 + metrics.ascent(), text)
    painter.end()
    return gray_array(image)


def gray_array(image: QImage) -> np.ndarray:
    """A copy of `image` as a 2-D uint8 array."""
    gray = image.convertToFormat(QImage.Format.Format_Grayscale8)
    buffer = np.frombuffer(gray.constBits(), np.uint8).reshape(gray.height(), gray.bytesPerLine())
    return buffer[:, : gray.width()].copy()


class _Canvas(QLabel):
    """The screenshot, with a rubber-band selection; emits `selected` with the box in widget pixels."""
    selected = Signal(QRect)

    def __init__(self, pixmap: QPixmap) -> None:
        super().__init__()
        self.setPixmap(pixmap)
        self.setFixedSize(pixmap.size())
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setAccessibleName("Screenshot: drag over one line of text")
        self._anchor: QPoint | None = None
        self.box = QRect()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self._anchor = event.position().toPoint()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._anchor is not None:
            self.box = QRect(self._anchor, event.position().toPoint()).normalized()
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._anchor is not None:
            self.selected.emit(self.box.intersected(self.rect()))
            self._anchor = None

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if not self.box.isNull():
            painter = QPainter(self)
            painter.setPen(QColor(255, 80, 80))
            painter.drawRect(self.box)


class FontMatchDialog(QDialog):
    """Shows the image, takes a dragged box and the words in it, ranks the installed fonts and lets the user
    choose one, which goes into the handoff as `visualFontMatch`. It is an approximation, and says so.

    Args:
        controller: Receives the choice through `select_font`.
        image_path: The image to show.
        families: Candidate families; the installed ones by default.
        render: Draws text in a family; `render_text` by default. Parameters for tests.
        parent: The owning window.
    """
    def __init__(self, controller: Controller, image_path: str, *, families: Callable[[], Iterable[str]] | None = None,
                 render: Callable[[str, str], np.ndarray] = render_text, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Match a font")
        self._controller, self._render = controller, render
        self._families = families or QFontDatabase.families
        self._image = QImage(image_path)
        pixmap = QPixmap.fromImage(self._image)
        if pixmap.width() > PREVIEW_WIDTH:
            pixmap = pixmap.scaledToWidth(PREVIEW_WIDTH, Qt.TransformationMode.SmoothTransformation)
        self._factor = self._image.width() / max(1, pixmap.width())
        self.canvas = _Canvas(pixmap)
        self.canvas.selected.connect(self.select_box)
        self._box = QRect()
        self.text = QLineEdit()
        self.text.setPlaceholderText("What does the selected line say?")
        self.text.setAccessibleName("Text in the selection")
        self.results = QListWidget()
        self.results.setAccessibleName("Closest fonts")
        self.status = QLabel("Drag over one line of text, type what it says, then find fonts. The match is approximate.")
        self.status.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.addWidget(self.canvas)
        layout.addWidget(self.text)
        for label, slot in (("Find fonts", self.find), ("Use selected font", self.use), ("Clear font match", self.clear)):
            button = QPushButton(label)
            button.setAccessibleName(label)
            button.clicked.connect(lambda _=False, s=slot: s())
            layout.addWidget(button)
        layout.addWidget(self.results)
        layout.addWidget(self.status)

    def select_box(self, box: QRect) -> None:
        """Take `box` (preview pixels) as the line to match."""
        self._box = box

    def _image_box(self) -> QRect:
        box, f = self._box, self._factor
        return QRect(round(box.x() * f), round(box.y() * f), round(box.width() * f), round(box.height() * f))

    def find(self) -> list[FontMatch]:
        """Rank the installed fonts against the selection and list the closest."""
        text = self.text.text().strip()
        if self._box.width() < 8 or self._box.height() < 6 or not text:
            self.status.setText("Drag over one line of text and type what it says first.")
            return []
        crop = gray_array(self._image.copy(self._image_box()))
        matches = rank(crop, text, self._families(), self._render)
        self.results.clear()
        for match in matches:
            self.results.addItem(f"{match.family}  ·  distance {match.distance:.2f}")
        if matches:
            self.results.setCurrentRow(0)
        self.status.setText("Closest installed fonts, best first." if matches else "No font looked close enough.")
        self._matches = matches
        return matches

    def use(self) -> None:
        """Put the selected font in the handoff."""
        row = self.results.currentRow()
        matches = getattr(self, "_matches", [])
        if not 0 <= row < len(matches):
            self.status.setText("Find fonts, then choose one.")
            return
        box, image = self._image_box(), self._image
        region = (box.x() / image.width(), box.y() / image.height(), box.width() / image.width(),
                  box.height() / image.height())
        chosen = matches[row]
        ok = self._controller.select_font(chosen.family, self.text.text(), region, chosen.distance)
        self.status.setText(f"{chosen.family} will go in the handoff." if ok else self._controller.message)

    def clear(self) -> None:
        """Take the font match out of the handoff."""
        self._controller.font_match = None
        self.status.setText("The handoff has no font match.")
