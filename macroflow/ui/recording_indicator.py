from ..i18n import tr
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QWidget

from .playback_panel import PAUSED, RUNNING
from .theme import icon, accent_color
from .floating import ScreenBounds, move_within_screens


class RecordingStop(QPushButton):
    def __init__(self, callback, parent):
        super().__init__(tr('Stop'), parent)
        self.accent = RUNNING
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(callback)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self.accent))
        painter.drawRoundedRect(QRectF(self.rect()), 9, 9)
        painter.setBrush(QColor("#000000"))
        painter.drawRoundedRect(QRectF(12, 15, 12, 12), 2, 2)
        painter.setPen(QColor("#000000"))
        painter.setFont(QFont("Inter", 10, QFont.Weight.DemiBold))
        painter.drawText(QRectF(30, 0, self.width() - 34, self.height()), Qt.AlignmentFlag.AlignCenter, self.text())


class RecordingIndicator(QWidget):
    stop_requested = Signal()
    pause_requested = Signal()

    def __init__(self):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint |
                         Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle(tr('Nexo · Recording indicator'))
        self.setFixedSize(460, 76)
        self.screen_bounds = ScreenBounds(self)
        self.phase, self.drag_origin = "running", None
        self.text = QLabel(self)
        self.text.setGeometry(76, 14, 218, 22)
        self.text.setStyleSheet("color:#ffffff; background:transparent; font-family:Inter; font-size:11px; font-weight:650;")
        self.subtitle = QLabel(self)
        self.subtitle.setGeometry(76, 38, 218, 20)
        self.subtitle.setStyleSheet("color:#a0a0a5; background:transparent; font-family:Inter; font-size:11px;")
        for widget in (self.text, self.subtitle):
            widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.stop = RecordingStop(self.stop_requested.emit, self)
        self.stop.setGeometry(344, 16, 102, 42)
        self.pause = QPushButton(self)
        self.pause.setGeometry(300, 16, 36, 42)
        self.pause.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.pause.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pause.setStyleSheet("QPushButton{background:#212225;border:0;border-radius:7px;} QPushButton:hover{background:#2e2f32;}")
        self.pause.clicked.connect(self.pause_requested.emit)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.update_phase("running")
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.right() - self.width() - 18, screen.top() + 18)

    def update_phase(self, phase):
        self.phase = phase
        paused = phase == "paused"
        self.text.setText(tr('RECORDING PAUSED') if paused else tr('RECORDING IN PROGRESS'))
        self.subtitle.setText(tr('You can stop at any time') if paused else tr('Press stop to finish'))
        self.stop.setText(tr('Stop'))
        self.stop.accent = PAUSED if paused else accent_color(self).name()
        self.pause.setIcon(icon("play" if paused else "pause", "#ffffff"))
        self.pause.setToolTip(tr('Resume recording') if paused else tr('Pause recording'))
        self.pause.setAccessibleName(self.pause.toolTip())
        self.pause.show()
        self.stop.setAccessibleName(tr('Stop recording'))
        self.stop.setToolTip(tr('Stop the current recording'))
        self.update()
        self.stop.update()

    def show_picker(self, emergency="Pause"):
        self.update_phase("running")
        self.text.setText(tr('PICK A POINT'))
        self.subtitle.setText(tr('{0} cancels selection', emergency))
        self.stop.setText(tr('Cancel'))
        self.stop.setAccessibleName(tr('Cancel position selection'))
        self.pause.hide()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor("#000000"))
        painter.setPen(QPen(QColor("#37383d"), 1))
        painter.drawRoundedRect(QRectF(1, 1, self.width() - 2, self.height() - 3), 13, 13)
        accent = QColor(PAUSED) if self.phase == 'paused' else accent_color(self)
        tint = QColor(accent)
        tint.setAlpha(35)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(tint)
        painter.drawRoundedRect(QRectF(12, 14, 44, 44), 10, 10)
        if self.phase == "paused":
            painter.setBrush(accent)
            for x in (25, 37):
                painter.drawRoundedRect(QRectF(x, 26, 6, 20), 1, 1)
        else:
            for radius, opacity in ((18, 40), (13, 80), (8, 255)):
                circle = QColor(accent)
                circle.setAlpha(opacity)
                painter.setBrush(circle)
                painter.drawEllipse(QPointF(34, 36), radius, radius)
        painter.setPen(QPen(QColor("#303136"), 1))
        painter.drawLine(65, 15, 65, 59)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_origin = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event):
        if self.drag_origin is not None and event.buttons() & Qt.MouseButton.LeftButton:
            move_within_screens(self, event.globalPosition().toPoint() - self.drag_origin)

    def mouseReleaseEvent(self, event):
        self.drag_origin = None
