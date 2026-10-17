from ..i18n import tr
from PySide6.QtCore import Qt, QTimer, QElapsedTimer, QEvent, QPointF, QRectF, QRect, QVariantAnimation, QEasingCurve, QObject
from PySide6.QtGui import QPainter, QPainterPath, QLinearGradient, QColor, QFont, QPen, QIcon, QBrush, QPalette
from PySide6.QtWidgets import (QComboBox, QCompleter, QListView, QDoubleSpinBox, QFrame, QHBoxLayout, QLabel,
                               QPushButton, QLineEdit, QSpinBox, QVBoxLayout, QWidget, QStyleOptionButton, QStyle, QStyledItemDelegate, QTableWidget)

from .theme import icon, accent_color


def light_surface(widget):
    return widget.palette().color(QPalette.ColorRole.WindowText).lightness() < 128


class LibraryDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        option.state &= ~QStyle.StateFlag.State_HasFocus
        self.initStyleOption(option, index)
        table = self.parent()
        dark = not light_surface(table)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        background = ('#141517' if dark else '#f0f2f5') if index.row() % 2 else ('#000000' if dark else '#ffffff')
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(option.rect, QColor(background))
        painter.setPen(Qt.PenStyle.NoPen)
        if selected:
            columns = [c for c in range(index.model().columnCount()) if not table.isColumnHidden(c)]
            first = table.visualRect(index.siblingAtColumn(columns[0]))
            last = table.visualRect(index.siblingAtColumn(columns[-1]))
            painter.save()
            painter.setClipRect(option.rect)
            painter.setBrush(QColor('#303238' if dark else '#dce1e9'))
            painter.drawRoundedRect(QRectF(first.united(last)).adjusted(2, 2, -2, -2), 7, 7)
            painter.restore()
        if hovered:
            painter.setBrush(QColor('#41444c' if dark and selected else '#2e2f32' if dark else '#c8ced8' if selected else '#e0e4eb'))
            painter.drawRoundedRect(QRectF(option.rect).adjusted(3, 3, -3, -3), 6, 6)
        painter.setFont(option.font)
        painter.setPen(option.palette.color(QPalette.ColorRole.Text))
        area = option.rect.adjusted(12, 0, -12, 0)
        text = option.fontMetrics.elidedText(option.text, Qt.TextElideMode.ElideRight, area.width())
        painter.drawText(area, int(option.displayAlignment | Qt.AlignmentFlag.AlignVCenter), text)
        painter.restore()


class TableOutline(QWidget):

    def __init__(self, table):
        super().__init__(table)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        curve = QPainterPath()
        curve.addRoundedRect(QRectF(self.rect()).adjusted(.5, .5, -.5, -.5), 10, 10)
        outside = QPainterPath()
        outside.addRect(QRectF(self.rect()))
        outside = outside.subtracted(curve)
        painter.fillPath(outside, QColor('#f5f5f5' if light_surface(self) else '#000000'))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor('#c3c7ce' if light_surface(self) else '#37383d'), 1))
        painter.drawPath(curve)


class LibraryTable(QTableWidget):
    def __init__(self, *args):
        super().__init__(*args)
        self.outline = TableOutline(self)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.outline.setGeometry(self.rect())
        self.outline.raise_()
        QTimer.singleShot(0, self.outline.raise_)


class ThemedButton(QPushButton):
    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.PaletteChange and getattr(self, 'symbol', None):
            self.setIcon(icon(self.symbol, accent_color(self).name() if self.property('danger') else '#555961' if light_surface(self) else '#b0b0b0'))


class LockSwitch(QPushButton):
    def __init__(self, callback):
        super().__init__()
        self.setCheckable(True)
        self.setFixedSize(42, 27)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(tr('Lock Nexo'))
        self.position = 0.0
        self.motion = QVariantAnimation(self)
        self.motion.setDuration(200)
        self.motion.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.motion.valueChanged.connect(self.advance)
        self.toggled.connect(self.animate)
        self.toggled.connect(callback)
        self.setToolTip(tr('Lock Nexo: off'))

    def advance(self, value):
        self.position = float(value)
        self.update()

    def animate(self, checked):
        self.setToolTip(tr('Lock Nexo: on') if checked else tr('Lock Nexo: off'))
        self.motion.stop()
        self.motion.setStartValue(self.position)
        self.motion.setEndValue(1.0 if checked else 0.0)
        self.motion.start()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = self.position
        off = QColor('#8a909a' if light_surface(self) else '#484b53')
        on = accent_color(self)
        tone = QColor(*[round(off.getRgb()[i] * (1-t) + on.getRgb()[i] * t) for i in range(3)])
        painter.setPen(Qt.PenStyle.NoPen)
        rim = QLinearGradient(0, 1, 0, 25)
        rim.setColorAt(0, QColor('#fafbfc' if light_surface(self) else '#767e89'))
        rim.setColorAt(.5, QColor('#e3e6ea' if light_surface(self) else '#3c424b'))
        rim.setColorAt(1, QColor('#f3f5f7' if light_surface(self) else '#555e6a'))
        painter.setBrush(rim)
        painter.drawRoundedRect(QRectF(.5, 1, 41, 24), 12, 12)
        gradient = QLinearGradient(0, 3, 0, 23)
        gradient.setColorAt(0, tone.darker(220))
        gradient.setColorAt(.35, tone.darker(130))
        gradient.setColorAt(1, tone)
        painter.setBrush(gradient)
        painter.drawRoundedRect(QRectF(2, 3, 38, 20), 10, 10)
        painter.setPen(QPen(QColor(0, 0, 0, 120), 1))
        painter.drawRoundedRect(QRectF(2.5, 3.5, 37, 19), 9.5, 9.5)
        painter.setPen(Qt.PenStyle.NoPen)
        x = 3 + 18*t
        painter.setBrush(QColor(0, 0, 0, 130))
        painter.drawEllipse(QRectF(x, 4, 19, 19))
        knob = QLinearGradient(0, 4, 0, 21)
        knob.setColorAt(0, QColor('#ffffff'))
        knob.setColorAt(.65, QColor('#f9fafb'))
        knob.setColorAt(1, QColor('#dce0e5'))
        painter.setBrush(knob)
        painter.setPen(QPen(QColor('#b0b6be'), .6))
        painter.drawEllipse(QRectF(x+.5, 4, 17.5, 17.5))


def shimmer_pen(widget, left=0):
    width = widget.fontMetrics().horizontalAdvance(widget.text())
    center = left - 32 + (width + 64) * ((widget.shimmer_clock.elapsed() / 1000 % 4.8) / 4.8)
    gradient = QLinearGradient(center - 28, 0, center + 28, widget.height())
    base, shine = ('#343840', '#707681') if light_surface(widget) else ('#bfc0c5', '#ffffff')
    gradient.setColorAt(0, QColor(base))
    gradient.setColorAt(.5, QColor(shine))
    gradient.setColorAt(1, QColor(base))
    return QPen(QBrush(gradient), 1)


class ShimmerLabel(QLabel):
    def __init__(self, text):
        super().__init__(text)
        self.shimmer_clock = QElapsedTimer()
        self.shimmer_clock.start()
        self.shimmer_timer = QTimer(self)
        self.shimmer_timer.setInterval(33)
        self.shimmer_timer.timeout.connect(self.update)

    def showEvent(self, event):
        self.shimmer_timer.start()
        super().showEvent(event)

    def hideEvent(self, event):
        self.shimmer_timer.stop()
        super().hideEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setFont(self.font())
        painter.setPen(shimmer_pen(self))
        flags = int(self.alignment())
        if self.wordWrap():
            flags |= int(Qt.TextFlag.TextWordWrap)
        painter.drawText(self.contentsRect(), flags, self.text())


def label(text, style=None, wrap=False):
    widget = ShimmerLabel(text) if style in ("pageTitle", "welcomeTitle", "captureTitle") else QLabel(text)
    if style:
        widget.setObjectName(style)
    widget.setWordWrap(wrap)
    return widget


class BrandButton(QPushButton):

    def __init__(self, callback):
        super().__init__("NEXO")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setMouseTracking(True)
        self.clicked.connect(callback)
        self.clock = QElapsedTimer()
        self.clock.start()
        self.motion = QTimer(self)
        self.motion.setInterval(33)
        self.motion.timeout.connect(self.update)

    def showEvent(self, event):
        self.motion.start()
        super().showEvent(event)

    def hideEvent(self, event):
        self.motion.stop()
        super().hideEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = self.font()
        metrics = self.fontMetrics()
        left = 15
        baseline = (self.height() - metrics.height()) / 2 + metrics.ascent()
        letters = QPainterPath()
        letters.addText(QPointF(left, baseline), font, self.text())
        seconds = self.clock.elapsed() / 1000
        text_width = metrics.horizontalAdvance(self.text())
        center = left - 32 + (text_width + 64) * ((seconds % 4.8) / 4.8)
        gradient = QLinearGradient(center - 28, 0, center + 28, self.height())
        base, shine = ('#343840', '#707681') if light_surface(self) else ('#bfc0c5', '#ffffff')
        gradient.setColorAt(0, QColor(base))
        gradient.setColorAt(.5, QColor(shine))
        gradient.setColorAt(1, QColor(base))
        painter.setOpacity(getattr(self, "detail_opacity", 1.0))
        painter.fillPath(letters, gradient)
        painter.setOpacity(1)
        first_letter = QPainterPath()
        first_letter.addText(QPointF(left, baseline), font, "N")
        painter.fillPath(first_letter, gradient)

    def hitButton(self, point):
        glyph_width = self.fontMetrics().horizontalAdvance("N")
        left = 15
        return left <= point.x() <= left + glyph_width and 0 <= point.y() < self.height()

    def mouseMoveEvent(self, event):
        self.setCursor(Qt.CursorShape.PointingHandCursor if self.hitButton(event.position().toPoint()) else Qt.CursorShape.ArrowCursor)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self.setCursor(Qt.CursorShape.ArrowCursor)
        super().leaveEvent(event)


class NavigationHint(QWidget):
    def __init__(self, owner):
        super().__init__(owner, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.caption = owner.toolTip()
        font = QFont("Inter")
        font.setPixelSize(13)
        font.setWeight(QFont.Weight.Medium)
        self.setFont(font)

    def reveal(self, owner):
        self.caption = owner.toolTip()
        self.resize(self.fontMetrics().horizontalAdvance(self.caption) + 40, 36)
        point = owner.mapToGlobal(owner.rect().topRight())
        self.move(point.x() + 7, point.y() + (owner.height() - self.height()) // 2)
        self.show()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        shape = QPainterPath()
        right, bottom = self.width() - .5, self.height() - .5
        shape.moveTo(15, .5)
        shape.lineTo(right - 8, .5)
        shape.quadTo(right, .5, right, 8.5)
        shape.lineTo(right, bottom - 8)
        shape.quadTo(right, bottom, right - 8, bottom)
        shape.lineTo(15, bottom)
        shape.quadTo(7, bottom, 7, bottom - 8)
        shape.lineTo(7, 24)
        shape.lineTo(1, 18)
        shape.lineTo(7, 12)
        shape.lineTo(7, 8.5)
        shape.quadTo(7, .5, 15, .5)
        shape.closeSubpath()
        painter.setPen(QPen(QColor('#343538'), 1))
        painter.setBrush(QColor('#0c0c0d'))
        painter.drawPath(shape)
        painter.setPen(QColor('#f5f5f5'))
        painter.drawText(self.rect().adjusted(15, 0, -10, 0), Qt.AlignmentFlag.AlignCenter, self.caption)


class NavigationButton(QPushButton):
    def __init__(self, name, callback, symbol):
        super().__init__(name)
        self.setIcon(icon("nav_" + symbol, "#bfc0c5"))
        self.active_icon = icon("nav_" + symbol, "#eeeeef")
        self.light_icon = icon("nav_" + symbol, "#666c77")
        self.light_active_icon = icon("nav_" + symbol, "#272b32")
        self.setToolTip(name)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(callback)
        self.hint = NavigationHint(self)
        self.hint_delay = QTimer(self)
        self.hint_delay.setSingleShot(True)
        self.hint_delay.setInterval(220)
        self.hint_delay.timeout.connect(lambda: self.hint.reveal(self) if self.underMouse() else None)
        self.shimmer_clock = QElapsedTimer()
        self.shimmer_clock.start()
        self.shimmer_timer = QTimer(self)
        self.shimmer_timer.setInterval(33)
        self.shimmer_timer.timeout.connect(self.update)
        self.toggled.connect(self.sync_shimmer)

    def sync_shimmer(self):
        if self.isChecked() and self.isVisible():
            self.shimmer_timer.start()
        else:
            self.shimmer_timer.stop()
        self.update()

    def showEvent(self, event):
        self.sync_shimmer()
        super().showEvent(event)

    def paintEvent(self, event):

        option = QStyleOptionButton()
        self.initStyleOption(option)
        option.state &= ~QStyle.StateFlag.State_HasFocus
        option.text = ""
        option.icon = QIcon()
        painter = QPainter(self)
        self.style().drawControl(QStyle.ControlElement.CE_PushButton, option, painter, self)
        current_icon = self.active_icon if self.isChecked() else self.icon()
        if light_surface(self):
            current_icon = self.light_active_icon if self.isChecked() else self.light_icon
        current_icon.paint(painter, QRect(13, (self.height() - 20) // 2, 20, 20))
        painter.setFont(self.font())
        painter.setPen(shimmer_pen(self, 43) if self.isChecked() else QColor('#555b65' if light_surface(self) else '#a0a0a5'))
        painter.setOpacity(getattr(self, "text_opacity", 1.0))
        painter.drawText(self.rect().adjusted(43, 0, -5, 0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.text())

    def event(self, event):
        if event.type() == QEvent.Type.ToolTip:
            return True
        return super().event(event)

    def enterEvent(self, event):
        self.hint_delay.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.dismiss_hint()
        super().leaveEvent(event)

    def hideEvent(self, event):
        self.dismiss_hint()
        self.shimmer_timer.stop()
        super().hideEvent(event)

    def mousePressEvent(self, event):
        self.dismiss_hint()
        self.drag_selected = None
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            point = event.globalPosition().toPoint()
            for target in self.window().findChildren(NavigationButton):
                if target.isVisible() and target.isEnabled() and target.rect().contains(target.mapFromGlobal(point)):
                    if target is not self and target is not getattr(self, 'drag_selected', None):
                        self.setDown(False)
                        self.drag_selected = target
                        target.click()
                    elif target is self and getattr(self, 'drag_selected', None) not in (None, self):
                        self.drag_selected = self
                        self.click()
                    break
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and getattr(self, 'drag_selected', None) is not None:
            self.drag_selected = None
            self.setDown(False)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        directions = {Qt.Key.Key_Up: -1, Qt.Key.Key_Left: -1, Qt.Key.Key_Down: 1, Qt.Key.Key_Right: 1}
        if event.key() in directions:
            tabs = [tab for tab in self.window().findChildren(NavigationButton) if tab.isVisible() and tab.isEnabled()]
            tabs.sort(key=lambda tab: tab.mapToGlobal(tab.rect().center()).y())
            if self in tabs:
                target = tabs[(tabs.index(self) + directions[event.key()]) % len(tabs)]
                self.dismiss_hint()
                target.setFocus(Qt.FocusReason.TabFocusReason)
                target.click()
                event.accept()
                return
        super().keyPressEvent(event)

    def dismiss_hint(self):
        self.hint_delay.stop()
        self.hint.hide()


def button(text, callback=None, *, symbol=None, primary=False, danger=False):
    widget = ThemedButton(text)
    widget.symbol = symbol
    if symbol:
        widget.setIcon(icon(symbol, "#ffffff" if primary else "#b0b0b0"))
    widget.setProperty("primary", primary)
    widget.setProperty("danger", danger)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    if callback:
        widget.clicked.connect(callback)
    return widget


def row(*widgets):
    container = QWidget()
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(10)
    for widget in widgets:
        if widget is None:
            layout.addStretch()
        else:
            layout.addWidget(widget)
    return container


def card(title=None, subtitle=None, hero=False):
    frame = QFrame()
    frame.setObjectName("hero" if hero else "card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(22, 20, 22, 20)
    layout.setSpacing(14)
    if title:
        layout.addWidget(label(title, "sectionTitle"))
    if subtitle:
        layout.addWidget(label(subtitle, "muted", True))
    return frame, layout


class Dropdown(QComboBox):
    def __init__(self):
        super().__init__()
        self.setView(QListView())
        self.view().setMouseTracking(True)
        self.setMaxVisibleItems(8)
        self.setCursor(Qt.CursorShape.PointingHandCursor)


class CategoryField(Dropdown):

    def __init__(self, categories, current):
        super().__init__()
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.setMinimumContentsLength(20)
        names = {}
        for value in [*categories, current]:
            value = value.strip()
            if value:
                names.setdefault(value.casefold(), value)
        self.addItems(sorted(names.values(), key=str.casefold))
        self.setEditText(current)
        self.lineEdit().setMaxLength(80)
        self.lineEdit().setPlaceholderText(tr('Type or select a category'))
        self.lineEdit().setStyleSheet('QLineEdit{background:transparent;border:0;padding:0;font-size:14px;font-weight:650;}')
        completer = self.completer()
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        completer.setMaxVisibleItems(8)
        completer.popup().setObjectName('categorySuggestions')
        popup = completer.popup()
        popup.setParent(self, popup.windowFlags())
        self.setToolTip(tr('Choose a category or type a new one; it is saved with the macro.'))
        self.setAccessibleName(tr('Macro category'))

    def text(self):
        value = self.currentText().strip()
        return next((self.itemText(i) for i in range(self.count()) if self.itemText(i).casefold() == value.casefold()), value)

    def setText(self, value):
        self.setEditText(value)


def combo(items):
    widget = Dropdown()
    for text, data in items:
        widget.addItem(text, data)
    return widget


class NumberSelection(QObject):
    def __init__(self, spinbox):
        super().__init__(spinbox)
        self.spinbox = spinbox
        self.adjusting = False
        spinbox.lineEdit().installEventFilter(self)
        spinbox.lineEdit().selectionChanged.connect(self.limit_selection)
        spinbox.lineEdit().cursorPositionChanged.connect(self.limit_cursor)
        spinbox.lineEdit().setMouseTracking(True)

    def bounds(self):
        return len(self.spinbox.prefix()), len(self.spinbox.lineEdit().text()) - len(self.spinbox.suffix())

    def limit_cursor(self, *args):
        field = self.spinbox.lineEdit()
        if self.adjusting or field.hasSelectedText():
            return
        start, end = self.bounds()
        position = max(start, min(end, field.cursorPosition()))
        if position != field.cursorPosition():
            self.adjusting = True
            field.setCursorPosition(position)
            self.adjusting = False

    def select_number(self):
        start, end = self.bounds()
        self.spinbox.lineEdit().setSelection(start, max(0, end-start))

    def limit_selection(self):
        field = self.spinbox.lineEdit()
        if self.adjusting or not field.hasSelectedText():
            return
        start, end = self.bounds()
        selected_start = field.selectionStart()
        selected_end = selected_start + len(field.selectedText())
        left, right = max(start, selected_start), min(end, selected_end)
        if left != selected_start or right != selected_end:
            self.adjusting = True
            field.setSelection(min(end, left), max(0, right-left))
            self.adjusting = False

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.MouseMove:
            start, end = self.bounds()
            position = watched.cursorPositionAt(event.position().toPoint())
            watched.setCursor(Qt.CursorShape.IBeamCursor if start <= position < end else Qt.CursorShape.ArrowCursor)
        if event.type() == QEvent.Type.FocusIn:
            QTimer.singleShot(0, watched, self.select_number)
        elif event.type() == QEvent.Type.MouseButtonDblClick or (event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_A and event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            self.select_number()
            return True
        return False


def configure_number(widget):
    widget.setMinimumHeight(38)
    widget.lineEdit().setStyleSheet('QLineEdit{padding:0;border:0;background:transparent;}')
    widget._number_selection = NumberSelection(widget)
    return widget


def spin(low, high, value, suffix="", decimals=None):
    widget = QDoubleSpinBox() if decimals is not None else QSpinBox()
    if decimals is not None:
        widget.setDecimals(decimals)
        widget.setSingleStep(0.1 if decimals < 3 else 0.01)
    widget.setRange(low, high)
    widget.setValue(value)
    widget.setSuffix(suffix)
    widget.setMinimumWidth(100)
    return configure_number(widget)


def duration_text(seconds):
    milliseconds = int(max(0, seconds) * 1000)
    hours, remainder = divmod(milliseconds, 3600000)
    minutes, remainder = divmod(remainder, 60000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02}.{millis:03}"


class DisplayTextPolicy(QObject):

    def eventFilter(self, watched, event):
        if isinstance(watched, QLabel) and event.type() in (QEvent.Type.Polish, QEvent.Type.Show):
            watched.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
            watched.setCursor(Qt.CursorShape.ArrowCursor)
        if isinstance(watched, QLineEdit) and watched.isReadOnly():
            if event.type() in (QEvent.Type.Polish, QEvent.Type.Show, QEvent.Type.Enter):
                watched.setCursor(Qt.CursorShape.ArrowCursor)
            if event.type() in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick, QEvent.Type.MouseMove, QEvent.Type.KeyPress):
                watched.deselect()
                return True
        return False


def install_display_text_policy(app):
    if not hasattr(app, '_display_text_policy'):
        app._display_text_policy = DisplayTextPolicy(app)
        app.installEventFilter(app._display_text_policy)
