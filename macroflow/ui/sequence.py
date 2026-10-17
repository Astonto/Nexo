from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPen
from PySide6.QtWidgets import QStyledItemDelegate, QStyle

from ..models import LABELS
from ..recording import token_vk
from ..triggers import key_label
from .theme import accent_color


def describe_event(event):
    if event.key:
        vk = token_vk(event.key)
        value = key_label(vk) if vk else event.key.removeprefix("char:").removeprefix("key:")
    elif event.button:
        value = {"left": "Izquierdo", "right": "Derecho", "middle": "Central", "x1": "Lateral 1", "x2": "Lateral 2"}[event.button]
    elif event.kind == "move":
        value = f"{event.x}, {event.y}"
    elif event.kind == "scroll":
        value = f"H {event.dx} · V {event.dy}"
    else:
        value = f"{event.delay:g} s"
    return f"{LABELS[event.kind]} · {value}"


class ActionDelegate(QStyledItemDelegate):

    def sizeHint(self, option, index):
        return QSize(138, 112)

    def paint(self, painter, option, index):
        if not index.isValid():
            return
        event = index.model().events[index.row()]
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        dark = option.palette.window().color().lightness() < 128
        rect = QRectF(option.rect).adjusted(4, 4, -4, -4)
        painter.save()
        painter.setRenderHint(painter.RenderHint.Antialiasing)
        accent = accent_color(option.widget)
        painter.setBrush(accent.darker(420) if selected else QColor('#141414' if dark else '#ffffff'))
        painter.setPen(QPen(accent if selected else QColor('#303030' if dark else '#bfc5ce'), 1))
        painter.drawRoundedRect(rect, 7, 7)
        painter.setFont(QFont("Inter", 9))
        painter.setPen(QColor("#999999"))
        painter.drawText(rect.adjusted(12, 7, -12, -70), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, f"{index.row() + 1:02d}")
        down = event.kind.endswith("_down")
        up = event.kind.endswith("_up")
        direction = "↓ Pulsar" if down else "↑ Soltar" if up else "Pausa" if event.kind == "wait" else "Mover" if event.kind == "move" else "Rueda"
        painter.drawText(rect.adjusted(12, 7, -10, -70), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, direction)
        title = describe_event(event).split(" · ", 1)[1]
        painter.setFont(QFont("Inter", 12, QFont.Weight.DemiBold))
        painter.setPen(QColor("#f3f3f3" if selected or dark else "#171717"))
        painter.drawText(rect.adjusted(10, 28, -10, -32), Qt.AlignmentFlag.AlignCenter,
                         painter.fontMetrics().elidedText(title, Qt.TextElideMode.ElideRight, int(rect.width() - 20)))
        painter.setFont(QFont("Inter", 9))
        painter.setPen(QColor("#a6a6a6" if dark or selected else "#666666"))
        painter.drawText(rect.adjusted(10, 70, -10, -7), Qt.AlignmentFlag.AlignCenter, f"{event.delay:g} s")
        painter.restore()
