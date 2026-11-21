# AnyPoach repository guidance

## Project shape

- `src/anypoach/analysis` decodes video and images in one process (PyAV, numpy): keyframes, palette, motion timing.
- `src/anypoach/brief` writes and reads shared briefs and cleans up temporary media.
- `src/anypoach/mcp` is the stdio MCP server (`anypoach-mcp`).
- `src/anypoach/capture` and `src/anypoach/pointer` record a screen area and sample the pointer.
- `src/anypoach/ui` is the PySide6 window; `ui/controller.py` holds the Qt-free flow it delegates to.

## Working rules

- Read the relevant module and its tests before changing behavior.
- Treat recordings, screenshots, and keyframes as private local data. Do not add network transmission, analytics, or persistent retention without an explicit product decision.
- MCP stdout is the protocol channel. Never print to stdout in `anypoach.mcp` or anything it imports; use stderr.
- Poll the pointer for position and button state only. No global input hooks, no keyboard capture.
- Keep the window operable by keyboard and give every control an accessible name.
- Update `README.md` and `CONTRIBUTING.md` when commands, capabilities, permissions, or data handling change.
- Do not commit build output, virtual environments, or temporary captures.
- Keep commits atomic and use Conventional Commit subjects (`type(scope): summary`). Never combine unrelated implementation and documentation changes in one commit.

## Useful commands

```sh
uv sync --group dev --extra ui
uv run pytest
uv run ruff check src tests tools
uv run anypoach
```
