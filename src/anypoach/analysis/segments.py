"""Splits a clip's frame-to-frame differences into motion segments, one per interaction."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class SegmentSpan:
    """One stretch of motion, in frame indices (`deltas[i]` is the change into frame `i + 1`).

    Attributes:
        start: First frame of the segment (the frame before the first active change).
        end: Last frame, after the slack that lets the movement settle.
        peak: The frame before the largest change inside the segment.
        strength: That largest change, from 0 to 1.
    """
    start: int
    end: int
    peak: int
    strength: float


def find_segments(deltas: Sequence[float], times_ms: Sequence[int], *, floor: float = 0.008, merge_ms: int = 400,
                  slack_ms: int = 250) -> list[SegmentSpan]:
    """Find the stretches of the clip where something moves.

    A change is active when it reaches `floor`. Active stretches closer than `merge_ms` are one segment, and each
    segment runs `slack_ms` past its last active change so the movement can settle (never into the next segment).

    Args:
        deltas: Change into each frame after the first; `len(times_ms) == len(deltas) + 1`.
        times_ms: Time of every sampled frame, in milliseconds.
        floor: Smallest change that counts as movement.
        merge_ms: Stretches closer than this are joined.
        slack_ms: Time kept after the last active change.

    Returns:
        The segments in time order; empty when nothing reaches `floor`.
    """
    runs: list[list[int]] = []
    for index, delta in enumerate(deltas):
        if delta >= floor:
            if runs and runs[-1][1] == index - 1:
                runs[-1][1] = index
            else:
                runs.append([index, index])
    merged: list[list[int]] = []
    for first, last in runs:
        if merged and times_ms[first] - times_ms[merged[-1][1] + 1] < merge_ms:
            merged[-1][1] = last
        else:
            merged.append([first, last])
    spans = []
    for k, (first, last) in enumerate(merged):
        limit = times_ms[last + 1] + slack_ms
        ceiling = merged[k + 1][0] - 1 if k + 1 < len(merged) else len(times_ms) - 1
        end = last + 1
        while end < ceiling and times_ms[end + 1] <= limit:
            end += 1
        peak = max(range(first, last + 1), key=lambda i: deltas[i])
        spans.append(SegmentSpan(first, end, peak, deltas[peak]))
    return spans
