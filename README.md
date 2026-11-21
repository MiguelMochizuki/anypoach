# AnyPoach

Record a UI interaction on Windows, Linux, or macOS and hand it to your coding assistant as evidence it can read: keyframes, color palette, motion timing, and a local pointer trace with your notes.

AnyPoach captures a screen area, samples the pointer (position and button state only), extracts the moments that matter, and writes a short-lived brief that an assistant reads through a local MCP server. Everything stays on your machine.

## Status

Early and in progress. Verified so far: analysis, brief storage, the MCP server, pointer-trace logic, and recording, all covered by automated tests on Linux. Not yet verified on real desktops: screen capture and the window on Windows and Linux X11. Not done: comment editor, global shortcut, Wayland capture, macOS pointer sampling. See [CONTRIBUTING.md](CONTRIBUTING.md) for the manual checks.

## Run it

Requires Python 3.11 or newer and [uv](https://docs.astral.sh/uv/).

```sh
uv sync --extra ui    # PySide6 for the window, mss for screen capture
uv run anypoach       # choose an area, record, stop, copy the prompt
```

Paste the copied prompt into your assistant. It asks the assistant to read the brief through the MCP server below.

## Connect an assistant

```sh
claude mcp add anypoach -- uv run --project /absolute/path/to/anypoach anypoach-mcp
```

Any MCP client that can launch a stdio command works the same way. The server offers four tools:

| Tool | Purpose |
| --- | --- |
| `anypoach_read_brief` | Read the latest shared brief, or one by `briefId`: keyframes, palette, timing, pointer trace, notes. |
| `anypoach_read_moment` | Read one frame of the shared recording at a timestamp, plus frames after drag releases. |
| `anypoach_inspect` | Analyze a local `.mp4` or `.mov` file. |
| `anypoach_inspect_image` | Analyze a local still image. |

## Privacy

No network access, telemetry, or audio. Recordings, frames, and briefs are private local files (owner-only permissions) and briefs expire after 24 hours. The pointer is polled for position and button state only; there are no global input hooks and no keyboard capture. On Wayland there is no global pointer position, so the trace is reported as unavailable.

## Develop

```sh
uv sync --group dev --extra ui
uv run pytest
uv run ruff check src tests tools
```

Details, conventions, and the manual checks for each platform are in [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
