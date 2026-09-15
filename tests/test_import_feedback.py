import csv
import io
import json

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QLabel, QPlainTextEdit

from kajovokarty.application.catalog import CatalogService
from kajovokarty.application.imports import ImportInput, ImportService
from kajovokarty.ui.main import MainWindow
from test_gui import spin


def invalid_booking(tmp_path, fixtures):
    rows = list(csv.reader(io.StringIO((fixtures / "booking_a.csv").read_text("utf-8-sig"))))
    rows[1][9] = "invalid_amount"
    path = tmp_path / "booking_invalid.csv"
    with path.open("w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows(rows)
    return path


def test_invalid_preview_reports_no_writes_and_persists_failure(db, tmp_path, fixtures):
    app = QApplication.instance() or QApplication([])
    window = MainWindow(db)
    window.show()
    spin(lambda: not window.jobs)
    preview = window.imports.preflight([ImportInput("BOOKING", str(invalid_booking(tmp_path, fixtures)))])
    assert not preview.valid and preview.new > 0
    checked, failures = [], []

    def inspect():
        dialog = next(d for d in window.findChildren(QDialog) if d.isVisible())
        try:
            summary = dialog.findChild(QLabel, "importOutcomeSummary").text()
            assert "Import nelze dokončit" in summary
            assert "nebyly uloženy" in summary
            assert not dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok).isEnabled()
            text = dialog.findChild(QPlainTextEdit).toPlainText()
            assert text.startswith("CHYBA") and "řádek 2" in text
            assert text.index("MONEY_INVALID") < text.index("Podrobnosti souborů")
            checked.append(True)
        except Exception as error:
            failures.append(error)
        finally:
            dialog.reject()

    QTimer.singleShot(0, inspect)
    try:
        window.import_preview(preview)
        spin(lambda: not window.jobs)
        assert checked and not failures, failures
        assert "Import selhal" in window.status.text()
        with db.connect() as c:
            row = c.execute("SELECT state,safe_error_json FROM operation WHERE id=?", (preview.id,)).fetchone()
            assert row["state"] == "FAILED"
            assert json.loads(row["safe_error_json"])["code"] == "IMPORT_INVALID"
            assert c.execute("SELECT count(*) FROM financial_source").fetchone()[0] == 0
        detail = CatalogService(db).import_detail(preview.id, preview.files[0].file_id)
        assert "nebyly uloženy" in detail and "Částku platby se nepodařilo přečíst" in detail
    finally:
        window.view_timer.stop()
        window.close()
        app.processEvents()


def test_valid_cancel_and_legacy_invalid_history(db, tmp_path, fixtures):
    imports = ImportService(db)
    preview = imports.preflight([ImportInput("BOOKING", str(fixtures / "booking_a.csv"))])
    imports.discard(preview.id)
    with db.connect() as c:
        assert c.execute("SELECT state FROM operation WHERE id=?", (preview.id,)).fetchone()[0] == "CANCELLED"
    invalid = imports.preflight([ImportInput("BOOKING", str(invalid_booking(tmp_path, fixtures)))])
    imports.discard(invalid.id)
    with db.connect() as c:
        c.execute("UPDATE operation SET state='CANCELLED',safe_error_json=NULL WHERE id=?", (invalid.id,))
    detail = CatalogService(db).import_detail(invalid.id, invalid.files[0].file_id)
    assert "Import nebyl dokončen" in detail and "Částku platby se nepodařilo přečíst" in detail
