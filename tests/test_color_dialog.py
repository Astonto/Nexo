from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from macroflow.ui.color_picker import ColorDialog


def test_hex_rgb_swatches_and_cancel_are_synchronized(qapp):
    dialog = ColorDialog('#ff1744')
    dialog.show()
    dialog.hex.selectAll()
    QTest.keyClicks(dialog.hex, '#2879ed')
    assert dialog.color.name() == '#2879ed'
    assert [field.value() for field in dialog.rgb] == [40, 121, 237]
    dialog.rgb[0].setValue(60)
    assert dialog.color.red() == 60 and dialog.hex.text() == '#3C79ED'
    QTest.mouseClick(dialog.chips[0], Qt.MouseButton.LeftButton)
    assert dialog.color.name() == '#ff1744'
    dialog.set_color(QColor('#2879ed'))
    dialog.reject()
    assert dialog.result() == 0 and dialog.initial.name() == '#ff1744'


def test_invalid_hex_blocks_accept_and_correction_accepts(qapp):
    dialog = ColorDialog('#ff1744')
    dialog.show()
    dialog.hex.selectAll()
    QTest.keyClicks(dialog.hex, '#GG1234')
    assert not dialog.use.isEnabled() and dialog.error.text()
    dialog.accept()
    assert dialog.result() == 0 and dialog.isVisible()
    dialog.hex.selectAll()
    QTest.keyClicks(dialog.hex, '25a56a')
    assert dialog.color.name() == '#25a56a'
    QTest.mouseClick(dialog.use, Qt.MouseButton.LeftButton)
    assert dialog.result() == 1


def test_surfaces_mouse_keyboard_and_black_hue(qapp):
    dialog = ColorDialog('#2879ed')
    dialog.show()
    QTest.mouseClick(dialog.plane, Qt.MouseButton.LeftButton, pos=dialog.plane.rect().center())
    assert .4 < dialog.plane.saturation < .6 and .4 < dialog.plane.value < .6
    previous = dialog.color.name()
    QTest.keyClick(dialog.plane, Qt.Key.Key_Right)
    assert dialog.color.name() != previous
    dialog.set_color(QColor('black'))
    QTest.mouseClick(dialog.hue, Qt.MouseButton.LeftButton, pos=dialog.hue.rect().center())
    assert abs(dialog.plane.hue - dialog.hue.hue) < .001
    QTest.mouseClick(dialog.plane, Qt.MouseButton.LeftButton, pos=dialog.plane.rect().center())
    assert dialog.color.hueF() > .4
    dialog.reject()
