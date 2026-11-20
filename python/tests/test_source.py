import numpy as np
import pytest

from anypoach.analysis.source import VideoSource, seek_for_moment

PNG = bytes([137, 80, 78, 71, 13, 10, 26, 10])


def test_seek_for_moment_matches_ts():
    times = [0.0, 1.0, 2.0, 3.0]
    assert seek_for_moment(times, 0.5) == 0          # fewer than two frames shown so far
    assert seek_for_moment(times, 1.5) == 0.5        # midpoint of the last two PTS <= t
    assert seek_for_moment(times, 2.0) == 1.5
    assert seek_for_moment(times, 10.0) == 2.5


def test_moment_between_sparse_frames_returns_held_frame(clips):
    with VideoSource(clips["sparse"]) as source:
        at = lambda ms: source.png_at(source.seek_for_moment(ms / 1000))
        first = at(0)
        assert first[:8] == PNG
        assert at(1999) == first
        assert at(2000) != first
        assert at(5999) == at(4000)


def test_frames_at_reads_rgb_in_one_pass(clips):
    with VideoSource(clips["motion"]) as source:
        frames = source.frames_at([0.0, 1.0], 96)
    assert [f.shape for f in frames] == [(54, 96, 3)] * 2
    assert frames[0].dtype == np.uint8


def test_presentation_times_are_sorted_unique_and_start_at_zero(clips):
    with VideoSource(clips["sparse"]) as source:
        times = source.presentation_times
    assert times == sorted(set(times)) and times[0] == 0 and len(times) == 3


def test_source_closes_and_rejects_bad_input(clips, tmp_path):
    with VideoSource(clips["static"]) as source:
        assert source.duration_s > 0
    assert source.closed
    (tmp_path / "x.txt").write_text("x")
    with pytest.raises(ValueError, match="mp4 and .mov"):
        VideoSource(tmp_path / "x.txt")
    with pytest.raises(ValueError, match="file"):
        VideoSource(tmp_path / "missing.mov")
