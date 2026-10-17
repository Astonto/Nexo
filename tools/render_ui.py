
import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication, QTabWidget
from macroflow.config import Settings
from macroflow.models import Event
from macroflow.ui.main_window import MainWindow
from macroflow.ui.widgets import install_display_text_policy

parser = argparse.ArgumentParser()
parser.add_argument("output", type=Path)
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
app = QApplication([])
install_display_text_policy(app)
QFontDatabase.addApplicationFont(str(root / "resources" / "Inter.ttf"))
app.setFont(QFont("Inter", 10))

def settle(milliseconds=180):
    loop = QEventLoop()
    QTimer.singleShot(milliseconds, loop.quit)
    loop.exec()

with tempfile.TemporaryDirectory(prefix="nexo-ui-") as directory:
    window = MainWindow(Settings(directory), enable_hooks=False)
    window.resize(1120, 690)
    window.show()
    window.new_macro(name="Secuencia de prueba")
    window.editor.insert([Event("move", .25, x=600, y=400), Event("mouse_down", button="left", x=600, y=400),
                          Event("mouse_up", .05, button="left", x=600, y=400), Event("key_down", .4, key="key:ctrl_l"),
                          Event("key_down", .02, key="char:c"), Event("key_up", .02, key="char:c"),
                          Event("key_up", .02, key="key:ctrl_l"), Event("wait", 1)])
    window.current.category = "Trabajo"
    window.save_current()
    original = window.current.id
    for name, category in (("Respuesta rápida", "Trabajo"), ("Secuencia de juego", "Personal"), ("Navegación", "Personal")):
        window.new_macro(name=name)
        window.current.category = category
        window.save_current()
    window.select_macro(original)
    window.change_page(0)
    settle(1000)
    window.grab().save(str(args.output / "inicio-referencia.png"))
    window.resize(1280, 840)
    for index, name in enumerate(("inicio", "grabador", "reproductor", "autoclicker", "editor", "biblioteca", "configuracion")):
        window.change_page(index)
        settle()
        window.grab().save(str(args.output / f"{name}.png"))
    window.open_settings_tab(2)
    settle()
    window.grab().save(str(args.output / "configuracion-exclusiones.png"))
    window.open_settings_tab(1)
    settle()
    window.grab().save(str(args.output / "configuracion-atajos.png"))
    window.change_page(4)
    window.editor.view_mode.setCurrentIndex(1)
    settle()
    window.grab().save(str(args.output / "editor-detalle.png"))
    window.editor.view_mode.setCurrentIndex(0)
    from macroflow.ui.dialogs import CreateMacroDialog
    wizard = CreateMacroDialog(window)
    wizard.name.setText("Enviar respuesta")
    wizard.show()
    settle()
    wizard.grab().save(str(args.output / "nueva-macro.png"))
    wizard.advance()
    settle()
    wizard.grab().save(str(args.output / "nueva-macro-acciones.png"))
    wizard.reject()
    window.capture_dialog.begin("Secuencia de teclado", .05, "Ctrl + Alt + Enter")
    window.capture_dialog.update_events([Event(kind, .05 if kind == "key_down" else 0, key=f"vk:{key}")
                                         for key in [65, 65, 68, 74, 72, 68, 74, 72, 68, 68, 74, 190, 187, 13]
                                         for kind in ("key_down", "key_up")])
    window.capture_dialog.set_phase("running")
    settle()
    window.capture_dialog.grab().save(str(args.output / "captura-pulsaciones.png"))
    window.capture_dialog.resize(760, 500)
    window.capture_dialog.set_phase("paused")
    settle()
    window.capture_dialog.grab().save(str(args.output / "captura-compacta.png"))
    window.capture_dialog.stop_for_review()
    settle()
    window.capture_dialog.grab().save(str(args.output / "captura-revision.png"))
    window.capture_dialog.hide()
    window.resize(980, 680)
    window.change_page(0)
    settle()
    window.grab().save(str(args.output / "inicio-compacto.png"))
    geometry = {"window_width": window.width(), "home_width": window.home.width(),
                "viewport_width": window.pages.widget(0).viewport().width(),
                "home_minimum": window.home.minimumSizeHint().width(),
                "horizontal_scroll": window.pages.widget(0).horizontalScrollBar().maximum()}
    (args.output / "geometry.json").write_text(json.dumps(geometry, indent=2))
    for page_index, filename in ((1, "grabar-compacto"), (2, "macros-compacto"), (3, "autoclicker-compacto"),
                                 (4, "editor-compacto"), (5, "biblioteca-compacta"), (6, "configuracion-compacta")):
        window.change_page(page_index)
        settle()
        window.grab().save(str(args.output / f"{filename}.png"))
    window.change_page(2)
    window.target_combo.addItem("Ventana de prueba", (12345, 1))
    window.target_combo.setCurrentIndex(window.target_combo.count() - 1)
    settle()
    window.grab().save(str(args.output / "destino-segundo-plano.png"))
    window.target_delivery.setCurrentIndex(1)
    settle()
    window.grab().save(str(args.output / "destino-con-foco.png"))
    window.target_delivery.setCurrentIndex(2)
    app.processEvents()
    window.grab().save(str(args.output / "destino-activar-ventana.png"))
    window.target_delivery.setCurrentIndex(1)
    window.playback_panel.update_phase("running", "Falsotortazo")
    window.playback_panel.set_progress(4, 12, 0, "00:00:01.812")
    window.playback_panel.show()
    settle()
    window.playback_panel.grab().save(str(args.output / "panel-reproduccion.png"))
    window.playback_panel.update_phase("paused", "Falsotortazo")
    settle()
    window.playback_panel.grab().save(str(args.output / "panel-reproduccion-pausa.png"))
    window.change_page(1)
    window.record_mode.setCurrentIndex(window.record_mode.findData("fixed"))
    settle()
    window.grab().save(str(args.output / "grabar-pulsaciones-instantaneo.png"))
    window.record_indicator.update_phase("running")
    window.record_indicator.show()
    settle()
    window.record_indicator.grab().save(str(args.output / "indicador-grabacion.png"))
    window.record_indicator.update_phase("paused")
    settle()
    window.record_indicator.grab().save(str(args.output / "indicador-grabacion-pausa.png"))
    window.set_sidebar_collapsed(True)
    settle(400)
    window.grab().save(str(args.output / "barra-lateral-plegada.png"))
    window.nav[1].hint.reveal(window.nav[1])
    settle()
    window.nav[1].hint.grab().save(str(args.output / "ayuda-navegacion.png"))
    window.nav[1].dismiss_hint()
    window.capture_dialog.hide()
    window.record_indicator.hide()
    window.playback_panel.hide()
    window.change_page(2)
    window.show_notice("Otra tarea está activa. La macro no se inició; revisa la cola o detén la tarea actual.", warning=True)
    settle()
    window.grab().save(str(args.output / "aviso-visible.png"))
    window.notice.hide()
    window.change_page(5)
    window.library_table.selectRow(1)
    window.library_table.setFocus()
    settle()
    window.grab().save(str(args.output / 'biblioteca-seleccion-oscuro.png'))
    from PySide6.QtTest import QTest
    QTest.mouseMove(window.library_table.viewport(), window.library_table.visualRect(window.library_table.model().index(0, 2)).center())
    settle()
    window.grab().save(str(args.output / 'biblioteca-hover-oscuro.png'))
    window.settings.data['theme'] = 'light'
    window.apply_theme()
    for index, name in enumerate(('inicio', 'grabador', 'reproductor', 'autoclicker', 'editor', 'biblioteca', 'configuracion')):
        window.change_page(index)
        settle()
        window.grab().save(str(args.output / f'{name}-claro.png'))
        if index == 5:
            QTest.mouseMove(window.library_table.viewport(), window.library_table.visualRect(window.library_table.model().index(0, 2)).center())
            settle()
            window.grab().save(str(args.output / 'biblioteca-hover-claro.png'))
    window.show_notice('Preferencias guardadas.')
    settle()
    window.grab().save(str(args.output / 'aviso-claro.png'))
    window.settings.data['theme'] = 'dark'
    window.apply_theme()
    settle()
    window.grab().save(str(args.output / 'aviso-cambio-oscuro.png'))
    window.set_sidebar_collapsed(False, animate=False)
    for theme, name in (('dark', 'oscuro'), ('light', 'claro')):
        window.settings.data['theme'] = theme
        window.apply_theme()
        window.lock_switch.setChecked(True)
        window.notice.hide()
        settle(350)
        window.grab().save(str(args.output / f'bloqueo-{name}.png'))
        window.lock_switch.grab().save(str(args.output / f'switch-{name}.png'))
        window.lock_switch.setChecked(False)
    window.settings.data['accent'] = '#2879ed'
    for theme, name in (('dark', 'oscuro'), ('light', 'claro')):
        window.settings.data['theme'] = theme
        window.apply_theme()
        window.change_page(2)
        window.lock_switch.setChecked(True)
        window.notice.hide()
        window.playback_panel.update_phase('running', 'Secuencia de prueba')
        window.record_indicator.update_phase('running')
        window.capture_dialog.set_phase('running')
        settle(350)
        window.grab().save(str(args.output / f'acento-azul-{name}.png'))
        window.playback_panel.grab().save(str(args.output / f'panel-azul-{name}.png'))
        window.record_indicator.grab().save(str(args.output / f'indicador-azul-{name}.png'))
        window.capture_dialog.grab().save(str(args.output / f'captura-azul-{name}.png'))
        window.lock_switch.setChecked(False)
    from macroflow.ui.color_picker import ColorDialog
    for theme, name in (('dark', 'oscuro'), ('light', 'claro')):
        window.settings.data['theme'] = theme
        window.apply_theme()
        picker = ColorDialog('#ff1744', window)
        picker.show()
        settle()
        picker.grab().save(str(args.output / f'selector-color-{name}.png'))
        picker.reject()
    for theme, name in (('dark', 'oscuro'), ('light', 'claro')):
        window.settings.data['theme'] = theme
        window.apply_theme()
        window.change_page(3)
        window.click_kind.setCurrentIndex(window.click_kind.findData('keyboard'))
        window.repeat_key.setText('Space')
        window.keyboard_hold_button.setText('MOUSELEFT' if theme == 'dark' else 'Ctrl+K')
        window.notice.hide()
        settle()
        window.grab().save(str(args.output / f'autoclicker-teclado-mantener-{name}.png'))
        click_tabs = next(widget for widget in window.findChildren(QTabWidget) if any(widget.tabText(i) == 'Intervalos y límites' for i in range(widget.count())))
        window.click_ignored_modifiers['ctrl'].setChecked(True)
        click_tabs.setCurrentIndex(2)
        settle()
        window.grab().save(str(args.output / f'autoclicker-exclusiones-{name}.png'))
        window.click_ignored_modifiers['ctrl'].setChecked(False)
        click_tabs.setCurrentIndex(0)
        window.change_page(1)
        window.record_mode.setCurrentIndex(window.record_mode.findData('timed'))
        window.record_countdown.setFocus()
        window.record_countdown.lineEdit().selectAll()
        settle()
        window.grab().save(str(args.output / f'numeros-seleccion-{name}.png'))
        from macroflow.ui.dialogs import AssignDialog
        assign = AssignDialog(window.router, window, allow_all_mouse=True)
        assign.show()
        settle()
        assign.grab().save(str(args.output / f'asignar-mantener-{name}.png'))
        assign.reject()
    window.close()
    app.processEvents()
print(f"Renderizadas {len(list(args.output.glob('*.png')))} vistas en {args.output}")
