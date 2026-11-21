"""The .mcpb bundle: layout and manifest, checked against the parts of the MCPB spec we rely on."""
import json
import tomllib
import zipfile
from pathlib import Path

import pytest

from tools.build_mcpb import ROOT, build, manifest


@pytest.fixture(scope="module")
def bundle(tmp_path_factory):
    return zipfile.ZipFile(build(tmp_path_factory.mktemp("mcpb") / "AnyPoach.mcpb"))


def test_the_manifest_sits_at_the_root_and_has_the_required_fields(bundle):
    data = json.loads(bundle.read("manifest.json"))
    for key in ("manifest_version", "name", "version", "description", "author", "server"):
        assert data[key]
    assert data["author"]["name"] and data["server"] == {"type": "uv", "entry_point": "src/server.py"}


def test_the_version_follows_the_package(bundle):
    assert json.loads(bundle.read("manifest.json"))["version"] == tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]


def test_the_uv_layout_has_pyproject_entry_point_and_the_package_but_no_environment(bundle):
    names = set(bundle.namelist())
    assert {"pyproject.toml", "src/server.py", "src/anypoach/mcp/server.py", "icon.png"} <= names
    assert not [n for n in names if "__pycache__" in n or n.endswith(".pyc") or "/lib/" in n or "venv" in n]
    assert b"anypoach.mcp.server" in bundle.read("src/server.py")


def test_the_manifest_lists_the_four_tools_the_server_registers():
    source = (ROOT / "src/anypoach/mcp/server.py").read_text()
    assert all(tool["name"] in source for tool in manifest()["tools"]) and len(manifest()["tools"]) == 4


def test_the_output_path_is_where_it_was_asked(tmp_path):
    assert build(tmp_path / "x.mcpb") == Path(tmp_path / "x.mcpb")
