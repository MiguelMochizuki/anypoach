import numpy as np
import pytest

from poach.analysis.motion import approximate_timing, pixel_difference

TIMES = [i * 100 for i in range(11)]


def ease_out(t):
    return 1 - (1 - t) ** 3


def test_pixel_difference_is_normalized_luma_change():
    black, white = np.zeros((4, 4, 3), np.uint8), np.full((4, 4, 3), 255, np.uint8)
    assert pixel_difference(black, black) == 0
    assert pixel_difference(black, white) == pytest.approx(1.0)
    with pytest.raises(ValueError, match="dimensions"):
        pixel_difference(black, np.zeros((2, 2, 3), np.uint8))


def test_ease_out_fits_the_default_expo_curve():
    deltas = [ease_out((i + 1) / 10) - ease_out(i / 10) for i in range(10)]
    timing = approximate_timing(TIMES, deltas, 0, 1000)
    assert (timing.duration_ms, timing.bezier) == (1000, (0.16, 1, 0.3, 1))
    assert timing.token == "1000ms • cubic-bezier(0.16, 1, 0.3, 1)"


def test_linear_motion_fits_a_straight_curve():
    timing = approximate_timing(TIMES, [0.1] * 10, 0, 1000)
    assert timing.bezier == (0.16, 0.3, 0.3, 0.7)
    assert timing.token == "1000ms • cubic-bezier(0.16, 0.3, 0.3, 0.7)"


def test_no_duration_or_too_few_samples_report_no_easing():
    none = approximate_timing(TIMES, [0.1] * 10, 0, 0)
    assert (none.duration_ms, none.bezier, none.token) == (0, None, "No measurable motion in sampled frames")
    few = approximate_timing([0, 100], [0.5], 0, 100)
    assert (few.duration_ms, few.bezier, few.token) == (100, None, "100ms • insufficient samples to estimate easing")
