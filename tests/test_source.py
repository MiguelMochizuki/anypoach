"""Video decoding by presentation time: seeking, held frames, and PNG output."""
import numpy as np
import pytest

from anypoach.analysis.source import VideoSource, seek_for_moment

PNG = bytes([137, 80, 78, 71, 13, 10, 26, 10])


def test_seek_for_moment_aims_between_the_shown_frame_and_its_predecessor():
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


def test_size_is_the_native_frame_size(clips):
    with VideoSource(clips["wide"]) as source:
        assert source.size == (1600, 900)


def native_rgb(source, seek):
    return source._collect([seek], lambda frame: frame.to_ndarray(format="rgb24"))[0]


def decode_png(data):
    import io

    import av
    with av.open(io.BytesIO(data)) as container:
        return next(container.decode(video=0)).to_ndarray(format="rgb24")


def test_png_at_crops_native_pixels_before_reducing(clips):
    with VideoSource(clips["wide"]) as source:
        seek = source.seek_for_moment(0)
        cropped = decode_png(source.png_at(seek, crop=(100, 50, 400, 300)))
        assert cropped.shape == (300, 400, 3)
        assert np.abs(cropped.astype(int) - native_rgb(source, seek)[50:350, 100:500].astype(int)).max() <= 1


def test_png_at_reduces_a_crop_that_exceeds_max_size(clips):
    with VideoSource(clips["wide"]) as source:
        shape = decode_png(source.png_at(source.seek_for_moment(0), max_size=500, crop=(0, 0, 1000, 800))).shape
        assert max(shape[:2]) == 500 and shape[:2] == (400, 500)


@pytest.mark.parametrize("crop", [(1500, 0, 200, 100), (0, 0, 0, 10), (-1, 0, 10, 10), (0, 850, 10, 100)])
def test_png_at_rejects_a_crop_outside_the_frame(clips, crop):
    with VideoSource(clips["wide"]) as source, pytest.raises(ValueError, match="Crop must fit inside the 1600x900 frame"):
        source.png_at(source.seek_for_moment(0), crop=crop)
