"""Build `AnyPoach.mcpb`, the Claude Desktop extension that runs the MCP server with `uv`.

The bundle follows the `uv` server type of the MCPB manifest spec: `manifest.json` at the root, a `pyproject.toml`
whose dependencies the host installs, and the server's source under `src/`. Usage: `uv run python tools/build_mcpb.py
[output.mcpb]`.
"""
from __future__ import annotations

import json
import sys
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHIM = '''"""Entry point of the MCPB bundle: runs the AnyPoach MCP server."""
from anypoach.mcp.server import main

if __name__ == "__main__":
    main()
'''


def manifest(root: Path = ROOT) -> dict:
    """The MCPB manifest for the project at `root`, with name, version and description taken from `pyproject.toml`."""
    project = tomllib.loads((root / "pyproject.toml").read_text())["project"]
    return {
        "manifest_version": "0.4",
        "name": "anypoach",
        "display_name": "AnyPoach",
        "version": project["version"],
        "description": project["description"],
        "author": {"name": "Miguel Mochizuki", "url": "https://github.com/MiguelMochizuki/anypoach"},
        "repository": {"type": "git", "url": "https://github.com/MiguelMochizuki/anypoach.git"},
        "license": project["license"],
        "icon": "icon.png",
        "server": {"type": "uv", "entry_point": "src/server.py"},
        "tools": [{"name": name} for name in
                  ("anypoach_read_brief", "anypoach_read_moment", "anypoach_inspect", "anypoach_inspect_image")],
        "compatibility": {"runtimes": {"python": ">=3.11"}},
    }


def build(output: Path, root: Path = ROOT) -> Path:
    """Write the bundle to `output` and return it."""
    package = root / "src" / "anypoach"
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("manifest.json", json.dumps(manifest(root), indent=2))
        bundle.write(root / "pyproject.toml", "pyproject.toml")
        bundle.write(package / "chrome_extension" / "icon.png", "icon.png")
        bundle.writestr("src/server.py", SHIM)
        for file in sorted(package.rglob("*")):
            if file.is_file() and "__pycache__" not in file.parts and file.suffix != ".pyc":
                bundle.write(file, f"src/anypoach/{file.relative_to(package).as_posix()}")
    return output


if __name__ == "__main__":
    target = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "AnyPoach.mcpb")
    print(build(target))
