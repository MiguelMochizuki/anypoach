# Architecture and stack

Pieces connected by files on disk, not by network.

## Modules

- `analysis`: `VideoSource` decodes with PyAV and seeks by presentation time; `motion`, `palette` and `keyframes` are numpy code; `segments` splits a clip into interactions; `inspect` ties them into an `InspectionResult`.
- `capture` and `pointer`: a `CaptureBackend` grabs BGRA frames (`MssBackend` on X11, Windows and macOS; `PortalBackend` on Wayland, through the desktop portal and a `gst-launch-1.0` subprocess reading PipeWire). `Recorder` encodes H.264 with real frame times and draws the cursor and click ring. `PointerTraceRecorder` polls a Windows, macOS (CoreGraphics through `anypoach.macos`) or X11 source at 120 Hz, at most 5,000 events. Wayland has no pointer source, so its trace is marked unavailable.
- `brief`: writes `active-brief.json` plus one archive per share into the per-OS cache directory, and cleans up temporary media.
- `bridge`: a loopback HTTP server (`127.0.0.1:47832`) that accepts a pairing-code-protected evidence session from the Chrome extension, validates it strictly, and keeps it in memory for 180 s.
- `mcp`: the `anypoach-mcp` server and its presence files.
- `ui`: `Controller` runs the flow without Qt; the rest is the PySide6 window, the area overlays, the review panel, favorites and settings.
- `packaging/` and `.github/workflows/package.yml`: the PyInstaller zips attached to each release.

## Stack

Python 3.11 or newer, managed with `uv`; `hatchling` builds the package.

| Library | Used for |
| --- | --- |
| `av` (PyAV) | Decoding video and encoding the H.264 recording, in process |
| `numpy` | Motion, palette and frame math |
| `mcp` | The stdio MCP server |
| `platformdirs` | The per-OS cache directory |
| `PySide6`, `mss` (extra `ui`) | The window and screen capture |
| `jeepney` (Linux only) | Talking to the desktop portal over DBus on Wayland |
| `pytest`, `ruff` (group `dev`) | Tests and lint |

## CI

- `python.yml` runs lint and tests on Ubuntu 22.04, Windows and macOS, plus the live capture test under Xvfb and on Windows.
- `package.yml` builds the zips on the three systems and, on a tag, attaches them, the `.mcpb` and `SHA256SUMS.txt` to the release.
- `conventional-commits.yml` checks commit subjects on pull requests.

Design notes, plans and measurements are in [docs/superpowers](superpowers).
