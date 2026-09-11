import copy, json
import httpx, pytest
from kajovokarty.application.settings import SettingsService
from kajovokarty.application.sync import SyncService
from kajovokarty.infrastructure.betterhotel import BetterHotelClient, BASE
from kajovokarty.domain.core import AppError


def client(wire, requests=None):
    def respond(request):
        assert request.method == "GET"
        assert str(request.url).startswith(BASE + "/")
        assert (
            request.headers["X-Access-Token"] == "test-access"
            and request.headers["X-Client-Token"] == "test-client"
        )
        assert "authorization" not in request.headers
        path = request.url.path[len("/api/connector/v/1") :]
        if requests is not None:
            requests.append(request)
        if path == "/invoice":
            assert request.url.params["filter[date_from]"] == "2026-09-07"
        if path == "/reservation":
            assert request.url.params.get_list("expand[]") == [
                "reservation_source",
                "reservation_note",
            ]
        return httpx.Response(200, json=wire[path])

    result = BetterHotelClient(
        "test-access", "test-client", transport=httpx.MockTransport(respond)
    )
    result.wait = lambda seconds: None
    return result


def test_full_and_empty(db, wire):
    sync = SyncService(db, SettingsService(db))
    http = client(wire)
    r = sync.full(http, True, scope=("2026-09-07", "2026-09-08"))
    assert r["status"] == "READY"
    assert len(sync.entities()) == 6
    with db.connect() as c:
        assert (
            c.execute("SELECT status FROM api_compatibility_run").fetchone()[0]
            == "PARTIAL"
        )
    http.close()
    empty = {
        "/currency": wire["/currency"],
        "/invoice": {"data": []},
        "/reservation": {"data": []},
        "/financial-stats": {"data": {}},
    }
    http = client(empty)
    sync.full(http, scope=("2026-09-07", "2026-09-08"))
    assert len(sync.entities()) == 2
    assert len(sync.entities(True)) == 6
    http.close()


def test_failed_projection_preserves_graph(db, wire):
    sync = SyncService(db, SettingsService(db))
    http = client(wire)
    sync.full(http, scope=("2026-09-07", "2026-09-08"))
    before = sync.state()["published_generation_id"]
    http.close()
    wrong = copy.deepcopy(wire)
    wrong["/reservation/R1"]["data"]["code"] = "999"
    http = client(wrong)
    with pytest.raises(AppError) as e:
        sync.full(http, scope=("2026-09-07", "2026-09-08"))
    assert e.value.code == "API_SNAPSHOT_CONFLICT"
    assert sync.state()["status"] == "STALE"
    assert sync.state()["published_generation_id"] == before
    http.close()


def test_detail_chain(db, wire):
    wire = copy.deepcopy(wire)
    wire["/reservation/R1/bill"] = {"data": [{"id": "B1"}]}
    wire["/bill/B1"] = {
        "id": "B1",
        "currency": "2",
        "total": "50.00",
        "balance": "0.00",
        "is_closed": True,
    }
    wire["/bill/B1/bill-item"] = {"data": [{"id": "BI1"}]}
    wire["/bill-item/BI1"] = {"id": "BI1", "amount": "50.00", "currency": "2"}
    wire["/reservation/R1/security-deposit"] = {
        "data": [{"id": "SD1", "amount": "20.00", "currency": "2", "status": "held"}]
    }
    sync = SyncService(db, SettingsService(db))
    http = client(wire)
    sync.full(http, True, scope=("2026-09-07", "2026-09-08"))
    assert len(sync.entities()) == 9
    http.close()


@pytest.mark.parametrize(
    "status,code",
    [(401, "API_AUTH"), (403, "API_AUTH"), (302, "API_HTTP"), (204, "API_HTTP")],
)
def test_no_retry_for_bad_status(status, code):
    calls = []

    def respond(r):
        calls.append(r)
        return httpx.Response(status, headers={"location": "https://evil.example/"})

    http = BetterHotelClient("a", "b", transport=httpx.MockTransport(respond))
    http.wait = lambda s: None
    with pytest.raises(AppError) as e:
        http.collection("/currency")
    assert e.value.code == code and len(calls) == 1
    http.close()


def test_cursor_cycle():
    http = BetterHotelClient(
        "a",
        "b",
        transport=httpx.MockTransport(
            lambda r: httpx.Response(
                200, json={"data": [], "meta": {"has_more": True, "cursor": "same"}}
            )
        ),
    )
    http.wait = lambda s: None
    with pytest.raises(AppError) as e:
        http.collection("/currency")
    assert e.value.code == "API_CURSOR_CYCLE"
    http.close()


def test_context_switch(db):
    class Protector:
        def encrypt(self, b):
            return b[::-1]

        def decrypt(self, b):
            return b[::-1]

    settings = SettingsService(db, Protector())
    states = []
    for a, b in [("A", "A"), ("B", "B"), ("A", "A")]:
        settings.save_tokens(a, b)
        states.append(SyncService(db, settings).state()["context_id"])
    assert len(set(states)) == 3
    settings.save_tokens("A", "A")
    assert SyncService(db, settings).state()["context_id"] == states[-1]


def test_override_undo(db, wire):
    from kajovokarty.application.overrides import OverrideService
    from kajovokarty.application.work import WorkService

    settings = SettingsService(db)
    sync = SyncService(db, settings)
    http = client(wire)
    sync.full(http, scope=("2026-09-07", "2026-09-08"))
    ctx = sync.state()["context_id"]
    o = OverrideService(db)
    r = o.inspect(ctx, "R1")
    cmd = o.decide(ctx, "R1", "REJECT", None, 0, r["reference"]["candidate_set_hash"])
    assert o.inspect(ctx, "R1")["decision"]["resolution_status"] == "REJECTED"
    WorkService(db).undo(cmd)
    assert o.inspect(ctx, "R1")["decision"]["resolution_status"] == "AUTO_CONFIRMED"
    WorkService(db).undo(cmd, True)
    assert o.inspect(ctx, "R1")["decision"]["resolution_status"] == "REJECTED"
    http.close()


def test_detail_refresh_and_pruning(db, wire):
    from kajovokarty.application.refresh import RefreshService

    settings = SettingsService(db)
    sync = SyncService(db, settings)
    http = client(wire)
    sync.full(http, scope=("2026-09-07", "2026-09-08"))
    ctx = sync.state()["context_id"]
    old = sync.state()["published_generation_id"]
    changed = copy.deepcopy(wire)
    changed["/reservation/R1"]["data"]["reservation_note"] = [
        {"channel": "Original ID: 1234567899"}
    ]
    http.close()
    http = client(changed)
    result = RefreshService(db, settings).refresh(http, "reservation", "R1", ctx)
    assert result["published"]
    assert (
        sync.state()["published_generation_id"] != old
        and sync.state()["status"] == "READY"
    )
    http.close()


def test_stale_detail_is_preview(db, wire):
    from kajovokarty.application.refresh import RefreshService

    settings = SettingsService(db)
    sync = SyncService(db, settings)
    http = client(wire)
    sync.full(http, scope=("2026-09-07", "2026-09-08"))
    ctx = sync.state()["context_id"]
    old = sync.state()["published_generation_id"]
    with db.transaction() as c:
        c.execute("UPDATE helper_state SET status='STALE'")
    result = RefreshService(db, settings).refresh(http, "reservation", "R1", ctx)
    assert not result["published"]
    assert (
        sync.state()["status"] == "STALE"
        and sync.state()["published_generation_id"] == old
    )
    http.close()


@pytest.mark.parametrize("restart_reason", [None, "old_contract", "changed_setting"])
def test_resume_completed_block(db, wire, restart_reason):
    settings = SettingsService(db)
    settings.save({"sync.block_days": 1})
    sync = SyncService(db, settings)
    seen = []

    def respond(request):
        path = request.url.path[len("/api/connector/v/1") :]
        seen.append((path, str(request.url.params)))
        if (
            path == "/invoice"
            and request.url.params["filter[date_from]"] == "2026-09-08"
        ):
            return httpx.Response(503)
        return httpx.Response(200, json=wire[path])

    http = BetterHotelClient(
        "a", "b", {"sync.retry_count": 0}, transport=httpx.MockTransport(respond)
    )
    http.wait = lambda s: None
    with pytest.raises(AppError):
        sync.full(http, scope=("2026-09-07", "2026-09-08"))
    with db.connect() as c:
        op = c.execute("SELECT id FROM operation WHERE type='SYNC'").fetchone()[0]
    http.close()
    if restart_reason == "old_contract":
        with db.transaction() as c:
            checkpoint = json.loads(c.execute("SELECT recovery_json FROM operation WHERE id=?", (op,)).fetchone()[0])
            checkpoint.pop("selection_contract")
            c.execute("UPDATE operation SET recovery_json=? WHERE id=?", (json.dumps(checkpoint), op))
    elif restart_reason == "changed_setting":
        settings.save({"sync.start_date": "2026-02-01"})
    # Keep this transport contract test to two days, including restarted runs.
    sync.scope = lambda: ("2026-09-07", "2026-09-08")
    seen = []

    def success(request):
        path = request.url.path[len("/api/connector/v/1") :]
        seen.append((path, dict(request.url.params)))
        return httpx.Response(200, json=wire[path])

    http = BetterHotelClient("a", "b", transport=httpx.MockTransport(success))
    http.wait = lambda s: None
    sync.resume(http, op)
    assert sync.state()["status"] == "READY"
    assert any(params.get("filter[date_from]") == "2026-09-07" for path, params in seen) == bool(restart_reason)
    assert any(path == "/currency" for path, params in seen) == bool(restart_reason)
    http.close()
