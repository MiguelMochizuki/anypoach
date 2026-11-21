"""Motion segments from a difference series. `deltas[i]` is the change into frame i + 1, sampled at 12 per second."""
from anypoach.analysis.segments import SegmentSpan, find_segments


def series(count, bursts):
    """`count` deltas (and `count + 1` times) with `{start_index: [values...]}` bursts written in."""
    deltas = [0.0] * count
    for start, values in bursts.items():
        deltas[start:start + len(values)] = values
    return deltas, [round(i * 1000 / 12) for i in range(count + 1)]


def test_a_static_series_has_no_segments():
    for level in (0.0, 0.007):
        _, times = series(40, {})
        assert find_segments([level] * 40, times) == []


def test_one_burst_is_one_span_with_slack():
    deltas, times = series(40, {10: [0.02, 0.05, 0.2, 0.1, 0.03, 0.01]})
    assert find_segments(deltas, times) == [SegmentSpan(start=10, end=19, peak=12, strength=0.2)]


def test_bursts_300_ms_apart_merge_and_500_ms_apart_do_not():
    near, times = series(60, {10: [0.1, 0.1, 0.1], 16: [0.3, 0.1]})
    assert len(find_segments(near, times)) == 1
    far, times = series(60, {10: [0.1, 0.1, 0.1], 20: [0.3, 0.1]})
    assert [s.start for s in find_segments(far, times)] == [10, 20]


def test_a_small_hover_next_to_a_big_movement_is_its_own_span():
    deltas, times = series(80, {10: [0.2] * 5, 60: [0.01] * 3})
    big, small = find_segments(deltas, times)
    assert big.strength == 0.2 and small.strength == 0.01 and small.start == 60


def test_spans_stay_inside_the_clip():
    deltas, times = series(30, {0: [0.1, 0.1], 29: [0.1]})
    first, last = find_segments(deltas, times)
    assert first.start == 0 and last.end == 30 and first.end < last.start


def test_one_sample_is_enough_to_start_a_span():
    deltas, times = series(20, {5: [0.05]})
    assert find_segments(deltas, times)[0].start == 5
