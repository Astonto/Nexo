from __future__ import annotations

import json
from dataclasses import replace

from PySide6.QtCore import QAbstractTableModel, QByteArray, QMimeData, QModelIndex, Qt, Signal
from PySide6.QtGui import QDrag, QKeySequence, QShortcut, QUndoCommand, QUndoStack
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QDialog, QDialogButtonBox,
                               QFormLayout, QHBoxLayout, QHeaderView, QInputDialog, QLineEdit, QMessageBox,
                               QPlainTextEdit, QTableView, QVBoxLayout, QWidget, QListView, QMenu, QStackedWidget)

from ..models import Event, KINDS, LABELS, MAX_EVENTS, ValidationError, normalize_key
from .sequence import ActionDelegate, describe_event
from .widgets import button, combo, label, row, spin


class ReplaceEvents(QUndoCommand):
    def __init__(self, model, events, description):
        super().__init__(description)
        self.model, self.before, self.after = model, list(model.events), list(events)

    def apply(self, events):
        self.model.beginResetModel()
        self.model.events = list(events)
        self.model.endResetModel()
        self.model.changed.emit()

    def redo(self):
        self.apply(self.after)

    def undo(self):
        self.apply(self.before)


class EventModel(QAbstractTableModel):
    changed = Signal()
    HEADERS = ("N.º", "Evento", "Tecla o botón", "X", "Y", "Tiempo (s)")

    def __init__(self):
        super().__init__()
        self.events = []
        self.history = QUndoStack(self)
        self.history.setUndoLimit(40)
        self.editable = True

    def load(self, events):
        self.beginResetModel()
        self.events = list(events)
        self.endResetModel()
        self.history.clear()

    def update(self, events, description):
        if not self.editable:
            return
        if len(events) > MAX_EVENTS:
            raise ValidationError("Se supera el límite de 100 000 eventos.")
        for event in events:
            event.validate()
        self.history.push(ReplaceEvents(self, events, description))

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.events)

    def columnCount(self, parent=QModelIndex()):
        return 6

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.HEADERS[section]

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self.events):
            return None
        event = self.events[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            value = event.key or event.button or (f"H {event.dx} · V {event.dy}" if event.kind == "scroll" else "—")
            return (str(index.row() + 1), LABELS[event.kind], value, str(event.x) if event.x is not None else "—",
                    str(event.y) if event.y is not None else "—", f"{event.delay:.4f}")[index.column()]
        if role == Qt.ItemDataRole.TextAlignmentRole and index.column() in (0, 3, 4, 5):
            return int(Qt.AlignmentFlag.AlignCenter)
        if role == Qt.ItemDataRole.ToolTipRole:
            return describe_event(event) + f" · Espera previa: {event.delay:g} s. Doble clic para editar."

    def flags(self, index):
        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        return flags | Qt.ItemFlag.ItemIsDragEnabled | Qt.ItemFlag.ItemIsDropEnabled if self.editable else flags

    def reorder(self, rows, target):
        if not self.editable:
            return
        rows = sorted(set(rows))
        moving = [self.events[r] for r in rows]
        remaining = [e for i, e in enumerate(self.events) if i not in set(rows)]
        target -= sum(r < target for r in rows)
        self.update(remaining[:target] + moving + remaining[target:], "Reordenar eventos")


class EventTable(QTableView):
    def __init__(self, model):
        super().__init__()
        self.setModel(model)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setAlternatingRowColors(True)
        self.setShowGrid(False)
        self.verticalHeader().hide()
        self.verticalHeader().setDefaultSectionSize(40)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)

    def selected_rows(self):
        return sorted(index.row() for index in self.selectionModel().selectedRows())

    def startDrag(self, actions):
        if not self.model().editable:
            return
        mime = QMimeData()
        mime.setData("application/x-macroflow-rows", QByteArray(json.dumps(self.selected_rows()).encode()))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.MoveAction)

    def dragEnterEvent(self, event):
        if event.source() is self and event.mimeData().hasFormat("application/x-macroflow-rows"):
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.source() is self:
            event.acceptProposedAction()

    def dropEvent(self, event):
        if event.source() is not self:
            return
        index = self.indexAt(event.position().toPoint())
        target = index.row() if index.isValid() else self.model().rowCount()
        self.model().reorder(json.loads(bytes(event.mimeData().data("application/x-macroflow-rows"))), target)
        event.acceptProposedAction()


class EventDialog(QDialog):
    def __init__(self, event=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Editar acción" if event else "Añadir acción")
        self.setMinimumWidth(430)
        event = event or Event("wait", delay=0.5)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.kind = combo([(LABELS[k], k) for k in KINDS])
        self.kind.setCurrentIndex(KINDS.index(event.kind))
        self.key = QLineEdit(event.key or "char:a")
        self.key.setPlaceholderText("a, key:enter, key:ctrl_l o vk:65")
        self.button = combo([(n, v) for n, v in (("Izquierdo", "left"), ("Derecho", "right"), ("Central", "middle"), ("Lateral X1", "x1"), ("Lateral X2", "x2"))])
        self.button.setCurrentIndex(max(0, self.button.findData(event.button)))
        self.x, self.y = spin(-1_000_000, 1_000_000, event.x or 0), spin(-1_000_000, 1_000_000, event.y or 0)
        self.dx, self.dy = spin(-1000, 1000, event.dx), spin(-1000, 1000, event.dy)
        self.delay = spin(0, 86400, event.delay, " s", 4)
        for title, widget in (("Acción", self.kind), ("Tecla", self.key), ("Botón", self.button), ("Coordenadas X / Y", row(self.x, self.y)),
                              ("Rueda horizontal / vertical", row(self.dx, self.dy)), ("Espera previa", self.delay)):
            form.addRow(title, widget)
        layout.addLayout(form)
        layout.addWidget(label("Las coordenadas usan píxeles físicos del escritorio. Una pulsación y su liberación son dos eventos.", "muted", True))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Guardar acción")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.kind.currentIndexChanged.connect(self.refresh)
        self.refresh()
        self.result_event = None

    def refresh(self):
        kind = self.kind.currentData()
        self.key.setEnabled(kind.startswith("key_"))
        self.button.setEnabled(kind.startswith("mouse_"))
        for widget in (self.x, self.y):
            widget.setEnabled(kind in ("mouse_down", "mouse_up", "move", "scroll"))
        for widget in (self.dx, self.dy):
            widget.setEnabled(kind == "scroll")

    def accept(self):
        try:
            kind = self.kind.currentData()
            pointer = kind in ("mouse_down", "mouse_up", "move", "scroll")
            self.result_event = Event(kind, self.delay.value(), normalize_key(self.key.text()) if kind.startswith("key_") else None,
                                      self.button.currentData() if kind.startswith("mouse_") else None,
                                      self.x.value() if pointer else None, self.y.value() if pointer else None,
                                      self.dx.value() if kind == "scroll" else 0, self.dy.value() if kind == "scroll" else 0).validate()
        except ValidationError as exc:
            QMessageBox.warning(self, "Revisa la acción", str(exc))
            return
        super().accept()


class Editor(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.model = EventModel()
        self.table = EventTable(self.model)
        add = button("Añadir acción", symbol="plus")
        additions = QMenu(add)
        for text, callback in (("Acción individual", self.add), ("Pausa", self.add_wait),
                               ("Combinación de teclas", self.add_chord), ("Texto", self.add_text),
                               ("Clic, doble clic o arrastre", self.add_pointer)):
            additions.addAction(text, callback)
        add.setMenu(additions)
        undo, redo = button("Deshacer", self.model.history.undo), button("Rehacer", self.model.history.redo)
        self.model.history.canUndoChanged.connect(undo.setEnabled)
        self.model.history.canRedoChanged.connect(redo.setEnabled)
        undo.setEnabled(False)
        redo.setEnabled(False)
        self.controls = row(add, None, undo, redo)
        layout.addWidget(self.controls)
        more = button("Más")
        operations = QMenu(more)
        for text, callback in (("Duplicar selección", self.duplicate), ("Copiar", self.copy), ("Pegar", self.paste),
                               ("Mover antes", lambda: self.move(-1)), ("Mover después", lambda: self.move(1))):
            operations.addAction(text, callback)
        more.setMenu(operations)
        self.operations = row(button("Editar acción", self.edit_selected), button("Eliminar", self.delete), more, None)
        self.view_mode = combo([("Bloques", 0), ("Detalle", 1)])
        self.operations.layout().addWidget(self.view_mode)
        layout.addWidget(self.operations)
        self.visual = QListView()
        self.visual.setObjectName("sequenceView")
        self.visual.setModel(self.model)
        self.visual.setModelColumn(0)
        self.visual.setViewMode(QListView.ViewMode.IconMode)
        self.visual.setResizeMode(QListView.ResizeMode.Adjust)
        self.visual.setMovement(QListView.Movement.Static)
        self.visual.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.visual.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.visual.setSelectionModel(self.table.selectionModel())
        self.visual.setWrapping(True)
        self.visual.setUniformItemSizes(True)
        self.visual.setItemDelegate(ActionDelegate(self.visual))
        self.visual.doubleClicked.connect(lambda index: self.edit(index.row()))
        self.views = QStackedWidget()
        self.views.addWidget(self.visual)
        self.views.addWidget(self.table)
        self.view_mode.currentIndexChanged.connect(self.views.setCurrentIndex)
        layout.addWidget(self.views, 1)
        self.empty = label("Tu secuencia empieza aquí.\nAñade una acción o graba desde la pestaña Grabar.", "emptyState", True)
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.empty)
        self.summary = label("0 eventos · 0.000 s", "muted")
        layout.addWidget(self.summary)
        self.model.changed.connect(self.refresh_summary)
        self.model.modelReset.connect(self.refresh_summary)
        self.refresh_summary()
        self.table.doubleClicked.connect(lambda index: self.edit(index.row()))
        self.shortcuts = []
        for sequence, callback in (("Ctrl+C", self.copy), ("Ctrl+V", self.paste), ("Ctrl+Z", self.model.history.undo),
                                   ("Ctrl+Y", self.model.history.redo), ("Delete", self.delete)):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(callback)
            self.shortcuts.append(shortcut)

    def set_editable(self, editable):
        self.model.editable = editable
        self.controls.setEnabled(editable)
        self.operations.setEnabled(editable)
        for shortcut in self.shortcuts:
            shortcut.setEnabled(editable)

    def refresh_summary(self):
        self.summary.setText(f"{len(self.model.events):,} acciones · {sum(e.delay for e in self.model.events):g} s · ↓ Pulsar  ↑ Soltar")
        self.empty.setVisible(not self.model.events)
        self.views.setVisible(bool(self.model.events))

    def edit_selected(self):
        selected = self.table.selected_rows()
        if selected:
            self.edit(selected[0])

    def insert(self, events, description="Insertar eventos"):
        selected = self.table.selected_rows()
        index = selected[-1] + 1 if selected else len(self.model.events)
        try:
            self.model.update(self.model.events[:index] + events + self.model.events[index:], description)
        except ValidationError as exc:
            QMessageBox.warning(self, "No se pudo insertar", str(exc))

    def add(self):
        dialog = EventDialog(parent=self)
        if dialog.exec():
            self.insert([dialog.result_event])

    def edit(self, index):
        if not self.model.editable:
            return
        dialog = EventDialog(self.model.events[index], self)
        if dialog.exec():
            events = list(self.model.events)
            events[index] = dialog.result_event
            self.model.update(events, "Editar evento")

    def add_wait(self):
        value, ok = QInputDialog.getDouble(self, "Insertar pausa", "Duración (segundos)", 1, 0, 86400, 4)
        if ok:
            self.insert([Event("wait", value)], "Insertar pausa")

    def add_chord(self):
        text, ok = QInputDialog.getText(self, "Combinación de teclas", "Ejemplo: ctrl_l+c, shift_l+a, alt_l+tab")
        if not ok:
            return
        try:
            keys = [normalize_key(part.strip()) for part in text.split("+")]
            if len(keys) > 10:
                raise ValidationError("Máximo 10 teclas por combinación.")
            events = [Event("key_down", 0.03, key=k) for k in keys]
            events += [Event("key_up", 0.03, key=k) for k in reversed(keys)]
            self.insert(events, "Insertar combinación")
        except ValidationError as exc:
            QMessageBox.warning(self, "Combinación inválida", str(exc))

    def add_text(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Insertar texto")
        layout = QVBoxLayout(dialog)
        layout.addWidget(label("El texto se convertirá en pulsaciones editables. No incluyas contraseñas.", "muted", True))
        text = QPlainTextEdit()
        layout.addWidget(text)
        enter = QCheckBox("Pulsar Enter al terminar")
        layout.addWidget(enter)
        layout.addWidget(button("Insertar", dialog.accept, primary=True))
        if dialog.exec():
            value = text.toPlainText()
            if len(value) > 10000:
                QMessageBox.warning(self, "Texto demasiado largo", "Máximo 10 000 caracteres.")
                return
            events = []
            for char in value + ("\n" if enter.isChecked() else ""):
                key = {"\n": "key:enter", "\t": "key:tab"}.get(char, "char:" + char)
                events.extend((Event("key_down", 0.025, key=key), Event("key_up", key=key)))
            self.insert(events, "Insertar texto")

    def add_pointer(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Clic, doble clic o arrastre")
        form = QFormLayout(dialog)
        kind = combo([("Clic", "click"), ("Doble clic", "double"), ("Arrastrar y soltar", "drag")])
        btn = combo([("Izquierdo", "left"), ("Derecho", "right"), ("Central", "middle"), ("Lateral X1", "x1"), ("Lateral X2", "x2")])
        x1, y1, x2, y2 = (spin(-1_000_000, 1_000_000, value) for value in (100, 100, 300, 300))
        duration = spin(0.05, 600, 0.5, " s", 3)
        form.addRow("Acción", kind)
        form.addRow("Botón", btn)
        form.addRow("Origen X / Y", row(x1, y1))
        form.addRow("Destino del arrastre X / Y", row(x2, y2))
        form.addRow("Duración del arrastre", duration)
        form.addRow(button("Insertar", dialog.accept, primary=True))
        if dialog.exec():
            events = [Event("mouse_down", button=btn.currentData(), x=x1.value(), y=y1.value())]
            if kind.currentData() == "drag":
                steps = max(2, min(1000, int(duration.value() * 50)))
                for i in range(1, steps + 1):
                    events.append(Event("move", duration.value() / steps, x=round(x1.value() + (x2.value() - x1.value()) * i / steps),
                                        y=round(y1.value() + (y2.value() - y1.value()) * i / steps)))
                events.append(Event("mouse_up", button=btn.currentData(), x=x2.value(), y=y2.value()))
            else:
                events.append(Event("mouse_up", 0.04, button=btn.currentData(), x=x1.value(), y=y1.value()))
                if kind.currentData() == "double":
                    events += [replace(events[0], delay=0.05), events[1]]
            self.insert(events, "Insertar acción de ratón")

    def duplicate(self):
        selected = self.table.selected_rows()
        if selected:
            self.insert([self.model.events[i] for i in selected], "Duplicar eventos")

    def delete(self):
        selected = set(self.table.selected_rows())
        if selected:
            self.model.update([e for i, e in enumerate(self.model.events) if i not in selected], "Eliminar eventos")

    def move(self, direction):
        selected = self.table.selected_rows()
        if selected:
            target = max(0, selected[0] - 1) if direction < 0 else min(len(self.model.events), selected[-1] + 2)
            self.model.reorder(selected, target)

    def copy(self):
        selected = self.table.selected_rows()
        if selected:
            mime = QMimeData()
            mime.setData("application/x-macroflow-events", QByteArray(json.dumps([self.model.events[i].to_dict() for i in selected]).encode()))
            QApplication.clipboard().setMimeData(mime)

    def paste(self):
        mime = QApplication.clipboard().mimeData()
        if not mime or not mime.hasFormat("application/x-macroflow-events"):
            return
        try:
            raw = bytes(mime.data("application/x-macroflow-events"))
            if len(raw) > 32 * 1024 * 1024:
                raise ValidationError("Secuencia demasiado grande.")
            data = json.loads(raw)
            if not isinstance(data, list) or len(data) > MAX_EVENTS:
                raise ValidationError("Secuencia inválida.")
            self.insert([Event.from_dict(event) for event in data], "Pegar eventos")
        except (ValueError, TypeError, RecursionError):
            QMessageBox.warning(self, "Portapapeles inválido", "No se pudo leer la secuencia de eventos.")
