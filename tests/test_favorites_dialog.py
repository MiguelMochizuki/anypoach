"""The favorites dialog, offscreen, with stand-in file pickers."""
import pytest
from PySide6.QtWidgets import QApplication

from anypoach.favorites import FavoriteStore
from anypoach.pointer.trace import Rect
from anypoach.ui.favorites import FavoritesDialog
from tests.test_ui_controller import make


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def controller(tmp_path):
    controller = make(tmp_path, favorites=FavoriteStore(tmp_path / "fav"))
    controller.choose_region(Rect(10, 10, 160, 90))
    controller.screenshot()
    controller.save_favorite("Card")
    return controller


def test_the_list_shows_the_favorite_and_copy_puts_a_prompt_on_the_clipboard(app, controller):
    dialog = FavoritesDialog(controller)
    assert dialog.list.count() == 1 and dialog.list.item(0).text() == "Card" and not dialog.list.item(0).icon().isNull()
    dialog.copy_handoff()
    assert "anypoach_read_brief" in QApplication.clipboard().text() and "copied" in dialog.status.text()


def test_export_import_and_delete(app, controller, tmp_path):
    out = tmp_path / "out.anypoach"
    dialog = FavoritesDialog(controller, ask_save=lambda name: str(out), ask_open=lambda: str(out))
    dialog.export()
    assert out.is_file()
    dialog.import_file()
    assert dialog.list.count() == 2
    dialog.delete()
    assert dialog.list.count() == 1


def test_a_bad_import_and_an_empty_selection_are_messages(app, controller, tmp_path):
    bad = tmp_path / "bad.anypoach"
    bad.write_text("{}")
    dialog = FavoritesDialog(controller, ask_open=lambda: str(bad))
    dialog.import_file()
    assert "Could not import" in dialog.status.text() and dialog.list.count() == 1
    controller.favorites.delete(controller.favorites.list()[0].id)
    dialog.refresh()
    dialog.copy_handoff()
    assert "Choose a favorite" in dialog.status.text()
