"""Picks the capture backend that fits the session."""
from __future__ import annotations

import os
import sys
from collections.abc import Mapping

from .backend import CaptureBackend


def default_backend(environ: Mapping[str, str] = os.environ, platform: str = sys.platform) -> CaptureBackend:
    """Return the portal backend on a Wayland session and `mss` everywhere else.

    Args:
        environ: Environment variables to read the session type from.
        platform: Value of `sys.platform`.
    """
    if platform.startswith("linux") and environ.get("XDG_SESSION_TYPE") == "wayland":
        from .portal_backend import PortalBackend
        return PortalBackend()
    from .mss_backend import MssBackend
    return MssBackend()
