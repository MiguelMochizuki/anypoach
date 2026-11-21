"""The favorites dialog: reuse, export, import and delete saved handoffs."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from anypoach.favorites import SUFFIX, FavoriteError

from .controller import Controller


class FavoritesDialog(QDialog):
    """Lists the favorites by cover and name. **Copy handoff** writes a fresh brief and puts its prompt on the
    clipboard; **Export…** and **Import…** move `.anypoach` files; **Delete** removes one.

    Args:
        controller: Owns the favorites and the handoff.
        ask_save: Where to get a file to write, given a suggested name; a parameter for tests.
        ask_open: Where to get a file to read; a parameter for tests.
        parent: The owning window.
    """
    def __init__(self, controller: Controller, *, ask_save: Callable[[str], str] | None = None,
                 ask_open: Callable[[], str] | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("AnyPoach favorites")
        self._controller = controller
        self._ask_save = ask_save or (lambda name: QFileDialog.getSaveFileName(self, "Export favorite", name,
                                                                                f"AnyPoach favorite (*{SUFFIX})")[0])
        self._ask_open = ask_open or (lambda: QFileDialog.getOpenFileName(self, "Import favorite", "",
                                                                          f"AnyPoach favorite (*{SUFFIX})")[0])
        self.list = QListWidget()
        self.list.setIconSize(QSize(120, 80))
        self.list.setAccessibleName("Favorites")
        self.status = QLabel("")
        self.status.setAccessibleName("Favorites status")
        layout = QVBoxLayout(self)
        layout.addWidget(self.list)
        for text, slot in (("Copy handoff", self.copy_handoff), ("Export…", self.export), ("Import…", self.import_file),
                           ("Delete", self.delete)):
            button = QPushButton(text)
            button.setAccessibleName(text)
            button.clicked.connect(lambda _=False, s=slot: s())
            layout.addWidget(button)
        layout.addWidget(self.status)
        self.refresh()

    def refresh(self) -> None:
        """Reload the list, newest first."""
        self.list.clear()
        for summary in self._controller.favorites.list():
            item = QListWidgetItem(summary.name)
            try:
                pixmap = QPixmap()
                pixmap.loadFromData(self._controller.favorites.cover(summary.id))
                item.setIcon(QIcon(pixmap))
            except FavoriteError:
                pass
            item.setData(Qt.ItemDataRole.UserRole, summary.id)
            self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)

    def _selected(self) -> str | None:
        item = self.list.currentItem()
        if item is None:
            self.status.setText("Choose a favorite first.")
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def copy_handoff(self) -> None:
        """Put a fresh handoff prompt for the selected favorite on the clipboard."""
        if (favorite_id := self._selected()) is None:
            return
        prompt = self._controller.favorite_handoff(favorite_id)
        if prompt:
            QApplication.clipboard().setText(prompt)
        self.status.setText("Prompt copied. Paste it to your assistant." if prompt else self._controller.message)

    def export(self) -> None:
        """Write the selected favorite to a `.anypoach` file."""
        if (favorite_id := self._selected()) is None:
            return
        name = self.list.currentItem().text()
        path = self._ask_save(f"{name}{SUFFIX}")
        if not path:
            return
        try:
            self._controller.favorites.export(favorite_id, Path(path))
            self.status.setText("Exported.")
        except (FavoriteError, OSError) as error:
            self.status.setText(f"Could not export: {error}")

    def import_file(self) -> None:
        """Add the favorites from a `.anypoach` file after checking it."""
        path = self._ask_open()
        if not path:
            return
        try:
            self._controller.favorites.import_file(Path(path))
        except (FavoriteError, OSError) as error:
            self.status.setText(f"Could not import: {error}")
            return
        self.status.setText("Imported.")
        self.refresh()

    def delete(self) -> None:
        """Remove the selected favorite."""
        if (favorite_id := self._selected()) is None:
            return
        self._controller.favorites.delete(favorite_id)
        self.status.setText("Deleted.")
        self.refresh()
