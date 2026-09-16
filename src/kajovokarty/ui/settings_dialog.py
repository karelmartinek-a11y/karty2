from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QFormLayout,
    QScrollArea,
    QWidget,
    QLineEdit,
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
    QPlainTextEdit,
)
from kajovokarty.application.settings import RANGES, DEFAULTS


LABELS = {
    "matching.business_window_days": "Tolerance párování (pracovní dny, české svátky)",
    "matching.warning_age_days": "Zvýraznění stáří (dny)",
    "imports.max_megabytes": "Limit jednoho souboru (MiB)",
    "backup.daily": "Denní automatická záloha",
    "backup.retention_days": "Uchování automatických záloh (dny)",
    "diagnostics.log_retention_days": "Uchování technických logů (dny)",
    "ui.row_density": "Hustota řádků",
    "ui.text_scale": "Velikost textu (%)",
    "ui.high_contrast": "Vysoký kontrast",
    "ui.reduce_motion": "Omezit animace",
    "data.directory": "Aktuální datová složka",
    "data.backup_directory": "Složka záloh",
    "data.export_directory": "Výchozí složka sestav",
    "imports.last_directory.CASHBOOK_CARD": "Poslední složka pokladny",
    "imports.last_directory.BANK_CARD": "Poslední složka terminálu",
    "imports.last_directory.BOOKING": "Poslední složka Bookingu",
    "imports.last_directory.ACCOUNTS": "Poslední složka Účtů",
}


def confirm_full_reset(parent):
    dialog = QDialog(parent)
    dialog.setObjectName("confirmFullReset")
    dialog.setWindowTitle("Resetovat celý program")
    layout = QVBoxLayout(dialog)
    text = QLabel(
        "Nenávratně se vymažou všechny platby, importy, pomocná data, spárování, "
        "historie, přihlašovací údaje a nastavení.\n\n"
        "Vymažou se také rozpoznané zálohy, diagnostika a staré provozní záznamy "
        "ve složkách aplikace a v nastavené složce záloh. Nová záloha nevznikne.\n\n"
        "Původní vstupní soubory mimo aplikaci a uložené exporty zůstanou zachované. "
        "Aplikace se restartuje prázdná ve stejné datové složce.\n\n"
        "Pro potvrzení napište VYMAZAT:"
    )
    text.setWordWrap(True)
    layout.addWidget(text)
    entry = QLineEdit()
    entry.setObjectName("resetConfirmation")
    entry.setAccessibleName("Pro potvrzení napište VYMAZAT")
    layout.addWidget(entry)
    buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
    buttons.button(QDialogButtonBox.Cancel).setText("Zrušit")
    erase = buttons.addButton("Vymazat vše a restartovat", QDialogButtonBox.AcceptRole)
    erase.setObjectName("confirmErase")
    erase.setEnabled(False)
    erase.setAutoDefault(False)
    buttons.button(QDialogButtonBox.Cancel).setDefault(True)
    entry.textChanged.connect(lambda value: erase.setEnabled(value == "VYMAZAT"))
    buttons.accepted.connect(lambda: dialog.accept() if entry.text() == "VYMAZAT" else None)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    dialog.resize(540, 330)
    return dialog.exec() == QDialog.Accepted


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
    catalogue = QPushButton("Přehled chyb a upozornění")
    catalogue.setObjectName("errorCatalogue")
    def show_catalogue():
        from kajovokarty.domain.errors import CATALOG
        dialog = QDialog(d)
        dialog.setWindowTitle("Přehled chyb a upozornění")
        dialog.resize(800, 600)
        layout = QVBoxLayout(dialog)
        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setPlainText("\n\n".join(f"{code} — {item.name}\n{item.description}\nCo udělat: {item.action}"
                                      for code, item in sorted(CATALOG.items())))
        layout.addWidget(text)
        close = QDialogButtonBox(QDialogButtonBox.Close)
        close.rejected.connect(dialog.reject)
        layout.addWidget(close)
        dialog.exec()
    catalogue.clicked.connect(show_catalogue)
    outer.addWidget(catalogue)
    error = QLabel()
    error.setWordWrap(True)
    error.setStyleSheet("color:#a13235")
    outer.addWidget(error)
    widgets = {}
    values = window.settings.get()
    for key, value in values.items():
        if key not in LABELS or key.startswith(("sync.", "network.")):
            continue
        if key in RANGES:
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

    def current_values():
        return {
            k: w.value()
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
            e.user_message
            + "\n"
            + "\n".join(LABELS.get(k, k) + ": " + str(v) for k, v in details.items())
            if isinstance(details, dict)
            else e.user_message
        )

    def saved(result):
        window.apply_appearance()
        d.accept()
        window.after_mutation()

    def save():
        updated = current_values()
        window.run(lambda p: window.settings.save_all(updated), saved, error_handler=fail)

    def reset():
        for k, w in widgets.items():
            if k == "data.directory":
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

    def full_reset():
        from kajovokarty.domain.core import AppError
        from kajovokarty.application.reset import RESET_EXIT

        if window.jobs or window.busy:
            fail(AppError("RESET_BUSY", "Probíhá jiná operace."))
            return
        if not confirm_full_reset(d):
            return
        # The modal confirmation processes events: check for newly started jobs.
        if window.jobs or window.busy:
            fail(AppError("RESET_BUSY", "Probíhá jiná operace."))
            return
        window.stop_background_activity()
        window.setEnabled(False)
        d.accept()
        QApplication.exit(RESET_EXIT)

    for label, fn in [
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
    erase = QPushButton("Resetovat celý program")
    erase.setObjectName("resetApplication")
    erase.setAccessibleName("Resetovat celý program")
    erase.setStyleSheet("QPushButton { color: #a02020; border-color: #a02020; }")
    erase.setToolTip("Vymazat všechna data, zálohy a nastavení a restartovat prázdnou aplikaci.")
    erase.clicked.connect(full_reset)
    form.addRow(erase)
    buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
    buttons.accepted.connect(save)
    buttons.rejected.connect(d.reject)
    outer.addWidget(buttons)
    d.exec()
