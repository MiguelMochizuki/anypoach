import threading

import pytest

from anypoach.pointer.recorder import PointerTraceRecorder
from anypoach.pointer.trace import PointerSample, Rect


class Script:
    """A pointer source that replays scripted samples (global physical pixels, top-left origin)."""

    def __init__(self, *samples):
        self.samples, self.index = list(samples), 0

    def sample(self):
        sample = self.samples[min(self.index, len(self.samples) - 1)]
        self.index += 1
        return sample


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def at(x, y, *buttons):
    return PointerSample(x, y, frozenset(buttons))


def run(bounds, *samples, step=0.01):
    clock = Clock()
    recorder = PointerTraceRecorder(bounds, Script(*samples), clock=clock)
    assert recorder.start(spawn=False)
    for _ in samples:
        recorder.poll()
        clock.now += step
    return recorder.stop().to_json()


def kinds(trace):
    return [(e["kind"], e.get("button"), e["timeMs"], round(e["x"], 3), round(e["y"], 3), e["withinCapture"]) for e in trace["events"]]


def test_press_drag_release_inside_the_capture():
    trace = run(Rect(100, 50, 400, 200), at(300, 150), at(300, 150, "left"), at(340, 170, "left"), at(340, 170))
    assert kinds(trace) == [("move", None, 0, 0.5, 0.5, True), ("down", "left", 10, 0.5, 0.5, True),
                            ("drag", "left", 20, 0.6, 0.6, True), ("up", "left", 30, 0.6, 0.6, True)]
    assert (trace["sampleCount"], trace["insideSampleCount"], trace["buttonSampleCount"]) == (4, 4, 2)
    assert trace["available"] and trace["boundsWidth"] == 400 and not trace["truncated"]


def test_moves_are_only_recorded_inside_the_capture_without_buttons():
    trace = run(Rect(0, 0, 100, 100), at(500, 500), at(500, 501), at(50, 50), at(50, 50), at(60, 50))
    assert [(k[0], k[3]) for k in kinds(trace)] == [("move", 0.5), ("move", 0.6)]
    assert trace["insideSampleCount"] == 3 and trace["sampleCount"] == 5


def test_button_edges_outside_the_capture_are_flagged_not_dropped():
    trace = run(Rect(0, 0, 100, 100), at(150, 50, "left"), at(160, 50, "left"), at(160, 50))
    # Like the Swift recorder, the first sample also reports a drag because there is no previous point.
    assert kinds(trace) == [("down", "left", 0, 1.0, 0.5, False), ("drag", "left", 0, 1.0, 0.5, False),
                            ("drag", "left", 10, 1.0, 0.5, False), ("up", "left", 20, 1.0, 0.5, False)]


def test_clamps_to_the_edge_and_orders_simultaneous_buttons():
    trace = run(Rect(0, 0, 100, 100), at(-30, 200, "right", "left"))
    assert kinds(trace) == [("down", "left", 0, 0.0, 1.0, False), ("down", "right", 0, 0.0, 1.0, False),
                            ("drag", "left", 0, 0.0, 1.0, False), ("drag", "right", 0, 0.0, 1.0, False)]


def test_monitor_with_negative_origin_and_hidpi_physical_pixels():
    left_monitor = Rect(-3840, 0, 3840, 2160)  # 2x scaled 1920x1080, positioned left of the primary
    assert kinds(run(left_monitor, at(-1920, 1080)))[0][3:5] == (0.5, 0.5)
    assert kinds(run(Rect(0, 0, 3840, 2160), at(960, 540)))[0][3:5] == (0.25, 0.25)


def test_empty_bounds_or_missing_source_make_an_unavailable_trace():
    for bounds, source in ((Rect(0, 0, 0, 10), Script(at(0, 0))), (Rect(0, 0, 10, 10), None)):
        recorder = PointerTraceRecorder(bounds, source, clock=Clock())
        assert recorder.start(spawn=False) is False
        assert recorder.stop().to_json()["available"] is False


def test_trace_truncates_after_5000_events():
    clock = Clock()
    samples = [at(i % 90, 10) for i in range(5200)]
    recorder = PointerTraceRecorder(Rect(0, 0, 100, 100), Script(*samples), clock=clock)
    recorder.start(spawn=False)
    for _ in samples:
        recorder.poll()
    trace = recorder.stop().to_json()
    assert len(trace["events"]) == 5000 and trace["truncated"] and trace["sampleCount"] == 5200


def test_loop_schedules_by_tick_so_error_does_not_accumulate():
    clock = Clock()
    recorder = None

    def sleep(seconds):
        clock.now += seconds + 0.0004  # every wake-up is late by 0.4 ms
        if clock.now - 100.0 >= 1.0:
            recorder.request_stop()

    recorder = PointerTraceRecorder(Rect(0, 0, 100, 100), Script(at(1, 1)), clock=clock, sleep=sleep)
    recorder.start(spawn=False)
    recorder.run()
    assert recorder.stop().to_json()["sampleCount"] == pytest.approx(120, abs=2)


def test_a_stalled_loop_skips_ahead_instead_of_bursting():
    clock = Clock()
    recorder = None
    calls = 0

    def sleep(seconds):
        nonlocal calls
        calls += 1
        clock.now += 0.5 if calls == 1 else seconds  # the machine stalls for half a second once
        if calls > 10:
            recorder.request_stop()

    recorder = PointerTraceRecorder(Rect(0, 0, 100, 100), Script(at(1, 1)), clock=clock, sleep=sleep)
    recorder.start(spawn=False)
    recorder.run()
    assert recorder.stop().to_json()["sampleCount"] <= 13  # no catch-up burst of ~60 samples


def test_real_thread_starts_samples_and_stops():
    recorder = PointerTraceRecorder(Rect(0, 0, 100, 100), Script(at(1, 1), at(2, 2)))
    assert recorder.start()
    threading.Event().wait(0.3)
    trace = recorder.stop()
    assert trace.sample_count >= 10
    assert recorder.stop().to_json()["sampleCount"] == trace.sample_count  # stopping twice is harmless


@pytest.mark.parametrize("env", [{"XDG_SESSION_TYPE": "wayland", "DISPLAY": ":0"}, {"XDG_SESSION_TYPE": "x11"}])
def test_no_source_on_wayland_or_without_a_display(monkeypatch, env):
    from anypoach import pointer
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    assert pointer.default_source() is None


def test_latest_exposes_the_last_sample_and_the_time_of_the_last_press():
    clock = Clock()
    recorder = PointerTraceRecorder(Rect(0, 0, 100, 100), Script(at(5, 6), at(7, 8, "left"), at(9, 9)), clock=clock)
    assert not recorder.started and recorder.latest() is None
    recorder.start(spawn=False)
    assert recorder.started
    recorder.poll()
    assert recorder.latest() == (at(5, 6), None)
    clock.now += 0.5
    recorder.poll()
    clock.now += 0.5
    recorder.poll()
    assert recorder.latest() == (at(9, 9), 100.5)
