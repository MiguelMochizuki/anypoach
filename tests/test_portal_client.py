"""ScreenCast client: the call sequence, the options it sends, and how portal answers become errors."""
import pytest

from anypoach.capture.portal import PortalStream, ScreenCastClient

SESSION = (0, {"session_handle": "/s/1"})
STREAMS = (0, {"streams": [(57, {"position": (0, 0), "size": (1920, 1080), "source_type": 1})]})


class FakeTransport:
    def __init__(self, responses):
        self.responses, self.calls, self.closed = list(responses), [], []

    def request(self, method, *args, options):
        self.calls.append((method, args, options))
        return self.responses.pop(0)

    def open_remote(self, session_handle):
        self.calls.append(("OpenPipeWireRemote", (session_handle,), {}))
        return 42

    def close_session(self, session_handle):
        self.closed.append(session_handle)

    def close(self):
        pass


def test_start_returns_the_stream_and_the_pipewire_fd():
    t = FakeTransport([SESSION, (0, {}), STREAMS])
    session = ScreenCastClient(t).start()
    assert session.streams == [PortalStream(57, (0, 0), (1920, 1080))]
    assert (session.handle, session.pipewire_fd) == ("/s/1", 42)
    assert [c[0] for c in t.calls] == ["CreateSession", "SelectSources", "Start", "OpenPipeWireRemote"]


def test_sources_ask_for_a_monitor_with_the_cursor_embedded_and_no_stored_permission():
    t = FakeTransport([SESSION, (0, {}), STREAMS])
    ScreenCastClient(t).start()
    options = t.calls[1][2]
    assert (options["types"], options["cursor_mode"]) == (1, 2)
    assert "persist_mode" not in options and "restore_token" not in options


def test_cancelling_the_dialog_raises_permission_error_and_closes_the_session():
    t = FakeTransport([SESSION, (0, {}), (1, {})])
    with pytest.raises(PermissionError):
        ScreenCastClient(t).start()
    assert t.closed == ["/s/1"]


def test_a_portal_failure_raises_oserror_and_closes_the_session():
    t = FakeTransport([SESSION, (2, {})])
    with pytest.raises(OSError):
        ScreenCastClient(t).start()
    assert t.closed == ["/s/1"]


def test_a_start_without_streams_raises_oserror():
    t = FakeTransport([SESSION, (0, {}), (0, {"streams": []})])
    with pytest.raises(OSError, match="no screen"):
        ScreenCastClient(t).start()
    assert t.closed == ["/s/1"]
