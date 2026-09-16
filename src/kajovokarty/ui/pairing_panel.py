"""Global, non-persistent pairing work surface."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QAbstractItemView, QFrame, QCheckBox,
)
from kajovokarty.ui.work_table import WorkTable
from kajovokarty.ui.models import TableModel, compact_payment_columns
from kajovokarty.domain.core import display_money
from kajovokarty.domain.columns import KIND_NAMES, value_token


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
    """The panel only owns a draft; it never reads selection changes implicitly."""

    requested = Signal(str)
    dropped = Signal(object, object)
    newGroup = Signal(object)
    detachRequested = Signal()
    allowAutoRequested = Signal()
    saveRequested = Signal()
    candidatesRequested = Signal()
    candidateAdded = Signal(object)
    draftChanged = Signal()
    candidateFilterChanged = Signal(object, object)

    def __init__(self, workspace):
        super().__init__()
        self.workspace = workspace
        self.current = None
        self.draft_rows = []
        self.dirty = False
        self.draft_revision = 0
        layout = QVBoxLayout(self)

        self.heading = QLabel("Párovací plocha")
        self.heading.setStyleSheet("font-size:18px;font-weight:bold;")
        layout.addWidget(self.heading)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)

        pairing_columns = [
            ("kinds", "Zdroj"), ("date", "Datum"),
            ("amount", "Částka"), ("currency", "Měna"),
            ("primary_identifier", "Identifikátor"), ("description", "Položka"),
        ]
        self.model = TableModel(columns=pairing_columns)
        self.table = WorkTable()
        self.table.workspace = workspace
        self.table.setAccessibleName("Položky párovací plochy")
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.groupDropped.connect(lambda payload, _target: self.dropped.emit(payload, 'add'))
        compact_payment_columns(self.table)
        layout.addWidget(self.table, 1)

        candidate_bar = QHBoxLayout()
        self.candidate_heading = QLabel("Kandidáti")
        candidate_bar.addWidget(self.candidate_heading)
        self.include_paired = QCheckBox("Zobrazit i spárované")
        self.include_paired.setObjectName("includePairedCandidates")
        self.include_paired.setVisible(False)
        self.include_paired.stateChanged.connect(lambda _state: self.candidatesRequested.emit())
        candidate_bar.addWidget(self.include_paired)
        candidate_bar.addStretch()
        self.candidate_bar = QWidget()
        self.candidate_bar.setLayout(candidate_bar)
        self.candidate_bar.hide()
        layout.addWidget(self.candidate_bar)

        self.candidate_model = TableModel(columns=pairing_columns)
        self.candidate_table = WorkTable()
        self.candidate_table.workspace = workspace
        self.candidate_table.setModel(self.candidate_model)
        self.candidate_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.candidate_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        compact_payment_columns(self.candidate_table)
        def sync_width(peer, index, _old, width):
            if index != 5 and peer.columnWidth(index) != width:
                peer.setColumnWidth(index, width)
        self.table.horizontalHeader().sectionResized.connect(
            lambda i, old, width: sync_width(self.candidate_table, i, old, width))
        self.candidate_table.horizontalHeader().sectionResized.connect(
            lambda i, old, width: sync_width(self.table, i, old, width))
        self.candidate_table.hide()
        self.candidate_table.column_controller.set_filter = self.set_candidate_filter
        layout.addWidget(self.candidate_table)
        self.add_candidate = QPushButton("Přidat označené kandidáty")
        self.add_candidate.clicked.connect(self._emit_candidates)
        self.add_candidate.hide()
        layout.addWidget(self.add_candidate)

        buttons = QHBoxLayout()
        self.detach = QPushButton("Vyjmout označené")
        self.detach.clicked.connect(self.detachRequested)
        buttons.addWidget(self.detach)
        layout.addLayout(buttons)
        self.save = QPushButton("Uložit skupinu")
        self.save.clicked.connect(self.saveRequested)
        self.save.setObjectName("saveGroups")
        layout.addWidget(self.save)
        self.candidates = QPushButton("Vyhledat kandidáty")
        self.candidates.clicked.connect(self.candidatesRequested)
        self.candidates.setObjectName("findCandidates")
        layout.addWidget(self.candidates)
        self.free_area = DropArea(
            workspace,
            "Vyjmout z párovací plochy\nPřetáhněte položku do tohoto rámečku.",
        )
        self.free_area.dropped.connect(lambda payload: self.dropped.emit(payload, 'remove'))
        layout.addWidget(self.free_area)
        hint = QLabel(
            "Párovací plocha je pracovní návrh. Uložit lze pouze skupinu nejméně dvou položek stejné měny se součtem 0."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.reset()

    def reset(self):
        self.current = None
        self.draft_rows = []
        self.dirty = False
        self.model.replace([])
        self.model.set_bold_ids([])
        self.candidate_model.replace([])
        self.candidate_model.set_bold_ids([])
        self.candidate_bar.hide()
        self.candidate_table.hide()
        self.add_candidate.hide()
        self.detach.setEnabled(False)
        self.save.setEnabled(False)
        self._update_summary()

    def dragEnterEvent(self, event):
        if WorkTable.decode(event.mimeData(), self.workspace):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        payload = WorkTable.decode(event.mimeData(), self.workspace)
        if payload:
            self.dropped.emit(payload, "add")
            event.setDropAction(Qt.MoveAction)
            event.accept()
        else:
            event.ignore()

    def clear_draft(self):
        self.reset()

    def clear_candidates(self):
        """Remove candidates from the panel without discarding the draft."""
        self.candidate_model.replace([])
        self.candidate_model.set_bold_ids([])
        self.candidate_bar.hide()
        self.candidate_table.hide()
        self.add_candidate.hide()

    def add_rows(self, rows, mark_dirty=True):
        existing = {r.get("id") for r in self.draft_rows}
        added = []
        for row in rows:
            if row.get('id') not in existing:
                added.append(dict(row))
                existing.add(row.get('id'))
        if not added:
            return False
        currencies = {r.get("currency") for r in self.draft_rows + added if r.get("currency")}
        if len(currencies) > 1:
            return False
        self.draft_rows.extend(added)
        self.current = self.draft_rows[0] if self.draft_rows else None
        self.model.replace(self.draft_rows)
        self.model.set_bold_ids([r.get("id") for r in self.draft_rows if r.get("resolved")])
        self.dirty = self.dirty or mark_dirty
        self.detach.setEnabled(bool(self.draft_rows))
        self._update_summary()
        return True

    def remove_selected_draft(self):
        selected = {
            self.model.rows[i.row()]["id"]
            for i in self.table.selectionModel().selectedRows()
        }
        if not selected:
            return False
        self.draft_rows = [r for r in self.draft_rows if r.get("id") not in selected]
        self.current = self.draft_rows[0] if self.draft_rows else None
        self.model.replace(self.draft_rows)
        self.model.set_bold_ids([r.get("id") for r in self.draft_rows if r.get("resolved")])
        self.dirty = True
        self._update_summary()
        return True

    def _update_summary(self):
        self.draft_revision += 1
        self.draftChanged.emit()
        currencies = {r.get("currency") for r in self.draft_rows if r.get("currency")}
        difference = sum(r.get("difference", 0) for r in self.draft_rows)
        if not self.draft_rows:
            text = "Pracovní návrh je prázdný. Přidejte platby stejné měny."
        elif len(currencies) != 1:
            text = "Návrh obsahuje více měn; takovou skupinu nelze uložit."
        else:
            currency = next(iter(currencies))
            state = "Připraveno k uložení" if len(self.draft_rows) >= 2 and difference == 0 else "Součet musí být 0"
            text = f"{len(self.draft_rows)} položek · rozdíl {display_money(difference)} {currency} · {state}"
        self.summary.setText(text)
        self.save.setEnabled(
            len(self.draft_rows) >= 2 and len(currencies) == 1 and difference == 0
        )

    def set_candidate_filter(self, field, selected):
        self.candidate_model.set_column_filter(field, selected)
        self.candidateFilterChanged.emit(field, selected)

    def default_candidate_sources(self):
        excluded = set(self.current.get('kinds', [])) if self.current else set()
        return [value_token([kind]) for kind in KIND_NAMES if kind not in excluded]

    def show_candidates(self, rows, reset_sources=False):
        if reset_sources:
            self.candidate_model.column_filters['kinds'] = self.default_candidate_sources()
        self.candidate_model.replace(rows)
        self.candidate_model.set_bold_ids([r.get("id") for r in rows if r.get("resolved")])
        visible = True  # Keep filters accessible even when nothing matches.
        self.candidate_bar.setVisible(visible)
        self.include_paired.setVisible(visible)
        self.candidate_table.setVisible(visible)
        self.add_candidate.setVisible(visible)
        self.candidate_table.column_controller.refresh()

    def _emit_candidates(self):
        rows = [
            self.candidate_model.rows[i.row()]
            for i in self.candidate_table.selectionModel().selectedRows()
        ]
        if rows:
            self.candidateAdded.emit(rows)
