"""Per-OS cache location and user-only permissions."""
from __future__ import annotations

import getpass
import os
import subprocess
import sys
from pathlib import Path

from platformdirs import user_cache_dir


def cache_dir() -> Path:
    """`~/Library/Caches/AnyPoach` on macOS, `~/.cache/AnyPoach` on Linux, `%LOCALAPPDATA%\\AnyPoach\\Cache` on Windows."""
    override = os.environ.get("ANYPOACH_CACHE_DIR")
    return Path(override) if override else Path(user_cache_dir("AnyPoach", appauthor=False))


def restrict(path: Path, *, directory: bool) -> None:
    """Make `path` readable only by the current user (0700/0600, or an ACL on Windows)."""
    if sys.platform == "win32":
        grant = f"{getpass.getuser()}:(OI)(CI)F" if directory else f"{getpass.getuser()}:F"
        subprocess.run(["icacls", str(path), "/inheritance:r", "/grant:r", grant], check=True, capture_output=True)
    else:
        os.chmod(path, 0o700 if directory else 0o600)


def private_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    restrict(path, directory=True)
    return path
