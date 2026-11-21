"""Cursor and click ring drawn by us from the pointer trace (screen grabs do not include them)."""
from __future__ import annotations

import numpy as np

CLICK_RING_SECONDS = 0.4
_RING_COLOR = np.array([255, 160, 64], np.float32)  # BGR


def _stamp(pixels: np.ndarray, mask: np.ndarray, x0: int, y0: int, color: tuple[int, int, int]) -> None:
    """Paint `color` where `mask` is set, with its top-left at (x0, y0); anything outside the frame is clipped."""
    height, width = pixels.shape[:2]
    top, left = max(0, -y0), max(0, -x0)
    bottom, right = min(mask.shape[0], height - y0), min(mask.shape[1], width - x0)
    if bottom <= top or right <= left:
        return
    window = pixels[y0 + top:y0 + bottom, x0 + left:x0 + right]
    window[mask[top:bottom, left:right], :3] = color
    window[mask[top:bottom, left:right], 3] = 255


def draw_cursor(pixels: np.ndarray, x: float, y: float, scale: float) -> None:
    """White arrow with a black outline, tip at (x, y), size multiplied by `scale`."""
    rows, cols = max(4, round(17 * scale)), max(3, round(11 * scale))
    fill = np.zeros((rows, cols), bool)
    for dy in range(rows):
        fill[dy, : min(cols, round(dy / rows * 0.65 * cols * 1.5) + 1)] = True
    pad = max(1, round(scale))
    outline = np.zeros((rows + 2 * pad, cols + 2 * pad), bool)
    for dy in range(-pad, pad + 1):
        for dx in range(-pad, pad + 1):
            outline[pad + dy:pad + dy + rows, pad + dx:pad + dx + cols] |= fill
    ox, oy = round(x) - pad, round(y) - pad
    _stamp(pixels, outline, ox, oy, (0, 0, 0))
    _stamp(pixels, fill, round(x), round(y), (255, 255, 255))


def draw_click_ring(pixels: np.ndarray, x: float, y: float, age_s: float, scale: float) -> None:
    """Expanding, fading ring around a click; nothing once `age_s` passes CLICK_RING_SECONDS."""
    if not 0 <= age_s <= CLICK_RING_SECONDS:
        return
    progress = age_s / CLICK_RING_SECONDS
    radius, half = (8 + 24 * progress) * scale, max(1.0, scale)
    reach = int(radius + half) + 1
    x0, y0 = round(x) - reach, round(y) - reach
    size = 2 * reach + 1
    yy, xx = np.ogrid[:size, :size]
    ring = np.abs(np.hypot(xx - reach, yy - reach) - radius) <= half
    height, width = pixels.shape[:2]
    top, left = max(0, -y0), max(0, -x0)
    bottom, right = min(size, height - y0), min(size, width - x0)
    if bottom <= top or right <= left:
        return
    window = pixels[y0 + top:y0 + bottom, x0 + left:x0 + right]
    mask = ring[top:bottom, left:right]
    alpha = 0.85 * (1 - progress)
    window[mask, :3] = (window[mask, :3] * (1 - alpha) + _RING_COLOR * alpha).astype(np.uint8)
