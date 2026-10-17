from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QGridLayout, QProgressBar, QVBoxLayout, QWidget

from ..models import LABELS
from ..recording import token_vk
from ..triggers import display_binding, key_label
from .widgets import button, card, combo, duration_text, label, row, spin
from .theme import icon


def glyph(name, size=20):
    widget = label("")
    widget.setPixmap(icon(name).pixmap(size, size))
    widget.setFixedSize(size, size)
    return widget


def event_text(event):
    if event.key:
        vk = token_vk(event.key)
        detail = key_label(vk) if vk else event.key.removeprefix("char:").removeprefix("key:")
    elif event.x is not None:
        detail = f"{event.button or ''}  X {event.x} · Y {event.y}"
    else:
        detail = f"{event.delay:g} s"
    return f"{LABELS[event.kind]} · {detail}"


class Console(QWidget):

    def __init__(self, owner):
        super().__init__()
        self.owner = owner
        self.index = 0
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(24)
        for i in range(3):
            grid.setColumnStretch(i, 1)

        recorder, content = card()
        recorder.setMinimumHeight(400)
        self.record_state = label("EN ESPERA", "muted")
        content.addWidget(row(glyph("record"), label("Grabador", "sectionTitle"), None, self.record_state))
        self.timer = label("00:00.000", "consoleTimer")
        self.timer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.count = label("0 acciones registradas", "muted")
        self.count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content.addWidget(self.timer)
        content.addWidget(self.count)
        self.moves = QCheckBox("Capturar movimientos del ratón")
        content.addWidget(self.moves)
        self.mode = combo([("Tiempo real", "timed"), ("Pulsaciones · intervalo fijo", "fixed")])
        content.addWidget(self.mode)
        self.countdown = spin(0, 30, 3, " s")
        content.addWidget(row(label("Cuenta regresiva", "muted"), None, self.countdown))
        self.record = button("Iniciar grabación", owner.start_recording, symbol="record", primary=True)
        self.record_stop = button("Detener", owner.stop_task, symbol="stop")
        for item in (self.record, self.record_stop):
            item.setStyleSheet("padding:9px 8px; font-size:12px;")
        content.addWidget(row(self.record, self.record_stop))
        self.target = label("Se guardará en la macro seleccionada.", "muted", True)
        content.addWidget(self.target)
        content.addWidget(button("Opciones de grabación", lambda: owner.change_page(1)))
        grid.addWidget(recorder, 0, 0)

        player, content = card()
        self.play_state = label("REPRODUCTOR", "muted")
        self.progress_text = label("Sin reproducción activa", "muted")
        controls, controls_layout = card()
        controls_layout.setContentsMargins(12, 10, 12, 10)
        controls_layout.setSpacing(8)
        controls_layout.addWidget(row(glyph("play", 14), self.play_state, None, self.progress_text))
        self.previous = button("Anterior", lambda: owner.engine.seek(-1))
        self.pause = button("Pausar", owner.pause_task)
        self.next = button("Siguiente", lambda: owner.engine.seek(1))
        self.restart = button("Reiniciar", lambda: owner.engine.seek(restart=True))
        self.stop = button("Detener", owner.stop_task, symbol="stop")
        for widget in (self.previous, self.pause, self.next, self.restart, self.stop):
            widget.setStyleSheet("padding:7px 10px;")
        controls_layout.addWidget(row(self.previous, self.pause, self.next, self.restart, self.stop))
        content.addWidget(controls)
        self.name = label("Selecciona una macro", "pageTitle", True)
        self.shortcut = label("", "keycap")
        self.elapsed = label("00:00.000", "muted")
        content.addWidget(row(self.name, self.shortcut, None, self.elapsed))
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        content.addWidget(self.progress)
        self.action = label("Añade o graba acciones para comenzar.", "currentAction", True)
        self.action.setMinimumHeight(78)
        content.addWidget(self.action)
        self.following = label("", "muted", True)
        content.addWidget(self.following)
        content.addStretch()
        self.parameters = label("", "muted", True)
        content.addWidget(self.parameters)
        self.play = button("Reproducir", owner.start_playback, primary=True, symbol="play")
        content.addWidget(row(self.play, button("Opciones", lambda: owner.change_page(2)), None))
        grid.addWidget(player, 0, 1, 1, 2)

        shortcuts, content = card("Controles de grabación")
        shortcuts.setMinimumHeight(280)
        self.shortcuts = {}
        for key, name in (("record_start", "Iniciar"), ("record_stop", "Detener"), ("record_pause", "Pausar")):
            value = label("", "keycap")
            self.shortcuts[key] = value
            content.addWidget(row(label(name, "muted"), None, value))
        content.addStretch()
        content.addWidget(label("Los atajos de control no se guardan en la grabación.", "muted", True))
        content.addWidget(button("Configurar controles", lambda: owner.change_page(6), symbol="settings"))
        grid.addWidget(shortcuts, 1, 0)

        quick, content = card()
        content.addWidget(row(label("Acceso rápido", "sectionTitle"), None,
                              button("Ver todas", lambda: owner.change_page(5))))
        self.quick = QVBoxLayout()
        self.quick.setSpacing(12)
        content.addLayout(self.quick)
        content.addStretch()
        self.policy = label("", "muted", True)
        content.addWidget(self.policy)
        grid.addWidget(quick, 1, 1)

        clicker, content = card()
        self.click_state = label("DETENIDO", "muted")
        content.addWidget(row(glyph("click"), label("Autoclicker", "sectionTitle"), None, self.click_state))
        self.click_kind = combo([("Ratón", "mouse"), ("Teclado", "keyboard")])
        self.click_target = label("Izquierdo", "muted")
        content.addWidget(row(self.click_kind, self.click_target))
        self.interval = spin(10, 90000000, 100, " ms")
        self.repetitions = spin(0, 10000000, 100)
        self.repetitions.setSpecialValueText("Sin límite")
        content.addWidget(row(label("Intervalo", "muted"), None, self.interval))
        content.addWidget(row(label("Repeticiones", "muted"), None, self.repetitions))
        content.addWidget(button("Configurar tecla / ratón", lambda: owner.change_page(3)))
        content.addStretch()
        self.click = button("Iniciar autoclicker", owner.start_clicker, symbol="play")
        content.addWidget(self.click)
        grid.addWidget(clicker, 1, 2)

    def wire(self):
        o = self.owner
        self.moves.setChecked(o.capture_moves.isChecked())
        self.moves.toggled.connect(o.capture_moves.setChecked)
        o.capture_moves.toggled.connect(self.moves.setChecked)
        for first, second, signal, setter in ((self.mode, o.record_mode, "currentIndexChanged", "setCurrentIndex"),
                                              (self.countdown, o.record_countdown, "valueChanged", "setValue"),
                                              (self.click_kind, o.click_kind, "currentIndexChanged", "setCurrentIndex")):
            getattr(first, setter)(second.currentIndex() if setter == "setCurrentIndex" else second.value())
            getattr(first, signal).connect(getattr(second, setter))
            getattr(second, signal).connect(getattr(first, setter))
        self.interval.valueChanged.connect(self.set_interval)
        for field in (o.interval_hours, o.interval_minutes, o.interval_seconds, o.interval_ms):
            field.valueChanged.connect(self.read_interval)
        self.repetitions.valueChanged.connect(lambda value: (o.click_infinite.setChecked(value == 0), o.click_repetitions.setValue(value or 1)))
        o.click_repetitions.valueChanged.connect(lambda value: self.read_repetitions())
        o.click_infinite.toggled.connect(lambda value: self.read_repetitions())
        self.update_settings()

    def set_interval(self, value):
        o = self.owner
        parts = (value // 3600000, value // 60000 % 60, value // 1000 % 60, value % 1000)
        fields = (o.interval_hours, o.interval_minutes, o.interval_seconds, o.interval_ms)
        for field, part in zip(fields, parts):
            field.blockSignals(True)
            field.setValue(part)
            field.blockSignals(False)

    def read_interval(self):
        o = self.owner
        self.interval.blockSignals(True)
        self.interval.setValue(o.interval_hours.value() * 3600000 + o.interval_minutes.value() * 60000 + o.interval_seconds.value() * 1000 + o.interval_ms.value())
        self.interval.blockSignals(False)

    def read_repetitions(self):
        o = self.owner
        self.repetitions.blockSignals(True)
        self.repetitions.setValue(0 if o.click_infinite.isChecked() else o.click_repetitions.value())
        self.repetitions.blockSignals(False)

    def update_settings(self):
        for action, field in self.shortcuts.items():
            field.setText(display_binding(self.owner.settings.data["hotkeys"][action]))
        self.policy.setText("Si otra macro está activa: " + ("poner en cola." if self.owner.settings.data["concurrency"] == "queue" else "bloquear la segunda."))

    def update_library(self):
        while self.quick.count():
            self.quick.takeAt(0).widget().deleteLater()
        macros = sorted(self.owner.macros.values(), key=lambda m: m.modified, reverse=True)[:3]
        for macro in macros:
            trigger = label(display_binding(macro.trigger) or "—", "keycap")
            name = label(macro.name, wrap=True)
            play = button("", lambda checked=False, identifier=macro.id: self.play_macro(identifier), symbol="play")
            play.setFixedWidth(38)
            play.setToolTip("Reproducir " + macro.name)
            play.setEnabled(not self.owner.engine.busy)
            self.quick.addWidget(row(trigger, name, None, play))
        if not macros:
            self.quick.addWidget(label("Crea tu primera macro desde Nueva.", "muted", True))

    def play_macro(self, identifier):
        if self.owner.require_idle():
            self.owner.select_macro(identifier)
            self.owner.start_playback()

    def update_progress(self, data):
        self.index = min(data["index"], data["total"] - 1)
        self.progress.setValue(round(data["index"] / data["total"] * 100))
        self.progress_text.setText(f"{min(data['index'] + 1, data['total'])} / {data['total']} acciones")
        self.elapsed.setText(duration_text(data["elapsed"])[3:])
        self.refresh_action()

    def refresh_action(self):
        o = self.owner
        macro = o.macros.get(o.engine.active_id) or o.current
        if not macro:
            return
        self.name.setText(macro.name)
        self.shortcut.setText(display_binding(macro.trigger) or "Sin atajo")
        self.parameters.setText(f"Velocidad  {macro.speed:g}×    Repeticiones  {macro.repetitions}    Modo  " + {"once": "Una pulsación", "hold": "Mantener", "toggle": "Alternar"}[macro.activation])
        index = self.index if o.engine.task == "play" else 0
        if macro.events and index < len(macro.events):
            self.action.setText(f"{index + 1:02}     {event_text(macro.events[index])}")
            self.following.setText("SIGUIENTE     " + event_text(macro.events[index + 1]) if index + 1 < len(macro.events) else "Fin de la secuencia")
        else:
            self.action.setText("Añade o graba acciones para comenzar.")
            self.following.setText("")

    def sync(self):
        o = self.owner
        busy, task, phase = o.engine.busy, o.engine.task, o.engine.phase
        self.record.setEnabled(not busy)
        self.record_stop.setEnabled(task == "record")
        self.record_state.setText("GRABANDO" if task == "record" else "EN ESPERA")
        self.play.setEnabled(not busy and o.current is not None and bool(o.current.events))
        self.play_state.setText("EN PAUSA" if phase == "paused" else "REPRODUCIENDO" if task == "play" else "REPRODUCTOR")
        self.pause.setText("Reanudar" if phase == "paused" else "Pausar")
        for widget in (self.previous, self.pause, self.next, self.restart):
            widget.setEnabled(task == "play" and phase in ("running", "paused"))
        self.stop.setEnabled(task == "play")
        self.click.setEnabled(not busy or task == "click")
        self.click.setText("Detener autoclicker" if task == "click" else "Iniciar autoclicker")
        self.click_state.setText("EN CURSO" if task == "click" else "DETENIDO")
        for widget in (self.moves, self.mode, self.countdown, self.interval, self.repetitions, self.click_kind):
            widget.setEnabled(not busy)
        self.moves.setEnabled(not busy and self.mode.currentData() == "timed")
        self.click_target.setText(display_binding(o.repeat_key.text()) if o.click_kind.currentData() == "keyboard" else o.click_button.currentText())
        self.target.setText("Se guardará en «" + o.current.name + "»." if o.current else "Se creará una macro para esta grabación.")
        self.refresh_action()
