"""The window's flow without Qt: recording, errors as messages, prompt text, and area conversion."""
import time

import numpy as np
import pytest

from anypoach.bridge.evidence import EvidenceStore
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


def make(tmp_path, backend=None, pointer=None, **kwargs):
    return Controller(backend or LiveBackend(), pointer, tmp_path / "work", cache=tmp_path / "cache", **kwargs)


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


def test_handoff_prompt_warns_about_several_interactions():
    sentence = ("A recording may hold several interactions: each segment in evidence.segments has its own timing, "
                "so never read one segment's timing as another's.")
    assert sentence in handoff_prompt("ID", None)


def test_denied_screen_recording_is_a_message_and_nothing_starts(tmp_path):
    controller = make(tmp_path, screen_access=lambda: False)
    controller.choose_region(Rect(10, 10, 160, 90))
    assert controller.check_screen_access() is False
    assert "Screen Recording" in controller.message and "System Settings" in controller.message
    controller.message = ""
    controller.start()
    assert controller.state == "idle" and "Screen Recording" in controller.message


@pytest.mark.parametrize("answer", [True, None])
def test_an_allowed_or_unknown_permission_does_not_block(tmp_path, answer):
    controller = make(tmp_path, screen_access=lambda: answer)
    controller.choose_region(Rect(10, 10, 160, 90))
    assert controller.check_screen_access() is True
    controller.start()
    assert controller.state == "recording"
    controller.stop()


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


def test_handoff_prompt_prefers_browser_evidence():
    prompt = handoff_prompt("ID", None)
    assert "evidence.browserEvidence" in prompt
    tail = prompt.split("evidence.browserEvidence")[1]
    assert "instead of measuring the video" in tail and "confirm" in tail
    assert "evidence.browserEvidence.components" in prompt


def test_device_scale_counts_video_pixels_when_the_recorder_downsizes(tmp_path):
    controller = make(tmp_path)
    controller.choose_region(Rect(0, 0, 2400, 1200), device_scale=2.0)  # 1200x600 CSS px, recorded at 1920 px wide
    controller.start()
    time.sleep(0.4)
    result = controller.stop()
    assert result.capture.width_px == 1920
    assert result.capture.device_scale == pytest.approx(1.6)  # video pixels per CSS pixel, not the screen's 2.0


def chrome_session(started, duration=1500):
    from tests.test_bridge_evidence import session
    return session(startedAtEpochMs=started, durationMs=duration)


def make_with_store(tmp_path, clock=time.time):
    store = EvidenceStore(clock)
    return Controller(LiveBackend(), None, tmp_path / "work", cache=tmp_path / "cache", store=store), store


def test_a_matching_chrome_session_is_attached_to_the_brief(tmp_path):
    controller, store = make_with_store(tmp_path)
    before = int(time.time() * 1000)
    record(controller)
    store.put(chrome_session(before - 200), final=True)
    controller.copy_handoff()
    attached = read_brief(cache=tmp_path / "cache")["evidence"]["browserEvidence"]
    assert -400 < attached["videoOffsetMs"] < -150 and attached["origin"] == "https://example.com"


def test_chrome_finishing_after_stop_still_attaches(tmp_path):
    controller, store = make_with_store(tmp_path)
    before = int(time.time() * 1000)
    record(controller)
    assert controller.browser_status == "waiting"
    store.put(chrome_session(before), final=True)
    assert controller.browser_status == "attached"
    controller.copy_handoff()
    assert "browserEvidence" in read_brief(cache=tmp_path / "cache")["evidence"]


def test_a_session_from_before_the_recording_is_not_attached(tmp_path):
    controller, store = make_with_store(tmp_path)
    store.put(chrome_session(int(time.time() * 1000) - 60_000), final=True)
    record(controller)
    controller.copy_handoff()
    assert "browserEvidence" not in read_brief(cache=tmp_path / "cache")["evidence"]


def test_a_stale_session_is_not_attached(tmp_path):
    now = [1000.0]
    controller, store = make_with_store(tmp_path, clock=lambda: now[0])
    before = int(time.time() * 1000)
    record(controller)
    store.put(chrome_session(before), final=True)
    now[0] += 181
    controller.copy_handoff()
    assert "browserEvidence" not in read_brief(cache=tmp_path / "cache")["evidence"]


def test_browser_status_follows_the_store(tmp_path):
    assert make(tmp_path).browser_status == "off"
    controller, store = make_with_store(tmp_path)
    assert controller.browser_status == "waiting"
    before = int(time.time() * 1000)
    controller.choose_region(Rect(10, 10, 160, 90))
    controller.start()
    store.put(chrome_session(before), final=False)
    assert controller.browser_status == "receiving"
    time.sleep(0.3)
    controller.stop()
    store.put(chrome_session(before), final=True)
    assert controller.browser_status == "attached"


def test_a_comment_is_stored_sorted_and_shared_in_the_brief(tmp_path):
    controller = make(tmp_path, pointer=Script(at(60, 50)))
    result = record(controller)
    assert result is not None
    assert controller.add_comment(300, "second") and controller.add_comment(100, "first")
    controller.context = "Ease it out."
    controller.copy_handoff()
    brief = read_brief(cache=tmp_path / "cache")
    assert brief["evidence"]["annotations"] == [{"timeMs": 100, "text": "first"}, {"timeMs": 300, "text": "second"}]
    assert brief["context"] == "Ease it out."


def test_empty_and_whitespace_comments_are_refused_with_a_message(tmp_path):
    controller = make(tmp_path)
    assert not controller.add_comment(0, "") and not controller.add_comment(0, "  \n\t ")
    assert "empty" in controller.message.lower() and controller.comments == []


def test_comment_length_is_limited_to_500_characters_after_stripping(tmp_path):
    controller = make(tmp_path)
    assert controller.add_comment(0, "a" * 500) and controller.add_comment(1, "  " + "b" * 500 + "  ")
    assert not controller.add_comment(2, "c" * 501) and "500" in controller.message
    assert [len(c["text"]) for c in controller.comments] == [500, 500]


def test_the_fifty_first_comment_is_refused(tmp_path):
    controller = make(tmp_path)
    assert all(controller.add_comment(i, f"note {i}") for i in range(50))
    assert not controller.add_comment(99, "one too many") and "50" in controller.message and len(controller.comments) == 50


def test_accents_and_emoji_survive_the_round_trip(tmp_path):
    controller = make(tmp_path, pointer=Script(at(60, 50)))
    record(controller)
    assert controller.add_comment(120, "Transição suave ✨ — não pule")
    controller.copy_handoff()
    assert read_brief(cache=tmp_path / "cache")["evidence"]["annotations"][0]["text"] == "Transição suave ✨ — não pule"


def test_removing_a_comment_by_index_and_an_out_of_range_index_is_ignored(tmp_path):
    controller = make(tmp_path)
    controller.add_comment(5, "keep")
    controller.add_comment(1, "drop")
    controller.remove_comment(0)
    controller.remove_comment(9)
    controller.remove_comment(-1)
    assert controller.comments == [{"timeMs": 5, "text": "keep"}]


def test_comments_is_a_copy(tmp_path):
    controller = make(tmp_path)
    controller.add_comment(5, "keep")
    controller.comments.clear()
    controller.comments[0:0] = [{"timeMs": 0, "text": "x"}]
    assert controller.comments == [{"timeMs": 5, "text": "keep"}]


def test_a_new_recording_clears_comments_but_keeps_the_instructions(tmp_path):
    controller = make(tmp_path)
    record(controller)
    controller.add_comment(100, "old")
    controller.context = "keep this"
    controller.choose_region(Rect(10, 10, 160, 90))
    controller.start()
    assert controller.comments == [] and controller.context == "keep this"
    controller.stop()


def test_a_refused_start_keeps_the_comments(tmp_path):
    controller = make(tmp_path)
    controller.add_comment(100, "stay")
    controller.start()  # no area chosen
    assert controller.comments == [{"timeMs": 100, "text": "stay"}]


def test_a_screenshot_of_the_chosen_area_becomes_an_image_brief(tmp_path):
    controller = make(tmp_path)
    assert controller.screenshot() is None and "area" in controller.message.lower()
    controller.choose_region(Rect(10, 10, 160, 90))
    result = controller.screenshot()
    assert result.media_type == "image" and (result.capture.width_px, result.capture.height_px) == (160, 90)
    assert controller.state == "ready" and controller.message == ""
    assert controller.copy_handoff() and read_brief(cache=tmp_path / "cache")["briefId"]


def test_a_denied_screenshot_is_a_message(tmp_path):
    controller = make(tmp_path, backend=LiveBackend(PermissionError("denied")))
    controller.choose_region(Rect(10, 10, 160, 90))
    assert controller.screenshot() is None and "permission" in controller.message


def test_importing_a_video_or_image_and_refusing_other_files(tmp_path):
    from tests.fixtures import build_multi
    video = build_multi(tmp_path, [(0.5, 0.6, 24)], "clip.mov")
    controller = make(tmp_path)
    assert controller.import_file(video).media_type == "video" and controller.state == "ready"
    controller.annotations = [{"timeMs": 1, "text": "old"}]
    shot = make(tmp_path)
    shot.choose_region(Rect(0, 0, 40, 40))
    image = shot.screenshot().source_path
    assert controller.import_file(image).media_type == "image" and controller.annotations == []
    notes = tmp_path / "notes.txt"
    notes.write_text("no")
    assert controller.import_file(notes) is None and "notes.txt" in controller.message


def test_nothing_is_imported_or_captured_while_recording(tmp_path):
    controller = make(tmp_path)
    controller.choose_region(Rect(10, 10, 160, 90))
    controller.start()
    try:
        assert controller.screenshot() is None and controller.import_file(tmp_path) is None
        assert "Stop" in controller.message
    finally:
        controller.stop()


def shot(tmp_path):
    controller = make(tmp_path)
    controller.choose_region(Rect(10, 10, 160, 90))
    controller.screenshot()
    return controller


def test_the_palette_edit_reaches_the_brief_and_reset_restores_the_analysis(tmp_path):
    controller = shot(tmp_path)
    analyzed = controller.palette
    assert analyzed and controller.set_palette(["#FF0000", "#ff0000", "#00ff00"])
    assert controller.palette == ["#ff0000", "#00ff00"]
    controller.copy_handoff()
    assert read_brief(cache=tmp_path / "cache")["evidence"]["palette"] == ["#ff0000", "#00ff00"]
    controller.reset_palette()
    assert controller.palette == analyzed


@pytest.mark.parametrize("colors", [[], ["red"], ["#12345"], ["#ff0000", 5]])
def test_a_bad_palette_is_refused_with_a_message_and_changes_nothing(tmp_path, colors):
    controller = shot(tmp_path)
    before = controller.palette
    assert controller.set_palette(colors) is False and controller.message and controller.palette == before


def test_the_palette_is_capped_at_twelve_and_cleared_by_a_new_result(tmp_path):
    controller = shot(tmp_path)
    assert controller.set_palette([f"#0000{i:02x}" for i in range(20)]) and len(controller.palette) == 12
    controller.screenshot()
    assert controller.palette != [f"#0000{i:02x}" for i in range(12)]
    assert make(tmp_path).set_palette(["#000000"]) is False
