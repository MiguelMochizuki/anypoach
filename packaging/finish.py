"""Smoke-test a PyInstaller build and zip it: `python packaging/finish.py dist/AnyPoach AnyPoach-v0.15.0-linux.zip`."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "smoke", "version": "1"}}}


def exe(folder: Path, name: str) -> Path:
    """The packaged program `name` in `folder` (with `.exe` on Windows)."""
    return folder / (name + (".exe" if sys.platform == "win32" else ""))


def smoke(folder: Path) -> None:
    """Fail unless the packaged MCP server answers `initialize` and the setup helper names the server beside it."""
    setup = subprocess.run([str(exe(folder, "anypoach-setup")), "json"], capture_output=True, text=True, timeout=60)
    entry = json.loads(setup.stdout)["mcpServers"]["anypoach"]["command"]
    assert Path(entry) == exe(folder, "anypoach-mcp"), f"setup points at {entry}"
    server = subprocess.run([str(exe(folder, "anypoach-mcp"))], input=json.dumps(INIT) + "\n", capture_output=True,
                            text=True, timeout=60)
    reply = json.loads(server.stdout.splitlines()[0])
    assert reply["result"]["serverInfo"]["name"] == "anypoach", reply


if __name__ == "__main__":
    folder, target = Path(sys.argv[1]), Path(sys.argv[2])
    smoke(folder)
    shutil.make_archive(str(target.with_suffix("")), "zip", folder.parent, folder.name)
    print(target)
