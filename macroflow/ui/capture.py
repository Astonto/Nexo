from PySide6.QtCore import QPointF, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (QCheckBox, QDialog, QDoubleSpinBox, QHBoxLayout,
                               QLayout, QPushButton, QScrollArea, QStyle, QStyleOptionButton, QVBoxLayout, QWidget)

from ..recording import modifier_token, token_vk
from ..triggers import key_label
from .widgets import label, configure_number
from .theme import icon, accent_color


class FlowLayout(QLayout):

    def __init__(self, parent):
        super().__init__(parent)
        self.items = []
        self.setContentsMargins(20, 22, 20, 22)
        self.setSpacing(14)

    def addItem(self, item):
        self.items.append(item)

    def count(self):
        return len(self.items)

    def itemAt(self, index):
        return self.items[index] if 0 <= index < len(self.items) else None

    def takeAt(self, index):
        return self.items.pop(index) if 0 <= index < len(self.items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self.arrange(QRect(0, 0, width, 0), True)

    def minimumSize(self):
        size = QSize()
        for item in self.items:
            size = size.expandedTo(item.minimumSize())
        left, top, right, bottom = self.getContentsMargins()
        return size + QSize(left + right, top + bottom)

    def sizeHint(self):
        return self.minimumSize()

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self.arrange(rect, False)

    def arrange(self, rect, measure):
        left, top, right, bottom = self.getContentsMargins()
        area = rect.adjusted(left, top, -right, -bottom)
        x, y, row_height = area.x(), area.y(), 0
        for item in self.items:
            if item.isEmpty():
                continue
            size = item.sizeHint()
            if x + size.width() > area.right() + 1 and row_height:
                x, y, row_height = area.x(), y + row_height + self.spacing(), 0
            if not measure:
                item.setGeometry(QRect(x, y, size.width(), size.height()))
            x += size.width() + self.spacing()
            row_height = max(row_height, size.height())
        return y + row_height - rect.y() + bottom


class FlowSurface(QWidget):
    resized = Signal()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.layout():
            self.setMinimumHeight(self.layout().heightForWidth(self.width()))
        self.resized.emit()


class CaptureCheckBox(QCheckBox):
    def paintEvent(self, event):
        super().paintEvent(event)
        if self.isChecked():
            option = QStyleOptionButton()
            self.initStyleOption(option)
            rect = self.style().subElementRect(QStyle.SubElement.SE_CheckBoxIndicator, option, self)
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(QPen(QColor("#ffffff"), 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawPolyline(QPolygonF([QPointF(rect.x() + 4, rect.center().y()),
                                            QPointF(rect.x() + 7, rect.bottom() - 4),
                                            QPointF(rect.right() - 3, rect.y() + 4)]))


class KeyTile(QWidget):
    def __init__(self, event, parent):
        super().__init__(parent)
        code = token_vk(event.key)
        self.text = key_label(code) if code else event.key.removeprefix("char:").removeprefix("key:")
        self.pressed = event.kind == "key_down"
        self.setFont(QFont("Inter", 11, QFont.Weight.DemiBold))
        self.setFixedSize(max(48, min(180, self.fontMetrics().horizontalAdvance(self.text) + 28)), 80)
        description = ("Pulsar " if self.pressed else "Soltar ") + self.text
        self.setToolTip(description)
        self.setAccessibleName(description)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(accent_color(self).darker(200 if self.pressed else 260))
        painter.drawRoundedRect(QRectF(0, 20, self.width(), 40), 4, 4)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(QRect(4, 20, self.width() - 8, 40), Qt.AlignmentFlag.AlignCenter, self.text)
        center = self.width() / 2
        points = [(center - 7, 66), (center + 7, 66), (center, 73)] if self.pressed else [(center - 7, 14), (center + 7, 14), (center, 7)]
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#ffffff"))
        painter.drawPolygon(QPolygonF([QPointF(x, y) for x, y in points]))


class StopTile(QPushButton):
    def __init__(self, stop, parent):
        super().__init__(parent)
        self.setFixedSize(56, 80)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAutoDefault(False)
        self.setToolTip("Detener captura y revisar antes de guardar")
        self.setAccessibleName("Detener captura")
        self.clicked.connect(stop)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#454545" if self.underMouse() else "#292929"))
        painter.drawRoundedRect(QRectF(0, 20, 56, 40), 4, 4)
        painter.setPen(QColor("#eeeeee"))
        painter.setBrush(accent_color(self) if self.isEnabled() else QColor('#555555'))
        painter.drawRoundedRect(QRectF(20, 32, 16, 16), 2, 2)


class KeyCaptureDialog(QDialog):

    def __init__(self, parent, stop):
        super().__init__(parent)
        self.owner, self.stop_capture = parent, stop
        self.events, self.fingerprint = [], None
        self.rendered = self.total = 0
        self.can_undo = False
        self.phase = "running"
        self.reviewing = False
        self.setObjectName("captureRoot")
        self.setWindowTitle("Nexo · Capturar pulsaciones")
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.resize(1080, 660)
        self.setMinimumSize(760, 500)
        self.setStyleSheet("""
            QDialog#captureRoot, QWidget#captureSurface { background:#000000; color:#eee; }
            QLabel#captureMuted { color:#a0a0a5; font-size:13px; font-weight:450; background:transparent; }
            QLabel#captureTitle { font-size:28px; font-weight:700; background:transparent; }
            QLabel#captureEyebrow { color:#a0a0a5; font-size:11px; font-weight:600; }
            QLabel#captureState { background:#212225; border:none; border-radius:10px; padding:6px 12px; font-weight:600; }
            QLabel#captureMode { color:#fff; background:#212225; border-radius:6px; padding:8px 12px; font-weight:600; }
            QLabel#captureInterval { color:#a0a0a5; font-size:11px; font-weight:600; }
            QPushButton { background:#212225; color:#fff; border:none; border-radius:7px; padding:10px 16px; font-weight:650; }
            QPushButton:hover, QPushButton:pressed { background:#2e2f32; color:#fff; }
            QPushButton:disabled { color:#777; background:#212225; }
            QPushButton#captureFinish { background:#212225; color:white; font-weight:650; }
            QPushButton#captureFinish:hover { background:#2e2f32; color:white; }
            QPushButton#captureFinish:disabled { background:#212225; color:#777; }
            QPushButton#captureBack { border:0; background:transparent; font-size:24px; padding:0; }
            QScrollArea { border:1px solid #292929; border-radius:8px; background:#0c0c0c; }
            QCheckBox { color:#fff; spacing:9px; font-weight:550; }
            QDoubleSpinBox { background:#212225; color:white; border:none; border-radius:6px; padding:7px 4px 7px 9px; font-weight:600; }
            QDoubleSpinBox:enabled:hover { background:#2e2f32; }
            QDoubleSpinBox:disabled { color:#ccc; border:none; }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(16)
        header = QHBoxLayout()
        back = self.action("‹", self.stop_capture)
        back.setObjectName("captureBack")
        back.setFixedSize(32, 32)
        back.setToolTip("Terminar y volver al editor")
        back.setAccessibleName("Terminar y volver al editor")
        header.addWidget(back)
        header.addWidget(label("CAPTURA POR PULSACIONES", "captureEyebrow"))
        header.addStretch()
        self.state = label("● Grabando", "captureState")
        header.addWidget(self.state)
        layout.addLayout(header)
        self.heading = label("Nueva macro", "captureTitle")
        layout.addWidget(self.heading)
        options = QHBoxLayout()
        self.mode = label("Una pulsación", "captureMode")
        options.addWidget(self.mode)
        options.addStretch()
        options.addWidget(label("INTERVALO FIJO", "captureInterval"))
        self.delay = configure_number(QDoubleSpinBox())
        self.delay.setRange(.01, 86400)
        self.delay.setDecimals(2)
        self.delay.setSuffix(" s")
        self.delay.setMaximumWidth(120)
        self.delay.setAccessibleName("Intervalo fijo entre pulsaciones")
        self.delay.setToolTip("Pausa la captura para cambiar el intervalo de toda la secuencia")
        self.delay.valueChanged.connect(self.interval_changed)
        options.addWidget(self.delay)
        layout.addLayout(options)
        self.show_releases = CaptureCheckBox("Mostrar pulsación y liberación")
        self.show_releases.setChecked(True)
        self.show_releases.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.show_releases.toggled.connect(self.render_events)
        layout.addWidget(self.show_releases)
        self.info = label("Pulsa las teclas aquí. Mantener una tecla añade sus repeticiones. Pausa para ajustar el intervalo.", "captureMuted", True)
        layout.addWidget(self.info)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.strip = FlowSurface()
        self.strip.setObjectName("captureSurface")
        self.keys = FlowLayout(self.strip)
        self.stop_button = StopTile(self.stop_for_review, self.strip)
        self.empty = label("Pulsa una tecla para comenzar", "captureMuted")
        self.empty.setParent(self.strip)
        self.keys.addWidget(self.stop_button)
        self.keys.addWidget(self.empty)
        self.scroll.setWidget(self.strip)
        self.scroll_timer = QTimer(self)
        self.scroll_timer.setSingleShot(True)
        self.scroll_timer.timeout.connect(self.reveal_stop)
        self.strip.resized.connect(lambda: self.scroll_timer.start(0))
        layout.addWidget(self.scroll, 1)
        metrics = QHBoxLayout()
        self.count = label("0 pulsaciones · 0 acciones", "captureMuted")
        self.preview_note = label("▼ Pulsar    ▲ Soltar", "captureMuted")
        metrics.addWidget(self.count)
        metrics.addStretch()
        metrics.addWidget(self.preview_note)
        layout.addLayout(metrics)
        footer = QHBoxLayout()
        self.reset_button = self.action("Restablecer", lambda: self.reset_events(False))
        self.undo_button = self.action("Deshacer borrado", lambda: self.reset_events(True))
        self.undo_button.hide()
        self.pause_button = self.action("Pausar", self.pause_capture)
        self.review_stop = self.action("Detener", self.stop_for_review)
        self.review_stop.setIcon(icon("stop"))
        self.review_stop.setToolTip("Detener la captura para revisarla antes de guardar")
        self.finish_button = self.action("Terminar y guardar", stop)
        self.finish_button.setIcon(icon("save"))
        self.finish_button.setToolTip("Detén la captura para habilitar el guardado")
        self.finish_button.setObjectName("captureFinish")
        footer.addWidget(self.reset_button)
        footer.addWidget(self.undo_button)
        footer.addStretch()
        footer.addWidget(self.pause_button)
        footer.addWidget(self.review_stop)
        footer.addWidget(self.finish_button)
        layout.addLayout(footer)
        self.shortcuts = label("", "captureMuted", True)
        layout.addWidget(self.shortcuts)

    def action(self, text, callback):
        control = QPushButton(text)
        control.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        control.setAutoDefault(False)
        control.clicked.connect(callback)
        control.setCursor(Qt.CursorShape.PointingHandCursor)
        return control

    def begin(self, name, interval, shortcut, mode="once"):
        self.reviewing = False
        self.events, self.fingerprint = [], None
        self.can_undo = False
        self.heading.setText(name)
        self.mode.setText({"once": "Una pulsación", "hold": "Mantener presionado", "toggle": "Alternar"}.get(mode, mode))
        self.delay.blockSignals(True)
        self.delay.setValue(interval)
        self.delay.blockSignals(False)
        from ..triggers import display_binding
        emergency = display_binding(self.owner.settings.data["hotkeys"]["emergency"]) if self.owner else "Pause"
        self.shortcuts.setText(f"Detener: {shortcut}   ·   Emergencia: {emergency}")
        self.render_events()
        self.set_phase(self.owner.engine.phase if self.owner else "running")
        self.show()
        self.activateWindow()
        self.setFocus()

    def set_phase(self, phase):
        if self.reviewing and phase == "paused":
            phase = "review"
        self.phase = phase
        self.state.setText({"countdown": "◷ Preparando", "running": "● Grabando", "paused": "Ⅱ En pausa", "review": "Captura detenida · Revisa y guarda", "stopping": "Guardando…"}.get(phase, "● Grabando"))
        self.state.setStyleSheet(f"color:{'#ffb800' if phase in ('paused', 'review') else accent_color(self).name()}; background:#212225; border:none;")
        self.pause_button.setText("Continuar grabación" if phase == "review" else "Reanudar" if phase == "paused" else "Pausar")
        self.pause_button.setIcon(icon("play" if phase in ("paused", "review") else "pause"))
        self.review_stop.setEnabled(phase in ("running", "paused"))
        self.pause_button.setEnabled(phase in ("running", "paused", "review"))
        self.delay.setEnabled(phase in ("paused", "review"))
        self.reset_button.setEnabled(bool(self.events) and phase in ("running", "paused", "review"))
        self.undo_button.setVisible(self.can_undo)
        self.undo_button.setEnabled(phase in ("running", "paused", "review"))
        self.finish_button.setEnabled(phase == "review")
        self.stop_button.setEnabled(phase in ("running", "paused"))

    def stop_for_review(self):
        if self.reviewing or self.phase not in ("running", "paused"):
            return
        if self.owner and self.owner.engine.phase == "running":
            self.owner.pause_task()
        self.reviewing = True
        if self.owner and self.owner.engine.recorder:
            self.update_events(self.owner.engine.recorder.snapshot())
        self.set_phase("review")

    def reveal_stop(self):
        self.keys.invalidate()
        self.strip.setMinimumHeight(self.keys.heightForWidth(self.strip.width()))
        self.keys.setGeometry(self.strip.rect())
        self.scroll.ensureWidgetVisible(self.stop_button, 20, 20)

    def update_events(self, events, can_undo=False):
        fingerprint = (len(events), events[0] if events else None, events[-1] if events else None, self.delay.value())
        self.can_undo = can_undo
        if fingerprint != self.fingerprint:
            self.events = list(events)
            self.fingerprint = fingerprint
            self.render_events()
        self.set_phase(self.phase)

    def render_events(self, *args):
        while self.keys.count():
            widget = self.keys.takeAt(0).widget()
            if widget not in (self.stop_button, self.empty):
                widget.hide()
                widget.deleteLater()
        preview = [event for event in self.events if event.kind == "key_down" or (self.show_releases.isChecked() and event.kind == "key_up")]
        for event in preview[-100:]:
            tile = KeyTile(event, self.strip)
            self.keys.addWidget(tile)
            tile.show()
        self.keys.addWidget(self.stop_button)
        self.empty.setVisible(not preview)
        if not preview:
            self.keys.addWidget(self.empty)
        self.total = sum(event.kind == "key_down" and not modifier_token(event.key) for event in self.events)
        self.rendered = len(self.events)
        self.count.setText(f"{self.total:,} pulsaciones · {len(self.events):,} acciones · {sum(event.delay for event in self.events):g} s")
        self.preview_note.setText("Últimas 100 acciones · Se guardan todas" if len(preview) > 100 else "▼ Pulsar    ▲ Soltar")
        self.strip.setMinimumHeight(self.keys.heightForWidth(self.strip.width()))
        self.keys.activate()
        self.scroll_timer.start(0)

    def interval_changed(self, interval):
        if not self.owner or self.phase not in ("paused", "review"):
            return
        self.owner.engine.set_record_interval(interval)
        self.owner.fixed_interval.setValue(interval)
        self.owner.settings.data["fixed_interval"] = interval
        self.owner.settings.save()
        recorder = self.owner.engine.recorder
        if recorder:
            self.update_events(recorder.snapshot(), recorder.can_undo_reset)

    def reset_events(self, undo):
        if self.owner and self.owner.engine.reset_recording(undo):
            self.fingerprint = None
            recorder = self.owner.engine.recorder
            self.update_events(recorder.snapshot(), recorder.can_undo_reset)
        self.setFocus()

    def pause_capture(self):
        if self.owner:
            self.reviewing = False
            self.owner.pause_task()
            self.set_phase(self.owner.engine.phase)
        self.setFocus()

    def keyPressEvent(self, event):
        event.accept()

    def keyReleaseEvent(self, event):
        event.accept()

    def reject(self):
        self.stop_capture()

    def closeEvent(self, event):
        self.stop_capture()
        event.ignore()
