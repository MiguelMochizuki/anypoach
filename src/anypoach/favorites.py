"""Favorites: a handoff worth reusing, kept as one `.anypoach` file (also the export format).

A favorite keeps the notes, the instructions, the palette, the timing, the sampled pointer evidence and up to three
reference images (256 KiB each, so 768 KiB in all). It does not keep the video, so a handoff made from it has no `anypoach_read_moment`.
Files are private to the user and are the only AnyPoach data that is kept until the user deletes it.
"""
from __future__ import annotations

import base64
import binascii
import json
import os
import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from platformdirs import user_data_dir
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from anypoach.analysis.motion import MotionTiming
from anypoach.analysis.source import read_still, scaled_png
from anypoach.analysis.types import CaptureInfo, InspectionResult, Keyframe
from anypoach.brief.paths import private_dir
from anypoach.brief.store import write_private

SUFFIX = ".anypoach"
FILE_LIMIT = 4 * 1024 * 1024
FRAME_LIMIT = 256 * 1024
MAX_FRAMES = 3
TRACE_LIMIT = 256 * 1024
FRAME_SIZES = (1152, 864, 648, 486, 320, 192, 128)
_PNG = b"\x89PNG\r\n\x1a\n"
_HEX = re.compile(r"#[0-9a-f]{6}")
_NAME = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")


class FavoriteError(ValueError):
    """A favorite cannot be saved, read or imported; the message is fit to show the user."""


class _Strict(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class _Frame(_Strict):
    kind: Literal["start", "peak", "settled"]
    timeMs: int = Field(ge=0, le=3_600_000)
    png: str  # base64


class _Timing(_Strict):
    durationMs: int = Field(ge=0, le=3_600_000)
    bezier: list[float] | None = Field(default=None, min_length=4, max_length=4)
    token: str = Field(max_length=120)


class _Capture(_Strict):
    widthPx: int = Field(ge=1, le=100_000)
    heightPx: int = Field(ge=1, le=100_000)
    deviceScale: float | None = Field(default=None, gt=0, le=16)
    imageMaxSize: int = Field(ge=1, le=100_000)


class _Note(_Strict):
    timeMs: int = Field(ge=0, le=3_600_000)
    text: str = Field(min_length=1, max_length=500)


class _Record(_Strict):
    version: Literal[1]
    name: str = Field(min_length=1, max_length=80)
    savedAt: float
    context: str = Field(max_length=8000)
    mediaType: Literal["video", "image"]
    durationMs: int = Field(ge=0, le=3_600_000)
    palette: list[str] = Field(max_length=12)
    timing: _Timing
    capture: _Capture | None = None
    notes: list[_Note] = Field(max_length=50)
    pointerTrace: dict[str, Any] | None = None
    frames: list[_Frame] = Field(min_length=1, max_length=MAX_FRAMES)

    @field_validator("palette")
    @classmethod
    def _colors(cls, colors: list[str]) -> list[str]:
        if not all(_HEX.fullmatch(color) for color in colors):
            raise ValueError("palette colors must look like #1a2b3c")
        return colors

    @field_validator("pointerTrace")
    @classmethod
    def _small_trace(cls, trace: dict[str, Any] | None) -> dict[str, Any] | None:
        if trace is not None and len(json.dumps(trace)) > TRACE_LIMIT:
            raise ValueError("pointer trace is too large")
        return trace


@dataclass(frozen=True)
class Summary:
    """What the list shows for a favorite."""
    id: str
    name: str
    saved_at: float


def data_dir() -> Path:
    """`ANYPOACH_DATA_DIR`, or the per-OS user data folder of AnyPoach, plus `favorites`."""
    base = os.environ.get("ANYPOACH_DATA_DIR") or user_data_dir("AnyPoach", appauthor=False)
    return Path(base) / "favorites"


def _decode_frames(record: _Record) -> list[tuple[_Frame, bytes]]:
    frames = []
    for frame in record.frames:
        try:
            png = base64.b64decode(frame.png, validate=True)
        except (binascii.Error, ValueError):
            raise FavoriteError("A reference image is not valid base64.") from None
        if not png.startswith(_PNG) or len(png) > FRAME_LIMIT:
            raise FavoriteError("A reference image is not a PNG within 256 KiB.")
        frames.append((frame, png))
    return frames


def _parse(raw: bytes) -> _Record:
    if len(raw) > FILE_LIMIT:
        raise FavoriteError("A favorite file can be up to 4 MiB.")
    try:
        record = _Record.model_validate_json(raw)
    except ValidationError:
        raise FavoriteError("This is not a valid AnyPoach favorite file.") from None
    _decode_frames(record)
    return record


def _compact(path: str) -> bytes:
    frame = read_still(path)
    for size in FRAME_SIZES:
        png = scaled_png(frame, size)
        if len(png) <= FRAME_LIMIT:
            return png
    raise FavoriteError("A reference image is too detailed to keep.")


class FavoriteStore:
    """A folder of `.anypoach` files.

    Args:
        root: The folder; `data_dir()` when omitted. It is created private to the user on first save.
    """
    def __init__(self, root: Path | None = None) -> None:
        self._root = root or data_dir()

    def _path(self, favorite_id: str) -> Path:
        if not _NAME.fullmatch(favorite_id):
            raise FavoriteError("Unknown favorite.")
        return self._root / f"{favorite_id}{SUFFIX}"

    def _write(self, record: _Record) -> str:
        private_dir(self._root)
        favorite_id = str(uuid.uuid4())
        write_private(self._path(favorite_id), record.model_dump_json().encode())
        return favorite_id

    def save(self, name: str, result: InspectionResult, context: str, annotations: list[dict[str, Any]],
             palette: list[str]) -> str:
        """Keep a handoff.

        Args:
            name: What to call it (trimmed, 1 to 80 characters).
            result: The analysis to keep: its timing, capture size, pointer trace and up to three keyframes.
            context: The general instructions.
            annotations: The notes pinned to moments.
            palette: The palette as the user left it.

        Returns:
            The favorite's id.

        Raises:
            FavoriteError: If the name is empty or too long, there is no keyframe to keep, or the data does not fit.
            OSError: If the file cannot be written.
        """
        keyframes = sorted(result.keyframes, key=lambda k: k.kind != "peak")[:MAX_FRAMES]
        if not keyframes:
            raise FavoriteError("There are no reference frames to keep.")
        try:
            frames = [_Frame(kind=k.kind, timeMs=int(k.time_ms),
                             png=base64.b64encode(_compact(k.image_path)).decode()) for k in keyframes]
        except (ValueError, OSError) as error:
            raise FavoriteError(f"The reference frames are unavailable: {error}") from None
        capture = result.capture.to_json() if result.capture else None
        try:
            record = _Record(
                version=1, name=name.strip(), savedAt=time.time(), context=context, mediaType=result.media_type,
                durationMs=result.duration_ms, palette=[c.lower() for c in palette],
                timing=_Timing(durationMs=result.timing.duration_ms,
                               bezier=list(result.timing.bezier) if result.timing.bezier else None,
                               token=result.timing.token),
                capture=_Capture(**capture) if capture else None,
                notes=[_Note(timeMs=int(a["timeMs"]), text=str(a["text"])) for a in annotations],
                pointerTrace=result.pointer_trace, frames=frames)
        except (ValidationError, KeyError, TypeError, ValueError) as error:
            raise FavoriteError(f"This handoff cannot be kept as a favorite: {error}") from None
        _decode_frames(record)
        return self._write(record)

    def _read(self, favorite_id: str) -> _Record:
        try:
            return _parse(self._path(favorite_id).read_bytes())
        except FileNotFoundError:
            raise FavoriteError("Unknown favorite.") from None

    def list(self) -> list[Summary]:
        """The valid favorites, newest first; files that do not parse are skipped."""
        if not self._root.is_dir():
            return []
        found = []
        for file in self._root.glob(f"*{SUFFIX}"):
            try:
                found.append(Summary(file.stem, (record := self._read(file.stem)).name, record.savedAt))
            except FavoriteError:
                continue
        return sorted(found, key=lambda s: s.saved_at, reverse=True)

    def cover(self, favorite_id: str) -> bytes:
        """PNG bytes of the favorite's cover: its peak frame, else its first."""
        frames = _decode_frames(self._read(favorite_id))
        return next((png for frame, png in frames if frame.kind == "peak"), frames[0][1])

    def delete(self, favorite_id: str) -> None:
        """Remove a favorite; an unknown id is ignored."""
        self._path(favorite_id).unlink(missing_ok=True)

    def export(self, favorite_id: str, destination: Path) -> None:
        """Copy a favorite to `destination` (a `.anypoach` file to share).

        Raises:
            FavoriteError: If the favorite is unknown or unreadable.
            OSError: If the file cannot be written.
        """
        self._read(favorite_id)
        destination.write_bytes(self._path(favorite_id).read_bytes())

    def import_file(self, source: Path) -> str:
        """Add a favorite from a `.anypoach` file, after checking every field and image.

        Returns:
            The id of the new favorite (the file's own id is never trusted).

        Raises:
            FavoriteError: If the file is too large or is not a valid favorite.
            OSError: If the file cannot be read or the favorite cannot be written.
        """
        with source.open("rb") as handle:
            raw = handle.read(FILE_LIMIT + 1)
        return self._write(_parse(raw))

    def to_result(self, favorite_id: str, frames_dir: Path) -> tuple[InspectionResult, str, list[dict[str, Any]]]:
        """Rebuild what a handoff needs from a favorite.

        Args:
            favorite_id: The favorite.
            frames_dir: Where the reference images are written for the brief to point at.

        Returns:
            The result (no source video), the instructions and the notes.
        """
        record = self._read(favorite_id)
        private_dir(frames_dir)
        keyframes = []
        for frame, png in _decode_frames(record):
            path = frames_dir / f"favorite-{favorite_id[:8]}-{frame.kind}-{frame.timeMs}ms.png"
            write_private(path, png)
            keyframes.append(Keyframe(frame.kind, frame.timeMs, str(path), 0.0))
        timing = MotionTiming(record.timing.durationMs, tuple(record.timing.bezier) if record.timing.bezier else None,
                              record.timing.token)
        capture = CaptureInfo(record.capture.widthPx, record.capture.heightPx, record.capture.deviceScale,
                              record.capture.imageMaxSize) if record.capture else None
        result = InspectionResult(record.mediaType, "", record.durationMs, keyframes, list(record.palette), timing,
                                  pointer_trace=record.pointerTrace, capture=capture)
        return result, record.context, [n.model_dump() for n in record.notes]
