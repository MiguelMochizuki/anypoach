"""Quantized weighted color histogram."""
from __future__ import annotations

import numpy as np


def extract_palette(frame: np.ndarray, size: float = 6) -> list[str]:
    """Return the dominant colors of a frame, most frequent first.

    Pixels are grouped into 4-bit-per-channel buckets and each bucket is reported as the rounded average
    of its pixels. Ties keep the order in which the colors first appear.

    Args:
        frame: RGB or RGBA image as a `(height, width, channels)` uint8 array.
        size: How many colors to return (rounded and clamped to 1-12).

    Returns:
        Uppercase hex strings such as `#1A2B3C`.
    """
    size = max(1, min(12, round(size)))
    px = frame.reshape(-1, frame.shape[-1])[:, :3].astype(np.int64)
    keys = ((px[:, 0] >> 4) << 8) | ((px[:, 1] >> 4) << 4) | (px[:, 2] >> 4)
    unique, first, inverse, counts = np.unique(keys, return_index=True, return_inverse=True, return_counts=True)
    sums = np.stack([np.bincount(inverse, weights=px[:, c], minlength=len(unique)) for c in range(3)], axis=1)
    # Highest count first; ties keep the order in which the colors first appear.
    order = sorted(range(len(unique)), key=lambda i: (-counts[i], first[i]))[:size]
    out = []
    for i in order:
        channels = [int((2 * int(sums[i, c]) + counts[i]) // (2 * counts[i])) for c in range(3)]  # round half up
        out.append("#" + "".join(f"{v:02X}" for v in channels))
    return out
