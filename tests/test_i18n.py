import ast
import json
import os
from pathlib import Path
import string
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_catalog_covers_every_message_and_preserves_placeholders():
    catalog = json.loads((ROOT / 'resources/locales/es.json').read_text(encoding='utf-8'))
    formatter = string.Formatter()
    for path in (ROOT / 'macroflow').rglob('*.py'):
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'tr':
                assert isinstance(node.args[0], ast.Constant), (path, node.lineno)
                message = node.args[0].value
                assert message in catalog, (path, node.lineno, message)
    for message, spanish in catalog.items():
        fields = lambda text: sorted((name, spec, conversion) for _, name, spec, conversion in formatter.parse(text) if name is not None)
        assert fields(message) == fields(spanish), message


@pytest.mark.parametrize('language', ['en', 'es'])
def test_full_interface_in_saved_language(language, tmp_path):
    (tmp_path / 'settings.json').write_text(json.dumps({'language': language}), encoding='utf-8')
    env = {**os.environ, 'NEXO_DATA_DIR': str(tmp_path), 'QT_QPA_PLATFORM': 'offscreen', 'PYTHONIOENCODING': 'utf-8'}
    env.pop('NEXO_LANGUAGE', None)
    program = r'''
import json, os
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QCheckBox, QLineEdit, QComboBox, QMessageBox
from macroflow.i18n import LANGUAGE, tr, install_qt_translations, _SPANISH
from macroflow.config import Settings
from macroflow.models import Event, ValidationError, number
from macroflow.ui.main_window import MainWindow
from macroflow.ui.dialogs import CreateMacroDialog, MacroDialog
from macroflow.ui.color_picker import ColorDialog

app = QApplication([])
install_qt_translations(app)
settings = Settings()
assert settings.data['language'] == LANGUAGE
window = MainWindow(settings, enable_hooks=False)
window.new_macro(name='Mi macro con texto en español')
window.current.category = 'Categoría personal'
window.editor.insert([Event('key_down', key='char:a'), Event('key_up', key='char:a')])
window.save_current()
window.refresh_library()
assert window.current.name == 'Mi macro con texto en español'
assert window.current.category == 'Categoría personal'
assert window.current.events[0].key == 'char:a'
assert window.page_names[0] == ('Home' if LANGUAGE == 'en' else 'Inicio')
assert window.setting_language.currentData() == LANGUAGE
assert window.setting_language.count() == 2
assert window.target_delivery.itemText(0) == tr('Background · Windows messages')
window.playback_panel.update_phase('paused', window.current.name)
assert window.playback_panel.title.text() == tr('PAUSED')
window.record_indicator.update_phase('paused')
assert window.record_indicator.text.text() == tr('RECORDING PAUSED')
window.capture_dialog.begin(window.current.name, .05, 'Ctrl+Enter')
window.capture_dialog.set_phase('paused')
window.capture_dialog.stop_for_review()
window.capture_dialog.hide()
wizard = CreateMacroDialog(window)
macro_dialog = MacroDialog(window.current, window.router, lambda *args: None, window)
color_dialog = ColorDialog('#ff1744', window)
if LANGUAGE == 'en':
    spanish_only = {value for key,value in _SPANISH.items() if key != value}
    for owner in (window, wizard, macro_dialog, color_dialog, window.capture_dialog, window.playback_panel, window.record_indicator):
        for widget in [owner, *owner.findChildren(QLabel), *owner.findChildren(QPushButton), *owner.findChildren(QCheckBox), *owner.findChildren(QLineEdit), *owner.findChildren(QComboBox)]:
            texts = [widget.toolTip(), widget.windowTitle(), widget.accessibleName()]
            if callable(getattr(widget, 'text', None)): texts.append(widget.text())
            if hasattr(widget, 'placeholderText'): texts.append(widget.placeholderText())
            if isinstance(widget, QComboBox) and widget is not window.target_combo:
                texts.extend(widget.itemText(i) for i in range(widget.count()))
            for text in texts:
                assert text not in spanish_only, (type(widget).__name__, text)
try:
    number(-1, tr('Interval'), 0, 1)
except ValidationError as exc:
    assert str(exc) == ('Interval: must be between 0 and 1.' if LANGUAGE == 'en' else 'Intervalo: debe estar entre 0 y 1.')
else:
    raise AssertionError('Expected a localized validation error')
other = 'es' if LANGUAGE == 'en' else 'en'
window.setting_language.setCurrentIndex(window.setting_language.findData(other))
window.save_settings()
assert settings.data['language'] == other
assert json.loads(settings.path.read_text(encoding='utf-8'))['language'] == other
assert window.hook_status.text() == tr('Preferences saved. Restart Nexo to apply the language.')
assert window.page_names[0] == tr('Home')
for dialog in (wizard, macro_dialog, color_dialog): dialog.reject()
window.exit_requested = True
window.close()
print('ok')
'''
    result = subprocess.run([sys.executable, '-c', program], cwd=ROOT, env=env, capture_output=True, text=True, encoding='utf-8', timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == 'ok'


def test_new_installation_starts_in_english_and_override_is_temporary(tmp_path):
    env = {**os.environ, 'NEXO_DATA_DIR': str(tmp_path)}
    env.pop('NEXO_LANGUAGE', None)
    result = subprocess.run([sys.executable, '-c', 'from macroflow.i18n import LANGUAGE; print(LANGUAGE)'], cwd=ROOT, env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'en'
    assert not (tmp_path / 'settings.json').exists()
    env['NEXO_LANGUAGE'] = 'es'
    result = subprocess.run([sys.executable, '-c', 'from macroflow.i18n import LANGUAGE; print(LANGUAGE)'], cwd=ROOT, env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'es'
    assert not (tmp_path / 'settings.json').exists()
