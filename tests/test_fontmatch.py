"""Font matching by ink shape, with synthetic 'fonts' drawn in numpy."""
import numpy as np
import pytest

from anypoach.fontmatch import distance, rank, signature


def line(strokes, width=120, height=30, ink=0, paper=255, noise=0.0, seed=0):
    """A fake text line: `strokes` is a list of (x, w) vertical bars of the full height."""
    image = np.full((height, width), paper, np.float64)
    for x, w in strokes:
        image[4:height - 4, x:x + w] = ink
    if noise:
        image += np.random.default_rng(seed).normal(0, noise, image.shape)
    return np.clip(image, 0, 255)


THIN = [(10, 2), (30, 2), (50, 2), (70, 2), (90, 2)]
THICK = [(10, 8), (30, 8), (50, 8), (70, 8), (90, 8)]
WIDE = [(10, 3), (50, 3), (90, 3), (130, 3), (170, 3)]


def test_the_same_shape_is_closer_than_a_different_one():
    assert distance(line(THIN), line(THIN)) < distance(line(THIN), line(THICK)) < 1
    assert distance(line(THIN), line(THIN, noise=8)) < distance(line(THIN), line(THICK))


def test_polarity_and_scale_do_not_matter():
    dark_on_light, light_on_dark = line(THICK), line(THICK, ink=255, paper=0)
    assert distance(dark_on_light, light_on_dark) < 0.05
    bigger = np.kron(dark_on_light, np.ones((2, 2)))
    assert distance(dark_on_light, bigger) < 0.1


def test_the_width_of_the_line_counts():
    assert distance(line(THIN, width=200), line(WIDE, width=200)) > distance(line(THIN), line(THIN, width=120))


def test_blank_or_tiny_images_have_no_signature():
    assert signature(np.full((20, 20), 7.0)) is None and signature(np.zeros((2, 2))) is None
    assert distance(np.full((20, 20), 7.0), line(THIN)) == float("inf")


def test_rank_orders_the_candidates_and_skips_failing_families():
    fonts = {"Thin": THIN, "Thick": THICK, "Wide": WIDE}

    def render(family, text):
        if family == "Broken":
            raise OSError("no such font")
        return line(fonts[family], width=200 if family == "Wide" else 120)

    crop = line(THICK, noise=6)
    ranked = rank(crop, "hello", ["Thin", "Broken", "Wide", "Thick"], render, limit=2)
    assert ranked[0].family == "Thick" and len(ranked) == 2
    assert ranked[0].distance < ranked[1].distance


@pytest.mark.parametrize("bad", [np.zeros(5), np.zeros((4, 4, 3))])
def test_not_a_2d_image_is_no_signature(bad):
    assert signature(bad) is None
