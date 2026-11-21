"""Browser evidence from the Chrome companion: validation, alignment with a recording, and storage."""
import json

import pytest

from anypoach.bridge.evidence import EvidenceStore, align, parse_evidence

START = 1_700_000_000_000
TARGET = {"tag": "button", "role": "", "classes": "btn"}


def session(**overrides):
    base = {"version": 1, "origin": "https://example.com", "target": TARGET, "startedAtEpochMs": START, "durationMs": 1500,
            "events": [{"atMs": 100, "type": "pointerdown", "target": TARGET, "point": [10, 12], "insideTarget": True}],
            "states": [{"atMs": 0, "rect": [0, 0, 100, 40], "styles": {"width": "100px"}, "text": "Go", "indicators": []}],
            "animations": [], "targetRemoved": False}
    return {**base, **overrides}


def state(at=0):
    return {"atMs": at, "rect": [0, 0, 100, 40], "styles": {}, "text": "", "indicators": []}


def animation(keyframes=0, at=0):
    return {"atMs": at, "target": TARGET, "durationMs": 300, "delayMs": 0, "easing": "ease",
            "keyframes": [{"offset": 0, "easing": "ease", "styles": {}}] * keyframes}


def test_a_valid_session_round_trips_and_drops_a_stored_offset():
    assert parse_evidence(json.dumps(session(videoOffsetMs=5))) == session()


def test_extra_page_numbers_are_kept_when_well_typed_and_ignored_otherwise():
    kept = parse_evidence(session(devicePixelRatio=2, viewport={"width": 1280, "height": 720}))
    assert kept["devicePixelRatio"] == 2 and kept["viewport"] == {"width": 1280, "height": 720}
    ignored = parse_evidence(session(devicePixelRatio="two", viewport="big"))
    assert "devicePixelRatio" not in ignored and "viewport" not in ignored


@pytest.mark.parametrize("bad", [
    session(version=2), session(durationMs=90_001), session(durationMs=-1),
    session(origin="https://example.com/path"), session(origin="https://example.com/"), session(origin="ftp://example.com"),
    session(origin="https://user@example.com"), session(origin="https://example.com?q=1"), session(origin="https://example.com#x"),
    session(origin="example.com"), session(startedAtEpochMs=0), session(startedAtEpochMs=10_000_000_000_000),
    session(events=[session()["events"][0]] * 97), session(states=[]), session(states=[state()] * 49),
    session(animations=[animation()] * 17), session(animations=[animation(keyframes=9)]),
    session(states=[{**state(), "rect": [0, 0, 1]}]),
    session(states=[{**state(), "indicators": [{"target": TARGET, "rect": [0, 0, 1, 1], "value": "1"}] * 5}]),
    session(events=[{**session()["events"][0], "point": [1, 2, 3]}]),
    session(events=[{**session()["events"][0], "atMs": 1501}]), session(states=[state(at=1501)]),
    session(animations=[animation(at=1501)]),
])
def test_invalid_sessions_are_refused(bad):
    with pytest.raises(ValueError):
        parse_evidence(bad)


def test_oversized_and_non_json_input_is_refused():
    with pytest.raises(ValueError):
        parse_evidence(b" " * (256 * 1024 + 1))
    with pytest.raises(ValueError):
        parse_evidence("not json")
    with pytest.raises(ValueError):
        parse_evidence("[1, 2]")


def test_align_sets_the_video_offset_when_the_ranges_overlap():
    assert align(session(), (START - 400, START + 3000))["videoOffsetMs"] == 400
    assert align(session(), (START + 1000, START + 5000))["videoOffsetMs"] == -1000
    assert align(session(), (START - 5000, START - 1)) is None
    assert align(session(), (START + 1501, START + 6000)) is None


def test_align_keeps_only_what_touches_the_recording_and_the_state_it_started_from():
    long = session(durationMs=30_000,
                   events=[{"atMs": t, "type": "pointerdown", "target": TARGET} for t in (500, 9_000, 10_500, 12_000, 20_000)],
                   states=[state(0), state(4_000), state(9_500), state(10_200), state(15_000)],
                   animations=[animation(at=2_000), animation(at=9_800), animation(at=10_700), animation(at=25_000)])
    kept = align(long, (START + 10_000, START + 11_000))  # the recording is 10 s into the session, 1 s long
    assert kept["videoOffsetMs"] == -10_000
    assert [e["atMs"] for e in kept["events"]] == [9_000, 10_500, 12_000]  # within 1 s either side
    assert [a["atMs"] for a in kept["animations"]] == [9_800, 10_700]  # 2_000 ended long before, 25_000 starts after
    assert [t["atMs"] for t in kept["states"]] == [9_500, 10_200]  # the one in force at the start, and what changed
    assert long["states"][0]["atMs"] == 0 and len(long["events"]) == 5, "the stored session is not modified"


def test_align_keeps_the_last_state_before_the_recording_even_when_nothing_changed_in_it():
    kept = align(session(durationMs=80_000, states=[state(0)], events=[]), (START + 60_000, START + 62_000))
    assert [s["atMs"] for s in kept["states"]] == [0]


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_store_keeps_final_sessions_for_180_seconds():
    clock = Clock()
    store = EvidenceStore(clock)
    store.put(session(), final=True)
    clock.now += 179
    assert store.latest_for((START, START + 1000)) is not None
    clock.now += 2
    assert store.latest_for((START, START + 1000)) is None


def test_store_reports_a_partial_session_only_while_fresh():
    clock = Clock()
    store = EvidenceStore(clock)
    store.put(session(), final=False)
    assert store.receiving_for((START, START + 1000)) and store.latest_for((START, START + 1000)) is None
    clock.now += 11
    assert not store.receiving_for((START, START + 1000))


def test_a_newer_final_replaces_the_older_one_and_clear_forgets_it():
    store = EvidenceStore(Clock())
    store.put(session(durationMs=1000), final=True)
    store.put(session(durationMs=1200), final=True)
    assert store.latest_for((START, START + 10))["durationMs"] == 1200
    store.clear()
    assert store.latest_for((START, START + 10)) is None


def test_a_session_from_another_time_does_not_match():
    store = EvidenceStore(Clock())
    store.put(session(), final=True)
    assert store.latest_for((START + 60_000, START + 70_000)) is None
