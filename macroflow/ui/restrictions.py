import copy

from PySide6.QtWidgets import QHeaderView, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from ..triggers import key_label, parse_binding
from .dialogs import AssignDialog
from .theme import icon
from .widgets import button, combo, label, row


class RecordingRestrictions(QWidget):
    def __init__(self, parent):
        super().__init__()
        self.owner = parent
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(label("Una exclusión activada impide grabar esa tecla. No afecta a los activadores de macros.", "muted", True))
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Tecla", "Exclusión", "", ""])
        parent.style_table(self.table)
        self.table.setMinimumHeight(280)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(2, 116)
        self.table.setColumnWidth(3, 48)
        layout.addWidget(self.table)
        self.preset = combo([(key_label(key), key) for key in (27, 46, 44, 45, 20, 17, 16, 18)])
        layout.addWidget(row(button("Añadir tecla…", self.assign), self.preset,
                             button("Añadir seleccionada", lambda: self.add(self.preset.currentData())), None))
        layout.addWidget(label("Ctrl, Shift y Alt se añaden desde la lista; incluyen ambos lados del teclado. Excluir Shift puede cambiar los símbolos reproducidos.", "muted", True))
        self.entries = []

    def load(self, entries):
        self.entries = copy.deepcopy(entries)
        self.refresh()

    def refresh(self):
        self.table.setRowCount(len(self.entries))
        for i, entry in enumerate(self.entries):
            self.table.setItem(i, 0, QTableWidgetItem(key_label(entry["key"])))
            self.table.setItem(i, 1, QTableWidgetItem("Activada" if entry["enabled"] else "Desactivada"))
            toggle = button("Desactivar" if entry["enabled"] else "Activar", lambda checked=False, k=entry["key"]: self.toggle(k))
            trash = button("", lambda checked=False, k=entry["key"]: self.remove(k), symbol='trash', danger=True)
            trash.setToolTip("Eliminar exclusión: permitir grabar esta tecla")
            trash.setAccessibleName("Eliminar exclusión de " + key_label(entry["key"]))
            self.table.setCellWidget(i, 2, toggle)
            self.table.setCellWidget(i, 3, trash)

    def toggle(self, key):
        for entry in self.entries:
            if entry["key"] == key:
                entry["enabled"] = not entry["enabled"]
        self.refresh()

    def remove(self, key):
        self.entries = [entry for entry in self.entries if entry["key"] != key]
        self.refresh()

    def add(self, key):
        if isinstance(key, int) and not any(entry["key"] == key for entry in self.entries):
            self.entries.append({"key": key, "enabled": True})
            self.refresh()

    def assign(self):
        if not self.owner.require_idle():
            return
        dialog = AssignDialog(self.owner.router, self.owner)
        if dialog.exec() and dialog.value:
            self.add(parse_binding(dialog.value).key)
