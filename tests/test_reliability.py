import copy
import threading
import pytest
from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtTest import QTest
from macroflow.config import DEFAULTS, Settings, validate_settings
from macroflow.models import Macro, Event, ValidationError
from macroflow.persistence import SaveService
from macroflow.storage import Library
from macroflow.ui.floating import bounded_position
from macroflow.ui.main_window import MainWindow


def test_notifications_visible_without_reflow_and_warning_not_overwritten(qapp, tmp_path):
    window = MainWindow(Settings(tmp_path), enable_hooks=False)
    window.show()
    qapp.processEvents()
    before = window.pages.geometry()
    window.statusBar().showMessage('Macro añadida a la cola.', 5000)
    assert window.notice.isVisible() and window.statusBar().isHidden()
    assert window.notice.message.text() == 'Macro añadida a la cola.'
    window.on_engine_event('warning', {'message': 'No se pudo guardar.'})
    window.statusBar().showMessage('Guardado automáticamente · 12:00', 4000)
    window.statusBar().showMessage('Otra información', 4000)
    assert window.notice.message.text() == 'No se pudo guardar.'
    assert not window.notice.timeout.isActive()
    assert window.pages.geometry() == before
    assert window.rect().contains(window.notice.geometry())
    QTest.mouseClick(window.notice.dismiss, Qt.MouseButton.LeftButton)
    assert not window.notice.isVisible()
    window.close()


def test_autoclicker_all_options_roundtrip_and_old_settings_migrate(qapp, tmp_path):
    original = copy.deepcopy(DEFAULTS)
    original.pop('clicker')
    assert validate_settings(original)['clicker'] == DEFAULTS['clicker']
    window = MainWindow(Settings(tmp_path), enable_hooks=False)
    values = dict(kind='keyboard', button='x2', double=True, position='fixed', x=-123, y=456,
                  key='Ctrl+G', hours=1, minutes=2, seconds=3, milliseconds=40,
                  variable=True, interval_max=4000.0, repetitions=55, infinite=True,
                  duration=12.5, countdown=7, hold_button='X1', ignore_ctrl=True, ignore_alt=False, ignore_shift=False, ignore_win=False)
    for name, value in values.items():
        field = window.clicker_fields[name]
        if hasattr(field, 'findData'):
            field.setCurrentIndex(field.findData(value))
        elif hasattr(field, 'setChecked'):
            field.setChecked(value)
        elif hasattr(field, 'setValue'):
            field.setValue(value)
        else:
            field.setText(value)
    window.close()
    reopened = MainWindow(Settings(tmp_path), enable_hooks=False)
    assert reopened.settings.data['clicker'] == values
    reopened.cache_clicker_settings()
    assert reopened.settings.data['clicker'] == values
    reopened.close()


def test_close_preferences_failure_keeps_window_and_writers_alive(qapp, tmp_path, monkeypatch):
    window = MainWindow(Settings(tmp_path), enable_hooks=False)
    window.show()
    errors = []
    monkeypatch.setattr(window, 'show_error', errors.append)
    save = window.settings.save
    def fail(*args):
        raise OSError('disk full')
    monkeypatch.setattr(window.settings, 'save', fail)
    assert not window.close()
    assert errors and 'preferencias' in errors[-1]
    assert window.isVisible() and not window.closed
    assert not window.writer.stopping and not window.recovery_writer.stopping
    assert not window.engine.shutting_down and window.timer.isActive()
    monkeypatch.setattr(window.settings, 'save', save)
    assert window.close()


def test_close_recovery_failure_is_reported_and_can_retry(qapp, tmp_path, monkeypatch):
    window = MainWindow(Settings(tmp_path), enable_hooks=False)
    errors = []
    monkeypatch.setattr(window, 'show_error', errors.append)
    flush = window.recovery_writer.flush
    monkeypatch.setattr(window.recovery_writer, 'flush', lambda: False)
    assert not window.close()
    assert 'recuperación' in errors[-1] and not window.closed
    assert not window.writer.stopping
    monkeypatch.setattr(window.recovery_writer, 'flush', flush)
    assert window.close()


def test_writer_retries_failed_snapshot_without_losing_latest_pending(tmp_path, monkeypatch):
    library = Library(tmp_path)
    service = SaveService(library, lambda *args: None)
    original = library.save
    def fail(macro):
        raise OSError('disk full')
    monkeypatch.setattr(library, 'save', fail)
    macro = Macro(name='Estado pendiente')
    service.submit(macro)
    assert not service.flush() and macro.id in service.failed
    monkeypatch.setattr(library, 'save', original)
    service.retry_failed()
    assert service.flush()
    assert library.load(macro.id).name == 'Estado pendiente'
    assert not service.failed_snapshots and service.close()


@pytest.mark.parametrize('position', [QPoint(-4000,-2000), QPoint(-20,1040), QPoint(4000,2000), QPoint(-1500,500)])
def test_panel_bounds_handle_negative_coordinates_gaps_and_taskbar(position):
    areas = [QRect(-1920,0,1920,1040), QRect(0,0,1920,1040)]
    size = QSize(460,76)
    target = bounded_position(position, size, areas)
    assert any(area.contains(QRect(target, size)) for area in areas)
    if position == QPoint(-1500,500):
        assert target == position


def test_floating_panels_recover_on_show_and_remain_inside_on_drag(qapp, tmp_path):
    window = MainWindow(Settings(tmp_path), enable_hooks=False)
    for panel in (window.playback_panel, window.record_indicator):
        panel.move(50000, 50000)
        panel.show()
        qapp.processEvents()
        assert any(screen.availableGeometry().contains(panel.frameGeometry()) for screen in qapp.screens())
        panel.hide()
    panel = window.playback_panel
    panel.begin_drag(panel.pos())
    panel.drag_to(QPoint(-50000, -50000))
    assert any(screen.availableGeometry().contains(panel.frameGeometry()) for screen in qapp.screens())
    panel.end_drag()
    window.close()


def test_progress_uses_completed_actions_in_both_views_and_resets(qapp, tmp_path):
    window = MainWindow(Settings(tmp_path), enable_hooks=False)
    for index in (0,4,12,0):
        window.on_engine_event('progress', dict(index=index,total=12,iterations=0,elapsed=.1))
        assert window.progress.value() == round(index / 12 * 100)
        assert window.playback_panel.progress_ratio == index / 12
        assert f'{index} / 12' in window.playback_panel.detail.text()
        assert f'{index} de 12' in window.play_progress.text()
    window.close()


def test_picker_displays_actual_configured_emergency(qapp, tmp_path, monkeypatch):
    class Picker:
        def __init__(self, callback): pass
        def start(self): pass
        def stop(self): pass
    monkeypatch.setattr('macroflow.ui.main_window.PositionPicker', Picker)
    window = MainWindow(Settings(tmp_path), enable_hooks=False)
    window.settings.data['hotkeys']['emergency'] = 'End'
    window.pick_position()
    assert window.record_indicator.subtitle.text() == 'End cancela la selección'
    assert 'Pause' not in window.record_indicator.subtitle.text()
    window.cancel_picker()
    window.close()


def test_invalid_clicker_preferences_rejected():
    for key, value in [('kind','unknown'), ('double',1), ('x',1.5), ('key', None)]:
        data = copy.deepcopy(DEFAULTS)
        data['clicker'][key] = value
        with pytest.raises(ValidationError):
            validate_settings(data)


def test_warning_is_visible_on_modal_capture_and_returns_to_main(qapp, tmp_path):
    window = MainWindow(Settings(tmp_path), enable_hooks=False)
    window.show()
    window.capture_dialog.begin('Avisos', .1, 'F3')
    window.on_engine_event('warning', {'message': 'Protección de captura no disponible.'})
    assert window.notice.parentWidget() is window.capture_dialog
    assert window.notice.isVisible()
    window.capture_dialog.hide()
    window.sync_state()
    assert window.notice.parentWidget() is window
    window.close()


def test_retry_never_queues_old_failure_behind_newer_inflight_save(tmp_path, monkeypatch):
    library = Library(tmp_path)
    service = SaveService(library, lambda *args: None)
    original = library.save
    monkeypatch.setattr(library, 'save', lambda macro: (_ for _ in ()).throw(OSError('full')))
    macro = Macro(name='Anterior')
    service.submit(macro)
    assert not service.flush()
    entered, release = threading.Event(), threading.Event()
    def slow_save(value):
        entered.set()
        assert release.wait(2)
        original(value)
    monkeypatch.setattr(library, 'save', slow_save)
    macro.name = 'Más reciente'
    service.submit(macro)
    try:
        assert entered.wait(2)
        service.retry_failed()
        assert macro.id not in service.pending
    finally:
        release.set()
    assert service.flush()
    assert library.load(macro.id).name == 'Más reciente'
    assert service.close()
