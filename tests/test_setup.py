"""The assistant setup text."""
import json

import pytest

from anypoach.setup import launcher, main, setup_text

CMD = ["/opt/bin/anypoach-mcp"]


def test_claude_and_codex_get_their_mcp_add_command():
    assert setup_text("claude", CMD) == "claude mcp add anypoach -- /opt/bin/anypoach-mcp"
    assert setup_text("codex", CMD) == "codex mcp add anypoach -- /opt/bin/anypoach-mcp"


def test_a_path_with_spaces_is_quoted_and_json_splits_command_and_args():
    command = ["/my py/python", "-m", "anypoach.mcp.server"]
    assert setup_text("claude", command).endswith("-- '/my py/python' -m anypoach.mcp.server")
    entry = json.loads(setup_text("json", command))["mcpServers"]["anypoach"]
    assert entry == {"command": "/my py/python", "args": ["-m", "anypoach.mcp.server"]}


def test_an_unknown_client_is_a_clean_error(capsys):
    with pytest.raises(ValueError):
        setup_text("vim", CMD)
    assert main(["vim"]) == 2 and "Unknown client" in capsys.readouterr().err


def test_launcher_always_gives_something_runnable():
    assert launcher()[0]
