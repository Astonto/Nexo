from PySide6.QtCore import QItemSelectionModel, QPoint, Qt
from PySide6.QtTest import QTest

from macroflow.config import Settings
from macroflow.models import Event
from macroflow.ui.dialogs import CreateMacroDialog
from macroflow.ui.editor import Editor
from macroflow.ui.main_window import MainWindow
from macroflow.ui.playback_panel import PAUSED, RUNNING, PlaybackPanel


def test_home_navigation_counts_and_rotating_message(qapp, tmp_path):
    window = MainWindow(Settings(tmp_path), enable_hooks=False)
    window.show()
    window.new_macro(name="Una")
    window.current.category = "Trabajo"
    window.new_macro(name="Dos")
    window.change_page(0)
    qapp.processEvents()
    assert window.home.macros.text() == "02" and window.home.categories.text() == "02"
    assert not window.macro_toolbar.isVisible() and not window.title.isVisible()
    assert window.home.message_timer.interval() == 7000
    original = window.home.message.text()
    window.home.advance_message()
    QTest.qWait(500)
    assert window.home.message.text() != original
    for i, navigation in enumerate(window.nav):
        navigation.click()
        qapp.processEvents()
        assert window.pages.currentIndex() == i and navigation.isChecked()
        assert sum(button.isChecked() for button in window.nav) == 1
        assert not window.stop_all.isVisible()
    window.home.record.click()
    assert window.pages.currentIndex() == 1 and not window.engine.busy
    window.open_settings_tab(2)
    assert window.pages.currentIndex() == 6 and window.settings_tabs.currentIndex() == 2
    window.close()


def test_home_types_letters_and_pauses_when_hidden_or_busy(qapp, tmp_path):
    window = MainWindow(Settings(tmp_path), enable_hooks=False)
    window.show()
    window.change_page(0)
    qapp.processEvents()
    home = window.home
    home.advance_message()
    target = home.MESSAGES[home.message_index]
    QTest.qWait(140)
    assert 0 < len(home.message.text()) < len(target)
    assert target.startswith(home.message.text())
    QTest.qWait(1300)
    assert home.message.text() == target and not home.typing_timer.isActive()
    window.change_page(1)
    assert not home.message_timer.isActive() and not home.typing_timer.isActive()
    index = home.message_index
    home.advance_message()
    assert home.message_index == index
    window.change_page(0)
    assert home.message_timer.isActive()
    window.engine.task, window.engine.phase = "play", "paused"
    home.refresh()
    assert not home.message_timer.isActive() and not home.typing_timer.isActive()
    home.advance_message()
    assert home.message_index == index
    window.engine.task, window.engine.phase = "idle", "idle"
    home.refresh()
    assert home.message_timer.isActive()
    window.close()


def test_creation_wizard_cancel_validation_and_modes(qapp):
    wizard = CreateMacroDialog()
    wizard.advance()
    assert wizard.steps.currentIndex() == 0 and wizard.error.text()
    wizard.name.setText("Enviar respuesta")
    wizard.modes.buttons()[2].click()
    wizard.advance()
    assert wizard.activation == "toggle" and wizard.steps.currentIndex() == 1
    wizard.destinations.buttons()[2].click()
    wizard.go_back()
    assert wizard.name.text() == "Enviar respuesta"
    wizard.advance()
    wizard.advance()
    assert wizard.result() == wizard.DialogCode.Accepted and wizard.destination == "editor"


def test_guided_creation_only_saves_after_confirmation(qapp, tmp_path, monkeypatch):
    window = MainWindow(Settings(tmp_path), enable_hooks=False)
    monkeypatch.setattr(CreateMacroDialog, "exec", lambda self: self.DialogCode.Rejected)
    window.new_macro()
    assert not window.macros
    def complete(dialog):
        dialog.name.setText("Atajo de trabajo")
        dialog.activation, dialog.destination = "hold", "timed"
        return dialog.DialogCode.Accepted
    monkeypatch.setattr(CreateMacroDialog, "exec", complete)
    window.new_macro()
    assert len(window.macros) == 1 and window.current.name == "Atajo de trabajo"
    assert window.current.activation == "hold" and not window.current.enabled
    assert window.pages.currentIndex() == 1 and window.record_mode.currentData() == "timed"
    assert not window.engine.busy
    window.close()


def test_blocks_and_detail_share_selection_edits_and_history(qapp):
    editor = Editor()
    editor.resize(700, 450)
    editor.show()
    events = [Event("key_down", key="vk:65"), Event("key_up", key="vk:65"), Event("wait", .5)]
    editor.insert(events)
    qapp.processEvents()
    index = editor.model.index(1, 0)
    QTest.mouseClick(editor.visual.viewport(), Qt.MouseButton.LeftButton, pos=editor.visual.visualRect(index).center())
    assert editor.table.selected_rows() == [1]
    editor.duplicate()
    assert len(editor.model.events) == 4
    editor.model.history.undo()
    assert editor.model.events == events
    editor.view_mode.setCurrentIndex(1)
    editor.table.selectRow(2)
    editor.delete()
    assert editor.model.events == events[:2]
    editor.model.history.undo()
    assert editor.model.events == events
    assert editor.visual.model() is editor.table.model()
    editor.set_editable(False)
    editor.delete()
    assert editor.model.events == events


def test_conditional_capture_and_clicker_fields(qapp, tmp_path):
    window = MainWindow(Settings(tmp_path), enable_hooks=False)
    window.show()
    window.change_page(1)
    window.record_mode.setCurrentIndex(window.record_mode.findData("fixed"))
    assert window.fixed_interval_row.isVisible() and not window.capture_moves.isVisible()
    window.record_mode.setCurrentIndex(window.record_mode.findData("timed"))
    assert not window.fixed_interval_row.isVisible() and window.capture_moves.isVisible()
    window.change_page(3)
    window.click_kind.setCurrentIndex(window.click_kind.findData("keyboard"))
    assert window.click_key_row.isVisible() and not window.click_mouse_row.isVisible()
    window.click_kind.setCurrentIndex(window.click_kind.findData("mouse"))
    window.click_position.setCurrentIndex(window.click_position.findData("fixed"))
    assert window.coordinates_row.isVisible() and not window.click_key_row.isVisible()
    window.close()


def test_playback_panel_matches_running_and_paused_states(qapp):
    panel = PlaybackPanel()
    panel.update_phase("running", "Falsotortazo")
    panel.set_progress(4, 12, 0, "00:00:01.812")
    panel.show()
    qapp.processEvents()
    assert panel.size().toTuple() == (450, 75)
    assert panel.title.text() == "REPRODUCIENDO"
    assert panel.macro_name.text() == "Falsotortazo"
    assert "4 / 12" in panel.detail.text() and "0 rep. completadas" in panel.detail.text()
    assert panel.progress_ratio == 4 / 12
    assert panel.pause.text() == "Pausar" and panel.pause.emphasis and panel.pause.accent == RUNNING
    assert panel.stop.stop_control and panel.stop.accessibleName() == "Detener reproducción"
    assert all(control.focusPolicy() == Qt.FocusPolicy.NoFocus for control in
               (panel.previous, panel.pause, panel.next, panel.restart, panel.stop))
    panel.update_phase("paused", "Falsotortazo")
    assert panel.title.text() == "EN PAUSA"
    assert panel.pause.text() == "Reanudar" and panel.pause.accent == PAUSED
    assert panel.progress_accent == PAUSED
    original_position = panel.pos()
    panel.begin_drag(panel.pos() + panel.title.pos())
    panel.drag_to(panel.pos() + panel.title.pos() + QPoint(-37, 24))
    panel.end_drag()
    assert panel.pos() == original_position + QPoint(-37, 24)
    assert panel.drag_origin is None
    panel.update_phase("countdown", "Falsotortazo")
    assert panel.title.text() == "PREPARANDO" and not panel.pause.isEnabled()
    panel.close()
