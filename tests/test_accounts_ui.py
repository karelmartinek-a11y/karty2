import os
from PySide6.QtCore import QTimer
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QFileDialog, QLabel, QPushButton

from kajovokarty.ui.main import MainWindow, SOURCE_NAMES
from test_accounts import SAMPLE
from test_gui import spin


def test_manual_accounts_import_preview_and_helper_table(db, monkeypatch):
    app = QApplication.instance() or QApplication([])
    QFontDatabase.addApplicationFont(str(SAMPLE.parent / "src/kajovokarty/assets/DejaVuSans.ttf"))
    window = MainWindow(db)
    errors, previews = [], []
    window.show_error = errors.append
    window.show()
    original = window.import_preview

    def accept():
        dialog = next((d for d in window.findChildren(QDialog) if d.isVisible() and "Náhled importu" in d.windowTitle()), None)
        if dialog:
            previews.append(" ".join(label.text() for label in dialog.findChildren(QLabel)))
            dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok).click()

    def preview(value):
        QTimer.singleShot(0, accept)
        original(value)

    monkeypatch.setattr(window, "import_preview", preview)
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *args, **kwargs: ([str(SAMPLE)], ""))
    try:
        spin(lambda: not window.jobs)
        assert "ACCOUNTS" in SOURCE_NAMES.values()
        assert "sync" not in window.registry.actions
        window.choose_import("ACCOUNTS")
        spin(lambda: previews and not window.jobs)
        window.nav.setCurrentRow(3)
        spin(lambda: not window.jobs and bool(window.model.rows))
        assert not errors
        assert "konflikty" in previews[0] and "neúplné" in previews[0]
        assert {"Variabilní symbol", "Číslo rezervace", "Original ID"} <= set(window.model.rows[0])
        assert not any("BetterHotel" in b.text() for b in window.findChildren(QPushButton))
        if os.environ.get("ACCOUNTS_QA_SCREENSHOT"):
            window.grab().save(os.environ["ACCOUNTS_QA_SCREENSHOT"])
    finally:
        spin(lambda: not window.jobs)
        window.view_timer.stop()
        window.close()
        app.processEvents()
