from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def resource_directory():
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent)) / 'resources'


def startup_language():
    override = os.environ.get('NEXO_LANGUAGE')
    if override in ('en', 'es'):
        return override
    directory = os.environ.get('NEXO_DATA_DIR') or os.environ.get('MACROFLOW_DATA_DIR')
    if directory:
        folders = [Path(directory)]
    else:
        base = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent.parent
        portable = base / 'Nexo-data'
        try:
            portable.mkdir(parents=True, exist_ok=True)
            probe = portable / '.language-write-check'
            probe.write_bytes(b'')
            probe.unlink()
            folders = [portable]
        except OSError:
            folders = [Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'Nexo']
    try:
        value = json.loads((folders[0] / 'settings.json').read_text(encoding='utf-8'))
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
