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

No network, telemetry, or audio. Only pointer position and button state are sampled, by polling, with no global hooks. Briefs and archives live in the per-OS cache directory (`~/Library/Caches/AnyPoach` on macOS, `~/.cache/AnyPoach` on Linux, `%LOCALAPPDATA%\AnyPoach\Cache` on Windows; `ANYPOACH_CACHE_DIR` overrides it for tests) and expire after 24 hours. On POSIX they use `0700` and `0600`. On Windows the same files get an ACL limited to the current user through `icacls`; that path has no local test and relies on CI. The Windows pointer source needs a per-monitor DPI-aware process, or coordinates arrive scaled. On Wayland there is no global pointer position, so the trace reports `available: false`.

## Manual checks

Before relying on a change to capture or the window, check by hand on Windows and on Linux X11: the AnyPoach window does not appear in the video (on Windows it is excluded with `SetWindowDisplayAffinity`; elsewhere it is hidden while recording and a tray menu stops the recording, with a 30 s limit), the selection overlay is not recorded, the cursor and click ring are drawn where the pointer was, and the brief shows up in the OS cache directory. On Wayland the screen cannot be captured with `mss` yet. `tools/bench.py` and `tools/jitter.py` print the timings recorded in `docs/superpowers/baseline.md`.

`tools/bench.py` and `tools/jitter.py` print the timings recorded in `docs/superpowers/baseline.md`.

## Repository map

```text
src/anypoach/   analysis, brief storage, MCP server, pointer trace, capture, window
tests/          unit, end-to-end, and window tests, plus golden files
tools/          benchmark and jitter measurement scripts
docs/           design, plan, and measured baseline (docs/superpowers)
```
