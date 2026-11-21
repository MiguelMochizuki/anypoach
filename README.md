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

Early (v0.13.0 is a pre-release). Analysis, brief storage, the MCP server, pointer-trace logic, and the recorder are covered by automated tests on Linux. Screen capture and the window have not been run on real Windows or Linux X11 desktops yet, and the Windows pieces (ACLs, pointer source) only have CI to lean on. Wayland capture goes through the desktop portal and has been tried on GNOME only; other compositors may work and are not promised. On Wayland the compositor draws the cursor into the video, and the pointer trace stays off because no global pointer position exists. On macOS the pointer comes from CoreGraphics, Retina regions are converted between points and pixels, and recording is refused with a message until Screen Recording is allowed; all of that is covered by tests with fakes and a smoke test on the macOS CI runner, and no person has run it on a Mac yet (see `docs/superpowers/macos-spike.md` once it exists). Not done: global shortcut, a Chrome Web Store listing for the companion extension. Manual checks are listed in [CONTRIBUTING.md](CONTRIBUTING.md#manual-checks).

### Why not just use Poach?

AnyPoach started as a fork of Poach, a charming Mac menu-bar app. It is lovely, provided you own a Mac, want macOS 15 for the good recorder, and do not mind it launching `ffmpeg` 364 times to look at 30 seconds of video (we counted). AnyPoach does the job in one process, runs where Poach never will, and has since been rewritten so thoroughly that the fork is mostly a matter of etiquette. It needed a Mac, a menu bar, and macOS 15, and never once asked how the Wayland people were holding up. The credit stays in [NOTICE](NOTICE), as the license asks.

## Highlights

- Windows, Linux (X11 and Wayland), and macOS from one Python code base (see the status above for what has been run where).
- One process decodes the video. On the same small test clips the analysis takes 0.06 s and 0.17 s, against 3.76 s and 33.5 s for the one-`ffmpeg`-per-sample approach ([measurements](docs/superpowers/baseline.md)).
- Private by construction: no telemetry, audio, global input hooks, or keyboard capture (the optional shortcut registers one chord and sees no other key); files are owner-only. The one network request is the update check, and only when you press **Check for updates…** (a GET of the GitHub releases list, nothing sent).
- Four MCP tools that any assistant able to launch a stdio command can use.
- A Chrome companion extension that sends the real CSS sizes, computed styles, and animation timing of the component you are recording, so the assistant stops guessing them from pixels.
- Honest about size: images are reduced to 1280 px, so every one is captioned with its real size, and `crop` returns a detail at native scale.

## Quick Start

Requires Python 3.11 or newer and [uv](https://docs.astral.sh/uv/).

```sh
uv sync --extra ui    # PySide6 for the window, mss for screen capture
uv run anypoach       # choose an area or the full screen, record, stop, copy the prompt
```

Without cloning the repository, `uv` can install it as a tool (the commands `anypoach`, `anypoach-mcp` and `anypoach-setup` then go on your `PATH`):

```sh
uv tool install "anypoach[ui] @ git+https://github.com/MiguelMochizuki/anypoach"
```

On macOS the first recording triggers the system Screen Recording prompt; allow AnyPoach (or the terminal that runs it) in System Settings > Privacy & Security > Screen Recording, then quit and reopen it.

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
│       ├── baseline.md
│       ├── poach-parity.md
│       └── wayland-spike.md
├── src/               # source code
│   └── anypoach/      # the package
│       ├── analysis/  # decode video, motion, palette, keyframes
│       ├── brief/     # shared briefs and temp-media cleanup
│       ├── bridge/    # loopback server and pairing for the Chrome companion
│       ├── chrome_extension/  # the unpacked extension (manifest, scripts, popup)
│       ├── capture/   # screen grabbing, portal capture, recording, cursor overlay
│       ├── mcp/       # the stdio MCP server
│       ├── pointer/   # pointer polling and trace
│       ├── ui/        # window and area selection
│       ├── __init__.py
│       └── … +1 more
├── tests/             # test suite
│   ├── golden/        # expected results for the synthetic clips
│   │   ├── image-start.png
│   │   ├── image.json
│   │   ├── motion-peak.png
│   │   ├── motion-settled.png
│   │   ├── motion-start.png
│   │   ├── motion.json
│   │   ├── overrun-peak.png
│   │   └── … +9 more
│   ├── __init__.py
│   ├── conftest.py
│   ├── fixtures.py
│   ├── portal_fake.py
│   ├── test_brief_store.py
│   ├── test_capture_recorder.py
│   └── … +19 more
├── tools/             # benchmark, jitter and portal spike scripts
│   ├── bench.py
│   ├── jitter.py
│   └── portal_spike.py
├── .gitignore
├── AGENTS.md
└── … +7 more
```

### Key modules

- `analysis`: `VideoSource` decodes with PyAV and seeks by presentation time; `motion`, `palette`, and `keyframes` are numpy code; `inspect` ties them into an `InspectionResult`.
- `capture` and `pointer`: a `CaptureBackend` grabs BGRA frames (`MssBackend` on X11 and Windows; `PortalBackend` on Wayland, through the desktop portal and a `gst-launch-1.0` subprocess reading PipeWire), `Recorder` encodes H.264 with real frame times and draws the cursor and click ring, and `PointerTraceRecorder` polls a Windows, macOS (CoreGraphics through `anypoach.macos`) or X11 source at 120 Hz (at most 5,000 events). Wayland has no pointer source, so its trace is marked unavailable.
- `brief`: writes `active-brief.json` plus one archive per share into the per-OS cache directory, and cleans up temporary media.
- `bridge`: a loopback HTTP server (`127.0.0.1:47832`) that accepts a pairing-code-protected evidence session from the Chrome extension, validates it strictly, and keeps it in memory for 180 s so the brief can include it.
- `mcp`: the `anypoach-mcp` server and its presence files.
- `ui`: `Controller` runs the flow without Qt; `app.py`, `selection.py`, and `frozen_selection.py` (a frozen screen frame to pick an area on Wayland) are the PySide6 window and the area overlays.

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
| `jeepney` (Linux only) | Talking to the desktop portal over DBus on Wayland |
| `pytest`, `ruff` (group `dev`) | Tests and lint |

### CI

`.github/workflows/python.yml` runs lint and tests on Ubuntu 22.04, Windows, and macOS, plus the live capture test under Xvfb and on Windows. `conventional-commits.yml` checks commit subjects on pull requests.

## Usage

### Run the window

`uv run anypoach` opens the window: choose an area (or press Full screen for the whole screen, or Window to record one window: a list of the windows on Windows and X11, the portal's window picker on Wayland, not available on macOS yet), press Screenshot for a still of it, press Import… to analyze a video (`.mp4`, `.mov`) or an image from disk, or record (up to 30 s; where the desktop has a tray, its icon also records the full screen without opening the window), stop, and review. The review panel plays the recording frame by frame (Space plays and pauses, Left and Right step one frame), shows where the video moves as bands on the timeline, and lets you pin a comment to any moment (up to 50, 500 characters each) and write general instructions for the whole capture. Comments and instructions travel in the brief as `evidence.annotations` and `context`, and the assistant sees each comment next to the frame it is pinned to. The frames of the panel are decoded once, kept in memory, and dropped when you record again or close the window. Copy the prompt when you are done; it does not wait for the frames. Enter activates the focused button. Outside Windows the window hides while recording and a tray menu stops it. **Settings…** shows how much space AnyPoach uses and clears unused captures (never what a valid brief or the open window needs), copies the connect command for Claude Code, Codex or any client, and checks for updates on request. Under the keyframes, the palette strip lets you change a color (click it), drop one (×), add one (up to 12) or reset to the analyzed palette; the brief carries your version. **Save as favorite…** keeps the handoff (instructions, notes, palette, timing, pointer evidence and up to three reference images, but not the video); **Favorites…** copies a fresh prompt from one, and exports or imports `.anypoach` files to share them. Favorites are the only thing AnyPoach keeps until you delete it, in a private folder (`ANYPOACH_DATA_DIR` overrides it); a handoff made from one has no `anypoach_read_moment`. On first launch a welcome tour explains the flow, names the one thing your system asks for before recording works, and offers to pair the Chrome companion; **Settings… > Welcome tour…** shows it again. **Settings… > Global shortcut** (off until you turn it on; Windows and X11 only) makes Ctrl+Alt+Shift+P start a full-screen recording and stop it. It registers that one chord with the system and sees no other key press. On a screenshot or imported image, **Match font…** lets you drag over one line of text, type what it says, and ranks the fonts installed on your computer by how their letters look; the one you choose goes into the handoff as `visualFontMatch` (an approximation, there is no text recognition).

### Chrome companion

For a web interface, the page knows what the video cannot: exact CSS sizes, font, radius, colors, and the timing and easing of each animation. The companion extension collects them from the component you pick.

1. In the window, press **Open the extension folder**. In Chrome (Edge and Brave work the same way) open `chrome://extensions`, turn on Developer mode, and choose **Load unpacked** on that folder.
2. Press **Copy pairing code** in the window, open the extension popup, and paste the code once.
3. On your page, press **Choose a component** in the popup. A card follows the pointer with the live size, font, colors, radius, and running animations of whatever is under it (**↑** picks the parent); click to pin it. Then record in AnyPoach as usual, do the interaction, and press **Finish and send** in the popup (before or after stopping in AnyPoach; a session is kept for 180 s).
4. Copy the prompt. The brief now carries `evidence.browserEvidence` with `components`, the measured visible descendants of the pinned one (up to 40, with size, font, colors, and short text; measured when you pin and again when you finish), and and `anypoach_read_moment` lists the nearby states with `rect`, sizes, colors, radius, opacity, transform, shadow, and the animations with duration, delay, easing, and keyframe offsets, plus the page's `devicePixelRatio` and viewport.

What stays local: the server listens on `127.0.0.1` only, while the window is open, rejects any other `Host` or a page `Origin`, and requires the pairing code on every request; **Create a new pairing code** revokes the old one. The extension asks for `activeTab`, `scripting`, `storage`, and `http://127.0.0.1/*`, reads text and computed styles of the picked component only, and nothing goes anywhere but your machine. Not yet: there is no Chrome Web Store listing, so you load the folder yourself.

### Connect an assistant

```sh
anypoach-setup claude   # prints: claude mcp add anypoach -- /path/to/anypoach-mcp
anypoach-setup codex    # the same for Codex
anypoach-setup json     # an `mcpServers` entry for any other client
```

Run the printed command (or paste the JSON). From a clone, use `uv run anypoach-setup claude`. Any MCP client that launches a stdio command works the same way.

| Tool | Purpose |
| --- | --- |
| `anypoach_read_brief` | Read the latest shared brief, or one by `briefId`: keyframes, palette, timing, pointer trace, notes. |
| `anypoach_read_moment` | Read one frame of the shared recording at a timestamp. `crop` (native pixels from the top left) and `maxSize` return a detail at native scale. |
| `anypoach_inspect` | Analyze a local `.mp4` or `.mov` file. |
| `anypoach_inspect_image` | Analyze a local still image. |

### Configuration

Briefs live in `~/Library/Caches/AnyPoach` (macOS), `~/.cache/AnyPoach` (Linux), or `%LOCALAPPDATA%\AnyPoach\Cache` (Windows). Set `ANYPOACH_CACHE_DIR` to use another folder.

### Tests

```sh
uv sync --group dev --extra ui
uv run pytest                    # needs the ffmpeg CLI to synthesize test clips; Node and Chrome tests skip when missing
uv run pytest -m live            # real capture; needs an X11 or Windows desktop
uv run ruff check src tests tools
```

## Key Outputs & Reports

A recording produces a few keyframe PNGs and a brief, a JSON file with the analysis, the pointer trace, your notes, and an instruction for the assistant. The brief is read back through `anypoach_read_brief`; the PNGs through the same tool and `anypoach_read_moment`. When the recording holds several interactions, `evidence.segments` lists each one (up to 12) with its own start, peak, end, strength and timing; the 4 strongest come with start, peak and settled frames, the others are one `anypoach_read_moment` away, and the top-level `keyframes` and `timing` stay those of the strongest one. The brief records the real size of the capture in `evidence.capture` (`widthPx`, `heightPx`, `deviceScale`) and every image the MCP returns is captioned with its size, because keyframes are reduced to 1280 px (a 1854x962 recording arrives as 1280x664). `deviceScale` is the number of video pixels per CSS pixel (the screen scale, adjusted when the recorder shrinks a capture past 1920 px) on Windows and X11, and `null` where it is unknown, such as Wayland or imported media; the prompt tells the assistant to ask instead of guessing. With the Chrome companion, the brief also holds `evidence.browserEvidence`: up to 48 states and 16 animations of the picked component, aligned to the video through `videoOffsetMs` and trimmed to the recording (one second of margin, plus the state that was in force when it began). The repository ships no sample output.

## Documentation Conventions

Docstrings follow the Google style described in [CONTRIBUTING.md](CONTRIBUTING.md#documentation-conventions).

## Contributing

Branch names, Conventional Commits, and the manual platform checks are in [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
