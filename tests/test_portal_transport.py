"""The DBus transport against a fake portal on a private session bus."""
import os
import shutil

import pytest

from anypoach.capture.portal import JeepneyTransport, ScreenCastClient

pytestmark = pytest.mark.skipif(shutil.which("dbus-daemon") is None, reason="dbus-daemon not found")


@pytest.fixture
def fake_portal(monkeypatch):
    from tests.portal_fake import FakePortal
    portal = FakePortal()
    monkeypatch.setenv("DBUS_SESSION_BUS_ADDRESS", portal.address)
    yield portal
    portal.stop()


def test_a_full_start_through_the_real_transport(fake_portal):
    client = ScreenCastClient(JeepneyTransport())
    session = client.start()
    assert session.streams[0].size == (640, 480) and session.streams[0].node_id == 57
    assert os.fstat(session.pipewire_fd)  # a live fd arrived over DBus
    client.close(session)
    assert fake_portal.closed_sessions == [session.handle]


def test_a_response_sent_before_the_reply_is_read_is_not_lost(fake_portal):
    fake_portal.emit_before_reply = True
    client = ScreenCastClient(JeepneyTransport())
    session = client.start()
    assert session.streams
    client.close(session)


def test_cancelling_in_the_portal_becomes_permission_error(fake_portal):
    fake_portal.start_code = 1
    with pytest.raises(PermissionError):
        ScreenCastClient(JeepneyTransport()).start()
    assert fake_portal.closed_sessions


def test_no_session_bus_is_an_oserror(monkeypatch):
    monkeypatch.delenv("DBUS_SESSION_BUS_ADDRESS", raising=False)
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/nonexistent")
    with pytest.raises(OSError):
        JeepneyTransport()


@pytest.mark.parametrize("error", ["org.freedesktop.DBus.Error.ServiceUnknown", "org.freedesktop.DBus.Error.UnknownMethod"])
def test_a_dbus_error_from_the_portal_becomes_oserror(fake_portal, error):
    fake_portal.error_name = error
    with pytest.raises(OSError, match="portal"):
        ScreenCastClient(JeepneyTransport()).start()
