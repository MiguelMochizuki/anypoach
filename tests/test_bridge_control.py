"""The Qt-free owner of the loopback server: start, rotate the code, stop, and report why it could not start."""
import http.client
import socket

from anypoach.bridge.control import BridgeController, extension_dir
from anypoach.bridge.evidence import EvidenceStore


def status_of(controller, code):
    connection = http.client.HTTPConnection("127.0.0.1", controller.port, timeout=5)
    connection.request("GET", "/v1/pair", headers={"Authorization": f"Bearer {code}"})
    status = connection.getresponse().status
    connection.close()
    return status


def test_start_listens_and_reports_it(tmp_path):
    bridge = BridgeController(EvidenceStore(), cache=tmp_path, port=0)
    assert bridge.status == "stopped"
    bridge.start()
    try:
        assert bridge.status == "listening" and status_of(bridge, bridge.code) == 204
    finally:
        bridge.stop()
    assert bridge.status == "stopped"


def test_a_busy_port_is_reported_not_raised(tmp_path):
    taken = socket.socket()
    taken.bind(("127.0.0.1", 0))
    taken.listen()
    port = taken.getsockname()[1]
    try:
        bridge = BridgeController(EvidenceStore(), cache=tmp_path, port=port)
        bridge.start()
        assert bridge.status.startswith("error:") and str(port) in bridge.status
        bridge.stop()
    finally:
        taken.close()


def test_rotating_the_code_replaces_what_the_server_accepts(tmp_path):
    bridge = BridgeController(EvidenceStore(), cache=tmp_path, port=0)
    bridge.start()
    try:
        old = bridge.code
        new = bridge.rotate()
        assert new != old and bridge.code == new
        assert status_of(bridge, old) == 401 and status_of(bridge, new) == 204
    finally:
        bridge.stop()


def test_stop_frees_the_port(tmp_path):
    bridge = BridgeController(EvidenceStore(), cache=tmp_path, port=0)
    bridge.start()
    port = bridge.port
    bridge.stop()
    probe = socket.socket()
    probe.bind(("127.0.0.1", port))
    probe.close()


def test_the_extension_folder_is_named_chrome_extension():
    assert extension_dir().name == "chrome_extension"
