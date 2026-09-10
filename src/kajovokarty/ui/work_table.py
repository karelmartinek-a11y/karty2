import json
from PySide6.QtCore import Qt, Signal, QMimeData
from PySide6.QtGui import QDrag, QKeySequence
from PySide6.QtWidgets import QTableView, QAbstractItemView


class WorkTable(QTableView):
    allRequested = Signal()
    copyRequested = Signal(bool)
    groupDropped = Signal(object, object)
    MIME = "application/x-kajovokarty-objects"

    def __init__(self):
        super().__init__()
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.SelectAll):
            self.allRequested.emit()
            event.accept()
        elif event.matches(QKeySequence.Copy):
            self.copyRequested.emit(False)
            event.accept()
        elif event.key() == Qt.Key_C and event.modifiers() == (
            Qt.ControlModifier | Qt.ShiftModifier
        ):
            self.copyRequested.emit(True)
            event.accept()
        else:
            super().keyPressEvent(event)

    def startDrag(self, actions):
        rows = [
            self.model().rows[i.row()] for i in self.selectionModel().selectedRows()
        ]
        if not rows or any(
            r.get("type") not in ("SOURCE", "GROUP") or r.get("resolved") for r in rows
        ):
            return
        mime = QMimeData()
        mime.setData(
            self.MIME, json.dumps({r["id"]: r["revision"] for r in rows}).encode()
        )
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.MoveAction)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(self.MIME):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        index = self.indexAt(event.position().toPoint())
        if index.isValid() and event.mimeData().hasFormat(self.MIME):
            row = self.model().rows[index.row()]
            if row.get("type") == "GROUP" and not row.get("resolved"):
                event.acceptProposedAction()
                return
        event.ignore()

    def dropEvent(self, event):
        index = self.indexAt(event.position().toPoint())
        if index.isValid() and event.mimeData().hasFormat(self.MIME):
            try:
                payload = json.loads(bytes(event.mimeData().data(self.MIME)))
            except (ValueError, TypeError):
                return
            row = self.model().rows[index.row()]
            if row.get("type") == "GROUP" and not row.get("resolved"):
                self.groupDropped.emit(payload, row)
                event.acceptProposedAction()
