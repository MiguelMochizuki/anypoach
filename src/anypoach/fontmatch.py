"""Match a line of text in a screenshot to the closest installed font, by comparing how the letters look.

No text recognition is involved: the user says what the line reads, each candidate font renders those words, and the
renders are compared with the crop by ink shape. It is an approximation, meant to give an assistant a sensible
font family to start from.
"""
from __future__ import annotations

import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass

import numpy as np

SIGNATURE_SIZE = (48, 192)  # rows, columns every comparison is scaled to
ASPECT_WEIGHT = 0.4
INK_FLOOR = 0.25  # of the strongest difference from the background


@dataclass(frozen=True)
class FontMatch:
    """A candidate font and how far its render is from the crop (0 is identical, larger is worse)."""
    family: str
    distance: float


def _resize(array: np.ndarray, rows: int, cols: int) -> np.ndarray:
    """Bilinear resize of a 2-D array."""
    height, width = array.shape
    y, x = np.linspace(0, height - 1, rows), np.linspace(0, width - 1, cols)
    y0, x0 = np.floor(y).astype(int), np.floor(x).astype(int)
    y1, x1 = np.minimum(y0 + 1, height - 1), np.minimum(x0 + 1, width - 1)
    fy, fx = (y - y0)[:, None], (x - x0)[None, :]
    top = array[np.ix_(y0, x0)] * (1 - fx) + array[np.ix_(y0, x1)] * fx
    bottom = array[np.ix_(y1, x0)] * (1 - fx) + array[np.ix_(y1, x1)] * fx
    return top * (1 - fy) + bottom * fy


def signature(gray: np.ndarray) -> tuple[np.ndarray, float] | None:
    """The ink of a grayscale image, whatever the colors: its shape at a fixed size and its width over height.

    The background is the median of the border; ink is whatever differs from it. Light-on-dark and dark-on-light
    text give the same signature.

    Returns:
        None when the image has no ink (or is smaller than 3x3 pixels).
    """
    if gray.ndim != 2 or min(gray.shape) < 3:
        return None
    values = gray.astype(np.float64)
    border = np.concatenate([values[0], values[-1], values[:, 0], values[:, -1]])
    difference = np.abs(values - np.median(border))
    peak = difference.max()
    if peak <= 0:
        return None
    ink = difference / peak
    rows, cols = np.where(ink >= INK_FLOOR)
    if rows.size == 0:
        return None
    box = ink[rows.min():rows.max() + 1, cols.min():cols.max() + 1]
    return _resize(box, *SIGNATURE_SIZE), box.shape[1] / box.shape[0]


def distance(a: np.ndarray, b: np.ndarray) -> float:
    """How different two grayscale images of text look; None-ink images are infinitely far."""
    first, second = signature(a), signature(b)
    if first is None or second is None:
        return math.inf
    return float(np.mean(np.abs(first[0] - second[0])) + ASPECT_WEIGHT * abs(math.log(first[1] / second[1])))


def rank(crop: np.ndarray, text: str, families: Iterable[str], render: Callable[[str, str], np.ndarray],
         limit: int = 5) -> list[FontMatch]:
    """The `limit` installed fonts whose render of `text` looks most like `crop`, closest first.

    Args:
        crop: Grayscale crop of one line of text.
        text: What the line reads.
        families: Candidate font family names.
        render: Draws `text` in a family and returns it as a grayscale array; a failing family is skipped.
        limit: How many to return.
    """
    scored = []
    for family in families:
        try:
            rendered = render(family, text)
        except (ValueError, OSError):
            continue
        score = distance(crop, rendered)
        if math.isfinite(score):
            scored.append(FontMatch(family, score))
    return sorted(scored, key=lambda match: match.distance)[:limit]
