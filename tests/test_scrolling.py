from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QScrollArea, QWidget

from macroflow.ui.scrolling import install_smooth_scrolling


def test_wheel_moves_gradually_accumulates_and_clamps(qapp):
    install_smooth_scrolling()
    area = QScrollArea()
    content = QWidget()
    content.resize(200, 2000)
    area.setWidget(content)
    area.resize(240, 240)
    area.show()
    qapp.processEvents()
    bar = area.verticalScrollBar()

    def wheel():
        event = QWheelEvent(QPointF(30, 30), QPointF(30, 30), QPoint(), QPoint(0, -120),
                            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                            Qt.ScrollPhase.NoScrollPhase, False)
        qapp.sendEvent(area.viewport(), event)

    wheel()
    target = bar._wheel_animation.endValue()
    assert bar.value() == 0 and target > 0
    QTest.qWait(60)
    assert 0 < bar.value() < target
    wheel()
    assert bar._wheel_animation.endValue() > target
    QTest.qWait(220)
    assert bar.value() == bar._wheel_animation.endValue()
    bar.setValue(bar.maximum() - 1)
    wheel()
    QTest.qWait(220)
    assert bar.value() == bar.maximum()
    area.close()
