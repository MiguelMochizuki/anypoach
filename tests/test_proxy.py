"""The editor's frame proxy: small JPEG frames with real presentation times, decoded once in the background."""
import threading

import av
import numpy as np
import pytest

from anypoach.analysis.inspect import read_video_moment
from anypoach.analysis.proxy import FrameProxy, ProxyFrame, build_proxy


def decode_jpeg(data: bytes) -> np.ndarray:
    context = av.CodecContext.create("mjpeg", "r")
    return context.decode(av.Packet(data))[0].to_ndarray(format="rgb24")


def decode_png(data: bytes) -> np.ndarray:
    context = av.CodecContext.create("png", "r")
    return context.decode(av.Packet(data))[0].to_ndarray(format="rgb24")


def test_frames_arrive_in_time_order_at_the_requested_rate(clips):
    proxy = build_proxy(clips["motion"], cancel=threading.Event())
    times = [f.time_ms for f in proxy.frames]
    assert proxy.done and times[0] == 0 and times == sorted(set(times))
    assert len(times) == 30 and times[1] == round(1000 / 15) and proxy.duration_ms == pytest.approx(2000, abs=50)


def test_every_frame_is_a_jpeg_within_the_size_limit(clips):
    small = build_proxy(clips["motion"], cancel=threading.Event()).frames[0]
    assert decode_jpeg(small.jpeg).shape[:2] == (90, 160)  # never enlarged
    wide = build_proxy(clips["wide"], cancel=threading.Event()).frames[0]
    assert max(decode_jpeg(wide.jpeg).shape[:2]) == 640


def test_nearest_and_step():
    proxy = FrameProxy(1000)
    for t in (0, 67, 133, 200):
        proxy.add(ProxyFrame(t, b"x"))
    assert proxy.nearest(60).time_ms == 67 and proxy.nearest(100).time_ms == 67  # ties go to the earlier frame
    assert proxy.nearest(10_000).time_ms == 200 and FrameProxy(0).nearest(5) is None
    assert proxy.step(67, 1).time_ms == 133 and proxy.step(67, -1).time_ms == 0
    assert proxy.step(0, -1) is None and proxy.step(200, 1) is None


def test_a_set_cancel_stops_early_and_leaves_done_false(clips):
    cancel, seen = threading.Event(), []

    def on_frame(frame):
        seen.append(frame)
        if len(seen) == 3:
            cancel.set()

    proxy = build_proxy(clips["motion"], cancel=cancel, on_frame=on_frame)
    assert not proxy.done and len(proxy.frames) == 3


def test_on_frame_is_called_once_per_frame_in_order(clips):
    seen = []
    proxy = build_proxy(clips["motion"], cancel=threading.Event(), on_frame=seen.append)
    assert seen == proxy.frames


def test_a_proxy_time_resolves_to_the_same_frame_as_read_moment(clips):
    proxy = build_proxy(clips["motion"], cancel=threading.Event())
    frame = proxy.frames[12]
    shown = decode_jpeg(frame.jpeg).astype(float)
    reference = decode_png(read_video_moment(clips["motion"], frame.time_ms)).astype(float)
    assert shown.shape == reference.shape and np.abs(shown - reference).mean() < 6


def test_an_unreadable_file_is_a_value_error(tmp_path):
    (tmp_path / "bad.mov").write_bytes(b"not a video")
    with pytest.raises(ValueError):
        build_proxy(tmp_path / "bad.mov", cancel=threading.Event())
