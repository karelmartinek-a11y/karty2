"""User-controlled history and filtering when the server ignores date parameters."""

from datetime import date, timedelta
import json

import httpx
import pytest

from kajovokarty.application.settings import SettingsService
from kajovokarty.application.sync import SyncService
from kajovokarty.domain.core import AppError
from kajovokarty.infrastructure.betterhotel import BASE, BetterHotelClient
from kajovokarty.infrastructure.database import Database


def mock_client(wire, seen):
    def respond(request):
        path = request.url.path[len(BASE.split(".com")[1]):]
        seen.append((path, dict(request.url.params)))
        return httpx.Response(200, json=wire[path])

    client = BetterHotelClient("a", "b", transport=httpx.MockTransport(respond))
    client.wait = lambda _: None
    return client


@pytest.mark.parametrize("old", [None, "", "2026-02-03"])
def test_start_setting_initialized_and_preserved(db, old):
    with db.transaction() as c:
        c.execute("DELETE FROM setting WHERE key='sync.start_date'")
        if old is not None:
            c.execute("INSERT INTO setting VALUES('sync.start_date',?,1)", (json.dumps(old),))
    reopened = Database(db.path)
    assert SettingsService(reopened).get()["sync.start_date"] == (old or "2026-01-01")
    SettingsService(reopened).save({"sync.start_date": "2026-03-04"})
    assert SettingsService(Database(db.path)).get()["sync.start_date"] == "2026-03-04"


@pytest.mark.parametrize("value", ["", None, "bad", "2026-02-30", "20260101"])
def test_invalid_date_rejected(db, value):
    with pytest.raises(AppError, match="Nastavení"):
        SettingsService(db).save({"sync.start_date": value})


def test_future_date_rejected(db):
    with pytest.raises(AppError):
        SettingsService(db).save({"sync.start_date": (date.today() + timedelta(days=1)).isoformat()})


def test_scope_ignores_previous_coverage_and_sources(db, wire, importer, fixtures):
    from kajovokarty.application.imports import ImportInput

    settings = SettingsService(db)
    sync = SyncService(db, settings)
    client = mock_client(wire, [])
    try:
        sync.full(client, scope=("2025-01-01", "2027-12-31"))
    finally:
        client.close()
    importer.commit(importer.preflight([ImportInput("BOOKING", str(fixtures / "booking_a.csv"))]).id)
    settings.save({"sync.start_date": date.today().isoformat()})
    assert sync.scope() == (date.today().isoformat(), date.today().isoformat())


@pytest.mark.parametrize("arrival,departure,included", [
    ("2026-09-07", "2026-09-08", True),
    ("2026-08-01", "2026-09-07", True),
    ("2026-09-08", "2026-10-01", True),
    ("2026-08-01", "2026-10-01", True),
    ("2026-08-01", "2026-09-06", False),
    ("2026-09-09", "2026-10-01", False),
])
def test_server_ignores_period_filter_before_relations(db, wire, arrival, departure, included):
    # A complete list record outside the range must not trigger even a detail call.
    raw = {**wire["/reservation/R1"]["data"], "arrival": arrival, "departure": departure}
    wire["/reservation"]["data"] = [raw]
    wire["/reservation/R1"]["data"] = raw
    seen = []
    client = mock_client(wire, seen)
    sync = SyncService(db, SettingsService(db))
    try:
        sync.full(client, scope=("2026-09-07", "2026-09-08"))
    finally:
        client.close()
    reservations = [e["external_id"] for e in sync.entities() if e["resource_type"] == "reservation"]
    assert reservations == (["R1"] if included else [])
    assert any(p.startswith("/reservation/R1") for p, _ in seen) == included
    assert next(q for p, q in seen if p == "/reservation")["date_from"] == "2026-09-07"
    assert next(q for p, q in seen if p == "/financial-stats")["to"] == "2026-09-08"


def test_null_list_dates_filled_by_detail(db, wire):
    wire["/reservation"]["data"][0].update(arrival=None, departure=None)
    seen = []
    client = mock_client(wire, seen)
    try:
        SyncService(db, SettingsService(db)).full(client, scope=("2026-09-07", "2026-09-08"))
    finally:
        client.close()
    assert sum(p == "/reservation/R1" for p, _ in seen) == 1


def test_selected_reservation_keeps_older_related_invoice(db, wire):
    wire["/invoice"]["data"] = []
    wire["/invoice/I1"]["data"]["date"] = "2025-12-01T10:00:00Z"
    client = mock_client(wire, [])
    sync = SyncService(db, SettingsService(db))
    try:
        sync.full(client, scope=("2026-09-07", "2026-09-08"))
    finally:
        client.close()
    invoice = next(e for e in sync.entities() if e["resource_type"] == "invoice" and e["external_id"] == "I1")
    assert json.loads(invoice["payload_json"])["date"].startswith("2025-12-01")
    with db.connect() as c:
        assert c.execute("SELECT 1 FROM helper_link WHERE from_id='R1' AND to_id='I1' AND active=1").fetchone()


def test_booking_pairing_after_filtered_import(db, wire):
    from test_acceptance_traces import seed
    from kajovokarty.application.matching import MatchingService

    seed(db, "CASHBOOK_CARD")
    seed(db, "BOOKING")
    # R2 is returned by the server but falls outside the selected period.
    wire["/reservation/R2"]["data"].update(arrival="2025-12-01", departure="2025-12-02")
    client = mock_client(wire, [])
    settings = SettingsService(db)
    try:
        SyncService(db, settings).full(client, scope=("2026-09-07", "2026-09-08"))
    finally:
        client.close()
    assert MatchingService(db, settings).run()["created_groups"] == 1
    with db.connect() as c:
        assert c.execute("SELECT 1 FROM helper_current WHERE resource_type='reservation' AND external_id='R2' AND active=1").fetchone() is None


@pytest.mark.parametrize("dates", [{"arrival": None}, {"departure": None},
                                  {"arrival": "2026-09-09", "departure": "2026-09-08"}])
def test_invalid_stay_does_not_publish(db, wire, dates):
    sync = SyncService(db, SettingsService(db))
    client = mock_client(wire, [])
    try:
        sync.full(client, scope=("2026-09-07", "2026-09-08"))
        previous = sync.state()["published_generation_id"]
        wire["/reservation/R1"]["data"].update(dates)
        with pytest.raises(AppError):
            sync.full(client, scope=("2026-09-07", "2026-09-08"))
        assert sync.state()["published_generation_id"] == previous
        assert sync.state()["status"] == "STALE"
    finally:
        client.close()
