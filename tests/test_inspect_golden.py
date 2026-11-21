"""Video and image analysis against the golden files, including the 30 s limit and recordings."""
import json
import math
import subprocess
from pathlib import Path

import av
import numpy as np
import pytest

from anypoach.analysis.inspect import (
    inspect_image,
    inspect_recording,
    inspect_video,
    read_drag_release_frames,
    read_video_moment,
)
from anypoach.analysis.source import VideoSource

GOLD = Path(__file__).parent / "golden"
PNG = bytes([137, 80, 78, 71, 13, 10, 26, 10])


def pixels(path):
    with av.open(str(path)) as c:
        return next(c.decode(video=0)).to_ndarray(format="rgb24").astype(float)


# The goldens come from the system ffmpeg's libswscale 9, while the PyAV wheels bundle their own
# libswscale, which differs by platform: chroma rounding moves a channel by up to +-2, and colors
# of near-equal weight can swap places. Palettes are therefore compared as dominant colors within
# that tolerance instead of byte for byte.
def close(a, b, tol=2):
    return all(abs(int(a[i:i + 2], 16) - int(b[i:i + 2], 16)) <= tol for i in (1, 3, 5))


def assert_palette(ours, gold):
    assert len(ours) == len(gold)
    assert all(any(close(g, o) for o in ours[:3]) for g in gold[:2]), (ours, gold)
    matched = sum(any(close(g, o) for o in ours) for g in gold)
    assert matched >= len(gold) - 2, (ours, gold)


def frame_at(path, seconds):
    with av.open(str(path)) as c:
        for f in c.decode(video=0):
            if f.time >= seconds - 1e-6:
                return f.to_ndarray(format="rgb24").astype(float)


def assert_matches_golden(result, name, lossy_source=None):
    gold = json.loads((GOLD / f"{name}.json").read_text(encoding="utf-8"))
    got = result.to_json()
    assert got["mediaType"] == gold["mediaType"] and got["durationMs"] == gold["durationMs"]
    assert_palette(got["palette"], gold["palette"])
    assert got["timing"] == gold["timing"]
    assert [(k["kind"], k["timeMs"]) for k in got["keyframes"]] == [(k["kind"], k["timeMs"]) for k in gold["keyframes"]]
    for ours, theirs in zip(got["keyframes"], gold["keyframes"], strict=True):
        assert ours["motion"] == pytest.approx(theirs["motion"], abs=1e-4, rel=0.05 if lossy_source else 0)
        got_px, gold_px = pixels(ours["imagePath"]), pixels(GOLD / theirs["imagePath"])
        if lossy_source is None:
            diff = np.abs(got_px - gold_px).mean()
            assert diff <= 1.0, f"{theirs['imagePath']} differs by {diff}"
        else:
            # A 30 s clip is re-encoded lossily by two different encoders; require our frame to be
            # no further from the original recording than the golden frame is (plus slack).
            original = frame_at(lossy_source, ours["timeMs"] / 1000)
            assert np.abs(got_px - original).mean() <= np.abs(gold_px - original).mean() + 0.5


@pytest.mark.parametrize("name", ["motion", "static", "sparse"])
def test_video_matches_golden(clips, tmp_path, name):
    assert_matches_golden(inspect_video(clips[name], output_dir=tmp_path), name)


def test_image_matches_golden(clips, tmp_path):
    assert_matches_golden(inspect_image(clips["image"], output_dir=tmp_path), "image")


def test_overrun_recording_matches_golden_and_is_clipped_to_30s(clips, tmp_path):
    result = inspect_recording(clips["overrun"], output_dir=tmp_path)
    assert_matches_golden(result, "overrun", lossy_source=clips["overrun"])
    assert Path(result.source_path) != clips["overrun"]
    with VideoSource(result.source_path) as clipped:
        assert clipped.duration_s == pytest.approx(30, abs=0.05)
        assert read_video_moment(result.source_path, 29_900)[:8] == PNG
        with pytest.raises(ValueError, match="before the end"):
            read_video_moment(result.source_path, 30_000)


def test_import_over_30_seconds_is_rejected(clips):
    with pytest.raises(ValueError, match="30-second limit"):
        inspect_video(clips["overrun"])


def test_unicode_name_is_sanitized_and_progress_is_ordered(clips, tmp_path):
    stages = []
    result = inspect_video(clips["unicode name"], output_dir=tmp_path, on_progress=stages.append)
    assert stages == ["motion", "frames", "palette"]
    assert all(Path(k.image_path).name.startswith("m-vimento-teste-") for k in result.keyframes)


def test_one_frame_video_has_only_a_start_keyframe(tmp_path):
    clip = tmp_path / "one.mov"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=96x64:rate=25",
                    "-frames:v", "1", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip)], check=True)
    result = inspect_video(clip, output_dir=tmp_path)
    assert [(k.kind, k.time_ms) for k in result.keyframes] == [("start", 0)]
    assert (result.duration_ms, result.timing.token) == (0, "No measurable motion in sampled frames")


def test_moment_rejects_bad_timestamps(clips):
    with pytest.raises(ValueError, match="nonnegative"):
        read_video_moment(clips["motion"], -1)
    with pytest.raises(ValueError, match="nonnegative"):
        read_video_moment(clips["motion"], math.nan)


def test_drag_release_frames_stop_before_the_next_drag(clips):
    full = read_drag_release_frames(clips["motion"], 1000, None)
    assert full.end_time_ms == 1999
    assert [f.time_ms for f in full.frames] == [920, 1150, 1800, 1999]
    cut = read_drag_release_frames(clips["motion"], 1000, 1500)
    assert [f.time_ms for f in cut.frames] == [920, 1150, 1499]
    assert read_drag_release_frames(clips["motion"], 1999.5, None).frames == []
    assert all(f.png[:8] == PNG for f in full.frames)


def png_size(path):
    data = Path(path).read_bytes()
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")


def test_video_result_carries_the_native_size(clips, tmp_path):
    result = inspect_video(clips["wide"], output_dir=tmp_path)
    assert result.to_json()["capture"] == {"widthPx": 1600, "heightPx": 900, "deviceScale": None, "imageMaxSize": 1280}
    assert png_size(result.keyframes[0].image_path) == (1280, 720)


def test_image_result_carries_the_native_size(clips, tmp_path):
    result = inspect_image(clips["image"], output_dir=tmp_path)
    assert result.to_json()["capture"] == {"widthPx": 160, "heightPx": 90, "deviceScale": None, "imageMaxSize": 1280}


def test_small_video_is_not_reduced(clips, tmp_path):
    result = inspect_video(clips["motion"], output_dir=tmp_path)
    assert (result.capture.width_px, result.capture.height_px) == (160, 90)
    assert png_size(result.keyframes[0].image_path) == (160, 90)
