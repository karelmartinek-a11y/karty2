"""Visible pairing work surface; no financial mutation is implemented in widgets."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QAbstractItemView,
    QFrame,
)
from kajovokarty.ui.work_table import WorkTable
from kajovokarty.ui.models import TableModel
from kajovokarty.domain.core import display_money


class DropArea(QFrame):
    dropped = Signal(object)

    def __init__(self, workspace, text):
        super().__init__()
        self.workspace = workspace
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet(
            "DropArea {border:2px dashed #7297b5;border-radius:6px;background:#f2f7fb;}"
        )
        layout = QVBoxLayout(self)
        label = QLabel(text)
        label.setWordWrap(True)
        layout.addWidget(label)
        self.setAccessibleName(text)

    def dragEnterEvent(self, event):
        if WorkTable.decode(event.mimeData(), self.workspace):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        self.dragEnterEvent(event)

    def dropEvent(self, event):
        payload = WorkTable.decode(event.mimeData(), self.workspace)
        if payload:
            self.setFocus(Qt.MouseFocusReason)
            self.dropped.emit(payload)
            event.setDropAction(Qt.MoveAction)
            event.accept()
        else:
            event.ignore()


class PairingPanel(QWidget):
    requested = Signal(str)
    dropped = Signal(object, object)
    newGroup = Signal(object)
    detachRequested = Signal()
    dissolveRequested = Signal()
    allowAutoRequested = Signal()

    def __init__(self, workspace):
        super().__init__()
        self.current = None
        layout = QVBoxLayout(self)
        self.heading = QLabel("Párovací plocha")
        self.heading.setStyleSheet("font-size:18px;font-weight:bold;")
        layout.addWidget(self.heading)
        self.summary = QLabel(
            "Označte platbu nebo skupinu. Přetažením na jinou platbu vytvoříte skupinu."
        )
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.target_area = DropArea(
            workspace, "Přidat platby do otevřeného detailu přetažením sem"
        )
        self.target_area.dropped.connect(
            lambda payload: self.dropped.emit(payload, self.current)
            if self.current
            else self.newGroup.emit(payload)
        )
        layout.addWidget(self.target_area)
        self.model = TableModel(
            columns=[
                ("primary_identifier", "Člen skupiny"),
                ("type", "Objekt"),
                ("kinds", "Zdroj"),
                ("amount", "Původní částka"),
                ("difference", "Příspěvek"),
                ("currency", "Měna"),
            ]
        )
        self.table = WorkTable()
        self.table.workspace = workspace
        self.table.setAccessibleName("Členové párování")
        self.table.setModel(self.model)
        for col, width in enumerate([140, 80, 105, 130, 115, 75]):
            self.table.setColumnWidth(col, width)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.groupDropped.connect(self.dropped)
        self.table.doubleClicked.connect(
            lambda index: self.requested.emit(self.model.rows[index.row()]["id"])
        )
        layout.addWidget(self.table, 1)
        buttons = QHBoxLayout()
        self.up = QPushButton("Nadřazená skupina")
        self.up.clicked.connect(
            lambda: self.requested.emit(self.parent_id) if self.parent_id else None
        )
        self.detach = QPushButton("Vyjmout označené")
        self.detach.clicked.connect(self.detachRequested)
        buttons.addWidget(self.up)
        buttons.addWidget(self.detach)
        layout.addLayout(buttons)
        self.clear = QPushButton("Rozpárovat celou skupinu")
        self.clear.clicked.connect(self.dissolveRequested)
        layout.addWidget(self.clear)
        self.allow_auto = QPushButton("Znovu povolit původní automatické shody")
        self.allow_auto.clicked.connect(self.allowAutoRequested)
        layout.addWidget(self.allow_auto)
        self.free_area = DropArea(
            workspace,
            "Rozpárovat / vrátit jednotlivě\nPřetáhněte sem člena nebo celou skupinu. Podskupiny zůstanou pohromadě.",
        )
        self.free_area.dropped.connect(lambda payload: self.dropped.emit(payload, None))
        layout.addWidget(self.free_area)
        self.new_area = DropArea(
            workspace, "Nová skupina — přetáhněte alespoň dvě označené platby"
        )
        self.new_area.dropped.connect(self.newGroup)
        layout.addWidget(self.new_area)
        label = QLabel(
            "Pokladna přispívá +částkou; terminál a Booking −částkou.\nVyřízeno = přesně nulový rozdíl v jedné měně. Každý přesun lze vrátit Ctrl+Z."
        )
        label.setWordWrap(True)
        layout.addWidget(label)
        self.parent_id = None
        self.reset()

    def reset(self):
        self.heading.setText("Párovací plocha")
        self.summary.setText(
            "Vyberte platbu nebo skupinu. Přetáhněte platbu na protějšek nebo skupinu. Změny lze vrátit Ctrl+Z."
        )
        self.current = None
        self.parent_id = None
        self.table.drop_target = None
        self.model.replace([])
        self.up.setEnabled(False)
        self.detach.setEnabled(False)
        self.clear.setEnabled(False)
        self.allow_auto.setVisible(False)

    def show_data(self, data):
        self.current = data["object"]
        self.parent_id = data["parent_id"]
        r = self.current
        self.heading.setText(r["primary_identifier"])
        self.summary.setText(
            f"{'Vyřízeno' if r['resolved'] else 'Nevyřízeno'} · {r['leaf_count']} listů\nRozdíl {display_money(r['difference'])} {r['currency']}\n"
            + (
                "Automatické párování; ruční úprava bude zaznamenána."
                if r.get("method") == "AUTO"
                else "Ruční pracovní prostor"
            )
        )
        self.model.replace(data["rows"])
        self.table.drop_target = r
        self.up.setEnabled(bool(self.parent_id))
        self.detach.setEnabled(r["type"] == "GROUP")
        self.clear.setEnabled(r["type"] == "GROUP" and not self.parent_id)
        self.allow_auto.setVisible(bool(data.get("suppressed_auto")))
