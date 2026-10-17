from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QWidget

from .widgets import button, label


class Home(QWidget):
    MESSAGES = (
        "Hoy es un buen día, ¿no?",
        "¿Alguien lee esto?",
        "¿Prefieres café o té?",
        "No sé qué poner aquí.",
        "Esta frase no tiene ninguna utilidad.",
        "¿Ya comiste?",
        "Hola, persona que está leyendo esto.",
        "¿Por qué sigues mirando aquí?",
        "Hay 86 400 segundos en un día.",
        "Los pulpos tienen tres corazones.",
        "La luz del Sol tarda unos 8 minutos en llegar a la Tierra.",
        "Un día en Venus dura más que su año.",
        "Los tiburones son más antiguos que los árboles.",
        "El ajedrez tiene más partidas posibles de las que podrías contar.",
        "Los gatos no pueden saborear lo dulce.",
        "¿Sabías que puedes ignorar este mensaje?",
        "No pulses Alt + F4. O sí.",
        "Probablemente deberías estar durmiendo.",
        "¿Y si hoy no hacemos nada?",
        "Esta frase fue elegida al azar.",
        "Nexo también necesita descansar. Bueno, no.",
        "¿Cuántas veces has leído esto?",
        "El teclado QWERTY existe desde el siglo XIX.",
        "Los flamencos nacen con plumaje grisáceo.",
        "¿Qué fue primero, el clic o la macro?",
    )

    def __init__(self, owner):
        super().__init__()
        self.owner = owner
        self.message_index = 0
        self.typed_characters = 0
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addSpacing(48)
        layout.addWidget(label("Bienvenido a Nexo", "welcomeTitle"))
        layout.addSpacing(18)
        self.message = label("", "welcomeSubtitle", True)
        self.message.setMinimumHeight(26)
        layout.addWidget(self.message)
        layout.addSpacing(44)
        actions = QHBoxLayout()
        actions.setSpacing(15)
        self.create = button("Nueva macro", owner.new_macro, symbol="plus", primary=True)
        self.record = button("Grabar", lambda: owner.change_page(1), symbol="play")
        self.create.setFixedSize(226, 54)
        self.record.setFixedSize(184, 54)
        actions.addWidget(self.create)
        actions.addWidget(self.record)
        actions.addStretch()
        layout.addLayout(actions)
        layout.addSpacing(76)
        layout.addWidget(label("TU ESPACIO", "eyebrow"))
        layout.addSpacing(16)
        line = QFrame()
        line.setObjectName("divider")
        line.setFixedHeight(1)
        layout.addWidget(line)
        layout.addSpacing(24)
        metrics = QHBoxLayout()
        metrics.setSpacing(36)
        self.macros = label("00", "homeMetric")
        self.categories = label("00", "homeMetric")
        self.state = label("Listo", "homeState")
        self.state_detail = label("Sistema preparado", "welcomeSubtitle", True)
        for index, (value, caption) in enumerate(((self.macros, "Macros"), (self.categories, "Categorías"), (self.state, None))):
            group = QVBoxLayout()
            group.setSpacing(8)
            group.addWidget(value)
            group.addWidget(self.state_detail if caption is None else label(caption, "welcomeSubtitle"))
            group.addStretch()
            metrics.addLayout(group, 1)
            if index < 2:
                separator = QFrame()
                separator.setObjectName("divider")
                separator.setFixedSize(1, 100)
                metrics.addWidget(separator)
        layout.addLayout(metrics)
        layout.addStretch(1)
        layout.addSpacing(36)

        self.typing_timer = QTimer(self)
        self.typing_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.typing_timer.setInterval(35)
        self.typing_timer.timeout.connect(self.type_next_character)
        self.message_timer = QTimer(self)
        self.message_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.message_timer.setInterval(7000)
        self.message_timer.timeout.connect(self.advance_message)

    def advance_message(self):
        if self.isVisible() and not self.owner.engine.busy:
            self.message_index = (self.message_index + 1) % len(self.MESSAGES)
            self.typed_characters = 0
            self.message.clear()
            self.typing_timer.start()
            self.message_timer.start()

    def type_next_character(self):
        if not self.isVisible() or self.owner.engine.busy:
            self.typing_timer.stop()
            return
        target = self.MESSAGES[self.message_index]
        self.typed_characters = min(self.typed_characters + 1, len(target))
        self.message.setText(target[:self.typed_characters])
        if self.typed_characters == len(target):
            self.typing_timer.stop()

    def resume_messages(self):
        if not self.isVisible() or self.owner.engine.busy:
            self.message_timer.stop()
            self.typing_timer.stop()
            return
        if not self.message_timer.isActive():
            self.message_timer.start()
        if self.typed_characters < len(self.MESSAGES[self.message_index]) and not self.typing_timer.isActive():
            self.typing_timer.start()

    def showEvent(self, event):
        super().showEvent(event)
        self.resume_messages()

    def hideEvent(self, event):
        self.message_timer.stop()
        self.typing_timer.stop()
        super().hideEvent(event)

    def refresh(self):
        self.resume_messages()
        self.macros.setText(f"{len(self.owner.macros):02d}")
        self.categories.setText(f"{len({m.category for m in self.owner.macros.values()}):02d}")
        engine = self.owner.engine
        ready = self.owner.hotkeys_ok and self.owner.router_ok
        state = {"record": "Grabando", "play": "Reproduciendo", "click": "Repitiendo"}.get(engine.task, "Listo" if ready else "Revisar")
        if engine.phase == "paused":
            state = "En pausa"
        elif engine.phase == "countdown":
            state = "Preparando"
        elif engine.phase == "stopping":
            state = "Deteniendo"
        self.state.setText(state)
        self.state_detail.setText("Tarea en curso" if engine.busy else "Sistema preparado" if ready else "Revisa los atajos en Configuración")
        self.create.setEnabled(not engine.busy)
