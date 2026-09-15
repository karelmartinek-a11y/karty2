"""Exact A.7–A.10 state transitions over SQLite; wire responses are local fixtures."""

import pytest
from kajovokarty.domain.core import canonical, digest, uid, now
from kajovokarty.infrastructure.parsers import cash, bank, booking
from kajovokarty.application.matching import MatchingService
from kajovokarty.application.settings import SettingsService


def seed(db, kind, amount="50.00", vs="20260001", seq="000001", minute="00", currency="EUR", day="07"):
    if kind == "CASHBOOK_CARD":
        source, _, _ = cash(
            dict(
                issued_local="07.09.2026 12:" + minute + ":00",
                movement="Příjem" if not amount.startswith("-") else "Výdaj",
                cashbook_number=None,
                label="FA" + vs,
                client="Synthetic",
                income_minor=amount if not amount.startswith("-") else "0",
                expense_minor=amount[1:] if amount.startswith("-") else "0",
                currency=currency,
                payment_form="Kartou",
                variable_symbol=vs,
                issued_by="Test",
            )
        )
    elif kind == "BANK_CARD":
        from kajovokarty.infrastructure.parsers import BANK_FIELDS

        d = {k: None for k in BANK_FIELDS}
        d.update(
            event_class="Prodej",
            terminal_id="TEST-FP",
            seq_id=seq,
            occurred_local=day + ".09.2026 12:02:00",
            signed_amount_minor=amount,
            currency=currency,
            variable_symbol=vs,
        )
        source, _, _ = bank(d)
    else:
        source, _, _ = booking(
            dict(
                invoice_type="Reservation",
                booking_reference="1234567890",
                arrival="2026-09-07",
                departure="2026-09-08",
                guest_name="Synthetic",
                provider="Booking.com",
                reservation_status="ok",
                currency=currency,
                payment_status="Paid Online",
                signed_amount_minor=amount,
                payout_date="2026-09-07",
                payout_id="TEST-" + seq,
            )
        )
    sid = uid()
    p = source.content
    raw = canonical(p)
    with db.transaction() as c:
        c.execute(
            "INSERT INTO financial_source VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                sid,
                kind,
                source.identity,
                raw,
                source.content_hash,
                source.local_date,
                source.occurred_at_utc,
                source.time_precision,
                source.amount,
                source.currency,
                source.primary,
                source.description,
                now(),
            ),
        )
        if kind == "CASHBOOK_CARD":
            c.execute(
                "INSERT INTO cashbook_detail VALUES(?,?,?,?,?)",
                (
                    sid,
                    p["cashbook_number"],
                    p["invoice_code"],
                    int(p["storno_marker"]),
                    raw,
                ),
            )
        elif kind == "BANK_CARD":
            c.execute(
                "INSERT INTO bank_detail VALUES(?,?,?,?,?)",
                (sid, p["terminal_id"], p["seq_id"], p["event_class"], raw),
            )
        else:
            c.execute(
                "INSERT INTO booking_detail VALUES(?,?,?,?,?)",
                (
                    sid,
                    digest([p[k] for k in ("payout_id", "payout_date", "currency")]),
                    p["payout_id"],
                    p["booking_reference"],
                    raw,
                ),
            )
        c.execute(
            "INSERT INTO work_object VALUES(?,'SOURCE',?,?,'ACTIVE',1)", (sid, sid, currency)
        )
    return sid


@pytest.mark.parametrize("cash_count,bank_count", [(1, 2), (2, 1)])
def test_C_strong_both_sides_ambiguity(db, cash_count, bank_count):
    for i in range(cash_count):
        seed(db, "CASHBOOK_CARD", minute=f"{i:02d}")
    for i in range(bank_count):
        seed(db, "BANK_CARD", seq=f"{i + 1:06d}", day="08")
    assert MatchingService(db, SettingsService(db)).run()["created_groups"] == 0
