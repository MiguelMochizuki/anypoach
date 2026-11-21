# AnyPoach

Record a UI interaction on Windows, Linux, or macOS and hand it to your coding assistant as evidence it can read.

[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python tests](https://github.com/MiguelMochizuki/anypoach/actions/workflows/python.yml/badge.svg)](https://github.com/MiguelMochizuki/anypoach/actions/workflows/python.yml)

- [Overview](#overview)
- [Highlights](#highlights)
- [Quick Start](#quick-start)
- [Project Organization](#project-organization)
- [Main Tools & Stack](#main-tools--stack)
- [Usage](#usage)
- [Key Outputs & Reports](#key-outputs--reports)
- [Documentation Conventions](#documentation-conventions)
- [Contributing](#contributing)
- [License](#license)

## Overview

### Problem

You are building a UI and a hover, a drag, or an easing curve is right in your head but hard to put in words. AnyPoach records the interaction and hands your coding assistant what it needs to rebuild it: keyframes, the color palette, motion timing, and a local pointer trace with your notes.

AnyPoach captures a screen area, samples the pointer (position and button state only), picks the moments that matter, and writes a brief that expires after 24 hours. The assistant reads it through a local MCP server. Nothing leaves your machine.

### Status and limitations

Early. Analysis, brief storage, the MCP server, pointer-trace logic, and the recorder are covered by automated tests on Linux. Screen capture and the window have not been run on real Windows or Linux X11 desktops yet, and the Windows pieces (ACLs, pointer source) only have CI to lean on. Wayland capture goes through the desktop portal and has been tried on GNOME only; other compositors may work and are not promised. On Wayland the compositor draws the cursor into the video, and the pointer trace stays off because no global pointer position exists. Not done: comment editor, global shortcut, macOS pointer sampling. Manual checks are listed in [CONTRIBUTING.md](CONTRIBUTING.md#manual-checks).

### Why not just use Poach?

AnyPoach started as a fork of Poach, a charming Mac menu-bar app. It is lovely, provided you own a Mac, want macOS 15 for the good recorder, and do not mind it launching `ffmpeg` 364 times to look at 30 seconds of video (we counted). AnyPoach does the job in one process, runs where Poach never will, and has since been rewritten so thoroughly that the fork is mostly a matter of etiquette. It needed a Mac, a menu bar, and macOS 15, and never once asked how the Wayland people were holding up. The credit stays in [NOTICE](NOTICE), as the license asks.

## Highlights

- Windows, Linux, and macOS from one Python code base (X11 and Windows first; see the status above).
- One process decodes the video. On the same small test clips the analysis takes 0.06 s and 0.17 s, against 3.76 s and 33.5 s for the one-`ffmpeg`-per-sample approach ([measurements](docs/superpowers/baseline.md)).
- Private by construction: no network, telemetry, audio, global input hooks, or keyboard capture; files are owner-only.
- Four MCP tools that any assistant able to launch a stdio command can use.

## Quick Start

Requires Python 3.11 or newer and [uv](https://docs.astral.sh/uv/).

```sh
uv sync --extra ui    # PySide6 for the window, mss for screen capture
uv run anypoach       # choose an area, record, stop, copy the prompt
```

On a Wayland session the screen comes through the desktop portal, which asks you to confirm each recording, and needs GStreamer with its PipeWire plugin (on Debian and Ubuntu: `sudo apt install gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-pipewire`). AnyPoach tells you what is missing.

Paste the copied prompt into your assistant. It tells the assistant to read the brief through the MCP server described under [Usage](#usage).

## Project Organization

```text
anypoach/
├── .github/           # GitHub config
│   ├── workflows/
│   │   ├── conventional-commits.yml
│   │   └── python.yml
│   └── CODEOWNERS
├── docs/              # documentation
│   └── superpowers/   # design, plan, measured baseline
│       ├── plans/
│       ├── specs/
│       └── baseline.md
├── src/               # source code
│   └── anypoach/      # the package
│       ├── analysis/  # decode video, motion, palette, keyframes
│       ├── brief/     # shared briefs and temp-media cleanup
│       ├── capture/   # screen grabbing, recording, cursor overlay
│       ├── mcp/       # the stdio MCP server
│       ├── pointer/   # pointer polling and trace
│       ├── ui/        # window and area overlay
│       └── … +2 more
├── tests/             # test suite
│   ├── golden/        # expected results for the synthetic clips
│   │   ├── image-start.png
│   │   ├── image.json
│   │   ├── motion-peak.png
│   │   ├── motion-settled.png
│   │   ├── motion-start.png
│   │   ├── motion.json
│   │   └── … +10 more
│   ├── __init__.py
│   ├── conftest.py
│   ├── fixtures.py
│   ├── test_brief_store.py
│   ├── test_capture_recorder.py
│   └── … +13 more
├── tools/             # benchmark and jitter scripts
│   ├── bench.py
│   └── jitter.py
├── .gitignore
└── … +8 more
```

### Key modules

- `analysis`: `VideoSource` decodes with PyAV and seeks by presentation time; `motion`, `palette`, and `keyframes` are numpy code; `inspect` ties them into an `InspectionResult`.
- `capture` and `pointer`: `MssBackend` grabs frames, `Recorder` encodes H.264 with real frame times and draws the cursor and click ring, and `PointerTraceRecorder` polls a Windows or X11 source at 120 Hz (at most 5,000 events).
- `brief`: writes `active-brief.json` plus one archive per share into the per-OS cache directory, and cleans up temporary media.
- `mcp`: the `anypoach-mcp` server and its presence files.
- `ui`: `Controller` runs the flow without Qt; `app.py` and `selection.py` are the PySide6 window and the area overlay.

## Main Tools & Stack

### Language and runtime

Python 3.11 or newer, managed with `uv`; `hatchling` builds the package.

### Key libraries

| Library | Used for |
| --- | --- |
| `av` (PyAV) | Decoding video and encoding the H.264 recording, in process |
| `numpy` | Motion, palette, and frame math |
| `mcp` | The stdio MCP server |
| `platformdirs` | The per-OS cache directory |
| `PySide6`, `mss` (extra `ui`) | The window and screen capture |
| `pytest`, `ruff` (group `dev`) | Tests and lint |

### CI

`.github/workflows/python.yml` runs lint and tests on Ubuntu 22.04, Windows, and macOS, plus the live capture test under Xvfb and on Windows. `conventional-commits.yml` checks commit subjects on pull requests.

## Usage

### Run the window

`uv run anypoach` opens the window: choose an area, record (up to 30 s), stop, look at the keyframes, and copy the prompt. Enter activates the focused button. Outside Windows the window hides while recording and a tray menu stops it.

### Connect an assistant

```sh
claude mcp add anypoach -- uv run --project /absolute/path/to/anypoach anypoach-mcp
```

Any MCP client that launches a stdio command works the same way.

| Tool | Purpose |
| --- | --- |
| `anypoach_read_brief` | Read the latest shared brief, or one by `briefId`: keyframes, palette, timing, pointer trace, notes. |
| `anypoach_read_moment` | Read one frame of the shared recording at a timestamp, plus frames after drag releases. |
| `anypoach_inspect` | Analyze a local `.mp4` or `.mov` file. |
| `anypoach_inspect_image` | Analyze a local still image. |

### Configuration

Briefs live in `~/Library/Caches/AnyPoach` (macOS), `~/.cache/AnyPoach` (Linux), or `%LOCALAPPDATA%\AnyPoach\Cache` (Windows). Set `ANYPOACH_CACHE_DIR` to use another folder.

### Tests

```sh
uv sync --group dev --extra ui
uv run pytest                    # needs the ffmpeg CLI to synthesize test clips
uv run pytest -m live            # real capture; needs an X11 or Windows desktop
uv run ruff check src tests tools
```

## Key Outputs & Reports

A recording produces a few keyframe PNGs and a brief, a JSON file with the analysis, the pointer trace, your notes, and an instruction for the assistant. The brief is read back through `anypoach_read_brief`; the PNGs through the same tool and `anypoach_read_moment`. The repository ships no sample output.

## Documentation Conventions

Docstrings follow the Google style described in [CONTRIBUTING.md](CONTRIBUTING.md#documentation-conventions).

## Contributing

Branch names, Conventional Commits, and the manual platform checks are in [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
