import pytest

from kajovokarty.application.work import WorkService
from kajovokarty.ui.models import TableModel, WORK_COLUMNS
from kajovokarty.domain.core import AppError
from test_acceptance_traces import seed


def add_sources(db, entries):
    for index, (kind, amount) in enumerate(entries, 1):
        seed(db, kind, amount, vs=f"2026{index:04d}", seq=f"{index:06d}")
    return WorkService(db)


def group(work, rows):
    return work.create_group([r["id"] for r in rows], {r["id"]: r["revision"] for r in rows})


@pytest.mark.parametrize("entries,amount,difference", [
    ([("CASHBOOK_CARD", "111.00"), ("BOOKING", "111.00")], 11100, 0),
    ([("CASHBOOK_CARD", "50.00"), ("CASHBOOK_CARD", "61.00"), ("BOOKING", "111.00")], 11100, 0),
    ([("CASHBOOK_CARD", "111.00"), ("BOOKING", "100.00")], 11100, 1100),
    ([("CASHBOOK_CARD", "-111.00"), ("BOOKING", "-111.00")], -11100, 0),
    ([("BANK_CARD", "50.00"), ("BOOKING", "61.00")], 11100, -11100),
    ([("CASHBOOK_CARD", "50.00"), ("CASHBOOK_CARD", "-50.00"), ("BOOKING", "61.00")], 0, -6100),
])
def test_group_amount_represents_cash_total_or_counterparts(db, entries, amount, difference):
    work = add_sources(db, entries)
    group(work, work.query(page_size=0)["rows"])
    row = work.query({"status": "all"})["rows"][0]
    assert row["amount"] == amount
    from kajovokarty.application.pairing import PairingService
    transferred = PairingService(db).resolve_draft_rows([row])[0]
    assert transferred['amount'] == amount
    assert row["difference"] == difference
    assert row["resolved"] == (difference == 0)
    if amount == 11100 and difference == 0:
        model = TableModel([row], WORK_COLUMNS)
        assert model.data(model.index(0, 7)) == "111,00"
        assert model.data(model.index(0, 9)) == "0,00"


def test_nested_groups_are_rejected(db):
    work = add_sources(db, [("CASHBOOK_CARD", "50.00"), ("CASHBOOK_CARD", "61.00"), ("BOOKING", "111.00")])
    rows = work.query(page_size=0)["rows"]
    first = group(work, [r for r in rows if "CASHBOOK_CARD" in r["kinds"]])
    with pytest.raises(AppError, match="přímé platební"):
        group(work, work.query({"status": "all"}, page_size=0)["rows"])
    assert work.evidence(first["id"])["object"]["lifecycle"] == "ACTIVE"


def test_amount_sort_and_filters_use_payment_value(db):
    work = add_sources(db, [("CASHBOOK_CARD", "111.00"), ("BOOKING", "111.00"),
                            ("CASHBOOK_CARD", "50.00"), ("BOOKING", "50.00")])
    rows = work.query(page_size=0)["rows"]
    for amount in (11100, 5000):
        group(work, [r for r in rows if r["amount"] == amount])
    assert [r["amount"] for r in work.query({"status": "resolved"}, [("amount", "asc")])["rows"]] == [5000, 11100]
    assert [r["amount"] for r in work.query({"status": "resolved"}, [("amount", "desc")])["rows"]] == [11100, 5000]
    for filters in ({"amount": 11100}, {"amount_min": 11000, "amount_max": 11200},
                    {"column_filters": {"amount": ["11100"]}}):
        result = work.query({"status": "resolved", **filters})
        assert [r["amount"] for r in result["rows"]] == [11100]
    facets = work.query({"status": "resolved", "_facet": "amount"})["facets"]
    assert {token for _, token in facets} == {"5000", "11100"}
