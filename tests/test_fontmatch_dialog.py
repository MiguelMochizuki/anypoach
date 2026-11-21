"""The font matching dialog, offscreen, with fake fonts."""
import numpy as np
import pytest
from PySide6.QtCore import QRect
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from anypoach.pointer.trace import Rect
from anypoach.ui.fontmatch import FontMatchDialog, gray_array, render_text
from tests.test_ui_controller import make


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def bars(width, gap, bar):
    image = np.full((30, width), 255.0)
    for x in range(10, width - 10, gap):
        image[5:25, x:x + bar] = 0
    return image


@pytest.fixture
def setup(app, tmp_path):
    controller = make(tmp_path)
    controller.choose_region(Rect(0, 0, 40, 40))
    controller.screenshot()
    path = tmp_path / "page.png"
    page = np.full((200, 400), 255, np.uint8)
    page[50:80, 30:230] = bars(200, 20, 8).astype(np.uint8)  # the "line of text" is the same drawing as the Thick font
    image = QImage(page.data, 400, 200, 400, QImage.Format.Format_Grayscale8).copy()
    image.save(str(path))
    return controller, str(path)


def test_the_closest_family_is_listed_first_and_used(setup):
    controller, path = setup
    fakes = {"Thin": bars(200, 20, 2), "Thick": bars(200, 20, 8), "Sparse": bars(200, 50, 8)}
    dialog = FontMatchDialog(controller, path, families=lambda: list(fakes), render=lambda family, text: fakes[family])
    dialog.text.setText("Hello")
    dialog.select_box(QRect(30, 50, 200, 30))
    matches = dialog.find()
    assert matches[0].family == "Thick" and dialog.results.item(0).text().startswith("Thick")
    dialog.use()
    assert controller.font_match["family"] == "Thick" and controller.font_match["text"] == "Hello"
    x, _, w, h = controller.font_match["region"]
    assert x == pytest.approx(30 / 400) and w == pytest.approx(200 / 400) and h == pytest.approx(30 / 200)
    dialog.clear()
    assert controller.font_match is None


def test_it_asks_for_a_selection_and_text_before_searching(setup):
    controller, path = setup
    dialog = FontMatchDialog(controller, path, families=lambda: ["A"], render=lambda f, t: np.zeros((9, 9)))
    assert dialog.find() == [] and "Drag over" in dialog.status.text()
    dialog.use()
    assert "Find fonts" in dialog.status.text()


def test_the_real_renderer_returns_a_grayscale_array_and_the_gray_helper_copies(app):
    rendered = render_text("Sans Serif", "Hello")
    assert rendered.ndim == 2 and rendered.dtype == np.uint8 and rendered.shape[0] > 10
    image = QImage(5, 4, QImage.Format.Format_Grayscale8)
    image.fill(QColor("white"))
    assert gray_array(image).shape == (4, 5)
