"""Result types; `to_json` produces the camelCase JSON stored in briefs."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from .motion import MotionTiming


@dataclass(frozen=True)
class Keyframe:
    kind: Literal["start", "peak", "settled"]
    time_ms: int
    image_path: str
    motion: float

    def to_json(self) -> dict[str, Any]:
        return {"kind": self.kind, "timeMs": self.time_ms, "imagePath": self.image_path, "motion": self.motion}


@dataclass(frozen=True)
class InspectionResult:
    media_type: Literal["video", "image"]
    source_path: str
    duration_ms: int
    keyframes: list[Keyframe]
    palette: list[str]
    timing: MotionTiming
    pointer_trace: dict[str, Any] | None = field(default=None)
    annotations: list[dict[str, Any]] | None = field(default=None)

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "mediaType": self.media_type, "sourcePath": self.source_path, "durationMs": self.duration_ms,
            "keyframes": [k.to_json() for k in self.keyframes], "palette": self.palette,
            "timing": {"durationMs": self.timing.duration_ms,
                       "bezier": list(self.timing.bezier) if self.timing.bezier else None,
                       "token": self.timing.token},
        }
        if self.pointer_trace is not None:
            out["pointerTrace"] = self.pointer_trace
        if self.annotations is not None:
            out["annotations"] = self.annotations
        return out


@dataclass(frozen=True)
class DragFrame:
    time_ms: float
    png: bytes


@dataclass(frozen=True)
class DragFrames:
    end_time_ms: float
    frames: list[DragFrame]
