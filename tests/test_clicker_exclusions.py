import copy
import pytest
from PySide6.QtWidgets import QTabWidget
from macroflow.models import ClickOptions, Macro, ValidationError, interval_seconds
from macroflow.config import DEFAULTS, Settings, validate_settings
from macroflow.triggers import InputRouter
from macroflow.ui.main_window import MainWindow


@pytest.mark.parametrize('milliseconds', [1, 2, 9])
def test_sub_ten_ms_interval_is_valid(milliseconds):
    value = interval_seconds(milliseconds=milliseconds)
    assert value == milliseconds / 1000
    ClickOptions(interval=value, interval_max=.009).validate()


def test_zero_interval_remains_invalid():
    with pytest.raises(ValidationError):
        interval_seconds(milliseconds=0)


@pytest.mark.parametrize('modifier,vk', [('Ctrl', 162), ('Alt', 164), ('Shift', 160), ('Win', 91)])
def test_excluded_modifier_can_be_held_before_or_during_activation(modifier, vk):
    events = []
    router = InputRouter(lambda *args: events.append(args))
    controls = dict(DEFAULTS['hotkeys'], keyboard_repeat_press='X1')
    router.configure([], controls, ignored_hold_modifiers=[modifier])
    assert not router.process(vk, True)
    assert router.process('x1', True)
    assert events == [('keyboard_repeat_press', '')]
    assert not router.process(vk, False)
    assert router.hold_active == 'x1'
    router.process(vk, True)
    assert router.hold_active == 'x1'
    router.process('x1', False)
    assert events[-1] == ('keyboard_repeat_release', '')


def test_unselected_modifiers_still_require_exact_binding():
    events = []
    router = InputRouter(lambda *args: events.append(args))
    router.configure([], dict(DEFAULTS['hotkeys'], keyboard_repeat_press='X1'))
    router.process(162, True)
    assert not router.process('x1', True) and not events


def test_explicit_modifier_is_required_even_when_ignored():
    events = []
    router = InputRouter(lambda *args: events.append(args))
    router.configure([], dict(DEFAULTS['hotkeys'], keyboard_repeat_press='Ctrl+X1'), ignored_hold_modifiers=['Ctrl', 'Alt'])
    assert not router.process('x1', True)
    router.process('x1', False)
    router.process(162, True)
    router.process(164, True)
    router.process('x1', True)
    assert events[-1] == ('keyboard_repeat_press', '')
    router.process(164, False)
    assert router.hold_active == 'x1'
    router.process(162, False)
    assert events[-1] == ('keyboard_repeat_release', '')


def test_exact_macro_binding_keeps_priority_over_ignored_modifier():
    events = []
    macro = Macro(name='Otra', trigger='Ctrl+X1', enabled=True)
    router = InputRouter(lambda *args: events.append(args))
    router.configure([macro], dict(DEFAULTS['hotkeys'], keyboard_repeat_press='X1'), ignored_hold_modifiers=['Ctrl'])
    router.process(162, True)
    router.process('x1', True)
    assert events == [('macro_press', macro.id)]


def test_old_preferences_migrate_with_exclusions_disabled():
    data = copy.deepcopy(DEFAULTS)
    for key in ('ctrl', 'alt', 'shift', 'win'):
        data['clicker'].pop('ignore_'+key)
    restored = validate_settings(data)
    assert all(restored['clicker']['ignore_'+key] is False for key in ('ctrl','alt','shift','win'))


def test_exclusion_flags_require_booleans():
    data = copy.deepcopy(DEFAULTS)
    data['clicker']['ignore_ctrl'] = 'yes'
    with pytest.raises(ValidationError):
        validate_settings(data)


def test_exclusions_tab_persists_and_changes_only_clicker(qapp, tmp_path):
    window = MainWindow(Settings(tmp_path), enable_hooks=False)
    tabs = next(widget for widget in window.findChildren(QTabWidget) if any(widget.tabText(i)=='Intervalos y límites' for i in range(widget.count())))
    assert tabs.tabText(2) == 'Exclusiones'
    original_hotkeys = copy.deepcopy(window.settings.data['hotkeys'])
    window.click_kind.setCurrentIndex(window.click_kind.findData('keyboard'))
    window.keyboard_hold_button.setText('X1')
    window.click_ignored_modifiers['ctrl'].setChecked(True)
    assert window.router.ignored_hold_modifiers == frozenset({'Ctrl'})
    window.close()
    reopened = MainWindow(Settings(tmp_path), enable_hooks=False)
    assert reopened.click_ignored_modifiers['ctrl'].isChecked()
    assert not reopened.click_ignored_modifiers['alt'].isChecked()
    assert reopened.settings.data['hotkeys'] == original_hotkeys
    reopened.close()
