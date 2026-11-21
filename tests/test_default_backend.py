"""Which capture backend a session gets."""
from anypoach.capture.default import default_backend
from anypoach.capture.mss_backend import MssBackend
from anypoach.capture.portal_backend import PortalBackend


def test_wayland_gets_the_portal_backend():
    assert isinstance(default_backend({"XDG_SESSION_TYPE": "wayland"}, "linux"), PortalBackend)


def test_x11_and_windows_keep_mss():
    assert isinstance(default_backend({"XDG_SESSION_TYPE": "x11"}, "linux"), MssBackend)
    assert isinstance(default_backend({}, "win32"), MssBackend)
