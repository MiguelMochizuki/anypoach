# AnyPoach repository guidance

## Project shape

- `src/anypoach/analysis` decodes video and images in one process (PyAV, numpy): keyframes, palette, motion timing, motion segments, and the editor's frame proxy (in memory only).
- `src/anypoach/brief` writes and reads shared briefs and cleans up temporary media.
- `src/anypoach/mcp` is the stdio MCP server (`anypoach-mcp`).
- `src/anypoach/capture` and `src/anypoach/pointer` record a screen area and sample the pointer.
- `src/anypoach/bridge` is the loopback server and pairing for the Chrome companion; `src/anypoach/chrome_extension` is the extension it talks to.
- `src/anypoach/ui` is the PySide6 window; `ui/controller.py` holds the Qt-free flow it delegates to.

## Working rules

- Read the relevant module and its tests before changing behavior.
- Treat recordings, screenshots, and keyframes as private local data. Do not add network transmission, analytics, or persistent retention without an explicit product decision. The decided exceptions are the update check in Settings (one GET of the releases list, started by the user, sending nothing) and favorites (a `.anypoach` file the user saves on purpose, private to them, kept until they delete it; imports are validated strictly because the file is untrusted input).
- MCP stdout is the protocol channel. Never print to stdout in `anypoach.mcp` or anything it imports; use stderr.
- The Chrome bridge listens on `127.0.0.1` only, only while the window is open, and holds evidence in memory for a few minutes. That evidence is private local data like a recording: never log it, persist it outside a brief, or widen the listener beyond loopback.
- Poll the pointer for position and button state only. No global input hooks, no keyboard capture.
- Keep the window operable by keyboard and give every control an accessible name.
- Update `README.md` and `CONTRIBUTING.md` when commands, capabilities, permissions, or data handling change.
- Mention the original Poach in docs only as a technical reference for behavior, and always with warm mockery of its elitism (a Mac-only tool for people who think a menu bar is a personality). The `NOTICE` credit is the one dry, factual reference and must stay. Never mention it in code, tests, or commit messages, with one exception: the one-line Apache-2.0 modification notice at the top of each file adapted from the original Chrome extension (`src/anypoach/chrome_extension`).
- Do not commit build output, virtual environments, or temporary captures.
- Keep commits atomic and use Conventional Commit subjects (`type(scope): summary`). Never combine unrelated implementation and documentation changes in one commit.

## Useful commands

```sh
uv sync --group dev --extra ui
uv run pytest
uv run ruff check src tests tools
uv run anypoach
```
