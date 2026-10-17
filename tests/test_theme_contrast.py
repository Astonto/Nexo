from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QStyle, QStyleOptionViewItem
from macroflow.config import Settings
from macroflow.ui.main_window import MainWindow
from macroflow.ui.widgets import light_surface, shimmer_pen


def test_theme_switch_updates_visible_notice_controls_and_shimmer(qapp, tmp_path):
    window = MainWindow(Settings(tmp_path), enable_hooks=False)
    window.show()
    window.show_notice('Preferencias guardadas.')
    for theme in ('light', 'dark', 'light'):
        window.settings.data['theme'] = theme
        window.apply_theme()
        qapp.processEvents()
        light = theme == 'light'
        assert light_surface(window.side_brand) == light
        assert light_surface(window.notice.message) == light
        assert window.notice.message.palette().color(QPalette.ColorRole.WindowText).lightness() < 128 if light else window.notice.message.palette().color(QPalette.ColorRole.WindowText).lightness() > 128
        pen = shimmer_pen(window.nav[0])
        brush = pen.brush()
        base = brush.gradient().stops()[0][1]
        assert (base.lightness() < 128) == light
        field = window.search.palette().color(QPalette.ColorRole.Base)
        assert field != window.palette().color(QPalette.ColorRole.Window)
    window.close()


def test_library_keeps_keyboard_selection_without_native_focus_frame(qapp, tmp_path):
    window = MainWindow(Settings(tmp_path), enable_hooks=False)
    window.new_macro(name='Primera')
    window.new_macro(name='Segunda')
    window.change_page(5)
    window.show()
    table = window.library_table
    table.setCurrentCell(0, 0)
    table.setFocus()
    from PySide6.QtTest import QTest
    QTest.keyClick(table, Qt.Key.Key_Down)
    assert table.currentRow() == 1
    option = QStyleOptionViewItem()
    option.initFrom(table)
    option.state |= QStyle.StateFlag.State_HasFocus
    from PySide6.QtGui import QPainter, QPixmap
    canvas = QPixmap(300, 44)
    painter = QPainter(canvas)
    table.itemDelegate().paint(painter, option, table.model().index(1, 0))
    painter.end()
    assert not option.state & QStyle.StateFlag.State_HasFocus
    window.close()


def test_sidebar_drag_switches_pages_and_release_does_not_return(qapp, tmp_path):
    from PySide6.QtCore import QEvent, QPointF
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtTest import QTest
    window = MainWindow(Settings(tmp_path), enable_hooks=False)
    window.show()
    source, target = window.nav[0], window.nav[2]
    QTest.mousePress(source, Qt.MouseButton.LeftButton)
    point = target.mapToGlobal(target.rect().center())
    event = QMouseEvent(QEvent.Type.MouseMove, QPointF(source.mapFromGlobal(point)), QPointF(point), Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    qapp.sendEvent(source, event)
    assert target.isChecked()
    QTest.mouseRelease(source, Qt.MouseButton.LeftButton, pos=source.mapFromGlobal(point))
    assert target.isChecked()
    QTest.mouseClick(source, Qt.MouseButton.LeftButton)
    assert source.isChecked()
    window.close()


def test_sidebar_arrow_keys_move_focus_and_activate_tabs(qapp, tmp_path):
    from PySide6.QtTest import QTest
    window = MainWindow(Settings(tmp_path), enable_hooks=False)
    window.show()
    window.activateWindow()
    qapp.processEvents()
    QTest.mouseClick(window.nav[0], Qt.MouseButton.LeftButton)
    QTest.keyClick(window.nav[0], Qt.Key.Key_Down)
    assert window.nav[1].isChecked() and window.nav[1].hasFocus()
    QTest.keyClick(window.nav[1], Qt.Key.Key_Right)
    assert window.nav[2].isChecked() and window.nav[2].hasFocus()
    QTest.keyClick(window.nav[2], Qt.Key.Key_Up)
    assert window.nav[1].isChecked()
    QTest.keyClick(window.nav[1], Qt.Key.Key_Left)
    assert window.nav[0].isChecked()
    QTest.keyClick(window.nav[0], Qt.Key.Key_Up)
    assert max(window.nav, key=lambda tab: tab.mapToGlobal(tab.rect().center()).y()).isChecked()
    window.close()
