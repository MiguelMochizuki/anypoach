"""PipeWire frame reader: the GStreamer command line, frame framing, stream end, and cleanup."""
import shutil
import sys
import time

import pytest

from anypoach.capture.pipewire import PipeWireStream, gst_command


def producer(frames, *, pause=0.0, partial=False, sleep_forever=False):
    """A command that writes `frames` 4x2 BGRA frames, frame n filled with the byte n."""
    script = (
        "import sys, time\n"
        f"for n in range({frames}):\n"
        "    sys.stdout.buffer.write(bytes([n]) * 32); sys.stdout.buffer.flush()\n"
        f"    time.sleep({pause})\n"
        f"if {partial}: sys.stdout.buffer.write(b'x' * 16); sys.stdout.buffer.flush()\n"
        f"if {sleep_forever}: time.sleep(60)\n")
    return [sys.executable, "-c", script]


def test_gst_command_pins_the_pipeline():
    assert gst_command(7, 57, (1920, 1080)) == [
        "gst-launch-1.0", "-q", "pipewiresrc", "fd=7", "path=57", "always-copy=true", "!",
        "videoconvert", "!", "videoscale", "!", "video/x-raw,format=BGRA,width=1920,height=1080", "!",
        "fdsink", "fd=1", "sync=false"]


def test_latest_returns_the_newest_complete_frame():
    stream = PipeWireStream(producer(frames=5, pause=0.05, sleep_forever=True), (4, 2))
    stream.start()
    try:
        assert stream.wait_first_frame().pixels.shape == (2, 4, 4)
        deadline = time.monotonic() + 5
        while stream.latest().pixels[0, 0, 0] != 4 and time.monotonic() < deadline:
            time.sleep(0.05)  # a loaded CI runner can deliver the last frame late
        assert stream.latest().pixels[0, 0, 0] == 4
    finally:
        stream.close()


def test_a_half_written_frame_is_never_returned():
    stream = PipeWireStream(producer(frames=0, partial=True), (4, 2))
    stream.start()
    with pytest.raises(OSError):
        stream.wait_first_frame(timeout_s=1)
    stream.close()


def test_the_first_frame_wait_times_out():
    stream = PipeWireStream(producer(frames=0, sleep_forever=True), (4, 2))
    stream.start()
    with pytest.raises(OSError, match="timed out"):
        stream.wait_first_frame(timeout_s=0.3)
    stream.close()


def test_latest_after_the_process_ended_raises():
    stream = PipeWireStream(producer(frames=1), (4, 2))
    stream.start()
    stream.wait_first_frame()
    time.sleep(0.4)
    assert stream.ended
    with pytest.raises(OSError, match="stopped"):
        stream.latest()
    stream.close()


def test_close_kills_the_process():
    stream = PipeWireStream(producer(frames=0, sleep_forever=True), (4, 2))
    stream.start()
    process = stream._process
    stream.close()
    stream.close()
    assert process.poll() is not None


@pytest.mark.skipif(shutil.which("gst-launch-1.0") is None, reason="GStreamer not installed")
def test_a_real_gstreamer_pipeline_delivers_bgra_frames():
    command = ["gst-launch-1.0", "-q", "videotestsrc", "num-buffers=10", "!", "videoconvert", "!", "videoscale", "!",
               "video/x-raw,format=BGRA,width=64,height=48", "!", "fdsink", "fd=1", "sync=false"]
    stream = PipeWireStream(command, (64, 48))
    stream.start()
    try:
        assert stream.wait_first_frame().pixels.shape == (48, 64, 4)
    finally:
        stream.close()
