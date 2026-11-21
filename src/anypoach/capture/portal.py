"""Client for the `xdg-desktop-portal` ScreenCast interface, used for capture on Wayland."""
from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

MONITOR = 1  # ScreenCast source type
EMBEDDED_CURSOR = 2  # ScreenCast cursor mode: the compositor draws the cursor into the video


@dataclass(frozen=True)
class PortalStream:
    """One shared monitor.

    Attributes:
        node_id: PipeWire node to read the frames from.
        position: Top-left corner in the compositor's coordinate space.
        size: Width and height of the stream.
    """
    node_id: int
    position: tuple[int, int]
    size: tuple[int, int]


@dataclass
class ScreenCastSession:
    """An open ScreenCast session.

    Attributes:
        handle: Object path of the portal session.
        streams: The shared monitors; always at least one.
        pipewire_fd: File descriptor of the PipeWire connection, owned by the caller once received.
    """
    handle: str
    streams: list[PortalStream]
    pipewire_fd: int


class PortalTransport(Protocol):
    """How the client reaches the portal, so tests can replace DBus."""
    def request(self, method: str, *args: Any, options: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Call a portal method, wait for its `Response`, and return `(code, results)` with plain values."""

    def open_remote(self, session_handle: str) -> int:
        """Return a file descriptor connected to the PipeWire daemon for the session."""

    def close_session(self, session_handle: str) -> None:
        """Close the portal session, which also ends the compositor's sharing indicator."""

    def close(self) -> None:
        """Release the connection."""


class ScreenCastClient:
    """Asks the portal to share a monitor.

    The portal itself shows the consent dialog; nothing is remembered between sessions.

    Args:
        transport: The way to reach the portal.
    """
    def __init__(self, transport: PortalTransport) -> None:
        self._transport = transport

    def start(self, *, cursor_mode: int = EMBEDDED_CURSOR) -> ScreenCastSession:
        """Create a session, let the user pick a monitor, and open the PipeWire connection.

        Args:
            cursor_mode: Portal cursor mode; the default has the compositor draw the cursor into the video.

        Returns:
            The open session. Close it with `close` when done.

        Raises:
            PermissionError: If the user cancels the portal dialog.
            OSError: If the portal fails or shares no screen.
        """
        token = uuid.uuid4().hex
        code, created = self._transport.request("CreateSession", options={"session_handle_token": f"s{token}"})
        self._check(code)
        handle = created["session_handle"]
        try:
            options = {"types": MONITOR, "multiple": False, "cursor_mode": cursor_mode}
            self._check(self._transport.request("SelectSources", handle, options=options)[0])
            code, started = self._transport.request("Start", handle, "", options={})
            self._check(code)
            streams = [PortalStream(node, tuple(p["position"]), tuple(p["size"])) for node, p in started["streams"]]
            if not streams:
                raise OSError("The portal shared no screen.")
            return ScreenCastSession(handle, streams, self._transport.open_remote(handle))
        except BaseException:
            self._transport.close_session(handle)
            raise

    def close(self, session: ScreenCastSession) -> None:
        """Close the session and its PipeWire file descriptor."""
        try:
            os.close(session.pipewire_fd)
        except OSError:
            pass
        self._transport.close_session(session.handle)

    @staticmethod
    def _check(code: int) -> None:
        if code == 1:
            raise PermissionError("Screen sharing was cancelled.")
        if code != 0:
            raise OSError(f"The screen sharing portal failed (response {code}).")
