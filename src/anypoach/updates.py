"""On-demand update check: one GET of the GitHub releases list, only when the user asks for it."""
from __future__ import annotations

import json
import re
import urllib.request
from collections.abc import Callable
from importlib.metadata import PackageNotFoundError, version

RELEASES_URL = "https://api.github.com/repos/MiguelMochizuki/anypoach/releases?per_page=1"  # includes pre-releases
TIMEOUT_S = 8


def parse_version(tag: str) -> tuple[int, ...]:
    """`v0.6.0` or `0.6.0` as `(0, 6, 0)`.

    Raises:
        ValueError: If the text is not dotted numbers.
    """
    match = re.fullmatch(r"v?(\d+(?:\.\d+)*)", tag.strip())
    if not match:
        raise ValueError(f"Not a version: {tag!r}")
    return tuple(int(part) for part in match.group(1).split("."))


def installed_version() -> str:
    """The installed package version, or `0` when AnyPoach runs from a tree that is not installed."""
    try:
        return version("anypoach")
    except PackageNotFoundError:
        return "0"


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "anypoach"})
    with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
        return response.read(1 << 20)


def check_for_update(current: str | None = None, fetch: Callable[[str], bytes] = _fetch) -> str:
    """Say in one sentence whether a newer release exists.

    Args:
        current: The running version; the installed one when omitted.
        fetch: Returns the body of a URL; replaced in tests.

    Returns:
        The sentence to show. Failures are sentences too ("Could not check for updates: ..."), never exceptions.
    """
    current = installed_version() if current is None else current
    try:
        release = json.loads(fetch(RELEASES_URL))[0]
        latest, page = str(release["tag_name"]), str(release["html_url"])
        newer = parse_version(latest) > parse_version(current)
    except (OSError, ValueError, KeyError, IndexError, TypeError) as error:
        return f"Could not check for updates: {error}"
    if newer:
        return f"AnyPoach {latest} is available (you have {current}): {page}"
    return f"AnyPoach {current} is up to date."
