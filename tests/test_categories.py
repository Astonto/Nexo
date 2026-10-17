from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from macroflow.config import Settings
from macroflow.models import Macro
from macroflow.storage import Library
from macroflow.triggers import InputRouter
from macroflow.ui.dialogs import MacroDialog
from macroflow.ui.main_window import MainWindow
from macroflow.ui.widgets import CategoryField


def test_category_dropdown_suggests_substring_ignores_case_and_deduplicates(qapp):
    field = CategoryField(['Juegos', 'Trabajo', 'juegos', '  Trabajo  ', 'Edición'], 'General')
    assert [field.itemText(i) for i in range(field.count())] == ['Edición', 'General', 'Juegos', 'Trabajo']
    field.show()
    field.lineEdit().selectAll()
    QTest.keyClicks(field.lineEdit(), 'UEG')
    qapp.processEvents()
    assert field.completer().completionPrefix() == 'UEG'
    assert field.completer().completionCount() == 1
    assert field.completer().currentCompletion() == 'Juegos'
    popup = field.completer().popup()
    assert popup.isVisible()
    QTest.mouseClick(popup.viewport(), Qt.MouseButton.LeftButton, pos=popup.visualRect(popup.model().index(0,0)).center())
    assert field.currentText() == 'Juegos'
    field.setCurrentIndex(field.findText('Trabajo'))
    assert field.text() == 'Trabajo'
    field.setText('  juegos ')
    assert field.text() == 'Juegos'
    assert field.lineEdit().maxLength() == 80
    field.close()


def test_new_category_persists_with_macro_and_is_suggested_after_reopen(qapp, tmp_path):
    library = Library(tmp_path)
    macro = Macro(name='Configuración')
    dialog = MacroDialog(macro, InputRouter(lambda *args: None), lambda m: None, categories=['Trabajo'])
    dialog.category.setText('  Automatización  ')
    dialog.accept()
    assert dialog.result_macro.category == 'Automatización'
    library.save(dialog.result_macro)
    stored = Library(tmp_path).all()
    reopened = MacroDialog(stored[0], dialog.router, lambda m: None, categories=[m.category for m in stored])
    reopened.category.completer().setCompletionPrefix('mATiz')
    assert reopened.category.completer().currentCompletion() == 'Automatización'
    assert reopened.category.text() == 'Automatización'
    reopened.reject()


def test_cancel_does_not_change_category_or_add_phantom_category(qapp):
    macro = Macro(name='Sin cambios', category='Trabajo')
    dialog = MacroDialog(macro, InputRouter(lambda *args: None), lambda m: None, categories=['Juegos'])
    dialog.category.setText('No guardar')
    dialog.reject()
    assert dialog.result_macro is None and macro.category == 'Trabajo'


def test_configuration_receives_categories_from_entire_current_library(qapp, tmp_path, monkeypatch):
    window = MainWindow(Settings(tmp_path), enable_hooks=False)
    window.new_macro(name='Primera')
    window.current.category = 'Juegos'
    window.save_current()
    window.new_macro(name='Segunda')
    window.current.category = 'Trabajo'
    captured = []
    def inspect(dialog):
        captured.extend(dialog.category.itemText(i) for i in range(dialog.category.count()))
        return 0
    monkeypatch.setattr(MacroDialog, 'exec', inspect)
    window.configure_macro()
    assert set(captured) == {'Juegos', 'Trabajo'}
    window.close()
