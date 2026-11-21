"""Keyframe selection from per-sample motion."""
from anypoach.analysis.keyframes import choose_keyframes


def test_single_frame_or_codec_noise_gives_only_start():
    assert choose_keyframes([], 1) == [("start", 0)]
    assert choose_keyframes([0.00001] * 5, 6) == [("start", 0)]


def test_motion_then_rest_gives_start_peak_settled():
    deltas = [0, 0.03, 0.2, 0.05, 0.004, 0.001, 0.001, 0.001, 0, 0]
    assert choose_keyframes(deltas, 11) == [("start", 1), ("peak", 2), ("settled", 6)]


def test_start_coinciding_with_peak_drops_the_peak():
    assert choose_keyframes([0.01, 0.5, 0.4], 4) == [("start", 1), ("settled", 3)]


def test_peak_coinciding_with_settled_drops_both():
    assert choose_keyframes([0.5], 2) == [("start", 0)]
