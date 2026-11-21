"""The loopback server the Chrome companion talks to, driven with a real HTTP client."""
import http.client
import json
import socket
import time

import pytest

from anypoach.bridge.evidence import EvidenceStore
from anypoach.bridge.server import BridgeServer
from tests.test_bridge_evidence import START, session

CODE = "0123ABCD-0000-4000-8000-0123456789AB"
RANGE = (START, START + 1000)


@pytest.fixture
def running():
    store = EvidenceStore()
    server = BridgeServer(store, CODE, port=0, timeout=0.5)
    server.start()
    yield server, store
    server.stop()


def call(server, method, path, body=None, headers=None, host=None):
    connection = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
    all_headers = {"Authorization": f"Bearer {CODE}", **(headers or {})}
    if host:
        connection.putrequest(method, path, skip_host=True)
        connection.putheader("Host", host)
        for name, value in all_headers.items():
            connection.putheader(name, value)
        data = body if isinstance(body, bytes) else (json.dumps(body).encode() if body is not None else b"")
        connection.putheader("Content-Length", str(len(data)))
        connection.endheaders(data)
    else:
        data = body if isinstance(body, bytes) else (json.dumps(body).encode() if body is not None else None)
        if data is not None:
            all_headers.setdefault("Content-Type", "application/json")
        connection.request(method, path, body=data, headers=all_headers)
    response = connection.getresponse()
    response.read()
    status = response.status
    connection.close()
    return status


def test_pair_requires_the_bearer_code(running):
    server, _ = running
    assert call(server, "GET", "/v1/pair") == 204
    assert call(server, "GET", "/v1/pair", headers={"Authorization": "Bearer WRONG"}) == 401
    assert call(server, "GET", "/v1/pair", headers={"Authorization": ""}) == 401
    assert call(server, "GET", f"/v1/pair?code={CODE}", headers={"Authorization": ""}) == 401
    assert server.connected


def test_capture_is_stored_as_final_or_partial(running):
    server, store = running
    assert call(server, "POST", "/v1/capture", session(), {"X-AnyPoach-Final": "0"}) == 204
    assert store.receiving_for(RANGE) and store.latest_for(RANGE) is None
    assert call(server, "POST", "/v1/capture", session(), {"X-AnyPoach-Final": "1"}) == 204
    assert store.latest_for(RANGE)["videoOffsetMs"] == 0


def test_a_foreign_host_header_is_refused(running):
    server, _ = running
    assert call(server, "GET", "/v1/pair", host="evil.example:47832") == 403
    assert call(server, "GET", "/v1/pair", host=f"localhost:{server.port}") == 204
    assert call(server, "GET", "/v1/pair", host=f"127.0.0.1:{server.port}") == 204


def test_a_web_page_origin_is_refused(running):
    server, _ = running
    assert call(server, "GET", "/v1/pair", headers={"Origin": "https://evil.example"}) == 403
    assert call(server, "GET", "/v1/pair", headers={"Origin": "chrome-extension://abcdef"}) == 204


def test_a_web_page_without_the_code_gets_nothing(running):
    server, _ = running
    assert call(server, "POST", "/v1/capture", session(),
                {"Authorization": "", "Origin": "https://evil.example"}) == 403
    assert call(server, "POST", "/v1/capture", session(), {"Authorization": "Bearer guess"}) == 401


def test_oversized_and_lying_bodies_are_bounded(running):
    server, _ = running
    assert call(server, "POST", "/v1/capture", b"x" * (300 * 1024), {"Content-Type": "application/json"}) == 413
    sock = socket.create_connection(("127.0.0.1", server.port), timeout=5)
    sock.sendall(f"POST /v1/capture HTTP/1.1\r\nHost: 127.0.0.1:{server.port}\r\nAuthorization: Bearer {CODE}\r\n"
                 "Content-Type: application/json\r\nContent-Length: 5000\r\n\r\n{}".encode())
    sock.close()
    started = time.monotonic()
    assert call(server, "GET", "/v1/pair") == 204 and time.monotonic() - started < 2


def test_invalid_evidence_and_invalid_json_are_422(running):
    server, _ = running
    assert call(server, "POST", "/v1/capture", session(version=2)) == 422
    assert call(server, "POST", "/v1/capture", b"not json", {"Content-Type": "application/json"}) == 422


def test_missing_length_or_content_type_is_400(running):
    server, _ = running
    assert call(server, "POST", "/v1/capture", session(), {"Content-Type": "text/plain"}) == 400
    sock = socket.create_connection(("127.0.0.1", server.port), timeout=5)
    sock.sendall(f"POST /v1/capture HTTP/1.1\r\nHost: 127.0.0.1:{server.port}\r\nAuthorization: Bearer {CODE}\r\n"
                 "Content-Type: application/json\r\n\r\n".encode())
    assert b" 400 " in sock.recv(256).split(b"\r\n")[0]
    sock.close()


def test_a_stalled_client_is_dropped(running):
    server, _ = running
    stalled = socket.create_connection(("127.0.0.1", server.port), timeout=5)
    stalled.sendall(f"GET /v1/pair HTTP/1.1\r\nHost: 127.0.0.1:{server.port}\r\n".encode())
    assert call(server, "GET", "/v1/pair") == 204
    time.sleep(0.8)
    assert stalled.recv(1) == b""
    stalled.close()


def test_routes_and_methods(running):
    server, _ = running
    assert call(server, "GET", "/v1/nothing") == 404
    assert call(server, "POST", "/v1/pair") == 405
    assert call(server, "DELETE", "/v1/capture") == 405


def test_open_capture_uses_the_callback():
    store = EvidenceStore()
    without = BridgeServer(store, CODE, port=0)
    with_callback = BridgeServer(store, CODE, port=0, on_open=lambda: True)
    for server in (without, with_callback):
        server.start()
    try:
        assert call(without, "POST", "/v1/open-capture") == 503
        assert call(with_callback, "POST", "/v1/open-capture") == 204
    finally:
        without.stop()
        with_callback.stop()


def test_start_reports_a_busy_port():
    taken = socket.socket()
    taken.bind(("127.0.0.1", 0))
    taken.listen()
    port = taken.getsockname()[1]
    try:
        with pytest.raises(OSError, match=str(port)):
            BridgeServer(EvidenceStore(), CODE, port=port).start()
    finally:
        taken.close()


def test_stop_releases_the_port():
    server = BridgeServer(EvidenceStore(), CODE, port=0)
    server.start()
    port = server.port
    server.stop()
    probe = socket.socket()
    probe.bind(("127.0.0.1", port))
    probe.close()


def test_windows_binds_the_port_exclusively(monkeypatch):
    """On Windows SO_REUSEADDR lets a second process share the port, so a busy port would go unnoticed."""
    monkeypatch.setattr("anypoach.bridge.server.sys.platform", "win32")
    server = BridgeServer(EvidenceStore(), CODE, port=0)
    server.start()
    try:
        assert server._httpd.allow_reuse_address is False
    finally:
        server.stop()


def test_an_oversized_body_still_gets_its_413_while_the_client_is_sending(running):
    """Closing with the body unread resets the connection, so the sender would see an error instead of the status."""
    server, _ = running
    for _ in range(20):
        sock = socket.create_connection(("127.0.0.1", server.port), timeout=5)
        body = b"x" * (900 * 1024)
        sock.sendall(f"POST /v1/capture HTTP/1.1\r\nHost: 127.0.0.1:{server.port}\r\nAuthorization: Bearer {CODE}\r\n"
                     f"Content-Type: application/json\r\nContent-Length: {len(body)}\r\n\r\n".encode() + body)
        try:
            reply = sock.recv(64)
        except ConnectionResetError:
            reply = b"reset"
        sock.close()
        assert b" 413 " in reply, reply


def test_a_session_with_41_components_is_422_and_one_with_components_is_204(running):
    server, store = running
    item = {"id": 0, "parent": -1, "target": {"tag": "p", "role": "", "classes": ""}, "rect": [0, 0, 10, 10], "styles": {}, "text": ""}
    many = [{**item, "id": i} for i in range(41)]
    assert call(server, "POST", "/v1/capture", session(components=many)) == 422
    assert call(server, "POST", "/v1/capture", session(components=[item]), {"X-AnyPoach-Final": "1"}) == 204
    assert store.latest_for((START, START + 1000))["components"] == [item]
