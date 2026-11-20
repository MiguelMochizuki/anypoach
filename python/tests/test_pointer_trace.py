from anypoach.pointer.trace import PointerTrace, PointerTraceBuffer, PointerTraceEvent, Rect


def event(t=0, kind="move", x=0.5, y=0.5, button=None, inside=True):
    return PointerTraceEvent(t, kind, x, y, button, inside)


def test_buffer_counts_samples_and_truncates_at_the_limit():
    buffer = PointerTraceBuffer(max_events=2)
    buffer.record_sample(inside=True, button_held=False)
    buffer.record_sample(inside=True, button_held=True)
    buffer.record_sample(inside=False, button_held=False)
    assert (buffer.sample_count, buffer.inside_sample_count, buffer.button_sample_count) == (3, 2, 1)
    for t in range(3):
        buffer.append(event(t))
    assert len(buffer.events) == 2 and buffer.truncated


def test_default_limit_is_5000_events():
    buffer = PointerTraceBuffer()
    for t in range(5001):
        buffer.append(event(t))
    assert len(buffer.events) == 5000 and buffer.truncated


def test_trace_json_matches_the_brief_contract():
    trace = PointerTrace(True, Rect(0, 0, 800, 600), 1000 / 120, 3, 2, 1, False, [event(5, "down", 0.1, 0.2, "left")])
    assert trace.to_json() == {
        "available": True, "coordinateSpace": "normalized-capture-bounds", "origin": "top-left",
        "boundsWidth": 800, "boundsHeight": 600, "sampleIntervalMs": 1000 / 120, "sampleCount": 3,
        "insideSampleCount": 2, "buttonSampleCount": 1, "scrollCaptured": False, "truncated": False,
        "events": [{"timeMs": 5, "kind": "down", "x": 0.1, "y": 0.2, "button": "left", "withinCapture": True}]}
    assert "button" not in event().to_json()


def test_unavailable_trace_says_so():
    trace = PointerTrace.unavailable(Rect(0, 0, 10, 20))
    assert trace.to_json()["available"] is False and trace.to_json()["events"] == []
    assert trace.to_json()["sampleIntervalMs"] == 1000 / 120
