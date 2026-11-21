"""Shared fixtures: the synthetic clips used across the suites."""
import pytest

from tests.fixtures import build_all


@pytest.fixture(scope="session")
def clips(tmp_path_factory):
    return build_all(tmp_path_factory.mktemp("clips"))


@pytest.fixture(scope="session", autouse=True)
def _delete_widgets_before_qt_shuts_down():
    """Delete leftover top-level widgets while the QApplication still exists: destroying them afterwards, at
    interpreter exit, crashes PySide6 (exit status 135 or 139) even though every test passed."""
    yield
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        return
    app = QApplication.instance()
    if app is not None:
        for widget in app.topLevelWidgets():
            widget.deleteLater()
        app.processEvents()
