# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

`AGENTS.md` holds the repository rules (privacy of captures, Conventional Commits, README/CONTRIBUTING upkeep). Read it first; this file only adds commands and architecture.

## Commands

Python 3.11+ managed with `uv`.

```sh
uv sync --group dev --extra ui
uv run pytest                                  # headless suites; needs the ffmpeg CLI only to synthesize test clips
uv run pytest tests/test_inspect_golden.py -k motion
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_ui_window.py
uv run pytest -m live                          # real screen capture; needs an X11 or Windows desktop
uv run ruff check src tests tools
uv run anypoach                                # PySide6 window
uv run anypoach-mcp                            # stdio MCP server
```

## Architecture

Pieces connected by files on disk, not by network:

1. **`anypoach.analysis`**: `VideoSource` decodes with PyAV and seeks by presentation time; `motion`, `palette`, and `keyframes` are numpy code; `inspect` ties them together and returns an `InspectionResult` whose `to_json()` is the camelCase shape stored in briefs, including `capture` (native size and `deviceScale`, null when unknown). `tests/golden` holds expected results for synthetic fixtures (`tests/fixtures.py`); palettes of two fixtures are compared with a tolerance because PyAV bundles its own libswscale.
2. **`anypoach.capture` and `anypoach.pointer`**: a `CaptureBackend` grabs BGRA frames (`MssBackend` on X11 and Windows; `PortalBackend` on Wayland, which asks the desktop portal through `jeepney` and reads PipeWire frames from a `gst-launch-1.0` subprocess; `default_backend()` picks one); `Recorder` encodes H.264 `.mov` with real presentation times and draws the cursor and click ring from the pointer trace. `PointerTraceRecorder` polls a `PointerSource` (`Win32PointerSource`, `X11PointerSource`) at 120 Hz, capped at 5,000 events; Wayland and macOS have no source, so the trace is `available: false` (on Wayland the compositor embeds the cursor in the video).
3. **`anypoach.brief`**: `share()` writes `active-brief.json` plus `briefs/<uuid>.json` in the per-OS cache directory (`ANYPOACH_CACHE_DIR` overrides it), owner-only permissions (`icacls` on Windows), 24 h expiry. `cleanup` removes temporary media no valid brief needs.
4. **`anypoach.bridge`**: `BridgeServer` is a loopback `http.server` (port 47832) with a bearer pairing code (uppercase UUID in `bridge-pairing`, 0600) compared with `hmac.compare_digest`; it refuses a foreign `Host` and any `Origin` that is not `chrome-extension://`, caps bodies at 256 KiB, and validates every session with strict pydantic models in `evidence.py`. `EvidenceStore` keeps the final session 180 s and a partial one 10 s; `Controller.copy_handoff()` attaches the session that overlaps `Recording.epoch_range_ms` as `browserEvidence`, aligned with `videoOffsetMs`. `BridgeController` owns start, stop, and the pairing code for the window. The extension itself is plain JS in `chrome_extension/`; `tests/chrome` drives it with Node and headless Chrome.
5. **`anypoach.mcp`**: stdio server with `anypoach_read_brief`, `anypoach_read_moment` (with `crop` and `maxSize` in native pixels), `anypoach_inspect`, `anypoach_inspect_image`; every image it returns carries a size caption built from `evidence.capture`; it also writes presence files in `connections/`.
6. **`anypoach.ui`**: `Controller` (no Qt) runs choose area, record, analyze, share and returns the assistant prompt; `app.py` and `selection.py` are the PySide6 window and area overlay.

## Gotchas

- The bridge's `open-capture` route answers 503: the server thread cannot touch Qt, so no callback is wired yet. The extension does not call it.
- The adapted extension files carry a one-line license notice; keep it when editing them.
- MCP stdout is the protocol channel. Never `print` to stdout in `anypoach.mcp` or what it imports.
- The MCP server relies on the private attribute `server._lowlevel_server` of `mcp` 2.3.0 to detect `initialized`; pin the version if that breaks.
- Real capture and the Windows/X11 pointer sources cannot be exercised on Wayland or headless Linux; only CI (Xvfb, Windows runner) and manual checks cover them. The portal path is tested with fakes (a private `dbus-daemon` and a Python frame producer) and by hand on GNOME; `docs/superpowers/wayland-spike.md` has the measurements and why the cursor position is unreachable.
- Design and plan documents are in `docs/superpowers`; measured timings are in `docs/superpowers/baseline.md`.
