import copy
import time
import pytest
from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QWidget, QPushButton
from macroflow.config import Settings, DEFAULTS, DEFAULT_HOTKEYS, validate_settings
from macroflow.models import Macro, Event
from macroflow.triggers import InputRouter
from macroflow.ui.main_window import MainWindow
from macroflow.ui.dialogs import AssignDialog


def keyboard_window(tmp_path, driver):
    window = MainWindow(Settings(tmp_path), enable_hooks=False)
    window.router.macro_allowed = lambda: True
    window.engine.driver_factory = lambda: driver
    window.click_kind.setCurrentIndex(window.click_kind.findData('keyboard'))
    window.repeat_key.setText('Space')
    window.click_infinite.setChecked(True)
    window.click_countdown.setValue(10)
    window.keyboard_hold_button.setText('X1')
    return window


def test_old_clicker_preferences_migrate_without_changing_keyboard_hotkey(tmp_path):
    old = copy.deepcopy(DEFAULTS)
    old['clicker'].pop('hold_button')
    restored = validate_settings(old)
    assert restored['clicker']['hold_button'] == ''
    assert restored['hotkeys']['click'] == DEFAULT_HOTKEYS['click']


def test_hold_router_release_repeats_injected_and_blocking():
    events = []
    router = InputRouter(lambda *args: events.append(args))
    for key in ('x1', 'x2', 'mbutton', 'mouseleft', 'mouseright', ord('J')):
        binding = key.upper() if isinstance(key, str) else 'J'
        router.configure([], dict(DEFAULT_HOTKEYS, keyboard_repeat_press=binding))
        events.clear()
        assert not router.process(key, True, injected=True)
        assert router.process(key, True)
        assert router.process(key, True)
        assert router.process(key, False)
        assert events == [('keyboard_repeat_press', ''), ('keyboard_repeat_release', '')]
        router.set_suspended(True)
        assert not router.process(key, True)
        router.set_suspended(False)
    router.macro_allowed = lambda: False
    assert not router.process(ord('J'), True)


@pytest.mark.parametrize('button,expected', [(Qt.MouseButton.LeftButton, 'MOUSELEFT'), (Qt.MouseButton.RightButton, 'MOUSERIGHT'), (Qt.MouseButton.MiddleButton, 'MBUTTON'), (Qt.MouseButton.BackButton, 'X1'), (Qt.MouseButton.ForwardButton, 'X2')])
def test_assignment_captures_every_standard_mouse_button(qapp, button, expected):
    owner = QWidget()
    router = InputRouter(lambda *args: None)
    dialog = AssignDialog(router, owner, allow_all_mouse=True)
    dialog.show()
    QTest.mouseClick(dialog, button, pos=QPoint(8, 8))
    assert dialog.value == expected and dialog.result() == 1
    assert router.capture is None and not router.capture_all_mouse
    owner.close()


def test_assignment_keyboard_combination_and_cancel_button(qapp):
    owner = QWidget()
    router = InputRouter(lambda *args: None)
    dialog = AssignDialog(router, owner, allow_all_mouse=True)
    dialog.show()
    QTest.keyClick(dialog, Qt.Key.Key_K, Qt.KeyboardModifier.ControlModifier)
    assert dialog.value == 'Ctrl+K'
    canceled = AssignDialog(router, owner, allow_all_mouse=True)
    canceled.show()
    cancel = next(button for button in canceled.findChildren(QPushButton) if button.text() == 'Cancelar')
    QTest.mouseClick(cancel, Qt.MouseButton.LeftButton)
    assert canceled.value is None and canceled.result() == 0
    assert router.capture is None and not router.capture_all_mouse
    owner.close()


def test_modifier_release_stops_hold_but_injected_release_does_not():
    events = []
    router = InputRouter(lambda *args: events.append(args))
    router.configure([], dict(DEFAULT_HOTKEYS, keyboard_repeat_press='Ctrl+K'))
    router.process(17, True)
    router.process(ord('K'), True)
    router.process(ord('K'), False, injected=True)
    assert router.hold_active == ord('K')
    router.process(17, False)
    assert router.hold_active is None
    assert events == [('keyboard_repeat_press', ''), ('keyboard_repeat_release', '')]


def test_left_capture_is_opt_in_and_does_not_intercept_nexo_buttons():
    captured = []
    router = InputRouter(lambda *args: None)
    router.capture = captured.append
    assert not router.process('mouseleft', True)
    router.process('mouseleft', False)
    router.capture_all_mouse = True
    router.capture_mouse_guard = lambda: False
    assert not router.process('mouseleft', True)
    router.process('mouseleft', False)
    assert captured == []
    router.capture_mouse_guard = lambda: True
    assert router.process('mouseleft', True)
    assert captured == ['MOUSELEFT']


def test_assign_and_clear_hold_field_do_not_change_existing_clicker_hotkey(qapp, tmp_path, driver, monkeypatch):
    window = keyboard_window(tmp_path, driver)
    window.show()
    window.change_page(3)
    original = window.settings.data['hotkeys']['click']
    def assign(dialog):
        assert dialog.allow_all_mouse
        dialog.assign('Ctrl+K')
        return dialog.result()
    monkeypatch.setattr(AssignDialog, 'exec', assign)
    QTest.mouseClick(window.keyboard_hold_assign, Qt.MouseButton.LeftButton)
    assert window.keyboard_hold_button.text() == 'Ctrl+K'
    assert window.settings.data['hotkeys']['click'] == original
    QTest.mouseClick(window.keyboard_hold_clear, Qt.MouseButton.LeftButton)
    assert window.keyboard_hold_button.text() == ''
    assert 'keyboard_repeat_press' not in window.router_controls()
    window.close()


def test_hold_mouse_repeats_keyboard_immediately_and_release_stops(qapp, tmp_path, driver):
    window = keyboard_window(tmp_path, driver)
    original_hotkey = window.settings.data['hotkeys']['click']
    window.router.process('x1', True)
    assert window.engine.task == 'click' and window.engine.phase == 'running'
    limit = time.monotonic() + 2
    while not driver.events and time.monotonic() < limit:
        time.sleep(.005)
    assert driver.events and all(event.kind.startswith('key_') for event in driver.events)
    window.router.process('x1', False)
    window.engine.thread.join(2)
    assert not window.engine.busy and not driver.held_keys
    assert window.settings.data['hotkeys']['click'] == original_hotkey
    window.close()
    assert Settings(tmp_path).data['clicker']['hold_button'] == 'X1'


def test_released_before_ui_press_is_processed_never_starts(qapp, tmp_path, driver):
    window = keyboard_window(tmp_path, driver)
    pending = []
    window.router.callback = lambda *args: pending.append(args)
    window.router.process('x1', True)
    window.router.process('x1', False)
    for action, identifier in pending:
        window.on_hotkey(action, identifier)
    assert not window.engine.busy and not driver.events
    window.close()


def test_mouse_mode_keeps_existing_keyboard_toggle_and_hold_conflicts(qapp, tmp_path, driver):
    window = keyboard_window(tmp_path, driver)
    window.click_countdown.setValue(0)
    window.on_hotkey('click', '')
    assert window.engine.task == 'click'
    window.router.process('x1', True)
    window.router.process('x1', False)
    assert window.engine.task == 'click'
    window.on_hotkey('click', '')
    window.engine.thread.join(2)
    window.click_kind.setCurrentIndex(window.click_kind.findData('mouse'))
    window.click_countdown.setValue(0)
    window.on_hotkey('click', '')
    assert window.engine.task == 'click'
    window.on_hotkey('click', '')
    window.engine.thread.join(2)
    window.macros['occupied'] = Macro(name='Ocupada', id='occupied', trigger='X1', enabled=True)
    window.click_kind.setCurrentIndex(window.click_kind.findData('keyboard'))
    assert window.keyboard_hold_button.text() == ''
    assert window.settings.data['hotkeys']['click'] == DEFAULT_HOTKEYS['click']
    window.close()


def test_late_release_cannot_cancel_an_unrelated_task(qapp, tmp_path, driver):
    window = keyboard_window(tmp_path, driver)
    window.router.process('x1', True)
    window.engine.stop()
    window.engine.thread.join(2)
    window.engine.play(Macro(name='Otra', events=[Event('wait', 5)]), seconds=0)
    window.router.process('x1', False)
    assert window.engine.busy and window.engine.task == 'play'
    window.close()
