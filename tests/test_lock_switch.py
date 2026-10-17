import time
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtTest import QSignalSpy
from macroflow.config import Settings, DEFAULTS
from macroflow.engine import Engine
from macroflow.models import Macro, Event, ClickOptions, ValidationError
from macroflow.triggers import InputRouter
from macroflow.ui.main_window import MainWindow


def test_suspended_router_passes_macro_control_and_emergency_keys():
    calls = []
    macro = Macro(name='Prueba', trigger='J', enabled=True)
    router = InputRouter(lambda *args: calls.append(args))
    router.configure([macro], DEFAULTS['hotkeys'])
    router.set_suspended(True)
    for key in (ord('J'), 17, 13, 19):
        assert not router.process(key, True)
        assert not router.process(key, False)
    assert calls == []
    router.set_suspended(False)
    assert router.process(ord('J'), True)
    assert calls == [('macro_press', macro.id)]


def test_disabled_engine_blocks_every_start_path_and_queue(driver):
    engine = Engine(driver_factory=lambda: driver)
    macro = Macro(name='Prueba', events=[Event('key_down', key='char:a'), Event('key_up', key='char:a')])
    engine.set_enabled(False)
    for start in (lambda: engine.play(macro, seconds=0), lambda: engine.record(seconds=0), lambda: engine.click(ClickOptions(), seconds=0)):
        with pytest.raises(ValidationError, match='bloqueado'):
            start()
    assert engine.trigger(macro) == 'blocked'
    assert not engine.next_queued() and not engine.busy
    assert driver.events == []
    engine.close()


def test_blocking_running_macro_cancels_releases_inputs_and_clears_queue(driver):
    engine = Engine(driver_factory=lambda: driver)
    macro = Macro(name='Activa', events=[Event('key_down', key='char:a'), Event('key_up', 5, key='char:a')])
    engine.play(macro, seconds=0)
    limit = time.monotonic() + 2
    while not driver.held_keys and time.monotonic() < limit:
        time.sleep(.005)
    assert driver.held_keys
    engine.policy = 'queue'
    assert engine.trigger(Macro(name='En cola', events=macro.events)) == 'queued'
    engine.set_enabled(False)
    engine.thread.join(2)
    assert not engine.busy and not engine.queue and not driver.held_keys
    before = len(driver.events)
    engine.set_enabled(True)
    assert not engine.busy and len(driver.events) == before
    engine.close()


def test_switch_click_animation_dark_light_and_pending_hotkeys(qapp, tmp_path, monkeypatch):
    window = MainWindow(Settings(tmp_path), enable_hooks=False)
    window.show()
    window.new_macro(name='Prueba')
    window.current.events = [Event('wait', .1)]
    window.sync_state()
    for theme in ('dark', 'light'):
        window.settings.data['theme'] = theme
        window.apply_theme()
        finished = QSignalSpy(window.lock_switch.motion.finished)
        QTest.mouseClick(window.lock_switch, Qt.MouseButton.LeftButton)
        assert finished.count() or finished.wait(5000)
        assert window.lock_switch.position == 1
        assert not window.engine.enabled and window.router.suspended
        assert not window.record_start.isEnabled() and not window.play_start.isEnabled() and not window.click_start.isEnabled()
        window.on_hotkey('play', '')
        window.on_hotkey('record_start', '')
        window.on_hotkey('click', '')
        assert not window.engine.busy
        window.set_sidebar_collapsed(True, animate=False)
        assert window.lock_switch.isVisible()
        assert window.lock_switch.width() <= window.sidebar.width() - 30
        finished = QSignalSpy(window.lock_switch.motion.finished)
        QTest.mouseClick(window.lock_switch, Qt.MouseButton.LeftButton)
        assert finished.count() or finished.wait(5000)
        assert window.lock_switch.position == 0
        assert window.engine.enabled and not window.router.suspended
        assert window.record_start.isEnabled() and window.play_start.isEnabled() and window.click_start.isEnabled()
    window.close()
