"""Write the Chrome extension's 128x128 icon: a source logo with a penguin next to it.

    uv run python tools/make_extension_icon.py path/to/logo.png path/to/tux.png

Needs the `ffmpeg` CLI. The logo is cropped to its rounded tile; the penguin sits at the bottom right.
"""
import subprocess
import sys
from pathlib import Path

SIZE = 128
PENGUIN_HEIGHT = 70
TARGET = Path(__file__).resolve().parent.parent / "src/anypoach/chrome_extension/icon.png"


def compose(logo: str, penguin: str) -> None:
    """Scale the cropped logo and the penguin, lay the penguin over it, and write the PNG."""
    graph = (f"[0:v]crop=1090:1090:80:80,scale={SIZE}:{SIZE}:flags=lanczos[tile];"
             f"[1:v]scale=-1:{PENGUIN_HEIGHT}:flags=lanczos[tux];"
             f"[tile][tux]overlay=x=W-w-6:y=H-h-8:format=auto")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", logo, "-i", penguin, "-filter_complex", graph,
                    "-frames:v", "1", str(TARGET)], check=True)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    compose(sys.argv[1], sys.argv[2])
