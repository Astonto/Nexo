from ..i18n import tr

import re
from PySide6.QtCore import Qt, QRectF, QPointF, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QLinearGradient, QPen
from PySide6.QtWidgets import QDialog, QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QLineEdit, QSpinBox
from .widgets import button, label, light_surface, configure_number
from .theme import DEFAULT_ACCENT


class ColorSurface(QWidget):
    changed = Signal(QColor)

    def __init__(self, hue_only=False):
        super().__init__()
        self.hue_only = hue_only
        self.keyboard_focus = False
        self.hue, self.saturation, self.value = .96, .9, 1.
        self.setFixedHeight(24 if hue_only else 190)
        self.setMinimumWidth(280)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(tr('Hue') if hue_only else tr('Saturation and brightness'))
        self.setToolTip(tr('Drag or use the arrow keys to adjust the color'))

    def set_color(self, color):
        hue, sat, val, _ = color.getHsvF()
        if hue >= 0:
            self.hue = min(hue, .9999)
        self.saturation, self.value = sat, val
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        area = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        shape = QPainterPath()
        shape.addRoundedRect(area, 9, 9)
        painter.save()
        painter.setClipPath(shape)
        gradient = QLinearGradient(area.left(), 0, area.right(), 0)
        if self.hue_only:
            for i in range(7):
                gradient.setColorAt(i/6, QColor.fromHsvF(min(i/6, .9999), 1, 1))
        else:
            gradient.setColorAt(0, QColor('white'))
            gradient.setColorAt(1, QColor.fromHsvF(self.hue, 1, 1))
        painter.fillRect(area, gradient)
        if not self.hue_only:
            shade = QLinearGradient(0, area.top(), 0, area.bottom())
            shade.setColorAt(0, QColor(0, 0, 0, 0))
            shade.setColorAt(1, QColor('black'))
            painter.fillRect(area, shade)
        painter.restore()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor('#bac0ca' if light_surface(self) else '#454951'), 1))
        painter.drawPath(shape)
        point = QPointF(area.left() + area.width() * (self.hue if self.hue_only else self.saturation), area.center().y() if self.hue_only else area.top() + area.height() * (1-self.value))
        point.setX(max(area.left()+6, min(area.right()-6, point.x())))
        point.setY(max(area.top()+6, min(area.bottom()-6, point.y())))
        painter.setPen(QPen(QColor(0, 0, 0, 110), 4))
        painter.drawEllipse(point, 5, 5)
        painter.setPen(QPen(QColor('white'), 2))
        painter.drawEllipse(point, 5, 5)
        if self.hasFocus() and self.keyboard_focus:
            painter.setPen(QPen(QColor('#ffffff' if not light_surface(self) else '#343840'), 1))
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(.5, .5, -.5, -.5), 10, 10)

    def choose(self, point):
        x = max(0., min(1., (point.x()-2)/max(1, self.width()-4)))
        y = max(0., min(1., (point.y()-2)/max(1, self.height()-4)))
        if self.hue_only:
            self.hue = min(x, .9999)
        else:
            self.saturation, self.value = x, 1-y
        self.changed.emit(QColor.fromHsvF(self.hue, self.saturation, self.value))
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            self.choose(event.position())

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.choose(event.position())

    def keyPressEvent(self, event):
        directions = {Qt.Key.Key_Left: (-.01, 0), Qt.Key.Key_Right: (.01, 0), Qt.Key.Key_Up: (0, .01), Qt.Key.Key_Down: (0, -.01)}
        if event.key() not in directions:
            return super().keyPressEvent(event)
        dx, dy = directions[event.key()]
        self.keyboard_focus = True
        if self.hue_only:
            self.hue = max(0., min(.9999, self.hue + dx + dy))
        else:
            self.saturation = max(0., min(1., self.saturation + dx))
            self.value = max(0., min(1., self.value + dy))
        self.changed.emit(QColor.fromHsvF(self.hue, self.saturation, self.value))
        self.update()

    def focusInEvent(self, event):
        self.keyboard_focus = event.reason() in (Qt.FocusReason.TabFocusReason, Qt.FocusReason.BacktabFocusReason, Qt.FocusReason.ShortcutFocusReason)
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        self.keyboard_focus = False
        super().focusOutEvent(event)


class ColorChip(QPushButton):
    def __init__(self, color, name, callback=None):
        super().__init__()
        self.color = QColor(color)
        self.selected = False
        self.setFixedSize(34, 34)
        self.setAccessibleName(name)
        self.setToolTip(name)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAutoDefault(False)
        if callback:
            self.clicked.connect(lambda: callback(self.color))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor('#c3c7ce' if light_surface(self) else '#454951'), .8))
        painter.setBrush(self.color)
        painter.drawRoundedRect(QRectF(4, 4, 26, 26), 8, 8)
        if self.selected or self.hasFocus():
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor('#343840' if light_surface(self) else '#f5f5f5'), 1.5))
            painter.drawRoundedRect(QRectF(1.5, 1.5, 31, 31), 10, 10)


class ColorDialog(QDialog):
    def __init__(self, initial, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr('Accent color'))
        self.setObjectName('colorDialog')
        self.setFixedWidth(460)
        self.initial = QColor(initial) if QColor(initial).isValid() else QColor(DEFAULT_ACCENT)
        self.color = QColor(self.initial)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)
        layout.addWidget(label(tr('Accent color'), 'sectionTitle'))
        layout.addWidget(label(tr('Make the interface your own.'), 'muted'))
        self.plane, self.hue = ColorSurface(), ColorSurface(True)
        self.plane.changed.connect(self.set_color)
        self.hue.changed.connect(self.change_hue)
        for surface in (self.plane, self.hue):
            layout.addWidget(surface)
        swatches = QHBoxLayout()
        swatches.setSpacing(10)
        self.chips = []
        for name, color in ((tr('Nexo red'), DEFAULT_ACCENT), ('Coral', '#f46b45'), (tr('Amber'), '#e4a321'), (tr('Green'), '#25a56a'), (tr('Teal'), '#10a6b4'), (tr('Blue'), '#2879ed'), (tr('Purple'), '#8759df'), (tr('Pink'), '#dc4c98')):
            chip = ColorChip(color, name, self.set_color)
            self.chips.append(chip)
            swatches.addWidget(chip)
        swatches.addStretch()
        layout.addLayout(swatches)
        fields = QHBoxLayout()
        fields.setSpacing(12)
        self.hex = QLineEdit()
        self.hex.setMinimumWidth(110)
        self.hex.setMaxLength(7)
        self.hex.setAccessibleName(tr('Hexadecimal color code'))
        self.hex.textEdited.connect(self.edit_hex)
        column = QVBoxLayout()
        column.addWidget(label('HEX', 'eyebrow'))
        column.addWidget(self.hex)
        fields.addLayout(column, 2)
        self.rgb = []
        for name in ('R', 'G', 'B'):
            field = configure_number(QSpinBox())
            field.setFixedWidth(78)
            field.setRange(0, 255)
            field.setKeyboardTracking(False)
            field.setAccessibleName({'R': tr('Red'), 'G': tr('Green'), 'B': tr('Blue')}[name])
            field.valueChanged.connect(self.edit_rgb)
            column = QVBoxLayout()
            column.addWidget(label(name, 'eyebrow'))
            column.addWidget(field)
            fields.addLayout(column, 1)
            self.rgb.append(field)
        layout.addLayout(fields)
        preview = QHBoxLayout()
        self.old_chip = ColorChip(self.initial, tr('Current color'), self.set_color)
        self.new_chip = ColorChip(self.color, tr('New color preview'))
        preview.addWidget(self.old_chip)
        preview.addWidget(label(tr('Current'), 'muted'))
        preview.addSpacing(16)
        preview.addWidget(self.new_chip)
        preview.addWidget(label(tr('New color'), 'muted'))
        preview.addStretch()
        layout.addLayout(preview)
        self.error = label('', 'formError')
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        actions = QHBoxLayout()
        actions.addWidget(button(tr('Reset to red'), lambda: self.set_color(QColor(DEFAULT_ACCENT))))
        actions.addStretch()
        actions.addWidget(button(tr('Cancel'), self.reject))
        self.use = button(tr('Use color'), self.accept, primary=True)
        actions.addWidget(self.use)
        layout.addLayout(actions)
        for control in self.findChildren(QPushButton):
            control.setAutoDefault(False)
        self.use.setDefault(True)
        self.set_color(self.color)

    def set_color(self, color):
        self.color = QColor(color)
        for field, value in zip(self.rgb, (color.red(), color.green(), color.blue())):
            field.blockSignals(True)
            field.setValue(value)
            field.blockSignals(False)
        self.hex.setText(color.name().upper())
        for surface in (self.plane, self.hue):
            surface.set_color(color)
        self.new_chip.color = QColor(color)
        self.new_chip.update()
        for chip in self.chips:
            chip.selected = chip.color == color
            chip.update()
        self.error.setText('')
        self.use.setEnabled(True)

    def edit_hex(self, text):
        value = text if text.startswith('#') else '#' + text
        valid = bool(re.fullmatch(r'#[0-9a-fA-F]{6}', value))
        self.use.setEnabled(valid)
        self.error.setText(tr('Enter six digits, for example #2879ED.') if not valid else '')
        if valid:
            self.set_color(QColor(value))

    def edit_rgb(self, *args):
        self.set_color(QColor(*[field.value() for field in self.rgb]))

    def change_hue(self, color):
        self.plane.hue = self.hue.hue
        self.set_color(color)

    def accept(self):
        if self.use.isEnabled():
            super().accept()
