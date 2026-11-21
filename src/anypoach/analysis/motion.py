"""Frame-to-frame motion and easing estimate."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

LUMA = np.array([0.2126, 0.7152, 0.0722])


@dataclass(frozen=True)
class MotionTiming:
    duration_ms: int
    bezier: tuple[float, float, float, float] | None
    token: str


def pixel_difference(left: np.ndarray, right: np.ndarray) -> float:
    """Mean absolute luma difference of two RGB frames, normalized to 0-1."""
    if left.shape != right.shape:
        raise ValueError("Frame dimensions must match to compute motion")
    luma = left.astype(np.float64) @ LUMA - right.astype(np.float64) @ LUMA
    return float(np.abs(luma).sum() / (left.shape[0] * left.shape[1] * 255))


def _g(value: float) -> str:
    return f"{value:g}"


def approximate_timing(times_ms: Sequence[int], deltas: Sequence[float], start_ms: int, duration_ms: int) -> MotionTiming:
    """Fit a cubic Bézier to cumulative frame-change progress. `deltas[i]` is the change into frame i+1."""
    if duration_ms <= 0 or len(deltas) == 0:
        return MotionTiming(max(0, duration_ms), None, "No measurable motion in sampled frames")
    end_ms = start_ms + duration_ms
    selected = [(t, deltas[i - 1] if i >= 1 and i - 1 < len(deltas) else 0.0)
                for i, t in enumerate(times_ms) if start_ms <= t <= end_ms]
    movement = [d for _, d in selected]
    total = sum(movement)
    if total < 1e-6 or len(selected) < 3:
        return MotionTiming(duration_ms, None, f"{duration_ms}ms • insufficient samples to estimate easing")
    cumulative = [0.0]
    for value in movement[1:]:
        cumulative.append(cumulative[-1] + value)
    xs = np.array([min(1.0, max(0.0, (t - start_ms) / duration_ms)) for t, _ in selected])
    ys = np.array(cumulative) / total

    def error(x1: float, y1: float, x2: float, y2: float) -> float:
        estimate = 3 * (1 - xs) ** 2 * xs * y1 + 3 * (1 - xs) * xs**2 * y2 + xs**3
        return float((x1 + x2) * 0.001 + ((estimate - ys) ** 2).sum())

    best, best_error = (0.16, 1.0, 0.3, 1.0), float("inf")
    for i in range(11):
        for j in range(11):
            candidate = (0.16, i / 10, 0.3, j / 10)
            e = error(*candidate)
            if e < best_error:
                best, best_error = candidate, e
    bezier = tuple(round(v, 2) for v in best)
    return MotionTiming(duration_ms, bezier, f"{duration_ms}ms • cubic-bezier({', '.join(_g(v) for v in bezier)})")
