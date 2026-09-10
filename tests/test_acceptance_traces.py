"""Exact A.7–A.10 state transitions over SQLite; wire responses are local fixtures."""

import copy
import httpx, pytest
from kajovokarty.domain.core import canonical, digest, uid, now
from kajovokarty.infrastructure.parsers import cash, bank, booking
from kajovokarty.application.matching import MatchingService
from kajovokarty.application.work import WorkService
from kajovokarty.application.sync import SyncService
from kajovokarty.application.settings import SettingsService
from kajovokarty.application.refresh import RefreshService
from kajovokarty.application.reports import ReportService
from test_api import client


def seed(db, kind, amount="50.00", vs="20260001", seq="000001", minute="00"):
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
                currency="EUR",
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
            occurred_local="07.09.2026 12:02:00",
            signed_amount_minor=amount,
            currency="EUR",
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
                currency="EUR",
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
            "INSERT INTO work_object VALUES(?,'SOURCE',?,'EUR','ACTIVE',1)", (sid, sid)
        )
    return sid


def fixedpoint_wire(wire):
    wire = copy.deepcopy(wire)
    wire["/reservation"] = {"data": [{"id": "R1", "code": "101"}]}
    wire["/reservation/R1/invoice"] = {"data": [{"id": "I1"}, {"id": "I2"}]}
    return wire


def test_A7_fixedpoint_and_A8_undo_suppression(db, wire):
    cash1 = seed(db, "CASHBOOK_CARD")
    cash2 = seed(db, "CASHBOOK_CARD", vs="20260002", minute="01")
    book = seed(db, "BOOKING")
    terminal = seed(db, "BANK_CARD")
    settings = SettingsService(db)
    sync = SyncService(db, settings)
    wire = fixedpoint_wire(wire)
    http = client(wire)
    try:
        sync.full(http, scope=("2026-09-07", "2026-09-08"))
    finally:
        http.close()
    match = MatchingService(db, settings)
    work = WorkService(db)
    result = match.run()
    assert (
        result["created_groups"] == 2
        and result["rounds"] == 3
        and result["reached_fixed_point"]
    )
    assert match.run()["created_groups"] == 0
    groups = work.query({"status": "resolved"})["rows"]
    assert {frozenset(r["leaves"]) for r in groups} == {
        frozenset((cash1, terminal)),
        frozenset((cash2, book)),
    }
    group = next(r for r in groups if book in r["leaves"])
    cmd = work.dissolve(group["id"], group["revision"])

    def suppression():
        with db.connect() as c:
            return dict(c.execute("SELECT * FROM auto_suppression").fetchone())

    assert suppression()["active"] == 1 and suppression()["revision"] == 1
    work.undo(cmd)
    assert suppression()["active"] == 0 and suppression()["revision"] == 2
    work.undo(cmd, True)
    assert suppression()["active"] == 1 and suppression()["revision"] == 3
    http = client(wire)
    try:
        sync.full(http, scope=("2026-09-07", "2026-09-08"))
    finally:
        http.close()
    assert match.run()["created_groups"] == 0 and suppression()["revision"] == 3
    data = ReportService(db).build("group_evidence", [group["id"]])
    assert len(data["group_leaves"]) == 2
    assert data["currency_totals"][0]["difference_minor"] == 0
    assert dict((r["key"], r["value_json"]) for r in data["metadata"])[
        "selected_helper_graphs"
    ]


@pytest.mark.parametrize("cash_count,bank_count", [(1, 2), (2, 1)])
def test_C_strong_both_sides_ambiguity(db, cash_count, bank_count):
    for i in range(cash_count):
        seed(db, "CASHBOOK_CARD", minute=f"{i:02d}")
    for i in range(bank_count):
        seed(db, "BANK_CARD", seq=f"{i + 1:06d}")
    assert MatchingService(db, SettingsService(db)).run()["created_groups"] == 0


def test_A9_moved_root_and_orphan_preserved(db, wire):
    from kajovokarty.infrastructure.betterhotel import BetterHotelClient

    settings = SettingsService(db)
    sync = SyncService(db, settings)
    wire = copy.deepcopy(wire)
    wire["/reservation/R1/bill"] = {"data": [{"id": "B1"}]}
    wire["/bill/B1"] = {"id": "B1", "currency": "EUR"}
    wire["/bill/B1/bill-item"] = {"data": []}

    def initial(r):
        return httpx.Response(200, json=wire[r.url.path[len("/api/connector/v/1") :]])

    http = BetterHotelClient("a", "b", transport=httpx.MockTransport(initial))
    try:
        sync.full(http, scope=("2026-09-01", "2026-09-14"))
    finally:
        http.close()
    old = sync.state()["published_generation_id"]
    changed = copy.deepcopy(wire)
    changed["/reservation/R1/bill"] = {"data": []}

    def moved(r):
        path = r.url.path[len("/api/connector/v/1") :]
        if path == "/invoice":
            return httpx.Response(200, json={"data": []})
        if path == "/reservation" and r.url.params["date_from"] == "2026-09-01":
            assert sync.state()["published_generation_id"] == old
            return httpx.Response(200, json={"data": []})
        return httpx.Response(200, json=changed[path])

    http = BetterHotelClient("a", "b", transport=httpx.MockTransport(moved))
    try:
        sync.full(http, scope=("2026-09-01", "2026-09-14"))
    finally:
        http.close()
    entities = {(r["resource_type"], r["external_id"]): r for r in sync.entities(True)}
    assert (
        entities["reservation", "R1"]["active"] == 1
        and entities["invoice", "I1"]["active"] == 1
    )
    assert entities["bill", "B1"]["active"] == 0
    with db.connect() as c:
        assert (
            c.execute(
                "SELECT active FROM helper_link WHERE generation_id=? AND relation='BILL'",
                (sync.state()["published_generation_id"],),
            ).fetchone()[0]
            == 0
        )
        assert (
            c.execute(
                "SELECT active FROM helper_current WHERE generation_id=? AND resource_type='bill'",
                (old,),
            ).fetchone()[0]
            == 1
        )


def test_security_deposit_only_refresh_and_pruning(db, wire):
    wire = copy.deepcopy(wire)
    wire["/reservation/R1/security-deposit"] = {
        "data": [{"id": "SD1", "amount": "10", "currency": "EUR"}]
    }
    settings = SettingsService(db)
    sync = SyncService(db, settings)
    http = client(wire)
    try:
        sync.full(http, scope=("2026-09-07", "2026-09-08"))
    finally:
        http.close()
    wire["/reservation/R1/security-deposit"] = {"data": []}
    seen = []
    http = client(wire, seen)
    try:
        RefreshService(db, settings).refresh(
            http, "security_deposit", "SD1", sync.state()["context_id"]
        )
    finally:
        http.close()
    assert len(seen) == 1 and seen[0].url.path.endswith(
        "/reservation/R1/security-deposit"
    )
    assert (
        next(r for r in sync.entities(True) if r["external_id"] == "SD1")["active"] == 0
    )
