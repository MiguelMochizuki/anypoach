# Contributing to AnyPoach

Thanks for helping improve AnyPoach. It is a Python project (`src/anypoach`) that records a UI interaction on Windows, Linux, or macOS and hands it to a coding assistant through a local MCP server.

## Contribute a change

Create your branch from the latest `main` and name it `username/what-you-did`. Use your GitHub username before the slash and a short, lowercase, hyphen-separated description after it. For example, `octocat/record-ui-flow` or `octocat/fix-capture-overlay`.

Open a pull request against `main`. Use a Conventional Commit title in the form `type(scope): summary`, such as `fix(capture): exclude AnyPoach windows from recordings`. Describe the change the reviewer will see. In the body, explain the problem, the resulting behavior, and how you verified it. For interface changes, include a screenshot or short recording made with synthetic or explicitly shareable media. Call out changes to permissions, storage, or supported macOS versions.

**Every commit must be atomic and use a Conventional Commit subject** in the same form. Choose the area touched as the scope and describe the change with an imperative verb. For example:

```text
fix(capture): keep frame times strictly increasing
test(pointer): cover monitors with a negative origin
docs(readme): list the manual checks per platform
```

Keep one independently reviewable change per commit. Include regression tests with the fix they verify. Split unrelated edits, formatting, or documentation into separate commits. Use `feat` for new behavior, `fix` for corrections, `docs` for documentation, and `style`, `refactor`, `test`, `build`, `ci`, or `chore` when appropriate. Flag breaking interface changes with `!` before the colon and describe the migration in the commit body.

Use a lowercase scope made of letters, digits, dots, underscores, slashes, or hyphens, starting with a letter or digit. The check also accepts `perf` and `revert`. Rebase your branch to update it and reword any failing commits. GitHub checks each commit subject. Reviewers check branch names and PR titles. Every PR must pass the commit check and resolve review conversations. PRs from contributors require approval from @guilopeszw, the code owner for every path. New commits dismiss earlier approvals. For an owner-authored PR, the owner can use GitHub’s review bypass to rebase and merge after the checks pass. Reserve repository administrator access for the owner.

Run the tests and lint before opening a pull request. Keep virtual environments, build output, temporary captures, and private media out of commits. Update the README and this guide when commands, capabilities, permissions, or data handling change. Contributions are licensed under the repository’s [Apache License 2.0](LICENSE).

## Development setup

Install [uv](https://docs.astral.sh/uv/) and the `ffmpeg` command-line tool (the tests use it only to synthesize clips; the package itself does not). Python 3.11 or newer is required.

```sh
uv sync --group dev --extra ui    # the ui extra adds PySide6 and mss
uv run pytest                     # headless suites
uv run ruff check src tests tools
uv run anypoach                   # the capture window
uv run anypoach-mcp               # stdio MCP server
uv run pytest -m live             # real capture; needs an X11 or Windows desktop (CI uses Xvfb on Linux)
```

Window tests run with `QT_QPA_PLATFORM=offscreen`. To connect an assistant to your checkout, point the MCP client at `uv run --project /absolute/path/to/anypoach anypoach-mcp`.

## Tests and goldens

`tests/fixtures.py` synthesizes clips; `tests/golden` holds the expected keyframes, palettes, and timing for them. The goldens were produced by the analysis code this project started from and are now frozen files: change them only together with a deliberate change of behavior, and say why in the commit. Keyframe kinds, times, durations, and timing tokens must match exactly. Palettes match exactly except for two fixtures, where the dominant colors are compared within two per channel because PyAV bundles its own libswscale. The 30 s recording clip is compared against the original frame instead of byte for byte.

## Data handling

No network, telemetry, or audio. Only pointer position and button state are sampled, by polling, with no global hooks (on macOS through CoreGraphics, which needs no input permission; recording itself needs Screen Recording). The review panel decodes the recording into small JPEG frames held in memory only (`analysis/proxy.py`); nothing of them is written to disk or sent anywhere. Briefs and archives live in the per-OS cache directory (`~/Library/Caches/AnyPoach` on macOS, `~/.cache/AnyPoach` on Linux, `%LOCALAPPDATA%\AnyPoach\Cache` on Windows; `ANYPOACH_CACHE_DIR` overrides it for tests) and expire after 24 hours. On POSIX they use `0700` and `0600`. On Windows the same files get an ACL limited to the current user through `icacls`; that path has no local test and relies on CI. The Windows pointer source needs a per-monitor DPI-aware process, or coordinates arrive scaled. On Wayland there is no global pointer position, so the trace reports `available: false`. The Chrome companion adds a loopback listener (`127.0.0.1:47832`, only while the window is open) and keeps the evidence it receives in memory for 180 s; it is covered by the same rules: no network beyond loopback, nothing retained after the brief expires.

## Manual checks

Before relying on a change to capture or the window, check by hand on Windows and on Linux X11: the AnyPoach window does not appear in the video (on Windows it is excluded with `SetWindowDisplayAffinity`; elsewhere it is hidden while recording and a tray menu stops the recording, with a 30 s limit), the selection overlay is not recorded, the cursor and click ring are drawn where the pointer was, and the brief shows up in the OS cache directory. `tools/bench.py` and `tools/jitter.py` print the timings recorded in `docs/superpowers/baseline.md`.

On a Wayland session (GNOME is the tested one), also check: choosing an area shows the portal dialog and then a frozen frame of the screen where you drag the area, and Escape or declining the dialog leaves no sharing indicator behind; a 10 s recording of a moving area produces keyframes and a brief that an MCP client can read; pressing "Stop sharing" in the shell mid-recording ends with a message instead of a hang; and `pgrep gst-launch` shows nothing after stopping or closing the app. The window is minimized while recording, because GNOME has no tray, so restore it from the dock to stop. `tools/portal_spike.py` reproduces the raw portal flow. On macOS, also check: the first recording shows the system Screen Recording prompt, or the refusal message with the System Settings path when it was denied before, and the window stays where it is; after allowing it and reopening AnyPoach, a 10 s recording has `pointerTrace.available == true`, a click ring where you clicked, and `evidence.capture` equal to the chosen area in physical pixels on a Retina display (and on a second display with another scale, if you have one); the red recording item shows in the menu bar and stops the recording. `tools/macos_spike.py` prints the display scales, the `mss` frame shape, the permission state and a few seconds of pointer samples; its results go to `docs/superpowers/macos-spike.md`. On any platform, read the brief back and check that `evidence.capture` has the real recording size and that `anypoach_read_moment` with a `crop` returns that rectangle at native size; `deviceScale` is video pixels per CSS pixel on Windows and X11 (check it on a capture wider than 1920 px) and `null` on Wayland. Full screen should select the whole shared stream without the frozen frame (on Wayland the dialog still appears). Where a tray exists, check that its menu shows AnyPoach, records the full screen and quits, that it switches to Stop recording while recording, and that the icon returns to idle afterwards. Check `anypoach-setup claude`, `codex` and `json` on a `uv tool install` install: the printed launcher path must start the server.

For the review panel and the motion segments, check by hand on a real desktop: record about 20 s with three separate interactions (hover, click, a drag) and check that `evidence.segments` holds three entries with sensible timing and that `anypoach_read_brief` returns their frames; stop and see that the first frame appears within a second on a 1080p area, that dragging the timeline is smooth and Space plays without stuttering badly, that a comment pinned at about 12 s shows, through `anypoach_read_moment` at the same time, the frame you were looking at, that Copy prompt works while the panel still says it is preparing frames, and that recording again or closing the window while frames are being prepared leaves nothing behind (the process exits promptly).

For the Chrome companion, check by hand with a real Chrome: load the unpacked `src/anypoach/chrome_extension` folder (the window's **Open the extension folder** button opens it), paste the pairing code, pick a component whose hover changes size or color, record it, press Stop in AnyPoach, then press **Finish and send** in the popup. Before pinning, check the inspector card: it follows the pointer, shows size, font, color capsules, radius, and running animations, stays fully inside the window near the edges (try a component at the right and bottom edge), never shows the element's text, and is gone after pinning. Copy the prompt, read the brief back, and check that `evidence.browserEvidence` holds the states and animations with a sensible `videoOffsetMs`, and that `anypoach_read_moment` near that time lists `rect` and the style keys. A wrong code in the popup must say to pair again, and a second AnyPoach window on the same port must show `error:` with the port in the Chrome section instead of failing to start. The automated pieces are `tests/test_chrome_extension.py`: the manifest and wheel checks always run, the service-worker flow needs `node`, and the capture script runs in headless Chrome when a `google-chrome`, `chromium`, or `chrome` binary is on the `PATH` (both skip otherwise). `tools/make_extension_icon.py` rebuilds the icon from two image paths and needs `ffmpeg`.

## Releases

Versions follow `docs/superpowers/poach-parity.md` (section "Roteiro de releases"). To prepare one:

1. Bump `version` in `pyproject.toml` and in `src/anypoach/chrome_extension/manifest.json` (a test keeps them equal), and refresh `uv.lock`.
2. Refresh the docs: README (status and usage), this file, and the roadmap table.
3. Check that CI is green on Ubuntu, Windows, and macOS, and run the manual checks above that the release touches.
4. Write the notes in the style of the v0.1.0 release: what is new, what was verified and where, what is not done.
5. Publish as a pre-release until 1.0. Create the tag and the release only after the maintainer says so.

## Documentation Conventions

### Python

Google-style docstrings, in English, with a summary line in the imperative mood (`Write`, `Return`, not `Writes`). Lines stay within 110 columns, like the code.

- Every module, tests included, starts with a one-line docstring saying what it owns. Empty `__init__.py` files are exempt.
- Every public class, function, and method has a docstring. Names starting with `_`, one-line properties, `__init__` that only stores arguments, and test functions are exempt (a test's name is its documentation).
- Add `Args:`, `Returns:`, and `Raises:` only when they say something the name and type hints do not: units, coordinate spaces, ranges, side effects, what `None` means. A one-line summary is enough for an obvious function.
- Do not repeat types in the docstring. The type hints carry the type; the docstring carries the meaning.
- Explain why, not what, in comments. Do not narrate the code.

Worked example (`src/anypoach/ui/controller.py`):

```python
def physical_rect(start: tuple[float, float], end: tuple[float, float], *, origin: tuple[float, float], dpr: float) -> Rect:
    """Convert two dragged corners into a global rectangle in physical pixels.

    Assumes one device pixel ratio per screen.

    Args:
        start: First corner, in the screen's logical coordinates.
        end: Opposite corner, in the same coordinates.
        origin: The screen's logical top-left in the global coordinate space.
        dpr: Device pixel ratio of that screen.

    Returns:
        A rectangle whose width and height are never negative, whichever way the drag went.
    """
```

## Repository map

```text
src/anypoach/   analysis, brief storage, MCP server, pointer trace, capture, window, Chrome bridge and extension
tests/          unit, end-to-end, and window tests, plus golden files
tools/          benchmark and jitter measurement scripts
docs/           design, plan, and measured baseline (docs/superpowers)
```
