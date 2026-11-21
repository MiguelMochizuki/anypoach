"""Screen capture interface. Backends only grab pixels; recording, cursor drawing and encoding live elsewhere."""
from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple, Protocol

import numpy as np

from anypoach.pointer.trace import Rect


class Screen(NamedTuple):
    """A display, with its place in the global pixel space (`bounds`) and its device pixel ratio (`scale`)."""
    id: int
    bounds: Rect  # global physical pixels, top-left origin (may be negative on multi-monitor setups)
    scale: float  # device pixel ratio (physical / logical)


@dataclass(frozen=True)
class Frame:
    """One grabbed image.

    Attributes:
        pixels: BGRA array of shape `(height, width, 4)`.
        time_s: Reading of the monotonic clock when the frame was grabbed; it becomes the frame's presentation time.
    """
    pixels: np.ndarray  # BGRA, shape (height, width, 4)
    time_s: float  # monotonic clock reading when the frame was grabbed


class CaptureBackend(Protocol):
    """Something that can list screens and grab pixels from them. Backends do no encoding or drawing."""
    def screens(self) -> list[Screen]:
        """List the available screens in global physical pixels."""

    def grab(self, region: Rect) -> Frame:
        """Grab the pixels of `region` (global physical pixels, top-left origin).

        Raises:
            PermissionError: If the OS denies screen capture.
        """
