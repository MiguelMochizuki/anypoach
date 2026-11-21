"""The macOS pointer source, against a fake CoreGraphics."""
import sys

import pytest

from anypoach import pointer
from anypoach.macos import Display
from anypoach.pointer.macos import MacPointerSource
from anypoach.pointer.trace import Rect


class FakeCG:
    def __init__(self, *rounds, at=(0.0, 0.0), down=()):
        self.rounds, self.at, self.down, self.calls = list(rounds), at, set(down), 0

    def displays(self):
        self.calls += 1
        return self.rounds[min(self.calls, len(self.rounds)) - 1]

    def pointer(self):
        return self.at

    def button_down(self, button):
        return button in self.down


def xy(sample):
    return sample.x, sample.y


RETINA = Display(1, Rect(0, 0, 1512, 982), 2.0)
LEFT_1X = Display(2, Rect(-1920, 0, 1920, 1080), 1.0)


def test_points_become_pixels_with_the_scale_of_the_display_under_the_pointer():
    cg = FakeCG([RETINA, LEFT_1X], at=(100, 50))
    assert xy(MacPointerSource(cg).sample()) == (200, 100)
    cg.at = (-1000, 40)
    assert xy(MacPointerSource(cg).sample()) == (-1000, 40)


def test_origin_of_a_second_display_scales_from_the_global_origin():
    right = Display(2, Rect(1512, 0, 1512, 982), 2.0)
    assert xy(MacPointerSource(FakeCG([RETINA, right], at=(1612, 10))).sample()) == (3224, 20)


def test_buttons_report_left_right_and_other():
    sample = MacPointerSource(FakeCG([RETINA], at=(1, 1), down={"left", "other"})).sample()
    assert sample.buttons == frozenset({"left", "other"})


def test_a_pointer_outside_every_display_refreshes_once_then_clamps():
    cg = FakeCG([RETINA], [RETINA, LEFT_1X], at=(-500, 20))
    source = MacPointerSource(cg)
    assert xy(source.sample()) == (-500, 20)  # the refresh found the display on the left
    assert cg.calls == 2
    cg.at = (9000, 20)  # outside everything: nearest display (the retina one), no second refresh storm
    assert source.sample().x == 18000


def test_no_displays_at_all_does_not_raise():
    assert xy(MacPointerSource(FakeCG([], at=(5, 6))).sample()) == (5, 6)


def test_default_source_is_a_mac_source_on_darwin(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr("anypoach.macos.CoreGraphics", lambda: FakeCG([RETINA]))
    assert isinstance(pointer.default_source(), MacPointerSource)


def test_default_source_is_none_when_coregraphics_is_missing(monkeypatch):
    def boom():
        raise OSError("no CoreGraphics")
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr("anypoach.macos.CoreGraphics", boom)
    assert pointer.default_source() is None


@pytest.mark.skipif(sys.platform != "darwin", reason="needs CoreGraphics")
def test_real_source_samples():
    assert MacPointerSource().sample().buttons is not None
