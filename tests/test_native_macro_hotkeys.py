import os
import pytest
from macroflow.config import Settings, DEFAULT_HOTKEYS
from macroflow.models import Macro, ValidationError
from macroflow.triggers import InputRouter
from macroflow.hotkeys import GlobalHotkeys
from macroflow.ui.main_window import MainWindow


def test_native_macro_press_reaches_os_but_release_still_tracks_hold():
    events = []
    macro = Macro(name='Prueba', trigger='J', enabled=True, activation='hold')
    router = InputRouter(lambda *args: events.append(args))
    router.configure([macro], DEFAULT_HOTKEYS)
    router.native_macros = {macro.id}
    assert not router.process(ord('J'), True)
    assert not events and any(item[0] == macro.id for item in router.active.values())
    assert router.process(ord('J'), False)
    assert events == [('macro_release', macro.id)]


def test_regular_macro_still_dispatches_from_hook():
    events = []
    macro = Macro(name='Prueba', trigger='J', enabled=True)
    router = InputRouter(lambda *args: events.append(args))
    router.configure([macro], DEFAULT_HOTKEYS)
    assert router.process(ord('J'), True)
    assert events == [('macro_press', macro.id)]


def test_native_bindings_only_use_keyboard_and_background_focus(qapp, tmp_path, monkeypatch):
    window = MainWindow(Settings(tmp_path), enable_hooks=False)
    keyboard = Macro(name='Tecla', enabled=True, trigger='J')
    mouse = Macro(name='Mouse', enabled=True, trigger='X1')
    window.macros = {m.id: m for m in (keyboard, mouse)}
    monkeypatch.setattr('macroflow.ui.main_window.foreground_process', lambda: os.getpid()+1)
    assert window.native_macro_bindings() == {}
    window.engine.input_delivery = 'activate'
    assert window.native_macro_bindings() == {'macro:'+keyboard.id: 'J'}
    monkeypatch.setattr('macroflow.ui.main_window.foreground_process', os.getpid)
    assert window.native_macro_bindings() == {}
    window.current = None
    window.close()


def test_native_once_hotkey_is_not_lost_after_fast_release(qapp, tmp_path, monkeypatch):
    window = MainWindow(Settings(tmp_path), enable_hooks=False)
    macro = Macro(name='Prueba', enabled=True, trigger='J')
    window.macros[macro.id] = macro
    window.engine.input_delivery = 'activate'
    window.router.native_macros = {macro.id}
    window.router.active.clear()
    monkeypatch.setattr(window.router, 'macro_allowed', lambda: True)
    calls = []
    monkeypatch.setattr(window, 'route_hotkey', lambda *args: calls.append(args))
    window.native_hotkey('macro:'+macro.id)
    assert calls == [('macro_press', macro.id)]
    window.engine.enabled = False
    window.native_hotkey('macro:'+macro.id)
    assert len(calls) == 1
    window.close()


def test_native_callbacks_do_not_execute_inside_nexo(qapp, tmp_path, monkeypatch):
    window = MainWindow(Settings(tmp_path), enable_hooks=False)
    macro = Macro(name='Prueba', enabled=True, trigger='J')
    window.engine.input_delivery = 'activate'
    window.router.native_macros = {macro.id}
    monkeypatch.setattr(window.router, 'macro_allowed', lambda: False)
    monkeypatch.setattr(window, 'route_hotkey', lambda *args: pytest.fail('No ejecutar mientras se escribe en Nexo'))
    window.native_hotkey('macro:'+macro.id)
    window.close()


def test_native_registration_tracks_focus_without_restarting_unchanged_bindings(qapp, tmp_path, monkeypatch):
    window = MainWindow(Settings(tmp_path), enable_hooks=False)
    macro = Macro(name='Prueba', enabled=True, trigger='J')
    window.macros[macro.id] = macro
    window.engine.input_delivery = 'activate'
    window.enable_hooks = True
    window.native_registration_ready = True
    calls = []
    monkeypatch.setattr(window.hotkeys, 'start', lambda mapping, **kwargs: calls.append(kwargs['extra']))
    monkeypatch.setattr('macroflow.ui.main_window.foreground_process', lambda: os.getpid()+1)
    window.sync_native_macros()
    window.sync_native_macros()
    assert calls == [{'macro:'+macro.id:'J'}]
    assert window.router.native_macros == {macro.id}
    monkeypatch.setattr('macroflow.ui.main_window.foreground_process', os.getpid)
    window.sync_native_macros()
    assert calls[-1] == {} and not window.router.native_macros
    window.enable_hooks = False
    window.close()


def test_global_registration_includes_native_macro_but_preserves_controls():
    class Registration(GlobalHotkeys):
        def _run(self, mapping, ready):
            self.captured = mapping
            ready.set()
    service = Registration(lambda action: None)
    try:
        service.start(DEFAULT_HOTKEYS, extra={'macro:test':'Ctrl+Alt+F23'})
        assert service.captured == dict(DEFAULT_HOTKEYS, **{'macro:test':'Ctrl+Alt+F23'})
        with pytest.raises(ValidationError):
            service.start(DEFAULT_HOTKEYS, extra={'macro:test':DEFAULT_HOTKEYS['play']})
    finally:
        service.stop()
