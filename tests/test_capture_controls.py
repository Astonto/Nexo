from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from macroflow.config import Settings
from macroflow.ui.main_window import MainWindow


def test_modal_capture_accepts_pause_resume_and_stop_from_both_surfaces(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr("macroflow.recording.Recorder.start", lambda self: None)
    window = MainWindow(Settings(tmp_path), enable_hooks=False)
    window.show()
    window.new_macro(name="Controles de captura")
    window.record_mode.setCurrentIndex(window.record_mode.findData("fixed"))
    window.start_recording()
    QTest.qWait(100)
    dialog = window.capture_dialog
    indicator = window.record_indicator
    assert QApplication.activeModalWidget() is dialog
    assert indicator.parentWidget() is dialog
    assert indicator.windowHandle().transientParent() is dialog.windowHandle()
    assert indicator.isVisible() and indicator.pause.isVisible()
    QTest.mouseClick(dialog.pause_button, Qt.MouseButton.LeftButton)
    QTest.qWait(30)
    assert window.engine.phase == "paused"
    assert dialog.pause_button.text() == "Reanudar"
    QTest.mouseClick(indicator.pause, Qt.MouseButton.LeftButton)
    QTest.qWait(30)
    assert window.engine.phase == "running"
    QTest.mouseClick(indicator.pause, Qt.MouseButton.LeftButton)
    QTest.qWait(30)
    assert window.engine.phase == "paused"
    QTest.mouseClick(dialog.pause_button, Qt.MouseButton.LeftButton)
    QTest.qWait(30)
    assert window.engine.phase == "running"
    QTest.mouseClick(indicator.stop, Qt.MouseButton.LeftButton)
    QTest.qWait(30)
    assert dialog.reviewing and window.engine.phase == "paused"
    assert dialog.finish_button.isEnabled()
    QTest.mouseClick(dialog.pause_button, Qt.MouseButton.LeftButton)
    QTest.qWait(30)
    assert not dialog.reviewing and window.engine.phase == "running"
    QTest.mouseClick(dialog.review_stop, Qt.MouseButton.LeftButton)
    QTest.qWait(30)
    assert dialog.reviewing and dialog.finish_button.isEnabled()
    QTest.mouseClick(dialog.finish_button, Qt.MouseButton.LeftButton)
    window.engine.thread.join(2)
    qapp.processEvents()
    assert not window.engine.busy and not dialog.isVisible()
    window.attach_record_indicator(None)
    indicator.show_picker()
    assert indicator.parentWidget() is None and indicator.pause.isHidden()
    window.close()
