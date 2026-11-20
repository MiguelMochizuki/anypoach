"""Screen capture interface. Backends only grab pixels; recording, cursor drawing and encoding live elsewhere."""
from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple, Protocol

import numpy as np

from poach.pointer.trace import Rect


class Screen(NamedTuple):
    id: int
    bounds: Rect  # global physical pixels, top-left origin (may be negative on multi-monitor setups)
    scale: float  # device pixel ratio (physical / logical)


@dataclass(frozen=True)
class Frame:
    pixels: np.ndarray  # BGRA, shape (height, width, 4)
    time_s: float  # monotonic clock reading when the frame was grabbed


class CaptureBackend(Protocol):
    def screens(self) -> list[Screen]: ...

    def grab(self, region: Rect) -> Frame: ...
