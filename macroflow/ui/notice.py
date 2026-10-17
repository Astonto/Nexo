from PySide6.QtCore import Qt, QTimer, QEvent
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QHBoxLayout


class Notice(QFrame):

    def __init__(self, parent):
        super().__init__(parent)
        self.priority = -1
        self.setObjectName('noticeOverlay')
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 8, 10)
        self.message = QLabel()
        self.message.setWordWrap(True)
        self.message.setTextFormat(Qt.TextFormat.PlainText)
        self.message.setAccessibleName('Aviso de Nexo')
        layout.addWidget(self.message, 1)
        self.dismiss = QPushButton('×')
        self.dismiss.setAccessibleName('Cerrar aviso')
        self.dismiss.setFixedSize(28, 28)
        self.dismiss.setCursor(Qt.CursorShape.PointingHandCursor)
        self.dismiss.setObjectName('noticeDismiss')
        self.dismiss.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.dismiss.clicked.connect(self.hide)
        layout.addWidget(self.dismiss)
        self.timeout = QTimer(self)
        self.timeout.setSingleShot(True)
        self.timeout.timeout.connect(self.hide)
        parent.installEventFilter(self)
        self.hide()

    def show_message(self, text, warning=False):
        priority = int(warning)
        if self.isVisible() and priority < self.priority:
            return
        self.priority = priority
        self.message.setText(text)
        self.timeout.stop()
        self.position()
        self.show()
        self.raise_()
        if not warning:
            self.timeout.start(7000)

    def attach(self, surface):
        if self.parentWidget() is surface:
            return
        visible = self.isVisible()
        self.parentWidget().removeEventFilter(self)
        self.setParent(surface)
        surface.installEventFilter(self)
        self.position()
        if visible:
            self.show()
            self.raise_()

    def position(self):
        self.setFixedWidth(min(430, max(200, self.parentWidget().width() - 32)))
        self.layout().activate()
        self.setFixedHeight(max(52, self.layout().heightForWidth(self.width()), self.layout().sizeHint().height()))
        self.move(self.parentWidget().width() - self.width() - 16,
                  self.parentWidget().height() - self.height() - 16)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Resize:
            self.position()
        return False
