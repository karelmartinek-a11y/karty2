import pytest, sqlite3
from kajovokarty.application.work import WorkService
from kajovokarty.application.imports import ImportInput
from kajovokarty.application.settings import SettingsService
from kajovokarty.application.matching import MatchingService
from kajovokarty.domain.core import AppError


@pytest.fixture
def work(importer, fixtures):
    p = importer.preflight(
        [
            ImportInput("CASHBOOK_CARD", str(fixtures / "cashbook_year.xls")),
            ImportInput("BANK_CARD", str(fixtures / "terminal.xlsx")),
        ]
    )
    importer.commit(p.id)
    return WorkService(importer.db)


def choose(work, n=2):
    return [r for r in work.query(page_size=0)["rows"] if r["currency"] == "EUR"][:n]


def create(work, rows):
    return work.create_group(
        [r["id"] for r in rows], {r["id"]: r["revision"] for r in rows}
    )


def test_tree(work):
    rs = choose(work, 3)
    g = create(work, rs[:2])
    rows = work.query(page_size=0)["rows"]
    sub = next(r for r in rows if r["id"] == g["id"])
    third = next(r for r in rows if r["id"] == rs[2]["id"])
    parent = create(work, [sub, third])
    e = work.evidence(parent["id"])
    assert len(e["leaves"]) == 3
    work.dissolve(parent["id"], e["object"]["revision"])
    assert len(work.evidence(g["id"])["leaves"]) == 2
    assert g["id"] in work.query(page_size=0)["ids"]


def test_undo_redo(work):
    g = create(work, choose(work))
    work.undo(g["command_id"])
    assert work.evidence(g["id"])["object"]["lifecycle"] == "DISSOLVED"
    work.undo(g["command_id"], True)
    assert work.evidence(g["id"])["object"]["lifecycle"] == "ACTIVE"


def test_stale_and_currency(work):
    rows = work.query(page_size=0)["rows"]
    a = next(r for r in rows if r["currency"] == "CZK")
    b = next(r for r in rows if r["currency"] == "EUR")
    with pytest.raises(AppError) as e:
        create(work, [a, b])
    assert e.value.code == "MIXED_CURRENCY"
    rs = choose(work)
    create(work, rs)
    with pytest.raises(AppError):
        create(work, rs)


def test_immutable(work):
    with work.db.connect() as c:
        with pytest.raises(sqlite3.IntegrityError):
            c.execute("UPDATE financial_source SET signed_amount_minor=1")
        with pytest.raises(sqlite3.IntegrityError):
            c.execute("DELETE FROM financial_source")


def test_auto_and_suppression(work):
    m = MatchingService(work.db, SettingsService(work.db))
    assert m.run()["created_groups"] == 1
    assert m.run()["created_groups"] == 0
    resolved = work.query({"status": "resolved"}, page_size=0)["rows"][0]
    cmd = work.dissolve(resolved["id"], resolved["revision"])
    assert m.run()["created_groups"] == 0
    work.undo(cmd)
    assert len(work.query({"status": "resolved"}, page_size=0)["rows"]) == 1
    work.undo(cmd, True)
    assert m.run()["created_groups"] == 0


def test_sequential_undo_redo(work):
    g = create(work, choose(work))
    e = work.evidence(g["id"])
    note = work.edit_note(g["id"], e["object"]["revision"], "Poznámka")
    work.undo(note)
    work.undo(g["command_id"])
    work.undo(g["command_id"], True)
    work.undo(note, True)
    assert work.evidence(g["id"])["group"]["note"] == "Poznámka"


def test_historical_group_keeps_original_leaves(work):
    rs = choose(work, 4)
    g = create(work, rs[:2])
    e = work.evidence(g["id"])
    work.dissolve(g["id"], e["object"]["revision"])
    original = {r["id"] for r in work.evidence(g["id"])["leaves"]}
    rows = work.query(page_size=0)["rows"]
    new = [r for r in rows if r["id"] in [rs[0]["id"], rs[2]["id"]]]
    create(work, new)
    assert {r["id"] for r in work.evidence(g["id"])["leaves"]} == original


def test_mixed_selection_exports_as_two_reports(work):
    from kajovokarty.application.reports import ReportService

    MatchingService(work.db, SettingsService(work.db)).run()
    rows = work.query({"status": "all"}, page_size=0)["rows"]
    ids = [
        next(r["id"] for r in rows if r["resolved"]),
        next(r["id"] for r in rows if not r["resolved"]),
    ]
    service = ReportService(work.db)
    plans = service.partition_work_selection(ids)
    assert set(plans) == {"unresolved", "resolved"}
    exported = []
    for report, selection in plans.items():
        data = service.build(report, selection, {"text": "not-matching"})
        exported.extend(r["object_id"] for r in data["work_objects"])
    assert set(exported) == set(ids) and len(exported) == 2
