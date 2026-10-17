import threading
import time

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from conftest import FakeDriver
from macroflow.config import Settings
from macroflow.models import Event, ValidationError
from macroflow.playback import RunControl, TargetDriver, play_events
from macroflow.ui.main_window import MainWindow


def test_sections_keep_window_geometry_and_recording_selection(qapp, tmp_path):
    window = MainWindow(Settings(tmp_path), enable_hooks=False)
    window.show()
    window.new_macro(name="Larga")
    window.editor.insert([Event("wait", 40)])
    window.save_current()
    first = window.current.id
    window.new_macro(name="Corta")
    window.editor.insert([Event("wait", 4)])
    window.save_current()
    window.refresh_current()
    assert window.record_timer.text() == "00:00:04.000"
    window.select_macro(first)
    assert window.record_timer.text() == "00:00:40.000"
    size = window.size()
    for index in range(7):
        window.change_page(index)
        qapp.processEvents()
        assert window.size() == size
        assert not window.statusBar().isVisible()
        assert not window.stop_all.isVisible()
    window.change_page(1)
    assert window.new_button.isVisible()
    assert "Primera acción" in window.player_action.text()
    window.close()


def test_capture_stop_reviews_before_save_and_follows_last_tile(qapp, tmp_path):
    window = MainWindow(Settings(tmp_path), enable_hooks=False)
    dialog = window.capture_dialog
    dialog.begin("Revisar", .05, "F3")
    dialog.set_phase("running")
    assert not dialog.finish_button.isEnabled()
    for count in (1, 17, 38, 71, 105):
        dialog.update_events([Event("key_down", key="vk:65") for _ in range(count)])
        QTest.qWait(30)
        visible = dialog.stop_button.mapTo(dialog.scroll.viewport(), dialog.stop_button.rect().center())
        assert dialog.scroll.viewport().rect().contains(visible)
    dialog.stop_button.click()
    assert dialog.reviewing and dialog.finish_button.isEnabled()
    assert not dialog.stop_button.isEnabled()
    assert dialog.phase == "review"
    window.close()


def test_window_target_selection_shared_and_disabled_while_busy(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr("macroflow.ui.main_window.application_windows", lambda: [(123, 42, "Juego")])
    window = MainWindow(Settings(tmp_path), enable_hooks=False)
    window.target_combo.setCurrentIndex(1)
    assert window.engine.input_target.hwnd == 123
    assert window.engine.input_target.pid == 42
    window.engine.task, window.engine.phase = "play", "paused"
    window.sync_state()
    assert not window.target_combo.isEnabled()
    window.engine.task, window.engine.phase = "idle", "idle"
    window.target_combo.setCurrentIndex(0)
    assert window.engine.input_target is None
    window.close()


def test_target_loss_during_wait_releases_held_keys():
    class Target:
        allowed = True
        def allows(self, event=None):
            return self.allowed
    target = Target()
    fake = FakeDriver()
    driver = TargetDriver(fake, target)
    control = RunControl()
    control.target_guard = driver.check_target
    errors = []
    def run():
        try:
            play_events([Event("key_down", key="char:a"), Event("key_up", 30, key="char:a")], driver, control)
        except ValidationError as error:
            errors.append(error)
    worker = threading.Thread(target=run)
    worker.start()
    deadline = time.monotonic() + 2
    while not fake.held_keys and time.monotonic() < deadline:
        time.sleep(.005)
    target.allowed = False
    worker.join(2)
    assert not worker.is_alive() and errors
    assert not fake.held_keys


def test_target_blocks_dispatch_before_first_action():
    class Target:
        def allows(self, event=None):
            return False
    fake = FakeDriver()
    with pytest.raises(ValidationError):
        TargetDriver(fake, Target()).dispatch(Event("key_down", key="char:a"))
    assert not fake.events


def test_recording_ignores_other_target_and_closes_held_input(monkeypatch):
    from test_recording_ui import make_recorder
    class Target:
        allowed = True
        def allows(self, event=None):
            return self.allowed
    target = Target()
    recorder = make_recorder(monkeypatch, input_target=target)
    try:
        recorder.feed(Event("key_down", key="char:a"))
        deadline = time.monotonic() + 1
        while not recorder.held_keys and time.monotonic() < deadline:
            time.sleep(.005)
        target.allowed = False
        recorder.feed(Event("key_down", key="char:b"))
        assert not recorder.held_keys
        assert [(e.kind, e.key) for e in recorder.snapshot()] == [("key_down", "char:a"), ("key_up", "char:a")]
    finally:
        recorder.stop()


def test_capture_review_keeps_engine_paused_until_explicit_finish(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr("macroflow.recording.Recorder.start", lambda self: None)
    window = MainWindow(Settings(tmp_path), enable_hooks=False)
    window.new_macro(name="Revisión")
    window.record_target = window.current.id
    window.engine.record(seconds=0, mode="fixed")
    deadline = time.monotonic() + 1
    while window.engine.recorder is None and time.monotonic() < deadline:
        time.sleep(.005)
    dialog = window.capture_dialog
    dialog.begin("Revisión", .05, "F3")
    dialog.stop_button.click()
    assert window.engine.phase == "paused" and dialog.reviewing
    assert window.engine.busy and not window.engine.control.cancelled
    assert dialog.finish_button.isEnabled()
    dialog.pause_button.click()
    assert window.engine.phase == "running" and not dialog.reviewing
    assert not dialog.finish_button.isEnabled()
    window.stop_task()
    assert dialog.reviewing and window.engine.phase == "paused"
    dialog.finish_button.click()
    window.engine.thread.join(2)
    qapp.processEvents()
    assert not window.engine.busy and not dialog.isVisible()
    window.close()
