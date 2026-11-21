"""Owns the loopback server for the window: start, stop, rotate the pairing code, and say why it cannot start."""
from __future__ import annotations

from collections.abc import Callable
from importlib.resources import files
from pathlib import Path

from . import pairing
from .evidence import EvidenceStore
from .server import DEFAULT_PORT, BridgeServer


def extension_dir() -> Path:
    """Folder of the packaged Chrome extension, to load as an unpacked extension."""
    return Path(str(files("anypoach") / "chrome_extension"))


class BridgeController:
    """The server, its pairing code and a status the window can show, with no Qt in it.

    Args:
        store: Where accepted Chrome sessions go.
        cache: Cache directory that holds the pairing code; the per-OS default when omitted.
        port: TCP port; 0 picks a free one.
        on_open: Called when the extension asks AnyPoach to open its capture window.

    Attributes:
        status: `stopped`, `listening`, or `error: <reason>` (for example a port that is already in use).
    """
    def __init__(self, store: EvidenceStore, *, cache: Path | None = None, port: int = DEFAULT_PORT,
                 on_open: Callable[[], bool] | None = None) -> None:
        self._store, self._cache, self._port, self._on_open = store, cache, port, on_open
        self._code = pairing.load_or_create(cache)
        self._server: BridgeServer | None = None
        self.status = "stopped"

    @property
    def code(self) -> str:
        """The pairing code the extension needs."""
        return self._code

    @property
    def port(self) -> int:
        """The bound port while listening, otherwise the requested one."""
        return self._server.port if self._server else self._port

    def start(self) -> None:
        """Start listening. A port problem becomes `status` instead of an exception."""
        self.stop()
        server = BridgeServer(self._store, self._code, port=self._port, on_open=self._on_open)
        try:
            server.start()
        except OSError as error:
            self.status = f"error: {error}"
            return
        self._server, self.status = server, "listening"

    def rotate(self) -> str:
        """Create a new pairing code; the old one stops working at once."""
        self._code = pairing.rotate(self._cache)
        if self._server is not None:
            self._server.set_code(self._code)
        return self._code

    def stop(self) -> None:
        """Stop listening and release the port."""
        if self._server is not None:
            self._server.stop()
            self._server = None
        self.status = "stopped"
