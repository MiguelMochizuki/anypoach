"""The window's flow without Qt: recording, errors as messages, prompt text, and area conversion."""
import time

import numpy as np
import pytest

from anypoach.brief.store import read_brief
from anypoach.capture.backend import Frame, Screen
from anypoach.pointer.trace import Rect
from anypoach.ui.controller import Controller, handoff_prompt, physical_rect
from tests.test_pointer_recorder import Script, at


class LiveBackend:
    """Black frames stamped with the real monotonic clock, like a real display would deliver."""

    def __init__(self, error=None):
        self.error = error

    def screens(self):
        return [Screen(1, Rect(0, 0, 200, 120), 1.0)]

    def grab(self, region):
        if self.error:
            raise self.error
        return Frame(np.zeros((int(region.height), int(region.width), 4), np.uint8), time.perf_counter())


def make(tmp_path, backend=None, pointer=None):
    return Controller(backend or LiveBackend(), pointer, tmp_path / "work", cache=tmp_path / "cache")


def record(controller, seconds=0.5):
    controller.choose_region(Rect(10, 10, 160, 90))
    controller.start()
    time.sleep(seconds)
    return controller.stop()


def test_full_flow_writes_a_brief_the_mcp_side_can_read(tmp_path):
    controller = make(tmp_path, pointer=Script(at(60, 50), at(60, 50, "left"), at(100, 70, "left"), at(100, 70)))
    controller.context = "Ease the box out."
    result = record(controller)
    assert controller.message == "" and result.keyframes and result.media_type == "video"
    prompt = controller.copy_handoff()
    brief = read_brief(cache=tmp_path / "cache")
    assert brief["briefId"] in prompt and brief["context"] == "Ease the box out."
    assert brief["evidence"]["pointerTrace"]["available"] is True
    assert "anypoach_read_moment" in prompt and "button transitions" in prompt


def test_empty_region_is_a_message_not_an_exception(tmp_path):
    controller = make(tmp_path)
    controller.start()
    assert "area" in controller.message.lower() and controller.state == "idle"
    controller.choose_region(Rect(5, 5, 0, 40))
    controller.start()
    assert controller.state == "idle" and "area" in controller.message.lower()


def test_capture_permission_errors_become_a_message(tmp_path):
    controller = make(tmp_path, backend=LiveBackend(PermissionError("denied")))
    assert record(controller, 0.2) is None
    assert "permission" in controller.message.lower() and controller.state == "idle"
    assert controller.copy_handoff() == "" and controller.message
    assert not list((tmp_path / "work").glob("*.mov")), "a failed capture must not leave an empty recording behind"


def test_second_start_is_refused_and_the_first_recording_survives(tmp_path):
    controller = make(tmp_path)
    controller.choose_region(Rect(0, 0, 160, 90))
    controller.start()
    controller.start()
    assert "already" in controller.message.lower() and controller.state == "recording"
    time.sleep(0.4)
    assert controller.stop() is not None and controller.state == "ready"


def test_stop_and_handoff_without_a_recording_are_messages(tmp_path):
    controller = make(tmp_path)
    assert controller.stop() is None and controller.message
    assert controller.copy_handoff() == "" and controller.message


def test_prompt_guidance_follows_the_pointer_evidence():
    unavailable = {"available": False, "events": [], "sampleCount": 0, "insideSampleCount": 0}
    still = {"available": True, "events": [], "sampleCount": 12, "insideSampleCount": 9}
    empty = {"available": True, "events": [], "sampleCount": 0, "insideSampleCount": 0}
    assert "no native pointer trace" in handoff_prompt("ID", unavailable)
    assert "collected 12 samples, including 9 inside" in handoff_prompt("ID", still)
    assert "collected no samples" in handoff_prompt("ID", empty)
    assert handoff_prompt("ID", None).startswith("Use AnyPoach MCP to call anypoach_read_brief with briefId ID. Verify the returned briefId matches.")


@pytest.mark.parametrize(("drag", "dpr", "origin", "expected"), [
    (((10, 20), (110, 70)), 2.0, (0, 0), Rect(20, 40, 200, 100)),
    (((110, 70), (10, 20)), 1.0, (0, 0), Rect(10, 20, 100, 50)),  # dragged up-left
    (((10, 20), (60, 40)), 1.5, (-1920, 0), Rect(-2865, 30, 75, 30)),  # monitor left of the primary
])
def test_selection_is_converted_to_physical_pixels(drag, dpr, origin, expected):
    assert physical_rect(*drag, origin=origin, dpr=dpr) == expected


class PreviewBackend(LiveBackend):
    """A portal-like backend: a preview frame first, and a session that must be closed."""

    def __init__(self):
        super().__init__()
        self.closed, self.failure = 0, None

    def preview(self):
        if self.failure:
            raise self.failure
        return Frame(np.zeros((120, 200, 4), np.uint8), time.perf_counter())

    def close(self):
        self.closed += 1


@pytest.fixture
def preview_controller(tmp_path):
    return make(tmp_path, backend=PreviewBackend())


def test_controller_without_a_preview_backend_does_not_support_it(tmp_path):
    controller = make(tmp_path)
    assert not controller.supports_preview and controller.preview() is None


def test_a_cancelled_portal_dialog_becomes_a_message(preview_controller):
    preview_controller.backend.failure = PermissionError("Screen sharing was cancelled.")
    assert preview_controller.preview() is None and "cancelled" in preview_controller.message


def test_stop_closes_the_portal_and_forgets_the_region(preview_controller):
    assert preview_controller.preview() is not None
    record(preview_controller)
    assert preview_controller.backend.closed == 1
    preview_controller.start()
    assert "Choose an area" in preview_controller.message


def test_a_stream_that_ended_before_recording_is_a_message(preview_controller):
    preview_controller.preview()
    preview_controller.choose_region(Rect(0, 0, 50, 50))
    preview_controller.backend.error = OSError("The screen sharing stopped.")
    preview_controller.start()
    assert preview_controller.state == "idle" and "stopped" in preview_controller.message


def test_close_releases_the_backend_and_the_region(preview_controller):
    preview_controller.preview()
    preview_controller.choose_region(Rect(0, 0, 50, 50))
    preview_controller.close()
    assert preview_controller.backend.closed == 1
    preview_controller.start()
    assert "Choose an area" in preview_controller.message


def test_ready_to_record_needs_an_area_and_no_running_recording(tmp_path):
    controller = make(tmp_path)
    assert not controller.ready_to_record
    controller.choose_region(Rect(10, 10, 160, 90))
    assert controller.ready_to_record
    controller.start()
    assert not controller.ready_to_record
    controller.stop()


def test_stop_sharing_during_a_recording_still_closes_the_portal(preview_controller):
    preview_controller.preview()
    preview_controller.choose_region(Rect(10, 10, 160, 90))
    preview_controller.start()
    time.sleep(0.3)
    preview_controller.backend.error = OSError("The screen sharing stopped.")  # the compositor ended the share
    time.sleep(0.3)
    assert preview_controller.stop() is None and "stopped" in preview_controller.message
    assert preview_controller.backend.closed == 1


def test_a_failed_first_grab_closes_the_portal_so_the_next_choice_starts_fresh(preview_controller):
    preview_controller.preview()
    preview_controller.choose_region(Rect(0, 0, 50, 50))
    preview_controller.backend.error = OSError("The screen sharing stopped.")
    preview_controller.start()
    assert preview_controller.backend.closed == 1


def test_device_scale_reaches_the_shared_brief(tmp_path):
    controller = make(tmp_path)
    controller.choose_region(Rect(10, 10, 160, 90), device_scale=2.0)
    controller.start()
    time.sleep(0.5)
    result = controller.stop()
    assert result.capture.device_scale == 2.0
    controller.copy_handoff()
    capture = read_brief(cache=tmp_path / "cache")["evidence"]["capture"]
    assert capture["deviceScale"] == 2.0 and capture["widthPx"] == result.capture.width_px


def test_device_scale_is_null_when_not_given(tmp_path):
    controller = make(tmp_path)
    assert record(controller).capture.device_scale is None


def test_choosing_again_resets_the_scale(tmp_path):
    controller = make(tmp_path)
    controller.choose_region(Rect(0, 0, 50, 50), device_scale=2.0)
    assert controller.device_scale == 2.0
    controller.choose_region(Rect(0, 0, 50, 50))
    assert controller.device_scale is None


def test_handoff_prompt_explains_size_and_scale():
    prompt = handoff_prompt("ID", None)
    assert "evidence.capture" in prompt and "deviceScale" in prompt and "reduced" in prompt
    assert "ask" in prompt.split("deviceScale")[-1]


def test_device_scale_counts_video_pixels_when_the_recorder_downsizes(tmp_path):
    controller = make(tmp_path)
    controller.choose_region(Rect(0, 0, 2400, 1200), device_scale=2.0)  # 1200x600 CSS px, recorded at 1920 px wide
    controller.start()
    time.sleep(0.4)
    result = controller.stop()
    assert result.capture.width_px == 1920
    assert result.capture.device_scale == pytest.approx(1.6)  # video pixels per CSS pixel, not the screen's 2.0
