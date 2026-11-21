"""UI-independent flow: choose a region, record, analyze, share. Failures become `message`, never exceptions."""
from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any, Literal

from anypoach.analysis.inspect import inspect_recording
from anypoach.analysis.types import InspectionResult
from anypoach.brief.store import share
from anypoach.capture.backend import CaptureBackend, Frame
from anypoach.capture.recorder import Recorder
from anypoach.pointer.recorder import PointerTraceRecorder
from anypoach.pointer.trace import PointerSource, Rect

State = Literal["idle", "recording", "ready"]

_LOOKUP = "Use AnyPoach MCP to call anypoach_read_brief with briefId {id}. Verify the returned briefId matches."


def physical_rect(start: tuple[float, float], end: tuple[float, float], *, origin: tuple[float, float], dpr: float) -> Rect:
    """Convert two dragged corners into a global rectangle in physical pixels.

    Assumes one device pixel ratio per screen.

    Args:
        start: First corner, in the screen's logical coordinates.
        end: Opposite corner, in the same coordinates.
        origin: The screen's logical top-left in the global coordinate space.
        dpr: Device pixel ratio of that screen.

    Returns:
        A rectangle whose width and height are never negative, whichever way the drag went.
    """
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
    """The prompt copied for an assistant to read a video brief."""
    return (f"{_LOOKUP.format(id=brief_id)} Use its images, pointer trace, and timestamped notes. {_pointer_guidance(trace)} "
            "Match pointer coordinates and timestamps to the frames to identify targets. For a drag, inspect the frames "
            "after release and include visible changes through the end of the response. Use the video and notes to "
            "describe visible results, and ask if behavior is ambiguous. Images may be reduced from the capture: read the "
            "caption before measuring, and use evidence.capture for the native size. Divide native pixels by "
            "evidence.capture.deviceScale to get CSS pixels; when deviceScale is null the scale is unknown, so ask. "
            "Recreate the recorded interaction in this project. For video details, call anypoach_read_moment with the "
            "same briefId and timeMs; pass crop and maxSize to read a detail at native scale.")


class Controller:
    """Runs the record-analyze-share flow without any UI toolkit, so it can be tested and reused.

    Failures never raise: they set `message` for the window to show and leave `state` unchanged or back at idle.

    Attributes:
        state: `idle`, `recording`, or `ready` (a result is available to share).
        message: Last problem or hint for the user; empty when all is well.
        context: Free text for the assistant, included in the brief.
        annotations: Notes pinned to timestamps, included in the brief.
        result: Analysis of the latest recording, once `stop()` succeeds.

    Args:
        backend: Screen capture to use.
        pointer_source: Where the pointer is read from, or None for no pointer trace.
        work_dir: Folder for recordings and keyframes.
        cache: Brief cache directory; the per-OS default when omitted.
    """
    def __init__(self, backend: CaptureBackend, pointer_source: PointerSource | None, work_dir: Path, *,
                 cache: Path | None = None) -> None:
        self._backend, self._source, self._work, self._cache = backend, pointer_source, Path(work_dir), cache
        self.state: State = "idle"
        self.message = ""
        self.context = ""
        self.annotations: list[dict[str, Any]] = []
        self.result: InspectionResult | None = None
        self._region: Rect | None = None
        self._device_scale: float | None = None
        self._recorder: Recorder | None = None

    @property
    def backend(self) -> CaptureBackend:
        """The capture backend in use."""
        return self._backend

    @property
    def ready_to_record(self) -> bool:
        """Whether `start()` would begin a recording: an area is chosen and nothing is recording."""
        return self._region is not None and self.state != "recording"

    @property
    def supports_preview(self) -> bool:
        """Whether the backend needs a preview frame to choose the area (the Wayland portal does)."""
        return hasattr(self._backend, "preview")

    def preview(self) -> Frame | None:
        """Open the backend's session and return its first frame, so the user can pick an area on it.

        Returns:
            The frame, or None with `message` set when the backend has no preview, the user cancelled the
            portal dialog, or sharing could not start.
        """
        if not self.supports_preview:
            return None
        try:
            frame = self._backend.preview()  # type: ignore[attr-defined]
        except PermissionError as error:
            self.message = str(error) or "Screen sharing was not allowed."
            return None
        except OSError as error:
            self.message = f"Could not start screen sharing: {error}"
            return None
        self.message = ""
        return frame

    def close(self) -> None:
        """Release the backend's session (the portal's sharing indicator goes away) and forget the area."""
        self._region, self._device_scale = None, None
        closer = getattr(self._backend, "close", None)
        if closer is not None:
            closer()

    @property
    def device_scale(self) -> float | None:
        """Scale factor of the screen the area was chosen on, or None when it is not known."""
        return self._device_scale

    def choose_region(self, region: Rect, device_scale: float | None = None) -> None:
        """Remember the area to record. Anything smaller than 2 px in either direction is refused with a message.

        Args:
            region: The area in physical pixels.
            device_scale: Scale factor of its screen, or None when unknown (it is then written as null, never 1.0).
        """
        self._device_scale = device_scale
        self._region = Rect(*region) if region.width >= 2 and region.height >= 2 else None
        self.message = "" if self._region else "Choose an area to record."

    def start(self) -> None:
        """Begin recording the chosen area. Refused with a message if no area is chosen, a recording is already running, or capture cannot start."""
        if self.state == "recording":
            self.message = "Already recording."
            return
        if self._region is None:
            self.message = "Choose an area to record first."
            return
        pointer = PointerTraceRecorder(self._region, self._source)
        recorder = Recorder(self._backend, pointer, self._work)
        try:
            if self.supports_preview:  # the recorder grabs on a thread: probe now so a dead stream fails fast
                self._backend.grab(self._region)
            recorder.start(self._region)
        except OSError as error:
            self.message = f"Could not start recording: {error}"
            if self.supports_preview:
                self.close()  # a dead share must not be reused by the next choice
            return
        self._recorder, self.state, self.message, self.result = recorder, "recording", "", None

    def stop(self) -> InspectionResult | None:
        """End the recording and analyze it.

        Returns:
            The analysis, or None with `message` set when nothing was recording, capture was denied (no screen
            recording permission), or the clip could not be analyzed.
        """
        recorder = self._recorder
        if self.state != "recording" or recorder is None:
            self.message = "There is no recording to stop."
            return None
        self._recorder, self.state = None, "idle"
        scale = self._device_scale  # close() below forgets the area, and the scale with it
        try:
            try:
                recording = recorder.stop()
            finally:
                if self.supports_preview:
                    self.close()  # the session is over, even if it ended on its own: the next recording asks again
            result = inspect_recording(recording.path, output_dir=self._work / "frames")
        except PermissionError:
            self.message = "AnyPoach cannot capture the screen. Check the screen recording permission and try again."
            return None
        except (ValueError, OSError) as error:
            self.message = f"Could not finish the recording: {error}"
            return None
        capture = dataclasses.replace(result.capture, device_scale=scale) if result.capture else None
        self.result = dataclasses.replace(result, pointer_trace=recording.trace.to_json(), capture=capture)
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
