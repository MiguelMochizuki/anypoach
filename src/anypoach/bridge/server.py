"""The loopback HTTP server the Chrome companion posts browser evidence to."""
from __future__ import annotations

import hmac
import sys
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .evidence import BYTE_LIMIT, EvidenceStore, parse_evidence

HOST = "127.0.0.1"
DEFAULT_PORT = 47832
_MARGIN = 4096


class _Server(ThreadingHTTPServer):
    def server_bind(self) -> None:
        # On Windows SO_REUSEADDR lets a second process bind a port that is already in use, so the busy-port error never shows.
        self.allow_reuse_address = sys.platform != "win32"
        super().server_bind()


class BridgeServer:
    """Accepts evidence from the paired Chrome extension, on 127.0.0.1 only.

    Every request must carry `Authorization: Bearer <code>`. Requests from a foreign `Host` (DNS rebinding) or from
    a web page (`Origin` other than `chrome-extension://`) are refused before anything is read.

    Args:
        store: Where accepted sessions go.
        code: The pairing code.
        port: TCP port; 0 picks a free one (see `port`).
        on_open: Called by `POST /v1/open-capture`; it answers 204 when it returns True and 503 otherwise.
        timeout: Seconds a client may stall before its connection is dropped.

    Attributes:
        connected: Whether an authorized request has been seen.
    """
    def __init__(self, store: EvidenceStore, code: str, *, port: int = DEFAULT_PORT,
                 on_open: Callable[[], bool] | None = None, timeout: float = 5.0) -> None:
        self._store, self._code, self._requested_port = store, code, port
        self._on_open, self._timeout = on_open, timeout
        self._httpd: _Server | None = None
        self._thread: threading.Thread | None = None
        self.connected = False

    @property
    def port(self) -> int:
        """The bound port once started, otherwise the requested one."""
        return self._httpd.server_address[1] if self._httpd else self._requested_port

    def set_code(self, code: str) -> None:
        """Start accepting `code` instead of the previous one."""
        self._code = code
        self.connected = False

    def start(self) -> None:
        """Bind the port and serve on a background thread.

        Raises:
            OSError: If the port is taken; the message names it.
        """
        owner = self

        class Handler(_Handler):
            timeout = owner._timeout
            bridge = owner

        try:
            self._httpd = _Server((HOST, self._requested_port), Handler)
        except OSError as error:
            raise OSError(f"Port {self._requested_port} is already in use, so Chrome cannot connect ({error.strerror})") from error
        httpd = self._httpd
        httpd.daemon_threads = True
        self._thread = threading.Thread(target=lambda: httpd.serve_forever(poll_interval=0.05), name="anypoach-bridge", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop serving and release the port. Safe to call when not started."""
        httpd, self._httpd = self._httpd, None
        if httpd is not None:
            httpd.shutdown()
            httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None


class _Handler(BaseHTTPRequestHandler):
    bridge: BridgeServer
    server_version = "AnyPoach"
    sys_version = ""

    def log_message(self, *args) -> None:
        return

    def _reply(self, status: int) -> None:
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True

    def _allowed_host(self) -> bool:
        port = self.server.server_address[1]
        return self.headers.get("Host", "") in (f"127.0.0.1:{port}", f"localhost:{port}")

    def _allowed_origin(self) -> bool:
        origin = self.headers.get("Origin")
        return origin is None or origin.startswith("chrome-extension://")

    def _authorized(self) -> bool:
        sent = self.headers.get("Authorization", "")
        return hmac.compare_digest(sent.encode("utf-8", "replace"), f"Bearer {self.bridge._code}".encode())

    def _handle(self, method: str) -> None:
        if not (self._allowed_host() and self._allowed_origin()):
            return self._reply(403)
        if not self._authorized():
            return self._reply(401)
        self.bridge.connected = True
        path = self.path.split("?", 1)[0]
        routes = {"/v1/pair": "GET", "/v1/capture": "POST", "/v1/open-capture": "POST"}
        if path not in routes:
            return self._reply(404)
        if routes[path] != method:
            return self._reply(405)
        if path == "/v1/pair":
            return self._reply(204)
        if path == "/v1/open-capture":
            return self._reply(204 if self.bridge._on_open and self.bridge._on_open() else 503)
        return self._capture()

    def _discard(self, length: int) -> None:
        """Read and drop up to 1 MiB of a refused body: closing with it unread resets the connection, and the sender
        would see a network error instead of the status."""
        remaining = min(length, 1 << 20)
        while remaining > 0:
            try:
                chunk = self.rfile.read(min(remaining, 65536))
            except OSError:
                return
            if not chunk:
                return
            remaining -= len(chunk)

    def _capture(self) -> None:
        if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
            return self._reply(400)
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            return self._reply(400)
        if length < 1:
            return self._reply(400)
        if length > BYTE_LIMIT + _MARGIN:
            self._discard(length)
            return self._reply(413)
        body = self.rfile.read(length)
        if len(body) != length:
            return self._reply(400)
        try:
            evidence = parse_evidence(body)
        except ValueError:
            return self._reply(422)
        self.bridge._store.put(evidence, final=self.headers.get("X-AnyPoach-Final") == "1")
        self._reply(204)

    def do_GET(self) -> None:
        self._handle("GET")

    def do_POST(self) -> None:
        self._handle("POST")

    def do_PUT(self) -> None:
        self._handle("PUT")

    def do_DELETE(self) -> None:
        self._handle("DELETE")
