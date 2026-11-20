"""Time the Python analysis on the fixture clips (compare with docs/superpowers/baseline.md).

    uv run python tools/bench.py /path/to/fixtures
"""
import resource
import sys
import tempfile
import time
from pathlib import Path

from poach.analysis.inspect import inspect_recording, inspect_video

fixtures = Path(sys.argv[1])
for name, fn in (("motion.mov", inspect_video), ("overrun.mov", inspect_recording)):
    start = time.perf_counter()
    fn(fixtures / name, output_dir=tempfile.mkdtemp())
    cpu = resource.getrusage(resource.RUSAGE_SELF)
    print(f"{name}: wall={time.perf_counter() - start:.2f}s cpu={cpu.ru_utime + cpu.ru_stime:.2f}s "
          f"peak_rss={cpu.ru_maxrss // 1024}MB (cumulative for this process)")
