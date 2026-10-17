import ctypes
from ctypes import wintypes
from types import SimpleNamespace
import pytest
from macroflow.windows import InputTarget
from macroflow.playback import RunControl, Cancelled
from macroflow.models import ValidationError, Event
from macroflow.engine import Engine


def api_for(*, minimized=False, foreground=0, accept=True, pid=42):
    state = dict(minimized=minimized, foreground=foreground, restores=0, attempts=0)
    def get_pid(hwnd, pointer):
        ctypes.cast(pointer, ctypes.POINTER(wintypes.DWORD)).contents.value = pid
        return 1
    def restore(hwnd, mode):
        assert mode in (5, 9)
        state['restores'] += int(mode == 9)
        state['minimized'] = False
        return True
    def activate(hwnd):
        state['attempts'] += 1
        if accept:
            state['foreground'] = hwnd
        return accept
    api = SimpleNamespace(IsWindow=lambda hwnd: True, IsIconic=lambda hwnd: state['minimized'],
        ShowWindowAsync=restore, SetForegroundWindow=activate, GetForegroundWindow=lambda: state['foreground'],
        GetWindowThreadProcessId=get_pid)
    return api, state


@pytest.mark.parametrize('minimized', [False, True])
def test_activation_restores_only_minimized_window_and_checks_focus(minimized):
    api, state = api_for(minimized=minimized)
    InputTarget(10, 42).activate(RunControl(), api=api)
    assert state['foreground'] == 10 and state['restores'] == int(minimized)
    assert state['attempts'] == 1


def test_denied_activation_does_not_keep_stealing_focus():
    api, state = api_for(accept=False)
    with pytest.raises(ValidationError, match='no permitió'):
        InputTarget(10, 42).activate(RunControl(), api=api, timeout=0)
    assert state['attempts'] == 1


def test_reused_hwnd_is_not_activated():
    api, state = api_for(pid=99)
    with pytest.raises(ValidationError, match='cerró o cambió'):
        InputTarget(10, 42).activate(RunControl(), api=api)
    assert state['attempts'] == 0


def test_cancelled_activation_never_changes_focus():
    api, state = api_for()
    control = RunControl()
    control.cancel()
    with pytest.raises(Cancelled):
        InputTarget(10, 42).activate(control, api=api)
    assert state['attempts'] == 0


def test_engine_activates_before_creating_input_driver_and_guards_initial_wait():
    calls = []
    active = [True]
    target = SimpleNamespace(activate=lambda control: calls.append('activate'), allows=lambda event=None: active[0])
    engine = Engine(driver_factory=lambda: calls.append('driver') or object())
    engine.input_target, engine.input_delivery = target, 'activate'
    control = RunControl()
    engine.make_driver(control)
    assert calls == ['activate', 'driver']
    active[0] = False
    with pytest.raises(ValidationError, match='perdió el foco'):
        control.wait()


def test_activation_failure_never_creates_input_driver():
    def fail(control):
        raise ValidationError('No se pudo activar')
    engine = Engine(driver_factory=lambda: pytest.fail('No debe crear el driver'))
    engine.input_target = SimpleNamespace(activate=fail)
    engine.input_delivery = 'activate'
    with pytest.raises(ValidationError):
        engine.make_driver(RunControl())


def test_new_delivery_option_is_available_without_changing_old_modes(qapp, tmp_path, monkeypatch):
    from macroflow.config import Settings
    from macroflow.ui.main_window import MainWindow
    monkeypatch.setattr('macroflow.ui.main_window.application_windows', lambda: [(10, 42, 'Prueba')])
    window = MainWindow(Settings(tmp_path), enable_hooks=False)
    window.target_combo.setCurrentIndex(1)
    assert [window.target_delivery.itemData(i) for i in range(3)] == ['background', 'foreground', 'activate']
    window.target_delivery.setCurrentIndex(2)
    assert window.engine.input_delivery == 'activate'
    assert 'Si Segundo plano no funciona' in window.target_note.text()
    window.close()



def test_worker_requests_focus_on_gui_thread(qapp, tmp_path):
    import threading
    import time
    from PySide6.QtCore import QThread
    from macroflow.config import Settings
    from macroflow.ui.main_window import MainWindow
    window = MainWindow(Settings(tmp_path), enable_hooks=False)
    called, errors = [], []
    def worker():
        try:
            window.request_target_activation(lambda: called.append(QThread.currentThread() == window.thread()), RunControl())
        except Exception as exc:
            errors.append(exc)
    thread = threading.Thread(target=worker)
    thread.start()
    deadline = time.monotonic() + 2
    while thread.is_alive() and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(.001)
    thread.join(.1)
    assert not thread.is_alive() and called == [True] and not errors
    window.close()


def test_cancelled_queued_request_does_not_activate(qapp, tmp_path):
    from macroflow.config import Settings
    from macroflow.ui.main_window import MainWindow
    import threading
    window = MainWindow(Settings(tmp_path), enable_hooks=False)
    called = []
    control = RunControl()
    control.cancel()
    request = dict(callback=lambda: called.append(True), control=control, done=threading.Event(), error=None)
    window.perform_target_activation(request)
    assert not called and isinstance(request['error'], Cancelled) and request['done'].is_set()
    window.close()


def test_recording_target_has_clear_label(qapp, tmp_path):
    from macroflow.config import Settings
    from macroflow.ui.main_window import MainWindow
    window = MainWindow(Settings(tmp_path), enable_hooks=False)
    window.change_page(1)
    assert window.target_label.text() == 'Ventana a grabar'
    window.change_page(2)
    assert window.target_label.text() == 'Destino'
    window.close()
