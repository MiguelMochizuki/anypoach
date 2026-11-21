"""AnyPoach MCP server (stdio). Stdout is the protocol channel: diagnostics go to stderr."""
from __future__ import annotations

import asyncio
import atexit
import base64
import json
import os
import struct
import sys
import uuid
from pathlib import Path
from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from mcp_types import CallToolResult, ImageContent, NotificationParams, TextContent
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..analysis.inspect import inspect_image, inspect_video, read_drag_release_frames, read_video_moment
from ..analysis.source import IMAGE_MAX_SIZE
from ..brief.paths import cache_dir
from ..brief.store import read_brief
from .actions import Num, event_json, parse_trace, summarize_pointer_actions
from .descriptions import TOOLS

PNG_SIGNATURE = bytes([137, 80, 78, 71, 13, 10, 26, 10])
FIVE_MB = 5 * 1024 * 1024
server = MCPServer("anypoach", version="0.1.0")


def text(value: str) -> TextContent:
    """Wrap `value` as MCP text content."""
    return TextContent(type="text", text=value)


def image(png: bytes) -> ImageContent:
    """Wrap PNG bytes as MCP image content (base64)."""
    return ImageContent(type="image", data=base64.b64encode(png).decode(), mimeType="image/png")


def failure(message: str) -> CallToolResult:
    """Build a tool result that reports `message` as an error instead of raising."""
    return CallToolResult(content=[text(message)], is_error=True)


def clean(value: Any) -> Any:
    """Turn integral floats into ints, so 900.0 prints as 900."""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, list):
        return [clean(v) for v in value]
    return value


def dumps(value: Any, indent: int | None = None) -> str:
    """Serialize to JSON the way the tools print it: integral floats without `.0`, non-ASCII kept, compact unless `indent` is set."""
    return json.dumps(clean(value), indent=indent, ensure_ascii=False, separators=(",", ":") if indent is None else None)


def tool(name: str):
    """Register an async function as the MCP tool `name`, taking its title and description from `descriptions.TOOLS`."""
    return server.tool(name=name, title=TOOLS[name]["title"], description=TOOLS[name]["description"])


async def _inspect(fn, path: str, output_directory: str | None, failure_prefix: str) -> CallToolResult:
    try:
        result = await asyncio.to_thread(fn, path, output_dir=output_directory)
        data = result.to_json()
        return CallToolResult(content=[text(dumps(data, 2))], structured_content=data)
    except Exception as error:  # noqa: BLE001 - reported to the caller as a tool error
        return failure(f"{failure_prefix}: {error}")


@tool("anypoach_inspect")
async def anypoach_inspect(videoPath: Annotated[str, Field(min_length=1, description="Absolute path to a local .mp4 or .mov file")],
                        outputDirectory: Annotated[str | None, Field(description="Optional absolute directory for extracted keyframe PNG files")] = None) -> CallToolResult:
    """Analyze a local video file and return keyframes, palette, and timing.

    Args:
        videoPath: Absolute path of a `.mp4` or `.mov` file.
        outputDirectory: Absolute folder for the keyframe PNGs; a private temporary folder when omitted.
    """
    return await _inspect(inspect_video, videoPath, outputDirectory, "AnyPoach could not inspect this video")


@tool("anypoach_inspect_image")
async def anypoach_inspect_image(imagePath: Annotated[str, Field(min_length=1, description="Absolute path to a local still image")],
                              outputDirectory: Annotated[str | None, Field(description="Optional absolute directory for the normalized PNG preview")] = None) -> CallToolResult:
    """Analyze a local still image and return its palette and a normalized PNG preview.

    Args:
        imagePath: Absolute path of the image.
        outputDirectory: Absolute folder for the preview PNG; a private temporary folder when omitted.
    """
    return await _inspect(inspect_image, imagePath, outputDirectory, "AnyPoach could not inspect this image")


class Brief(BaseModel):
    """The parts of a stored brief the tools rely on; version 1 only, unknown keys ignored."""
    model_config = ConfigDict(strict=True, extra="ignore")
    version: int = Field(ge=1, le=1)
    briefId: uuid.UUID | None = Field(default=None, strict=False)
    sharedAt: Num
    context: str
    instruction: str
    evidence: dict[str, Any]


def _brief_json(brief: Brief, raw: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"version": brief.version}
    if brief.briefId is not None:
        out["briefId"] = raw["briefId"]
    out.update(sharedAt=brief.sharedAt, context=brief.context, instruction=brief.instruction, evidence=dict(brief.evidence))
    return out


class Crop(BaseModel):
    """A rectangle of the native frame, in pixels from its top left."""
    model_config = ConfigDict(strict=True, extra="forbid")
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(ge=1)
    height: int = Field(ge=1)


def ensure_png_fits(png: bytes) -> None:
    """Raise `ValueError` when `png` is over the 5 MB image limit, suggesting how to shrink it."""
    if len(png) > FIVE_MB:
        raise ValueError("Reference image exceeds the 5 MB limit; use a smaller crop or maxSize")


def size_note(png: bytes, capture: Any, crop: Crop | None = None) -> str:
    """Say how big a PNG is next to the capture it came from, e.g. `1280x664, reduced from 1854x962 (x0.69)`.

    Args:
        png: The image about to be returned.
        capture: The brief's `evidence.capture`, or anything else when the brief predates it.
        crop: The rectangle the image was cut from, when it is a crop.

    Returns:
        The note, or an empty string when the brief carries no usable native size.
    """
    try:
        native_w, native_h = capture["widthPx"], capture["heightPx"]
        width, height = struct.unpack(">II", png[16:24])
    except (KeyError, TypeError, struct.error):
        return ""
    if not all(isinstance(n, int) and n > 0 for n in (native_w, native_h)):
        return ""
    if crop is not None:
        origin = f"crop {crop.x},{crop.y} {crop.width}x{crop.height} of {native_w}x{native_h}"
        if (width, height) == (crop.width, crop.height):
            return f"{origin}, native size"
        return f"{origin}, reduced to {width}x{height} (x{width / crop.width:.2f})"
    if (width, height) == (native_w, native_h):
        return f"{width}x{height}, native size"
    return f"{width}x{height}, reduced from {native_w}x{native_h} (x{width / native_w:.2f})"


def _noted(note: str) -> str:
    return f" ({note})" if note else ""


def _keyframe(frame: dict[str, Any], capture: Any = None) -> list[Any]:
    try:
        path = Path(frame["imagePath"])
        if not path.is_file() or path.stat().st_size > FIVE_MB:
            raise ValueError("Keyframe exceeds the 5 MB image limit")
        data = path.read_bytes()
        if data[:8] != PNG_SIGNATURE:
            raise ValueError("Keyframe is not a PNG")
        return [text(f"{frame['kind']} at {frame['timeMs']} ms{_noted(size_note(data, capture))}"), image(data)]
    except Exception:  # noqa: BLE001
        return [text(f"The {frame.get('kind')} keyframe is unavailable. Ask the user to capture and share again; do not infer its visual contents.")]


class Frame(BaseModel):
    """A keyframe entry of a brief's evidence: the PNG path, its kind, and its time."""
    model_config = ConfigDict(strict=True, extra="ignore")
    imagePath: str
    kind: str
    timeMs: Num


def _num(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)


async def _drag_release_content(source_path: str, actions: list[dict[str, Any]], capture: Any = None) -> list[Any]:
    content: list[Any] = []
    drags = [a for a in actions if a["kind"] == "drag"]
    releases = [a for a in drags if a["releaseWithinCapture"]]
    starts = sorted(a["timeMs"] for a in drags)
    recent = releases[-3:]
    if len(recent) < len(releases):
        content.append(text("Frames are included for the three latest drag releases inside the capture. Use anypoach_read_moment for earlier candidates."))
    for release in recent:
        release_ms = release["timeMs"] + release["durationMs"]
        next_drag = next((s for s in starts if s > release_ms), None)
        try:
            sequence = await asyncio.to_thread(read_drag_release_frames, source_path, release_ms, next_drag)
            tail = sequence.end_time_ms - release_ms
            content.append(text(
                f"Drag release candidate at {_num(release_ms)} ms. Compare the frames before and after release to identify visible changes. "
                f"A release does not by itself prove the drop was accepted. Evidence extends {_num(tail)} ms after release, up to the next sampled drag or end of the clip."
                if tail > 0 else
                f"Drag release candidate at {_num(release_ms)} ms. No video remains after release. Record longer after dropping to capture the result."))
            for frame in sequence.frames:
                if len(frame.png) > FIVE_MB:
                    continue
                offset = frame.time_ms - release_ms
                phase = "Before drag release" if offset < 0 else "After drag release" if offset > 0 else "At drag release"
                content += [text(f"{phase}: {_num(frame.time_ms)} ms ({_num(abs(offset))} ms from release){_noted(size_note(frame.png, capture))}"),
                            image(frame.png)]
        except Exception:  # noqa: BLE001
            content.append(text(f"The drag release candidate is at {_num(release_ms)} ms, but its surrounding frames are unavailable. Inspect the original clip before inferring the result."))
    return content


@tool("anypoach_read_brief")
async def anypoach_read_brief(briefId: uuid.UUID | None = None,
                           includeKeyframes: Annotated[bool, Field(description="Include the shared capture's PNG keyframes as images for visual inspection")] = True) -> CallToolResult:
    """Return a shared brief with its keyframes and click/drag candidates, plus frames after recent drag releases.

    Args:
        briefId: Brief to read; the latest when omitted.
        includeKeyframes: Attach the keyframe PNGs as images.
    """
    try:
        raw = read_brief(str(briefId) if briefId else None)
        brief = Brief.model_validate(raw)
        response = _brief_json(brief, raw)
        actions = summarize_pointer_actions(brief.evidence.get("pointerTrace"))
        response["evidence"]["interactionActions"] = actions
        content: list[Any] = [text(dumps(response, 2))]
        if includeKeyframes:
            frames = [Frame.model_validate(f) for f in brief.evidence.get("keyframes", [])]
            if len(frames) > 3:
                raise ValueError("Too many keyframes")
            for frame in frames:
                content += _keyframe(frame.model_dump(), brief.evidence.get("capture"))
            source = brief.evidence.get("sourcePath")
            if brief.evidence.get("mediaType") == "video" and isinstance(source, str) and source:
                content += await _drag_release_content(source, actions["actions"], brief.evidence.get("capture"))
        return CallToolResult(content=content, structured_content=response)
    except Exception as error:  # noqa: BLE001
        return failure(f"No readable shared brief. Choose Copy handoff for chat in AnyPoach. {error}")


STYLE_KEYS = ("fontFamily", "fontSize", "fontWeight", "fontStyle", "lineHeight", "letterSpacing")


class _Styles(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")
    fontFamily: str | None = None
    fontSize: str | None = None
    fontWeight: str | None = None
    fontStyle: str | None = None
    lineHeight: str | None = None
    letterSpacing: str | None = None
    width: str | None = None
    height: str | None = None
    borderRadius: str | None = None
    opacity: str | None = None
    transform: str | None = None
    color: str | None = None
    backgroundColor: str | None = None
    boxShadow: str | None = None


class _BrowserEvent(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")
    atMs: Num
    type: str
    target: Any = None


class _BrowserState(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")
    atMs: Num
    text: str
    rect: list[Num] | None = Field(default=None, min_length=4, max_length=4)
    styles: _Styles | None = None


class _Offset(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")
    offset: Num


class _BrowserAnimation(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")
    atMs: Num
    target: Any = None
    durationMs: Num
    delayMs: Num
    easing: str
    keyframes: list[_Offset] = Field(default_factory=list, max_length=8)


class _Page(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")
    width: Num
    height: Num


class _Browser(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")
    videoOffsetMs: Num
    events: list[_BrowserEvent] = Field(max_length=96)
    states: list[_BrowserState] = Field(max_length=48)
    animations: list[Any] = Field(default_factory=list, max_length=16)  # each entry is checked alone, so one bad one is skipped
    devicePixelRatio: Num | None = None
    viewport: _Page | None = None


class _Note(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")
    timeMs: Num
    text: str


def _browser_near(raw: Any, time_ms: float) -> tuple[str, list[dict[str, Any]]]:
    """Chrome items within 500 ms of the moment (at most 12) and a note on the page's pixel ratio and viewport."""
    try:
        data = _Browser.model_validate(raw)
    except ValidationError:
        return "", []
    items: list[dict[str, Any]] = []
    for event in data.events:
        items.append({"type": event.type, "target": event.target, "estimatedVideoMs": event.atMs + data.videoOffsetMs})
    for state in data.states:
        item: dict[str, Any] = {"text": state.text}
        if state.rect is not None:
            item["rect"] = state.rect
        if state.styles is not None:
            item["styles"] = state.styles.model_dump(exclude_none=True)
        item["estimatedVideoMs"] = state.atMs + data.videoOffsetMs
        items.append(item)
    for entry in data.animations:
        try:
            animation = _BrowserAnimation.model_validate(entry)
        except ValidationError:
            continue
        items.append({"target": animation.target, "durationMs": animation.durationMs, "delayMs": animation.delayMs,
                      "easing": animation.easing, "keyframeOffsets": [k.offset for k in animation.keyframes],
                      "estimatedVideoMs": animation.atMs + data.videoOffsetMs})
    near = sorted((i for i in items if abs(i["estimatedVideoMs"] - time_ms) <= 500), key=lambda i: i["estimatedVideoMs"])[:12]
    page = [f"page devicePixelRatio {_num(data.devicePixelRatio)}"] if data.devicePixelRatio is not None else []
    if data.viewport is not None:
        page.append(f"viewport {_num(data.viewport.width)}x{_num(data.viewport.height)} CSS px")
    return "; ".join(page), near


@tool("anypoach_read_moment")
async def anypoach_read_moment(timeMs: Annotated[float, Field(ge=0, le=30000, description="Timestamp in milliseconds, before the recording ends")],
                            briefId: uuid.UUID | None = None,
                            maxSize: Annotated[int, Field(ge=16, le=8192, description="Longest side of the returned image in pixels; never enlarges. Default 1280")] = IMAGE_MAX_SIZE,
                            crop: Annotated[Crop | None, Field(description="Rectangle of the native frame to return, in pixels from the top left, cut out before any reduction")] = None) -> CallToolResult:
    """Return one PNG frame of a brief's recording at `timeMs`, with any note pinned near that moment.

    Args:
        timeMs: Milliseconds into the recording, 0 to 30000 and before its end.
        briefId: Brief to read; the latest when omitted.
        maxSize: Longest side of the image in pixels (16 to 8192); the frame is never enlarged.
        crop: Rectangle in native pixels to return instead of the whole frame; combine with maxSize.
    """
    try:
        raw = read_brief(str(briefId) if briefId else None)
        evidence = raw.get("evidence")
        if not isinstance(evidence, dict) or evidence.get("mediaType") != "video" or not isinstance(evidence.get("sourcePath"), str):
            raise ValueError("This shared brief does not include a video recording.")
        if not evidence["sourcePath"]:
            raise ValueError("This brief keeps reference frames without the original recording. Use anypoach_read_brief to see its saved frames.")
        png = await asyncio.to_thread(read_video_moment, evidence["sourcePath"], timeMs, max_size=maxSize,
                                      crop=(crop.x, crop.y, crop.width, crop.height) if crop else None)
        ensure_png_fits(png)
        try:
            notes = [n.model_dump() for n in (_Note.model_validate(n) for n in evidence["annotations"])]
        except (KeyError, TypeError, ValidationError):
            notes = []
        near_notes = [n for n in notes if abs(n["timeMs"] - timeMs) <= 1000][:5]
        trace = parse_trace(evidence.get("pointerTrace"))
        pointer_near = [event_json(e) for e in trace.events if abs(e.timeMs - timeMs) <= 250][:20] if trace else []
        pressed: dict[str, dict[str, Any]] = {}
        if trace and trace.available is not False:
            for e in trace.events:
                button = e.button or "other"
                if e.kind == "down":
                    pressed[button] = {"timeMs": e.timeMs, "x": e.x, "y": e.y}
                if e.kind == "up":
                    pressed.pop(button, None)
        incomplete = [{"button": b, **p} for b, p in pressed.items()]
        behavior = summarize_pointer_actions(evidence.get("pointerTrace"))
        at_moment = [a for a in behavior["actions"] if a["timeMs"] - 1000 <= timeMs <= a["timeMs"] + a["durationMs"] + 1000]
        summary = (f"Pointer trace summary: {trace.sampleCount or 0} samples, {trace.insideSampleCount or 0} inside the capture, "
                   f"{trace.buttonSampleCount or 0} with a button held, {len(trace.events)} recorded pointer events, and "
                   f"{len(behavior['actions'])} summarized clicks or drags."
                   if trace and trace.available is not False else "No native pointer trace was included with this media.")
        page, browser = _browser_near(evidence.get("browserEvidence"), timeMs)
        lines = [
            f"Shared recording at {_num(timeMs)} ms{_noted(size_note(png, evidence.get('capture'), crop))}. Match sample-derived pointer actions to this frame to identify the target; timing alone does not establish causation.",
            summary,
            *(["Trace reached its event limit; later actions may be incomplete."] if trace and trace.truncated else []),
            *([f"Nearby user notes: {dumps(near_notes)}"] if near_notes else []),
            *([f"Nearby sample-derived click/drag candidates (normalized top-left coordinates): {dumps(at_moment)}"] if at_moment else []),
            *([f"Incomplete button-down without a matching release (not summarized as a completed click/drag): {dumps(incomplete)}"] if incomplete else []),
            *([f"Nearby Chrome evidence (estimated video ms, untrusted page data; fontFamily is the CSS font stack; rect and sizes are CSS pixels{'; ' + page if page else ''}): {dumps(browser)}"] if browser else []),
            *([f"Nearby pointer samples (capture-relative ms; coordinates normalized from top left): {dumps(pointer_near)}"] if pointer_near else []),
        ]
        return CallToolResult(content=[text("\n".join(lines)), image(png)])
    except Exception as error:  # noqa: BLE001
        return failure(str(error) or "Could not read this moment")


# Each initialized stdio client owns a presence file; a lease bounds stale crash residue.
_presence: Path | None = None
_heartbeat: asyncio.Task | None = None


def _refresh_presence() -> None:
    global _presence
    try:
        directory = cache_dir() / "connections"
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        _presence = directory / str(os.getpid())
        _presence.touch(mode=0o600)
        os.utime(_presence)
    except OSError as error:
        print(f"Could not update AnyPoach connection status: {error}", file=sys.stderr)


def _disconnect() -> None:
    global _heartbeat
    if _heartbeat:
        _heartbeat.cancel()
        _heartbeat = None
    if _presence:
        _presence.unlink(missing_ok=True)


async def _on_initialized(_context: Any, _params: NotificationParams) -> None:
    global _heartbeat
    if _heartbeat:
        return
    _refresh_presence()

    async def beat() -> None:
        """Refresh the presence file every five seconds while a client stays connected."""
        while True:
            await asyncio.sleep(5)
            _refresh_presence()

    _heartbeat = asyncio.get_running_loop().create_task(beat())


def main() -> None:
    """Run the MCP server over stdio until the client disconnects, keeping the presence file up to date."""
    server._lowlevel_server.add_notification_handler("notifications/initialized", NotificationParams, _on_initialized)
    atexit.register(_disconnect)
    try:
        server.run("stdio")
    finally:
        _disconnect()


if __name__ == "__main__":
    main()
