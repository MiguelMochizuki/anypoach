"""Keyframe selection."""
from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

Kind = Literal["start", "peak", "settled"]


def choose_keyframes(deltas: Sequence[float], count: int) -> list[tuple[Kind, int]]:
    """`deltas[i]` is the change into frame i+1. Indices keep the frame before the largest change,
    so the golden files stay comparable."""
    if count == 1:
        return [("start", 0)]
    peak_delta = max(deltas)
    if peak_delta < 0.00002:  # codec noise in an otherwise stationary recording
        return [("start", 0)]
    peak = max(1, list(deltas).index(peak_delta))
    meaningful = max(0.008, peak_delta * 0.12)
    start = next((i for i, d in enumerate(deltas) if d >= meaningful), 0)
    settle = max(0.003, peak_delta * 0.08)
    settled = count - 1
    quiet = min(3, max(1, len(deltas) - peak))  # quiet tail of three intervals, or what is left
    for i in range(peak + quiet, count):
        tail = list(deltas[i - quiet + 1 : i + 1])
        if len(tail) == quiet and all(d <= settle for d in tail):
            settled = i
            break
    chosen: dict[int, Kind] = {start: "start"}
    if peak != start and peak != settled:
        chosen[peak] = "peak"
    if settled != start and settled != peak:
        chosen[settled] = "settled"
    return sorted(((kind, index) for index, kind in chosen.items()), key=lambda item: item[1])
