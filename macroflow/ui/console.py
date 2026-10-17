from ..i18n import tr
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
        self.record_state = label(tr('IDLE'), "muted")
        content.addWidget(row(glyph("record"), label(tr('Recorder'), "sectionTitle"), None, self.record_state))
        self.timer = label("00:00.000", "consoleTimer")
        self.timer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.count = label(tr('0 recorded actions'), "muted")
        self.count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content.addWidget(self.timer)
        content.addWidget(self.count)
        self.moves = QCheckBox(tr('Capture mouse movements'))
        content.addWidget(self.moves)
        self.mode = combo([(tr('Real time'), "timed"), (tr('Keystrokes · fixed interval'), "fixed")])
        content.addWidget(self.mode)
        self.countdown = spin(0, 30, 3, " s")
        content.addWidget(row(label(tr('Countdown'), "muted"), None, self.countdown))
        self.record = button(tr('Start recording'), owner.start_recording, symbol="record", primary=True)
        self.record_stop = button(tr('Stop'), owner.stop_task, symbol="stop")
        for item in (self.record, self.record_stop):
            item.setStyleSheet("padding:9px 8px; font-size:12px;")
        content.addWidget(row(self.record, self.record_stop))
        self.target = label(tr('This recording will be saved to the selected macro.'), "muted", True)
        content.addWidget(self.target)
        content.addWidget(button(tr('Recording options'), lambda: owner.change_page(1)))
        grid.addWidget(recorder, 0, 0)

        player, content = card()
        self.play_state = label(tr('PLAYER'), "muted")
        self.progress_text = label(tr('Nothing playing'), "muted")
        controls, controls_layout = card()
        controls_layout.setContentsMargins(12, 10, 12, 10)
        controls_layout.setSpacing(8)
        controls_layout.addWidget(row(glyph("play", 14), self.play_state, None, self.progress_text))
        self.previous = button(tr('Previous'), lambda: owner.engine.seek(-1))
        self.pause = button(tr('Pause'), owner.pause_task)
        self.next = button(tr('Next'), lambda: owner.engine.seek(1))
        self.restart = button(tr('Restart'), lambda: owner.engine.seek(restart=True))
        self.stop = button(tr('Stop'), owner.stop_task, symbol="stop")
        for widget in (self.previous, self.pause, self.next, self.restart, self.stop):
            widget.setStyleSheet("padding:7px 10px;")
        controls_layout.addWidget(row(self.previous, self.pause, self.next, self.restart, self.stop))
        content.addWidget(controls)
        self.name = label(tr('Select a macro'), "pageTitle", True)
        self.shortcut = label("", "keycap")
        self.elapsed = label("00:00.000", "muted")
        content.addWidget(row(self.name, self.shortcut, None, self.elapsed))
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        content.addWidget(self.progress)
        self.action = label(tr('Add or record actions to get started.'), "currentAction", True)
        self.action.setMinimumHeight(78)
        content.addWidget(self.action)
        self.following = label("", "muted", True)
        content.addWidget(self.following)
        content.addStretch()
        self.parameters = label("", "muted", True)
        content.addWidget(self.parameters)
        self.play = button(tr('Play'), owner.start_playback, primary=True, symbol="play")
        content.addWidget(row(self.play, button(tr('Options'), lambda: owner.change_page(2)), None))
        grid.addWidget(player, 0, 1, 1, 2)

        shortcuts, content = card(tr('Recording controls'))
        shortcuts.setMinimumHeight(280)
        self.shortcuts = {}
        for key, name in (("record_start", tr('Start')), ("record_stop", tr('Stop')), ("record_pause", tr('Pause'))):
            value = label("", "keycap")
            self.shortcuts[key] = value
            content.addWidget(row(label(name, "muted"), None, value))
        content.addStretch()
        content.addWidget(label(tr('Control shortcuts are excluded from recordings.'), "muted", True))
        content.addWidget(button(tr('Configure controls'), lambda: owner.change_page(6), symbol="settings"))
        grid.addWidget(shortcuts, 1, 0)

        quick, content = card()
        content.addWidget(row(label(tr('Quick access'), "sectionTitle"), None,
                              button(tr('View all'), lambda: owner.change_page(5))))
        self.quick = QVBoxLayout()
        self.quick.setSpacing(12)
        content.addLayout(self.quick)
        content.addStretch()
        self.policy = label("", "muted", True)
        content.addWidget(self.policy)
        grid.addWidget(quick, 1, 1)

        clicker, content = card()
        self.click_state = label(tr('STOPPED'), "muted")
        content.addWidget(row(glyph("click"), label("Autoclicker", "sectionTitle"), None, self.click_state))
        self.click_kind = combo([(tr('Mouse'), "mouse"), (tr('Keyboard'), "keyboard")])
        self.click_target = label(tr('Left'), "muted")
        content.addWidget(row(self.click_kind, self.click_target))
        self.interval = spin(10, 90000000, 100, " ms")
        self.repetitions = spin(0, 10000000, 100)
        self.repetitions.setSpecialValueText(tr('Unlimited'))
        content.addWidget(row(label(tr('Interval'), "muted"), None, self.interval))
        content.addWidget(row(label(tr('Repeats'), "muted"), None, self.repetitions))
        content.addWidget(button(tr('Assign key / mouse button'), lambda: owner.change_page(3)))
        content.addStretch()
        self.click = button(tr('Start autoclicker'), owner.start_clicker, symbol="play")
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
        self.policy.setText(tr('If another macro is running: ') + (tr('queue it.') if self.owner.settings.data["concurrency"] == "queue" else tr('block the second macro.')))

    def update_library(self):
        while self.quick.count():
            self.quick.takeAt(0).widget().deleteLater()
        macros = sorted(self.owner.macros.values(), key=lambda m: m.modified, reverse=True)[:3]
        for macro in macros:
            trigger = label(display_binding(macro.trigger) or "—", "keycap")
            name = label(macro.name, wrap=True)
            play = button("", lambda checked=False, identifier=macro.id: self.play_macro(identifier), symbol="play")
            play.setFixedWidth(38)
            play.setToolTip(tr('Play ') + macro.name)
            play.setEnabled(not self.owner.engine.busy)
            self.quick.addWidget(row(trigger, name, None, play))
        if not macros:
            self.quick.addWidget(label(tr('Create your first macro with New.'), "muted", True))

    def play_macro(self, identifier):
        if self.owner.require_idle():
            self.owner.select_macro(identifier)
            self.owner.start_playback()

    def update_progress(self, data):
        self.index = min(data["index"], data["total"] - 1)
        self.progress.setValue(round(data["index"] / data["total"] * 100))
        self.progress_text.setText(tr('{0} / {1} actions', min(data['index'] + 1, data['total']), data['total']))
        self.elapsed.setText(duration_text(data["elapsed"])[3:])
        self.refresh_action()

    def refresh_action(self):
        o = self.owner
        macro = o.macros.get(o.engine.active_id) or o.current
        if not macro:
            return
        self.name.setText(macro.name)
        self.shortcut.setText(display_binding(macro.trigger) or tr('No shortcut'))
        self.parameters.setText(tr('Speed  {0:g}×    Repeats  {1}    Mode  ', macro.speed, macro.repetitions) + {"once": tr('Single press'), "hold": tr('Hold'), "toggle": tr('Toggle')}[macro.activation])
        index = self.index if o.engine.task == "play" else 0
        if macro.events and index < len(macro.events):
            self.action.setText(f"{index + 1:02}     {event_text(macro.events[index])}")
            self.following.setText(tr('NEXT     ') + event_text(macro.events[index + 1]) if index + 1 < len(macro.events) else tr('End of sequence'))
        else:
            self.action.setText(tr('Add or record actions to get started.'))
            self.following.setText("")

    def sync(self):
        o = self.owner
        busy, task, phase = o.engine.busy, o.engine.task, o.engine.phase
        self.record.setEnabled(not busy)
        self.record_stop.setEnabled(task == "record")
        self.record_state.setText(tr('RECORDING') if task == "record" else tr('IDLE'))
        self.play.setEnabled(not busy and o.current is not None and bool(o.current.events))
        self.play_state.setText(tr('PAUSED') if phase == "paused" else tr('PLAYING') if task == "play" else tr('PLAYER'))
        self.pause.setText(tr('Resume') if phase == "paused" else tr('Pause'))
        for widget in (self.previous, self.pause, self.next, self.restart):
            widget.setEnabled(task == "play" and phase in ("running", "paused"))
        self.stop.setEnabled(task == "play")
        self.click.setEnabled(not busy or task == "click")
        self.click.setText(tr('Stop autoclicker') if task == "click" else tr('Start autoclicker'))
        self.click_state.setText(tr('RUNNING') if task == "click" else tr('STOPPED'))
        for widget in (self.moves, self.mode, self.countdown, self.interval, self.repetitions, self.click_kind):
            widget.setEnabled(not busy)
        self.moves.setEnabled(not busy and self.mode.currentData() == "timed")
        self.click_target.setText(display_binding(o.repeat_key.text()) if o.click_kind.currentData() == "keyboard" else o.click_button.currentText())
        self.target.setText(tr('Will be saved to “{0}”.', o.current.name) if o.current else tr('A new macro will be created for this recording.'))
        self.refresh_action()
