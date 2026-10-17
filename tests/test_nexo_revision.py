import copy
import threading
import time

import pytest

from macroflow.config import DEFAULTS, DEFAULT_HOTKEYS, Settings, validate_settings
from macroflow.models import ClickOptions, Event, Macro, ValidationError
from macroflow.playback import Cancelled, RunControl, run_clicker
from macroflow.recording import Recorder
from macroflow.triggers import Binding, InputRouter, parse_binding


class Probe:
    reason = "Campo protegido"
    def allowed(self):
        return True
    def close(self):
        pass


def recorder(monkeypatch, **kwargs):
    monkeypatch.setattr("macroflow.recording.foreground_process", lambda: -1)
    result = Recorder(privacy_factory=Probe, **kwargs)
    result.worker = threading.Thread(target=result._consume, daemon=True)
    result.worker.start()
    assert result.ready.wait(1)
    return result


def chord(result, *tokens):
    for token in tokens:
        result.feed(Event("key_down", key=token))
    for token in reversed(tokens):
        result.feed(Event("key_up", key=token))


def test_exact_controls_preserve_plain_enter_and_other_chords(monkeypatch):
    controls = dict(DEFAULT_HOTKEYS, record_start="Ctrl+Enter", record_stop="Ctrl+Alt+Enter")
    result = recorder(monkeypatch, controls=controls)
    chord(result, "key:ctrl_l", "key:enter")
    chord(result, "key:ctrl_l", "key:alt_l", "key:enter")
    chord(result, "key:enter")
    chord(result, "key:shift_l", "key:enter")
    result.stop()
    assert [(e.kind, e.key) for e in result.events] == [
        ("key_down", "key:enter"), ("key_up", "key:enter"),
        ("key_down", "key:shift_l"), ("key_down", "key:enter"),
        ("key_up", "key:enter"), ("key_up", "key:shift_l")]


@pytest.mark.parametrize("mode", ["timed", "fixed"])
def test_default_exclusions_only_affect_recording(monkeypatch, mode):
    keys = {item["key"] for item in DEFAULTS["excluded_keys"] if item["enabled"]}
    result = recorder(monkeypatch, reserved=keys, mode=mode)
    for key in keys:
        chord(result, f"vk:{key}")
    chord(result, "vk:190")
    result.stop()
    assert [e.key for e in result.events] == ["vk:190", "vk:190"]
    calls = []
    router = InputRouter(lambda *args: calls.append(args))
    macro = Macro(trigger="Delete", enabled=True)
    router.configure([macro], DEFAULT_HOTKEYS)
    router.process(46, True)
    assert calls == [("macro_press", macro.id)]


def test_fixed_interval_ignores_wall_clock_and_records_typematic(monkeypatch):
    result = recorder(monkeypatch, mode="fixed", fixed_interval=1)
    for stamp, kind, key in [(5, "key_down", "vk:65"), (5.3, "key_down", "vk:65"),
                             (5.35, "key_down", "vk:65"), (5.4, "key_up", "vk:65"),
                             (100, "key_down", "vk:66"), (120, "key_up", "vk:66")]:
        result.queue.put((Event(kind, key=key), result.started + stamp, result.epoch, False))
    result.stop()
    assert [e.key for e in result.events if e.kind == "key_down"] == ["vk:65"] * 3 + ["vk:66"]
    assert [e.delay for e in result.events] == [0, 0, 1, 0, 1, 0, 1, 0]
    assert not result.held_keys


@pytest.mark.parametrize("mode", ["timed", "fixed"])
def test_modifier_held_across_record_start_is_known(monkeypatch, mode):
    result = recorder(monkeypatch, controls={"record_start": "Ctrl+Enter", "record_stop": "Ctrl+Alt+Enter"},
                      mode=mode, physical_modifiers=lambda: {162})


    chord(result, "key:enter")
    chord(result, "vk:67")
    result.stop()
    assert [e.key for e in result.events] == ["vk:162", "vk:67", "vk:67", "vk:162"]


def test_fixed_combinations_release_between_presses(monkeypatch):
    result = recorder(monkeypatch, mode="fixed")
    chord(result, "key:ctrl_l", "vk:67")
    chord(result, "vk:86")
    result.stop()
    assert [(e.kind, e.key) for e in result.events] == [
        ("key_down", "key:ctrl_l"), ("key_down", "vk:67"), ("key_up", "vk:67"),
        ("key_up", "key:ctrl_l"), ("key_down", "vk:86"), ("key_up", "vk:86")]
    assert result.events[4].delay == 1


@pytest.mark.parametrize("vk", [186, 187, 188, 189, 190, 191, 192, 219, 220, 221, 222, 226])
def test_physical_punctuation_roundtrips_and_triggers(vk):
    binding = Binding(frozenset({"Ctrl"}), vk)
    assert parse_binding(binding.label) == binding
    calls = []
    macro = Macro(trigger=binding.label, enabled=True)
    router = InputRouter(lambda *args: calls.append(args))
    router.configure([macro], DEFAULT_HOTKEYS)
    router.process(162, True)
    router.process(vk, True)
    assert calls == [("macro_press", macro.id)]


@pytest.mark.parametrize("text", ["+", "Ctrl++", ".", "-", ",", "{", "}"])
def test_character_binding_canonicalization(text):
    binding = parse_binding(text)
    assert parse_binding(binding.label) == binding


def test_restrictions_persist_toggle_delete_and_old_settings(tmp_path):
    settings = Settings(tmp_path)
    settings.data["excluded_keys"][0]["enabled"] = False
    settings.data["excluded_keys"] = [entry for entry in settings.data["excluded_keys"] if entry["key"] != 46]
    settings.data["excluded_keys"].append({"key": 65, "enabled": True})
    settings.save()
    assert Settings(tmp_path).data["excluded_keys"] == settings.data["excluded_keys"]
    old = {key: value for key, value in DEFAULTS.items() if key not in ("excluded_keys", "record_mode", "fixed_interval")}
    assert validate_settings(old)["excluded_keys"] == DEFAULTS["excluded_keys"]
    malformed = copy.deepcopy(settings.data)
    malformed["excluded_keys"].append({"key": 65, "enabled": True})
    with pytest.raises(ValidationError):
        validate_settings(malformed)


def test_keyboard_repeater_repetitions_and_no_mouse(driver):
    result = run_clicker(ClickOptions(key="Ctrl+V", repetitions=3, interval=.01), driver, RunControl())
    assert result == 3
    assert [e.key for e in driver.events] == ["vk:162", "vk:86"] * 3
    assert all(e.kind == "key_down" for e in driver.events)
    assert not driver.held_keys and not driver.held_buttons


def test_keyboard_repeater_failure_releases_modifiers(driver):
    original = driver.dispatch
    def dispatch(event):
        original(event)
        if event.key == "vk:86":
            raise RuntimeError("failure")
    driver.dispatch = dispatch
    with pytest.raises(RuntimeError):
        run_clicker(ClickOptions(key="Ctrl+V", repetitions=3), driver, RunControl())
    assert not driver.held_keys


def test_keyboard_repeater_emergency_cancels_long_interval(driver):
    control = RunControl()
    def run():
        try:
            run_clicker(ClickOptions(key="Z", interval=8000), driver, control)
        except Cancelled:
            pass
    thread = threading.Thread(target=run)
    thread.start()
    limit = time.monotonic() + 1
    while not driver.events and time.monotonic() < limit:
        time.sleep(.001)
    control.cancel()
    thread.join(.5)
    assert not thread.is_alive() and not driver.held_keys


def test_escape_cancels_global_assignment(qapp):
    from macroflow.ui.dialogs import AssignDialog
    router = InputRouter(lambda *args: None)
    router.configure([], DEFAULT_HOTKEYS)
    dialog = AssignDialog(router, None)
    dialog.show()
    router.process(27, True)
    qapp.processEvents()
    assert not dialog.isVisible() and dialog.value is None and router.capture is None
    assert not dialog.timeout_timer.isActive()


def test_macro_assignment_readonly_auto_enable_and_remove(qapp):
    from macroflow.ui.dialogs import MacroDialog
    macro = Macro(name="Mi macro")
    dialog = MacroDialog(macro, InputRouter(lambda *args: None), lambda m: None)
    assert dialog.trigger.isReadOnly()
    dialog.trigger.setText("VK187")
    dialog.accept()
    assert dialog.result_macro.enabled and dialog.result_macro.trigger == "VK187"
    second = MacroDialog(dialog.result_macro, dialog.router, lambda m: None)
    second.trigger.setText("")
    second.accept()
    assert not second.result_macro.enabled and not second.result_macro.trigger


def test_recording_reuses_configured_macro_and_controls_persist(qapp, tmp_path, monkeypatch):
    from macroflow.ui.main_window import MainWindow
    window = MainWindow(Settings(tmp_path), enable_hooks=False)
    qapp.processEvents()
    window.new_macro(name="Configurada")
    window.current.trigger, window.current.enabled = "A", True
    window.current.speed, window.current.repetitions = 2.5, 7
    window.editor.insert([Event("wait", 2)])
    identifier = window.current.id
    window.setting_hotkeys["record_start"].setText("Ctrl+Enter")
    window.setting_hotkeys["record_stop"].setText("Ctrl+Alt+Enter")
    window.save_settings()
    assert all(field.isReadOnly() for field in window.setting_hotkeys.values())
    assert Settings(tmp_path).data["hotkeys"]["record_stop"] == "Ctrl+Alt+Enter"
    arguments = {}
    monkeypatch.setattr(window.engine, "record", lambda **kwargs: arguments.update(kwargs))
    window.start_recording()
    assert window.record_target == identifier and len(window.macros) == 1
    assert arguments["controls"]["record_start"] == "Ctrl+Enter"
    assert 13 not in arguments["reserved"]
    assert (tmp_path / "recovery" / f"{identifier}.json").exists()
    recorded = [Event("key_down", key="vk:190"), Event("key_up", key="vk:190")]
    window.on_engine_event("finished", {"task": "record", "result": {"events": recorded, "display_signature": []}, "error": None})
    assert window.current.id == identifier and window.current.events == recorded
    assert (window.current.name, window.current.trigger, window.current.enabled, window.current.speed, window.current.repetitions) == ("Configurada", "A", True, 2.5, 7)
    window.on_engine_event("finished", {"task": "record", "result": {"events": [], "display_signature": []}, "error": None})
    assert window.current.events == recorded
    window.close()


def test_capture_strip_stop_moves_and_preview_stays_bounded(qapp):
    from macroflow.ui.capture import KeyCaptureDialog
    dialog = KeyCaptureDialog(None, lambda: None)
    dialog.begin("Prueba", 1, "Ctrl+Alt+Enter")
    events = [Event("key_down", key="vk:65")] * 120
    dialog.update_events(events)
    assert dialog.total == 120 and dialog.keys.count() == 101
    assert dialog.keys.itemAt(100).widget() is dialog.stop_button
    dialog.hide()


@pytest.mark.parametrize("mode", ["timed", "fixed"])
@pytest.mark.parametrize("generic, variants", [(17, (162, 163)), (16, (160, 161)), (18, (164, 165))])
def test_modifier_exclusions_cover_both_sides_and_can_be_disabled(monkeypatch, mode, generic, variants):
    from macroflow.triggers import excluded_key_codes
    for enabled in (True, False):
        blocked = excluded_key_codes([{"key": generic, "enabled": enabled}])
        result = recorder(monkeypatch, mode=mode, reserved=blocked)
        for modifier in variants:
            chord(result, f"vk:{modifier}", "vk:221")
        result.stop()
        recorded_modifiers = [e.key for e in result.events if e.kind == "key_down" and e.key != "vk:221"]
        assert recorded_modifiers == ([] if enabled else [f"vk:{value}" for value in variants])
        assert [e.key for e in result.events].count("vk:221") == 4
        assert not result.held_keys


def test_default_exclusions_preserve_shift_and_ctrl():
    from macroflow.triggers import excluded_key_codes
    blocked = excluded_key_codes(DEFAULTS["excluded_keys"])
    assert not blocked.intersection({16, 17, 18, 160, 161, 162, 163, 164, 165})


def test_capture_reset_undo_and_interval_preserve_combinations():
    capture = Recorder(mode="fixed", fixed_interval=1, privacy_factory=Probe)
    capture.physical_keys = {"vk:162": 162}
    capture._fixed_press(Event("key_down", key="vk:67"))
    capture.physical_keys.clear()
    capture._fixed_press(Event("key_down", key="vk:86"))
    original = [(e.kind, e.key) for e in capture.events]
    capture.set_fixed_interval(.05)
    assert [e.delay for e in capture.events] == [0, 0, 0, 0, .05, 0]
    assert capture.reset_capture() and not capture.events and capture.can_undo_reset
    capture.set_fixed_interval(.25)
    assert capture.reset_capture(undo=True)
    assert [(e.kind, e.key) for e in capture.events] == original
    assert [e.delay for e in capture.events] == [0, 0, 0, 0, .25, 0]
    assert not capture.can_undo_reset
    capture.reset_capture()
    capture._fixed_press(Event("key_down", key="vk:66"))
    assert not capture.can_undo_reset and not capture.reset_capture(undo=True)
    assert [(e.kind, e.key, e.delay) for e in capture.events] == [("key_down", "vk:66", 0), ("key_up", "vk:66", 0)]
    capture.stop()
    assert not capture.reset_capture()


def test_capture_wraps_and_visibility_does_not_change_events(qapp):
    from macroflow.ui.capture import KeyCaptureDialog
    dialog = KeyCaptureDialog(None, lambda: None)
    dialog.resize(760, 500)
    dialog.begin("Prueba", 1, "Ctrl+Alt+Enter")
    events = [Event(kind, key="vk:65") for _ in range(18) for kind in ("key_down", "key_up")]
    dialog.update_events(events)
    qapp.processEvents()
    first = dialog.keys.itemAt(0).widget()
    assert dialog.stop_button.y() > first.y()
    assert dialog.keys.itemAt(dialog.keys.count() - 1).widget() is dialog.stop_button
    assert dialog.scroll.horizontalScrollBar().maximum() == 0
    dialog.show_releases.setChecked(False)
    assert dialog.keys.count() == 19 and dialog.events == events and dialog.total == 18
    dialog.set_phase("paused")
    assert dialog.delay.isEnabled() and dialog.pause_button.text() == "Reanudar"
    dialog.set_phase("running")
    assert not dialog.delay.isEnabled()
    dialog.hide()


def test_restrictions_ui_add_toggle_remove_modifiers(qapp, tmp_path):
    from macroflow.ui.main_window import MainWindow
    from macroflow.triggers import excluded_key_codes
    window = MainWindow(Settings(tmp_path), enable_hooks=False)
    restrictions = window.restrictions
    assert restrictions.preset.findData(17) >= 0 and restrictions.preset.findData(16) >= 0
    restrictions.add(16)
    restrictions.toggle(16)
    restrictions.add(17)
    window.save_settings()
    stored = Settings(tmp_path).data["excluded_keys"]
    assert 162 in excluded_key_codes(stored) and 160 not in excluded_key_codes(stored)
    restrictions.remove(17)
    window.save_settings()
    assert 162 not in excluded_key_codes(Settings(tmp_path).data["excluded_keys"])
    window.close()
