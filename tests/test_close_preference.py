from macroflow.config import Settings, DEFAULTS, validate_settings
from macroflow.ui.main_window import MainWindow


def test_close_preference_defaults_migration_and_persistence(qapp, tmp_path):
    old = dict(DEFAULTS)
    old.pop('minimize_on_close')
    assert validate_settings(old)['minimize_on_close'] is True
    window = MainWindow(Settings(tmp_path), enable_hooks=False)
    assert window.setting_close.isChecked()
    window.setting_close.setChecked(False)
    window.save_settings()
    assert Settings(tmp_path).data['minimize_on_close'] is False
    window.close()


def test_titlebar_close_hides_and_tray_can_restore_and_exit(qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QSystemTrayIcon
    monkeypatch.setattr(QSystemTrayIcon, 'isSystemTrayAvailable', lambda: True)
    window = MainWindow(Settings(tmp_path), enable_hooks=False)
    window.show()
    window.enable_hooks = True
    window.close()
    qapp.processEvents()
    assert not window.isVisible() and not window.closed and window.tray.isVisible()
    assert window.timer.isActive() and not window.engine.shutting_down
    window.tray_show.trigger()
    assert window.isVisible() and not window.isMinimized()
    window.close()
    window.tray_activated(QSystemTrayIcon.ActivationReason.Trigger)
    assert window.isVisible()
    window.close()
    window.tray_exit.trigger()
    assert window.closed and not window.isVisible()
    assert not window.tray.isVisible()


def test_missing_tray_never_hides_window_without_a_way_back(qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QSystemTrayIcon
    monkeypatch.setattr(QSystemTrayIcon, 'isSystemTrayAvailable', lambda: False)
    window = MainWindow(Settings(tmp_path), enable_hooks=False)
    window.show()
    window.enable_hooks = True
    window.close()
    assert window.isVisible() and not window.closed and window.tray is None
    assert 'bandeja' in window.notice.message.text()
    window.request_exit()
