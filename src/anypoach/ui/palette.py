"""The palette strip: swatches the user can edit, remove, add to, or reset."""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QColorDialog, QHBoxLayout, QPushButton, QWidget

from .controller import MAX_PALETTE, Controller


def ask_color(current: str) -> str | None:
    """Show the system color dialog starting at `current`; returns `#rrggbb`, or None when cancelled."""
    color = QColorDialog.getColor(QColor(current), None, "Choose a color")
    return color.name() if color.isValid() else None


class PaletteEditor(QWidget):
    """One swatch per color of the brief's palette. Click a swatch to change it, `×` to drop it, **Add color** to
    append one (up to 12) and **Reset** to return to the analyzed palette. Every change goes through
    `Controller.set_palette`.

    Args:
        controller: Owns the palette.
        pick: Asks the user for a color given the current one; a parameter for tests.
    """
    def __init__(self, controller: Controller, pick: Callable[[str], str | None] = ask_color) -> None:
        super().__init__()
        self._controller, self._pick = controller, pick
        self._row = QHBoxLayout(self)
        self.setAccessibleName("Palette")
        self.refresh()

    def refresh(self) -> None:
        """Rebuild the swatches from the controller's palette; hidden when there is no result."""
        while self._row.count():
            if (widget := self._row.takeAt(0).widget()) is not None:
                widget.deleteLater()
        colors = self._controller.palette
        self.setVisible(bool(colors))
        if not colors:
            return
        for index, color in enumerate(colors):
            swatch = self._button("", lambda _=False, i=index: self.edit(i), f"Palette color {color}")
            swatch.setStyleSheet(f"background-color: {color}; min-width: 36px; min-height: 24px;")
            swatch.setToolTip(color)
            self._row.addWidget(swatch)
            self._row.addWidget(self._button("×", lambda _=False, i=index: self.remove(i), f"Remove {color}", small=True))
        add = self._button("Add color", self.add, "Add color")
        add.setEnabled(0 < len(colors) < MAX_PALETTE)
        self._row.addWidget(add)
        self._row.addWidget(self._button("Reset", self.reset, "Reset palette"))
        self._row.addStretch()

    def _button(self, text: str, slot, name: str, small: bool = False) -> QPushButton:
        button = QPushButton(text)
        button.setAccessibleName(name)
        button.clicked.connect(slot)
        if small:
            button.setMaximumWidth(28)
        return button

    def _apply(self, colors: list[str]) -> None:
        self._controller.set_palette(colors)
        self.refresh()

    def edit(self, index: int) -> None:
        """Change the color at `index` to what the user picks."""
        colors = self._controller.palette
        picked = self._pick(colors[index])
        if picked:
            colors[index] = picked
            self._apply(colors)

    def remove(self, index: int) -> None:
        """Drop the color at `index`; the last one cannot be dropped."""
        colors = self._controller.palette
        if len(colors) > 1:
            del colors[index]
            self._apply(colors)

    def add(self) -> None:
        """Append the color the user picks."""
        colors = self._controller.palette
        picked = self._pick(colors[-1])
        if picked:
            self._apply([*colors, picked])

    def reset(self) -> None:
        """Return to the analyzed palette."""
        self._controller.reset_palette()
        self.refresh()
