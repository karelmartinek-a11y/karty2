from __future__ import annotations
from pathlib import Path
import json, threading
from PySide6.QtCore import Qt, QThreadPool, QTimer, QByteArray, QItemSelectionModel
from PySide6.QtGui import QFont, QIcon, QPainter, QPixmap, QColor
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
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
    QTreeWidget,
    QTreeWidgetItem,
)
from kajovokarty.domain.core import (
    AppError,
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
from kajovokarty.application.sync import SyncService
from kajovokarty.application.matching import MatchingService
from kajovokarty.application.backup import BackupService
from kajovokarty.application.catalog import CatalogService
from kajovokarty.application.reports import ReportService
from kajovokarty.infrastructure.betterhotel import BetterHotelClient
from kajovokarty.ui.models import TableModel, WORK_COLUMNS
from kajovokarty.ui.work_table import WorkTable
from kajovokarty.ui.workers import Job
from kajovokarty.ui.actions import ActionSpec, ActionRegistry

NAV = [
    "Nevyřízené",
    "Vyřízené",
    "Importy a BetterHotel",
    "Pomocná data",
    "Vyhledávání",
    "Sestavy",
    "Audit",
    "Nastavení",
]
SOURCE_NAMES = {
    "Pokladna (XLS)": "CASHBOOK_CARD",
    "Terminál (CSV / XLS / XLSX)": "BANK_CARD",
    "Booking.com (CSV)": "BOOKING",
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
    "Ověření BetterHotel": "api_compatibility",
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
        self.imports = ImportService(db)
        self.settings = SettingsService(db)
        self.sync = SyncService(db, self.settings)
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
        self.sort_order = [("date", "asc")]
        self.advanced = {}
        self.helper_inactive = False
        self.global_history = False
        self.helper_history = None
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
        QApplication.instance().focusChanged.connect(
            lambda old, new: self.registry.refresh()
        )
        bar = QToolBar()
        bar.setMovable(False)
        self.addToolBar(bar)
        wordmark = QLabel("  KájovoKarty  ")
        wordmark.setFont(QFont("Segoe UI", 17, QFont.Bold))
        bar.addWidget(wordmark)
        specs = [
            ("import", "Importovat", "Ctrl+I", self.choose_import),
            ("sync", "Načíst BetterHotel", "", self.start_sync),
            ("auto", "Spustit automatické párování", "", self.start_auto),
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
            ("add_group", "Přidat do skupiny", "", self.add_group_dialog),
            ("drop_group", "Přetáhnout do skupiny", "", self.drop_group),
            ("copy", "Kopírovat hlavní ID", "", lambda: self.copy_rows(False)),
            (
                "copy_all",
                "Kopírovat řádky a všechna ID",
                "",
                lambda: self.copy_rows(True),
            ),
            ("audit_object", "Audit objektu", "", self.open_detail),
            ("group", "Vytvořit skupinu / spárovat", "Ctrl+M", self.group_dialog),
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
            ("clear", "Vyčistit výběr", "Ctrl+Shift+Space", self.clear_selection),
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
            if id in ("import", "sync", "auto"):
                bar.addAction(action)
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
        self.source.addItems(["Všechny zdroje", *SOURCE_NAMES])
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
        self.table = WorkTable()
        self.table.allRequested.connect(self.highlight_all)
        self.table.copyRequested.connect(self.copy_rows)
        self.table.groupDropped.connect(
            lambda payload, row: self.registry.invoke("drop_group", payload, row)
        )
        self.table.setModel(self.model)
        self.table.selectionModel().selectionChanged.connect(self.selection_changed)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setAccessibleName("Pracovní tabulka")
        self.table.horizontalHeader().setSectionsMovable(True)
        self.table.horizontalHeader().sectionClicked.connect(self.sort_clicked)
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.doubleClicked.connect(self.open_detail)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.context_menu)
        self.contentlayout.addWidget(self.table, 1)
        self.table.horizontalHeader().setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.horizontalHeader().customContextMenuRequested.connect(
            self.column_menu
        )
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
        bottom.addWidget(button("Přidat označené", self.add_selection))
        bottom.addWidget(button("Vytvořit skupinu / spárovat", self.group_dialog))
        bottom.addWidget(button("Vyčistit", self.clear_selection))
        rootlayout.addLayout(bottom)
        self.status = QLabel("Připraveno")
        self.statusBar().addWidget(self.status, 1)
        self.cancel_button = button("Zrušit operaci", self.cancel_operation)
        self.cancel_button.setEnabled(False)
        self.statusBar().addPermanentWidget(self.cancel_button)
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

    def run(self, fn, done=None, mutating=True, error_handler=None):
        if mutating and self.busy:
            return
        if mutating:
            self.busy = True
            self.cancel.clear()
            self.registry.refresh()
            self.cancel_button.setEnabled(True)
        job = Job(fn)
        self.jobs.add(job)
        job.signals.progress.connect(self.status.setText)
        job.signals.error.connect(error_handler or self.show_error)
        if done:
            job.signals.result.connect(done)

        def finish():
            self.jobs.discard(job)
            if mutating:
                self.busy = False
                self.cancel_button.setEnabled(False)
                self.registry.refresh()

        job.signals.finished.connect(finish)
        self.pool.start(job)

    def show_error(self, e):
        self.status.setText(e.code + " — " + e.message)
        QMessageBox.warning(
            self,
            "Operace nebyla dokončena",
            e.code
            + "\n"
            + e.message
            + ("\n" + canonical(e.details) if e.details else ""),
        )

    def cancel_operation(self):
        self.cancel.set()
        self.status.setText("Ruším — čekám na bezpečné dokončení rozpracovaného kroku.")

    def navigate(self, index):
        self.result_selection = None
        self.scope = index
        self.page = 0
        self.title.setText(NAV[index])
        while self.contextbar.count():
            item = self.contextbar.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        actions = {
            0: [
                ("Najít možné protějšky", self.counterparts),
                ("Přidat výběr do skupiny", self.add_group_dialog),
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
                ("Zopakovat uložený import", self.repeat_import),
                ("Původní soubor", self.save_original),
            ],
            3: [
                ("Úplně načíst BetterHotel", self.start_sync),
                ("Detail a reference", self.open_detail),
                ("Zahrnout / skrýt nezjištěné", self.toggle_inactive),
                ("Historie připojení", self.choose_helper_history),
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
                ("Pokračovat v označeném načítání", self.resume_sync),
                ("Nápověda", self.help_dialog),
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
        f = {
            **self.advanced,
            "text": self.search.text(),
            "status": "resolved"
            if self.scope == 1
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

        def query(progress):
            selection = self.work.selection()
            if scope in (0, 1, 4):
                result = self.work.query(
                    f,
                    sort=sort_order,
                    page=page,
                    page_size=0 if scope == 4 and self.global_history else 500,
                )
                if scope == 4 and self.global_history:
                    extra = self.catalog.global_matches(f.get("text", ""))
                    combined = result["rows"] + extra
                    result["ids"] = [r["id"] for r in combined]
                    result["total"] = len(combined)
                    result["rows"] = combined[page * 500 : (page + 1) * 500]
                return (
                    "work",
                    result,
                    selection,
                    self.catalog.view("columns:" + str(scope)),
                )
            if scope == 2:
                rows = self.catalog.rows("imports")
            elif scope == 3:
                rows = self.sync.entities(
                    self.helper_inactive, *(self.helper_history or (None, None))
                )
                from kajovokarty.domain.core import search_tokens

                tokens = search_tokens(f.get("text", ""))
                rows = [
                    r for r in rows if all(t in r["local_search_text"] for t in tokens)
                ]
            elif scope == 6:
                rows = self.catalog.rows("audit")
            elif scope == 5:
                rows = [{"sestava": k, "report_id": v} for k, v in REPORT_NAMES.items()]
            else:
                rows = self.catalog.rows("operations")
            return (
                "other",
                rows,
                selection,
                self.catalog.view("columns:" + str(scope)),
            )

        def done(result):
            if revision != self.query_revision:
                return
            kind, value, self.selection, state = result
            selected = set(self.selected_ids())
            self.rows = value["rows"] if kind == "work" else value
            scroll = self.table.verticalScrollBar().value()
            cols = (
                WORK_COLUMNS
                if kind == "work"
                else [(k, k) for k in self.rows[0]]
                if self.rows
                else [("info", "Žádné záznamy")]
            )
            self.restoring_selection = True
            self.model.replace(self.rows, cols)
            self.total = value["total"] if kind == "work" else len(self.rows)
            self.empty_hint.setVisible(
                scope == 0 and self.total == 0 and not self.search.text()
            )
            self.all_ids = value["ids"] if kind == "work" else []
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
            self.table.horizontalHeader().blockSignals(True)
            if state:
                self.table.horizontalHeader().restoreState(
                    QByteArray.fromBase64(state.encode())
                )
            else:
                for i in range(len(cols)):
                    self.table.setColumnWidth(
                        i,
                        (
                            [86, 65, 105, 95, 120, 160, 70, 100, 55, 100, 165, 160][i]
                            if kind == "work"
                            else 145
                        ),
                    )
            self.table.horizontalHeader().blockSignals(False)
            self.restoring_selection = False
            self.registry.refresh()

        self.run(query, done, False)

    def sort_clicked(self, column):
        if self.scope not in (0, 1, 4):
            return
        field = self.model.columns[column][0]
        previous = next((d for f, d in self.sort_order if f == field), "desc")
        direction = "desc" if previous == "asc" else "asc"
        self.sort_order = (
            [(f, d) for f, d in self.sort_order if f != field]
            if QApplication.keyboardModifiers() & Qt.ShiftModifier
            else []
        ) + [(field, direction)]
        self.table.horizontalHeader().setSortIndicator(
            column, Qt.AscendingOrder if direction == "asc" else Qt.DescendingOrder
        )
        self.page = 0
        self.refresh()

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
            lambda p: self.catalog.save_view("columns:" + str(scope), state),
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
            return id in ("import", "sync", "auto", "find", "refresh")
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
        if id in ("note", "dissolve", "add_group"):
            return (
                len(rows) == 1
                and rows[0].get("type") == "GROUP"
                and rows[0].get("lifecycle") == "ACTIVE"
            )
        if id == "group":
            return len(self.selection) >= 2
        return True

    def selection_changed(self, *args):
        if not self.restoring_selection:
            self.result_selection = None
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

    def drop_group(self, revisions, group):
        if self.busy:
            return
        ids = [i for i in revisions if i != group["id"]]
        if not ids:
            return
        revisions = {**revisions, group["id"]: group["revision"]}
        if (
            QMessageBox.question(
                self,
                "Přidat do skupiny",
                f"Přidat {len(ids)} kořenů do {group['primary_identifier']}?",
            )
            == QMessageBox.Yes
        ):
            self.run(
                lambda p: self.work.add_to_group(group["id"], ids, revisions),
                self.after_mutation,
            )

    def select_all(self):
        if self.scope not in (0, 4):
            return
        ids = list(self.all_ids)
        self.run(lambda p: self.work.select(ids), self.after_mutation)

    def after_mutation(self, result=None):
        self.status.setText("Operace dokončena.")
        self.refresh()

    def add_selection(self):
        ids = self.selected_ids()
        if ids:
            self.run(lambda p: self.work.select(ids), self.after_mutation)

    def clear_selection(self):
        self.run(lambda p: self.work.select([], clear=True), self.after_mutation)

    def group_dialog(self):
        def preview(progress):
            return self.work.selection(), self.work.query(
                {"status": "unresolved"}, page_size=0
            )["rows"]

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
                self.run(
                    lambda p: self.work.create_group(
                        list(selection), selection, note.text()
                    ),
                    self.after_mutation,
                )

        self.run(preview, show, False)

    def add_group_dialog(self):
        rows = self.selected_rows()
        if len(rows) != 1 or rows[0].get("type") != "GROUP":
            self.show_error(
                AppError("GROUP_INVALID", "Označte jednu otevřenou cílovou skupinu.")
            )
            return
        group = rows[0]

        def preview(progress):
            return self.work.selection()

        def show(selection):
            ids = [i for i in selection if i != group["id"]]
            if not ids:
                self.show_error(
                    AppError("GROUP_INVALID", "Pracovní výběr neobsahuje další kořeny.")
                )
                return
            revisions = {**selection, group["id"]: group["revision"]}
            if (
                QMessageBox.question(
                    self,
                    "Přidat do skupiny",
                    f"Přidat {len(ids)} dalších přímých dětí do skupiny {group['primary_identifier']}?",
                )
                == QMessageBox.Yes
            ):
                self.run(
                    lambda p: self.work.add_to_group(group["id"], ids, revisions),
                    self.after_mutation,
                )

        self.run(preview, show, False)

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
            "Vyberte úplné exportní soubory",
            self.settings.get().get("imports.last_directory." + kind, ""),
            "Exporty (*.xls *.xlsx *.csv)",
        )
        if paths:
            self.settings.save(
                {"imports.last_directory." + kind: str(Path(paths[0]).parent)}
            )
            self.preflight([ImportInput(kind, p) for p in paths])

    def preflight(self, inputs):
        self.run(
            lambda p: self.imports.preflight(
                inputs, self.settings.get()["imports.max_megabytes"], self.cancel, p
            ),
            self.import_preview,
        )

    def import_preview(self, preview):
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
        d.setWindowTitle("Náhled importu — dosud nic finančně nezapsáno")
        d.resize(940, 650)
        layout = QVBoxLayout(d)
        layout.addWidget(
            QLabel(
                f"Nové: {preview.new} · známé: {preview.known} · součty nových řádků: "
                + ", ".join(
                    display_money(v) + " " + k for k, v in preview.totals.items()
                )
            )
        )
        box = QPlainTextEdit()
        box.setReadOnly(True)
        box.setPlainText(
            "\n".join(
                f.name
                + " · "
                + ("STORED_SNAPSHOT" if f.request.source_file_id else "EXTERNAL_FILE")
                + " · "
                + f.sha256
                + "\n"
                + canonical(f.parsed.counters if f.parsed else {})
                for f in preview.files
            )
            + "\n\n"
            + "\n".join(canonical(e) for e in preview.diagnostics)
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
                    self.after_mutation,
                ),
            )
        else:
            self.imports.discard(preview.id)

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

    def toggle_inactive(self):
        self.helper_inactive = not self.helper_inactive
        self.refresh()

    def choose_helper_history(self):
        def show(rows):
            labels = ["Aktuální připojení"] + [
                r["published_at"] + " · " + r["context_id"] + " · " + r["id"]
                for r in rows
            ]
            label, ok = QInputDialog.getItem(
                self, "Historické grafy — pouze prohlížení", "Graf:", labels, 0, False
            )
            if ok:
                index = labels.index(label)
                self.helper_history = (
                    None
                    if index == 0
                    else (rows[index - 1]["context_id"], rows[index - 1]["id"])
                )
                self.refresh()

        self.run(lambda p: self.catalog.rows("generations"), show, False)

    def resume_sync(self):
        rows = self.selected_rows()
        if not rows or rows[0].get("type") != "SYNC":
            self.show_error(
                AppError(
                    "STALE_STATE",
                    "Označte přerušenou operaci SYNC v tabulce Nastavení.",
                )
            )
            return
        op = rows[0]["id"]

        def execute(progress):
            a, b = self.settings.tokens()
            http = BetterHotelClient(
                a,
                b,
                self.settings.get(),
                self.cancel,
                proxy_auth=self.settings.proxy_auth(),
            )
            try:
                return self.sync.resume(http, op, progress)
            finally:
                http.close()

        self.run(execute, self.after_mutation)

    def start_sync(self, compatibility=False):
        if self.busy:
            return

        def confirm(scope):
            if (
                QMessageBox.question(
                    self,
                    "Ověřit kompatibilitu BetterHotel"
                    if compatibility
                    else "Načíst BetterHotel",
                    f"Úplně načíst období {scope[0]} až {scope[1]}? Přerušené načtení se nezpřístupní pro nové automatické vazby.",
                )
                != QMessageBox.Yes
            ):
                return

            def execute(progress):
                access, client = self.settings.tokens()
                http = BetterHotelClient(
                    access,
                    client,
                    self.settings.get(),
                    self.cancel,
                    proxy_auth=self.settings.proxy_auth(),
                )
                try:
                    return self.sync.full(http, compatibility, progress, scope)
                finally:
                    http.close()

            self.run(
                execute,
                lambda r: (
                    self.status.setText("BetterHotel: graf publikován."),
                    self.refresh(),
                ),
            )

        self.run(lambda p: self.sync.scope(), confirm, False)

    def start_auto(self):
        if (
            QMessageBox.question(
                self,
                "Automatické párování",
                "Spustit nad celou databází bez ohledu na filtr?",
            )
            == QMessageBox.Yes
        ):
            self.run(
                lambda p: self.matching.run(self.cancel, p),
                lambda r: (
                    self.status.setText(
                        f"Vytvořeno {r['created_groups']} skupin, kol {r['rounds']}."
                    ),
                    self.refresh(),
                ),
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
        elif self.scope == 3:
            self.helper_dialog(r)
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
        layout.addWidget(
            button("Obnovit tento detail", lambda: (d.accept(), self.refresh_helper(r)))
        )
        if r["resource_type"] == "reservation":
            layout.addWidget(
                button(
                    "Rozhodnutí o Booking referenci",
                    lambda: (d.accept(), self.reference_dialog(r)),
                )
            )
        layout.addWidget(button("Zavřít", d.accept))
        d.exec()

    def refresh_helper(self, r):
        from kajovokarty.application.refresh import RefreshService

        def execute(progress):
            a, b = self.settings.tokens()
            client = BetterHotelClient(
                a,
                b,
                self.settings.get(),
                self.cancel,
                proxy_auth=self.settings.proxy_auth(),
            )
            try:
                return RefreshService(self.db, self.settings).refresh(
                    client, r["resource_type"], r["external_id"], r["context_id"]
                )
            finally:
                client.close()

        self.run(
            execute,
            lambda result: (
                self.refresh(),
                text_dialog(
                    self,
                    "Publikovaný detail"
                    if result["published"]
                    else "Pouze náhled — pro automatiku načtěte celý graf",
                    json.dumps(result["target"], ensure_ascii=False, indent=2),
                ),
            ),
        )

    def reference_dialog(self, r):
        from kajovokarty.application.overrides import OverrideService

        service = OverrideService(self.db)

        def show(result):
            ref = result["reference"]
            previous = result["override"]
            d = QDialog(self)
            d.setWindowTitle("Booking reference")
            layout = QVBoxLayout(d)
            layout.addWidget(QLabel(result["decision"]["resolution_status"]))
            choices = QComboBox()
            choices.addItems(ref["candidates"])
            layout.addWidget(choices)

            def apply(action):
                candidate = choices.currentText() if action == "ACCEPT" else None
                d.accept()
                self.run(
                    lambda p: service.decide(
                        r["context_id"],
                        r["external_id"],
                        action,
                        candidate,
                        previous["revision"] if previous else 0,
                        ref["candidate_set_hash"],
                    ),
                    self.after_mutation,
                )

            accept = button("Potvrdit tuto referenci", lambda: apply("ACCEPT"))
            accept.setEnabled(bool(ref["candidates"]))
            layout.addWidget(accept)
            layout.addWidget(
                button("Odmítnout reference pro automatiku", lambda: apply("REJECT"))
            )
            layout.addWidget(button("Zrušit ruční rozhodnutí", lambda: apply("CLEAR")))
            d.exec()

        self.run(
            lambda p: service.inspect(r["context_id"], r["external_id"]), show, False
        )

    def detail_dialog(self, e):
        d = QDialog(self)
        d.resize(1000, 680)
        d.setWindowTitle("Důkaz " + e["object"]["id"])
        layout = QVBoxLayout(d)
        layout.addWidget(
            QLabel(
                f"Rozdíl {display_money(e['difference'])} {e['object']['currency']} · listů {len(e['leaves'])}"
            )
        )
        tree = QTreeWidget()
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
            item = QTreeWidgetItem(
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
        if (
            QMessageBox.question(
                self,
                "Rozložit skupinu",
                "Uvolnit všechny přímé děti? Vnořené podskupiny zůstanou zachovány.",
            )
            == QMessageBox.Yes
        ):
            self.run(
                lambda p: self.work.dissolve(r["id"], r["revision"]),
                self.after_mutation,
            )

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

        def show(rows):
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
            model = TableModel(
                rows, WORK_COLUMNS + [("pair_difference", "Rozdíl po spojení")]
            )
            table.setModel(model)
            table.setSelectionBehavior(QAbstractItemView.SelectRows)
            table.setSelectionMode(QAbstractItemView.ExtendedSelection)
            layout.addWidget(table)

            def add():
                ids = [anchor["id"]] + [
                    rows[i.row()]["id"] for i in table.selectionModel().selectedRows()
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
            "1. Importovat → zvolit zdroj a úplné exporty → zkontrolovat náhled → Importovat.\n2. Načíst BetterHotel pouze po zadání tokenů v Nastavení.\n3. Spustit automatické párování výslovným tlačítkem.\n4. Ručně: označit kořeny → Přidat označené → Vytvořit skupinu. CZK a EUR nelze spojit. Rozdíl musí být přesně nula pro Vyřízeno.\n5. Rozložení zachová podskupiny. Ctrl+Z / Ctrl+Y vrací platné příkazy. Import se nevrací.\n6. Sestavy: CSV jako ZIP, XLSX s textovými identifikátory, PDF.\n7. Zálohy neobsahují tokeny. Obnova vytvoří nové připojení, pomocná data je třeba úplně načíst.\n\nKlávesy: Ctrl+I import, Ctrl+F hledání, Ctrl+Space výběr, Ctrl+M skupina, Enter detail, F2 poznámka, F5 místní obnova.\n\nVývojová verze 0.2.0 — rozsah ověření a zbývající omezení jsou v docs/VALIDATION.md repozitáře.",
        )

    def save_filter(self):
        name, ok = QInputDialog.getText(self, "Uložit filtr", "Název:")
        if ok:
            try:
                f = self.filters()
            except AppError as e:
                self.show_error(e)
                return
            self.run(
                lambda p: self.catalog.save_filter(
                    name, NAV[self.scope], f, self.sort_order
                ),
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
                self.nav.setCurrentRow(int(saved["scope"]))
                f = json.loads(saved["filter_json"])
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
            action = menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(not self.table.isColumnHidden(i))
            action.toggled.connect(
                lambda checked, index=i: self.table.setColumnHidden(index, not checked)
            )
        menu.exec(self.table.horizontalHeader().mapToGlobal(pos))

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if not paths:
            return
        name, ok = QInputDialog.getItem(
            self, "Import souborů", "Zdroj:", list(SOURCE_NAMES), 0, False
        )
        if ok:
            self.preflight([ImportInput(SOURCE_NAMES[name], p) for p in paths])

    def closeEvent(self, event):
        if self.jobs:
            self.status.setText("Dokončete nebo zrušte běžící operaci před zavřením.")
            event.ignore()
        else:
            event.accept()
