"""Motion segments in the analysis result, on synthetic multi-interaction clips."""
from pathlib import Path

import pytest

from anypoach.analysis.inspect import inspect_image, inspect_video
from tests.fixtures import build_multi


@pytest.fixture(scope="module")
def made(tmp_path_factory):
    directory = tmp_path_factory.mktemp("multi")
    return {
        "one": build_multi(directory, [(0.5, 0.6, 24)], "one.mov"),
        "clean": build_multi(directory, [(0.5, 0.6, 24), (1.8, 0.3, 1)], "clean.mov"),  # same length as `residual`
        "residual": build_multi(directory, [(0.5, 0.6, 24), (1.8, 0.3, 5)], "residual.mov"),
        "three": build_multi(directory, [(0.5, 0.6, 24), (2.5, 0.6, 24), (4.5, 0.6, 24)], "three.mov"),
        "small_after_big": build_multi(directory, [(0.5, 0.6, 40), (4.0, 0.4, 16)], "small.mov"),
        "many": build_multi(directory, [(0.3 + k, 0.4, 14 + 2 * k) for k in range(14)], "many.mov"),
    }


def top(result):
    return [(k.kind, k.time_ms) for k in result.keyframes], result.timing


def test_a_clip_with_one_interaction_has_one_segment_sharing_the_top_level(made, tmp_path):
    result = inspect_video(made["one"], output_dir=tmp_path)
    assert len(result.segments) == 1
    assert [k.image_path for k in result.segments[0].keyframes] == [k.image_path for k in result.keyframes]
    assert result.segments[0].timing == result.timing


def test_three_bursts_make_three_segments_in_time_order(made, tmp_path):
    segments = inspect_video(made["three"], output_dir=tmp_path).segments
    assert len(segments) == 3
    assert [s.start_ms for s in segments] == sorted(s.start_ms for s in segments)
    assert all(abs(s.start_ms - expected) < 400 for s, expected in zip(segments, (500, 2500, 4500), strict=True))
    assert all(s.start_ms <= s.peak_ms <= s.end_ms for s in segments)


def test_a_small_burst_after_a_big_one_is_its_own_segment_with_its_own_timing(made, tmp_path):
    result = inspect_video(made["small_after_big"], output_dir=tmp_path)
    big, small = result.segments
    assert big.strength > small.strength > 0 and small.start_ms > 3500
    assert small.keyframes and small.timing.duration_ms > 0


def test_the_top_level_is_the_strongest_segment_and_shares_its_files(made, tmp_path):
    result = inspect_video(made["small_after_big"], output_dir=tmp_path)
    strongest = max(result.segments, key=lambda s: s.strength)
    assert strongest.keyframes == result.keyframes and strongest.timing == result.timing


def test_more_than_twelve_bursts_keep_the_twelve_strongest_and_images_for_four(made, tmp_path):
    segments = inspect_video(made["many"], output_dir=tmp_path).segments
    assert len(segments) == 12
    with_images = sorted(segments, key=lambda s: s.strength, reverse=True)[:4]
    assert all(s.keyframes for s in with_images) and not any(s.keyframes for s in segments if s not in with_images)
    assert all(Path(k.image_path).is_file() for s in with_images for k in s.keyframes)


def test_residual_motion_does_not_change_the_top_level(made, tmp_path):
    clean = inspect_video(made["clean"], output_dir=tmp_path / "a")
    noisy = inspect_video(made["residual"], output_dir=tmp_path / "b")
    assert top(noisy) == top(clean)
    assert len(noisy.segments) >= 1


def test_a_static_clip_has_no_segments_and_a_start_keyframe(clips, tmp_path):
    result = inspect_video(clips["static"], output_dir=tmp_path)
    assert result.segments == [] and [k.kind for k in result.keyframes] == ["start"]
    assert result.to_json()["segments"] == []


def test_an_image_has_no_segments(clips, tmp_path):
    result = inspect_image(clips["image"], output_dir=tmp_path)
    assert result.segments is None and "segments" not in result.to_json()


def test_segment_json_has_the_camel_case_shape(made, tmp_path):
    data = inspect_video(made["one"], output_dir=tmp_path).to_json()["segments"][0]
    assert set(data) == {"startMs", "peakMs", "endMs", "strength", "timing", "keyframes"}
    assert set(data["timing"]) == {"durationMs", "bezier", "token"}
