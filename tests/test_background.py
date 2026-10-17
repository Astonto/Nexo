import ctypes
import os
import threading
import time

import pytest

from macroflow.background import WindowMessageDriver
from macroflow.engine import Engine
from macroflow.models import Event, ValidationError
from macroflow.playback import RunControl, play_events
from macroflow.windows import InputTarget


class Transport:
    def __init__(self):
        self.valid, self.receiver = True, 101
        self.messages = []

    def alive(self):
        return self.valid

    def keyboard_receiver(self):
        return self.receiver

    def resolve_key(self, token):
        return {"char:a": 65, "key:ctrl_l": 162}[token]

    def key(self, *args):
        self.messages.append(("key", *args))

    def mouse_receiver(self, x, y):
        return 202

    def position(self):
        return 120, 150

    def mouse(self, *args):
        self.messages.append(("mouse", *args))


def test_background_pins_key_release_to_original_receiver():
    transport = Transport()
    driver = WindowMessageDriver(None, transport)
    driver.dispatch(Event("key_down", key="char:a"))
    transport.receiver = 999
    driver.dispatch(Event("key_down", key="char:a"))
    driver.release_all()
    assert [item[1] for item in transport.messages] == [101, 101, 101]
    assert [item[4] for item in transport.messages] == [False, True, True]
    assert not driver.held_keys


def test_background_mouse_flags_suspend_and_restore():
    transport = Transport()
    driver = WindowMessageDriver(None, transport)
    driver.dispatch(Event("key_down", key="key:ctrl_l"))
    driver.dispatch(Event("mouse_down", button="left", x=120, y=150))
    assert transport.messages[-1][-1] == 9
    state = driver.suspend()
    assert not driver.held_keys and not driver.held_buttons
    assert transport.messages[-1][2].kind == "mouse_up"
    driver.restore(state)
    assert driver.held_keys and driver.held_buttons
    driver.release_all()
    assert not driver.held_keys and not driver.held_buttons


def test_background_closed_window_stops_without_fallback():
    transport = Transport()
    driver = WindowMessageDriver(None, transport)
    driver.dispatch(Event("key_down", key="char:a"))
    transport.valid = False
    with pytest.raises(ValidationError):
        driver.dispatch(Event("key_down", key="char:a"))
    driver.release_all()
    assert len(transport.messages) == 1 and not driver.held_keys


def test_delivery_selection_is_shared_and_locked_during_playback(qapp, tmp_path, monkeypatch):
    from macroflow.config import Settings
    from macroflow.ui.main_window import MainWindow
    monkeypatch.setattr("macroflow.ui.main_window.application_windows", lambda: [(123, 42, "Destino de prueba")])
    window = MainWindow(Settings(tmp_path), enable_hooks=False)
    window.target_combo.setCurrentIndex(1)
    assert window.engine.input_delivery == "background"
    window.target_delivery.setCurrentIndex(1)
    assert window.engine.input_delivery == "foreground"
    window.engine.task, window.engine.phase = "play", "paused"
    window.sync_state()
    assert not window.target_delivery.isEnabled()
    window.engine.task, window.engine.phase = "idle", "idle"
    window.close()


def test_engine_background_never_creates_global_driver(monkeypatch):
    def forbidden():
        pytest.fail("El envío en segundo plano no debe crear un controlador global")
    transport = Transport()
    monkeypatch.setattr("macroflow.background.NativeWindowMessages", lambda target: transport)
    engine = Engine(driver_factory=forbidden)
    engine.input_target = InputTarget(101, 42)
    control = RunControl()
    driver = engine.make_driver(control)
    assert isinstance(driver, WindowMessageDriver)
    assert control.target_guard == driver.check_target
    play_events([Event("key_down", key="char:a"), Event("key_up", key="char:a")], driver, control)
    assert len(transport.messages) == 2


def test_background_cancellation_releases_to_target():
    transport = Transport()
    driver = WindowMessageDriver(None, transport)
    control = RunControl()
    errors = []
    def run():
        try:
            play_events([Event("key_down", key="char:a"), Event("key_up", 30, key="char:a")], driver, control)
        except Exception as error:
            errors.append(error)
    worker = threading.Thread(target=run)
    worker.start()
    deadline = time.monotonic() + 2
    while not driver.held_keys and time.monotonic() < deadline:
        time.sleep(.005)
    control.cancel()
    worker.join(2)
    assert not worker.is_alive() and not driver.held_keys and errors
    assert transport.messages[-1][1:4] == (101, 65, False)


@pytest.mark.skipif(os.name != "nt", reason="Prueba real de mensajes Windows")
def test_native_background_messages_arrive_without_foreground_activation():
    from ctypes import wintypes
    from macroflow.background import NativeWindowMessages
    api = ctypes.WinDLL("user32", use_last_error=True)
    api.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                  ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                  wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, ctypes.c_void_p]
    api.CreateWindowExW.restype = wintypes.HWND
    api.DestroyWindow.argtypes = [wintypes.HWND]
    api.GetForegroundWindow.restype = wintypes.HWND
    api.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    api.SetWindowLongPtrW.restype = ctypes.c_ssize_t
    api.CallWindowProcW.argtypes = [ctypes.c_void_p, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    api.CallWindowProcW.restype = ctypes.c_ssize_t
    api.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT]
    api.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
    api.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
    api.DispatchMessageW.restype = ctypes.c_ssize_t
    received = []
    foreground = api.GetForegroundWindow()
    hwnd = api.CreateWindowExW(0, "STATIC", "Nexo isolated message receiver", 0, 80, 80, 300, 200, None, None, None, None)
    assert hwnd
    previous = None
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
    def receive(handle, msg, wp, lp):
        if 0x100 <= msg <= 0x20E:
            received.append((msg, wp, lp))
        return api.CallWindowProcW(previous, handle, msg, wp, lp)
    callback = callback_type(receive)
    previous = api.SetWindowLongPtrW(hwnd, -4, ctypes.cast(callback, ctypes.c_void_p).value)
    try:
        transport = NativeWindowMessages(InputTarget(hwnd, os.getpid()))
        driver = WindowMessageDriver(None, transport)
        driver.dispatch(Event("key_down", key="vk:38"))
        driver.dispatch(Event("key_up", key="vk:38"))
        driver.dispatch(Event("mouse_down", button="left", x=100, y=100))
        driver.release_all()
        message = wintypes.MSG()
        while api.PeekMessageW(ctypes.byref(message), hwnd, 0, 0, 1):
            api.TranslateMessage(ctypes.byref(message))
            api.DispatchMessageW(ctypes.byref(message))
        kinds = [item[0] for item in received]
        assert all(kind in kinds for kind in (0x100, 0x101, 0x201, 0x202))
        key_down = next(item for item in received if item[0] == 0x100)
        key_up = next(item for item in received if item[0] == 0x101)
        assert key_down[1] == 38 and key_down[2] & (1 << 24)
        assert key_up[2] & (1 << 31)
        assert api.GetForegroundWindow() == foreground
    finally:
        api.SetWindowLongPtrW(hwnd, -4, previous)
        api.DestroyWindow(hwnd)


@pytest.mark.skipif(os.name != 'nt', reason='Windows EDIT real')
def test_background_writes_actual_child_text_without_focus():
    from native_text_receiver import TextReceiver
    from macroflow.background import NativeWindowMessages
    api = ctypes.windll.user32
    api.GetForegroundWindow.restype = ctypes.c_void_p
    foreground = api.GetForegroundWindow()
    receiver = TextReceiver()
    try:
        transport = NativeWindowMessages(InputTarget(receiver.hwnd, os.getpid()))
        assert transport.keyboard_receiver() == receiver.edit
        driver = WindowMessageDriver(None, transport)
        for key in ('char:a', 'char:b', 'vk:32', 'vk:49'):
            driver.dispatch(Event('key_down', key=key))
            driver.dispatch(Event('key_up', key=key))
        deadline = time.monotonic() + 2
        while receiver.text() != 'ab 1' and time.monotonic() < deadline:
            time.sleep(.01)
        assert receiver.text() == 'ab 1'
        assert any(item[0] == receiver.edit and item[1] == 0x102 for item in receiver.messages)
        assert not any(item[0] == receiver.hwnd for item in receiver.messages)
        assert api.GetForegroundWindow() == foreground
        driver.release_all()
    finally:
        receiver.close()


def discovery_transport(editors, visible=None):
    from types import SimpleNamespace
    from macroflow.background import NativeWindowMessages
    transport = object.__new__(NativeWindowMessages)
    transport.target = InputTarget(10, 42)
    transport.last_keyboard_receiver = None
    transport.owned = lambda hwnd: True
    transport.class_name = lambda hwnd: 'Edit' if hwnd in editors else 'STATIC'
    transport.child_callback_type = lambda callback: callback
    transport.api = SimpleNamespace(GetWindowThreadProcessId=lambda *args: 1,
        GetGUIThreadInfo=lambda *args: False, IsWindowVisible=lambda hwnd: visible is None or hwnd in visible,
        IsWindowEnabled=lambda hwnd: True, EnumChildWindows=lambda root, callback, unused: [callback(hwnd, 0) for hwnd in editors])
    return transport


def test_background_ambiguous_editors_are_not_guessed():
    transport = discovery_transport([11, 12])
    with pytest.raises(ValidationError, match='varios controles'):
        transport.keyboard_receiver()


def test_background_hidden_cached_editor_is_replaced():
    transport = discovery_transport([11, 12], visible={12})
    transport.last_keyboard_receiver = 11
    assert transport.keyboard_receiver() == 12


def test_background_unknown_window_preserves_message_backend():
    transport = discovery_transport([])
    assert transport.keyboard_receiver() == 10
    assert transport.last_keyboard_receiver is None


@pytest.mark.skipif(os.name != 'nt', reason='Windows errors')
@pytest.mark.parametrize('error', [5, 1400])
def test_background_send_error_reports_real_code(error):
    from macroflow.background import NativeWindowMessages
    from types import SimpleNamespace
    transport = object.__new__(NativeWindowMessages)
    transport.target = InputTarget(10, 42)
    transport.alive = lambda: True
    transport.owned = lambda hwnd: True
    def reject(*args):
        ctypes.set_last_error(error)
        return False
    transport.api = SimpleNamespace(PostMessageW=reject)
    with pytest.raises(ValidationError, match='UIPI' if error == 5 else '1400'):
        transport.post(11, 0x100, 65, 1)


def test_background_reused_handle_pid_is_rejected():
    from macroflow.background import NativeWindowMessages
    from types import SimpleNamespace
    from ctypes import wintypes
    transport = object.__new__(NativeWindowMessages)
    transport.target = InputTarget(10, 42)
    def pid(hwnd, pointer):
        ctypes.cast(pointer, ctypes.POINTER(wintypes.DWORD)).contents.value = 99
        return 1
    transport.api = SimpleNamespace(GetWindowThreadProcessId=pid, IsWindow=lambda hwnd: True)
    assert not transport.alive()


@pytest.mark.parametrize('vk,down,repeated,alt,expected', [
    (38, True, False, False, 0x100), (38, False, False, False, 0x101),
    (65, True, True, False, 0x100), (65, True, False, True, 0x104),
    (65, False, False, True, 0x105)])
def test_background_keystroke_bit_fields(vk, down, repeated, alt, expected):
    from macroflow.background import NativeWindowMessages
    from types import SimpleNamespace
    transport = object.__new__(NativeWindowMessages)
    transport.api = SimpleNamespace(GetWindowThreadProcessId=lambda *args: 1,
        GetKeyboardLayout=lambda thread: 1, MapVirtualKeyExW=lambda *args: 0xE048 if vk == 38 else 0x1E)
    sent = []
    transport.post = lambda *args: sent.append(args)
    transport.key(11, vk, down, repeated, alt)
    hwnd, message, key, bits = sent[0]
    assert message == expected and key == vk
    assert bits & 65535 == 1
    assert bool(bits & (1 << 24)) == (vk == 38)
    assert bool(bits & (1 << 29)) == alt
    assert bool(bits & (1 << 30)) == (repeated or not down)
    assert bool(bits & (1 << 31)) == (not down)


def test_background_compatibility_notice_does_not_claim_processing(monkeypatch):
    transport = Transport()
    monkeypatch.setattr('macroflow.background.NativeWindowMessages', lambda target: transport)
    notices = []
    engine = Engine(notify=lambda *args: notices.append(args))
    engine.input_target = InputTarget(101, 42)
    engine.make_driver(RunControl())
    assert notices == [('warning', {'message': 'Destino encontrado. Se enviarán mensajes en segundo plano; la respuesta de la aplicación no está verificada.'})]
