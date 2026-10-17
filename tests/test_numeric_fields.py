import pytest
from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest
from macroflow.ui.widgets import spin
from macroflow.ui.theme import stylesheet


@pytest.mark.parametrize('suffix,decimals', [(' s', None), (' ms', None), ('×', 2)])
def test_only_numeric_part_is_selected_and_unit_survives_typing(qapp, suffix, decimals):
    field = spin(-1000, 1000, 12, suffix, decimals)
    field.show()
    field.setFocus()
    qapp.processEvents()
    QTest.keyClick(field.lineEdit(), Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    assert field.lineEdit().selectedText() == field.cleanText()
    assert suffix.strip() not in field.lineEdit().selectedText()
    QTest.keyClicks(field.lineEdit(), '25')
    QTest.keyClick(field, Qt.Key.Key_Return)
    assert field.value() == 25 and field.suffix() == suffix
    field.lineEdit().selectAll()
    assert field.lineEdit().selectedText() == field.cleanText()
    field.close()


def test_larger_arrow_targets_increment_and_decrement(qapp):
    field = spin(0, 30, 3, ' s')
    field.setStyleSheet(stylesheet())
    field.resize(220, 38)
    field.show()
    qapp.processEvents()
    QTest.mouseClick(field, Qt.MouseButton.LeftButton, pos=QPoint(field.width()-15, 9))
    assert field.value() == 4
    QTest.mouseClick(field, Qt.MouseButton.LeftButton, pos=QPoint(field.width()-15, field.height()-9))
    assert field.value() == 3
    field.close()


@pytest.mark.parametrize('suffix', [' s', ' ms', '×'])
def test_caret_cannot_enter_unit(qapp, suffix):
    field = spin(0, 1000, 100, suffix)
    field.show()
    qapp.processEvents()
    edit = field.lineEdit()
    edit.deselect()
    edit.setCursorPosition(len(edit.text()))
    end = len(edit.text()) - len(suffix)
    assert edit.cursorPosition() == end
    QTest.keyClick(edit, Qt.Key.Key_End)
    assert edit.cursorPosition() == end
    QTest.keyClick(edit, Qt.Key.Key_Right)
    assert edit.cursorPosition() == end
    field.close()


def test_display_text_is_not_selectable_but_inputs_remain_editable(qapp):
    from PySide6.QtWidgets import QLabel, QLineEdit
    from macroflow.ui.widgets import install_display_text_policy
    from macroflow.ui.dialogs import ShortcutField
    install_display_text_policy(qapp)
    label = QLabel('Texto fijo')
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    label.show()
    readonly = ShortcutField('Ctrl+K')
    readonly.show()
    editable = QLineEdit('Nombre')
    editable.show()
    qapp.processEvents()
    assert label.textInteractionFlags() == Qt.TextInteractionFlag.NoTextInteraction
    QTest.mouseDClick(readonly, Qt.MouseButton.LeftButton)
    assert not readonly.hasSelectedText()
    editable.selectAll()
    QTest.keyClicks(editable, 'Nuevo')
    assert editable.text() == 'Nuevo'
    for widget in (label, readonly, editable):
        widget.close()
