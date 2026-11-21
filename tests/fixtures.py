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
        "overrun": "overrun.mov", "image": "image.png", "wide": "wide.mov"}.items()}
    # An orange box eases out cubically across 0.6 s, then rests until 2 s.
    _ffmpeg("-f", "lavfi", "-i", "color=black:s=160x90:r=30:d=2", "-f", "lavfi", "-i", "color=orange:s=24x24:r=30:d=2",
            "-filter_complex", f"[0][1]overlay=x='{EASE}':y=33", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clips["motion"]))
    _ffmpeg("-f", "lavfi", "-i", "color=black:size=96x64:rate=12", "-t", "1", "-c:v", "libx264", str(clips["static"]))
    _ffmpeg("-f", "lavfi", "-i", "testsrc2=size=96x64:rate=1/2", "-frames:v", "3", "-c:v", "libx264", str(clips["sparse"]))
    _ffmpeg("-f", "lavfi", "-i", "testsrc2=size=96x64:rate=30", "-t", "31.5", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clips["overrun"]))
    _ffmpeg("-f", "lavfi", "-i", "testsrc2=size=160x90:rate=1", "-frames:v", "1", str(clips["image"]))
    _ffmpeg("-f", "lavfi", "-i", "testsrc2=size=1600x900:rate=10", "-t", "1", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clips["wide"]))
    unicode_clip = directory / "mövimento teste.mov"
    shutil.copyfile(clips["motion"], unicode_clip)
    clips["unicode name"] = unicode_clip
    return clips


def build_multi(directory: Path, bursts: list[tuple[float, float, int]], name: str = "multi.mov") -> Path:
    """A 160x90, 30 fps black clip where each `(start_s, duration_s, box_px)` burst slides an orange box across.

    A box waits off screen, then eases out cubically across its window, like the `motion` clip, and stays where it
    lands. The clip ends one second after the last burst.
    """
    if any(size < 2 or size % 2 for _, _, size in bursts):
        raise ValueError("Box sizes must be even and at least 2: older ffmpeg rejects a 1-pixel yuv420p input")
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / name
    end = max(start + length for start, length, _ in bursts) + 1.0
    inputs, graph, last = ["-f", "lavfi", "-i", f"color=black:s=160x90:r=30:d={end}"], [], "0"
    for k, (start, length, size) in enumerate(bursts, 1):
        inputs += ["-f", "lavfi", "-i", f"color=orange:s={size}x{size}:r=30:d={end}"]
        ease = f"if(lt(t\\,{start})\\,-200\\,(160-{size})*(1-pow(1-min((t-{start})/{length}\\,1)\\,3)))"
        row = 4 + ((k - 1) % 3) * 28
        graph.append(f"[{last}][{k}]overlay=x='{ease}':y={row}[v{k}]")
        last = f"v{k}"
    _ffmpeg(*inputs, "-filter_complex", ";".join(graph), "-map", f"[{last}]", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(target))
    return target
