"""The settings dialog: storage, the assistant connection commands, and the update check."""
from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication, QCheckBox, QDialog, QLabel, QPushButton, QVBoxLayout

from anypoach.brief.cleanup import clear_storage, scan_storage
from anypoach.hotkey import CHORD
from anypoach.setup import setup_text
from anypoach.updates import check_for_update


def megabytes(size: int) -> str:
    """`size` bytes as a short text such as `3.4 MB`."""
    return f"{size / 1_000_000:.1f} MB"


class _Answer(QObject):
    """Carries the update check's sentence from its thread back to the dialog."""
    ready = Signal(str)


class SettingsDialog(QDialog):
    """Storage use with a button that clears unused captures, copy buttons for the MCP commands, and an
    update check that touches the network only when its button is pressed.

    Args:
        open_paths: Returns the media the window has open, which clearing must keep.
        temp: Folder holding temporary media (the system one when omitted); a parameter for tests.
        cache: Brief cache directory (the default one when omitted); a parameter for tests.
        check: The update check; a parameter for tests.
        on_tour: Shows the welcome tour; the button is left out when None.
        shortcut: The shortcut's current state and a function that turns it on or off and says whether it is on; the
            checkbox is left out when None.
        parent: The owning window.
    """
    def __init__(self, open_paths: Callable[[], list[str]], *, temp: Path | None = None, cache: Path | None = None,
                 check: Callable[[], str] = check_for_update, on_tour: Callable[[], None] | None = None,
                 shortcut: tuple[bool, Callable[[bool], bool]] | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("AnyPoach settings")
        self._open_paths, self._temp, self._cache, self._check = open_paths, temp, cache, check
        self._answer = _Answer()
        self._answer.ready.connect(lambda text: (self.update_label.setText(text), self.update_button.setEnabled(True)))
        self.storage_label, self.update_label = QLabel(), QLabel("Updates are checked only when you ask.")
        for label, name in ((self.storage_label, "Storage"), (self.update_label, "Update status")):
            label.setAccessibleName(name)
            label.setWordWrap(True)
            label.setOpenExternalLinks(True)
        self.clear_button = self._button("Clear unused captures", self.clear)
        self.update_button = self._button("Check for updates…", self.check_updates)
        layout = QVBoxLayout(self)
        for widget in (self.storage_label, self.clear_button, QLabel("Connect an assistant:"),
                       *(self._button(f"Copy {title} setup", lambda _=False, c=client: self.copy_setup(c))
                         for client, title in (("claude", "Claude Code"), ("codex", "Codex"), ("json", "JSON"))),
                       self.update_label, self.update_button,
                       *([self._button("Welcome tour…", lambda _=False: on_tour())] if on_tour else [])):
            layout.addWidget(widget)
        self.shortcut_box = None
        if shortcut is not None:
            self._set_shortcut = shortcut[1]
            self.shortcut_box = QCheckBox(f"Global shortcut {CHORD} starts and stops a full-screen recording")
            self.shortcut_box.setAccessibleName("Global shortcut")
            self.shortcut_box.setChecked(shortcut[0])
            self.shortcut_box.toggled.connect(self._shortcut_toggled)
            layout.addWidget(self.shortcut_box)
        self.refresh()

    def _shortcut_toggled(self, checked: bool) -> None:
        if self._set_shortcut(checked) != checked:
            self.shortcut_box.blockSignals(True)
            self.shortcut_box.setChecked(not checked)
            self.shortcut_box.blockSignals(False)
            self.update_label.setText("The shortcut could not be registered: another program may be using it.")

    def _button(self, text: str, slot) -> QPushButton:
        button = QPushButton(text)
        button.setAccessibleName(text)
        button.clicked.connect(slot)
        return button

    def refresh(self) -> None:
        """Re-measure the temporary media and show the totals."""
        try:
            usage = scan_storage(temp=self._temp, cache=self._cache, open_paths=self._open_paths())
        except (ValueError, OSError) as error:
            self.storage_label.setText(f"Could not measure storage: {error}")
            self.clear_button.setEnabled(False)
            return
        self.storage_label.setText(f"AnyPoach uses {megabytes(usage.total)}; {megabytes(usage.unused)} is unused.")
        self.clear_button.setEnabled(bool(usage.removable))

    def clear(self) -> None:
        """Delete the unused captures (never what the window has open or a valid brief still needs)."""
        try:
            clear_storage(temp=self._temp, cache=self._cache, open_paths=self._open_paths())
        except (ValueError, OSError) as error:
            self.storage_label.setText(f"Could not clear storage: {error}")
            return
        self.refresh()

    def copy_setup(self, client: str) -> None:
        """Put the connect command (or JSON entry) for `client` on the clipboard."""
        QApplication.clipboard().setText(setup_text(client))

    def check_updates(self) -> None:
        """Ask GitHub for the newest release on a thread; the answer replaces the update label."""
        self.update_button.setEnabled(False)
        self.update_label.setText("Checking…")
        threading.Thread(target=lambda: self._answer.ready.emit(self._check()), daemon=True).start()
