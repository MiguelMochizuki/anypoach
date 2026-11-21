"""The palette strip, offscreen, with a stand-in color picker."""
import pytest
from PySide6.QtWidgets import QApplication, QPushButton

from anypoach.pointer.trace import Rect
from anypoach.ui.palette import PaletteEditor
from tests.test_ui_controller import make


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def ready(tmp_path):
    controller = make(tmp_path)
    controller.choose_region(Rect(10, 10, 160, 90))
    controller.screenshot()
    controller.set_palette(["#111111", "#222222", "#333333"])
    return controller


def test_hidden_without_a_result_and_one_swatch_per_color_with_one(app, tmp_path):
    editor = PaletteEditor(ready(tmp_path))
    names = [b.accessibleName() for b in editor.findChildren(QPushButton)]
    assert names.count("Palette color #111111") == 1 and "Remove #333333" in names and "Add color" in names


def test_edit_remove_add_and_reset_go_through_the_controller(app, tmp_path):
    controller = ready(tmp_path)
    editor = PaletteEditor(controller, pick=lambda current: "#abcdef")
    editor.edit(1)
    assert controller.palette == ["#111111", "#abcdef", "#333333"]
    editor.remove(0)
    editor.add()
    assert controller.palette == ["#abcdef", "#333333"]  # the added color repeats the edited one, so it is dropped
    editor.reset()
    assert controller.palette == list(controller.result.palette)


def test_a_cancelled_picker_and_the_last_color_change_nothing(app, tmp_path):
    controller = ready(tmp_path)
    editor = PaletteEditor(controller, pick=lambda current: None)
    editor.edit(0)
    editor.add()
    assert controller.palette == ["#111111", "#222222", "#333333"]
    controller.set_palette(["#111111"])
    PaletteEditor(controller).remove(0)
    assert controller.palette == ["#111111"]
