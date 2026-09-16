from __future__ import annotations
from pathlib import Path
import json
import threading
from PySide6.QtCore import Qt, QThreadPool, QTimer, QByteArray, QItemSelectionModel
from PySide6.QtGui import QFont, QIcon, QPainter, QPixmap, QColor
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QDockWidget,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QLabel,
    QLineEdit,
    QPushButton,
    QAbstractItemView,
    QComboBox,
    QToolBar,
    QDialog,
    QDialogButtonBox,
    QPlainTextEdit,
    QMessageBox,
    QFileDialog,
    QFormLayout,
    QCheckBox,
    QInputDialog,
    QSplitter,
    QMenu,
)
from kajovokarty.domain.core import (
    AppError,
    uid,
    canonical,
    checked,
    decimal_money,
    display_money,
    money,
    parse_date,
)
from kajovokarty.application.imports import ImportService, ImportInput
from kajovokarty.application.work import WorkService
from kajovokarty.application.settings import SettingsService
from kajovokarty.application.matching import MatchingService
from kajovokarty.application.backup import BackupService
from kajovokarty.application.catalog import CatalogService
from kajovokarty.application.reports import ReportService
from kajovokarty.ui.models import TableModel, WORK_COLUMNS, HIDDEN_PAYMENT_COLUMNS, payment_columns, hide_payment_columns
from kajovokarty.ui.work_table import WorkTable
from kajovokarty.ui.workers import Job
from kajovokarty.ui.actions import ActionSpec, ActionRegistry

NAV = [
    "Nevyřízené",
    "Vyřízené",
    "Importy",
    "Pomocná data",
    "Vyhledávání",
    "Sestavy",
    "Audit",
    "Nastavení",
    "Skupiny",
]
SOURCE_NAMES = {
    "Pokladna (XLS)": "CASHBOOK_CARD",
    "Terminál (CSV / XLS / XLSX)": "BANK_CARD",
    "Booking.com (CSV)": "BOOKING",
    "Účty (XLS)": "ACCOUNTS",
}
REPORT_NAMES = {
    "Nevyřízené": "unresolved",
    "Vyřízené skupiny": "resolved",
    "Důkaz skupiny": "group_evidence",
    "Karty pokladny": "cashbook_cards",
    "Terminálové transakce": "terminal",
    "Booking platby": "booking",
    "Pomocná data": "helpers",
    "Audit": "audit",
    "Importní chyby": "import_errors",
}


def button(label, fn):
    owner = getattr(fn, "__self__", None)
    if not hasattr(owner, "registry"):
        for cell in getattr(fn, "__closure__", None) or ():
            candidate = cell.cell_contents
            if hasattr(candidate, "registry"):
                owner = candidate
                break
    if hasattr(owner, "registry"):
        return owner.registry.button(label, fn)
    b = QPushButton(label)
    b.setAccessibleName(label)
    b.setToolTip(label)
    b.clicked.connect(fn)
    return b


def text_dialog(parent, title, text):
    d = QDialog(parent)
    d.setWindowTitle(title)
    d.resize(900, 600)
    layout = QVBoxLayout(d)
    box = QPlainTextEdit()
    box.setPlainText(text)
    box.setReadOnly(True)
    layout.addWidget(box)
    close = QDialogButtonBox(QDialogButtonBox.Close)
    close.rejected.connect(d.reject)
    layout.addWidget(close)
    d.exec()


class MainWindow(QMainWindow):
    def __init__(self, db):
        super().__init__()
        self.db = db
        self.work = WorkService(db)
        from kajovokarty.application.pairing import PairingService

        self.pairing = PairingService(db)
        self.workspace_id = uid()
        self.panel_revision = 0
        self.imports = ImportService(db)
        self.settings = SettingsService(db)
        self.matching = MatchingService(db, self.settings)
        self.backup = BackupService(db)
        self.catalog = CatalogService(db)
        self.reports = ReportService(db)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(2)
        self.jobs = set()
        self.busy = False
        self.cancel = threading.Event()
        self.rows = []
        self.selection = {}
        self.result_selection = None
        self.restoring_selection = False
        self.scope = 0
        self.query_revision = 0
        # Invalidates read-only responses which were started before a mutation.
        self.live_view_revision = 0
        self.candidate_request = 0
        self.candidate_context = None
        self.candidate_rows = None
        self.sort_order = [("date", "asc")]
        self.advanced = {}
        self.column_states = {}
        self.view_sorts = {}
        self.facet_rows = []
        self.global_history = False
        self.combined_groups_only = False
        self.setWindowTitle("KájovoKarty")
        self.resize(1366, 850)
        self.setMinimumSize(1100, 700)
        self.setFont(QFont("Segoe UI", 10))
        self.setAcceptDrops(True)
        pix = QPixmap(48, 48)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#2873b8"))
        p.drawRoundedRect(5, 5, 31, 24, 4, 4)
        p.setBrush(QColor("#133557"))
        p.drawRoundedRect(13, 18, 31, 24, 4, 4)
        p.end()
        self.setWindowIcon(QIcon(pix))
        self.setStyleSheet(
            "QMainWindow,QWidget { background:#ffffff; color:#182b3b; } QLineEdit,QComboBox,QSpinBox,QPlainTextEdit { border:1px solid #b4c3d0; padding:6px; border-radius:4px; } QPushButton { padding:8px 12px; border:1px solid #a8bed0; border-radius:4px; background:#f3f7fb; } QPushButton:hover { background:#deebf8; } QPushButton:focus { border:2px solid #2064a0; } QListWidget { background:#f2f6fa; border:0; padding:8px; } QListWidget::item { padding:12px; } QListWidget::item:selected { background:#dce9f8; color:#153957; } QHeaderView::section { background:#edf3f8; padding:8px; border:0; border-bottom:1px solid #ced9e3; } QTableView { gridline-color:#e7edf3; selection-background-color:#dbeaf8; selection-color:#14293c; }"
        )
        self.base_stylesheet = self.styleSheet()
        root = QWidget()
        rootlayout = QVBoxLayout(root)
        rootlayout.setContentsMargins(0, 0, 0, 0)
        self.setCentralWidget(root)
        self.registry = ActionRegistry(self)
        self.focus_callback = lambda old, new: self.registry.refresh()
        QApplication.instance().focusChanged.connect(self.focus_callback)
        bar = QToolBar()
        bar.setMovable(False)
        self.addToolBar(bar)
        wordmark = QLabel("  KájovoKarty  ")
        wordmark.setFont(QFont("Segoe UI", 17, QFont.Bold))
        bar.addWidget(wordmark)
        specs = [
            ("import", "Importovat", "Ctrl+I", self.choose_import),
            ("auto", "Automaticky spárovat vše", "", self.start_auto),
            ("detail", "Otevřít detail", "Return", self.open_detail),
            (
                "select",
                "Přidat / odebrat pracovní výběr",
                "Ctrl+Space",
                self.toggle_selection,
            ),
            (
                "counterparts",
                "Najít možné protějšky",
                "Ctrl+Shift+F",
                self.counterparts,
            ),
            ("add_group", "Přidat do párovací plochy", "", self.add_selection),
            # Keystroke/API compatibility for existing integrations; grouping is
            # now exposed through the pairing panel instead of a section button.
            ("group", "Vytvořit skupinu / spárovat", "", self.group_dialog),
            ("drop_group", "Přetáhnout do skupiny", "", self.drop_group),
            ("copy", "Kopírovat hlavní ID", "", lambda: self.copy_rows(False)),
            (
                "copy_all",
                "Kopírovat řádky a všechna ID",
                "",
                lambda: self.copy_rows(True),
            ),
            ("audit_object", "Audit objektu", "", self.open_detail),
            (
                "undo",
                "Zpět",
                "Ctrl+Z",
                lambda: self.run(lambda p: self.work.undo(), self.after_mutation),
            ),
            (
                "redo",
                "Znovu",
                "Ctrl+Y",
                lambda: self.run(
                    lambda p: self.work.undo(redo=True), self.after_mutation
                ),
            ),
            ("refresh", "Obnovit pohled", "F5", self.refresh),
            ("find", "Fulltext", "Ctrl+F", lambda: self.search.setFocus()),
            ("dissolve", "Rozložit skupinu", "Shift+Delete", self.dissolve_selected),
            ("note", "Upravit poznámku", "F2", self.edit_note),
            ("export", "Exportovat", "", self.export_dialog),
        ]
        for id, label, shortcut, handler in specs:
            action = self.registry.register(
                ActionSpec(
                    id,
                    label,
                    shortcut,
                    (),
                    lambda action_id=id: self.action_allowed(action_id),
                    "Probíhá operace.",
                    handler,
                )
            )
            if id in ("import", "auto"):
                bar.addAction(action)
            if id == "group":
                action.setVisible(False)
        bar.addSeparator()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Hledat číslo, hosta, VS…")
        self.search.setAccessibleName("Fulltextové vyhledávání")
        self.search.setMinimumWidth(210)
        bar.addWidget(self.search)
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(300)
        self.search.textChanged.connect(lambda: self.search_timer.start())
        self.search_timer.timeout.connect(self.refresh)
        middle = QSplitter()
        rootlayout.addWidget(middle, 1)
        self.nav = QListWidget()
        self.nav.addItems(NAV)
        self.nav.setMaximumWidth(220)
        self.nav.setAccessibleName("Hlavní navigace")
        middle.addWidget(self.nav)
        content = QWidget()
        self.contentlayout = QVBoxLayout(content)
        middle.addWidget(content)
        middle.setStretchFactor(1, 1)
        self.title = QLabel(NAV[0])
        self.title.setFont(QFont("Segoe UI", 22, QFont.Bold))
        self.contentlayout.addWidget(self.title)
        self.kpi = QLabel()
        self.kpi.setWordWrap(True)
        self.contentlayout.addWidget(self.kpi)
        self.empty_hint = QLabel(
            "Zatím zde nejsou žádné finanční pohyby. Začněte tlačítkem Importovat a vyberte úplný export pokladny, terminálu nebo Bookingu."
        )
        self.empty_hint.setWordWrap(True)
        self.contentlayout.addWidget(self.empty_hint)
        filters = QHBoxLayout()
        self.currency = QComboBox()
        self.currency.addItems(["Všechny měny", "CZK", "EUR"])
        self.source = QComboBox()
        self.source.addItems(["Všechny zdroje", *[n for n, k in SOURCE_NAMES.items() if k != "ACCOUNTS"]])
        self.date_from = QLineEdit()
        self.date_from.setPlaceholderText("Datum od YYYY-MM-DD")
        self.date_to = QLineEdit()
        self.date_to.setPlaceholderText("Datum do YYYY-MM-DD")
        for w in (self.currency, self.source, self.date_from, self.date_to):
            filters.addWidget(w)
        filters.addWidget(button("Další filtry", self.advanced_filters))
        filters.addWidget(button("Uložit filtr", self.save_filter))
        filters.addWidget(button("Načíst filtr", self.load_filter))
        self.contentlayout.addLayout(filters)
        self.currency.currentIndexChanged.connect(self.refresh)
        self.source.currentIndexChanged.connect(self.refresh)
        self.date_from.editingFinished.connect(self.refresh)
        self.date_to.editingFinished.connect(self.refresh)
        self.contextbar = QHBoxLayout()
        self.contentlayout.addLayout(self.contextbar)
        self.model = TableModel(columns=WORK_COLUMNS)
        self.model.remote = True
        self.table = WorkTable()
        self.table.workspace = self.workspace_id
        self.table.drag_guard = self.can_start_drag
        self.table.dropHint.connect(lambda text: self.status.setText(text))
        self.table.allRequested.connect(self.highlight_all)
        self.table.copyRequested.connect(self.copy_rows)
        self.table.groupDropped.connect(self.add_drag_to_panel)
        self.table.setModel(self.model)
        hide_payment_columns(self.table, self.model.columns)
        cc = self.table.column_controller
        cc.get_filters = lambda: self.column_states.setdefault(self.scope, {})
        cc.set_filter = self.set_column_filter
        cc.set_sort = self.set_column_sort
        cc.get_options = self.column_options
        self.table.selectionModel().selectionChanged.connect(self.selection_changed)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setAccessibleName("Pracovní tabulka")
        self.table.horizontalHeader().setSectionsMovable(True)
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.doubleClicked.connect(self.open_detail)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.context_menu)
        self.group_detail_model = TableModel(columns=[
            ("primary_identifier", "Položka"), ("type", "Objekt"),
            ("kinds", "Zdroj"), ("amount", "Částka"),
            ("difference", "Příspěvek"), ("currency", "Měna"),
        ])
        self.group_detail_table = WorkTable()
        self.group_detail_table.workspace = self.workspace_id
        self.group_detail_table.setModel(self.group_detail_model)
        self.group_detail_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.group_detail_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.group_detail_table.setAccessibleName("Obsah vybrané skupiny")
        self.group_detail_title = QLabel("Vyberte skupinu")
        detail = QWidget()
        detail_layout = QVBoxLayout(detail)
        detail_layout.addWidget(self.group_detail_title)
        detail_layout.addWidget(self.group_detail_table, 1)
        self.group_detail = detail
        self.group_detail.hide()
        self.group_splitter = QSplitter(Qt.Horizontal)
        self.group_splitter.addWidget(self.table)
        self.group_splitter.addWidget(self.group_detail)
        self.group_splitter.setStretchFactor(0, 3)
        self.group_splitter.setStretchFactor(1, 2)
        self.contentlayout.addWidget(self.group_splitter, 1)
        self.page = 0
        self.total = 0
        pager = QHBoxLayout()
        pager.addWidget(button("Předchozí", lambda: self.turn_page(-1)))
        self.page_label = QLabel()
        pager.addWidget(self.page_label)
        pager.addWidget(button("Další", lambda: self.turn_page(1)))
        pager.addStretch()
        pager.addWidget(button("Vybrat všechny výsledky", self.select_all))
        self.contentlayout.addLayout(pager)
        bottom = QHBoxLayout()
        self.selection_label = QLabel("Pracovní výběr je prázdný.")
        bottom.addWidget(self.selection_label, 1)
        bottom.addWidget(button("Přidat do párovací plochy", self.add_selection))
        rootlayout.addLayout(bottom)
        self.status = QLabel("Připraveno")
        self.statusBar().addWidget(self.status, 1)
        self.cancel_button = button("Zrušit operaci", self.cancel_operation)
        self.cancel_button.setEnabled(False)
        self.statusBar().addPermanentWidget(self.cancel_button)
        from kajovokarty.ui.pairing_panel import PairingPanel

        self.pair_panel = PairingPanel(self.workspace_id)
        self.pair_dock = QDockWidget("Párovací plocha", self)
        self.pair_dock.setObjectName("pairingDock")
        self.pair_dock.setWidget(self.pair_panel)
        self.pair_dock.setMinimumWidth(550)
        self.addDockWidget(Qt.RightDockWidgetArea, self.pair_dock)
        self.pair_dock.hide()
        bar.addAction(self.pair_dock.toggleViewAction())
        self.pair_panel.requested.connect(self.open_pairing)
        self.pair_panel.dropped.connect(self.panel_drop)
        self.pair_panel.newGroup.connect(self.drop_new_group)
        self.pair_panel.detachRequested.connect(self.detach_panel_members)
        self.pair_panel.saveRequested.connect(self.save_panel_draft)
        self.pair_panel.candidatesRequested.connect(self.find_panel_candidates)
        self.pair_panel.candidateAdded.connect(lambda rows: self.pair_panel.add_rows(rows))
        self.pair_panel.draftChanged.connect(self.invalidate_candidates)
        self.pair_panel.candidateFilterChanged.connect(self.candidate_filter_changed)
        self.pair_panel.table.drag_guard = lambda: not self.busy
        self.pair_panel.table.dropHint.connect(self.status.setText)
        self.panel_timer = QTimer(self)
        self.panel_timer.setSingleShot(True)
        self.panel_timer.setInterval(130)
        self.panel_timer.timeout.connect(self.open_selected_pairing)
        self.nav.currentRowChanged.connect(self.navigate)
        self.apply_appearance()
        self.nav.setCurrentRow(0)
        self.view_timer = QTimer(self)
        self.view_timer.setSingleShot(True)
        self.view_timer.setInterval(700)
        self.view_timer.timeout.connect(self.save_columns)
        self.table.horizontalHeader().sectionResized.connect(self.persist_columns)
        self.table.horizontalHeader().sectionMoved.connect(self.persist_columns)
        self.refresh()

    def run(
        self, fn, done=None, mutating=True, error_handler=None, progress_handler=None
    ):
        if getattr(self, "shutting_down", False):
            return
        if mutating and self.busy:
            return
        if mutating:
            self.busy = True
            self.cancel.clear()
            self.registry.refresh()
            self.cancel_button.setEnabled(True)
        job = Job(fn, self.db.log)
        self.jobs.add(job)
        job.signals.progress.connect(
            progress_handler or (lambda event: self.status.setText(str(event)))
        )
        job.signals.error.connect(error_handler or self.show_error)
        if done:
            job.signals.result.connect(done)

        def finish():
            self.jobs.discard(job)
            if self.db.log.failure:
                self.status.setText("Podrobný provozní záznam se nepodařilo uložit. Zkontrolujte volné místo a přístup do datové složky.")
            if mutating:
                self.busy = False
                self.cancel_button.setEnabled(False)
                self.registry.refresh()

        job.signals.finished.connect(finish)
        self.pool.start(job)

    def show_error(self, e):
        from kajovokarty.domain.errors import explain
        item = explain(e.code)
        self.status.setText(item.name + " — " + e.user_message)
        QMessageBox.warning(self, item.name, e.user_message + "\nČíslo chyby: " + e.code
                            + ("\nOperace: " + e.operation_id if e.operation_id else ""))

    def cancel_operation(self):
        self.cancel.set()
        self.status.setText("Ruším — čekám na bezpečné dokončení rozpracovaného kroku.")

    def navigate(self, index):
        self.result_selection = None
        self.view_sorts[self.scope] = list(self.sort_order)
        if index != 4:
            self.candidate_rows = None
            self.candidate_context = None
            self.candidate_request += 1
        if index == 8 and hasattr(self, "pair_panel"):
            self.pair_panel.clear_draft()
            self.pair_dock.hide()
        self.scope = index
        self.sort_order = self.view_sorts.get(
            index, [("date", "asc")] if index in (0, 1, 4) else []
        )
        self.page = 0
        self.title.setText(NAV[index])
        while self.contextbar.count():
            item = self.contextbar.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        actions = {
            0: [
                ("Najít možné protějšky", self.counterparts),
                ("Přidat do párovací plochy", self.add_selection),
                ("Exportovat filtr", self.export_dialog),
            ],
            1: [
                ("Rozložit skupinu", self.dissolve_selected),
                ("Exportovat", self.export_dialog),
            ],
            2: [
                ("Pokladna", lambda: self.choose_import("CASHBOOK_CARD")),
                ("Terminál", lambda: self.choose_import("BANK_CARD")),
                ("Booking", lambda: self.choose_import("BOOKING")),
                ("Účty", lambda: self.choose_import("ACCOUNTS")),
                ("Zopakovat uložený import", self.repeat_import),
                ("Původní soubor", self.save_original),
            ],
            3: [
                ("Importovat Účty", lambda: self.choose_import("ACCOUNTS")),
                ("Detail vazby", self.open_detail),
            ],
            4: [
                ("Přidat do výběru", self.add_selection),
                (
                    "Zahrnout / skrýt pomocná data a historii",
                    self.toggle_global_history,
                ),
            ],
            5: [("Vytvořit sestavu", self.export_dialog)],
            6: [("Exportovat audit", self.export_dialog)],
            7: [
                ("Nastavení", self.settings_dialog),
                ("Záloha", self.backup_dialog),
                ("Obnova", self.restore_dialog),
                ("Diagnostika", self.diagnostic_dialog),
                ("Nápověda", self.help_dialog),
            ],
            8: [
                ("Jen kombinované skupiny", self.toggle_combined_groups),
                ("Exportovat", self.export_dialog),
            ],
        }
        for label, fn in actions.get(index, []):
            self.contextbar.addWidget(button(label, fn))
        self.contextbar.addStretch()
        self.refresh()

    def toggle_global_history(self):
        self.global_history = not self.global_history
        self.refresh()

    def filters(self):
        if self.scope in (0, 1, 4):
            self.column_states[self.scope] = {
                k: v for k, v in self.column_states.get(self.scope, {}).items()
                if k not in HIDDEN_PAYMENT_COLUMNS
            }
            self.sort_order = [(k, direction) for k, direction in self.sort_order
                               if k not in HIDDEN_PAYMENT_COLUMNS] or (
                                   [] if self.scope == 4 and self.candidate_context is not None
                                   else [("date", "asc")])
        f = {
            **self.advanced,
            "text": self.search.text(),
            "column_filters": {
                k: list(v) for k, v in self.column_states.get(self.scope, {}).items()
            },
            "status": "resolved"
            if self.scope in (1, 8)
            else "all"
            if self.scope == 4
            else "unresolved",
        }
        if self.currency.currentIndex():
            f["currency"] = [self.currency.currentText()]
        if self.source.currentIndex():
            f["kind"] = [SOURCE_NAMES[self.source.currentText()]]
        if self.date_from.text():
            f["date_from"] = parse_date(self.date_from.text())
        if self.date_to.text():
            f["date_to"] = parse_date(self.date_to.text())
        return f

    def refresh(self, *args):
        self.query_revision += 1
        revision = self.query_revision
        scope = self.scope
        try:
            f = self.filters()
        except AppError as e:
            self.status.setText(e.message)
            return
        page = self.page
        sort_order = list(self.sort_order)
        candidate_context = self.candidate_context if scope == 4 else None

        def query(progress):
            selection = self.work.selection()
            if scope in (0, 1, 4, 8):
                result = self.work.query(
                    {**f, "column_filters": {}}
                    if scope == 4 and self.global_history
                    else f,
                    sort=sort_order,
                    page=page,
                    page_size=0 if scope == 4 and self.global_history else 500,
                )
                if candidate_context is not None:
                    anchor_id, anchor_revision, include_paired = candidate_context
                    candidates = self.work.candidates(anchor_id, anchor_revision, include_paired)
                    filtered = self.filter_catalog_rows(candidates, f.get('column_filters'), sort_order, page)
                    result = {**result, **filtered}
                elif scope == 4 and self.global_history:
                    extra = self.catalog.global_matches(f.get("text", ""))
                    from kajovokarty.domain.columns import filter_rows

                    combined = filter_rows(
                        result["rows"] + extra, f.get("column_filters"), sort_order
                    )
                    result["ids"] = [r["id"] for r in combined]
                    result["total"] = len(combined)
                    result["rows"] = combined[page * 500 : (page + 1) * 500]
                if scope == 8:
                    result["rows"] = [r for r in result["rows"] if r.get("type") == "GROUP"]
                    if getattr(self, "combined_groups_only", False):
                        result["rows"] = [r for r in result["rows"] if r.get("leaf_count", 0) >= 3]
                    result["ids"] = [r["id"] for r in result["rows"]]
                    result["total"] = len(result["rows"])
                return (
                    "work",
                    result,
                    selection,
                    self.catalog.view("columns:compact-v1:" + str(scope)),
                )
            if scope == 2:
                rows = self.catalog.rows("imports")
            elif scope == 3:
                from kajovokarty.application.accounts import rows as account_rows
                from kajovokarty.domain.core import search_normalize, search_tokens
                tokens = search_tokens(f.get("text", ""))
                rows = [r for r in account_rows(self.db) if all(t in search_normalize(" ".join(str(v) for v in r.values())) for t in tokens)]
            elif scope == 6:
                rows = self.catalog.rows("audit")
            elif scope == 5:
                rows = [{"sestava": k, "report_id": v} for k, v in REPORT_NAMES.items()]
            else:
                rows = self.catalog.rows("operations")
            return (
                "other",
                self.filter_catalog_rows(
                    rows, f.get("column_filters"), sort_order, page
                ),
                selection,
                self.catalog.view("columns:compact-v1:" + str(scope)),
            )

        def done(result):
            if revision != self.query_revision:
                return
            kind, value, self.selection, state = result
            selected = set(self.selected_ids())
            self.rows = list(value["rows"])
            self.facet_rows = value.get("base_rows", [])
            if candidate_context is not None:
                self.candidate_rows = list(self.facet_rows)
                self.pair_panel.show_candidates(self.facet_rows)
            self.page = value.get("page", page)
            scroll = self.table.verticalScrollBar().value()
            cols = (
                payment_columns(f.get("kind") == ["BOOKING"])
                if kind == "work"
                else [(k, k) for k in self.facet_rows[0]]
                if self.facet_rows
                else self.model.columns
                if self.column_states.get(scope)
                else [("info", "Žádné záznamy")]
            )
            if scope == 2:
                cols = [("original_name", "Soubor"), ("started_at", "Čas načtení"), ("status_label", "Stav"), ("result_text", "Výsledek")]
            if scope == 8:
                cols = payment_columns(False)
            self.restoring_selection = True
            self.model.replace(self.rows, cols)
            draft_ids = {r.get("id") for r in self.pair_panel.draft_rows}
            self.model.set_bold_ids([r.get("id") for r in self.rows if r.get("id") in draft_ids])
            self.total = value["total"]
            self.empty_hint.setVisible(
                scope == 0 and self.total == 0 and not self.search.text()
            )
            self.all_ids = value["ids"]
            self.page_label.setText(
                f"{self.page * 500 + 1 if self.total else 0}–{min((self.page + 1) * 500, self.total)} / {self.total}"
            )
            if kind == "work":
                self.kpi.setText(
                    "Celá databáze před filtrem:  "
                    + "   |   ".join(
                        f"{cur}: potřeba {display_money(v['need'])} · přebytek {display_money(v['surplus'])} · kořeny {v['roots']}"
                        for cur, v in value["kpi"].items()
                    )
                )
            else:
                self.kpi.setText(
                    "Pomocná data slouží k identifikaci, nikdy jako finanční krytí."
                    if scope == 3
                    else ""
                )
            hidden = len(set(self.selection) - set(self.all_ids))
            totals = value.get("selection_totals", {}) if kind == "work" else {}
            summary = " · ".join(
                display_money(v) + " " + cur for cur, v in totals.items()
            )
            self.selection_label.setText(
                f"Výběr: {len(self.selection)} · mimo filtr: {hidden} · rozdíl {summary}"
            )
            self.table.verticalScrollBar().setValue(scroll)
            for i, r in enumerate(self.rows):
                if r.get("id") in selected:
                    self.table.selectionModel().select(
                        self.model.index(i, 0),
                        QItemSelectionModel.Select | QItemSelectionModel.Rows,
                    )
            layout_key = (scope, tuple(key for key, _ in cols))
            if getattr(self, "displayed_layout", None) != layout_key:
                self.table.horizontalHeader().blockSignals(True)
                for i in range(len(cols)):
                    self.table.setColumnHidden(i, False)
                if state:
                    self.table.horizontalHeader().restoreState(
                        QByteArray.fromBase64(state.encode())
                    )
                else:
                    for i in range(len(cols)):
                        self.table.setColumnWidth(
                            i,
                            (
                                [
                                    100,
                                    85,
                                    125,
                                    110,
                                    140,
                                    180,
                                    100,
                                    115,
                                    85,
                                    115,
                                    185,
                                    180,
                                ][i]
                                if kind == "work"
                                else 165
                            ),
                        )
                self.table.horizontalHeader().blockSignals(False)
                if kind == 'work' and not state:
                    from kajovokarty.ui.models import compact_payment_columns
                    compact_payment_columns(self.table)
                self.displayed_layout = layout_key
            if kind == "work":
                hide_payment_columns(self.table, cols)
            self.restoring_selection = False
            self.table.column_controller.refresh(sort_order)
            self.registry.refresh()
            self.group_detail.setVisible(scope == 8)
            if scope == 8:
                self.show_selected_group_detail()

        self.run(query, done, False,
                 error_handler=lambda error: self.show_error(error) if revision == self.query_revision else None)

    @staticmethod
    def filter_catalog_rows(rows, filters, sort, page):
        from kajovokarty.domain.columns import filter_rows

        filtered = filter_rows(rows, filters, sort)
        page = min(page, max(0, (len(filtered) - 1) // 500))
        return {
            "rows": filtered[page * 500 : (page + 1) * 500],
            "total": len(filtered),
            "page": page,
            "ids": [r["id"] for r in filtered if "id" in r],
            "base_rows": rows,
        }

    def set_column_filter(self, field, selected):
        state = self.column_states.setdefault(self.scope, {})
        if field is None:
            state.clear()
        elif selected is None:
            state.pop(field, None)
        else:
            state[field] = list(selected)
        self.result_selection = None
        if self.scope == 4 and self.candidate_context is not None:
            self.pair_panel.candidate_model.set_column_filter(field, selected)
            self.pair_panel.candidate_table.column_controller.refresh()
        self.page = 0
        self.refresh()

    def set_column_sort(self, sort):
        self.sort_order = list(sort)
        self.page = 0
        self.refresh()

    def column_options(self, field, done):
        from kajovokarty.domain.columns import filter_options

        scope = self.scope
        f = self.filters()
        history = self.global_history
        rows = list(self.facet_rows)
        if scope == 4 and self.candidate_context is not None:
            done(filter_options(rows, field, f.get('column_filters')))
            return

        def query(progress):
            if scope in (0, 1, 4):
                if scope == 4 and history:
                    all_rows = self.work.query(
                        {**f, "column_filters": {}}, page_size=0
                    )["rows"]
                    all_rows += self.catalog.global_matches(f.get("text", ""))
                    return filter_options(all_rows, field, f.get("column_filters"))
                return self.work.query({**f, "_facet": field})["facets"]
            return filter_options(rows, field, f.get("column_filters"))

        self.run(
            query, lambda options: done(options) if self.scope == scope else None, False
        )

    def advanced_filters(self):
        d = QDialog(self)
        d.setWindowTitle("Další filtry — všechna vyplněná pole platí současně")
        layout = QVBoxLayout(d)
        form = QFormLayout()
        layout.addLayout(form)
        widgets = {}
        labels = {
            "invoice_code": "Doklad FA",
            "cashbook_number": "Pokladní číslo",
            "booking_reference": "Booking reference",
            "payout_id": "Payout ID",
            "seq_id": "SEQ",
            "terminal_id": "Terminál",
            "authorization_code": "Autorizace",
            "arn": "ARN",
            "variable_symbol": "VS",
            "variable_symbol_2": "VS 2",
            "amount": "Přesná částka",
            "amount_min": "Částka od",
            "amount_max": "Částka do",
        }
        for key, label in labels.items():
            value = self.advanced.get(key)
            w = QLineEdit(
                decimal_money(value)
                if key.startswith("amount") and value is not None
                else "; ".join(value)
                if isinstance(value, list)
                else str(value or "")
            )
            widgets[key] = w
            form.addRow(label, w)
        source_boxes = {}
        for label, kind in SOURCE_NAMES.items():
            box = QCheckBox(label)
            box.setChecked(kind in self.advanced.get("kind", []))
            source_boxes[kind] = box
            form.addRow(box)
        kind_mode = QComboBox()
        kind_mode.addItems(["Libovolný vybraný zdroj", "Všechny vybrané zdroje"])
        kind_mode.setCurrentIndex(int(self.advanced.get("kind_mode") == "all"))
        form.addRow("Zdroje", kind_mode)
        side = QComboBox()
        side.addItems(["Všechny strany", "Potřeba", "Přebytek", "Vyrovnáno"])
        form.addRow("Strana", side)
        reasons = QLineEdit("; ".join(self.advanced.get("reason", [])))
        form.addRow("Kódy důvodů (oddělit ;)", reasons)
        types = QComboBox()
        types.addItems(["Všechny objekty", "Položky", "Skupiny"])
        form.addRow("Typ objektu", types)
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Reset
        )
        buttons.accepted.connect(d.accept)
        buttons.rejected.connect(d.reject)
        buttons.button(QDialogButtonBox.Reset).clicked.connect(
            lambda: [w.clear() for w in widgets.values()]
        )
        layout.addWidget(buttons)
        if d.exec():
            try:
                values = {
                    k: money(w.text())
                    if k.startswith("amount")
                    else [v.strip() for v in w.text().split(";") if v.strip()]
                    for k, w in widgets.items()
                    if w.text().strip()
                }
                if types.currentIndex():
                    values["type"] = "SOURCE" if types.currentIndex() == 1 else "GROUP"
                selected_kinds = [k for k, w in source_boxes.items() if w.isChecked()]
                if selected_kinds:
                    values["kind"] = selected_kinds
                    values["kind_mode"] = "all" if kind_mode.currentIndex() else "any"
                    self.source.setCurrentIndex(0)
                if side.currentIndex():
                    values["side"] = ["", "NEED", "SURPLUS", "BALANCED"][
                        side.currentIndex()
                    ]
                if reasons.text().strip():
                    values["reason"] = [
                        v.strip() for v in reasons.text().split(";") if v.strip()
                    ]
                self.advanced = values
                self.page = 0
                self.refresh()
            except AppError as e:
                self.show_error(e)

    def persist_columns(self, *args):
        self.view_timer.start()

    def save_columns(self):
        state = bytes(self.table.horizontalHeader().saveState().toBase64()).decode()
        scope = self.scope
        self.run(
            lambda p: self.catalog.save_view("columns:compact-v1:" + str(scope), state),
            mutating=False,
        )

    def turn_page(self, delta):
        self.page = max(0, min(max(0, (self.total - 1) // 500), self.page + delta))
        self.refresh()

    def selected_rows(self):
        return [
            self.rows[i.row()]
            for i in self.table.selectionModel().selectedRows()
            if i.row() < len(self.rows)
        ]

    def selected_ids(self):
        if self.result_selection is not None:
            return list(self.result_selection)
        return [r["id"] for r in self.selected_rows() if "id" in r]

    def action_allowed(self, id):
        if id in ("undo", "redo", "detail", "note", "dissolve") and isinstance(
            QApplication.focusWidget(), (QLineEdit, QPlainTextEdit)
        ):
            return False
        if self.busy and id not in (
            "find",
            "refresh",
            "detail",
            "copy",
            "copy_all",
            "audit_object",
        ):
            return False
        if not hasattr(self, "table"):
            return id in ("import", "auto", "find", "refresh")
        rows = self.selected_rows()
        if id in ("detail", "copy", "copy_all", "audit_object"):
            return bool(rows)
        if id in ("select", "counterparts"):
            return bool(rows) and all(
                r.get("type") in ("SOURCE", "GROUP")
                and not r.get("resolved")
                and r.get("lifecycle") == "ACTIVE"
                for r in rows
            )
        if id in ("note", "dissolve"):
            return (
                len(rows) == 1
                and rows[0].get("type") == "GROUP"
                and rows[0].get("lifecycle") == "ACTIVE"
            )
        if id == "add_group":
            return bool(rows) and all(
                r.get("type") in ("SOURCE", "GROUP")
                and r.get("lifecycle") == "ACTIVE"
                for r in rows
            )
        if id == "group":
            return len(self.selection) >= 2 or (
                len(rows) >= 2
                and all(
                    r.get("type") in ("SOURCE", "GROUP") and not r.get("resolved")
                    for r in rows
                )
            )
        return True

    def selection_changed(self, *args):
        if self.restoring_selection:
            return
        self.result_selection = None
        if self.scope == 8:
            self.show_selected_group_detail()
        self.registry.refresh()

    def highlight_all(self):
        self.restoring_selection = True
        self.table.selectAll()
        self.result_selection = (
            list(self.all_ids)
            if self.scope in (0, 1, 4)
            else [r["id"] for r in self.rows if "id" in r]
        )
        self.restoring_selection = False
        self.status.setText(
            f"Označeno všech {len(self.result_selection)} řádků aktuálního výsledku."
        )

    def toggle_selection(self):
        ids = self.selected_ids()
        if not ids:
            return
        remove = all(i in self.selection for i in ids)
        self.run(
            lambda p: self.work.deselect(ids) if remove else self.work.select(ids),
            self.after_mutation,
        )

    def copy_rows(self, all_values=False):
        if all_values:
            text = "\n".join(
                "\t".join(str(r.get(k) or "") for k, label in self.model.columns)
                for r in self.selected_rows()
            )
        else:
            text = "\n".join(
                str(
                    r.get("primary_identifier")
                    or r.get("external_id")
                    or r.get("id")
                    or r.get("run_id")
                    or ""
                )
                for r in self.selected_rows()
            )
        QApplication.clipboard().setText(text)

    def can_start_drag(self):
        if self.busy:
            return False
        if self.result_selection is not None and len(self.result_selection) > len(
            self.model.rows
        ):
            self.status.setText(
                "Výběr přesahuje stránku. Pro hromadné vytvoření skupiny použijte pracovní výběr; přetažení není částečně provedeno."
            )
            return False
        return True

    def open_selected_pairing(self):
        # Selection in the work table never changes the global draft.
        return

    def open_pairing(self, identity):
        self.pair_dock.show()

    def drop_group(self, payload, target):
        if self.busy or payload.get("workspace") != self.workspace_id:
            return
        rows = payload["rows"]
        if target and (
            target.get("type") not in ("SOURCE", "GROUP")
            or target.get("lifecycle") != "ACTIVE"
        ):
            self.show_error(
                AppError(
                    "SELECTION_INVALID", "Párovat lze pouze aktuální finanční objekty."
                )
            )
            return
        ids = [r["id"] for r in rows]
        revisions = {r["id"]: r["revision"] for r in rows}
        parents = {
            r["id"]: [r["parent_id"], r["parent_revision"]]
            for r in rows
            if r.get("parent_id")
        }
        if target and target.get("parent_id"):
            parents[target["id"]] = [target["parent_id"], target["parent_revision"]]
        self.run(
            lambda p: self.pairing.move(
                ids,
                revisions,
                target=target["id"] if target else None,
                target_revision=target["revision"] if target else None,
                parent_revisions=parents,
            ),
            self.pairing_done,
        )

    def add_transfer_to_draft(self, rows):
        draft_revision = self.pair_panel.draft_revision
        view_revision = self.live_view_revision
        def current():
            return (draft_revision == self.pair_panel.draft_revision
                    and view_revision == self.live_view_revision)
        def done(resolved):
            if not current():
                return
            currencies = {r.get('currency') for r in self.pair_panel.draft_rows + resolved}
            if len(currencies) > 1:
                self.show_error(AppError('MIXED_CURRENCY', 'Nelze spojit různé měny.'))
                return
            self.pair_dock.show()
            self.pair_panel.add_rows(resolved)
        self.run(lambda p: self.pairing.resolve_draft_rows(rows), done, False,
                 error_handler=lambda error: self.show_error(error) if current() else None)

    def panel_drop(self, payload, target):
        if self.busy or payload.get('workspace') != self.workspace_id:
            return
        rows = payload.get('rows', [])
        if target == 'remove':
            ids = {r.get('id') for r in rows}
            panel = self.pair_panel
            panel.draft_rows = [r for r in panel.draft_rows if r.get('id') not in ids]
            panel.current = panel.draft_rows[0] if panel.draft_rows else None
            panel.model.replace(panel.draft_rows)
            panel.dirty = True
            panel._update_summary()
            return
        self.add_transfer_to_draft(rows)


    def pairing_done(self, result):
        if hasattr(self, "pair_panel"):
            self.pair_panel.dirty = False
            self.pair_panel.clear_draft()
        self.after_mutation(result)
        self.status.setText(f"Uloženo {result.get('moved', 0)} plateb. Zpět: Ctrl+Z.")

    def drop_new_group(self, payload):
        rows = payload.get("rows", [])
        if rows and not self.busy and payload.get('workspace') == self.workspace_id:
            self.add_transfer_to_draft(rows)
            self.status.setText("Položky byly přidány do pracovního návrhu. Uložte skupiny.")

    def detach_panel_members(self):
        if self.pair_panel.remove_selected_draft():
            self.status.setText("Označené položky byly vyjmuty z pracovního návrhu. Uložte skupiny.")

    def allow_panel_auto(self):
        if self.pair_panel.current:
            identity = self.pair_panel.current["id"]
            self.run(
                lambda p: self.pairing.allow_previous_auto(identity),
                self.after_mutation,
            )

    def unpair_panel(self):
        r = self.pair_panel.current
        if r and r["type"] == "GROUP" and not r.get("parent_id"):
            self.drop_group({"workspace": self.workspace_id, "rows": [r]}, None)

    def select_all(self):
        if self.scope not in (0, 4):
            return
        ids = list(self.all_ids)
        self.run(lambda p: self.work.select(ids), self.after_mutation)

    def after_mutation(self, result=None):
        self.live_view_revision += 1
        self.invalidate_candidates(refresh=False)
        if hasattr(self, "pair_panel"):
            self.pair_panel.clear_candidates()
        self.status.setText("Operace dokončena.")
        self.refresh()

    def add_selection(self):
        rows = self.selected_rows()
        if rows:
            self.pair_dock.show()
            self.pair_panel.add_rows(rows)
            self.status.setText(f"Do párovací plochy přidáno: {len(rows)}. Změny uložte tlačítkem Uložit skupiny.")

    def add_drag_to_panel(self, payload, target):
        if self.busy or payload.get("workspace") != self.workspace_id:
            return
        rows = list(payload.get("rows", []))
        if target and target.get("id") not in {r.get("id") for r in rows}:
            rows.append(target)
        self.add_transfer_to_draft(rows)

    def save_panel_draft(self):
        panel = self.pair_panel
        rows = list(panel.draft_rows)
        if len(rows) < 2:
            self.show_error(AppError("GROUP_INVALID", "Párovací plocha potřebuje alespoň dvě položky."))
            return
        paired = [r for r in rows if r.get("resolved") and r.get("type") == "GROUP"]
        if paired:
            old = "\n".join(
                f"• {r.get('primary_identifier', r.get('id'))} ({r.get('leaf_count', '?')} plateb)"
                for r in paired
            )
            new = "\n".join(
                f"• {r.get('primary_identifier', r.get('id'))}"
                for r in rows
            )
            answer = QMessageBox.question(
                self,
                "Přestavět spárování",
                "Uložením se rozpustí původní skupiny:\n\n"
                + old
                + "\n\nVznikne nová skupina:\n\n"
                + new
                + "\n\nChcete pokračovat?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
        self.run(lambda p: self.pairing.save_draft(rows), self.pairing_done)

    def find_panel_candidates(self):
        if not self.pair_panel.current:
            self.status.setText("Nejprve přidejte položku do párovací plochy.")
            return
        anchor = self.pair_panel.current
        include_paired = self.pair_panel.include_paired.isChecked()
        view_revision = self.live_view_revision
        self.candidate_request += 1
        request = self.candidate_request
        draft_revision = self.pair_panel.draft_revision
        context = (anchor['id'], anchor['revision'], include_paired)
        def current():
            return (request == self.candidate_request and view_revision == self.live_view_revision
                    and draft_revision == self.pair_panel.draft_revision)
        self.run(lambda p: self.work.candidates(anchor["id"], anchor["revision"], include_paired),
                 lambda rows: self.show_candidate_rows(rows, view_revision, context) if current() else None,
                 False, error_handler=lambda error: self.show_error(error) if current() else None)

    def invalidate_candidates(self, refresh=True):
        active = self.candidate_context is not None
        self.candidate_request += 1
        self.candidate_context = None
        self.candidate_rows = None
        self.query_revision += 1
        self.pair_panel.clear_candidates()
        if active and self.scope == 4 and refresh:
            self.refresh()

    def candidate_filter_changed(self, field, selected):
        if self.scope == 4 and self.candidate_context is not None:
            self.set_column_filter(field, selected)

    def show_candidate_rows(self, rows, view_revision=None, context=None):
        if view_revision is not None and view_revision != self.live_view_revision:
            return
        self.pair_panel.show_candidates(rows, reset_sources=True)
        self.candidate_context = context
        self.candidate_rows = list(rows)
        self.column_states[4] = dict(self.pair_panel.candidate_model.column_filters)
        self.view_sorts[4] = []  # Preserve the service's proximity ranking.
        self.nav.setCurrentRow(4)
        self.sort_order = []
        self.refresh()
        self.status.setText(f"Nalezeno kandidátů: {len(rows)}. Nejbližší shody jsou nahoře.")

    def toggle_combined_groups(self):
        self.combined_groups_only = not getattr(self, "combined_groups_only", False)
        self.refresh()

    def show_selected_group_detail(self):
        if self.scope != 8:
            return
        rows = self.selected_rows()
        if len(rows) != 1 or rows[0].get("type") != "GROUP":
            self.group_detail_title.setText("Vyberte skupinu")
            self.group_detail_model.replace([])
            return
        identity = rows[0]["id"]
        view_revision = self.live_view_revision

        def done(data):
            if self.scope != 8 or view_revision != self.live_view_revision:
                return
            group = data["object"]
            self.group_detail_title.setText(
                f"{group['primary_identifier']} · {group['leaf_count']} plateb · rozdíl {display_money(group['difference'])} {group['currency']}"
            )
            self.group_detail_model.replace(data["rows"])

        self.run(lambda p: self.pairing.panel(identity), done, False)

    def clear_selection(self):
        self.run(lambda p: self.work.select([], clear=True), self.after_mutation)

    def group_dialog(self):
        highlighted = set(self.selected_ids())

        def preview(progress):
            rows = self.work.query({"status": "unresolved"}, page_size=0)["rows"]
            return (
                self.work.selection()
                or {r["id"]: r["revision"] for r in rows if r["id"] in highlighted}
            ), rows

        def show(result):
            selection, rows = result
            chosen = [r for r in rows if r["id"] in selection]
            if len(chosen) != len(selection) or any(
                r["revision"] != selection[r["id"]] for r in chosen
            ):
                self.show_error(
                    AppError("STALE_STATE", "Pracovní výběr obsahuje změněný objekt.")
                )
                return
            if len(chosen) < 2:
                self.show_error(
                    AppError(
                        "GROUP_INVALID",
                        "Do pracovního výběru přidejte alespoň dvě položky.",
                    )
                )
                return
            currencies = {r["currency"] for r in chosen}
            if len(currencies) != 1:
                self.show_error(AppError("MIXED_CURRENCY", "CZK a EUR nelze spojit."))
                return
            diff = checked(sum(r["difference"] for r in chosen))
            d = QDialog(self)
            d.setWindowTitle("Náhled finanční skupiny")
            layout = QVBoxLayout(d)
            layout.addWidget(
                QLabel(
                    f"{len(chosen)} přímých dětí · rozdíl {display_money(diff)} {next(iter(currencies))}\nVýsledek: "
                    + ("Vyřízeno" if diff == 0 else "Nevyřízeno — otevřená skupina")
                )
            )
            details = QPlainTextEdit()
            details.setReadOnly(True)
            details.setPlainText(
                "\n".join(
                    r["primary_identifier"] + "  " + display_money(r["difference"])
                    for r in chosen
                )
            )
            layout.addWidget(details)
            note = QLineEdit()
            note.setPlaceholderText("Volitelná poznámka")
            layout.addWidget(note)
            buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            buttons.button(QDialogButtonBox.Ok).setText(
                "Spárovat" if diff == 0 else "Vytvořit otevřenou skupinu"
            )
            buttons.accepted.connect(d.accept)
            buttons.rejected.connect(d.reject)
            layout.addWidget(buttons)
            if d.exec():
                # Capture widgets while still in the GUI thread and before the
                # dialog can be destroyed; workers receive only plain values.
                note_value = note.text()
                self.run(
                    lambda p: self.work.create_group(
                        list(selection), selection, note_value
                    ),
                    self.after_mutation,
                )

        self.run(preview, show, False)

    def add_group_dialog(self):
        self.add_selection()

    def choose_import(self, kind=None):
        if self.busy:
            return
        if kind not in SOURCE_NAMES.values():
            name, ok = QInputDialog.getItem(
                self, "Typ importu", "Zdroj:", list(SOURCE_NAMES), 0, False
            )
            if not ok:
                return
            kind = SOURCE_NAMES[name]
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Vyberte jeden nebo více CSV souborů z Bookingu" if kind == "BOOKING" else "Vyberte úplné exportní soubory",
            self.settings.get().get("imports.last_directory." + kind, ""),
            "Booking CSV (*.csv)" if kind == "BOOKING" else "Exporty (*.xls *.xlsx *.csv)",
        )
        if paths:
            self.settings.save(
                {"imports.last_directory." + kind: str(Path(paths[0]).parent)}
            )
            self.preflight([ImportInput(kind, p) for p in paths])

    def preflight(self, inputs):
        if self.busy or not inputs:
            return
        from threading import Event
        from kajovokarty.application.import_batch import ImportBatchService
        from kajovokarty.ui.import_progress import ImportProgressDialog
        self.cancel.clear()
        dialog = ImportProgressDialog(self, self.cancel)
        self.import_dialog = dialog
        dialog.show()
        dialog.raise_()
        service = ImportBatchService(self.db)

        def execute(progress):
            def choose_sheet(name, sheets):
                request = dict(sheet_request=True, name=name, sheets=sheets, ready=Event(), answer=None)
                progress(request)
                while not request["ready"].wait(0.1):
                    if self.cancel.is_set():
                        return None
                return request["answer"]
            return service.run(inputs, self.settings.get()["imports.max_megabytes"],
                               self.cancel, progress, choose_sheet)

        def completed(reports):
            self.after_mutation()
            dialog.finish(reports)
            self.status.setText(dialog.windowTitle())

        def failed(error):
            self.after_mutation()
            dialog.finish(getattr(service, "reports", []), error)
            self.status.setText(error.user_message)

        self.run(execute, completed, error_handler=failed, progress_handler=dialog.update_progress)

    def booking_import_queue(self, inputs):
        self.preflight(inputs)

    def import_preview(self, preview):
        from kajovokarty.application.import_messages import reason, counter_text
        ambiguous = [e for e in preview.diagnostics if e["code"] == "SHEET_AMBIGUOUS"]
        if ambiguous:
            from dataclasses import replace

            choices = {}
            for error in ambiguous:
                sheet, ok = QInputDialog.getItem(
                    self,
                    "Výběr listu",
                    str(error.get("file") or "Soubor"),
                    error["details"]["sheets"],
                    0,
                    False,
                )
                if not ok:
                    self.imports.discard(preview.id)
                    return
                choices[error.get("file_id")] = sheet
            inputs = [
                replace(f.request, sheet=choices.get(f.file_id, f.request.sheet))
                for f in preview.files
            ]
            self.imports.discard(preview.id)
            QTimer.singleShot(0, lambda: self.preflight(inputs))
            return
        d = QDialog(self)
        d.setWindowTitle("Náhled importu — dosud nepotvrzeno")
        d.resize(940, 650)
        layout = QVBoxLayout(d)
        errors = [e for e in preview.diagnostics if e.get("severity") == "ERROR"]
        summary = QLabel(
            f"Import nelze dokončit: {len(errors)} chyb. Žádné nové položky ani vazby nebyly uloženy."
            if errors else "Toto je náhled. Položky se uloží až tlačítkem Importovat."
        )
        summary.setObjectName("importOutcomeSummary")
        summary.setWordWrap(True)
        if errors:
            d.setWindowTitle("Import nelze dokončit — nalezeny chyby")
            summary.setStyleSheet("color:#a13235;font-weight:bold")
        layout.addWidget(summary)
        layout.addWidget(
            QLabel(
                f"Připravené nové: {preview.new} · známé: {preview.known} · součty připravených řádků: "
                + ", ".join(
                    display_money(v) + " " + k for k, v in preview.totals.items()
                )
            )
        )
        if any(f.request.kind == "ACCOUNTS" for f in preview.files):
            layout.addWidget(QLabel(f"Účty: nové vazby {preview.accounts['new']} · duplicity {preview.accounts['known']} · konflikty {preview.accounts['conflicts']} · neúplné řádky {preview.accounts['incomplete']}"))
        box = QPlainTextEdit()
        box.setReadOnly(True)
        box.setPlainText(
            "\n".join(
                ("CHYBA" if e.get("severity") == "ERROR" else "UPOZORNĚNÍ")
                + " · " + str(e.get("file") or "")
                + (f" · řádek {e['row_start']}" if e.get("row_start") else "")
                + ": " + reason(e) + " (" + e["code"] + ")"
                for e in preview.diagnostics
            )
            + "\n\nPodrobnosti souborů:\n"
            +
            "\n".join(
                f.name
                + " · "
                + ("Uložená kopie" if f.request.source_file_id else "Vybraný soubor")
                + "\n"
                + counter_text(f.parsed.counters if f.parsed else {})
                for f in preview.files
            )

        )
        layout.addWidget(box)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Importovat")
        buttons.button(QDialogButtonBox.Ok).setEnabled(preview.valid)
        buttons.accepted.connect(d.accept)
        buttons.rejected.connect(d.reject)
        layout.addWidget(buttons)
        if d.exec():
            # The result signal arrives before worker.finished. Queue the commit.
            QTimer.singleShot(
                0,
                lambda: self.run(
                    lambda p: self.imports.commit(
                        preview.id,
                        {f.file_id: f.sha256 for f in preview.files},
                        self.cancel,
                    ),
                    self.import_completed,
                ),
            )
        else:
            self.imports.discard(preview.id)
            self.status.setText(
                "Import selhal: žádné nové položky ani vazby nebyly uloženy. Podrobnosti jsou v Importech."
                if errors else "Import zrušen: žádné nové položky ani vazby nebyly uloženy."
            )
            self.refresh()

    def import_completed(self, result):
        self.after_mutation(result)
        self.status.setText(f"Import dokončen. Nově uloženo: {result['new']} · již známé: {result['known']}.")

    def repeat_import(self):
        rows = self.selected_rows()
        if not rows:
            return
        r = rows[0]
        if not r.get("file_id"):
            return
        kind, ok = QInputDialog.getItem(
            self, "Zopakovat uložený import", "Zdroj:", list(SOURCE_NAMES), 0, False
        )
        if ok:
            self.preflight(
                [
                    ImportInput(
                        SOURCE_NAMES[kind],
                        source_file_id=r["file_id"],
                        original_run_id=r["run_id"],
                        original_name=r["original_name"],
                        sheet=r["sheet_name"] or None,
                    )
                ]
            )

    def save_original(self):
        rows = self.selected_rows()
        if rows and rows[0].get("file_id"):
            r = rows[0]
            path, _ = QFileDialog.getSaveFileName(
                self, "Uložit původní soubor", r["original_name"]
            )
            if path:
                self.run(
                    lambda p: self.catalog.original(r["file_id"], path),
                    self.after_mutation,
                )

    def start_auto(self):
        if self.busy:
            return
        from kajovokarty.ui.auto_progress import AutoProgressDialog

        dialog = AutoProgressDialog(self, self.cancel_operation)
        self.auto_progress = dialog
        dialog.show()

        def completed(result):
            dialog.finish()
            from kajovokarty.ui.auto_result import show_result

            self.after_mutation(result)
            show_result(self, result)
            self.status.setText(
                f"Automatika: {result['newly_resolved_leaves']} nově vyřízených položek v {result['created_groups']} skupinách; {result['rounds']} kol. Výsledek je uložen v detailu operace."
            )

        def interrupted(error):
            dialog.finish()
            from kajovokarty.ui.auto_result import show_result

            self.after_mutation()
            result = error.details.get("auto_result")
            if result:
                show_result(self, result, error)
                self.status.setText(error.user_message)
            else:
                self.show_error(error)

        self.run(
            lambda p: self.matching.run(self.cancel, p),
            completed,
            error_handler=interrupted,
            progress_handler=dialog.update_progress,
        )

    def open_detail(self, *args):
        rows = self.selected_rows()
        if not rows:
            return
        r = rows[0]
        if r.get("resource_type"):
            self.helper_dialog(r)
        elif self.scope in (0, 1, 4):
            self.run(
                lambda p: self.work.evidence(r["id"]),
                lambda e: self.detail_dialog(
                    {**e, "matched_leaf_ids": r.get("matched_leaves", [])}
                ),
                False,
            )
        elif self.scope == 7 and r.get("type") == "AUTO_MATCH":

            def load(progress):
                with self.db.connect() as c:
                    return dict(
                        c.execute(
                            "SELECT * FROM operation WHERE id=?", (r["id"],)
                        ).fetchone()
                    )

            def show(operation):
                from kajovokarty.ui.auto_result import show_result

                result = json.loads(operation["recovery_json"])
                error = json.loads(operation["safe_error_json"] or "{}")
                if result.get("operation_id"):
                    show_result(
                        self,
                        result,
                        AppError(error["code"], error["message"]) if error else None,
                    )
                else:
                    text_dialog(self, "Detail běhu automatiky", canonical(operation))

            self.run(load, show, False)
        elif self.scope == 2 and r.get("run_id") and r.get("file_id"):
            self.run(
                lambda p: self.catalog.import_detail(r["run_id"], r["file_id"]),
                lambda detail: text_dialog(self, "Výsledek importu", detail),
                False,
            )
        elif self.scope == 3:
            text_dialog(self, "Vazba z Účtů", json.dumps(r, ensure_ascii=False, indent=2))
        else:
            text_dialog(
                self, "Detail záznamu", json.dumps(r, ensure_ascii=False, indent=2)
            )

    def helper_dialog(self, r):
        d = QDialog(self)
        d.setWindowTitle("Pomocná entita — pouze identifikace")
        d.resize(900, 600)
        layout = QVBoxLayout(d)
        label = QLabel(
            "Připojení: "
            + r["context_id"]
            + "\nGenerace: "
            + r["generation_id"]
            + "\n"
            + (
                "Aktivní pomocná entita"
                if r["active"]
                else "V úplném načtení nezjištěna — nepoužitelná pro nové párování"
            )
        )
        label.setWordWrap(True)
        layout.addWidget(label)
        box = QPlainTextEdit()
        box.setReadOnly(True)
        box.setPlainText(
            json.dumps(json.loads(r["payload_json"]), ensure_ascii=False, indent=2)
        )
        layout.addWidget(box)
        layout.addWidget(button("Zavřít", d.accept))
        d.exec()

    def detail_dialog(self, e):
        d = QDialog(self)
        d.resize(1000, 680)
        d.setWindowTitle("Důkaz " + e["object"]["id"])
        layout = QVBoxLayout(d)
        layout.addWidget(
            QLabel(
                f"Rozdíl {display_money(e['difference'])} {e['object']['currency']} · počet plateb {len(e['leaves'])}"
            )
        )
        from kajovokarty.ui.evidence_tree import EvidenceTree, EvidenceItem, RAW_ROLE

        tree = EvidenceTree()
        tree.setHeaderLabels(["Jedinečný list", "Zdroj", "Původní částka", "Měna"])
        tree.setAccessibleName("Listy finančního důkazu")
        sources = {source["id"]: source for source in e["leaves"]}
        children = e.get("tree_children", {})
        if not children and e.get("edges"):
            for edge in e["edges"]:
                children.setdefault(edge["parent_id"], []).append(edge["child_id"])
        pending = [(e["object"]["id"], None)]
        while pending:
            identity, parent = pending.pop()
            source = sources.get(identity)
            item = EvidenceItem(
                [
                    source["primary_identifier"],
                    source["kind"],
                    display_money(source["signed_amount_minor"]),
                    source["currency"],
                ]
                if source
                else [
                    "Skupina G" + identity[:10],
                    "Podskupina" if parent else "Kořen",
                    "",
                    e["object"]["currency"],
                ]
            )
            item.setData(0, Qt.UserRole, identity)
            for col, raw in enumerate(
                [
                    source["primary_identifier"] if source else "G" + identity[:10],
                    source["kind"] if source else "GROUP",
                    source["signed_amount_minor"] if source else None,
                    e["object"]["currency"],
                ]
            ):
                item.setData(col, RAW_ROLE, raw)
            if parent:
                parent.addChild(item)
            else:
                tree.addTopLevelItem(item)
            if identity in e.get("matched_leaf_ids", []):
                item.setText(0, "Nalezeno: " + item.text(0))
                item.setSelected(True)
            pending.extend(
                (child, item) for child in reversed(children.get(identity, []))
            )
        tree.enable_filters()
        tree.expandToDepth(2)
        tree.itemDoubleClicked.connect(
            lambda item, column: self.run(
                lambda p: self.work.evidence(item.data(0, Qt.UserRole)),
                self.detail_dialog,
                False,
            )
        )
        layout.addWidget(tree)
        box = QPlainTextEdit()
        box.setReadOnly(True)
        box.setPlainText(json.dumps(e, ensure_ascii=False, indent=2))
        layout.addWidget(box)
        buttons = QHBoxLayout()
        if e.get("parent"):

            def unlink():
                d.accept()

                def execute(progress):
                    return self.work.unlink_parent(
                        e["object"]["id"], e["parent_revision"]
                    )

                if (
                    QMessageBox.question(
                        self,
                        "Rozpojit rodiče",
                        "Rozložit přímé nadřazené párování a uvolnit jeho děti?",
                    )
                    == QMessageBox.Yes
                ):
                    self.run(execute, self.after_mutation)

            buttons.addWidget(button("Rozpojit nadřazené párování", unlink))
        buttons.addWidget(
            button(
                "Kopírovat ID",
                lambda: QApplication.clipboard().setText(e["object"]["id"]),
            )
        )
        if e["object"]["type"] == "GROUP":
            buttons.addWidget(
                button(
                    "Exportovat důkaz",
                    lambda: self.export_dialog("group_evidence", [e["object"]["id"]]),
                )
            )
            proof = json.loads(e["group"]["evidence_json"])
            finger = proof.get("fingerprint")
            if finger:
                buttons.addWidget(
                    button(
                        "Znovu povolit automatické spojení",
                        lambda: (
                            d.accept(),
                            self.run(
                                lambda p: self.work.allow_auto(finger),
                                self.after_mutation,
                            ),
                        ),
                    )
                )
        if e["object"]["type"] == "SOURCE":
            buttons.addWidget(
                button(
                    "Původní řádky",
                    lambda: self.run(
                        lambda p: self.catalog.source_origin(e["object"]["id"]),
                        lambda rs: text_dialog(
                            self,
                            "Původní řádky",
                            json.dumps(rs, ensure_ascii=False, indent=2),
                        ),
                        False,
                    ),
                )
            )
        buttons.addWidget(button("Zavřít", d.accept))
        layout.addLayout(buttons)
        d.exec()

    def dissolve_selected(self):
        rows = self.selected_rows()
        if not rows or rows[0].get("type") != "GROUP":
            return
        r = rows[0]
        self.drop_group({"workspace": self.workspace_id, "rows": [r]}, None)

    def edit_note(self):
        rows = self.selected_rows()
        if not rows or rows[0].get("type") != "GROUP":
            return
        r = rows[0]
        note, ok = QInputDialog.getMultiLineText(
            self, "Poznámka", "Volitelná poznámka:", r.get("note") or ""
        )
        if ok:
            self.run(
                lambda p: self.work.edit_note(r["id"], r["revision"], note),
                self.after_mutation,
            )

    def counterparts(self):
        selected = self.selected_rows()
        if len(selected) != 1 or selected[0].get("type") not in ("SOURCE", "GROUP"):
            self.show_error(
                AppError(
                    "SELECTION_INVALID", "Označte jeden nevyřízený finanční kořen."
                )
            )
            return
        anchor = selected[0]
        view_revision = self.live_view_revision

        def show(rows):
            if view_revision != self.live_view_revision:
                return
            d = QDialog(self)
            d.setWindowTitle("Možné protějšky · " + anchor["primary_identifier"])
            d.resize(1050, 620)
            layout = QVBoxLayout(d)
            layout.addWidget(
                QLabel(
                    "Ruční výběr ve stejné měně. Nulový součet sám o sobě nedokládá automatickou shodu."
                )
            )
            table = WorkTable()
            table.workspace = self.workspace_id
            table.groupDropped.connect(
                lambda payload, target: (d.accept(), self.drop_group(payload, target))
            )
            table.dropHint.connect(self.status.setText)
            model = TableModel(
                rows, payment_columns()
            )
            table.setModel(model)
            hide_payment_columns(table, model.columns)
            table.setSelectionBehavior(QAbstractItemView.SelectRows)
            table.setSelectionMode(QAbstractItemView.ExtendedSelection)
            layout.addWidget(table)

            def add():
                ids = [anchor["id"]] + [
                    model.rows[i.row()]["id"]
                    for i in table.selectionModel().selectedRows()
                ]
                if len(ids) > 1:
                    d.accept()
                    self.run(lambda p: self.work.select(ids), self.after_mutation)

            layout.addWidget(
                button("Přidat zvolené protějšky do pracovního výběru", add)
            )
            layout.addWidget(button("Zavřít", d.accept))
            d.exec()

        self.run(
            lambda p: self.work.counterparts(anchor["id"], anchor["revision"]),
            show,
            False,
        )

    def export_dialog(self, report=None, ids=None):
        from kajovokarty.ui.export_dialog import export_dialog

        export_dialog(self, report, ids)

    def settings_dialog(self):
        from kajovokarty.ui.settings_dialog import settings_dialog

        settings_dialog(self)

    def apply_appearance(self):
        prefs = self.settings.get()
        self.setFont(
            QFont("Segoe UI", max(8, round(10 * prefs["ui.text_scale"] / 100)))
        )
        self.table.verticalHeader().setDefaultSectionSize(
            round(
                {"compact": 26, "normal": 34, "comfortable": 44}[
                    prefs["ui.row_density"]
                ]
                * prefs["ui.text_scale"]
                / 100
            )
        )
        self.table.setProperty("highContrast", prefs["ui.high_contrast"])
        self.setStyleSheet(
            self.base_stylesheet
            + (
                " QWidget {color:#000;background:#fff;} QTableView {selection-background-color:#000;selection-color:#fff;} QPushButton:focus,QLineEdit:focus {border:2px solid #000;}"
                if prefs["ui.high_contrast"]
                else ""
            )
        )
        self.model.high_contrast = prefs["ui.high_contrast"]
        self.model.warning_age_days = prefs["matching.warning_age_days"]
        # The desktop uses no custom animations; this also disables Qt menu/tooltip effects.
        for effect in (
            Qt.UI_AnimateMenu,
            Qt.UI_FadeMenu,
            Qt.UI_AnimateTooltip,
            Qt.UI_FadeTooltip,
        ):
            QApplication.setEffectEnabled(effect, not prefs["ui.reduce_motion"])

    def backup_dialog(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Vytvořit zálohu",
            str(
                Path(self.settings.get()["data.backup_directory"])
                / "KajovoKarty-zaloha.zip"
            ),
            "Záloha (*.zip)",
        )
        if path:
            self.run(lambda p: self.backup.backup(path), self.after_mutation)

    def restore_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Obnovit zálohu",
            self.settings.get()["data.backup_directory"],
            "Záloha (*.zip)",
        )
        if not path:
            return

        def confirm(manifest):
            if (
                QMessageBox.warning(
                    self,
                    "Obnova kompletních dat",
                    f"Záloha z {manifest['created_at']} · schéma {manifest['schema']}.\nPozdější změny budou nahrazeny. Před obnovou vznikne bezpečnostní záloha současných dat. Pokračovat?",
                    QMessageBox.Yes | QMessageBox.No,
                )
                == QMessageBox.Yes
            ):
                self.run(lambda p: self.backup.restore(path), self.after_mutation)

        self.run(lambda p: self.backup.inspect(path)[0], confirm, False)

    def diagnostic_dialog(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Anonymní diagnostika", "KajovoKarty-diagnostika.zip", "ZIP (*.zip)"
        )
        if path:
            self.run(lambda p: self.backup.diagnostic(path), self.after_mutation)

    def help_dialog(self):
        text_dialog(
            self,
            "Nápověda",
            "1. Importovat → zvolit zdroj a soubory → průběh → výsledek → Hotovo.\n2. Importovat Účty (XLS): Variabilní symbol, Číslo rezervace a Original ID.\n3. Spustit automatické párování výslovným tlačítkem.\n4. Ručně: přetáhnout platbu na protějšek nebo skupinu. Přetažení mění pracovní návrh; potvrďte jej tlačítkem Uložit skupinu. CZK a EUR nelze spojit. Rozdíl musí být přesně nula pro Vyřízeno.\n5. Skupiny mají přímé platební členy, ne podskupiny. Ctrl+Z / Ctrl+Y vrací platné příkazy. Import se nevrací.\n6. Každý sloupec: šipka v záhlaví otevře filtr hodnot; kliknutí na název přepíná řazení. Sestavy: CSV jako ZIP, XLSX, PDF.\n7. Zálohy obsahují také importované vazby z Účtů.\n\nKlávesy: Ctrl+I import, Ctrl+F hledání, Ctrl+Space výběr, Ctrl+M skupina, Enter detail, F2 poznámka, F5 místní obnova.\n\nVerze 0.4.5. Automatika spojuje dvojice i vyrovnané součtové skupiny. Tolerance je dva pracovní dny bez víkendů a českých svátků. Booking přes Účty má přednost. Storno pokladny lze započíst s opačnou částkou do dvou kalendářních dnů. V Nastavení najdete přehled chyb a upozornění.",
        )

    def save_filter(self):
        name, ok = QInputDialog.getText(self, "Uložit filtr", "Název:")
        if ok:
            try:
                f = self.filters()
            except AppError as e:
                self.show_error(e)
                return
            scope, sort = str(self.scope), list(self.sort_order)
            self.run(
                lambda p: self.catalog.save_filter(name, scope, f, sort),
                self.after_mutation,
            )

    def load_filter(self):
        def show(rows):
            if not rows:
                return
            name, ok = QInputDialog.getItem(
                self, "Načíst filtr", "Filtr:", [r["name"] for r in rows], 0, False
            )
            if ok:
                saved = next(r for r in rows if r["name"] == name)
                action, confirmed = QInputDialog.getItem(
                    self,
                    "Uložený filtr",
                    name,
                    ["Použít", "Přejmenovat", "Odstranit"],
                    0,
                    False,
                )
                if not confirmed:
                    return
                if action == "Přejmenovat":
                    new_name, ok = QInputDialog.getText(
                        self, "Přejmenovat filtr", "Nový název:", text=name
                    )
                    if ok:
                        self.run(
                            lambda p: self.catalog.rename_filter(saved["id"], new_name),
                            self.after_mutation,
                        )
                    return
                if action == "Odstranit":
                    if (
                        QMessageBox.question(
                            self, "Odstranit filtr", f"Odstranit uložený filtr {name}?"
                        )
                        == QMessageBox.Yes
                    ):
                        self.run(
                            lambda p: self.catalog.delete_filter(saved["id"]),
                            self.after_mutation,
                        )
                    return
                scope = (
                    NAV.index(saved["scope"])
                    if saved["scope"] in NAV
                    else int(saved["scope"])
                )
                self.nav.setCurrentRow(scope)
                f = json.loads(saved["filter_json"])
                self.column_states[self.scope] = f.pop("column_filters", {})
                self.sort_order = json.loads(saved["sort_json"]) or [("date", "asc")]
                self.advanced = {
                    k: v
                    for k, v in f.items()
                    if k
                    not in (
                        "text",
                        "currency",
                        "date_from",
                        "date_to",
                        "status",
                        "kind",
                    )
                }
                self.source.setCurrentIndex(0)
                if f.get("kind"):
                    self.advanced["kind"] = f["kind"]
                self.search.setText(f.get("text", ""))
                self.currency.setCurrentText((f.get("currency") or ["Všechny měny"])[0])
                self.date_from.setText(f.get("date_from", ""))
                self.date_to.setText(f.get("date_to", ""))
                self.refresh()

        self.run(lambda p: self.catalog.filters(), show, False)

    def context_menu(self, pos):
        menu = QMenu(self)
        for key in (
            "detail",
            "select",
            "group",
            "add_group",
            "counterparts",
            "note",
            "dissolve",
            "copy",
            "copy_all",
            "audit_object",
            "export",
        ):
            menu.addAction(self.registry.actions[key])
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def column_menu(self, pos):
        menu = QMenu(self)
        for i, (key, label) in enumerate(self.model.columns):
            if self.scope in (0, 1, 4) and key in HIDDEN_PAYMENT_COLUMNS:
                continue
            action = menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(not self.table.isColumnHidden(i))
            action.toggled.connect(
                lambda checked, index=i: self.table.setColumnHidden(index, not checked)
            )
        menu.exec(self.table.horizontalHeader().mapToGlobal(pos))

    def dragEnterEvent(self, event):
        if WorkTable.decode(event.mimeData(), self.workspace_id):
            event.acceptProposedAction()
            return
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        payload = WorkTable.decode(event.mimeData(), self.workspace_id)
        if payload:
            self.panel_drop(payload, None)
            event.setDropAction(Qt.MoveAction)
            event.accept()
            return
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if not paths:
            return
        name, ok = QInputDialog.getItem(
            self, "Import souborů", "Zdroj:", list(SOURCE_NAMES), 0, False
        )
        if ok:
            self.preflight([ImportInput(SOURCE_NAMES[name], p) for p in paths])

    def stop_background_activity(self):
        self.shutting_down = True
        for timer in self.findChildren(QTimer):
            timer.stop()
        if self.focus_callback is not None:
            QApplication.instance().focusChanged.disconnect(self.focus_callback)
            self.focus_callback = None

    def closeEvent(self, event):
        if self.jobs:
            self.status.setText("Dokončete nebo zrušte běžící operaci před zavřením.")
            event.ignore()
        elif getattr(self, "pair_panel", None) is not None and self.pair_panel.dirty:
            answer = QMessageBox.question(
                self,
                "NevyÄtenĂ© zmÄ›ny",
                "V pĂˇrovacĂ­ ploĹˇe jsou neuloĹľenĂ© zmÄ›ny. UloĹľit pĹ™ed ukonÄenĂ­m?",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                QMessageBox.Save,
            )
            if answer == QMessageBox.Cancel:
                event.ignore()
                return
            if answer == QMessageBox.Save:
                self.save_panel_draft()
                if self.pair_panel.dirty:
                    event.ignore()
                    return
            self.stop_background_activity()
            event.accept()
        else:
            self.stop_background_activity()
            event.accept()
