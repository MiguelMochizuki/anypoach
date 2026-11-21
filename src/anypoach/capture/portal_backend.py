"""Wayland capture: the ScreenCast portal for consent and a PipeWire stream for the pixels."""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from collections.abc import Callable
from typing import Any

from anypoach.pointer.trace import Rect

from .backend import Frame, Screen
from .pipewire import PipeWireStream, gst_command
from .portal import JeepneyTransport, ScreenCastClient, ScreenCastSession


def portal_problems(which: Callable[[str], str | None] = shutil.which, run: Callable[..., Any] = subprocess.run) -> list[str]:
    """Find what is missing for portal capture and say which package fixes it.

    Args:
        which: Looks a program up on `PATH`.
        run: Runs a command; used to ask GStreamer whether the PipeWire plugin exists.

    Returns:
        One sentence per problem; empty when capture can work.
    """
    problems = []
    if which("gst-launch-1.0") is None or which("gst-inspect-1.0") is None:
        problems.append("GStreamer is missing. Install gstreamer1.0-tools and gstreamer1.0-plugins-base.")
    elif run(["gst-inspect-1.0", "pipewiresrc"], capture_output=True).returncode != 0:
        problems.append("The GStreamer PipeWire plugin is missing. Install gstreamer1.0-pipewire.")
    runtime = os.environ.get("XDG_RUNTIME_DIR", "")
    if not os.environ.get("DBUS_SESSION_BUS_ADDRESS") and not os.path.exists(os.path.join(runtime, "bus")):
        problems.append("No DBus session bus was found, so the screen sharing portal cannot be reached.")
    return problems


def _default_client() -> ScreenCastClient:
    return ScreenCastClient(JeepneyTransport())


def _default_stream(session: ScreenCastSession) -> PipeWireStream:
    stream = session.streams[0]
    return PipeWireStream(gst_command(session.pipewire_fd, stream.node_id, stream.size), stream.size,
                          pass_fds=(session.pipewire_fd,))


class PortalBackend:
    """Captures a whole monitor through the desktop portal; the area is cropped from it.

    `preview()` opens the session (the portal asks the user for consent) and must run before `grab`.
    Regions are in stream pixels with the origin at the top left. The newest frame is returned on every grab,
    stamped with the time of the grab, because the compositor only sends frames when the screen changes.

    Args:
        client_factory: Builds the portal client; replaceable for tests.
        stream_factory: Builds the frame reader for a session; replaceable for tests.
        problems: Reports missing packages; replaceable for tests.
        clock: Monotonic clock stamped on every frame.
    """
    def __init__(self, *, client_factory: Callable[[], Any] = _default_client,
                 stream_factory: Callable[[ScreenCastSession], Any] = _default_stream,
                 problems: Callable[[], list[str]] = portal_problems,
                 clock: Callable[[], float] = time.perf_counter) -> None:
        self._client_factory, self._stream_factory, self._problems, self._clock = (
            client_factory, stream_factory, problems, clock)
        self._client: Any = None
        self._session: ScreenCastSession | None = None
        self._stream: Any = None
        self._size = (0, 0)

    @property
    def active(self) -> bool:
        """Whether a session is open."""
        return self._stream is not None

    def preview(self) -> Frame:
        """Open the session and return the first frame of the shared monitor.

        Raises:
            PermissionError: If the user cancels the portal dialog.
            OSError: If packages are missing, the portal fails, or no frame arrives.
        """
        if self.active:
            if not self._stream.ended:
                return self._stream.latest()
            self.close()  # the compositor ended the share: release it and ask again instead of reusing the dead stream
        problems = self._problems()
        if problems:
            raise OSError(" ".join(problems))
        client = self._client_factory()
        session = client.start()
        stream = self._stream_factory(session)
        try:
            stream.start()
            first = stream.wait_first_frame()
        except BaseException:
            stream.close()
            client.close(session)
            raise
        self._client, self._session, self._stream = client, session, stream
        self._size = (first.pixels.shape[1], first.pixels.shape[0])
        return first

    def screens(self) -> list[Screen]:
        """The shared monitor in stream pixels, or nothing before `preview()`."""
        return [Screen(1, Rect(0, 0, *self._size), 1.0)] if self.active else []

    def grab(self, region: Rect) -> Frame:
        """Crop `region` from the newest frame, clamped to the frame.

        Raises:
            PermissionError: If no session is open.
            OSError: If the stream stopped or the region lies outside the frame.
        """
        if not self.active:
            raise PermissionError("Screen sharing is not active.")
        pixels = self._stream.latest().pixels
        height, width = pixels.shape[:2]
        left, top = max(0, round(region.x)), max(0, round(region.y))
        right, bottom = min(width, round(region.x + region.width)), min(height, round(region.y + region.height))
        if right <= left or bottom <= top:
            raise OSError("The region is outside the shared screen.")
        return Frame(pixels[top:bottom, left:right], self._clock())

    def close(self) -> None:
        """Stop the stream and close the portal session. Safe to call more than once."""
        stream, client, session = self._stream, self._client, self._session
        self._stream = self._client = self._session = None
        if stream is not None:
            stream.close()
        if client is not None and session is not None:
            client.close(session)
