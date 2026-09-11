from PySide6.QtCore import QTimer, QDate
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QFormLayout,
    QScrollArea,
    QWidget,
    QLineEdit,
    QDateEdit,
    QCheckBox,
    QComboBox,
    QSpinBox,
    QLabel,
    QPushButton,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QMessageBox,
    QApplication,
)
from kajovokarty.application.settings import RANGES, DEFAULTS
from kajovokarty.infrastructure.betterhotel import BetterHotelClient
from kajovokarty.domain.core import AppError


class SecretEdit(QLineEdit):
    def __init__(self):
        super().__init__()
        self.setEchoMode(QLineEdit.Password)

    def focusOutEvent(self, event):
        self.setEchoMode(QLineEdit.Password)
        super().focusOutEvent(event)


LABELS = {
    "sync.start_date": "Načítat pomocná data od",
    "sync.block_days": "Dní v synchronizačním bloku",
    "sync.timeout_seconds": "Síťový timeout (sekundy)",
    "sync.retry_count": "Počet opakování síťové chyby",
    "sync.requests_per_second": "Požadavků za sekundu",
    "matching.bank_window_days": "Časové okno banky (dny)",
    "matching.max_combination": "Maximální kombinace automatiky",
    "matching.max_component_items": "Maximální počet vstupů komponenty",
    "matching.max_search_states": "Limit prozkoumaných kombinací",
    "matching.warning_age_days": "Zvýraznění stáří (dny)",
    "imports.max_megabytes": "Limit jednoho souboru (MiB)",
    "backup.daily": "Denní automatická záloha",
    "backup.retention_days": "Uchování automatických záloh (dny)",
    "diagnostics.log_retention_days": "Uchování technických logů (dny)",
    "ui.row_density": "Hustota řádků",
    "ui.text_scale": "Velikost textu (%)",
    "ui.high_contrast": "Vysoký kontrast",
    "ui.reduce_motion": "Omezit animace",
    "network.proxy_url": "Explicitní proxy (volitelné)",
    "data.directory": "Aktuální datová složka",
    "data.backup_directory": "Složka záloh",
    "data.export_directory": "Výchozí složka sestav",
    "imports.last_directory.CASHBOOK_CARD": "Poslední složka pokladny",
    "imports.last_directory.BANK_CARD": "Poslední složka terminálu",
    "imports.last_directory.BOOKING": "Poslední složka Bookingu",
}


def settings_dialog(window):
    d = QDialog(window)
    d.setWindowTitle("Nastavení KájovoKarty")
    d.resize(780, 700)
    outer = QVBoxLayout(d)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    body = QWidget()
    form = QFormLayout(body)
    scroll.setWidget(body)
    outer.addWidget(scroll)
    state = QLabel("Načítám stav připojení…")
    state.setWordWrap(True)
    form.addRow(state)
    window.run(
        lambda p: window.sync.state(),
        lambda s: state.setText(
            f"Připojení: {s['context_id']}\nStav: {s['status']} · poslední úplné načtení: {s['last_full_success_at'] or 'dosud neproběhlo'}"
        ),
        False,
    )
    access, client, username, password = (
        SecretEdit(),
        SecretEdit(),
        QLineEdit(),
        SecretEdit(),
    )
    for label, w in [
        ("Access Token — nahrazení", access),
        ("Client Token — nahrazení", client),
        ("Proxy uživatel — nahrazení", username),
        ("Proxy heslo — nahrazení", password),
    ]:
        w.setAccessibleName(label)
        w.setToolTip(label)
        form.addRow(label, w)
    form.addRow(QLabel("Prázdná přihlašovací pole zachovají uložené hodnoty."))
    show = QPushButton("Dočasně zobrazit vyplněná tajemství")

    hide_secrets = QTimer(d)
    hide_secrets.setSingleShot(True)
    hide_secrets.timeout.connect(
        lambda: [w.setEchoMode(QLineEdit.Password) for w in (access, client, password)]
    )

    def reveal():
        for w in (access, client, password):
            w.setEchoMode(QLineEdit.Normal)
        hide_secrets.start(10000)

    show.clicked.connect(reveal)
    form.addRow(show)
    error = QLabel()
    error.setWordWrap(True)
    error.setStyleSheet("color:#a13235")
    outer.addWidget(error)
    widgets = {}
    values = window.settings.get()
    for key, value in values.items():
        if key not in LABELS:
            continue
        if key == "sync.start_date":
            w = QDateEdit(QDate.fromString(value, "yyyy-MM-dd"))
            w.setCalendarPopup(True)
            w.setDisplayFormat("d. M. yyyy")
            w.setMaximumDate(QDate.currentDate())
        elif key in RANGES:
            w = QSpinBox()
            w.setRange(*RANGES[key])
            w.setValue(value)
        elif isinstance(value, bool):
            w = QCheckBox()
            w.setChecked(value)
        elif key == "ui.row_density":
            w = QComboBox()
            w.addItems(["compact", "normal", "comfortable"])
            w.setCurrentText(value)
        else:
            w = QLineEdit(str(value))
        widgets[key] = w
        w.setAccessibleName(LABELS[key])
        w.setToolTip(LABELS[key])
        if key.startswith("data.") or key.startswith("imports.last_directory."):
            row = QWidget()
            layout = QHBoxLayout(row)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(w)
            if key == "data.directory":
                w.setReadOnly(True)
            else:
                pick = QPushButton("Vybrat…")
                pick.setAccessibleName("Vybrat " + LABELS[key])
                layout.addWidget(pick)

                def choose(checked=False, edit=w):
                    folder = QFileDialog.getExistingDirectory(
                        d, "Vybrat složku", edit.text()
                    )
                    if folder:
                        edit.setText(folder)

                pick.clicked.connect(choose)
            form.addRow(LABELS[key], row)
        else:
            form.addRow(LABELS[key], w)
        if key == "sync.start_date":
            hint = QLabel(
                "Do dneška včetně. Zahrnou se pobyty, které do období alespoň částečně "
                "zasahují. Změna se použije při příštím úplném načtení. "
                "API může vrátit širší seznam; rezervace mimo období se dále nezpracují."
            )
            hint.setWordWrap(True)
            form.addRow(hint)

    def current_values():
        return {
            k: w.date().toString("yyyy-MM-dd")
            if isinstance(w, QDateEdit)
            else w.value()
            if isinstance(w, QSpinBox)
            else w.isChecked()
            if isinstance(w, QCheckBox)
            else w.currentText()
            if isinstance(w, QComboBox)
            else w.text()
            for k, w in widgets.items()
        }

    def fail(e):
        details = e.details or {}
        error.setText(
            e.message
            + "\n"
            + "\n".join(LABELS.get(k, k) + ": " + str(v) for k, v in details.items())
            if isinstance(details, dict)
            else e.message
        )

    def saved(result):
        window.apply_appearance()
        d.accept()
        window.after_mutation()

    def save():
        pair = (
            (access.text(), client.text()) if access.text() or client.text() else None
        )
        proxy = (
            (username.text(), password.text())
            if username.text() or password.text()
            else None
        )
        updated = current_values()
        window.run(
            lambda p: window.settings.save_all(updated, pair, proxy),
            saved,
            error_handler=fail,
        )

    def test():
        a, b = access.text().strip(), client.text().strip()
        settings = current_values()
        proxy = (
            (username.text(), password.text())
            if username.text() or password.text()
            else None
        )

        def execute(progress):
            aa, bb = (a, b) if a or b else window.settings.tokens()
            http = BetterHotelClient(
                aa,
                bb,
                settings,
                window.cancel,
                proxy_auth=proxy or window.settings.proxy_auth(),
            )
            try:
                return len(http.collection("/currency"))
            finally:
                http.close()

        window.run(
            execute,
            lambda n: error.setText(
                f"GET /currency uspěl ({n} měn). Ostatní endpointy tím nejsou ověřeny."
            ),
            error_handler=fail,
        )

    def compatible():
        if access.text() or client.text():
            fail(
                AppError(
                    "SETTING_INVALID",
                    "Před ověřením kompatibility nejprve uložte změněnou dvojici tokenů.",
                )
            )
            return
        d.accept()
        window.start_sync(True)

    def reset():
        for k, w in widgets.items():
            if k in ("data.directory", "sync.start_date"):
                continue
            value = DEFAULTS[k]
            if isinstance(w, QSpinBox):
                w.setValue(value)
            elif isinstance(w, QCheckBox):
                w.setChecked(value)
            elif isinstance(w, QComboBox):
                w.setCurrentText(value)
            else:
                w.setText(str(value))

    def move():
        target = QFileDialog.getExistingDirectory(d, "Cílová prázdná datová složka")
        if not target:
            return
        if (
            QMessageBox.question(
                d,
                "Přesun pracovního prostoru",
                f"Přesunout data do {target} a restartovat aplikaci? Původní kopie zůstane zachována.",
            )
            != QMessageBox.Yes
        ):
            return
        from kajovokarty.application.workspace import WorkspaceService

        pointer = getattr(
            window.db,
            "workspace_pointer",
            window.db.path.parent.parent / "workspace.json",
        )

        def moved(result):
            d.accept()
            window.status.setText("Přesun ověřen. Restartuji…")
            QTimer.singleShot(0, lambda: QApplication.exit(23))

        window.run(
            lambda p: WorkspaceService(window.db, pointer).move(target),
            moved,
            error_handler=fail,
        )

    for label, fn in [
        ("Test připojení", test),
        ("Ověřit kompatibilitu uloženého připojení", compatible),
        (
            "Odstranit uložené tokeny",
            lambda: window.run(
                lambda p: window.settings.save_tokens("", ""),
                lambda r: error.setText("Tokeny odstraněny."),
                error_handler=fail,
            ),
        ),
        (
            "Odstranit proxy přihlášení",
            lambda: window.run(
                lambda p: window.settings.save_proxy("", ""),
                lambda r: error.setText("Proxy přihlášení odstraněno."),
                error_handler=fail,
            ),
        ),
        ("Obnovit výchozí volby ve formuláři", reset),
        (
            "Resetovat rozložení tabulek",
            lambda: window.run(
                lambda p: window.catalog.reset_views(),
                lambda r: window.refresh(),
                error_handler=fail,
            ),
        ),
        ("Přesunout pracovní prostor a restartovat", move),
    ]:
        button = QPushButton(label)
        button.setAccessibleName(label)
        button.setToolTip(label)
        button.clicked.connect(fn)
        form.addRow(button)
    buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
    buttons.accepted.connect(save)
    buttons.rejected.connect(d.reject)
    outer.addWidget(buttons)
    d.exec()
