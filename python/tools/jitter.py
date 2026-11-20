"""Measure the 120 Hz polling loop's timing with a synthetic source (the loop, not the OS call).

    uv run python tools/jitter.py [seconds]
"""
import statistics
import sys
import time

from poach.pointer.recorder import PointerTraceRecorder
from poach.pointer.trace import PointerSample, Rect

stamps: list[float] = []


class Source:
    def sample(self):
        stamps.append(time.perf_counter())
        return PointerSample(1, 1, frozenset())


seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 10
recorder = PointerTraceRecorder(Rect(0, 0, 100, 100), Source())
recorder.start()
time.sleep(seconds)
recorder.stop()
gaps = [(b - a) * 1000 for a, b in zip(stamps, stamps[1:], strict=False)]
expected = int(seconds * 120)
print(f"samples={len(stamps)} expected~{expected} lost={max(0, expected - len(stamps))} "
      f"gap_ms mean={statistics.mean(gaps):.2f} p99={sorted(gaps)[int(len(gaps) * 0.99)]:.2f} max={max(gaps):.2f}")
