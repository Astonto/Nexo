from __future__ import annotations
from ..i18n import tr
import os

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QDialog, QFormLayout, QLineEdit, QMessageBox, QStackedWidget, QVBoxLayout, QWidget)

from ..models import Macro, ValidationError
from ..triggers import Binding, MOD_ORDER, display_binding, parse_binding
from ..windows import foreground_process
from .widgets import CategoryField, button, combo, label, row, spin


class ShortcutField(QLineEdit):

    def __init__(self, value=""):
        super().__init__()
        self.setReadOnly(True)
        self.setText(value)

    def setText(self, text):
        self.binding = text
        super().setText(display_binding(text) if text else "")

    def text(self):
        return self.binding


class AssignDialog(QDialog):
    captured = Signal(str)

    def __init__(self, router, parent, *, allow_all_mouse=False):
        super().__init__(parent)
        self.router = router
        self.value = None
        self.allow_all_mouse = allow_all_mouse
        self.setWindowTitle(tr('Assign shortcut'))
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        layout.addWidget(label(tr('Press your new shortcut'), "sectionTitle"))
        help_text = tr('Press a key, a combination, or a mouse button: left, right, middle, X1 or X2. You can click in this window to assign it.\n\nEscape cancels. Emergency stop remains active.') if allow_all_mouse else tr('A letter, a function key, a key combination, or a side mouse button X1 / X2.\n\nEscape cancels. Emergency stop remains active.')
        layout.addWidget(label(help_text, 'muted', True))
        layout.addWidget(button(tr('Cancel'), self.reject))
        self.captured.connect(self.assign)
        self.router.capture = self.captured.emit
        self.router.capture_all_mouse = allow_all_mouse
        self.router.capture_mouse_guard = lambda: foreground_process() != os.getpid()
        self.timeout_timer = QTimer(self)
        self.timeout_timer.setSingleShot(True)
        self.timeout_timer.timeout.connect(self.reject)
        self.timeout_timer.start(20000)

    def assign(self, value):
        if value.lower() == "esc":
            self.reject()
            return
        try:
            self.value = parse_binding(value).label
            self.accept()
        except ValidationError as exc:
            self.router.capture = None
            QMessageBox.warning(self, tr('Shortcut unavailable'), str(exc))
            self.router.capture = self.captured.emit

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        if event.key() in (Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Shift, Qt.Key.Key_Meta):
            return

        vk = event.nativeVirtualKey()
        mods = event.modifiers()
        if vk:
            names = [name for flag, name in ((Qt.KeyboardModifier.ControlModifier, "Ctrl"),
                      (Qt.KeyboardModifier.AltModifier, "Alt"), (Qt.KeyboardModifier.ShiftModifier, "Shift"),
                      (Qt.KeyboardModifier.MetaModifier, "Win")) if mods & flag]
            text = Binding(frozenset(names), vk).label
        else:
            text = QKeySequence(event.keyCombination()).toString(QKeySequence.SequenceFormat.PortableText)
        self.assign(text)

    def mousePressEvent(self, event):
        buttons = {Qt.MouseButton.LeftButton: 'mouseleft', Qt.MouseButton.RightButton: 'mouseright', Qt.MouseButton.MiddleButton: 'mbutton', Qt.MouseButton.BackButton: 'x1', Qt.MouseButton.ForwardButton: 'x2'}
        if self.allow_all_mouse and event.button() in buttons:
            names = frozenset(name for flag, name in ((Qt.KeyboardModifier.ControlModifier, 'Ctrl'), (Qt.KeyboardModifier.AltModifier, 'Alt'), (Qt.KeyboardModifier.ShiftModifier, 'Shift'), (Qt.KeyboardModifier.MetaModifier, 'Win')) if event.modifiers() & flag)
            self.assign(Binding(names, buttons[event.button()]).label)
            event.accept()
            return
        super().mousePressEvent(event)

    def done(self, result):
        self.timeout_timer.stop()
        self.router.capture = None
        self.router.capture_all_mouse = False
        self.router.capture_mouse_guard = None
        super().done(result)


class MacroDialog(QDialog):
    def __init__(self, macro, router, validator, parent=None, *, categories=()):
        super().__init__(parent)
        self.macro, self.router, self.validator = macro, router, validator
        self.assigned = False
        self.result_macro = None
        self.setWindowTitle(tr('Configure macro'))
        self.setMinimumWidth(580)
        layout = QVBoxLayout(self)
        layout.addWidget(label(tr('Macro settings'), "sectionTitle"))
        layout.addWidget(label(tr('The shortcut works globally while Nexo is open. Macro triggers are suspended while you edit in Nexo.'), "muted", True))
        form = QFormLayout()
        form.setVerticalSpacing(13)
        self.name = QLineEdit(macro.name)
        self.category = CategoryField(categories, macro.category)
        self.name.setMaxLength(120)
        self.trigger = ShortcutField(macro.trigger)
        self.trigger.setPlaceholderText(tr('No shortcut · A, Ctrl+G, F6, X1…'))
        self.mode = combo([(tr('Single press'), "once"), (tr('Hold down'), "hold"), (tr('Toggle (on/off)'), "toggle")])
        self.mode.setCurrentIndex(self.mode.findData(macro.activation))
        self.repetitions = spin(1, 10_000_000, macro.repetitions)
        self.speed = spin(0.1, 10, macro.speed, "×", 2)
        self.interval = spin(0.01, 86400, macro.repeat_interval, " s", 3)
        for title, widget in ((tr('Name'), self.name), (tr('Category'), self.category),
                              (tr('Trigger'), row(self.trigger, button(tr('Assign shortcut'), self.assign),
                                                button(tr('Remove'), lambda: self.trigger.setText("")))),
                              (tr('Mode'), self.mode), (tr('Repeats per press'), self.repetitions),
                              (tr('Speed'), self.speed), (tr('Interval between repeats'), self.interval)):
            form.addRow(title, widget)
        layout.addLayout(form)
        layout.addWidget(label(tr('Single press uses the repeat count. Hold and Toggle repeat until you release or press again; both use the interval. The trigger key is consumed only when the macro is enabled and you are outside Nexo.'), "muted", True))
        layout.addWidget(row(None, button(tr('Cancel'), self.reject), button(tr('Save settings'), self.accept, primary=True)))
        self.mode.currentIndexChanged.connect(lambda: self.repetitions.setEnabled(self.mode.currentData() == "once"))
        self.repetitions.setEnabled(macro.activation == "once")

    def assign(self):
        dialog = AssignDialog(self.router, self)
        if dialog.exec() and dialog.value:
            self.trigger.setText(dialog.value)
            self.assigned = True

    def accept(self):
        try:
            macro = Macro.from_dict(self.macro.to_dict())
            macro.name, macro.category = self.name.text().strip(), self.category.text().strip()
            macro.trigger = parse_binding(self.trigger.text()).label if self.trigger.text().strip() else ""
            macro.activation = self.mode.currentData()
            macro.enabled = bool(macro.trigger) if self.assigned or macro.trigger != self.macro.trigger else self.macro.enabled
            macro.repetitions, macro.speed = self.repetitions.value(), self.speed.value()
            macro.repeat_interval = self.interval.value()
            macro.validate()
            self.validator(macro)
            self.result_macro = macro
        except ValidationError as exc:
            QMessageBox.warning(self, tr('Check the settings'), str(exc))
            return
        super().accept()


class CreateMacroDialog(QDialog):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr('New macro'))
        self.setMinimumWidth(540)
        self.activation, self.destination = "once", "fixed"
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(18)
        self.step = label(tr('01 / 02   DEFINE YOUR MACRO'), "eyebrow")
        layout.addWidget(self.step)
        layout.addWidget(label(tr('New macro'), "pageTitle"))
        self.steps = QStackedWidget()
        first = QWidget()
        form = QVBoxLayout(first)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(12)
        form.addWidget(label(tr('Name'), "muted"))
        self.name = QLineEdit()
        self.name.setPlaceholderText(tr('For example, Open my workspace'))
        self.name.setMaxLength(120)
        form.addWidget(self.name)
        form.addSpacing(12)
        form.addWidget(label(tr('How it runs'), "muted"))
        self.modes = QButtonGroup(self)
        for title, detail, mode in ((tr('Single press'), tr('Runs the full sequence.'), "once"),
                                    (tr('Hold down'), tr('Repeats while you hold the trigger.'), "hold"),
                                    (tr('Toggle'), tr('Press once to start; press again to stop.'), "toggle")):
            choice = button(title + "\n" + detail, lambda checked=False, value=mode: setattr(self, "activation", value))
            choice.setProperty("choice", True)
            choice.setCheckable(True)
            choice.setChecked(mode == "once")
            self.modes.addButton(choice)
            form.addWidget(choice)
        form.addStretch()
        second = QWidget()
        actions = QVBoxLayout(second)
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(14)
        actions.addWidget(label(tr('How would you like to add actions?'), "sectionTitle"))
        self.destinations = QButtonGroup(self)
        for title, detail, destination in ((tr('Keystrokes'), tr('Keys in blocks, with a fixed interval.'), "fixed"),
                                           (tr('Keyboard and mouse'), tr('Record the sequence with its original timing.'), "timed"),
                                           (tr('Build in editor'), tr('Add text, delays, clicks and other actions.'), "editor")):
            choice = button(title + "\n" + detail, lambda checked=False, value=destination: setattr(self, "destination", value))
            choice.setProperty("choice", True)
            choice.setCheckable(True)
            choice.setChecked(destination == "fixed")
            self.destinations.addButton(choice)
            actions.addWidget(choice)
        actions.addWidget(label(tr('You can review the sequence and assign its shortcut in the editor afterward. Recording begins when you press Start.'), "muted", True))
        actions.addStretch()
        self.steps.addWidget(first)
        self.steps.addWidget(second)
        layout.addWidget(self.steps)
        self.error = label("", "formError", True)
        layout.addWidget(self.error)
        self.back = button(tr('Back'), self.go_back)
        self.back.hide()
        self.next_button = button(tr('Continue'), self.advance, primary=True)
        layout.addWidget(row(button(tr('Cancel'), self.reject), self.back, None, self.next_button))
        self.name.returnPressed.connect(self.advance)

    def advance(self):
        if self.steps.currentIndex() == 0:
            if not self.name.text().strip() or any(ord(char) < 32 for char in self.name.text()):
                self.error.setText(tr('Enter a name for your macro.'))
                self.name.setFocus()
                return
            self.error.clear()
            self.steps.setCurrentIndex(1)
            self.step.setText(tr('02 / 02   ADD ACTIONS'))
            self.next_button.setText(tr('Create macro'))
            self.back.show()
        else:
            self.accept()

    def go_back(self):
        self.steps.setCurrentIndex(0)
        self.step.setText(tr('01 / 02   DEFINE YOUR MACRO'))
        self.next_button.setText(tr('Continue'))
        self.back.hide()
