import pytest
from hypothesis import given, strategies as st
from kajovokarty.domain.core import (
    AppError,
    LIMIT,
    money,
    decimal_money,
    local_time,
    identifier,
)
from kajovokarty.domain.helpers import extract_references, reference_decision, merge, normalize_entity
from kajovokarty.domain.matching import isolated, zero_combinations, terminal_edges


@pytest.mark.parametrize(
    "s,n",
    [
        ("1 250,50", 125050),
        ("-83.49", -8349),
        ("50.000", 5000),
        ("-0", 0),
        ("1\u202f250,50", 125050),
    ],
)
def test_money(s, n):
    assert money(s) == n


@pytest.mark.parametrize(
    "s",
    ["1.005", "1,234.00", "1 25", "NaN", "Infinity", "1e3", "50 Kč", "(50)", "1,0001"],
)
def test_invalid_money(s):
    with pytest.raises(AppError):
        money(s)


@given(st.integers(-LIMIT, LIMIT))
def test_money_roundtrip(n):
    assert money(decimal_money(n)) == n


def test_terminal_edges_match_duplicates_one_to_one_without_variable_symbol():
    cash = [
        {"id": "c1", "local_date": "2026-09-07", "currency": "EUR", "signed_amount_minor": 5000, "source_identity": "cash-1"},
        {"id": "c2", "local_date": "2026-09-07", "currency": "EUR", "signed_amount_minor": 5000, "source_identity": "cash-2"},
        {"id": "c3", "local_date": "2026-09-07", "currency": "EUR", "signed_amount_minor": 7000, "source_identity": "cash-3"},
    ]
    bank = [
        {"id": "b1", "local_date": "2026-09-07", "currency": "EUR", "signed_amount_minor": 5000, "source_identity": "bank-1"},
        {"id": "b2", "local_date": "2026-09-07", "currency": "EUR", "signed_amount_minor": 5000, "source_identity": "bank-2"},
        {"id": "b3", "local_date": "2026-09-08", "currency": "EUR", "signed_amount_minor": 7000, "source_identity": "bank-3"},
    ]
    assert terminal_edges(cash, bank) == [{"c1", "b1"}, {"c2", "b2"}]


def test_merge_enriches_null_projection_but_rejects_real_conflict():
    assert merge({"reservation_source": None}, {"reservation_source": {"name": "Booking.com"}}) == {
        "reservation_source": {"name": "Booking.com"}
    }
    with pytest.raises(AppError):
        merge({"reservation_source": {"name": "Booking.com"}}, {"reservation_source": {"name": "Other"}})


def test_api_helper_money_rounds_calculated_fractional_cents():
    assert normalize_entity("bill_item", {"id": "B1", "amount": "12.345"}, {"EUR": "EUR"})["amount"] == "12.35"


def test_dst():
    with pytest.raises(AppError):
        local_time("29.3.2026 2:30:00")
    t, p, u, c = local_time("25.10.2026 2:30:00")
    assert p == "AMBIGUOUS_LOCAL" and u is None and len(c) == 2


def test_reservation_source_aliases_are_normalized_and_merged():
    value = normalize_entity(
        "reservation",
        {"id": "R1", "source": {"id": 7}, "reservation_source": {"uuid": "7", "name": "Booking.com"}},
        {},
    )
    assert value["reservation_source"] == {"id": "7", "name": "Booking.com"}


def test_identifiers():
    assert (
        identifier("001859") == "001859"
        and identifier(20266155.0) == "20266155"
        and identifier("123.0") == "123.0"
    )


def test_reference_decisions():
    ref = extract_references(
        [
            {"channel": "Original ID: 1234567890"},
            {"channel": "Channel reservation id = 1234567890"},
        ],
        "Booking.com",
    )
    assert reference_decision(ref)["resolution_status"] == "AUTO_CONFIRMED"
    override = {
        "active": 1,
        "accepted": 0,
        "candidate": None,
        "candidate_set_hash": ref["candidate_set_hash"],
    }
    assert reference_decision(ref, override)["resolution_status"] == "REJECTED"
    changed = extract_references(
        [{"channel": "Original ID: 1234567891"}], "Booking.com"
    )
    assert (
        reference_decision(changed, override)["resolution_status"] == "REVIEW_REQUIRED"
    )
    assert not extract_references(
        [{"channel": "Original ID: 123456789012345678901"}], "booking.com"
    )["candidates"]


def test_merge():
    assert merge({"id": "R1"}, {"id": "R1", "code": "101"}) == {
        "id": "R1",
        "code": "101",
    }
    with pytest.raises(AppError):
        merge({"id": "R1", "code": None}, {"id": "R1", "code": "101"})


def test_ambiguity():
    assert isolated([frozenset("ab"), frozenset("ac")]) == []


def test_negative_combinations_and_limit():
    items = [
        {
            "id": str(i),
            "kind": "CASHBOOK_CARD" if i == 0 else "BOOKING",
            "source_identity": str(i),
            "contribution": n,
        }
        for i, n in enumerate([5000, -6000, 1000])
    ]
    found, limit, states = zero_combinations(items)
    assert found == [frozenset(["0", "1", "2"])] and not limit
    assert zero_combinations(items, max_states=2)[1]
