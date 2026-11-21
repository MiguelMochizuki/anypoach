"""Write the Chrome extension's 128x128 icon with the standard library only.

    uv run python tools/make_extension_icon.py
"""
import struct
import zlib
from pathlib import Path

SIZE = 128
TARGET = Path(__file__).resolve().parent.parent / "src/anypoach/chrome_extension/icon.png"


def pixel(x: int, y: int) -> tuple[int, int, int, int]:
    """A cobalt tile with a white ring: a plain geometric mark of our own."""
    inside = 8 <= x < SIZE - 8 and 8 <= y < SIZE - 8
    if not inside:
        return 0, 0, 0, 0
    distance = ((x - SIZE / 2 + 0.5) ** 2 + (y - SIZE / 2 + 0.5) ** 2) ** 0.5
    return (255, 255, 255, 255) if 24 <= distance <= 40 else (35, 120, 255, 255)


def png(width: int, height: int, rows: list[bytes]) -> bytes:
    """Encode RGBA rows as a PNG file."""
    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))
    raw = b"".join(b"\x00" + row for row in rows)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


if __name__ == "__main__":
    TARGET.write_bytes(png(SIZE, SIZE, [b"".join(bytes(pixel(x, y)) for x in range(SIZE)) for y in range(SIZE)]))
