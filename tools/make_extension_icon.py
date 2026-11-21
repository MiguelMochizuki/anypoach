"""Write the Chrome extension's 128x128 icon: a source logo turned upside down, with a penguin next to it.

    uv run python tools/make_extension_icon.py path/to/logo.png

Needs the `ffmpeg` CLI to crop, flip and scale the logo. The penguin is drawn here from plain shapes.
"""
import struct
import subprocess
import sys
import zlib
from pathlib import Path

SIZE = 128
SAMPLES = 3
TARGET = Path(__file__).resolve().parent.parent / "src/anypoach/chrome_extension/icon.png"


def logo_pixels(source: str) -> list[list[tuple[int, int, int, int]]]:
    """The logo's rounded tile, flipped vertically and scaled to the icon size, as rows of RGBA tuples."""
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", source, "-vf", f"crop=1090:1090:80:80,vflip,scale={SIZE}:{SIZE}:flags=area",
         "-f", "rawvideo", "-pix_fmt", "rgba", "-"], check=True, capture_output=True).stdout
    return [[tuple(raw[(y * SIZE + x) * 4:(y * SIZE + x) * 4 + 4]) for x in range(SIZE)] for y in range(SIZE)]


def inside(x: float, y: float, cx: float, cy: float, rx: float, ry: float) -> bool:
    """Whether the point is inside the ellipse."""
    return ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 <= 1


def penguin(x: float, y: float) -> tuple[int, int, int] | None:
    """Colour of the penguin at a point of the icon, or None outside it (about 46 px wide, bottom right)."""
    x, y = (x - 78) * 1.0, (y - 62) * 1.0
    if inside(x, y, 10, 55, 8, 3.4) or inside(x, y, 36, 55, 8, 3.4):
        return 255, 168, 0
    if inside(x, y, 20, 14, 5.5, 2.6) and y > 13:
        return 255, 168, 0
    if inside(x, y, 14.5, 11, 3.3, 3.8) or inside(x, y, 25.5, 11, 3.3, 3.8):
        return (20, 20, 20) if inside(x, y, 15, 11.5, 1.4, 1.8) or inside(x, y, 25, 11.5, 1.4, 1.8) else (255, 255, 255)
    if inside(x, y, 23, 38, 12, 17):
        return 250, 250, 250
    if inside(x, y, 23, 33, 18, 24) or inside(x, y, 23, 12, 12, 12) or inside(x, y, 4, 36, 4.5, 14) or inside(x, y, 42, 36, 4.5, 14):
        return 24, 24, 28
    return None


def compose(source: str) -> list[bytes]:
    """RGBA rows of the icon: the flipped logo with the penguin drawn over it, anti-aliased by supersampling."""
    background = logo_pixels(source)
    rows = []
    for y in range(SIZE):
        row = bytearray()
        for x in range(SIZE):
            hits = [penguin(x + (i + 0.5) / SAMPLES, y + (j + 0.5) / SAMPLES) for i in range(SAMPLES) for j in range(SAMPLES)]
            covered = [h for h in hits if h]
            r, g, b, a = background[y][x]
            if covered:
                share = len(covered) / len(hits)
                mean = [sum(c[k] for c in covered) / len(covered) for k in range(3)]
                r, g, b = (round(mean[0] * share + r * (1 - share)), round(mean[1] * share + g * (1 - share)),
                           round(mean[2] * share + b * (1 - share)))
                a = max(a, round(255 * share))
            row += bytes((r, g, b, a))
        rows.append(bytes(row))
    return rows


def png(width: int, height: int, rows: list[bytes]) -> bytes:
    """Encode RGBA rows as a PNG file."""
    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))
    raw = b"".join(b"\x00" + row for row in rows)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    TARGET.write_bytes(png(SIZE, SIZE, compose(sys.argv[1])))
