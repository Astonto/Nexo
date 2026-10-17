
from PySide6.QtCore import QAbstractAnimation, QEasingCurve, QEvent, QObject, QPropertyAnimation, Qt
from PySide6.QtWidgets import QAbstractItemView, QAbstractScrollArea, QApplication, QScrollBar


class SmoothScrolling(QObject):
    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Show and isinstance(watched, QAbstractItemView):
            watched.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
            watched.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        if event.type() != QEvent.Type.Wheel or event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            return False
        area = watched.parentWidget() if hasattr(watched, "parentWidget") else None
        if not isinstance(area, QAbstractScrollArea) or watched is not area.viewport():
            return False
        horizontal = bool(event.angleDelta().x()) or bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        bar = area.horizontalScrollBar() if horizontal else area.verticalScrollBar()
        if bar.maximum() == bar.minimum():
            return False

        if not event.pixelDelta().isNull():
            animation = getattr(bar, "_wheel_animation", None)
            if animation:
                animation.stop()
            return False
        delta = event.angleDelta().x() if event.angleDelta().x() else event.angleDelta().y()
        if not delta:
            return False
        animation = getattr(bar, "_wheel_animation", None)
        if animation is None:
            animation = QPropertyAnimation(bar, b"value", bar)
            animation.setDuration(160)
            animation.setEasingCurve(QEasingCurve.Type.OutCubic)
            bar._wheel_animation = animation
            bar.sliderPressed.connect(animation.stop)
            bar.actionTriggered.connect(lambda _: animation.stop())
        base = animation.endValue() if animation.state() == QAbstractAnimation.State.Running else bar.value()
        target = max(bar.minimum(), min(bar.maximum(), round(base - delta / 120 * bar.singleStep() * QApplication.wheelScrollLines())))
        if target == bar.value() and animation.state() != QAbstractAnimation.State.Running:
            return False
        animation.stop()
        animation.setStartValue(bar.value())
        animation.setEndValue(target)
        animation.start()
        event.accept()
        return True


def install_smooth_scrolling():
    app = QApplication.instance()
    if not hasattr(app, "_smooth_scrolling"):
        app._smooth_scrolling = SmoothScrolling(app)
        app.installEventFilter(app._smooth_scrolling)
