import copy
import time

import pytest

from macroflow.config import DEFAULT_HOTKEYS
from macroflow.engine import Engine
from macroflow.hotkeys import parse_hotkey, validate_hotkeys
from macroflow.models import Event, Macro, ValidationError
from macroflow.triggers import InputRouter, parse_binding, validate_bindings


def test_hotkey_conflicts():
    mapping = dict(DEFAULT_HOTKEYS)
    mapping["play"] = "alt+ctrl+f6"
    with pytest.raises(ValidationError):
        validate_hotkeys(mapping)
    assert parse_hotkey("Ctrl+Alt+F6") == (3, 0x75)
    with pytest.raises(ValidationError):
        parse_hotkey("F12")


def test_conflicts_include_disabled_macros_and_controls():
    a = Macro(trigger="Ctrl+G")
    b = Macro(trigger="ctrl+g")
    with pytest.raises(ValidationError):
        validate_bindings([a, b], DEFAULT_HOTKEYS)
    with pytest.raises(ValidationError):
        validate_bindings([Macro(trigger="Ctrl+Alt+F6")], DEFAULT_HOTKEYS)


@pytest.mark.parametrize("binding", ["A", "B", "F6", "Ctrl+G", "Shift+X1", "X2", "Ctrl+Alt+F10"])
def test_binding_roundtrip(binding):
    assert parse_binding(parse_binding(binding).label) == parse_binding(binding)


@pytest.mark.parametrize("binding", ["Win+L", "Ctrl+Alt+Delete", "Alt+Tab", "F12", "Ctrl+Ctrl+A", "", "abc"])
def test_reserved_or_invalid_binding(binding):
    with pytest.raises(ValidationError):
        parse_binding(binding)


def test_multiple_macros_isolated_and_synthetic_rejected():
    calls = []
    macros = [Macro(name="A", trigger="A", enabled=True), Macro(name="B", trigger="B", enabled=True),
              Macro(name="G", trigger="Ctrl+G", enabled=True), Macro(name="Ratón", trigger="X1", enabled=True)]
    router = InputRouter(lambda *args: calls.append(args))
    router.configure(macros, DEFAULT_HOTKEYS)
    assert not router.process(ord("A"), True, injected=True)
    assert calls == []
    assert router.process(ord("A"), True)
    assert router.process(ord("A"), True)
    router.process(ord("A"), False)
    router.process(ord("B"), True)
    router.process(ord("B"), False)
    router.process(0xA2, True)
    router.process(ord("G"), True)
    router.process(ord("G"), False)
    router.process(0xA2, False)
    router.process("x1", True)
    router.process("x1", False)
    assert [identifier for action, identifier in calls] == [m.id for m in macros]


def test_disabled_normal_keys_and_inhibited_editor():
    macro = Macro(trigger="A", enabled=False)
    calls = []
    router = InputRouter(lambda *args: calls.append(args))
    router.configure([macro], DEFAULT_HOTKEYS)
    assert not router.process(65, True) and not router.process(65, False)
    macro.enabled = True
    router.configure([macro], DEFAULT_HOTKEYS)
    router.macro_allowed = lambda: False
    assert not router.process(65, True) and calls == []


def test_hold_release_on_key_or_modifier_release():
    calls = []
    macro = Macro(trigger="Ctrl+G", enabled=True, activation="hold")
    router = InputRouter(lambda *args: calls.append(args))
    router.configure([macro], DEFAULT_HOTKEYS)
    router.process(0xA2, True)
    router.process(71, True)
    router.process(0xA2, False)
    assert calls == [("macro_press", macro.id), ("macro_release", macro.id)]


def test_emergency_priority_and_synthetic_does_not_trigger():
    calls = []
    router = InputRouter(lambda *args: calls.append(args))
    router.configure([], DEFAULT_HOTKEYS)
    router.capture = lambda value: calls.append(("captured", value))
    assert not router.process(0x13, True, injected=True)
    assert router.process(0x13, True)
    assert calls == [("emergency", "")]


def wait_idle(engine):
    deadline = time.monotonic() + 2
    while engine.busy and time.monotonic() < deadline:
        time.sleep(.003)
    assert not engine.busy


def test_toggle_hold_queue_and_emergency(driver):
    engine = Engine(driver_factory=lambda: driver)
    a = Macro(name="A", trigger="A", enabled=True, activation="toggle", events=[Event("wait", .02)])
    b = Macro(name="B", trigger="B", enabled=True, activation="hold", events=[Event("wait", .02)])
    assert engine.trigger(a) == "started"
    assert engine.trigger(b) == "blocked"
    engine.policy = "queue"
    assert engine.trigger(b) == "queued" and len(engine.queue) == 1
    engine.release_trigger(b.id)
    assert not engine.queue
    assert engine.trigger(a) == "stopped"
    wait_idle(engine)
    assert engine.trigger(b) == "started"
    engine.release_trigger(b.id)
    wait_idle(engine)
    engine.trigger(a)
    engine.trigger(b)
    engine.stop()
    wait_idle(engine)
    assert not engine.queue and not driver.held_keys and not driver.held_buttons
    engine.close()


def test_queue_drains_in_order(driver):
    engine = Engine(driver_factory=lambda: driver)
    engine.policy = "queue"
    a = Macro(events=[Event("wait", .03)])
    b = Macro(events=[Event("wait", .01)], repetitions=2)
    engine.trigger(a)
    assert engine.trigger(b) == "queued"
    wait_idle(engine)
    assert engine.next_queued() == "started"
    wait_idle(engine)
    assert len(driver.events) == 3
    engine.close()


def test_running_snapshot_is_independent(driver):
    engine = Engine(driver_factory=lambda: driver)
    macro = Macro(events=[Event("wait", .05)])
    engine.trigger(macro)
    macro.events.clear()
    wait_idle(engine)
    assert len(driver.events) == 1
    engine.close()


def test_incompatible_tasks_block(driver):
    from macroflow.models import ClickOptions
    engine = Engine(driver_factory=lambda: driver)
    engine.click(ClickOptions(interval=100), seconds=0)
    with pytest.raises(ValidationError):
        engine.play(Macro(events=[Event("wait")]), seconds=0)
    assert engine.trigger(Macro(events=[Event("wait")])) == "blocked"
    engine.close()
