from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from macroflow.config import Settings
from macroflow.ui.main_window import MainWindow


def test_brand_toggles_sidebar_navigation_and_persists(qapp, tmp_path):
    window = MainWindow(Settings(tmp_path), enable_hooks=False)
    window.show()
    qapp.processEvents()
    positions = [item.y() for item in window.nav]
    assert window.breadcrumb.isHidden()
    assert window.nav[0].shimmer_timer.isActive()
    assert not any(item.shimmer_timer.isActive() for item in window.nav[1:])
    assert not window.side_brand.toolTip()
    QTest.mouseMove(window.side_brand, QPoint(90, 16))
    assert window.side_brand.cursor().shape() == Qt.CursorShape.ArrowCursor
    QTest.mouseClick(window.side_brand, Qt.MouseButton.LeftButton, pos=QPoint(90, 16))
    assert not window.settings.data["sidebar_collapsed"]
    QTest.mouseMove(window.side_brand, QPoint(24, 16))
    assert window.side_brand.cursor().shape() == Qt.CursorShape.PointingHandCursor
    QTest.mouseClick(window.side_brand, Qt.MouseButton.LeftButton, pos=QPoint(24, 16))
    QTest.qWait(100)
    assert 72 < window.sidebar.width() < 186
    assert 0 < len(window.nav[6].text()) < len(window.page_names[6])
    assert window.version_label.isVisible()
    QTest.qWait(300)
    assert window.sidebar.width() == 72
    assert [item.y() for item in window.nav] == positions
    assert window.side_brand.text() == "N"
    for item, name in zip(window.nav, window.page_names):
        assert item.text() == "" and item.toolTip() == name and not item.icon().isNull()
    hint_owner = window.nav[1]
    hint_owner.hint.reveal(hint_owner)
    expected = hint_owner.mapToGlobal(hint_owner.rect().topRight())
    assert hint_owner.hint.x() == expected.x() + 7
    assert hint_owner.hint.y() == expected.y() + (hint_owner.height() - 36) // 2
    hint_owner.dismiss_hint()
    assert not hint_owner.hint.isVisible()
    QTest.mouseClick(window.nav[6], Qt.MouseButton.LeftButton)
    assert window.pages.currentIndex() == 6 and window.nav[6].isChecked()
    assert window.nav[6].shimmer_timer.isActive()
    assert not window.nav[0].shimmer_timer.isActive()
    assert window.title.shimmer_timer.isActive()
    window.close()
    restored = MainWindow(Settings(tmp_path), enable_hooks=False)
    restored.show()
    qapp.processEvents()
    assert restored.sidebar.width() == 72 and restored.side_brand.text() == "N"
    QTest.mouseClick(restored.side_brand, Qt.MouseButton.LeftButton)
    QTest.qWait(400)
    assert restored.sidebar.width() == 186 and restored.side_brand.text() == "NEXO"
    assert [item.text() for item in restored.nav] == restored.page_names
    restored.close()



def test_space_after_clicking_brand_does_not_toggle_sidebar(qapp, tmp_path):
    from PySide6.QtCore import Qt, QPoint
    from PySide6.QtTest import QTest
    from macroflow.ui.widgets import BrandButton
    from macroflow.ui.main_window import MainWindow
    from macroflow.config import Settings
    window = MainWindow(Settings(tmp_path), enable_hooks=False)
    window.show()
    qapp.processEvents()
    brand = window.findChild(BrandButton)
    QTest.mouseClick(brand, Qt.MouseButton.LeftButton, pos=QPoint(24, brand.height()//2))
    qapp.processEvents()
    collapsed = window.settings.data['sidebar_collapsed']
    assert qapp.focusWidget() is not brand
    QTest.keyClick(qapp.focusWidget() or window, Qt.Key.Key_Space)
    qapp.processEvents()
    assert window.settings.data['sidebar_collapsed'] == collapsed
    window.close()
