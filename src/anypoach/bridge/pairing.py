"""The pairing code that lets the Chrome companion talk to the local server."""
from __future__ import annotations

import uuid
from pathlib import Path

from ..brief.paths import cache_dir, private_dir
from ..brief.store import check_uuid, write_private

FILE_NAME = "bridge-pairing"


def load_or_create(cache: Path | None = None) -> str:
    """Return the pairing code, creating it on first use.

    Args:
        cache: Cache directory; the per-OS default when omitted.

    Returns:
        An uppercase UUID kept in an owner-only file. A missing or malformed file is replaced.
    """
    path = private_dir(cache or cache_dir()) / FILE_NAME
    try:
        return check_uuid(path.read_text(encoding="ascii").strip()).upper()
    except (OSError, ValueError, UnicodeDecodeError):
        return rotate(cache)


def rotate(cache: Path | None = None) -> str:
    """Replace the pairing code; the old one stops working as soon as the server is given the new one."""
    code = str(uuid.uuid4()).upper()
    write_private(private_dir(cache or cache_dir()) / FILE_NAME, code.encode("ascii"))
    return code
