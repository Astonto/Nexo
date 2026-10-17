
from PySide6.QtCore import QEvent, QObject, QPoint, QTimer
from PySide6.QtWidgets import QApplication


def bounded_position(position, size, areas):
    if not areas:
        return position
    areas = [area for area in areas if area.width() >= size.width() and area.height() >= size.height()] or areas
    center = position + QPoint(size.width() // 2, size.height() // 2)
    def distance(rect):
        x = max(rect.left(), min(center.x(), rect.right()))
        y = max(rect.top(), min(center.y(), rect.bottom()))
        return (center.x() - x) ** 2 + (center.y() - y) ** 2
    area = min(areas, key=distance)
    return QPoint(max(area.left(), min(position.x(), area.left() + max(0, area.width() - size.width()))),
                  max(area.top(), min(position.y(), area.top() + max(0, area.height() - size.height()))))


def move_within_screens(widget, position):
    widget.move(bounded_position(position, widget.size(), [screen.availableGeometry() for screen in QApplication.screens()]))


class ScreenBounds(QObject):
    def __init__(self, widget):
        super().__init__(widget)
        self.widget = widget
        widget.installEventFilter(self)
        app = QApplication.instance()
        app.screenAdded.connect(self.add_screen)
        app.screenRemoved.connect(self.schedule)
        for screen in app.screens():
            screen.availableGeometryChanged.connect(self.schedule)

    def add_screen(self, screen):
        screen.availableGeometryChanged.connect(self.schedule)
        self.schedule()

    def schedule(self, *args):
        QTimer.singleShot(0, self.clamp)

    def clamp(self):
        move_within_screens(self.widget, self.widget.pos())

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Show:
            self.clamp()
        return False
