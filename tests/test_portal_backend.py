"""PortalBackend: session lifecycle, cropping the newest frame, and the missing-package diagnosis."""
import types

import numpy as np
import pytest

from anypoach.capture.backend import Frame, Screen
from anypoach.capture.portal import PortalStream
from anypoach.capture.portal_backend import PortalBackend, portal_problems
from anypoach.pointer.trace import Rect


def make_frame():
    pixels = np.zeros((80, 100, 4), np.uint8)
    pixels[..., 0] = np.arange(100, dtype=np.uint8)[None, :]
    pixels[..., 1] = np.arange(80, dtype=np.uint8)[:, None]
    return Frame(pixels, 1.0)


class FakeStream:
    def __init__(self):
        self.frame, self.closed, self.ended = make_frame(), 0, False

    def start(self):
        pass

    def wait_first_frame(self):
        return self.frame

    def latest(self):
        if self.ended:
            raise OSError("The screen sharing stopped.")
        return self.frame

    def end(self):
        self.ended = True

    def close(self):
        self.closed += 1


class FakeClient:
    def __init__(self, cancel):
        self.cancel, self.closed = cancel, 0

    def start(self, **options):
        self.types_seen = [*getattr(self, "types_seen", []), options.get("types", 1)]
        if self.cancel:
            raise PermissionError("Screen sharing was cancelled.")
        return types.SimpleNamespace(pipewire_fd=5, streams=[PortalStream(1, (0, 0), (100, 80))])

    def close(self, session):
        self.closed += 1


class Rig:
    def __init__(self, cancel=False, problems=()):
        self.client, self.stream = FakeClient(cancel), FakeStream()
        self.kwargs = {"client_factory": lambda: self.client, "stream_factory": lambda session: self.stream,
                       "problems": lambda: list(problems), "clock": lambda: 7.0}


def started():
    rig = Rig()
    backend = PortalBackend(**rig.kwargs)
    backend.preview()
    return backend, rig


def test_screens_are_empty_until_the_preview_opens_the_session():
    assert PortalBackend(**Rig().kwargs).screens() == []


def test_preview_opens_the_session_and_returns_the_first_frame():
    backend = PortalBackend(**Rig().kwargs)
    assert backend.preview().pixels.shape == (80, 100, 4) and backend.active
    assert backend.screens() == [Screen(1, Rect(0, 0, 100, 80), 1.0)]


def test_grab_crops_the_newest_frame_and_stamps_it_with_the_grab_time():
    backend, _ = started()
    frame = backend.grab(Rect(10, 20, 30, 40))
    assert frame.pixels.shape == (40, 30, 4) and tuple(frame.pixels[0, 0, :2]) == (10, 20)
    assert frame.time_s == 7.0


def test_grab_clamps_a_region_that_overflows_the_frame():
    backend, _ = started()
    assert backend.grab(Rect(90, 70, 50, 50)).pixels.shape == (10, 10, 4)


def test_grab_outside_the_frame_raises():
    backend, _ = started()
    with pytest.raises(OSError, match="outside"):
        backend.grab(Rect(500, 500, 10, 10))


def test_grab_after_the_stream_ended_raises_oserror():
    backend, rig = started()
    rig.stream.end()
    with pytest.raises(OSError, match="stopped"):
        backend.grab(Rect(0, 0, 10, 10))


def test_grab_before_preview_raises_permission_error():
    with pytest.raises(PermissionError):
        PortalBackend(**Rig().kwargs).grab(Rect(0, 0, 10, 10))


def test_a_cancelled_dialog_leaves_the_backend_inactive():
    backend = PortalBackend(**Rig(cancel=True).kwargs)
    with pytest.raises(PermissionError):
        backend.preview()
    assert not backend.active


def test_missing_packages_stop_the_preview_with_their_names():
    backend = PortalBackend(**Rig(problems=["Install gstreamer1.0-tools."]).kwargs)
    with pytest.raises(OSError, match="gstreamer1.0-tools"):
        backend.preview()


def test_close_stops_the_stream_and_the_session_once():
    backend, rig = started()
    backend.close()
    backend.close()
    assert rig.stream.closed == 1 and rig.client.closed == 1 and not backend.active


def test_problems_name_the_missing_package():
    assert any("gstreamer1.0-tools" in p for p in portal_problems(which=lambda name: None))


def test_problems_name_the_missing_pipewire_plugin():
    run = lambda *args, **kwargs: types.SimpleNamespace(returncode=1)
    assert any("gstreamer1.0-pipewire" in p for p in portal_problems(which=lambda n: "/bin/" + n, run=run))


def test_no_problems_when_everything_is_present(monkeypatch):
    monkeypatch.setenv("DBUS_SESSION_BUS_ADDRESS", "unix:path=/x")
    run = lambda *args, **kwargs: types.SimpleNamespace(returncode=0)
    assert portal_problems(which=lambda n: "/bin/" + n, run=run) == []


def test_a_preview_after_the_stream_ended_starts_a_new_session():
    backend, rig = started()
    rig.stream.end()
    old_stream, old_client = rig.stream, rig.client
    rig.stream, rig.client = FakeStream(), FakeClient(cancel=False)
    assert backend.preview().pixels.shape == (80, 100, 4) and backend.active
    assert old_stream.closed == 1 and old_client.closed == 1
    assert backend.grab(Rect(0, 0, 10, 10)).pixels.shape == (10, 10, 4)


def test_a_window_preview_asks_the_portal_for_windows_and_a_kind_change_reopens_the_session():
    rig = Rig()
    backend = PortalBackend(**rig.kwargs)
    backend.preview()
    backend.preview(window=True)
    backend.preview(window=True)  # same kind: the open session is reused
    assert rig.client.types_seen == [1, 2] and rig.client.closed == 1 and rig.stream.closed == 1
