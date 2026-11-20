"""Synthetic clips shared by the golden generator and the Python tests (ffmpeg is a test tool only)."""
import shutil
import subprocess
from pathlib import Path

EASE = "(160-24)*(1-pow(1-min(t/0.6\\,1)\\,3))"


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def build_all(directory: Path) -> dict[str, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    clips = {name: directory / f for name, f in {
        "motion": "motion.mov", "static": "static.mov", "sparse": "sparse.mov",
        "overrun": "overrun.mov", "image": "image.png"}.items()}
    # An orange box eases out cubically across 0.6 s, then rests until 2 s.
    _ffmpeg("-f", "lavfi", "-i", "color=black:s=160x90:r=30:d=2", "-f", "lavfi", "-i", "color=orange:s=24x24:r=30:d=2",
            "-filter_complex", f"[0][1]overlay=x='{EASE}':y=33", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clips["motion"]))
    _ffmpeg("-f", "lavfi", "-i", "color=black:size=96x64:rate=12", "-t", "1", "-c:v", "libx264", str(clips["static"]))
    _ffmpeg("-f", "lavfi", "-i", "testsrc2=size=96x64:rate=1/2", "-frames:v", "3", "-c:v", "libx264", str(clips["sparse"]))
    _ffmpeg("-f", "lavfi", "-i", "testsrc2=size=96x64:rate=30", "-t", "31.5", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clips["overrun"]))
    _ffmpeg("-f", "lavfi", "-i", "testsrc2=size=160x90:rate=1", "-frames:v", "1", str(clips["image"]))
    unicode_clip = directory / "mövimento teste.mov"
    shutil.copyfile(clips["motion"], unicode_clip)
    clips["unicode name"] = unicode_clip
    return clips
