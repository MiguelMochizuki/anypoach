"""Area selection on a frozen frame: the coordinate mapping and the widget's signals, run offscreen."""
import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from anypoach.capture.backend import Frame
from anypoach.pointer.trace import Rect
from anypoach.ui.frozen_selection import FrozenSelection, frame_rect


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def frame(width, height):
    return Frame(np.zeros((height, width, 4), np.uint8), 0.0)


def test_frame_rect_scales_widget_pixels_to_frame_pixels():
    assert frame_rect((10, 10), (60, 30), widget_size=(100, 50), frame_size=(200, 100)) == Rect(20, 20, 100, 40)


def test_frame_rect_accepts_a_drag_in_any_direction():
    assert frame_rect((60, 30), (10, 10), widget_size=(100, 50), frame_size=(100, 50)) == Rect(10, 10, 50, 20)


def test_frame_rect_clamps_to_the_frame():
    assert frame_rect((-20, -5), (500, 500), widget_size=(100, 50), frame_size=(100, 50)) == Rect(0, 0, 100, 50)


def test_a_drag_emits_the_area_in_frame_pixels(app):
    widget = FrozenSelection(frame(200, 100))
    widget.resize(100, 50)
    got = []
    widget.selected.connect(got.append)
    QTest.mousePress(widget, Qt.MouseButton.LeftButton, pos=QPoint(10, 10))
    QTest.mouseRelease(widget, Qt.MouseButton.LeftButton, pos=QPoint(60, 30))
    assert got == [Rect(20, 20, 100, 40)]


def test_a_tiny_drag_emits_nothing_and_keeps_the_widget_open(app):
    widget = FrozenSelection(frame(100, 50))
    widget.resize(100, 50)
    widget.show()
    got = []
    widget.selected.connect(got.append)
    QTest.mousePress(widget, Qt.MouseButton.LeftButton, pos=QPoint(10, 10))
    QTest.mouseRelease(widget, Qt.MouseButton.LeftButton, pos=QPoint(11, 10))
    assert got == [] and widget.isVisible()
    widget.close()


def test_escape_cancels(app):
    widget = FrozenSelection(frame(20, 10))
    seen = []
    widget.cancelled.connect(lambda: seen.append(1))
    QTest.keyClick(widget, Qt.Key.Key_Escape)
    assert seen == [1]


def test_the_widget_has_an_accessible_name(app):
    assert "Drag" in FrozenSelection(frame(20, 10)).accessibleName()
