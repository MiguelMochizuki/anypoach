"""Shared briefs: `active-brief.json` (latest) plus `briefs/<uuid>.json`, user-only, valid for 24 h."""
from __future__ import annotations

import json
import os
import re
import stat
import time
import uuid
from pathlib import Path
from typing import Any

from ..analysis.types import InspectionResult
from .paths import cache_dir, private_dir, restrict

VALIDITY_SECONDS = 86_400
_UUID = re.compile(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")
_INSTRUCTIONS = {
    "image": "Recreate the visible UI using the screenshot and palette. Use the selected visual font match as an "
             "approximation when present. Ask about behavior the screenshot does not show.",
    "video": "Recreate this UI in the current project. Inspect the keyframes, preserve observed behavior and colors, "
             "and treat timing estimates as approximate. Ask about ambiguous behavior.",
}


def check_uuid(value: str) -> str:
    """Return `value` unchanged if it is a UUID.

    Raises:
        ValueError: If it is anything else, which keeps path tricks like `../x` out of file names.
    """
    if not _UUID.fullmatch(value):
        raise ValueError("briefId must be a UUID")
    return value


def write_private(path: Path, data: bytes) -> None:
    """Write `data` to `path` atomically, readable only by the current user."""
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temp.write_bytes(data)
    restrict(temp, directory=False)
    os.replace(temp, path)


def read_regular(path: Path) -> bytes:
    """Read a cache file, refusing symlinks and anything that is not a regular file."""
    if not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError(f"{path.name} is not a regular file")
    return path.read_bytes()


def archive_active(active: Path, archive: Path) -> None:
    """Keep the outgoing latest brief readable by ID while it is still valid."""
    try:
        data = read_regular(active)
        handoff = json.loads(data)
        brief_id, shared_at = check_uuid(handoff["briefId"]), float(handoff["sharedAt"])
    except (FileNotFoundError, ValueError, KeyError, TypeError):
        return
    destination = archive / f"{brief_id.lower()}.json"
    if time.time() - shared_at <= VALIDITY_SECONDS and not destination.exists():
        write_private(destination, data)


def share(result: InspectionResult, context: str, annotations: list[dict[str, Any]], *,
          cache: Path | None = None) -> str:
    """Write a brief and make it the latest one.

    The previous latest brief is archived by id while it is still valid. The new brief keeps the analysis
    without its per-keyframe `motion` value, and can be read back with `read_brief`.

    Args:
        result: Analysis of the recording or image.
        context: Free text for the assistant, such as what to build.
        annotations: Notes pinned to timestamps.
        cache: Brief cache directory; the per-OS default when omitted.

    Returns:
        The new brief id, an uppercase UUID.

    Raises:
        OSError: If the files cannot be written.
    """
    root = private_dir(cache or cache_dir())
    archive = private_dir(root / "briefs")
    evidence = result.to_json()
    for keyframe in evidence["keyframes"]:
        keyframe.pop("motion", None)  # the app's brief never carried it
    evidence["annotations"] = annotations
    brief_id = str(uuid.uuid4()).upper()
    data = json.dumps({"briefId": brief_id, "version": 1, "sharedAt": time.time(), "context": context,
                       "instruction": _INSTRUCTIONS[result.media_type], "evidence": evidence},
                      sort_keys=True).encode()
    active = root / "active-brief.json"
    archive_active(active, archive)
    write_private(archive / f"{brief_id.lower()}.json", data)
    write_private(active, data)
    return brief_id


def read_brief(brief_id: str | None = None, *, cache: Path | None = None) -> dict[str, Any]:
    """Read the latest shared brief, or an archived one by id.

    Args:
        brief_id: UUID of the brief; the latest when omitted.
        cache: Brief cache directory; the per-OS default when omitted.

    Returns:
        The brief as stored: `briefId`, `sharedAt`, `context`, `instruction`, and `evidence`.

    Raises:
        ValueError: If `brief_id` is not a UUID, nothing was shared, the file is unreadable or not a regular
            file, the id was replaced, or the brief is older than 24 hours. An expired archived brief is deleted.
    """
    root = cache or cache_dir()
    latest = root / "active-brief.json"
    path = latest
    if brief_id is not None:
        check_uuid(brief_id)
        archived = root / "briefs" / f"{brief_id.lower()}.json"
        if archived.is_symlink() or archived.exists():
            path = archived
    try:
        brief = json.loads(read_regular(path))
        shared_at = float(brief["sharedAt"])
    except FileNotFoundError:
        raise ValueError("No shared brief is available. Share one from AnyPoach first.") from None
    except (KeyError, TypeError, json.JSONDecodeError):
        raise ValueError("The shared brief is unreadable. Share it again from AnyPoach.") from None
    if brief_id is not None and str(brief.get("briefId", "")).lower() != brief_id.lower():
        raise ValueError("This handoff was replaced or its local archive is unavailable. Share it again from AnyPoach.")
    if time.time() - shared_at > VALIDITY_SECONDS:
        # Only the app replaces the latest snapshot; archived IDs live at immutable paths.
        if path != latest:
            path.unlink(missing_ok=True)
        raise ValueError("This shared brief expired. Share it again from AnyPoach.")
    return brief
