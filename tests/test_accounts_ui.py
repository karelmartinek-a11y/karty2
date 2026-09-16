import os
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication, QFileDialog, QPushButton

from kajovokarty.ui.main import MainWindow, SOURCE_NAMES
from test_accounts import SAMPLE
from test_gui import spin


def test_manual_accounts_import_preview_and_helper_table(db, monkeypatch):
    app = QApplication.instance() or QApplication([])
    QFontDatabase.addApplicationFont(str(SAMPLE.parent / "src/kajovokarty/assets/DejaVuSans.ttf"))
    window = MainWindow(db)
    errors = []
    window.show_error = errors.append
    window.show()
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *args, **kwargs: ([str(SAMPLE)], ""))
    try:
        spin(lambda: not window.jobs)
        assert "ACCOUNTS" in SOURCE_NAMES.values()
        assert "sync" not in window.registry.actions
        window.choose_import("ACCOUNTS")
        spin(lambda: window.import_dialog.completed and not window.jobs)
        result = window.import_dialog.details.toPlainText()
        window.import_dialog.accept()
        window.nav.setCurrentRow(3)
        spin(lambda: not window.jobs and bool(window.model.rows))
        assert not errors
        assert "Vazby Účtů" in result and "Neúplné řádky" in result
        assert {"Variabilní symbol", "Číslo rezervace", "Original ID"} <= set(window.model.rows[0])
        assert not any("BetterHotel" in b.text() for b in window.findChildren(QPushButton))
        if os.environ.get("ACCOUNTS_QA_SCREENSHOT"):
            window.grab().save(os.environ["ACCOUNTS_QA_SCREENSHOT"])
    finally:
        spin(lambda: not window.jobs)
        window.view_timer.stop()
        window.close()
        app.processEvents()
