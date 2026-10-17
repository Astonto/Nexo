import ctypes
import os
import pytest
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QStyle, QStyleOptionViewItem, QTableWidgetItem
from macroflow import triggers
from macroflow.config import Settings
from macroflow.ui.main_window import MainWindow
from macroflow.ui.widgets import LibraryTable, LibraryDelegate


def test_oem_display_uses_layout_without_changing_stored_binding(monkeypatch):
    monkeypatch.setattr(triggers, 'keyboard_layout', lambda: 123)
    monkeypatch.setattr(triggers, 'layout_character', lambda key, layout: 'Ñ' if layout == 123 else '`')
    assert triggers.display_binding('Ctrl+VK192') == 'Ctrl + Ñ'
    assert triggers.parse_binding('Ctrl+VK192').label == 'Ctrl+VK192'
    assert triggers.display_binding('J') == 'J'


@pytest.mark.skipif(os.name != 'nt', reason='Windows keyboard API')
def test_native_layout_translation_preserves_dead_key_state():
    layout = triggers.keyboard_layout()
    assert layout
    mapper = ctypes.windll.user32.MapVirtualKeyExW
    for key in (0xBA, 0xC0, 0xDE, 0xE2):
        text = triggers.layout_character(key, layout)
        expected = mapper(key, 2, layout) & 0xffff
        assert text == (chr(expected).upper() if expected >= 32 and expected != 127 else '')


def test_hover_is_inset_and_outer_table_is_clipped(qapp):
    table = LibraryTable(1, 1)
    table.setItem(0, 0, QTableWidgetItem('Nombre'))
    table.resize(300, 180)
    table.show()
    qapp.processEvents()
    assert table.outline.geometry() == table.rect()
    assert table.outline.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    assert table.mask().isEmpty()
    delegate = LibraryDelegate(table)
    option = QStyleOptionViewItem()
    option.initFrom(table)
    option.rect = QRect(0, 0, 180, 44)
    option.state = QStyle.StateFlag.State_Enabled | QStyle.StateFlag.State_MouseOver
    canvas = QImage(180, 44, QImage.Format.Format_ARGB32)
    canvas.fill(Qt.GlobalColor.transparent)
    painter = QPainter(canvas)
    delegate.paint(painter, option, table.model().index(0, 0))
    painter.end()
    assert canvas.pixelColor(1, 1) != canvas.pixelColor(90, 5)
    assert canvas.pixelColor(3, 3) != canvas.pixelColor(90, 5)
    table.close()


def test_library_and_editor_show_readable_shortcut(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(triggers, 'layout_character', lambda key, layout: 'Ñ')
    window = MainWindow(Settings(tmp_path), enable_hooks=False)
    window.new_macro(name='Prueba')
    window.current.trigger = 'VK192'
    window.refresh_library()
    window.refresh_current()
    assert window.library_table.item(0, 1).text() == 'Ñ'
    assert 'Ñ' in window.macro_summary.text()
    assert window.current.trigger == 'VK192'
    monkeypatch.setattr(triggers, 'layout_character', lambda key, layout: '`')
    monkeypatch.setattr('macroflow.ui.main_window.keyboard_layout', lambda: 456)
    window.tick()
    assert window.library_table.item(0, 1).text() == '`'
    assert window.current.trigger == 'VK192'
    window.close()
