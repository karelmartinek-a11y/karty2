import pytest

from kajovokarty.application.booking_import import BookingImportService
from kajovokarty.application.imports import ImportInput
from test_booking_batch import csv_file


@pytest.mark.parametrize("status", ["no_show", "no-show", "cancelled", "unknown_future_status", ""])
def test_stay_status_never_blocks_paid_payment(db, fixtures, tmp_path, status):
    def rows(source):
        source[0][6] = status
        source[0][2] = "unreadable stay date"
        return source[:1]
    path = csv_file(fixtures, tmp_path, "status.csv", rows)
    report = BookingImportService(db).run([ImportInput("BOOKING", str(path))])[0]
    assert report["state"] == "COMPLETED" and report["added"] == 1


def test_metadata_changes_keep_existing_payment_and_do_not_duplicate(db, fixtures, tmp_path):
    first = csv_file(fixtures, tmp_path, "first.csv", lambda r: r[:1])
    def changed(rows):
        row = rows[0]
        row[2:7] = ["bad date", "Aug 21, 2026", "JÃºlius VigaÅ¡", "Other provider spelling", "no_show"]
        return [row]
    second = csv_file(fixtures, tmp_path, "second.csv", changed)
    service = BookingImportService(db)
    assert service.run([ImportInput("BOOKING", str(first))])[0]["added"] == 1
    with db.connect() as c:
        before = tuple(c.execute("SELECT id,canonical_json,content_hash FROM financial_source").fetchone())
    report = service.run([ImportInput("BOOKING", str(second))])[0]
    assert report["state"] == "COMPLETED" and report["already_saved"] == 1 and report["added"] == 0
    with db.connect() as c:
        assert tuple(c.execute("SELECT id,canonical_json,content_hash FROM financial_source").fetchone()) == before
        assert c.execute("SELECT count(*) FROM financial_source").fetchone()[0] == 1
        assert c.execute("SELECT count(*) FROM source_occurrence WHERE source_id=?", (before[0],)).fetchone()[0] == 2


def test_changed_payment_amount_still_rejected(db, fixtures, tmp_path):
    first = csv_file(fixtures, tmp_path, "first.csv", lambda r: r[:1])
    def changed(rows):
        rows[0][9] = "9876.54"
        return rows[:1]
    second = csv_file(fixtures, tmp_path, "second.csv", changed)
    reports = BookingImportService(db).run([ImportInput("BOOKING", str(p)) for p in (first, second)])
    assert reports[0]["state"] == "COMPLETED"
    assert reports[1]["state"] == "FAILED" and reports[1]["added"] == 0
