"""The settings dialog, offscreen: storage numbers, clearing, copying and the update check."""
import time

import pytest
from PySide6.QtWidgets import QApplication

from anypoach.setup import setup_text
from anypoach.ui.settings import SettingsDialog, megabytes


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def wait_until(app, condition):
    deadline = time.time() + 3
    while not condition() and time.time() < deadline:
        app.processEvents()
        time.sleep(0.01)
    return condition()


def folders(tmp_path):
    temp, cache = tmp_path / "temp", tmp_path / "cache"
    (temp / "anypoach-abc123").mkdir(parents=True)
    cache.mkdir()
    return temp, cache, temp / "anypoach-abc123"


def test_it_reports_unused_frames_and_clears_only_those(app, tmp_path):
    temp, cache, folder = folders(tmp_path)
    old, kept = folder / "a-start-0ms.png", folder / "b-start-0ms.png"
    old.write_bytes(b"x" * 2_000_000)
    kept.write_bytes(b"y" * 1_000_000)
    dialog = SettingsDialog(lambda: [str(kept)], temp=temp, cache=cache)
    assert "3.0 MB" in dialog.storage_label.text() and "2.0 MB is unused" in dialog.storage_label.text()
    dialog.clear_button.click()
    assert not old.exists() and kept.exists() and not dialog.clear_button.isEnabled()


def test_a_corrupt_brief_disables_clearing_instead_of_guessing(app, tmp_path):
    temp, cache, _ = folders(tmp_path)
    (cache / "active-brief.json").write_text("{broken")
    dialog = SettingsDialog(list, temp=temp, cache=cache)
    assert "Could not measure" in dialog.storage_label.text() and not dialog.clear_button.isEnabled()


def test_setup_buttons_copy_the_matching_command(app, tmp_path):
    temp, cache, _ = folders(tmp_path)
    dialog = SettingsDialog(list, temp=temp, cache=cache)
    dialog.copy_setup("codex")
    assert QApplication.clipboard().text() == setup_text("codex")


def test_the_update_check_runs_only_on_click_and_shows_its_answer(app, tmp_path):
    temp, cache, _ = folders(tmp_path)
    calls = []
    dialog = SettingsDialog(list, temp=temp, cache=cache, check=lambda: calls.append(1) or "AnyPoach 9 is available")
    assert calls == [] and "only when you ask" in dialog.update_label.text()
    dialog.update_button.click()
    assert wait_until(app, lambda: "9 is available" in dialog.update_label.text())
    assert calls == [1] and dialog.update_button.isEnabled()


def test_megabytes_is_short():
    assert megabytes(1_500_000) == "1.5 MB"
