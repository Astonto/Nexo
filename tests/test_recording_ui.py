import threading
import time

from macroflow.models import Event, Macro
from macroflow.recording import Recorder


class Probe:
    reason = "Campo protegido"
    allow = True
    def allowed(self):
        return self.allow
    def close(self):
        pass


def make_recorder(monkeypatch, **kwargs):
    monkeypatch.setattr("macroflow.recording.foreground_process", lambda: -1)
    recorder = Recorder(privacy_factory=Probe, **kwargs)
    recorder.worker = threading.Thread(target=recorder._consume, daemon=True)
    recorder.worker.start()
    recorder.ready.wait(1)
    return recorder


def test_recording_reserved_controls_and_injected_events(monkeypatch):
    recorder = make_recorder(monkeypatch, reserved={0x75})
    recorder.feed(Event("key_down", key="key:ctrl_l"))
    recorder.feed(Event("key_down", key="key:alt_l"))
    recorder.feed(Event("key_down", key="key:f6"))
    recorder.feed(Event("key_up", key="key:f6"))
    recorder.feed(Event("key_up", key="key:alt_l"))
    recorder.feed(Event("key_up", key="key:ctrl_l"))
    recorder.feed(Event("key_down", key="char:z"), injected=True)
    recorder.feed(Event("key_down", key="char:a"))
    recorder.feed(Event("key_up", key="char:a"))
    recorder.stop()
    assert [e.key for e in recorder.events] == ["char:a", "char:a"]


def test_recording_pause_timing_and_release(monkeypatch):
    recorder = make_recorder(monkeypatch)
    recorder.feed(Event("key_down", key="char:a"))
    time.sleep(.03)
    recorder.pause()
    before = len(recorder.events)
    recorder.feed(Event("key_down", key="char:b"))
    time.sleep(.06)
    recorder.pause(False)
    recorder.feed(Event("key_down", key="char:c"))
    recorder.stop()
    assert before == 2
    assert not recorder.held_keys and all(e.key != "char:b" for e in recorder.events)
    assert sum(e.delay for e in recorder.events) < .09


def test_password_probe_blocks_keys(monkeypatch):
    monkeypatch.setattr(Probe, "allow", False)
    recorder = make_recorder(monkeypatch)
    recorder.feed(Event("key_down", key="char:a"))
    recorder.stop()
    assert recorder.events == []
    assert recorder.privacy_reason == "Campo protegido"


def test_move_sampling_and_mixed_drag(monkeypatch):
    recorder = make_recorder(monkeypatch, capture_moves=True)
    recorder.feed(Event("mouse_down", button="x1", x=-100, y=10))
    for x in range(100):
        recorder.feed(Event("move", x=x, y=100))
    recorder.feed(Event("scroll", x=30, y=30, dx=2, dy=-1))
    recorder.feed(Event("mouse_up", button="x1", x=90, y=100))
    recorder.stop()
    assert sum(e.kind == "move" for e in recorder.events) <= 2
    assert any(e.kind == "scroll" and e.dx == 2 for e in recorder.events)
    assert not recorder.held_buttons


def test_editor_undo_redo_reorder_and_copy(qapp):
    from macroflow.ui.editor import Editor
    editor = Editor()
    a, b, c = Event("wait", 1), Event("wait", 2), Event("wait", 3)
    editor.insert([a, b, c])
    editor.model.reorder([0, 2], 3)
    assert editor.model.events == [b, a, c]
    editor.model.history.undo()
    assert editor.model.events == [a, b, c]
    editor.model.history.redo()
    assert editor.model.events == [b, a, c]
    editor.table.selectRow(1)
    editor.copy()
    editor.paste()
    assert editor.model.events == [b, a, a, c]
    editor.model.history.undo()
    assert editor.model.events == [b, a, c]
    editor.close()


def test_main_window_pages_persistence_and_settings(qapp, tmp_path):
    from macroflow.config import Settings
    from macroflow.ui.main_window import MainWindow
    window = MainWindow(Settings(tmp_path), enable_hooks=False)
    window.show()
    qapp.processEvents()
    assert window.pages.count() == 7
    window.new_macro(name="QA secuencia")
    window.editor.insert([Event("wait", .1), Event("key_down", key="char:a"), Event("key_up", key="char:a")])
    window.current.trigger = "Ctrl+G"
    window.current.enabled = True
    window.save_current()
    assert window.writer.flush()
    assert window.library.load(window.current.id).trigger == "Ctrl+G"
    window.setting_theme.setCurrentIndex(window.setting_theme.findData("light"))
    window.save_settings()
    assert window.settings.data["theme"] == "light"
    for i in range(7):
        window.change_page(i)
        qapp.processEvents()
        assert window.pages.currentIndex() == i
    window.resize(980, 680)
    qapp.processEvents()
    assert window.centralWidget().width() <= window.width()
    window.close()
    qapp.processEvents()
    reopened = MainWindow(Settings(tmp_path), enable_hooks=False)
    assert len(reopened.macros) == 1 and reopened.current.trigger == "Ctrl+G"
    assert len(reopened.current.events) == 3
    reopened.close()


def test_recording_start_stop_controls_are_independent_and_excluded(monkeypatch):
    from macroflow.config import DEFAULT_HOTKEYS
    from macroflow.hotkeys import reserved_keys
    from macroflow.triggers import InputRouter
    calls = []
    router = InputRouter(lambda *args: calls.append(args))
    router.configure([], DEFAULT_HOTKEYS)
    router.process(0xA2, True)
    router.process(0xA4, True)
    router.process(0x75, True)
    router.process(0x75, False)
    router.process(0x74, True)
    router.process(0x74, False)
    assert calls == [("record_start", ""), ("record_stop", "")]
    recorder = make_recorder(monkeypatch, reserved=reserved_keys(DEFAULT_HOTKEYS))
    for function_key in ("f5", "f6", "f7"):
        for key in ("ctrl_l", "alt_l", function_key):
            recorder.feed(Event("key_down", key="key:" + key))
        for key in (function_key, "alt_l", "ctrl_l"):
            recorder.feed(Event("key_up", key="key:" + key))
    recorder.feed(Event("key_down", key="char:a"))
    recorder.stop()
    assert [e.key for e in recorder.events] == ["char:a", "char:a"]


def test_control_settings_and_playback_panel(qapp, tmp_path):
    from macroflow.config import Settings
    from macroflow.ui.main_window import MainWindow
    window = MainWindow(Settings(tmp_path), enable_hooks=False)
    qapp.processEvents()
    window.record_hotkey_fields["record_start"].setText("F2")
    window.record_hotkey_fields["record_stop"].setText("F3")
    window.save_record_controls()
    assert Settings(tmp_path).data["hotkeys"]["record_start"] == "F2"
    assert Settings(tmp_path).data["hotkeys"]["record_stop"] == "F3"
    window.new_macro(name="Panel QA")
    window.editor.insert([Event("wait", 30)])
    window.engine.play(window.current, seconds=0)
    qapp.processEvents()
    window.sync_state()
    assert window.playback_panel.isVisible()
    assert window.playback_panel.macro_name.text() == "Panel QA"
    window.playback_panel.pause.click()
    qapp.processEvents()
    assert window.engine.control.paused
    assert window.playback_panel.pause.text() == "Reanudar"
    assert window.playback_panel.title.text() == "EN PAUSA"
    assert window.playback_panel.isVisible()
    window.playback_panel.restart.click()
    window.playback_panel.stop.click()
    qapp.processEvents()
    assert not window.playback_panel.isVisible()
    window.close()
    qapp.processEvents()


def test_legacy_record_control_migration(tmp_path):
    from macroflow.config import DEFAULTS, Settings
    from macroflow.storage import atomic_json
    import copy
    old = copy.deepcopy(DEFAULTS)
    old["hotkeys"]["record"] = "Ctrl+F2"
    old["hotkeys"].pop("record_start")
    old["hotkeys"].pop("record_stop")
    atomic_json(tmp_path / "settings.json", old)
    settings = Settings(tmp_path)
    assert settings.data["hotkeys"]["record_start"] == "Ctrl+F2"
    assert settings.data["hotkeys"]["record_stop"] == "Ctrl+Alt+F5"
