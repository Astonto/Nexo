from .i18n import tr

import getpass
import os
import hashlib
import time
from pathlib import Path
from PySide6.QtCore import QDir, QLockFile, QObject, QTimer, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket


def instance_name(smoke_directory=None):
    scope = 'user:' + getpass.getuser()
    if smoke_directory is not None:
        scope += ':smoke:' + str(Path(smoke_directory).resolve())
    return 'Nexo-v2-' + hashlib.sha256(scope.encode()).hexdigest()[:24]


class SingleInstance(QObject):
    activated = Signal()

    def __init__(self, name, parent=None):
        super().__init__(parent)
        self.requested = False
        self.name = name
        self.lock = QLockFile(str(Path(QDir.tempPath()) / (name + '.lock')))
        self.lock.setStaleLockTime(0)
        self.server = QLocalServer(self)
        self.server.newConnection.connect(self.drain)

    def acquire(self, timeout_ms=10000):
        deadline = time.monotonic() + timeout_ms / 1000
        while True:
            if self.lock.tryLock(0):

                QLocalServer.removeServer(self.name)
                if not self.server.listen(self.name):
                    self.lock.unlock()
                    raise RuntimeError(tr('Could not create the single-instance control.'))
                return True
            if os.name == 'nt':

                import ctypes
                pid, host, application = self.lock.getLockInfo()
                if pid > 0:
                    ctypes.windll.user32.AllowSetForegroundWindow(pid)
            socket = QLocalSocket()
            socket.connectToServer(self.name)
            if socket.waitForConnected(150):
                socket.disconnectFromServer()
                return False
            if time.monotonic() >= deadline:
                raise RuntimeError(tr('Nexo is still starting. Open it again in a few seconds.'))
            time.sleep(.05)

    def drain(self):
        while self.server.hasPendingConnections():
            connection = self.server.nextPendingConnection()
            connection.disconnectFromServer()
            connection.deleteLater()
            self.requested = True
            self.activated.emit()

    def attach(self, callback):
        self.activated.connect(callback)
        QTimer.singleShot(0, self.drain)
        if self.requested:
            QTimer.singleShot(0, callback)

    def close(self):
        self.server.close()
        self.lock.unlock()


def create_installation_guard():
    if os.name != 'nt':
        return None
    import ctypes
    create = ctypes.windll.kernel32.CreateMutexW
    create.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    create.restype = ctypes.c_void_p
    return create(None, False, 'Nexo.SetupGuard')
