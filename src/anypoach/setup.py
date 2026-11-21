"""`anypoach-setup`: print the command that connects an assistant to the MCP server, with the right launcher."""
from __future__ import annotations

import json
import shlex
import shutil
import sys

CLIENTS = ("claude", "codex", "json")


def launcher() -> list[str]:
    """The command that starts the MCP server: the installed `anypoach-mcp` script, else this interpreter."""
    script = shutil.which("anypoach-mcp")
    return [script] if script else [sys.executable, "-m", "anypoach.mcp.server"]


def setup_text(client: str, command: list[str] | None = None) -> str:
    """The text to run (or paste) to register the server with `client`.

    Args:
        client: One of `CLIENTS`: `claude` and `codex` give their `mcp add` command, `json` the `mcpServers` entry.
        command: The launcher argv; defaults to `launcher()`.

    Raises:
        ValueError: If `client` is not one of `CLIENTS`.
    """
    command = command or launcher()
    if client == "json":
        return json.dumps({"mcpServers": {"anypoach": {"command": command[0], "args": command[1:]}}}, indent=2)
    if client not in ("claude", "codex"):
        raise ValueError(f"Unknown client {client!r}; choose one of {', '.join(CLIENTS)}")
    return f"{client} mcp add anypoach -- {shlex.join(command)}"


def main(argv: list[str] | None = None) -> int:
    """Print the setup text for the client named in `argv` (default `claude`); returns the exit status."""
    args = sys.argv[1:] if argv is None else argv
    try:
        print(setup_text(args[0] if args else "claude"))
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
