"""Recovery stays available even when normal repositories cannot open SQLite."""

from pathlib import Path
import sqlite3
from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QFileDialog,
    QMessageBox,
)
from kajovokarty.ui.workers import Job
from kajovokarty.application.workspace import recover_backup, atomic_json


def recovery_dialog(parent, data, pointer, message):
    d = QDialog(parent)
    d.setWindowTitle("Zotavení KájovoKarty")
    d.resize(650, 300)
    layout = QVBoxLayout(d)
    label = QLabel(
        message
        + "\n\nZvolte existující pracovní prostor nebo ověřenou zálohu. Původní data zůstanou uchována."
    )
    label.setWordWrap(True)
    layout.addWidget(label)
    pool = QThreadPool(d)
    workers = []

    def start(fn):
        worker = Job(fn)
        workers.append(worker)
        restore.setEnabled(False)
        locate.setEnabled(False)
        worker.signals.result.connect(lambda result: d.accept())
        worker.signals.error.connect(lambda error: label.setText(error.message))
        worker.signals.finished.connect(
            lambda: (restore.setEnabled(True), locate.setEnabled(True))
        )
        pool.start(worker)

    def restore_backup():
        path, _ = QFileDialog.getOpenFileName(d, "Obnovit zálohu", "", "Záloha (*.zip)")
        if not path:
            return
        if (
            QMessageBox.question(
                d,
                "Obnovit pracovní prostor",
                "Obnova nahradí lokální data stavem zálohy. Poškozené soubory se nejprve uchovají. Pokračovat?",
            )
            != QMessageBox.Yes
        ):
            return

        def execute(progress):
            result = recover_backup(path, data)
            atomic_json(pointer, {"data_directory": result})
            return result

        start(execute)

    def locate_workspace():
        folder = QFileDialog.getExistingDirectory(d, "Existující datová složka")
        if not folder:
            return

        def execute(progress):
            from kajovokarty.domain.core import require

            require(
                (Path(folder) / "kajovokarty.sqlite").is_file(),
                "DATABASE_INVALID",
                "Ve složce není existující databáze.",
            )
            with sqlite3.connect(
                (Path(folder) / "kajovokarty.sqlite").resolve().as_uri() + "?mode=ro",
                uri=True,
            ) as c:
                require(
                    c.execute("PRAGMA quick_check").fetchone()[0] == "ok",
                    "DATABASE_INVALID",
                    "Kontrola databáze neuspěla.",
                )
            atomic_json(pointer, {"data_directory": folder})

        start(execute)

    restore = QPushButton("Obnovit ze zálohy")
    restore.clicked.connect(restore_backup)
    layout.addWidget(restore)
    locate = QPushButton("Vyhledat existující pracovní prostor")
    locate.clicked.connect(locate_workspace)
    layout.addWidget(locate)
    close = QPushButton("Zavřít")
    close.clicked.connect(d.reject)
    layout.addWidget(close)
    for button in (restore, locate, close):
        button.setAccessibleName(button.text())
        button.setToolTip(button.text())
    d.exec()
    pool.waitForDone()
    return d.result() == QDialog.Accepted
