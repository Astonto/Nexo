from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from .paths import data_directory


def resource_directory():
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent)) / 'resources'


def startup_language():
    override = os.environ.get('NEXO_LANGUAGE')
    if override in ('en', 'es'):
        return override
    try:
        value = json.loads((data_directory() / 'settings.json').read_text(encoding='utf-8'))
        if isinstance(value, dict) and value.get('language') in ('en', 'es'):
            return value['language']
    except (OSError, ValueError):
        pass
    return 'en'


LANGUAGE = startup_language()
_SPANISH = json.loads((resource_directory() / 'locales' / 'es.json').read_text(encoding='utf-8'))


def tr(message, *args):
    text = _SPANISH.get(message, message) if LANGUAGE == 'es' else message
    return text.format(*args) if args else text


def install_qt_translations(app):
    from PySide6.QtCore import QLocale, QTranslator
    QLocale.setDefault(QLocale('es_ES' if LANGUAGE == 'es' else 'en_US'))
    if LANGUAGE == 'es':
        translator = QTranslator(app)
        if translator.load(str(resource_directory() / 'locales' / 'qtbase_es.qm')):
            app.installTranslator(translator)
            app._nexo_translator = translator
