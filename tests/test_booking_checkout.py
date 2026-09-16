import csv
import io
import json
import pytest
from kajovokarty.application.work import WorkService
from kajovokarty.application.pairing import PairingService
from kajovokarty.application.imports import ImportInput, ImportService
from kajovokarty.domain.core import AppError
from test_acceptance_traces import seed
from test_group_amount import group


def test_checkout_projection_filters_sort_and_pairing(db):
    seed(db, "BOOKING")  # payout September 7, checkout September 8
    seed(db, "CASHBOOK_CARD")
    work = WorkService(db)
    rows = work.query(sort=[("date", "asc")])["rows"]
    assert [r["date"] for r in rows] == ["2026-09-07", "2026-09-08"]
    booking = next(r for r in rows if "BOOKING" in r["kinds"])
    assert PairingService(db).panel(booking["id"])["object"]["date"] == "2026-09-08"
    assert work.query({"date_from": "2026-09-08", "date_to": "2026-09-08"})["total"] == 1
    assert work.query({"kind": ["BOOKING"], "date_to": "2026-09-07"})["total"] == 0
    assert work.query({"column_filters": {"date": ['"2026-09-08"']}})["total"] == 1
    assert ("08. září 2026", '"2026-09-08"') in work.query({"_facet": "date"})["facets"]
    group(work, rows)
    row = work.query({"status": "all"})["rows"][0]
    assert (row["date"], row["date_end"]) == ("2026-09-07", "2026-09-08")
    panel = PairingService(db).panel(row["id"])
    assert sorted(r["date"] for r in panel["rows"]) == ["2026-09-07", "2026-09-08"]
    with db.connect() as c:
        assert c.execute("select local_date from financial_source where kind='BOOKING'").fetchone()[0] == "2026-09-07"


@pytest.mark.parametrize("checkout", ["", "not a date", "2026-02-30"])
def test_invalid_checkout_blocks_import_with_human_error(db, tmp_path, fixtures, checkout):
    rows = list(csv.reader(io.StringIO((fixtures / "booking_a.csv").read_text("utf-8-sig"))))
    rows[1][3] = checkout
    path = tmp_path / "invalid_checkout.csv"
    with path.open("w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows(rows)
    imports = ImportService(db)
    preview = imports.preflight([ImportInput("BOOKING", str(path))])
    assert not preview.valid
    assert any(d["code"] == "BOOKING_CHECKOUT_INVALID" for d in preview.diagnostics)
    with pytest.raises(AppError) as error:
        imports.commit(preview.id)
    assert error.value.code == "IMPORT_INVALID"
    events = [json.loads(line) for path in db.log.folder.glob("*.jsonl")
              for line in path.read_text(encoding="utf-8").splitlines()]
    assert any(e.get("error_code") == "BOOKING_CHECKOUT_INVALID" for e in events)
    with db.connect() as c:
        assert c.execute("select count(*) from financial_source").fetchone()[0] == 0

