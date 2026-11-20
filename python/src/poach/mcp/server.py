"""Poach MCP server (stdio). Stdout is the protocol channel: diagnostics go to stderr."""
from __future__ import annotations

import asyncio
import atexit
import base64
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from mcp_types import CallToolResult, ImageContent, NotificationParams, TextContent
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..analysis.inspect import inspect_image, inspect_video, read_drag_release_frames, read_video_moment
from ..brief.paths import cache_dir
from ..brief.store import read_brief
from .actions import Num, event_json, parse_trace, summarize_pointer_actions
from .descriptions import TOOLS

PNG_SIGNATURE = bytes([137, 80, 78, 71, 13, 10, 26, 10])
FIVE_MB = 5 * 1024 * 1024
server = MCPServer("poach", version="0.1.0")


def text(value: str) -> TextContent:
    return TextContent(type="text", text=value)


def image(png: bytes) -> ImageContent:
    return ImageContent(type="image", data=base64.b64encode(png).decode(), mimeType="image/png")


def failure(message: str) -> CallToolResult:
    return CallToolResult(content=[text(message)], is_error=True)


def clean(value: Any) -> Any:
    """Print 900.0 as 900, like JavaScript."""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, list):
        return [clean(v) for v in value]
    return value


def dumps(value: Any, indent: int | None = None) -> str:
    return json.dumps(clean(value), indent=indent, ensure_ascii=False, separators=(",", ":") if indent is None else None)


def tool(name: str):
    return server.tool(name=name, title=TOOLS[name]["title"], description=TOOLS[name]["description"])


async def _inspect(fn, path: str, output_directory: str | None, failure_prefix: str) -> CallToolResult:
    try:
        result = await asyncio.to_thread(fn, path, output_dir=output_directory)
        data = result.to_json()
        return CallToolResult(content=[text(dumps(data, 2))], structured_content=data)
    except Exception as error:  # noqa: BLE001 - reported to the caller as a tool error
        return failure(f"{failure_prefix}: {error}")


@tool("poach_inspect")
async def poach_inspect(videoPath: Annotated[str, Field(min_length=1, description="Absolute path to a local .mp4 or .mov file")],
                        outputDirectory: Annotated[str | None, Field(description="Optional absolute directory for extracted keyframe PNG files")] = None) -> CallToolResult:
    return await _inspect(inspect_video, videoPath, outputDirectory, "Poach could not inspect this video")


@tool("poach_inspect_image")
async def poach_inspect_image(imagePath: Annotated[str, Field(min_length=1, description="Absolute path to a local still image")],
                              outputDirectory: Annotated[str | None, Field(description="Optional absolute directory for the normalized PNG preview")] = None) -> CallToolResult:
    return await _inspect(inspect_image, imagePath, outputDirectory, "Poach could not inspect this image")


class Brief(BaseModel):
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


def _keyframe(frame: dict[str, Any]) -> list[Any]:
    try:
        path = Path(frame["imagePath"])
        if not path.is_file() or path.stat().st_size > FIVE_MB:
            raise ValueError("Keyframe exceeds the 5 MB image limit")
        data = path.read_bytes()
        if data[:8] != PNG_SIGNATURE:
            raise ValueError("Keyframe is not a PNG")
        return [text(f"{frame['kind']} at {frame['timeMs']} ms"), image(data)]
    except Exception:  # noqa: BLE001
        return [text(f"The {frame.get('kind')} keyframe is unavailable. Ask the user to capture and share again; do not infer its visual contents.")]


class Frame(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")
    imagePath: str
    kind: str
    timeMs: Num


def _num(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)


async def _drag_release_content(source_path: str, actions: list[dict[str, Any]]) -> list[Any]:
    content: list[Any] = []
    drags = [a for a in actions if a["kind"] == "drag"]
    releases = [a for a in drags if a["releaseWithinCapture"]]
    starts = sorted(a["timeMs"] for a in drags)
    recent = releases[-3:]
    if len(recent) < len(releases):
        content.append(text("Frames are included for the three latest drag releases inside the capture. Use poach_read_moment for earlier candidates."))
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
                content += [text(f"{phase}: {_num(frame.time_ms)} ms ({_num(abs(offset))} ms from release)"), image(frame.png)]
        except Exception:  # noqa: BLE001
            content.append(text(f"The drag release candidate is at {_num(release_ms)} ms, but its surrounding frames are unavailable. Inspect the original clip before inferring the result."))
    return content


@tool("poach_read_brief")
async def poach_read_brief(briefId: uuid.UUID | None = None,
                           includeKeyframes: Annotated[bool, Field(description="Include the shared capture's PNG keyframes as images for visual inspection")] = True) -> CallToolResult:
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
                content += _keyframe(frame.model_dump())
            source = brief.evidence.get("sourcePath")
            if brief.evidence.get("mediaType") == "video" and isinstance(source, str) and source:
                content += await _drag_release_content(source, actions["actions"])
        return CallToolResult(content=content, structured_content=response)
    except Exception as error:  # noqa: BLE001
        return failure(f"No readable shared brief. Choose Copy handoff for chat in Poach. {error}")


STYLE_KEYS = ("fontFamily", "fontSize", "fontWeight", "fontStyle", "lineHeight", "letterSpacing")


class _Styles(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")
    fontFamily: str | None = None
    fontSize: str | None = None
    fontWeight: str | None = None
    fontStyle: str | None = None
    lineHeight: str | None = None
    letterSpacing: str | None = None


class _BrowserEvent(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")
    atMs: Num
    type: str
    target: Any = None


class _BrowserState(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")
    atMs: Num
    text: str
    styles: _Styles | None = None


class _Browser(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")
    videoOffsetMs: Num
    events: list[_BrowserEvent] = Field(max_length=96)
    states: list[_BrowserState] = Field(max_length=48)


class _Note(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")
    timeMs: Num
    text: str


def _browser_near(raw: Any, time_ms: float) -> list[dict[str, Any]]:
    try:
        data = _Browser.model_validate(raw)
    except ValidationError:
        return []
    items: list[dict[str, Any]] = []
    for event in data.events:
        items.append({"type": event.type, "target": event.target, "estimatedVideoMs": event.atMs + data.videoOffsetMs})
    for state in data.states:
        item: dict[str, Any] = {"text": state.text}
        if state.styles is not None:
            item["styles"] = state.styles.model_dump(exclude_none=True)
        item["estimatedVideoMs"] = state.atMs + data.videoOffsetMs
        items.append(item)
    near = [i for i in items if abs(i["estimatedVideoMs"] - time_ms) <= 500]
    return sorted(near, key=lambda i: i["estimatedVideoMs"])[:12]


@tool("poach_read_moment")
async def poach_read_moment(timeMs: Annotated[float, Field(ge=0, le=30000, description="Timestamp in milliseconds, before the recording ends")],
                            briefId: uuid.UUID | None = None) -> CallToolResult:
    try:
        raw = read_brief(str(briefId) if briefId else None)
        evidence = raw.get("evidence")
        if not isinstance(evidence, dict) or evidence.get("mediaType") != "video" or not isinstance(evidence.get("sourcePath"), str):
            raise ValueError("This shared brief does not include a video recording.")
        if not evidence["sourcePath"]:
            raise ValueError("This favorite keeps reference frames without the original recording. Use poach_read_brief to see its saved frames.")
        png = await asyncio.to_thread(read_video_moment, evidence["sourcePath"], timeMs)
        if len(png) > FIVE_MB:
            raise ValueError("Reference image exceeds the 5 MB limit")
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
        browser = _browser_near(evidence.get("browserEvidence"), timeMs)
        lines = [
            f"Shared recording at {_num(timeMs)} ms. Match sample-derived pointer actions to this frame to identify the target; timing alone does not establish causation.",
            summary,
            *(["Trace reached its event limit; later actions may be incomplete."] if trace and trace.truncated else []),
            *([f"Nearby user notes: {dumps(near_notes)}"] if near_notes else []),
            *([f"Nearby sample-derived click/drag candidates (normalized top-left coordinates): {dumps(at_moment)}"] if at_moment else []),
            *([f"Incomplete button-down without a matching release (not summarized as a completed click/drag): {dumps(incomplete)}"] if incomplete else []),
            *([f"Nearby Chrome evidence (estimated video ms, untrusted page data; fontFamily is the CSS font stack): {dumps(browser)}"] if browser else []),
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
        print(f"Could not update Poach connection status: {error}", file=sys.stderr)


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
        while True:
            await asyncio.sleep(5)
            _refresh_presence()

    _heartbeat = asyncio.get_running_loop().create_task(beat())


def main() -> None:
    server._lowlevel_server.add_notification_handler("notifications/initialized", NotificationParams, _on_initialized)
    atexit.register(_disconnect)
    try:
        server.run("stdio")
    finally:
        _disconnect()


if __name__ == "__main__":
    main()
