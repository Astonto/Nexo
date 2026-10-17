from __future__ import annotations

import argparse
import json
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .windows import enable_dpi_awareness
from . import __version__


def resource_path(name):
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return root / "resources" / name


def main(argv=None):
    parser = argparse.ArgumentParser(description="Nexo · automatización local")
    parser.add_argument("--smoke-test", action="store_true", help="Abrir y cerrar la interfaz sin instalar escuchas globales.")
    parser.add_argument("--smoke-report", help="Guardar el resultado de la prueba de inicio en JSON.")
    args = parser.parse_args(argv)
    enable_dpi_awareness()
    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QFont, QFontDatabase, QIcon
    from PySide6.QtWidgets import QApplication, QMessageBox
    from .config import Settings
    from .ui.main_window import MainWindow

    app = QApplication(sys.argv[:1])
    from .ui.widgets import install_display_text_policy
    install_display_text_policy(app)
    app.setApplicationName("Nexo")
    app.setOrganizationName("Nexo")
    QFontDatabase.addApplicationFont(str(resource_path("Inter.ttf")))
    app.setFont(QFont("Inter", 10))
    app.setWindowIcon(QIcon(str(resource_path("nexo.ico"))))
    from .single_instance import SingleInstance, instance_name

    from .config import data_directory
    instance = SingleInstance(instance_name(data_directory() if args.smoke_test else None), app)
    try:
        if not instance.acquire():
            return 0
    except RuntimeError as exc:
        QMessageBox.warning(None, "Nexo", str(exc))
        return 1
    app.aboutToQuit.connect(instance.close)
    settings = Settings()
    log = logging.getLogger("macroflow")
    log.setLevel(logging.INFO)
    try:
        handler = RotatingFileHandler(settings.directory / "errors.log", maxBytes=256_000, backupCount=2, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        log.addHandler(handler)
    except OSError:
        log.addHandler(logging.NullHandler())

    window = MainWindow(settings, enable_hooks=not args.smoke_test)
    instance.attach(window.show_from_tray)

    def exception_hook(exc_type, exc, tb):
        window.engine.stop()
        log.error("ui_failure type=%s", exc_type.__name__)
        QMessageBox.critical(window, "Nexo", "Se detectó un error de interfaz y se detuvo la automatización. Guarda o exporta tu trabajo antes de continuar.")
    sys.excepthook = exception_hook
    window.show()
    if args.smoke_test:
        def smoke():
            import threading
            from .playback import PynputDriver
            from .windows import PrivacyProbe
            provider = []
            def check_provider():
                probe = PrivacyProbe()
                provider.append(probe.automation is not None)
                probe.close()
            provider_thread = threading.Thread(target=check_provider, daemon=True)
            provider_thread.start()
            provider_thread.join(5)
            driver = PynputDriver()
            from .background import WindowMessageDriver
            from .models import Event
            window.capture_dialog.begin("Comprobación del paquete", .05, "Ctrl + Alt + Enter")
            window.capture_dialog.update_events([Event("key_down", key="vk:65"), Event("key_up", key="vk:65")])
            window.capture_dialog.set_phase("paused")
            window.record_mode.setCurrentIndex(window.record_mode.findData("fixed"))
            window.record_indicator.update_phase("paused")
            requires_stop = not window.capture_dialog.finish_button.isEnabled()
            window.capture_dialog.stop_for_review()
            review_enabled = window.capture_dialog.finish_button.isEnabled()
            window.playback_panel.update_phase("paused", "Comprobación del paquete")
            window.playback_panel.set_progress(2, 8, 1, "00:00:01.250")
            report = {"window_visible": window.isVisible(), "pages": window.pages.count(),
                      "icon_loaded": not app.windowIcon().isNull(), "frozen": bool(getattr(sys, "frozen", False)),
                      "resources": all(resource_path(name).exists() for name in ("nexo.ico", "nexo.svg", "defaults.json", "Inter.ttf", "check.svg", "chevron-down.svg", "chevron-up.svg")),
                      "global_hooks_disabled": True, "privacy_provider_loaded": bool(provider and provider[0]),
                      "input_driver_loaded": driver.resolve_key("key:enter") is not None,
                      "product_name": app.applicationName(), "version": __version__, "accent": settings.data["accent"],
                      "home": window.page_names[0] == "Inicio", "capture_strip": window.capture_dialog is not None,
                      "sidebar_pages": len(window.nav), "home_message_interval": window.home.message_timer.interval(),
                      "home_message_count": len(window.home.MESSAGES),
                      "fixed_countdown_hidden": window.record_countdown_row.isHidden() and window.record_countdown_label.isHidden(),
                      "recording_indicator_size": list(window.record_indicator.size().toTuple()),
                      "recording_indicator_paused": window.record_indicator.text.text() == "GRABACIÓN EN PAUSA",
                      "visual_editor": window.editor.visual.model() is window.editor.table.model(),
                      "settings_tabs": window.settings_tabs.count(),
                      "readonly_shortcuts": all(field.isReadOnly() for field in window.setting_hotkeys.values()),
                      "keyboard_repeater": window.click_kind.findData("keyboard") >= 0,
                      "recording_exclusions": len(settings.data["excluded_keys"]),
                      "capture_flow": window.capture_dialog.keys.count() == 3,
                      "capture_timing_editable_paused": window.capture_dialog.delay.isEnabled(),
                      "capture_save_requires_stop": requires_stop and review_enabled,
                      "window_target_selector": window.target_combo.count() >= 1 and window.target_combo.currentData() is None,
                      "stable_bottom": window.statusBar().isHidden() and window.stop_all.isHidden(),
                      "background_delivery": window.target_delivery.itemData(0) == "background" and callable(WindowMessageDriver.dispatch),
                      "flat_dark_palette": "#000000" in window.styleSheet() and "#212225" in window.styleSheet(),
                      "modifier_exclusions_available": all(window.restrictions.preset.findData(vk) >= 0 for vk in (16, 17, 18)),
                      "playback_panel_size": list(window.playback_panel.size().toTuple()),
                      "playback_pause_state": window.playback_panel.title.text() == "EN PAUSA" and window.playback_panel.pause.text() == "Reanudar",
                      "playback_progress": window.playback_panel.progress_ratio == 2 / 8 and "rep. completadas" in window.playback_panel.detail.text()}
            if args.smoke_report:
                Path(args.smoke_report).write_text(json.dumps(report, indent=2), encoding="utf-8")
            window.close()
        QTimer.singleShot(1000, smoke)
    return app.exec()
