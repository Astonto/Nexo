from __future__ import annotations

from PySide6.QtCore import QEvent, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget
from .floating import ScreenBounds, move_within_screens
from .theme import accent_color


RUNNING = "#ff1744"
RUNNING_TINT = RUNNING
PAUSED = "#ffb800"


class MacroName(QLabel):
    def set_name(self, name):
        self.full_name = name
        self.setToolTip(name)
        self.setText(self.fontMetrics().elidedText(name, Qt.TextElideMode.ElideRight, self.width()))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.set_name(getattr(self, "full_name", ""))


def replay_path():

    path = QPainterPath()
    path.moveTo(12, 5)
    path.lineTo(12, 1)
    path.lineTo(7, 6)
    path.lineTo(12, 11)
    path.lineTo(12, 7)
    path.cubicTo(15.31, 7, 18, 9.69, 18, 13)
    path.cubicTo(18, 16.31, 15.31, 19, 12, 19)
    path.cubicTo(8.69, 19, 6, 16.31, 6, 13)
    path.lineTo(4, 13)
    path.cubicTo(4, 17.42, 7.58, 21, 12, 21)
    path.cubicTo(16.42, 21, 20, 17.42, 20, 13)
    path.cubicTo(20, 8.58, 16.42, 5, 12, 5)
    path.closeSubpath()
    return path


class PlaybackDetail(QWidget):


    def __init__(self):
        super().__init__()
        self.progress = None
        self.fallback = "Preparando…"
        self.setFixedHeight(16)

    def sizeHint(self):
        return QSize(400, 16)

    def setText(self, text):
        self.progress, self.fallback = None, text
        self.update()

    def text(self):
        if self.progress:
            position, total, iterations, elapsed = self.progress
            return f"{position} / {total} · {iterations} rep. completadas · {elapsed}"
        return self.fallback

    def set_progress(self, position, total, iterations, elapsed):
        self.progress = position, total, iterations, elapsed
        self.setToolTip(f"Acciones completadas: {position} de {total} · Repeticiones completadas: {iterations} · Tiempo: {elapsed}")
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(QFont("Inter", 8))
        painter.setPen(QColor("#a8a9ae"))
        if not self.progress:
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.fallback)
            return
        position, total, iterations, elapsed = self.progress
        baseline = self.height() / 2
        x = 0
        def text(value):
            nonlocal x
            width = painter.fontMetrics().horizontalAdvance(value) + 2
            painter.drawText(QRectF(x, 0, width, self.height()), Qt.AlignmentFlag.AlignVCenter, value)
            x += width + 10
        text(f"{position} / {total}")
        text("·")
        painter.save()
        painter.translate(x, baseline - 6)
        painter.scale(.55, .55)
        painter.fillPath(replay_path(), QColor("#a8a9ae"))
        painter.restore()
        painter.setPen(QColor("#a8a9ae"))
        x += 18
        text(f"{iterations} hechas")
        text("·")
        painter.setPen(QPen(QColor("#a8a9ae"), 1.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(x + 6, baseline), 5.5, 5.5)
        painter.drawLine(QPointF(x + 6, baseline), QPointF(x + 6, baseline - 3.5))
        painter.drawLine(QPointF(x + 6, baseline), QPointF(x + 9, baseline + 1))
        painter.setPen(QColor("#a8a9ae"))
        x += 18
        text(elapsed)


class PlaybackControl(QPushButton):


    def __init__(self, kind, accessible_name, callback, *, stop=False):
        super().__init__(accessible_name)
        self.kind = kind
        self.stop_control = stop
        self.emphasis = False
        self.accent = RUNNING
        self.setFixedSize(36, 36)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAccessibleName(accessible_name)
        self.setToolTip(accessible_name)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(callback)

    def set_emphasis(self, enabled, accent=RUNNING):
        self.emphasis, self.accent = enabled, accent
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.scale(self.width() / 66, self.height() / 66)
        rect = QRectF(2, 2, 62, 62)
        if self.stop_control:
            fill, border = accent_color(self), accent_color(self)
        elif self.emphasis:
            fill = QColor(self.accent)
            fill.setAlpha(50 if self.underMouse() and self.isEnabled() else 38)
            border = QColor(self.accent)
        else:
            fill = QColor("#2e2f32" if self.underMouse() and self.isEnabled() else "#212225")
            border = QColor("#303236")
        if not self.isEnabled():
            fill.setAlpha(115)
            border.setAlpha(115)
        painter.setBrush(fill)
        painter.setPen(QPen(border, 2.2) if self.emphasis else Qt.PenStyle.NoPen)
        painter.drawRoundedRect(rect, 12, 12)
        color = QColor("#ffffff" if self.isEnabled() else "#777777")
        painter.setPen(QPen(color, 3.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(color)
        center = QPointF(33, 33)
        if self.kind == "previous":
            painter.drawLine(QPointF(center.x() - 12, center.y() - 13), QPointF(center.x() - 12, center.y() + 13))
            painter.drawPolygon(QPolygonF([QPointF(center.x() + 10, center.y() - 13),
                                            QPointF(center.x() + 10, center.y() + 13),
                                            QPointF(center.x() - 8, center.y())]))
        elif self.kind == "next":
            painter.drawLine(QPointF(center.x() + 12, center.y() - 13), QPointF(center.x() + 12, center.y() + 13))
            painter.drawPolygon(QPolygonF([QPointF(center.x() - 10, center.y() - 13),
                                            QPointF(center.x() - 10, center.y() + 13),
                                            QPointF(center.x() + 8, center.y())]))
        elif self.kind == "pause":
            if self.text() == "Reanudar":
                painter.drawPolygon(QPolygonF([QPointF(center.x() - 8, center.y() - 14),
                                                QPointF(center.x() - 8, center.y() + 14),
                                                QPointF(center.x() + 14, center.y())]))
            else:
                painter.drawRoundedRect(QRectF(center.x() - 11, center.y() - 14, 7, 28), 1.5, 1.5)
                painter.drawRoundedRect(QRectF(center.x() + 4, center.y() - 14, 7, 28), 1.5, 1.5)
        elif self.kind == "restart":

            painter.save()
            painter.translate(center.x() - 16.8, center.y() - 16.8)
            painter.scale(1.4, 1.4)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.fillPath(replay_path(), color)
            painter.restore()
        elif self.kind == "stop":
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(QRectF(center.x() - 10, center.y() - 10, 20, 20), 2, 2)


class PlaybackPanel(QWidget):
    pause_requested = Signal()
    stop_requested = Signal()
    previous_requested = Signal()
    next_requested = Signal()
    restart_requested = Signal()

    def __init__(self):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint |
                         Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("Nexo · Reproducción")
        self.setAccessibleName("Panel flotante de reproducción")
        self.setFixedSize(450, 75)
        self.screen_bounds = ScreenBounds(self)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.drag_origin = None
        self.phase = "running"
        self.progress_ratio = 0.0
        self.progress_accent = RUNNING
        self.setStyleSheet("QLabel { background:transparent; color:#f5f5f5; font-family:Inter; }")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 8, 14, 12)
        outer.setSpacing(3)
        root = QHBoxLayout()
        root.setSpacing(6)
        outer.addLayout(root)
        self.dot = QFrame()
        self.dot.setFixedSize(9, 9)
        root.addWidget(self.dot, 0, Qt.AlignmentFlag.AlignTop)
        information = QVBoxLayout()
        information.setContentsMargins(0, 0, 0, 0)
        information.setSpacing(0)
        self.title = QLabel("REPRODUCIENDO")
        self.title.setFont(QFont("Inter", 7, QFont.Weight.Medium))
        self.title.setStyleSheet("color:#929398; letter-spacing:1px;")
        self.macro_name = MacroName("")
        self.macro_name.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.macro_name.setFont(QFont("Inter", 10, QFont.Weight.DemiBold))
        self.detail = PlaybackDetail()
        information.addWidget(self.title)
        information.addWidget(self.macro_name)
        outer.addWidget(self.detail)
        root.addLayout(information, 1)
        self.separator = QFrame()
        self.separator.setFixedSize(1, 30)
        self.separator.setStyleSheet("background:#343539;")
        root.addWidget(self.separator, 0, Qt.AlignmentFlag.AlignVCenter)
        self.previous = PlaybackControl("previous", "Acción anterior", self.previous_requested.emit)
        self.pause = PlaybackControl("pause", "Pausar", self.pause_requested.emit)
        self.next = PlaybackControl("next", "Acción siguiente", self.next_requested.emit)
        self.restart = PlaybackControl("restart", "Reiniciar macro", self.restart_requested.emit)
        self.stop = PlaybackControl("stop", "Detener reproducción", self.stop_requested.emit, stop=True)
        self.previous.setToolTip("Volver a la acción anterior de esta macro")
        self.next.setToolTip("Saltar a la siguiente acción de esta macro")
        self.restart.setToolTip("Volver al inicio y reiniciar el contador de repeticiones")
        for control in (self.previous, self.pause, self.next, self.restart, self.stop):
            root.addWidget(control)
        self.drag_targets = (self.dot, self.title, self.macro_name, self.detail, self.separator)
        for target in self.drag_targets:
            target.installEventFilter(self)
            target.setCursor(Qt.CursorShape.OpenHandCursor)
        self.update_phase("running", "Macro actual")
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.right() - self.width() - 18, screen.top() + 18)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        shadow = QPainterPath()
        shadow.addRoundedRect(QRectF(2, 4, self.width() - 4, self.height() - 5), 12, 12)
        painter.fillPath(shadow, QColor(0, 0, 0, 145))
        panel = QPainterPath()
        panel.addRoundedRect(QRectF(2, 1, self.width() - 4, self.height() - 5), 11, 11)
        painter.fillPath(panel, QColor("#000000"))
        painter.setPen(QPen(QColor("#37383c"), 1.5))
        painter.drawPath(panel)
        progress_y = self.height() - 8
        progress_start, progress_end = 15, self.width() - 15
        painter.setPen(QPen(QColor("#292a2d"), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(QPointF(progress_start, progress_y), QPointF(progress_end, progress_y))
        if self.progress_ratio > 0:
            painter.setPen(QPen(QColor(self.progress_accent), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            filled = progress_start + (progress_end - progress_start) * self.progress_ratio
            painter.drawLine(QPointF(progress_start, progress_y), QPointF(filled, progress_y))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.begin_drag(event.globalPosition().toPoint())

    def mouseMoveEvent(self, event):
        if self.drag_origin is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.drag_to(event.globalPosition().toPoint())

    def mouseReleaseEvent(self, event):
        self.end_drag()

    def eventFilter(self, watched, event):
        if watched in self.drag_targets:
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                self.begin_drag(event.globalPosition().toPoint())
                return True
            if event.type() == QEvent.Type.MouseMove and event.buttons() & Qt.MouseButton.LeftButton:
                self.drag_to(event.globalPosition().toPoint())
                return True
            if event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
                self.end_drag()
                return True
        return super().eventFilter(watched, event)

    def begin_drag(self, global_position):
        self.drag_origin = global_position - self.pos()
        for target in self.drag_targets:
            target.setCursor(Qt.CursorShape.ClosedHandCursor)

    def drag_to(self, global_position):
        if self.drag_origin is not None:
            move_within_screens(self, global_position - self.drag_origin)

    def end_drag(self):
        self.drag_origin = None
        for target in self.drag_targets:
            target.setCursor(Qt.CursorShape.OpenHandCursor)

    def set_progress(self, index, total, iterations, elapsed):
        position = max(0, min(index, total)) if total else 0
        self.progress_ratio = position / total if total else 0.0
        self.detail.set_progress(position, total, iterations, elapsed)
        self.update()

    def update_phase(self, phase, name):
        self.phase = phase
        paused = phase == "paused"
        accent = PAUSED if paused else accent_color(self).name()
        self.progress_accent = accent
        titles = {"countdown": "PREPARANDO", "running": "REPRODUCIENDO",
                  "paused": "EN PAUSA", "stopping": "DETENIENDO"}
        self.title.setText(titles.get(phase, "REPRODUCCIÓN"))
        self.macro_name.set_name(name)
        self.dot.setStyleSheet(f"background:{accent}; border-radius:4px;")
        self.pause.setText("Reanudar" if paused else "Pausar")
        self.pause.setAccessibleName("Reanudar" if paused else "Pausar")
        self.pause.setToolTip("Reanudar reproducción" if paused else "Pausar reproducción")
        self.pause.set_emphasis(phase in ("running", "paused"), accent)
        for item in (self.previous, self.next, self.restart, self.pause):
            item.setEnabled(phase in ("running", "paused"))
        self.stop.setEnabled(phase != "stopping")
        self.update()
