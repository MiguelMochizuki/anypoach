"""The recorder and capture backend: frame times, sizes, frame rate, cursor drawing, and failures."""
import itertools
from types import SimpleNamespace
from typing import ClassVar

import av
import numpy as np
import pytest

from anypoach.analysis.inspect import inspect_recording
from anypoach.analysis.source import VideoSource
from anypoach.capture.backend import Frame, Screen
from anypoach.capture.mss_backend import MssBackend
from anypoach.capture.overlay import CLICK_RING_SECONDS, draw_click_ring, draw_cursor
from anypoach.capture.recorder import Recorder
from anypoach.macos import Display
from anypoach.pointer.recorder import PointerTraceRecorder
from anypoach.pointer.trace import Rect
from tests.test_pointer_recorder import Clock, Script, at


class FakeBackend:
    """Returns black frames and advances the fake clock by a scripted amount per grab (slow or stalled grabs)."""

    def __init__(self, clock, steps=(0.0,)):
        self.clock, self.steps, self.grabs = clock, list(steps), 0

    def screens(self):
        return [Screen(1, Rect(0, 0, 100, 100), 1.0)]

    def grab(self, region):
        self.clock.now += self.steps[min(self.grabs, len(self.steps) - 1)]
        self.grabs += 1
        return Frame(np.zeros((int(region.height), int(region.width), 4), np.uint8), self.clock.now)


def make(tmp_path, steps=(0.0,), pointer=None, clock=None, **kwargs):
    clock = clock or Clock()
    return Recorder(FakeBackend(clock, steps), pointer, tmp_path, clock=clock, wall_clock=lambda: 1_700_000_000.0 + clock.now,
                    sleep=lambda s: setattr(clock, "now", clock.now + s), **kwargs), clock


def stream_size(path):
    with av.open(str(path)) as c:
        s = c.streams.video[0]
        return s.codec_context.width, s.codec_context.height


def test_frames_keep_their_real_presentation_times(tmp_path):
    recorder, _ = make(tmp_path, steps=[0.001, 0.033, 0.037, 0.43, 0.033])
    recorder.start(Rect(0, 0, 64, 48), spawn=False)
    for _ in range(5):
        recorder.capture_once()
    recording = recorder.stop()
    with VideoSource(recording.path) as source:
        times = source.presentation_times
    assert len(times) == 5, "frames are never invented to fill gaps"
    gaps = [round((b - a) * 1000) for a, b in itertools.pairwise(times)]
    assert gaps == [33, 37, 430, 33]
    assert recording.path.suffix == ".mov" and recording.path.name.startswith("capture-")


@pytest.mark.parametrize(("width", "height", "expected"), [(4001, 1001, (1920, 480)), (101, 51, (100, 50)), (1, 1, (2, 2)), (1920, 1080, (1920, 1080))])
def test_dimensions_are_even_and_capped_at_1920(tmp_path, width, height, expected):
    recorder, _ = make(tmp_path)
    recorder.start(Rect(0, 0, width, height), spawn=False)
    recorder.capture_once()
    recorder.capture_once()
    assert stream_size(recorder.stop().path) == expected


def test_capture_never_exceeds_30_fps(tmp_path):
    recorder, clock = make(tmp_path)
    recorder.start(Rect(0, 0, 32, 32), spawn=False)
    stop_at = clock.now + 1.0
    real_sleep = recorder._sleep
    recorder._sleep = lambda s: (real_sleep(s), recorder.request_stop() if clock.now >= stop_at else None)
    recorder.run()
    with VideoSource(recorder.stop().path) as source:
        assert 25 <= len(source.presentation_times) <= 31


def test_cursor_and_click_ring_are_drawn_from_the_pointer(tmp_path):
    clock = Clock()
    pointer = PointerTraceRecorder(Rect(0, 0, 100, 100), Script(at(40, 30, "left")), clock=clock)
    pointer.start(spawn=False)
    pointer.poll()
    recorder, _ = make(tmp_path, pointer=pointer, clock=clock)
    recorder.start(Rect(0, 0, 100, 100), spawn=False)
    recorder.capture_once()
    recorder.capture_once()
    recording = recorder.stop()
    with av.open(str(recording.path)) as container:
        frame = next(container.decode(video=0)).to_ndarray(format="rgb24").astype(int)
    assert frame[30:40, 40:46].mean() > 40, "the cursor is drawn at the pointer position"
    assert frame[80:100, 0:20].mean() < 10, "the rest of the frame is untouched"
    assert recording.trace.available and recording.trace.sample_count == 1


def test_overlay_primitives():
    blank = lambda: np.zeros((100, 100, 4), np.uint8)
    cursor = blank()
    draw_cursor(cursor, 10, 10, 1.0)
    assert cursor[10:25, 10:20].any() and not cursor[40:, 40:].any()
    ring = blank()
    draw_click_ring(ring, 50, 50, 0.1, 1.0)
    assert ring.any() and not ring[50, 50].any()  # a ring, not a disc
    expired = blank()
    draw_click_ring(expired, 50, 50, CLICK_RING_SECONDS + 0.01, 1.0)
    assert not expired.any()
    draw_cursor(cursor, -500, 500, 1.0)  # fully outside the frame is a no-op, not an error
    edge = blank()
    draw_cursor(edge, 98, 98, 1.0)  # partly outside is clipped


def test_recording_reads_back_through_the_analysis_and_reports_the_epoch_range(tmp_path):
    recorder, _ = make(tmp_path, steps=[0.1])
    recorder.start(Rect(0, 0, 96, 64), spawn=False)
    for _ in range(6):
        recorder.capture_once()
    recording = recorder.stop()
    assert recording.trace.available is False  # no pointer source was given
    start, end = recording.epoch_range_ms
    assert end - start == pytest.approx(600, abs=150) and start > 1_700_000_000_000
    assert inspect_recording(recording.path, output_dir=tmp_path / "frames").keyframes


def test_stopping_without_any_frame_is_an_error_not_an_empty_file(tmp_path):
    recorder, _ = make(tmp_path)
    recorder.start(Rect(0, 0, 32, 32), spawn=False)
    with pytest.raises(ValueError, match="no frames"):
        recorder.stop()
    assert not list(tmp_path.glob("*.mov"))


def test_mss_backend_converts_regions_and_monitors():
    shots = []

    class FakeSct:
        monitors: ClassVar = [{"left": -10, "top": 0, "width": 30, "height": 10}, {"left": -10, "top": 0, "width": 30, "height": 10}]

        def grab(self, box):
            shots.append(box)
            return SimpleNamespace(bgra=bytes(box["width"] * box["height"] * 4), width=box["width"], height=box["height"])

    backend = MssBackend(sct=FakeSct(), clock=lambda: 5.0, platform="linux")
    assert backend.screens() == [Screen(1, Rect(-10, 0, 30, 10), 1.0)]
    frame = backend.grab(Rect(-5.4, 2.0, 11.6, 4.0))
    assert shots == [{"left": -5, "top": 2, "width": 12, "height": 4}]
    assert frame.pixels.shape == (4, 12, 4) and frame.time_s == 5.0


class RetinaSct:
    """`mss` as measured on macOS (assumption A1): boxes in points, frames in pixels (`scale` times larger)."""
    monitors: ClassVar = [{}, {"left": 0, "top": 0, "width": 1512, "height": 982}]

    def __init__(self, scale=2):
        self.boxes, self.scale = [], scale

    def grab(self, box):
        self.boxes.append(box)
        w, h = box["width"] * self.scale, box["height"] * self.scale
        return SimpleNamespace(bgra=bytes(w * h * 4), width=w, height=h)


class FakeCG:
    def __init__(self, *displays):
        self._displays = list(displays)

    def displays(self):
        return self._displays


RETINA = Display(1, Rect(0, 0, 1512, 982), 2.0)
LEFT_1X = Display(2, Rect(-1920, 0, 1920, 1080), 1.0)


def test_retina_region_is_converted_to_points_and_the_frame_has_the_region_size():
    sct = RetinaSct()
    backend = MssBackend(sct=sct, platform="darwin", cg=FakeCG(RETINA), clock=lambda: 1.0)
    frame = backend.grab(Rect(200, 100, 800, 600))
    assert sct.boxes == [{"left": 100, "top": 50, "width": 400, "height": 300}]
    assert frame.pixels.shape == (600, 800, 4)


def test_an_odd_retina_region_covers_whole_points_and_is_cropped_to_its_size():
    sct = RetinaSct()
    frame = MssBackend(sct=sct, platform="darwin", cg=FakeCG(RETINA)).grab(Rect(201, 101, 801, 601))
    assert sct.boxes == [{"left": 100, "top": 50, "width": 401, "height": 301}]
    assert frame.pixels.shape == (601, 801, 4)


def test_a_1x_display_next_to_a_retina_one_uses_its_own_scale():
    sct = RetinaSct(scale=1)
    frame = MssBackend(sct=sct, platform="darwin", cg=FakeCG(RETINA, LEFT_1X)).grab(Rect(-1000, 100, 200, 100))
    assert sct.boxes == [{"left": -1000, "top": 100, "width": 200, "height": 100}]
    assert frame.pixels.shape == (100, 200, 4)


def test_a_short_frame_is_padded_to_the_region_size():
    sct = RetinaSct(scale=1)  # the display claims 2x but mss answered at 1x: still hand the recorder the right size
    frame = MssBackend(sct=sct, platform="darwin", cg=FakeCG(RETINA)).grab(Rect(200, 100, 800, 600))
    assert frame.pixels.shape == (600, 800, 4)


def test_screens_report_physical_bounds_and_scale_on_macos():
    backend = MssBackend(sct=RetinaSct(), platform="darwin", cg=FakeCG(RETINA, LEFT_1X))
    assert backend.screens() == [Screen(1, Rect(0, 0, 3024, 1964), 2.0), Screen(2, Rect(-1920, 0, 1920, 1080), 1.0)]


def test_other_platforms_do_not_convert():
    sct = RetinaSct(scale=1)
    MssBackend(sct=sct, platform="linux", cg=FakeCG(RETINA)).grab(Rect(200, 100, 800, 600))
    assert sct.boxes == [{"left": 200, "top": 100, "width": 800, "height": 600}]


@pytest.mark.live
def test_live_capture_of_a_real_display(tmp_path):
    import os
    import sys
    linux_without_x11 = sys.platform.startswith("linux") and (not os.environ.get("DISPLAY") or os.environ.get("XDG_SESSION_TYPE") == "wayland")
    if linux_without_x11 or sys.platform == "darwin":
        pytest.skip("needs an X11 or Windows desktop session")
    backend = MssBackend()
    screen = backend.screens()[0]
    recorder = Recorder(backend, None, tmp_path)
    recorder.start(Rect(screen.bounds.x, screen.bounds.y, min(320, screen.bounds.width), min(200, screen.bounds.height)))
    import time
    time.sleep(1.0)
    with VideoSource(recorder.stop().path) as source:
        assert len(source.presentation_times) >= 5


def test_frames_grabbed_at_the_same_instant_still_get_increasing_times(tmp_path):
    recorder, _ = make(tmp_path)  # the fake clock never advances: every frame carries the same time_s
    recorder.start(Rect(0, 0, 32, 32), spawn=False)
    for _ in range(4):
        recorder.capture_once()
    with VideoSource(recorder.stop().path) as source:
        times = source.presentation_times
    assert len(times) == 4 and all(b > a for a, b in itertools.pairwise(times))


def test_recording_name_is_recognized_by_the_storage_cleanup(tmp_path):
    from anypoach.brief.cleanup import _ANYPOACH_FILES
    recorder, _ = make(tmp_path)
    recorder.start(Rect(0, 0, 32, 32), spawn=False)
    recorder.capture_once()
    assert _ANYPOACH_FILES.match(recorder.stop().path.name)
