from ..i18n import tr
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QWidget

from .widgets import button, label


class Home(QWidget):
    MESSAGES = (
        tr("Nice day, isn't it?"),
        tr('Does anyone read this?'),
        tr('Coffee or tea?'),
        tr('Not sure what to put here.'),
        tr('This message serves no purpose.'),
        tr('Have you eaten yet?'),
        tr('Hello, person reading this.'),
        tr('Why are you still looking here?'),
        tr('There are 86,400 seconds in a day.'),
        tr('Octopuses have three hearts.'),
        tr('Sunlight takes about 8 minutes to reach Earth.'),
        tr('A day on Venus lasts longer than its year.'),
        tr('Sharks are older than trees.'),
        tr('Chess has more possible games than you could count.'),
        tr("Cats can't taste sweetness."),
        tr('Did you know you can ignore this message?'),
        tr("Don't press Alt + F4. Or do."),
        tr('You should probably be sleeping.'),
        tr('What if we did nothing today?'),
        tr('This message was picked at random.'),
        tr('Nexo needs a break too. Well, no.'),
        tr('How many times have you read this?'),
        tr('The QWERTY keyboard dates back to the 19th century.'),
        tr('Flamingos are born with gray feathers.'),
        tr('Which came first, the click or the macro?'),
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
        layout.addWidget(label(tr('Welcome to Nexo'), "welcomeTitle"))
        layout.addSpacing(18)
        self.message = label("", "welcomeSubtitle", True)
        self.message.setMinimumHeight(26)
        layout.addWidget(self.message)
        layout.addSpacing(44)
        actions = QHBoxLayout()
        actions.setSpacing(15)
        self.create = button(tr('New macro'), owner.new_macro, symbol="plus", primary=True)
        self.record = button(tr('Record'), lambda: owner.change_page(1), symbol="play")
        self.create.setFixedSize(226, 54)
        self.record.setFixedSize(184, 54)
        actions.addWidget(self.create)
        actions.addWidget(self.record)
        actions.addStretch()
        layout.addLayout(actions)
        layout.addSpacing(76)
        layout.addWidget(label(tr('YOUR SPACE'), "eyebrow"))
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
        self.state = label(tr('Ready'), "homeState")
        self.state_detail = label(tr('System ready'), "welcomeSubtitle", True)
        for index, (value, caption) in enumerate(((self.macros, "Macros"), (self.categories, tr('Categories')), (self.state, None))):
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
        state = {"record": tr('Recording'), "play": tr('Playing'), "click": tr('Repeating')}.get(engine.task, tr('Ready') if ready else tr('Review'))
        if engine.phase == "paused":
            state = tr('Paused')
        elif engine.phase == "countdown":
            state = tr('Getting ready')
        elif engine.phase == "stopping":
            state = tr('Stopping')
        self.state.setText(state)
        self.state_detail.setText(tr('Task running') if engine.busy else tr('System ready') if ready else tr('Check your shortcuts in Settings'))
        self.create.setEnabled(not engine.busy)
