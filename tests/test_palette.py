"""Palette extraction: ordering, rounding, and size limits."""
import numpy as np

from anypoach.analysis.palette import extract_palette


def frame():
    px = []
    for rgb, n in [((255, 0, 0), 3), ((0, 255, 0), 3), ((17, 17, 17), 1), ((18, 18, 18), 1),
                   ((0, 0, 255), 2), ((250, 250, 250), 5)]:
        px += [rgb] * n
    return np.array(px, np.uint8).reshape(5, 3, 3)


def test_orders_by_count_then_first_seen_and_rounds_half_up():
    # (17,17,17) and (18,18,18) share a 4-bit bucket whose mean 17.5 rounds up to 0x12.
    assert extract_palette(frame(), 4) == ["#FAFAFA", "#FF0000", "#00FF00", "#121212"]


def test_size_is_clamped_to_one_through_twelve():
    assert extract_palette(frame(), 99)[-1] == "#0000FF" and len(extract_palette(frame(), 99)) == 5
    assert extract_palette(frame(), 0) == ["#FAFAFA"]
