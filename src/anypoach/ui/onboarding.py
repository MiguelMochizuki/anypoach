"""The welcome tour: what AnyPoach does, then the optional Chrome pairing."""
from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from anypoach.bridge.control import BridgeController, extension_dir
from anypoach.onboarding import platform_note

POINTS = (
    "Record the screen: an area, the full screen or one window. Nothing leaves your computer.",
    "Pointer clicks and drags are traced while you record, so the assistant sees what you did.",
    "Pause the recording on the timeline and pin comments to the exact moment.",
    "Copy the prompt and paste it to your assistant; the MCP connector (Settings) lets it read the brief.",
)


class OnboardingDialog(QDialog):
    """Two steps: what AnyPoach does (with this system's one requirement), then pairing Chrome, which can be
    skipped. Closing it in any way counts as done.

    Args:
        bridge: The Chrome connection, or None when the companion is off (the second step is then left out).
        note: The platform note; computed for this system when omitted.
        parent: The owning window.
    """
    def __init__(self, bridge: BridgeController | None = None, note: str | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Welcome to AnyPoach")
        self._bridge = bridge
        self.pages = QStackedWidget()
        self.pages.addWidget(self._welcome(platform_note() if note is None else note))
        if bridge is not None:
            self.pages.addWidget(self._chrome(bridge))
        layout = QVBoxLayout(self)
        self.step = QLabel()
        self.step.setAccessibleName("Step")
        layout.addWidget(self.step)
        layout.addWidget(self.pages)
        row = QHBoxLayout()
        self.next_button = self._button("Next", self.next)
        self.skip_button = self._button("Skip Chrome", self.accept)
        row.addWidget(self.skip_button)
        row.addWidget(self.next_button)
        layout.addLayout(row)
        self._sync()

    def _button(self, text: str, slot) -> QPushButton:
        button = QPushButton(text)
        button.setAccessibleName(text)
        button.clicked.connect(lambda _=False: slot())
        return button

    def _welcome(self, note: str) -> QWidget:
        page = QWidget()
        column = QVBoxLayout(page)
        title = QLabel("Show your assistant how an interaction works.")
        title.setAccessibleName("Welcome")
        column.addWidget(title)
        for text in POINTS:
            label = QLabel("• " + text)
            label.setWordWrap(True)
            column.addWidget(label)
        if note:
            hint = QLabel(note)
            hint.setWordWrap(True)
            hint.setAccessibleName("Platform note")
            column.addWidget(hint)
        return page

    def _chrome(self, bridge: BridgeController) -> QWidget:
        page = QWidget()
        column = QVBoxLayout(page)
        intro = QLabel("Optional: pair the Chrome companion to add real CSS sizes, colors and animation timing.")
        intro.setWordWrap(True)
        self.code_field = QLineEdit(bridge.code)
        self.code_field.setReadOnly(True)
        self.code_field.setAccessibleName("Pairing code")
        copy = self._button("Copy pairing code", lambda: QApplication.clipboard().setText(bridge.code))
        folder = self._button("Open the extension folder",
                              lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(extension_dir()))))
        for widget in (intro, self.code_field, copy, folder):
            column.addWidget(widget)
        return page

    def next(self) -> None:
        """Go to the Chrome step, or finish when there is nothing more."""
        if self.pages.currentIndex() + 1 < self.pages.count():
            self.pages.setCurrentIndex(self.pages.currentIndex() + 1)
            self._sync()
        else:
            self.accept()

    def _sync(self) -> None:
        total, index = self.pages.count(), self.pages.currentIndex()
        self.step.setText(f"Step {index + 1} of {total}" + (" · Optional" if index == 1 else ""))
        last = index + 1 >= total
        self.next_button.setText("Done" if last else "Next")
        self.next_button.setAccessibleName(self.next_button.text())
        self.skip_button.setVisible(index == 1)
