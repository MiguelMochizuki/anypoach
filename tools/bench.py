"""Time the Python analysis on the fixture clips (compare with docs/superpowers/baseline.md).

    uv run python tools/bench.py /path/to/fixtures [clip.mov ...]

Without clip names it times `motion.mov` and `overrun.mov`; with names it times each one as a recording.
"""
import resource
import sys
import tempfile
import time
from pathlib import Path

from anypoach.analysis.inspect import inspect_recording, inspect_video

fixtures = Path(sys.argv[1])
cases = [(name, inspect_recording) for name in sys.argv[2:]] or [("motion.mov", inspect_video), ("overrun.mov", inspect_recording)]
for name, fn in cases:
    start = time.perf_counter()
    fn(fixtures / name, output_dir=tempfile.mkdtemp())
    cpu = resource.getrusage(resource.RUSAGE_SELF)
    print(f"{name}: wall={time.perf_counter() - start:.2f}s cpu={cpu.ru_utime + cpu.ru_stime:.2f}s "
          f"peak_rss={cpu.ru_maxrss // 1024}MB (cumulative for this process)")
