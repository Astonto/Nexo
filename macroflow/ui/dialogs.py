from __future__ import annotations
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
        self.setWindowTitle("Asignar atajo")
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        layout.addWidget(label("Pulsa tu nuevo atajo", "sectionTitle"))
        help_text = 'Pulsa una tecla o combinación, o un botón del ratón: izquierdo, derecho, central, X1 o X2. Puedes hacer clic en esta ventana para asignarlo.\n\nEscape cancela. La parada de emergencia sigue activa.' if allow_all_mouse else 'Una letra, una tecla de función, una combinación o un botón lateral X1 / X2.\n\nEscape cancela. La parada de emergencia sigue activa.'
        layout.addWidget(label(help_text, 'muted', True))
        layout.addWidget(button("Cancelar", self.reject))
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
            QMessageBox.warning(self, "Atajo no disponible", str(exc))
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
        self.setWindowTitle("Configurar macro")
        self.setMinimumWidth(580)
        layout = QVBoxLayout(self)
        layout.addWidget(label("Configuración de la macro", "sectionTitle"))
        layout.addWidget(label("El atajo funciona globalmente mientras Nexo está abierto. Al editar dentro de Nexo, los activadores de macros se suspenden.", "muted", True))
        form = QFormLayout()
        form.setVerticalSpacing(13)
        self.name = QLineEdit(macro.name)
        self.category = CategoryField(categories, macro.category)
        self.name.setMaxLength(120)
        self.trigger = ShortcutField(macro.trigger)
        self.trigger.setPlaceholderText("Sin atajo · A, Ctrl+G, F6, X1…")
        self.mode = combo([("Una pulsación", "once"), ("Mantener presionado", "hold"), ("Alternar (Toggle)", "toggle")])
        self.mode.setCurrentIndex(self.mode.findData(macro.activation))
        self.repetitions = spin(1, 10_000_000, macro.repetitions)
        self.speed = spin(0.1, 10, macro.speed, "×", 2)
        self.interval = spin(0.01, 86400, macro.repeat_interval, " s", 3)
        for title, widget in (("Nombre", self.name), ("Categoría", self.category),
                              ("Activador", row(self.trigger, button("Asignar atajo", self.assign),
                                                button("Quitar", lambda: self.trigger.setText("")))),
                              ("Modo", self.mode), ("Repeticiones por pulsación", self.repetitions),
                              ("Velocidad", self.speed), ("Intervalo entre repeticiones", self.interval)):
            form.addRow(title, widget)
        layout.addLayout(form)
        layout.addWidget(label("Una pulsación respeta el número configurado. Mantener y Alternar repiten hasta soltar o volver a pulsar; ambos respetan el intervalo. La tecla activadora se consume solo cuando la macro está activada y fuera de Nexo.", "muted", True))
        layout.addWidget(row(None, button("Cancelar", self.reject), button("Guardar configuración", self.accept, primary=True)))
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
            QMessageBox.warning(self, "Revisa la configuración", str(exc))
            return
        super().accept()


class CreateMacroDialog(QDialog):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Nueva macro")
        self.setMinimumWidth(540)
        self.activation, self.destination = "once", "fixed"
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(18)
        self.step = label("01 / 02   DEFINE TU MACRO", "eyebrow")
        layout.addWidget(self.step)
        layout.addWidget(label("Nueva macro", "pageTitle"))
        self.steps = QStackedWidget()
        first = QWidget()
        form = QVBoxLayout(first)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(12)
        form.addWidget(label("Nombre", "muted"))
        self.name = QLineEdit()
        self.name.setPlaceholderText("Por ejemplo, Abrir mi espacio de trabajo")
        self.name.setMaxLength(120)
        form.addWidget(self.name)
        form.addSpacing(12)
        form.addWidget(label("Cómo se ejecuta", "muted"))
        self.modes = QButtonGroup(self)
        for title, detail, mode in (("Una pulsación", "Ejecuta la secuencia completa.", "once"),
                                    ("Mantener presionado", "Repite mientras mantienes el activador.", "hold"),
                                    ("Alternar", "Una pulsación inicia; la siguiente detiene.", "toggle")):
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
        actions.addWidget(label("¿Cómo quieres añadir las acciones?", "sectionTitle"))
        self.destinations = QButtonGroup(self)
        for title, detail, destination in (("Pulsaciones", "Teclas en bloques, con un intervalo fijo.", "fixed"),
                                           ("Teclado y ratón", "Graba la secuencia con sus tiempos reales.", "timed"),
                                           ("Construir en el editor", "Añade texto, pausas, clics y otras acciones.", "editor")):
            choice = button(title + "\n" + detail, lambda checked=False, value=destination: setattr(self, "destination", value))
            choice.setProperty("choice", True)
            choice.setCheckable(True)
            choice.setChecked(destination == "fixed")
            self.destinations.addButton(choice)
            actions.addWidget(choice)
        actions.addWidget(label("Después podrás revisar la secuencia y asignar su atajo desde el editor. La grabación comienza cuando pulses Iniciar.", "muted", True))
        actions.addStretch()
        self.steps.addWidget(first)
        self.steps.addWidget(second)
        layout.addWidget(self.steps)
        self.error = label("", "formError", True)
        layout.addWidget(self.error)
        self.back = button("Atrás", self.go_back)
        self.back.hide()
        self.next_button = button("Continuar", self.advance, primary=True)
        layout.addWidget(row(button("Cancelar", self.reject), self.back, None, self.next_button))
        self.name.returnPressed.connect(self.advance)

    def advance(self):
        if self.steps.currentIndex() == 0:
            if not self.name.text().strip() or any(ord(char) < 32 for char in self.name.text()):
                self.error.setText("Escribe un nombre para tu macro.")
                self.name.setFocus()
                return
            self.error.clear()
            self.steps.setCurrentIndex(1)
            self.step.setText("02 / 02   AÑADE LAS ACCIONES")
            self.next_button.setText("Crear macro")
            self.back.show()
        else:
            self.accept()

    def go_back(self):
        self.steps.setCurrentIndex(0)
        self.step.setText("01 / 02   DEFINE TU MACRO")
        self.next_button.setText("Continuar")
        self.back.hide()
