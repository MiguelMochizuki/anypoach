"""Pointer-trace parsing and click/drag summary (port of summarizePointerActions in packages/mcp-server)."""
from __future__ import annotations

import math
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

Button = Literal["left", "right", "other"]
Num = int | float  # keeps JSON integers as integers, like JavaScript numbers


class TraceEvent(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")
    timeMs: Num = Field(ge=0)
    kind: Literal["move", "down", "up", "drag"]
    x: Num = Field(ge=0, le=1)
    y: Num = Field(ge=0, le=1)
    button: Button | None = None
    withinCapture: bool | None = None


class Trace(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")
    available: bool | None = None
    truncated: bool | None = None
    boundsWidth: Num | None = Field(default=None, gt=0)
    boundsHeight: Num | None = Field(default=None, gt=0)
    sampleCount: int | None = Field(default=None, ge=0)
    insideSampleCount: int | None = Field(default=None, ge=0)
    buttonSampleCount: int | None = Field(default=None, ge=0)
    events: list[TraceEvent]


def parse_trace(value: Any) -> Trace | None:
    try:
        return Trace.model_validate(value)
    except ValidationError:
        return None


def event_json(event: TraceEvent) -> dict[str, Any]:
    """Key order and omitted-when-absent fields like the JS server's parsed objects."""
    return event.model_dump(exclude_none=True)


def summarize_pointer_actions(value: Any) -> dict[str, Any]:
    """Condense sampled pointer edges into coordinate-level clicks and drags."""
    trace = parse_trace(value)
    if trace is None or trace.available is False:
        return {"available": False, "samplingBased": True, "truncated": False, "actions": []}
    pending: dict[str, dict[str, Any]] = {}
    actions: list[dict[str, Any]] = []
    for event in trace.events:
        button = event.button or "other"
        if event.kind == "down":
            if event.withinCapture is not False:
                pending[button] = {"start": event, "moved": False, "outside": False}
            continue
        action = pending.get(button)
        if action is None:
            continue
        if event.kind == "drag":
            action["moved"] = True
            action["outside"] = action["outside"] or event.withinCapture is False
            continue
        if event.kind != "up":
            continue
        start = action["start"]
        distance = math.hypot((event.x - start.x) * (trace.boundsWidth or 1), (event.y - start.y) * (trace.boundsHeight or 1))
        is_drag = (action["moved"] and (distance >= 6 or action["outside"])) or event.withinCapture is False
        actions.append({
            "kind": "drag" if is_drag else "click", "button": button, "timeMs": start.timeMs,
            "durationMs": max(0, event.timeMs - start.timeMs), "releaseWithinCapture": event.withinCapture is not False,
            "start": {"x": start.x, "y": start.y}, "end": {"x": event.x, "y": event.y}})
        del pending[button]
    return {"available": True, "samplingBased": True, "truncated": trace.truncated or False, "actions": actions}
