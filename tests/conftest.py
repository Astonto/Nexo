import os
os.environ.setdefault("NEXO_LANGUAGE", "es")
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

_QT_APP = None

@pytest.fixture(scope="session")
def qapp():
    global _QT_APP
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QApplication
    _QT_APP = app = QApplication.instance() or QApplication([])
    yield app


    app.clipboard().clear()
    for widget in app.topLevelWidgets():
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()



@pytest.fixture(autouse=True)
def dispose_test_windows(request):

    if "qapp" not in request.fixturenames:
        yield
        return
    from PySide6.QtCore import QCoreApplication, QEvent
    from shiboken6 import isValid
    app = request.getfixturevalue("qapp")
    before = set(app.topLevelWidgets())
    yield
    app.clipboard().clear()
    roots = [widget for widget in app.topLevelWidgets() if widget not in before and widget.parent() is None]

    for widget in roots:
        if isValid(widget) and hasattr(widget, "engine"):
            widget.close()
    for widget in roots:
        if isValid(widget):
            widget.hide()
            widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()

    import gc
    gc.collect()


class FakeDriver:
    def __init__(self):
        self.events = []
        self.held_keys = set()
        self.held_buttons = set()
        self.releases = 0
        self.suspensions = 0
        self.restorations = 0

    def dispatch(self, event):
        self.events.append(event)
        if event.kind == "key_down":
            self.held_keys.add(event.key)
        elif event.kind == "key_up":
            self.held_keys.discard(event.key)
        elif event.kind == "mouse_down":
            self.held_buttons.add(event.button)
        elif event.kind == "mouse_up":
            self.held_buttons.discard(event.button)

    def release_all(self):
        self.releases += 1
        self.held_keys.clear()
        self.held_buttons.clear()

    def suspend(self):
        self.suspensions += 1
        state = set(self.held_keys), set(self.held_buttons)
        self.release_all()
        return state

    def restore(self, state):
        self.restorations += 1
        self.held_keys, self.held_buttons = state

    def position(self):
        return 100, 100


@pytest.fixture
def driver():
    return FakeDriver()
