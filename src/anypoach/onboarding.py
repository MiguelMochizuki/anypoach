"""First-run state and the platform note shown in the welcome tour."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from anypoach.favorites import data_dir


def _marker() -> Path:
    return data_dir().parent / "onboarded"


def needs_onboarding(marker: Path | None = None) -> bool:
    """True until the welcome tour has been closed once."""
    return not (marker or _marker()).exists()


def mark_done(marker: Path | None = None) -> None:
    """Remember that the welcome tour was shown; a failure to write only means it shows again next time."""
    path = marker or _marker()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    except OSError:
        pass


def platform_note(platform: str | None = None, session: str | None = None) -> str:
    """The one thing this system asks of the user before recording works, or '' when it asks nothing.

    Args:
        platform: `sys.platform` by default.
        session: `XDG_SESSION_TYPE` by default.
    """
    platform = sys.platform if platform is None else platform
    session = os.environ.get("XDG_SESSION_TYPE", "") if session is None else session
    if platform == "darwin":
        return ("The first recording asks for Screen Recording permission: allow AnyPoach in System Settings > "
                "Privacy & Security > Screen Recording, then quit and reopen it.")
    if platform.startswith("linux") and session == "wayland":
        return ("On Wayland the desktop asks you to confirm each screen share; it needs GStreamer with its PipeWire "
                "plugin (see the README).")
    return ""
