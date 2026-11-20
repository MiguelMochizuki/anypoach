"""Find (and remove) Poach's temporary media that no valid brief still needs."""
from __future__ import annotations

import json
import os
import re
import stat
import tempfile
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from .paths import cache_dir
from .store import VALIDITY_SECONDS, read_regular

_ID = r"[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}"
_POACH_FILES = re.compile(rf"^(?:capture-{_ID}\.mov|screenshot-{_ID}\.png)$")
_RECORDING_DIR = re.compile(r"^poach-recording-[a-zA-Z0-9]{6}$")
_RECORDING_FILE = re.compile(r"^recording\.mp4$")
_FRAME_DIR = re.compile(r"^poach-[a-zA-Z0-9]{6}$")
_FRAME_FILE = re.compile(r"^[a-zA-Z0-9_-]{1,48}-(image|(start|peak|settled)-[0-9]+ms)\.png$")


@dataclass
class Usage:
    total: int = 0
    unused: int = 0
    removable: list[Path] = field(default_factory=list)


def _real_dir(path: Path) -> bool:
    mode = path.lstat().st_mode
    return stat.S_ISDIR(mode) and not stat.S_ISLNK(mode)


def _protected_media(cache: Path) -> set[str]:
    files = [cache / "active-brief.json"]
    archive = cache / "briefs"
    if archive.is_dir():
        files += sorted(archive.glob("*.json"))
    paths: set[str] = set()
    for file in files:
        try:
            brief = json.loads(read_regular(file))
            evidence = brief["evidence"]
            if time.time() - float(brief["sharedAt"]) > VALIDITY_SECONDS:
                continue
            if evidence.get("sourcePath"):
                paths.add(evidence["sourcePath"])
            paths.update(frame["imagePath"] for frame in evidence["keyframes"])
        except FileNotFoundError:
            continue  # nothing shared yet, or a brief expired during the scan
        except (KeyError, TypeError, json.JSONDecodeError):
            raise ValueError(f"{file.name} is unreadable; refusing to guess which media is still needed") from None
    return paths


def scan_storage(*, temp: Path | None = None, cache: Path | None = None, open_paths: Iterable[str] = ()) -> Usage:
    temp = temp or Path(tempfile.gettempdir())
    protected = {os.path.realpath(p) for p in (*open_paths, *_protected_media(cache or cache_dir()))}
    usage = Usage()
    for folder in sorted(temp.iterdir()):
        if folder.name == "Poach":
            pattern = _POACH_FILES
        elif _RECORDING_DIR.match(folder.name):
            pattern = _RECORDING_FILE
        elif _FRAME_DIR.match(folder.name):
            pattern = _FRAME_FILE
        else:
            continue
        if not _real_dir(folder):
            continue
        for file in sorted(folder.iterdir()):
            if not pattern.match(file.name):
                continue
            info = file.lstat()
            if not stat.S_ISREG(info.st_mode):
                continue
            usage.total += info.st_size
            if os.path.realpath(file) not in protected:
                usage.unused += info.st_size
                usage.removable.append(file)
    return usage


def clear_storage(*, temp: Path | None = None, cache: Path | None = None, open_paths: Iterable[str] = ()) -> None:
    files = scan_storage(temp=temp, cache=cache, open_paths=open_paths).removable
    for file in files:
        file.unlink()
    for folder in {f.parent for f in files}:
        if folder.name != "Poach":
            try:
                folder.rmdir()  # only removes empty folders, even if a new file appeared meanwhile
            except OSError:
                pass
