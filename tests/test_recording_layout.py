from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QScrollArea

from macroflow.config import Settings
from macroflow.models import Event
from macroflow.ui.main_window import MainWindow
from macroflow.ui.playback_panel import PAUSED, RUNNING


def test_fixed_recording_skips_countdown_without_changing_timed_preference(qapp, tmp_path, monkeypatch):
    window = MainWindow(Settings(tmp_path), enable_hooks=False)
    window.new_macro(name="Instantánea")
    calls = []
    monkeypatch.setattr(window.engine, "record", lambda **options: calls.append(options))
    window.record_countdown.setValue(3)
    window.record_mode.setCurrentIndex(window.record_mode.findData("fixed"))
    assert window.record_countdown_row.isHidden() and window.record_countdown_label.isHidden()
    window.start_recording()
    assert calls[-1]["seconds"] == 0 and window.capture_dialog.isVisible()
    window.capture_dialog.hide()
    window.record_mode.setCurrentIndex(window.record_mode.findData("timed"))
    assert not window.record_countdown_row.isHidden()
    window.start_recording()
    assert calls[-1]["seconds"] == 3 and window.record_countdown.value() == 3
    window.close()


def test_compact_macro_and_recorder_fit_without_scrolling(qapp, tmp_path, monkeypatch):
    from pathlib import Path
    QFontDatabase.addApplicationFont(str(Path(__file__).resolve().parents[1] / "resources/Inter.ttf"))
    old_font = qapp.font()
    qapp.setFont(QFont("Inter", 10))
    monkeypatch.setattr("macroflow.ui.main_window.application_windows", lambda: [(123, 42, "Ventana larga " * 20)])
    window = MainWindow(Settings(tmp_path), enable_hooks=False)
    try:
        window.new_macro(name="Pokebola")
        window.editor.insert([Event("key_down", key="key:up"), Event("key_up", key="key:up")])
        window.resize(980, 680)
        window.show()
        for selected in (0, 1):
            window.target_combo.setCurrentIndex(selected)
            for page in (1, 2):
                window.change_page(page)
                qapp.processEvents()
                root = window.pages.widget(page)
                for scroll in (root, *root.findChildren(QScrollArea)):
                    if isinstance(scroll, QScrollArea):
                        assert scroll.horizontalScrollBar().maximum() == 0
                        assert scroll.verticalScrollBar().maximum() == 0
                        assert scroll.widget().width() <= scroll.viewport().width()
                assert window.record_start.isVisible() if page == 1 else window.play_start.isVisible()
    finally:
        window.close()
        qapp.setFont(old_font)


def test_recording_indicator_colors_stop_and_picker(qapp, tmp_path):
    window = MainWindow(Settings(tmp_path), enable_hooks=False)
    indicator = window.record_indicator
    assert indicator.size().toTuple() == (460, 76)
    indicator.update_phase("running")
    assert indicator.text.text() == "GRABACIÓN EN EJECUCIÓN" and indicator.stop.accent == RUNNING
    indicator.update_phase("paused")
    assert indicator.text.text() == "GRABACIÓN EN PAUSA" and indicator.stop.accent == PAUSED
    assert indicator.stop.text() == "Detener"
    window.picking = True
    indicator.show_picker()
    indicator.stop.click()
    assert not window.picking
    window.close()
