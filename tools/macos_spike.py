"""Measures what the macOS code assumes, on a real Mac. Prints plain lines; paste them into docs/superpowers/macos-spike.md.

Run it with `uv run python tools/macos_spike.py`, move the pointer across your displays and click left and right
while it samples. Run it a second time with Screen Recording denied for your terminal to see the denied state.
"""
from __future__ import annotations

import sys
import time

from anypoach.macos import CoreGraphics


def main() -> int:
    if sys.platform != "darwin":
        print("This spike needs macOS.")
        return 1
    cg = CoreGraphics()
    print(f"A4 displays (bounds in points, scale = pixels per point): {cg.displays()}")
    print(f"A5 Screen Recording allowed: {cg.screen_recording_allowed()}")
    import mss
    with mss.mss() as sct:
        print(f"A1 mss monitors (expect points): {sct.monitors}")
        shot = sct.grab({"left": 0, "top": 0, "width": 100, "height": 100})
        print(f"A1 grab of a 100x100 box returned {shot.width}x{shot.height} px (expect 100 x scale)")
    print("A2/A3 sampling the pointer for 5 s: move across displays, click left and right")
    for _ in range(50):
        x, y = cg.pointer()
        held = [b for b in ("left", "right", "other") if cg.button_down(b)]
        print(f"  pointer ({x:.1f}, {y:.1f}) held {held}")
        time.sleep(0.1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
