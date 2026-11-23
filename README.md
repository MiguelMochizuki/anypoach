# AnyPoach

Record a UI interaction on Windows, Linux, or macOS and hand it to your coding assistant as evidence it can read.

[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python tests](https://github.com/MiguelMochizuki/anypoach/actions/workflows/python.yml/badge.svg)](https://github.com/MiguelMochizuki/anypoach/actions/workflows/python.yml)

- [Overview](#overview)
- [Quick Start](#quick-start)
- [Usage](#usage)
- [Project Organization](#project-organization)
- [Main Tools & Stack](#main-tools--stack)
- [Documentation](#documentation)
- [Acknowledgments](#acknowledgments)
- [Contributing](#contributing)
- [License](#license)

## Overview

You are building a UI, and a hover, a drag, or an easing curve is right in your head but hard to put in words. AnyPoach records the interaction and hands your coding assistant what it needs to rebuild it: keyframes, the color palette, motion timing, a local pointer trace, and your notes. The assistant reads it through a local MCP server. Nothing leaves your machine.

What you get:

- **Windows, Linux (X11 and Wayland) and macOS** from one Python code base.
- **One process** decodes the video: 0.06 s and 0.17 s on two small test clips, against 3.76 s and 33.5 s for the one-`ffmpeg`-per-sample code AnyPoach forked from (Poach has batched since 1.0.0; not re-measured) ([measurements](docs/superpowers/baseline.md)).
- **Private by construction:** no telemetry, audio or keyboard capture; briefs are owner-only and expire after 24 hours ([details](docs/privacy.md)).
- **Four MCP tools** any assistant that can launch a stdio command can use.
- **A Chrome companion** that sends the real CSS sizes, computed styles and animation timing of the component you record, so the assistant stops guessing them from pixels.
- **Honest about size:** images are reduced to 1280 px and captioned with their real size; `crop` returns a detail at native scale.

### Status

Version 1.0.1. Automated tests and CI on Ubuntu, Windows and macOS cover analysis, brief storage, the MCP server, pointer-trace logic, the recorder, the window and the packaging.

**No person has yet run the window, screen capture or the packaged builds on a real desktop.** Real captures ran only on CI runners (Xvfb on Linux, a Windows runner) and, on Wayland, by hand on GNOME. Treat anything else as untested and [report it](https://github.com/MiguelMochizuki/anypoach/issues). The checklist is [issue #12](https://github.com/MiguelMochizuki/anypoach/issues/12).

Not done: global shortcut on macOS and Wayland, code signing, native installers, a Chrome Web Store listing.

## Quick Start

### Without Python or `uv`

1. Download the zip for your system (`AnyPoach-<version>-linux|windows|macos.zip`) from the [latest release](https://github.com/MiguelMochizuki/anypoach/releases) and check it against `SHA256SUMS.txt`.
2. Unzip it with your file manager or `unzip` (not Python's `extractall`, which drops the execute bit).
3. Run `anypoach` from the folder.

The builds are unsigned. On macOS, right-click `anypoach` > Open the first time (or `xattr -dr com.apple.quarantine AnyPoach`). On Windows, choose More info > Run anyway in SmartScreen.

### From source

Requires Python 3.11 or newer and [uv](https://docs.astral.sh/uv/).

```sh
uv sync --extra ui    # PySide6 for the window, mss for screen capture
uv run anypoach       # choose an area, record, stop, copy the prompt
```

Or install it as a tool (puts `anypoach`, `anypoach-mcp` and `anypoach-setup` on your `PATH`):

```sh
uv tool install "anypoach[ui] @ git+https://github.com/MiguelMochizuki/anypoach"
```

### Platform notes

- **macOS:** the first recording triggers the Screen Recording prompt. Allow AnyPoach (or your terminal), then quit and reopen it.
- **Wayland:** the desktop portal asks you to confirm each recording, and GStreamer with its PipeWire plugin must be installed. On Debian and Ubuntu: `sudo apt install gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-pipewire`. AnyPoach tells you what is missing.

## Usage

### Record and hand off

1. Choose what to capture: an **area**, **Full screen**, a **Window**, a **Screenshot**, or **Import…** a video or image.
2. Record (up to 30 s) and stop. Review the frames, pin comments to moments, and edit the palette.
3. **Copy the prompt** and paste it into your assistant, or use **Continue with Claude** or **Continue with Codex**.

Everything the window does is in [Using the window](docs/usage.md).

### Connect an assistant

```sh
anypoach-setup claude   # prints: claude mcp add anypoach -- /path/to/anypoach-mcp
anypoach-setup codex    # the same for Codex
anypoach-setup json     # an `mcpServers` entry for any other client
```

Run the printed command (from a clone: `uv run anypoach-setup claude`), or paste the JSON into any MCP client that launches a stdio command.

**Claude Desktop:** download `AnyPoach.mcpb` from the [latest release](https://github.com/MiguelMochizuki/anypoach/releases) and install it in Settings > Extensions > Advanced settings. It needs `uv`. The bundle has been checked by running its server by hand, not yet inside Claude Desktop.

### Chrome companion

For a web page, the extension adds exact CSS sizes, fonts, colors and animation timing. Set it up once and pin a component before recording: [Chrome companion](docs/chrome-companion.md).

### Run the tests

```sh
uv sync --group dev --extra ui
uv run pytest                    # needs the ffmpeg CLI to synthesize test clips; Node and Chrome tests skip when missing
uv run pytest -m live            # real capture; needs an X11 or Windows desktop
uv run ruff check src tests tools
```

## Project Organization

```text
anypoach/
├── .github/    # CI and release workflows
├── docs/       # guides, plus designs, plans and the roadmap in superpowers/
├── packaging/  # PyInstaller spec for the release zips
├── src/        # the package: analysis, capture, pointer, brief, bridge, mcp, ui, chrome_extension
├── tests/      # test suite
├── tools/      # benchmark, jitter, portal spike, .mcpb builder
├── AGENTS.md
├── CLAUDE.md
├── CONTRIBUTING.md
├── LICENSE
├── NOTICE
├── pyproject.toml
└── README.md
```

What each module owns is in [Architecture and stack](docs/architecture.md).

## Main Tools & Stack

Python 3.11+ with `uv` and `hatchling`; PyAV and numpy for analysis and encoding; `mcp` for the server; PySide6 and `mss` for the window and capture; `jeepney` for the Wayland portal; `pytest` and `ruff` for tests and lint. CI runs on Ubuntu, Windows and macOS. The full table is in [Architecture and stack](docs/architecture.md#stack).

## Documentation

| Guide | What is in it |
| --- | --- |
| [Using the window](docs/usage.md) | Capture modes, review panel, palette, favorites, font match, tray, shortcut, settings |
| [Chrome companion](docs/chrome-companion.md) | Set up, pin a component, what the brief gains, what stays local |
| [What a recording produces](docs/output-format.md) | The brief, the MCP tools, segments, sizes |
| [Privacy](docs/privacy.md) | What is recorded, kept and sent |
| [Architecture and stack](docs/architecture.md) | Modules, libraries, CI |
| [Roadmap](docs/superpowers/poach-parity.md) | Releases and what is next (in Portuguese) |

## Acknowledgments

AnyPoach began as a fork of [**Poach**](https://github.com/guilopeszw/poach) by **Guilherme Lopes**, a charming Mac menu-bar app, and the idea, and the Chrome extension it grew from, are his. The credit stays in [NOTICE](NOTICE), as the license asks. The first version of Poach launched `ffmpeg` 364 times to look at 30 seconds of video (we counted); AnyPoach was rewritten in Python to do the job in one process and to run on Windows, Linux and macOS.

Thank you, Guilherme. The rivalry is friendly and the borrowing runs both ways. Poach 1.0.0 credits AnyPoach in its release notes and NOTICE for the child measurement and the live inspector, which it adapted with receipts attached, and it now has favorites, a font snatcher, size captions on images and a single `ffmpeg` process, which we are sure is convergent evolution. We took the tray, the window picker and the favorites file from the same playbook, so nobody is clean. Poach is still the one with the native Mac app, ScreenCaptureKit and a menu bar with a personality: if that is you, [use Poach](https://github.com/guilopeszw/poach). If you are on Windows or Linux, we are here, and the ideas keep flowing both ways.

## Contributing

Branch names, Conventional Commits and the manual platform checks are in [CONTRIBUTING.md](CONTRIBUTING.md). Docstrings follow the Google style described there.

## License

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
