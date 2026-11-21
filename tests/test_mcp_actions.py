"""Click and drag candidates derived from a pointer trace."""
from anypoach.mcp.actions import summarize_pointer_actions


def ev(t, kind, x=0.5, y=0.5, button="left", inside=True):
    return {"timeMs": t, "kind": kind, "x": x, "y": y, "button": button, "withinCapture": inside}


def trace(*events, **extra):
    return {"available": True, "boundsWidth": 800, "boundsHeight": 600, "events": list(events), **extra}


def kinds(value):
    return [(a["kind"], a["button"], a["timeMs"], a["durationMs"]) for a in summarize_pointer_actions(value)["actions"]]


def test_press_and_release_in_place_is_a_click():
    assert kinds(trace(ev(900, "down"), ev(980, "up"))) == [("click", "left", 900, 80)]


def test_moving_seven_pixels_or_leaving_the_capture_is_a_drag():
    assert kinds(trace(ev(0, "down", 0.5), ev(10, "drag", 0.5 + 7 / 800), ev(20, "up", 0.5 + 7 / 800))) == [("drag", "left", 0, 20)]
    assert kinds(trace(ev(0, "down", 0.5), ev(10, "drag", 0.5 + 4 / 800), ev(20, "up", 0.5 + 4 / 800))) == [("click", "left", 0, 20)]
    assert kinds(trace(ev(0, "down", 0.99), ev(10, "drag", 1, inside=False), ev(20, "up", 0.99))) == [("drag", "left", 0, 20)]
    assert kinds(trace(ev(0, "down"), ev(10, "up", inside=False))) == [("drag", "left", 0, 10)]


def test_buttons_are_tracked_independently():
    got = kinds(trace(ev(0, "down"), ev(5, "down", button="right"), ev(9, "up", button="right"), ev(20, "up")))
    assert got == [("click", "right", 5, 4), ("click", "left", 0, 20)]


def test_down_outside_the_capture_and_unmatched_events_are_ignored():
    assert kinds(trace(ev(0, "down", inside=False), ev(5, "up"), ev(9, "drag"), ev(11, "move"))) == []
    assert kinds(trace(ev(0, "down"))) == []  # an incomplete press is not an action


def test_unavailable_or_invalid_traces_report_nothing():
    for value in (None, {"available": False, "events": []}, {"events": [{"kind": "wiggle"}]}, "x", {"events": [ev(0, "down", x=2)]}):
        assert summarize_pointer_actions(value) == {"available": False, "samplingBased": True, "truncated": False, "actions": []}


def test_result_shape_matches_the_ts_server():
    result = summarize_pointer_actions(trace(ev(0, "down"), ev(10, "up", 0.6, 0.7), truncated=True))
    assert result == {"available": True, "samplingBased": True, "truncated": True, "actions": [{
        "kind": "click", "button": "left", "timeMs": 0, "durationMs": 10, "releaseWithinCapture": True,
        "start": {"x": 0.5, "y": 0.5}, "end": {"x": 0.6, "y": 0.7}}]}
