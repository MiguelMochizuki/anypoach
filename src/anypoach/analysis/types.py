"""Result types; `to_json` produces the camelCase JSON stored in briefs."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from .motion import MotionTiming


@dataclass(frozen=True)
class Keyframe:
    """A frame chosen to represent the clip.

    Attributes:
        kind: `start` (movement begins), `peak` (just before the biggest change), or `settled` (calm again,
        or the last frame when it never calms down).
        time_ms: Moment in the clip, in milliseconds.
        image_path: PNG written for this frame.
        motion: Change from the previous sample, from 0 to 1.
    """
    kind: Literal["start", "peak", "settled"]
    time_ms: int
    image_path: str
    motion: float

    def to_json(self) -> dict[str, Any]:
        """Return the camelCase dictionary stored in briefs."""
        return {"kind": self.kind, "timeMs": self.time_ms, "imagePath": self.image_path, "motion": self.motion}


@dataclass(frozen=True)
class CaptureInfo:
    """The real size of what was captured, so an assistant can tell a reduced image from the original.

    Attributes:
        width_px: Native width of the video or image in pixels.
        height_px: Native height in pixels.
        device_scale: Screen scale factor (2.0 on a 200% display), or None when it is not known.
        image_max_size: Longest side, in pixels, that the keyframe images were reduced to.
    """
    width_px: int
    height_px: int
    device_scale: float | None = None
    image_max_size: int = 1280

    def to_json(self) -> dict[str, Any]:
        """Return the camelCase dictionary stored in briefs."""
        return {"widthPx": self.width_px, "heightPx": self.height_px, "deviceScale": self.device_scale,
                "imageMaxSize": self.image_max_size}


@dataclass(frozen=True)
class InspectionResult:
    """Everything learned from analyzing one video or image.

    Attributes:
        media_type: Whether the source was a `video` or an `image`.
        source_path: Absolute path of the analyzed file.
        duration_ms: Length of the clip in milliseconds (0 for images).
        keyframes: Chosen frames, in time order.
        palette: Dominant colors as hex strings.
        timing: Estimated duration and easing of the main movement.
        pointer_trace: Pointer samples recorded alongside the clip, when there are any.
        annotations: Notes pinned to timestamps, when there are any.
        capture: Native size and screen scale of the media, when known.
    """
    media_type: Literal["video", "image"]
    source_path: str
    duration_ms: int
    keyframes: list[Keyframe]
    palette: list[str]
    timing: MotionTiming
    pointer_trace: dict[str, Any] | None = field(default=None)
    annotations: list[dict[str, Any]] | None = field(default=None)
    capture: CaptureInfo | None = field(default=None)

    def to_json(self) -> dict[str, Any]:
        """Return the camelCase dictionary stored in briefs; optional parts appear only when set."""
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
        if self.capture is not None:
            out["capture"] = self.capture.to_json()
        return out


@dataclass(frozen=True)
class DragFrame:
    """One frame captured after a drag was released.

    Attributes:
        time_ms: Moment in the clip, in milliseconds.
        png: The frame as PNG bytes.
    """
    time_ms: float
    png: bytes


@dataclass(frozen=True)
class DragFrames:
    """Frames sampled after a drag was released.

    Attributes:
        end_time_ms: Last moment frames may come from: just before the next recorded drag or the end of the clip.
        frames: Frames in time order; empty when the release is already past `end_time_ms`.
    """
    end_time_ms: float
    frames: list[DragFrame]
