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

1. **`anypoach.analysis`**: `VideoSource` decodes with PyAV and seeks by presentation time; `motion`, `palette`, and `keyframes` are numpy code; `inspect` ties them together and returns an `InspectionResult` whose `to_json()` is the camelCase shape stored in briefs. `tests/golden` holds expected results for synthetic fixtures (`tests/fixtures.py`); palettes of two fixtures are compared with a tolerance because PyAV bundles its own libswscale.
2. **`anypoach.capture` and `anypoach.pointer`**: a `CaptureBackend` (`MssBackend`) grabs BGRA frames; `Recorder` encodes H.264 `.mov` with real presentation times and draws the cursor and click ring from the pointer trace. `PointerTraceRecorder` polls a `PointerSource` (`Win32PointerSource`, `X11PointerSource`) at 120 Hz, capped at 5,000 events; Wayland and macOS have no source, so the trace is `available: false`.
3. **`anypoach.brief`**: `share()` writes `active-brief.json` plus `briefs/<uuid>.json` in the per-OS cache directory (`ANYPOACH_CACHE_DIR` overrides it), owner-only permissions (`icacls` on Windows), 24 h expiry. `cleanup` removes temporary media no valid brief needs.
4. **`anypoach.mcp`**: stdio server with `anypoach_read_brief`, `anypoach_read_moment`, `anypoach_inspect`, `anypoach_inspect_image`; it also writes presence files in `connections/`.
5. **`anypoach.ui`**: `Controller` (no Qt) runs choose area, record, analyze, share and returns the assistant prompt; `app.py` and `selection.py` are the PySide6 window and area overlay.

## Gotchas

- MCP stdout is the protocol channel. Never `print` to stdout in `anypoach.mcp` or what it imports.
- The MCP server relies on the private attribute `server._lowlevel_server` of `mcp` 2.3.0 to detect `initialized`; pin the version if that breaks.
- Real capture and the Windows/X11 pointer sources cannot be exercised on Wayland or headless Linux; only CI (Xvfb, Windows runner) and manual checks cover them.
- Design and plan documents are in `docs/superpowers`; measured timings are in `docs/superpowers/baseline.md`.
