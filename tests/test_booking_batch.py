import csv
import io
import os
import threading

from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QPlainTextEdit

from kajovokarty.application.booking_import import BookingImportService
from kajovokarty.application.catalog import CatalogService
from kajovokarty.application.import_messages import batch_text
from kajovokarty.application.imports import ImportInput
from kajovokarty.ui.main import MainWindow
from test_gui import spin


def csv_file(fixtures, tmp_path, name, rows):
    source = list(csv.reader(io.StringIO((fixtures / "booking_a.csv").read_text("utf-8-sig"))))
    path = tmp_path / name
    with path.open("w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows([source[0], *rows(source[1:])])
    return path


def test_files_committed_in_order_with_bad_file_between(db, fixtures, tmp_path):
    first = csv_file(fixtures, tmp_path, "leden.csv", lambda r: r[:2])
    bad = tmp_path / "spatny.csv"
    bad.write_text("Chybna,hlavicka\n1,2", encoding="utf-8")
    last = csv_file(fixtures, tmp_path, "unor.csv", lambda r: [r[0], r[2]])
    reports = BookingImportService(db).run([ImportInput("BOOKING", str(p)) for p in (first, bad, last)])
    assert [r["state"] for r in reports] == ["COMPLETED", "FAILED", "COMPLETED"]
    assert [r["added"] for r in reports] == [2, 0, 1]
    assert reports[2]["already_saved"] == 1
    with db.connect() as c:
        assert c.execute("SELECT count(*) FROM financial_source").fetchone()[0] == 3
        assert c.execute("SELECT count(*) FROM operation WHERE type='IMPORT' AND state='RUNNING'").fetchone()[0] == 0
    text = batch_text(reports)
    assert "Načtené platby celkem: 3" in text
    assert "Chybí potřebné názvy sloupců" in text
    assert not any(word in text for word in ("HEADER_INVALID", "known", "duplicity", "sha256"))
    for row in CatalogService(db).rows("imports"):
        detail = CatalogService(db).import_detail(row["run_id"], row["file_id"])
        assert row["original_name"] in detail
        assert "result_text" in row


def test_repeated_file_reports_saved_payments(db, fixtures):
    request = ImportInput("BOOKING", str(fixtures / "booking_a.csv"))
    reports = BookingImportService(db).run([request, request])
    assert reports[0]["added"] == 21
    assert reports[1]["added"] == 0 and reports[1]["already_saved"] == 21
    assert reports[1]["not_loaded"] == 0
    assert "Podruhé jsme je neukládali" in batch_text(reports)


def test_cancel_keeps_completed_files_and_lists_remaining(db, fixtures):
    request = ImportInput("BOOKING", str(fixtures / "booking_a.csv"))
    stop = threading.Event()
    def progress(message):
        if message.startswith("Načítám soubor 2"):
            stop.set()
    reports = BookingImportService(db).run([request, request, request], cancel=stop, progress=progress)
    assert [r["state"] for r in reports] == ["COMPLETED", "CANCELLED", "NOT_STARTED"]
    with db.connect() as c:
        assert c.execute("SELECT count(*) FROM financial_source").fetchone()[0] == 21
    assert "Již načtené platby zůstávají uložené" in batch_text(reports)


def test_skipped_unpaid_and_zero_payments_are_explained(db, fixtures, tmp_path):
    def rows(source):
        selected = source[:3]
        selected[1][8] = "Unpaid"
        selected[2][9] = "0.00"
        return selected
    path = csv_file(fixtures, tmp_path, "platby.csv", rows)
    report = BookingImportService(db).run([ImportInput("BOOKING", str(path))])[0]
    assert report["added"] == 1
    assert report["excluded"] == {"UNPAID": 1, "ZERO_AMOUNT": 1}
    assert report["not_loaded"] == 0
    assert "neuhrazené: 1" in batch_text([report])
    assert "nulovou částkou: 1" in batch_text([report])


def test_bad_row_blocks_only_its_file_and_explains_count(db, fixtures, tmp_path):
    def rows(source):
        selected = source[:3]
        selected[1][9] = "invalid_amount"
        return selected
    path = csv_file(fixtures, tmp_path, "chybna_platba.csv", rows)
    reports = BookingImportService(db).run([ImportInput("BOOKING", str(path)), ImportInput("BOOKING", str(fixtures / "booking_a.csv"))])
    assert reports[0]["state"] == "FAILED" and reports[0]["not_loaded"] == 3
    assert reports[1]["added"] == 21
    assert "Řádek 3" in batch_text(reports)
    assert "ani jeho ostatní řádky" in batch_text(reports)


def test_picker_multiple_csv_automatic_import_and_readable_result(db, fixtures, tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    QFontDatabase.addApplicationFont(str(fixtures.parent / "src/kajovokarty/assets/DejaVuSans.ttf"))
    first = csv_file(fixtures, tmp_path, "leden.csv", lambda r: r[:2])
    second = csv_file(fixtures, tmp_path, "unor.csv", lambda r: [r[0], r[2]])
    window = MainWindow(db)
    window.show()
    spin(lambda: not window.jobs)
    choices = []
    def pick(*args):
        choices.append(args)
        return [str(first), str(second)], "Booking CSV (*.csv)"
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", pick)
    try:
        window.choose_import("BOOKING")
        spin(lambda: not window.jobs and window.import_dialog.completed)
        assert len(choices) == 1
        assert "Booking CSV (*.csv)" in choices[0]
        result = window.findChild(QDialog, "importProgressDialog")
        text = result.findChild(QPlainTextEdit).toPlainText()
        assert "nově uloženo: 3" in text and "unor.csv" in text
        assert "již uložené: 1" in text
        if os.environ.get("BOOKING_BATCH_SCREENSHOT"):
            result.grab().save(os.environ["BOOKING_BATCH_SCREENSHOT"])
        result.close()
    finally:
        spin(lambda: not window.jobs)
        window.view_timer.stop()
        window.close()
        app.processEvents()
