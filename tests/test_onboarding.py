"""First-run state, the platform note and the welcome dialog."""
import pytest
from PySide6.QtWidgets import QApplication, QPushButton

from anypoach.bridge.control import BridgeController
from anypoach.bridge.evidence import EvidenceStore
from anypoach.onboarding import mark_done, needs_onboarding, platform_note
from anypoach.ui.onboarding import POINTS, OnboardingDialog
from anypoach.ui.settings import SettingsDialog


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_the_tour_is_pending_until_it_has_been_marked(tmp_path):
    marker = tmp_path / "deep" / "onboarded"
    assert needs_onboarding(marker)
    mark_done(marker)
    assert not needs_onboarding(marker)


def test_a_failure_to_remember_is_silent(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    mark_done(blocker / "onboarded")  # the parent is a file: nothing raised
    assert needs_onboarding(blocker / "onboarded")


def test_the_platform_note_names_the_one_requirement():
    assert "Screen Recording" in platform_note("darwin", "")
    assert "portal" not in platform_note("linux", "x11") and platform_note("linux", "x11") == ""
    assert "PipeWire" in platform_note("linux", "wayland") and platform_note("win32", "") == ""


def test_without_chrome_the_tour_is_one_step_and_done_closes_it(app):
    dialog = OnboardingDialog(None, note="")
    assert dialog.pages.count() == 1 and dialog.step.text() == "Step 1 of 1" and dialog.next_button.text() == "Done"
    dialog.show()
    dialog.next()
    assert not dialog.isVisible()


def test_with_chrome_the_second_step_shows_the_code_and_can_be_skipped(app, tmp_path):
    bridge = BridgeController(EvidenceStore(), cache=tmp_path)
    dialog = OnboardingDialog(bridge, note="Allow it.")
    assert dialog.step.text() == "Step 1 of 2" and len(POINTS) == 4
    dialog.next()
    assert dialog.step.text() == "Step 2 of 2 · Optional" and dialog.code_field.text() == bridge.code
    assert dialog.skip_button.isVisibleTo(dialog) and dialog.next_button.text() == "Done"


def test_settings_offers_the_tour_only_when_given_one(app, tmp_path):
    calls = []
    with_tour = SettingsDialog(list, temp=tmp_path, cache=tmp_path, on_tour=lambda: calls.append(1))
    button = next(b for b in with_tour.findChildren(QPushButton) if b.text() == "Welcome tour…")
    button.click()
    without = SettingsDialog(list, temp=tmp_path, cache=tmp_path)
    assert calls == [1] and not [b for b in without.findChildren(QPushButton) if b.text() == "Welcome tour…"]
