"""Real file selection, automatic commit and acknowledged result for every non-Booking import adapter."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QFileDialog

from kajovokarty.ui.main import MainWindow
from test_gui import spin


@pytest.mark.parametrize("kind,filename,expected", [
    ("CASHBOOK_CARD", "cashbook_week.xls", 9),
    ("BANK_CARD", "terminal.xlsx", 56),
    ("BANK_CARD", "terminal_synthetic.xls", 1),
    ("BANK_CARD", "terminal_synthetic.csv", 1),
])
def test_real_import_adapter_through_dialog(db, fixtures, monkeypatch, kind, filename, expected):
    app = QApplication.instance() or QApplication([])
    window = MainWindow(db)
    errors = []
    window.show_error = errors.append
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *args, **kwargs: ([str(fixtures / filename)], ""))
    try:
        window.show()
        spin(lambda: not window.jobs)
        window.choose_import(kind)
        spin(lambda: window.import_dialog.completed and not window.jobs and not window.busy
             and window.model.rowCount() == expected, seconds=20)
        assert window.import_dialog.isVisible()
        assert window.import_dialog.button.text() == "Hotovo"
        window.import_dialog.button.click()
        assert not errors
        with db.connect() as c:
            assert c.execute("SELECT count(*) FROM financial_source").fetchone()[0] == expected
            assert c.execute("SELECT state FROM operation WHERE type='IMPORT'").fetchone()[0] == "COMPLETED"
            assert c.execute("SELECT count(*) FROM operation WHERE type='AUTO_MATCH'").fetchone()[0] == 0
    finally:
        spin(lambda: not window.jobs, seconds=20)
        window.view_timer.stop()
        window.close()
        app.processEvents()
