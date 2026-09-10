import json
from PySide6.QtCore import Qt, Signal, QMimeData
from PySide6.QtGui import QDrag, QKeySequence
from PySide6.QtWidgets import QTableView, QAbstractItemView


class WorkTable(QTableView):
    allRequested = Signal()
    copyRequested = Signal(bool)
    groupDropped = Signal(object, object)
    dropHint = Signal(str)
    MIME = "application/x-kajovokarty-objects"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWordWrap(False)
        self.setTextElideMode(Qt.ElideRight)
        self.workspace = None
        self.drag_guard = lambda: True
        self.drop_target = None  # Optional panel target overrides the hovered member.
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)

    def setModel(self, model):
        super().setModel(model)
        from kajovokarty.ui.column_filters import ColumnController

        ColumnController(self, model)

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.SelectAll):
            self.selectAll()
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

    def mime_for_rows(self, rows):
        if (
            not self.workspace
            or not rows
            or any(
                r.get("type") not in ("SOURCE", "GROUP")
                or r.get("lifecycle") != "ACTIVE"
                for r in rows
            )
        ):
            return None
        mime = QMimeData()
        keys = (
            "id",
            "revision",
            "parent_id",
            "parent_revision",
            "currency",
            "difference",
            "type",
            "resolved",
            "primary_identifier",
        )
        mime.setData(
            self.MIME,
            json.dumps(
                {
                    "version": 2,
                    "workspace": self.workspace,
                    "rows": [{k: r.get(k) for k in keys} for r in rows],
                }
            ).encode(),
        )
        return mime

    @staticmethod
    def decode(mime, workspace):
        if not workspace or not mime.hasFormat(WorkTable.MIME):
            return None
        raw = bytes(mime.data(WorkTable.MIME))
        if len(raw) > 2_000_000:
            return None
        try:
            data = json.loads(raw)
            rows = data["rows"]
            if (
                data.get("version") != 2
                or data.get("workspace") != workspace
                or not isinstance(rows, list)
                or not rows
            ):
                return None
            if any(
                not isinstance(r, dict)
                or not isinstance(r.get("id"), str)
                or not isinstance(r.get("revision"), int)
                or r.get("type") not in ("SOURCE", "GROUP")
                for r in rows
            ):
                return None
            return data
        except (ValueError, TypeError, KeyError):
            return None

    def startDrag(self, actions):
        if not self.drag_guard():
            return
        rows = [
            self.model().rows[i.row()] for i in self.selectionModel().selectedRows()
        ]
        mime = self.mime_for_rows(rows)
        if mime is None:
            return
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.MoveAction)

    def target_at(self, event):
        if self.drop_target is not None:
            return self.drop_target
        index = self.indexAt(event.position().toPoint())
        return self.model().rows[index.row()] if index.isValid() else None

    def dragEnterEvent(self, event):
        if self.decode(event.mimeData(), self.workspace):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        payload = self.decode(event.mimeData(), self.workspace)
        if payload is None:
            event.ignore()
            return
        target = self.target_at(event)
        if target and (
            target.get("type") not in ("SOURCE", "GROUP")
            or target.get("lifecycle") != "ACTIVE"
            or target["id"] in {r["id"] for r in payload["rows"]}
        ):
            self.dropHint.emit(
                "Sem nelze přesunout: nefinanční objekt nebo vlastní položka."
            )
            event.ignore()
            return
        currencies = {r.get("currency") for r in payload["rows"]}
        if target:
            currencies.add(target.get("currency"))
        if len(currencies) != 1:
            self.dropHint.emit("Nelze spojit různé měny.")
            event.ignore()
            return
        from kajovokarty.domain.core import display_money

        if target:
            difference = target.get("difference", 0) + sum(
                r.get("difference", 0)
                for r in payload["rows"]
                if r.get("parent_id") != target["id"]
            )
            self.dropHint.emit(
                f"Po puštění: {'vyřízeno' if difference == 0 else 'otevřená skupina'} · rozdíl {display_money(difference)} {target['currency']}. Zpět: Ctrl+Z."
            )
        else:
            self.dropHint.emit(
                "Uvolnit členy / rozpárovat skupinu. Podskupiny a zdroje zůstanou zachovány. Zpět: Ctrl+Z."
            )
        event.acceptProposedAction()

    def dropEvent(self, event):
        payload = self.decode(event.mimeData(), self.workspace)
        if payload:
            self.setFocus(Qt.MouseFocusReason)
            self.groupDropped.emit(payload, self.target_at(event))
            event.setDropAction(Qt.MoveAction)
            event.accept()
        else:
            event.ignore()
