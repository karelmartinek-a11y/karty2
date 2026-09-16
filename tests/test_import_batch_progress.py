import json
import threading
import pytest
from PySide6.QtWidgets import QApplication
from kajovokarty.application.imports import ImportInput
from kajovokarty.application.import_batch import ImportBatchService, batch_text
from kajovokarty.application.catalog import CatalogService
from kajovokarty.ui.main import MainWindow
from test_accounts import SAMPLE
from test_booking_batch import csv_file
from test_gui import spin


@pytest.mark.parametrize("kind,name", [("BOOKING", "booking_a.csv"), ("BANK_CARD", "terminal.xlsx"),
                                      ("CASHBOOK_CARD", "cashbook_week.xls"), ("ACCOUNTS", None)])
def test_all_kinds_committed_counts_history_progress_and_repeat(db, fixtures, kind, name):
    path = fixtures / name if name else SAMPLE
    request = ImportInput(kind, str(path))
    events = []
    service = ImportBatchService(db)
    reports = service.run([request, request], progress=lambda event: events.append(event.snapshot))
    assert [r["state"] for r in reports] == ["COMPLETED", "COMPLETED"]
    assert reports[0]["added"] > 0 and reports[1]["added"] == 0
    assert reports[1]["already_saved"] >= reports[0]["added"]
    assert all(r["not_saved"] == 0 for r in reports)
    for r in reports:
        assert r["total"] == r["added"] + r["already_saved"] + sum(r["skipped"].values())
    assert any(e["stage"] == "Kontrola" and e["current"] == e["total"] for e in events)
    assert all(e["added"] == 0 for e in events if e["file_index"] == 1 and e["stage"] != "Soubor dokončen")
    assert events[-1]["added"] == reports[0]["added"]
    for r in CatalogService(db).rows("imports"):
        assert "Nově uložené" in r["result_text"]
        assert CatalogService(db).import_detail(r["run_id"], r["file_id"]) == batch_text(reports)
    with db.connect() as c:
        assert c.execute("select count(*) from operation where state='RUNNING'").fetchone()[0] == 0
        table = "account_symbol" if kind == "ACCOUNTS" else "financial_source"
        assert c.execute("select count(*) from " + table).fetchone()[0] == reports[0]["added"]


def test_bad_file_between_good_files_and_unknown_size(db, fixtures, tmp_path):
    first = csv_file(fixtures, tmp_path, "first.csv", lambda rows: rows[:1])
    last = csv_file(fixtures, tmp_path, "last.csv", lambda rows: rows[1:2])
    broken = tmp_path / "missing.csv"
    reports = ImportBatchService(db).run([ImportInput("BOOKING", str(p)) for p in (first, broken, last)])
    assert [r["state"] for r in reports] == ["COMPLETED", "FAILED", "COMPLETED"]
    assert reports[1]["total"] is None and reports[1]["not_saved"] is None
    assert sum(r["added"] for r in reports) == 2
    assert "počet nezjištěn" in batch_text(reports)


def test_cancel_during_write_rolls_back_file_and_keeps_previous(db, fixtures):
    stop = threading.Event()
    request = ImportInput("BOOKING", str(fixtures / "booking_a.csv"))
    other = ImportInput("BOOKING", str(fixtures / "booking_b.csv"))
    def progress(event):
        d = event.snapshot
        if d["file_index"] == 2 and d["stage"] == "Ukládání plateb":
            stop.set()
    reports = ImportBatchService(db).run([request, other, other], cancel=stop, progress=progress)
    assert [r["state"] for r in reports] == ["COMPLETED", "CANCELLED", "NOT_STARTED"]
    assert reports[1]["added"] == 0
    with db.connect() as c:
        assert c.execute("select count(*) from financial_source").fetchone()[0] == reports[0]["added"]


@pytest.mark.parametrize("kind,name", [("BOOKING", "booking_a.csv"), ("BANK_CARD", "terminal.xlsx"),
                                      ("CASHBOOK_CARD", "cashbook_week.xls"), ("ACCOUNTS", None)])
def test_actual_popup_stays_visible_until_done_for_every_kind(db, fixtures, kind, name):
    app = QApplication.instance() or QApplication([])
    window = MainWindow(db)
    window.show()
    spin(lambda: not window.jobs)
    path = fixtures / name if name else SAMPLE
    try:
        window.preflight([ImportInput(kind, str(path))])
        dialog = window.import_dialog
        assert dialog.isVisible() and not dialog.completed
        assert dialog.button.text() == "Zastavit import"
        spin(lambda: not window.jobs and dialog.completed, seconds=30)
        assert dialog.isVisible() and dialog.button.text() == "Hotovo"
        assert "Nově uložené" in dialog.details.toPlainText()
        assert "Import dokončen" in dialog.windowTitle()
        dialog.button.click()
        assert not dialog.isVisible()
    finally:
        if window.jobs:
            window.cancel.set()
            spin(lambda: not window.jobs, seconds=30)
        window.close()
        app.processEvents()


def test_write_failure_counts_only_committed_files(db, fixtures, monkeypatch):
    original = db.audit
    failures = [1]
    def audit(c, event, *args, **kwargs):
        if event == "OPERATION_COMPLETED" and failures:
            failures.pop()
            raise OSError("simulated write failure")
        return original(c, event, *args, **kwargs)
    monkeypatch.setattr(db, "audit", audit)
    request = ImportInput("BOOKING", str(fixtures / "booking_a.csv"))
    reports = ImportBatchService(db).run([request, request])
    assert [r["state"] for r in reports] == ["FAILED", "COMPLETED"]
    assert reports[0]["added"] == 0 and reports[0]["not_saved"] == 21
    assert reports[1]["added"] == 21
    with db.connect() as c:
        assert c.execute("select count(*) from financial_source").fetchone()[0] == 21
    events = [json.loads(line) for path in db.log.folder.glob("*.jsonl") for line in path.read_text(encoding="utf-8").splitlines()]
    results = [e for e in events if e["event"] == "IMPORT_FILE_RESULT"]
    assert [e["counts"]["added"] for e in results] == [0, 21]


def test_unreadable_single_file_visible_in_history(db, tmp_path):
    reports = ImportBatchService(db).run([ImportInput("BANK_CARD", str(tmp_path / "missing.xlsx"))])
    rows = CatalogService(db).rows("imports")
    assert len(rows) == 1 and rows[0]["state"] == "FAILED"
    assert CatalogService(db).import_detail(rows[0]["run_id"], rows[0]["file_id"]) == batch_text(reports)


@pytest.mark.parametrize("accept", [True, False])
def test_sheet_choice_on_gui_thread_without_confirmation(db, fixtures, tmp_path, monkeypatch, accept):
    import openpyxl
    from PySide6.QtWidgets import QInputDialog
    book = openpyxl.load_workbook(fixtures / "terminal.xlsx")
    book.copy_worksheet(book.active)
    path = tmp_path / "two_sheets.xlsx"
    book.save(path)
    app = QApplication.instance() or QApplication([])
    window = MainWindow(db)
    window.show()
    spin(lambda: not window.jobs)
    calls = []
    def choose(*args):
        calls.append(threading.current_thread() is threading.main_thread())
        return args[3][1], accept
    monkeypatch.setattr(QInputDialog, "getItem", choose)
    try:
        window.preflight([ImportInput("BANK_CARD", str(path))])
        spin(lambda: not window.jobs and window.import_dialog.completed, seconds=30)
        assert calls == [True]
        with db.connect() as c:
            count = c.execute("select count(*) from financial_source").fetchone()[0]
            assert bool(count) == accept
            assert c.execute("select count(*) from operation where state='RUNNING'").fetchone()[0] == 0
        assert window.import_dialog.isVisible()
        window.import_dialog.accept()
    finally:
        window.close()
        app.processEvents()


def test_slow_import_popup_live_counts_and_close_requests_cancel(db, fixtures, monkeypatch):
    import kajovokarty.application.imports as module
    from kajovokarty.domain.import_progress import ImportProgress
    original = module.parse
    entered, release = threading.Event(), threading.Event()
    def slow(raw, name, kind, sheet, cancel, progress):
        progress(ImportProgress("Kontrola", 2, 10))
        entered.set()
        assert release.wait(10)
        return original(raw, name, kind, sheet, cancel, progress)
    monkeypatch.setattr(module, "parse", slow)
    app = QApplication.instance() or QApplication([])
    window = MainWindow(db)
    window.show()
    spin(lambda: not window.jobs)
    try:
        window.preflight([ImportInput("BOOKING", str(fixtures / "booking_a.csv"))])
        dialog = window.import_dialog
        spin(lambda: entered.is_set() and "2 z 10" in dialog.counts.text())
        assert "zbývá 8" in dialog.counts.text() and dialog.isVisible()
        dialog.close()
        assert dialog.isVisible() and window.cancel.is_set()
        release.set()
        spin(lambda: not window.jobs and dialog.completed)
        assert dialog.windowTitle() == "Import zastaven"
        with db.connect() as c:
            assert c.execute("select count(*) from financial_source").fetchone()[0] == 0
        dialog.button.click()
    finally:
        release.set()
        spin(lambda: not window.jobs)
        window.close()
        app.processEvents()


def test_duplicate_inside_rejected_file_is_not_reported_as_already_saved(db, fixtures, tmp_path):
    def rows(source):
        bad = list(source[1])
        bad[9] = "bad amount"
        return [source[0], source[0], bad]
    path = csv_file(fixtures, tmp_path, "duplicate_and_error.csv", rows)
    report = ImportBatchService(db).run([ImportInput("BOOKING", str(path))])[0]
    assert report["state"] == "FAILED"
    assert report["added"] == report["already_saved"] == 0
    assert report["not_saved"] == 3 and report["error_rows"] == 1


def test_repeated_conflicting_row_is_not_counted_as_existing_payment(db, fixtures, tmp_path):
    first = csv_file(fixtures, tmp_path, "original.csv", lambda rows: rows[:1])
    service = ImportBatchService(db)
    assert service.run([ImportInput("BOOKING", str(first))])[0]["added"] == 1
    def changed(rows):
        row = list(rows[0])
        row[9] = "1.00"
        return [row, row]
    path = csv_file(fixtures, tmp_path, "conflict.csv", changed)
    report = service.run([ImportInput("BOOKING", str(path))])[0]
    assert report["state"] == "FAILED" and report["already_saved"] == 0
    assert report["not_saved"] == 2
