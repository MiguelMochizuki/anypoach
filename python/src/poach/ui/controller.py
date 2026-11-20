"""UI-independent flow: choose a region, record, analyze, share. Failures become `message`, never exceptions."""
from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any, Literal

from poach.analysis.inspect import inspect_recording
from poach.analysis.types import InspectionResult
from poach.brief.store import share
from poach.capture.backend import CaptureBackend
from poach.capture.recorder import Recorder
from poach.pointer.recorder import PointerTraceRecorder
from poach.pointer.trace import PointerSource, Rect

State = Literal["idle", "recording", "ready"]

_LOOKUP = "Use Poach MCP to call poach_read_brief with briefId {id}. Verify the returned briefId matches."


def physical_rect(start: tuple[float, float], end: tuple[float, float], *, origin: tuple[float, float], dpr: float) -> Rect:
    """Two dragged corners in a screen's logical coordinates -> global physical pixels, normalized so width/height >= 0.
    Assumes one device pixel ratio per screen; `origin` is the screen's logical top-left in the global space."""
    left, right = sorted((start[0], end[0]))
    top, bottom = sorted((start[1], end[1]))
    return Rect((origin[0] + left) * dpr, (origin[1] + top) * dpr, (right - left) * dpr, (bottom - top) * dpr)


def _pointer_guidance(trace: dict[str, Any] | None) -> str:
    if not trace or not trace.get("available"):
        return ("This media has no native pointer trace; do not assume clicks or drags that are not visible in the "
                "video or described in notes.")
    if any(e["kind"] in ("down", "up", "drag") for e in trace["events"]):
        return ("The native pointer trace contains sampled button transitions and may provide click/drag candidates. "
                "Polling can miss or misclassify brief actions; correlate trace events with frames and notes, and do "
                "not infer an interaction's effect from the trace alone.")
    if trace["sampleCount"] > 0:
        return (f"The native pointer sampler collected {trace['sampleCount']} samples, including "
                f"{trace['insideSampleCount']} inside the capture bounds, but observed no button-down, button-up, or "
                "drag events. Do not claim clicks or drags; rely on visible video and notes, and ask if behavior is unclear.")
    return ("A native pointer trace was started but collected no samples. Do not claim clicks or drags; rely on "
            "visible video and notes, and ask if behavior is unclear.")


def handoff_prompt(brief_id: str, trace: dict[str, Any] | None) -> str:
    """The same text the macOS app copies for a video brief (FloatingHUDView.swift), without browser evidence."""
    return (f"{_LOOKUP.format(id=brief_id)} Use its images, pointer trace, and timestamped notes. {_pointer_guidance(trace)} "
            "Match pointer coordinates and timestamps to the frames to identify targets. For a drag, inspect the frames "
            "after release and include visible changes through the end of the response. Use the video and notes to "
            "describe visible results, and ask if behavior is ambiguous. Recreate the recorded interaction in this "
            "project. For video details, call poach_read_moment with the same briefId and timeMs.")


class Controller:
    def __init__(self, backend: CaptureBackend, pointer_source: PointerSource | None, work_dir: Path, *,
                 cache: Path | None = None) -> None:
        self._backend, self._source, self._work, self._cache = backend, pointer_source, Path(work_dir), cache
        self.state: State = "idle"
        self.message = ""
        self.context = ""
        self.annotations: list[dict[str, Any]] = []
        self.result: InspectionResult | None = None
        self._region: Rect | None = None
        self._recorder: Recorder | None = None

    def choose_region(self, region: Rect) -> None:
        self._region = Rect(*region) if region.width >= 2 and region.height >= 2 else None
        self.message = "" if self._region else "Choose an area to record."

    def start(self) -> None:
        if self.state == "recording":
            self.message = "Already recording."
            return
        if self._region is None:
            self.message = "Choose an area to record first."
            return
        pointer = PointerTraceRecorder(self._region, self._source)
        recorder = Recorder(self._backend, pointer, self._work)
        try:
            recorder.start(self._region)
        except OSError as error:
            self.message = f"Could not start recording: {error}"
            return
        self._recorder, self.state, self.message, self.result = recorder, "recording", "", None

    def stop(self) -> InspectionResult | None:
        recorder = self._recorder
        if self.state != "recording" or recorder is None:
            self.message = "There is no recording to stop."
            return None
        self._recorder, self.state = None, "idle"
        try:
            recording = recorder.stop()
            result = inspect_recording(recording.path, output_dir=self._work / "frames")
        except PermissionError:
            self.message = "Poach cannot capture the screen. Check the screen recording permission and try again."
            return None
        except (ValueError, OSError) as error:
            self.message = f"Could not finish the recording: {error}"
            return None
        self.result = dataclasses.replace(result, pointer_trace=recording.trace.to_json())
        self.state, self.message = "ready", ""
        return self.result

    def copy_handoff(self) -> str:
        """Writes the brief and returns the prompt for the assistant (the window puts it on the clipboard)."""
        if self.result is None:
            self.message = "Record something first."
            return ""
        try:
            brief_id = share(self.result, self.context, self.annotations, cache=self._cache)
        except OSError as error:
            self.message = f"Could not share: {error}"
            return ""
        self.message = ""
        return handoff_prompt(brief_id, self.result.pointer_trace)
