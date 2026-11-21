"""The timeline: marker grouping (pure) and the widget's mouse and keyboard behavior, offscreen."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from anypoach.ui.timeline import TimelineWidget, group_markers


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def timeline(app):
    """416 px wide with 8 px margins: a 400 px track over 4 s, so 10 ms per pixel."""
    widget = TimelineWidget()
    widget.resize(416, 40)
    widget.set_duration(4000)
    widget.show()
    return widget


def test_group_markers():
    assert group_markers([], 4000, 400) == []
    assert group_markers([1000, 1100], 4000, 400) == [(100, [0, 1])]  # 10 px apart
    assert group_markers([1000, 1300], 4000, 400) == [(100, [0]), (130, [1])]  # 30 px apart
    assert group_markers([0, 100, 150], 4000, 400) == [(0, [0, 1, 2])]
    assert group_markers([5, 9], 0, 400) == [(0, [0, 1])]  # a zero duration does not divide by zero


def test_markers_are_grouped_by_distance_from_the_first_of_the_group():
    assert group_markers([1000, 1200, 1400], 4000, 400) == [(100, [0, 1]), (140, [2])]  # 40 px from the first
    assert group_markers([1000, 1100, 1200], 4000, 400) == [(100, [0, 1, 2])]
    assert group_markers([1100, 1000], 4000, 400) == [(100, [1, 0])]  # indices follow the input; order by time


def test_clicking_the_track_emits_the_time_under_the_pointer(timeline):
    got = []
    timeline.position_requested.connect(got.append)
    QTest.mouseClick(timeline, Qt.MouseButton.LeftButton, pos=QPoint(108, 10))
    assert got and abs(got[-1] - 1000) <= 10


def test_dragging_emits_repeatedly_and_clamps_to_the_ends(timeline):
    got = []
    timeline.position_requested.connect(got.append)
    QTest.mousePress(timeline, Qt.MouseButton.LeftButton, pos=QPoint(108, 10))
    QTest.mouseMove(timeline, QPoint(208, 10))
    QTest.mouseMove(timeline, QPoint(-50, 10))
    QTest.mouseMove(timeline, QPoint(5000, 10))
    QTest.mouseRelease(timeline, Qt.MouseButton.LeftButton, pos=QPoint(5000, 10))
    assert len(got) >= 4 and got[0] == pytest.approx(1000, abs=10) and 0 in got and got[-1] == 4000


def test_arrow_keys_emit_a_step_around_the_current_position(timeline):
    got = []
    timeline.position_requested.connect(got.append)
    timeline.set_position(1000)
    QTest.keyClick(timeline, Qt.Key.Key_Right)
    QTest.keyClick(timeline, Qt.Key.Key_Left)
    assert got == [1067, 933]
    timeline.set_position(0)
    QTest.keyClick(timeline, Qt.Key.Key_Left)
    assert got[-1] == 0


def test_clicking_a_marker_emits_its_comment_indices(timeline):
    timeline.set_comments([1000, 1100, 3000])
    marked = []
    moved = []
    timeline.marker_activated.connect(marked.append)
    timeline.position_requested.connect(moved.append)
    QTest.mouseClick(timeline, Qt.MouseButton.LeftButton, pos=QPoint(108, 34))
    assert marked == [[0, 1]] and moved == []
    QTest.mouseClick(timeline, Qt.MouseButton.LeftButton, pos=QPoint(308, 34))
    assert marked[-1] == [2]


def test_the_widget_has_an_accessible_name_and_takes_focus(timeline):
    assert timeline.accessibleName() == "Timeline" and timeline.focusPolicy() == Qt.FocusPolicy.StrongFocus
    timeline.set_segments([(500, 1100), (2500, 3100)])  # painting with bands must not raise
    timeline.set_comments([700])
    timeline.set_position(700)
    timeline.grab()
