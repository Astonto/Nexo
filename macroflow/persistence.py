
from __future__ import annotations

import copy
import threading


class SaveService:
    def __init__(self, library, notify):
        self.library, self.notify = library, notify
        self.condition = threading.Condition()
        self.pending = {}
        self.writing = False
        self.inflight = None
        self.stopping = False
        self.failed = set()
        self.failed_snapshots = {}
        self.thread = threading.Thread(target=self._run, name="Nexo-save", daemon=True)
        self.thread.start()

    def submit(self, macro):
        snapshot = copy.copy(macro)
        snapshot.events = list(macro.events)
        with self.condition:
            self.pending[macro.id] = snapshot
            self.condition.notify_all()

    def _run(self):
        while True:
            with self.condition:
                self.condition.wait_for(lambda: self.pending or self.stopping)
                if self.stopping and not self.pending:
                    return
                identifier = next(iter(self.pending))
                macro = self.pending.pop(identifier)
                self.writing = True
                self.inflight = identifier
            try:
                self.library.save(macro)
                with self.condition:
                    self.failed.discard(macro.id)
                    self.failed_snapshots.pop(macro.id, None)
                self.notify("saved", {"id": macro.id})
            except Exception:
                with self.condition:
                    self.failed.add(macro.id)
                    self.failed_snapshots[macro.id] = macro
                self.notify("warning", {"message": "No se pudo guardar una macro. Revisa el espacio y los permisos de la carpeta; exporta una copia antes de cerrar."})
            finally:
                with self.condition:
                    self.writing = False
                    self.inflight = None
                    self.condition.notify_all()

    def retry_failed(self):
        with self.condition:
            for identifier, snapshot in self.failed_snapshots.items():
                if identifier != self.inflight:
                    self.pending.setdefault(identifier, snapshot)
            self.condition.notify_all()

    def flush(self, timeout=10):
        with self.condition:
            return self.condition.wait_for(lambda: not self.pending and not self.writing, timeout) and not self.failed

    def close(self):
        flushed = self.flush()
        with self.condition:
            self.stopping = True
            self.condition.notify_all()
        self.thread.join(3)
        return flushed
