"""Browser evidence sent by the Chrome companion: validation, alignment with a recording, and a short-lived store."""
from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

BYTE_LIMIT = 256 * 1024
MAX_DURATION_MS = 90_000
FINAL_TTL_S = 180
PARTIAL_TTL_S = 10
TRIM_MARGIN_MS = 1_000


class _Model(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")


class _Element(_Model):
    tag: str = Field(max_length=120)
    role: str = Field(max_length=120)
    classes: str = Field(max_length=240)


class _Event(_Model):
    atMs: int = Field(ge=0)
    type: str = Field(max_length=40)
    target: _Element
    point: list[int] | None = Field(default=None, min_length=2, max_length=2)
    insideTarget: bool | None = None


class _Indicator(_Model):
    target: _Element
    rect: list[float] = Field(min_length=4, max_length=4)
    value: str = Field(max_length=240)


class _State(_Model):
    atMs: int = Field(ge=0)
    rect: list[float] = Field(min_length=4, max_length=4)
    styles: dict[str, str]
    text: str = Field(max_length=480)
    indicators: list[_Indicator] = Field(default_factory=list, max_length=4)


class _Frame(_Model):
    offset: float
    easing: str = Field(max_length=120)
    styles: dict[str, str]


class _Animation(_Model):
    atMs: int = Field(ge=0)
    target: _Element
    durationMs: float
    delayMs: float
    easing: str = Field(max_length=120)
    keyframes: list[_Frame] = Field(max_length=8)


class _Component(_Model):
    id: int = Field(ge=0)
    parent: int = Field(ge=-1)
    target: _Element
    rect: list[float] = Field(min_length=4, max_length=4)
    styles: dict[str, str]
    text: str = Field(max_length=80)


class _Viewport(_Model):
    width: float = Field(gt=0)
    height: float = Field(gt=0)


class _Session(_Model):
    version: Literal[1]
    origin: str
    target: _Element
    startedAtEpochMs: int = Field(gt=0, lt=10_000_000_000_000)
    durationMs: int = Field(ge=0, le=MAX_DURATION_MS)
    events: list[_Event] = Field(max_length=96)
    states: list[_State] = Field(min_length=1, max_length=48)
    animations: list[_Animation] = Field(max_length=16)
    targetRemoved: bool
    devicePixelRatio: float | None = None
    viewport: _Viewport | None = None
    components: list[_Component] | None = Field(default=None, max_length=40)
    componentsAtEnd: list[_Component] | None = Field(default=None, max_length=40)

    @field_validator("devicePixelRatio", "viewport", mode="before")
    @classmethod
    def _optional_page_numbers(cls, value: Any, info) -> Any:
        """Ignore a badly typed optional field instead of refusing the whole session."""
        if info.field_name == "devicePixelRatio":
            return value if isinstance(value, (int, float)) and not isinstance(value, bool) and 0 < value <= 16 else None
        return value if isinstance(value, dict) and all(isinstance(value.get(k), (int, float)) and value[k] > 0
                                                       for k in ("width", "height")) else None

    @field_validator("origin")
    @classmethod
    def _plain_origin(cls, value: str) -> str:
        parts = urlsplit(value)
        if (parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password
                or parts.path or parts.query or parts.fragment or value.endswith(("?", "#"))):
            raise ValueError("origin must be http(s)://host with nothing after it")
        return value

    @model_validator(mode="after")
    def _components_form_a_tree(self) -> _Session:
        for items in (self.components, self.componentsAtEnd):
            if items is not None and any(c.id != i or c.parent >= c.id for i, c in enumerate(items)):
                raise ValueError("components must be numbered in order, each after its parent")
        return self

    @model_validator(mode="after")
    def _times_inside_the_session(self) -> _Session:
        times = [e.atMs for e in self.events] + [s.atMs for s in self.states] + [a.atMs for a in self.animations]
        if any(t > self.durationMs for t in times):
            raise ValueError("a timestamp falls after the end of the session")
        return self


def parse_evidence(raw: bytes | str | dict[str, Any]) -> dict[str, Any]:
    """Validate one Chrome session and return it as a plain dictionary.

    Args:
        raw: The JSON body (bytes or text) or an already parsed dictionary.

    Returns:
        The session without any `videoOffsetMs` the sender may have included; that value is ours to compute.

    Raises:
        ValueError: If it is too large, not a JSON object, or outside the documented limits.
    """
    if isinstance(raw, (bytes, str)):
        if len(raw) > BYTE_LIMIT:
            raise ValueError("The Chrome session is larger than 256 KiB")
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as error:
            raise ValueError("The Chrome session is not valid JSON") from error
    if not isinstance(raw, dict):
        raise ValueError("The Chrome session must be a JSON object")  # noqa: TRY004 - one error type for every bad input
    try:
        return _Session.model_validate(raw).model_dump(exclude_none=True)
    except ValidationError as error:
        raise ValueError(f"The Chrome session is not valid: {error.errors()[0]['loc']}") from error


def align(evidence: dict[str, Any], recording_ms: tuple[int, int]) -> dict[str, Any] | None:
    """Add `videoOffsetMs` to a session that overlaps a recording.

    Args:
        evidence: A validated session.
        recording_ms: Wall-clock start and end of the recording in Unix milliseconds.

    Returns:
        A copy whose `videoOffsetMs` is what to add to the session's `atMs` to estimate a position in the video,
        or None when the session and the recording do not overlap in time.
    """
    start = evidence["startedAtEpochMs"]
    if start > recording_ms[1] or start + evidence["durationMs"] < recording_ms[0]:
        return None
    return {**_trim(evidence, recording_ms[0] - start, recording_ms[1] - start), "videoOffsetMs": start - recording_ms[0]}


def _trim(evidence: dict[str, Any], first: int, last: int) -> dict[str, Any]:
    """Keep what touches the recording, given as session milliseconds, plus a second of margin either side.

    The state that was in force when the recording began stays even when it is older, so the page's sizes and typography
    at the start are never lost. A session always keeps at least one state.
    """
    low, high = first - TRIM_MARGIN_MS, last + TRIM_MARGIN_MS
    states = evidence["states"]
    in_force = max((i for i, s in enumerate(states) if s["atMs"] <= first), default=None)
    kept = [s for i, s in enumerate(states) if low <= s["atMs"] <= high or i == in_force] or states[:1]
    return {**evidence,
            "events": [e for e in evidence["events"] if low <= e["atMs"] <= high],
            "states": kept,
            "animations": [a for a in evidence["animations"] if a["atMs"] <= high and a["atMs"] + a["delayMs"] + a["durationMs"] >= low]}


class EvidenceStore:
    """Holds the latest Chrome session so it can be matched to a recording, in memory only.

    A final session is kept for 180 s and a partial (still streaming) one for 10 s. Safe to use from the server
    threads and the window thread at once.

    Args:
        clock: Seconds clock, replaceable in tests.
    """
    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._final: tuple[float, dict[str, Any]] | None = None
        self._partial: tuple[float, dict[str, Any]] | None = None

    def put(self, evidence: dict[str, Any], final: bool) -> None:
        """Remember a session; a final one replaces the previous final and ends any partial."""
        with self._lock:
            if final:
                self._final, self._partial = (self._clock(), evidence), None
            else:
                self._partial = (self._clock(), evidence)

    def latest_for(self, recording_ms: tuple[int, int]) -> dict[str, Any] | None:
        """The final session that overlaps the recording and is at most 180 s old, aligned to it."""
        with self._lock:
            item = self._final
        return self._match(item, recording_ms, FINAL_TTL_S)

    def receiving_for(self, recording_ms: tuple[int, int]) -> bool:
        """Whether a partial session overlapping the recording arrived in the last 10 s."""
        with self._lock:
            item = self._partial
        return self._match(item, recording_ms, PARTIAL_TTL_S) is not None

    def clear(self) -> None:
        """Forget every session."""
        with self._lock:
            self._final = self._partial = None

    def _match(self, item: tuple[float, dict[str, Any]] | None, recording_ms: tuple[int, int], ttl: float) -> dict[str, Any] | None:
        if item is None or self._clock() - item[0] > ttl:
            return None
        return align(item[1], recording_ms)
