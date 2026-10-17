import json
from macroflow.config import DEFAULTS, Settings, validate_settings
from macroflow.ui.main_window import MainWindow
from macroflow.ui.theme import accent_color
from macroflow.ui.playback_panel import PAUSED


def test_default_red_custom_color_persistence_and_legacy_migration(tmp_path):
    assert DEFAULTS['accent'] == '#ff1744'
    settings = Settings(tmp_path)
    settings.data['accent'] = '#2879ED'
    settings.save()
    assert Settings(tmp_path).data['accent'] == '#2879ed'
    data = dict(settings.data, accent='#555555')
    settings.path.write_text(json.dumps(data), encoding='utf-8')
    assert Settings(tmp_path).data['accent'] == DEFAULTS['accent']
    assert validate_settings(dict(DEFAULTS, accent='#555555'))['accent'] == '#555555'


def test_custom_accent_reaches_main_floating_panels_and_pause_stays_yellow(qapp, tmp_path):
    window = MainWindow(Settings(tmp_path), enable_hooks=False)
    window.show()
    for theme in ('dark', 'light'):
        window.settings.data.update(theme=theme, accent='#2879ed')
        window.apply_theme()
        qapp.processEvents()
        for widget in (window.nav[0], window.lock_switch, window.playback_panel.stop, window.record_indicator.stop, window.capture_dialog):
            assert accent_color(widget).name() == '#2879ed'
        window.playback_panel.update_phase('running', 'Prueba')
        window.record_indicator.update_phase('running')
        assert window.playback_panel.progress_accent == '#2879ed'
        assert window.playback_panel.pause.accent == '#2879ed'
        assert window.record_indicator.stop.accent == '#2879ed'
        window.playback_panel.update_phase('paused', 'Prueba')
        window.record_indicator.update_phase('paused')
        assert window.playback_panel.progress_accent == PAUSED
        assert window.record_indicator.stop.accent == PAUSED
    window.close()


def test_cancel_color_picker_keeps_current_value(qapp, tmp_path, monkeypatch):
    from PySide6.QtGui import QColor
    window = MainWindow(Settings(tmp_path), enable_hooks=False)
    before = window.setting_accent.text()
    monkeypatch.setattr('macroflow.ui.main_window.ColorDialog.exec', lambda dialog: 0)
    window.choose_accent()
    assert window.setting_accent.text() == before
    def accept_blue(dialog):
        dialog.set_color(QColor('#2879ed'))
        return 1
    monkeypatch.setattr('macroflow.ui.main_window.ColorDialog.exec', accept_blue)
    window.choose_accent()
    assert window.setting_accent.text() == '#2879ed'
    window.close()
