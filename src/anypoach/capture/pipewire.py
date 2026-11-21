"""Reads raw video frames from a PipeWire stream through a `gst-launch-1.0` subprocess."""
from __future__ import annotations

import subprocess
import threading
import time
from collections.abc import Callable, Sequence

import numpy as np

from .backend import Frame


def gst_command(fd: int, node_id: int, size: tuple[int, int]) -> list[str]:
    """Build the `gst-launch-1.0` command that writes BGRA frames of exactly `size` to stdout.

    Args:
        fd: File descriptor of the PipeWire connection; it must be passed to the child process.
        node_id: PipeWire node of the stream.
        size: Width and height of every frame written.
    """
    width, height = size
    return ["gst-launch-1.0", "-q", "pipewiresrc", f"fd={fd}", f"path={node_id}", "always-copy=true", "!",
            "videoconvert", "!", "videoscale", "!", f"video/x-raw,format=BGRA,width={width},height={height}", "!",
            "fdsink", "fd=1", "sync=false"]


class PipeWireStream:
    """Runs a command that writes fixed-size BGRA frames to stdout and keeps the newest complete one.

    Args:
        command: Program and arguments; see `gst_command`.
        size: Width and height of every frame the command writes.
        pass_fds: File descriptors the child process inherits.
        clock: Monotonic clock stamped on every frame.
    """
    def __init__(self, command: Sequence[str], size: tuple[int, int], *, pass_fds: Sequence[int] = (),
                 clock: Callable[[], float] = time.perf_counter) -> None:
        self._command, self._size, self._pass_fds, self._clock = list(command), size, tuple(pass_fds), clock
        self._process: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None
        self._frame: Frame | None = None
        self._lock = threading.Lock()
        self._first = threading.Event()
        self._ended = threading.Event()

    @property
    def ended(self) -> bool:
        """Whether the stream stopped delivering frames."""
        return self._ended.is_set()

    def start(self) -> None:
        """Launch the command and begin reading frames on a background thread."""
        self._process = subprocess.Popen(self._command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                         pass_fds=self._pass_fds)
        self._thread = threading.Thread(target=self._read, args=(self._process.stdout,), name="anypoach-pipewire",
                                        daemon=True)
        self._thread.start()

    def _read(self, stdout) -> None:
        width, height = self._size
        length = width * height * 4
        while True:
            data = stdout.read(length)
            if len(data) < length:  # end of stream, possibly in the middle of a frame
                break
            frame = Frame(np.frombuffer(data, np.uint8).reshape(height, width, 4), self._clock())
            with self._lock:
                self._frame = frame
            self._first.set()
        self._ended.set()
        self._first.set()

    def wait_first_frame(self, timeout_s: float = 5.0) -> Frame:
        """Wait for the first complete frame.

        Raises:
            OSError: If it takes longer than `timeout_s` or the stream ends first.
        """
        if not self._first.wait(timeout_s):
            raise OSError("Waiting for the first screen frame timed out.")
        with self._lock:
            frame = self._frame
        if frame is None:
            raise OSError("The screen sharing stopped before the first frame.")
        return frame

    def latest(self) -> Frame:
        """Return the newest complete frame.

        Raises:
            OSError: If the stream ended or nothing has arrived yet.
        """
        if self.ended:
            raise OSError("The screen sharing stopped.")
        with self._lock:
            frame = self._frame
        if frame is None:
            raise OSError("No screen frame has arrived yet.")
        return frame

    def close(self) -> None:
        """Stop the process and the reader. Safe to call more than once."""
        process, self._process = self._process, None
        if process is None:
            return
        process.terminate()
        try:
            process.wait(1)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        if self._thread is not None:
            self._thread.join(1)
        if process.stdout is not None:
            process.stdout.close()
        self._ended.set()
