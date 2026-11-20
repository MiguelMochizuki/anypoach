"""Pointer-only evidence: types, bounded buffer and JSON that matches the brief contract.

Coordinates are normalized to the captured bounds with a top-left origin. Only pointer
position and mouse-button state are sampled; no keyboard input, scroll or global hooks.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, NamedTuple, Protocol

SAMPLE_INTERVAL_MS = 1000 / 120
MAX_EVENTS = 5_000
Button = Literal["left", "right", "other"]
Kind = Literal["move", "down", "up", "drag"]


class Rect(NamedTuple):
    """Capture bounds in global physical pixels, top-left origin (origin may be negative on multi-monitor setups)."""
    x: float
    y: float
    width: float
    height: float

    def contains(self, px: float, py: float) -> bool:
        return self.x <= px < self.x + self.width and self.y <= py < self.y + self.height


@dataclass(frozen=True)
class PointerSample:
    x: float
    y: float
    buttons: frozenset[Button]


class PointerSource(Protocol):
    """Reads the current pointer position (global physical pixels, top-left origin) and held buttons."""

    def sample(self) -> PointerSample: ...


@dataclass(frozen=True)
class PointerTraceEvent:
    time_ms: int
    kind: Kind
    x: float
    y: float
    button: Button | None
    within_capture: bool

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"timeMs": self.time_ms, "kind": self.kind, "x": self.x, "y": self.y}
        if self.button is not None:
            out["button"] = self.button
        out["withinCapture"] = self.within_capture
        return out


@dataclass
class PointerTraceBuffer:
    max_events: int = MAX_EVENTS
    events: list[PointerTraceEvent] = field(default_factory=list)
    truncated: bool = False
    sample_count: int = 0
    inside_sample_count: int = 0
    button_sample_count: int = 0

    def record_sample(self, *, inside: bool, button_held: bool) -> None:
        self.sample_count += 1
        self.inside_sample_count += inside
        self.button_sample_count += button_held

    def append(self, event: PointerTraceEvent) -> None:
        if len(self.events) >= self.max_events:
            self.truncated = True
            return
        self.events.append(event)


@dataclass(frozen=True)
class PointerTrace:
    available: bool
    bounds: Rect
    sample_interval_ms: float
    sample_count: int
    inside_sample_count: int
    button_sample_count: int
    truncated: bool
    events: list[PointerTraceEvent]

    @classmethod
    def unavailable(cls, bounds: Rect) -> PointerTrace:
        return cls(False, bounds, SAMPLE_INTERVAL_MS, 0, 0, 0, False, [])

    def to_json(self) -> dict[str, Any]:
        return {
            "available": self.available, "coordinateSpace": "normalized-capture-bounds", "origin": "top-left",
            "boundsWidth": self.bounds.width, "boundsHeight": self.bounds.height,
            "sampleIntervalMs": self.sample_interval_ms, "sampleCount": self.sample_count,
            "insideSampleCount": self.inside_sample_count, "buttonSampleCount": self.button_sample_count,
            "scrollCaptured": False, "truncated": self.truncated, "events": [e.to_json() for e in self.events],
        }
