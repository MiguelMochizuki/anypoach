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
        """Whether the point lies inside the rectangle (right and bottom edges excluded)."""
        return self.x <= px < self.x + self.width and self.y <= py < self.y + self.height


@dataclass(frozen=True)
class PointerSample:
    """One reading of the pointer.

    Attributes:
        x: Horizontal position in global physical pixels.
        y: Vertical position in global physical pixels, from the top.
        buttons: Buttons held down at that moment.
    """
    x: float
    y: float
    buttons: frozenset[Button]


class PointerSource(Protocol):
    """Reads the current pointer position (global physical pixels, top-left origin) and held buttons."""

    def sample(self) -> PointerSample:
        """Read the pointer now."""


@dataclass(frozen=True)
class PointerTraceEvent:
    """A press, release, move, or drag in the trace.

    Attributes:
        time_ms: Milliseconds since sampling started.
        kind: `move`, `down`, `up`, or `drag`.
        x: Horizontal position, 0 to 1 across the capture bounds.
        y: Vertical position, 0 to 1 down the capture bounds.
        button: The button involved; None for moves.
        within_capture: Whether the pointer was inside the capture bounds.
    """
    time_ms: int
    kind: Kind
    x: float
    y: float
    button: Button | None
    within_capture: bool

    def to_json(self) -> dict[str, Any]:
        """Return the brief's camelCase form of the event; `button` appears only when set."""
        out: dict[str, Any] = {"timeMs": self.time_ms, "kind": self.kind, "x": self.x, "y": self.y}
        if self.button is not None:
            out["button"] = self.button
        out["withinCapture"] = self.within_capture
        return out


@dataclass
class PointerTraceBuffer:
    """Collects events up to a limit and counts every sample, kept or not.

    Attributes:
        max_events: Most events kept; later ones are dropped and `truncated` is set.
        events: The kept events, in time order.
        truncated: Whether any event was dropped.
        sample_count: Samples taken.
        inside_sample_count: Samples inside the capture bounds.
        button_sample_count: Samples with a button held.
    """
    max_events: int = MAX_EVENTS
    events: list[PointerTraceEvent] = field(default_factory=list)
    truncated: bool = False
    sample_count: int = 0
    inside_sample_count: int = 0
    button_sample_count: int = 0

    def record_sample(self, *, inside: bool, button_held: bool) -> None:
        """Count one sample, and whether it was inside the bounds and had a button held."""
        self.sample_count += 1
        self.inside_sample_count += inside
        self.button_sample_count += button_held

    def append(self, event: PointerTraceEvent) -> None:
        """Keep `event`, or drop it and mark the buffer truncated once the limit is reached."""
        if len(self.events) >= self.max_events:
            self.truncated = True
            return
        self.events.append(event)


@dataclass(frozen=True)
class PointerTrace:
    """The pointer evidence for one recording.

    Attributes:
        available: False when the pointer could not be sampled (no source, empty bounds, Wayland).
        bounds: Capture area the positions are normalized to.
        sample_interval_ms: Time between samples.
        sample_count: Samples taken.
        inside_sample_count: Samples inside the capture bounds.
        button_sample_count: Samples with a button held.
        truncated: Whether events beyond the limit were dropped.
        events: Presses, releases, moves, and drags.
    """
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
        """Return an empty trace marked unavailable, for when the pointer could not be sampled."""
        return cls(False, bounds, SAMPLE_INTERVAL_MS, 0, 0, 0, False, [])

    def to_json(self) -> dict[str, Any]:
        """Return the brief's camelCase form of the trace, as stored in `evidence.pointerTrace`."""
        return {
            "available": self.available, "coordinateSpace": "normalized-capture-bounds", "origin": "top-left",
            "boundsWidth": self.bounds.width, "boundsHeight": self.bounds.height,
            "sampleIntervalMs": self.sample_interval_ms, "sampleCount": self.sample_count,
            "insideSampleCount": self.inside_sample_count, "buttonSampleCount": self.button_sample_count,
            "scrollCaptured": False, "truncated": self.truncated, "events": [e.to_json() for e in self.events],
        }
