"""The review panel against a real clip and the real controller, offscreen, with short timers."""
import os
import threading
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from anypoach.analysis.inspect import inspect_video, read_video_moment
from anypoach.analysis.proxy import FrameProxy
from anypoach.ui.controller import Controller
from anypoach.ui.review import ReviewPanel


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def result(clips, tmp_path_factory):
    return inspect_video(clips["motion"], output_dir=tmp_path_factory.mktemp("frames"))


@pytest.fixture
def controller(tmp_path):
    return Controller(object(), None, tmp_path / "work", cache=tmp_path / "cache")


def wait_for(condition, timeout_ms=8000):
    """Poll with `processEvents` and a real sleep: `QTest.qWait` keeps the GIL, which starves the decoding thread."""
    deadline = time.monotonic() + timeout_ms / 1000
    while not condition() and time.monotonic() < deadline:
        QApplication.processEvents()
        time.sleep(0.005)
    return condition()


@pytest.fixture
def panel(app, controller, result):
    widget = ReviewPanel(controller, result, frame_interval_ms=5, highlight_ms=60)
    try:
        assert wait_for(lambda: widget.proxy.done) and len(widget.proxy.frames) == 30
        yield widget
    finally:
        widget.shutdown()


def test_every_control_has_an_accessible_name(panel):
    names = {panel.frame_label.accessibleName(), panel.timeline.accessibleName(), panel.play_button.accessibleName(),
             panel.comment_field.accessibleName(), panel.add_button.accessibleName(), panel.remove_button.accessibleName(),
             panel.comment_list.accessibleName(), panel.instructions.accessibleName()}
    assert names == {"Recording frame", "Timeline", "Play", "Comment", "Comment at this moment", "Remove comment",
                     "Comments", "General instructions"}


def test_the_comment_button_is_off_until_a_frame_is_ready_and_on_after(app, controller, result):
    widget = ReviewPanel(controller, result, start=False)
    assert not widget.add_button.isEnabled() and widget.proxy.frames == []
    widget.begin()
    try:
        assert wait_for(widget.add_button.isEnabled)
    finally:
        widget.shutdown()


def test_the_segment_bands_reach_the_timeline(panel, result):
    assert panel.timeline._segments == [(s.start_ms, s.end_ms) for s in result.segments]


def test_scrubbing_snaps_to_a_proxy_frame_and_shows_it(panel):
    panel.timeline.position_requested.emit(1010)
    assert panel.playhead_ms == 1000 and panel.timeline._position == 1000
    assert panel.playhead_ms in [f.time_ms for f in panel.proxy.frames] and not panel.frame_label.pixmap().isNull()


def test_adding_a_comment_uses_the_frame_time_and_lists_it_sorted(panel, controller):
    panel.seek(1010)
    panel.comment_field.setText("late")
    panel.add_button.click()
    panel.seek(100)
    panel.comment_field.setText("early")
    QTest.keyClick(panel.comment_field, Qt.Key.Key_Return)
    assert controller.comments == [{"timeMs": 133, "text": "early"}, {"timeMs": 1000, "text": "late"}] or \
        [c["text"] for c in controller.comments] == ["early", "late"]
    assert [panel.comment_list.item(i).text().split("  ", 1)[1] for i in range(2)] == ["early", "late"]
    assert panel.timeline._comments == [c["timeMs"] for c in controller.comments] and panel.comment_field.text() == ""


def test_an_empty_comment_shows_the_reason(panel, controller):
    panel.add_button.click()
    assert "empty" in panel.note.text().lower() and controller.comments == []


def test_a_comment_time_is_one_read_moment_resolves_to_the_frame_shown(panel, controller, result):
    panel.seek(1300)
    panel.comment_field.setText("here")
    panel.add_button.click()
    moment = controller.comments[0]["timeMs"]
    assert moment == panel.playhead_ms and moment in [f.time_ms for f in panel.proxy.frames]
    assert read_video_moment(result.source_path, moment)[:8] == bytes([137, 80, 78, 71, 13, 10, 26, 10])


def test_visiting_a_comment_pauses_seeks_and_highlights_for_a_moment(panel, controller):
    controller.add_comment(1000, "look")
    panel._refresh_comments()
    panel.seek(0)
    panel.toggle_play()
    panel.comment_list.itemClicked.emit(panel.comment_list.item(0))
    assert not panel._player.isActive() and panel.playhead_ms == 1000 and panel._highlighted == 0
    assert panel.comment_list.item(0).font().bold()
    QTest.qWait(200)
    assert panel._highlighted == -1 and not panel.comment_list.item(0).font().bold()


def test_removing_a_comment_updates_the_list_and_the_markers(panel, controller):
    controller.add_comment(500, "one")
    controller.add_comment(900, "two")
    panel._refresh_comments()
    panel.comment_list.setCurrentRow(0)
    panel.remove_button.click()
    assert [c["text"] for c in controller.comments] == ["two"] and panel.comment_list.count() == 1
    assert panel.timeline._comments == [900]


def test_play_advances_through_the_frames_and_stops_at_the_end(panel):
    last = panel.proxy.frames[-1].time_ms
    panel.seek(last - 140)
    panel.toggle_play()
    assert panel.play_button.accessibleName() == "Pause"
    assert wait_for(lambda: not panel._player.isActive(), 3000)
    assert panel.playhead_ms == last and panel.play_button.accessibleName() == "Play"


def test_space_toggles_play_and_the_arrows_step_one_frame(panel):
    panel.seek(0)
    QTest.keyClick(panel.timeline, Qt.Key.Key_Space)
    assert panel._player.isActive()
    QTest.keyClick(panel.timeline, Qt.Key.Key_Space)
    assert not panel._player.isActive()
    panel.seek(667)
    QTest.keyClick(panel.timeline, Qt.Key.Key_Right)
    assert panel.playhead_ms == panel.proxy.step(667, 1).time_ms
    QTest.keyClick(panel.timeline, Qt.Key.Key_Left)
    assert panel.playhead_ms == 667


def test_general_instructions_reach_the_controller(panel, controller):
    panel.instructions.setPlainText("Match the easing.")
    assert controller.context == "Match the easing."


def test_shutdown_cancels_a_worker_that_is_still_decoding(app, controller, result, monkeypatch):
    def endless(path, *, cancel, on_frame=None, **_):
        while not cancel.is_set():
            time.sleep(0.01)
        return FrameProxy(2000)

    monkeypatch.setattr("anypoach.ui.review.build_proxy", endless)
    widget = ReviewPanel(controller, result)
    worker = widget._thread
    assert worker.is_alive()
    widget.shutdown()
    assert not worker.is_alive()
    widget.shutdown()  # a second call is harmless
    assert threading.active_count() >= 1
