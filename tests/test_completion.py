"""Regression tests for the SSOT completion work; all API data is synthetic."""

import asyncio, copy, json, sqlite3, threading, time
from pathlib import Path
import httpx, pytest
from kajovokarty.domain.core import AppError, canonical, uid, now
from kajovokarty.infrastructure.betterhotel import (
    BetterHotelClient,
    TokenBucket,
    request_shape,
)
from kajovokarty.infrastructure.database import Database
from kajovokarty.application.settings import SettingsService
from kajovokarty.application.sync import SyncService
from kajovokarty.application.refresh import RefreshService
from kajovokarty.application.imports import ImportInput
from kajovokarty.application.work import WorkService
from kajovokarty.application.reports import ReportService, REPORTS
from kajovokarty.infrastructure.export import export, values
from kajovokarty.application.workspace import WorkspaceService, recover_backup
from kajovokarty.application.backup import BackupService
from test_api import client


def test_reservation_detail_contract(wire):
    seen = []
    http = client(wire, seen)
    try:
        http.detail("/reservation/{reservation_id}", {"reservation_id": "R1"})
        assert seen[0].url.params.get_list("expand[]") == [
            "reservation_source",
            "reservation_note",
        ]
        assert request_shape("/reservation/{reservation_id}") != request_shape(
            "/reservation"
        )
    finally:
        http.close()


def test_bucket_burst_and_refill():
    clock = [0.0]
    waits = []
    bucket = TokenBucket(2, clock=lambda: clock[0])

    def wait(seconds):
        waits.append(seconds)
        clock[0] += seconds

    for _ in range(10):
        bucket.acquire(wait)
    assert waits == []
    bucket.acquire(wait)
    bucket.acquire(wait)
    assert waits == [0.5, 0.5]
    clock[0] += 30
    for _ in range(10):
        bucket.acquire(wait)
    assert len(waits) == 2


@pytest.mark.parametrize(
    "retry_after,expected", [("61", "API_RATE_LIMIT"), ("NaN", None), ("invalid", None)]
)
def test_retry_after(retry_after, expected):
    calls = []
    waits = []

    def respond(r):
        calls.append(r)
        return (
            httpx.Response(429, headers={"Retry-After": retry_after})
            if len(calls) == 1
            else httpx.Response(200, json={"data": []})
        )

    http = BetterHotelClient("a", "b", transport=httpx.MockTransport(respond))
    http.wait = waits.append
    try:
        if expected:
            with pytest.raises(AppError, match="60"):
                http.collection("/currency")
            assert len(calls) == 1
        else:
            assert http.collection("/currency") == [] and waits == [1]
    finally:
        http.close()


def test_http_wall_deadline():
    async def slow(r):
        await asyncio.sleep(1)
        return httpx.Response(200, json={"data": []})

    http = BetterHotelClient(
        "a", "b", {"sync.retry_count": 0}, transport=httpx.MockTransport(slow)
    )
    http.attempt_deadline = 0.02
    start = time.monotonic()
    try:
        with pytest.raises(AppError) as error:
            http.collection("/currency")
        assert error.value.code == "API_NETWORK" and time.monotonic() - start < 0.5
    finally:
        http.close()


def test_schema_fail_cannot_be_overwritten():
    count = [0]

    def respond(r):
        count[0] += 1
        return httpx.Response(
            200,
            json={"data": [], "meta": {"has_more": "false"}}
            if count[0] == 1
            else {"data": [{"id": "2", "code": "EUR"}]},
        )

    http = BetterHotelClient("a", "b", transport=httpx.MockTransport(respond))
    try:
        with pytest.raises(AppError):
            http.collection("/currency")
        http.collection("/currency")
        assert http.stats["/currency"]["state"] == "FAIL"
    finally:
        http.close()


def test_detail_identical_graph_and_revision(db, wire):
    settings = SettingsService(db)
    sync = SyncService(db, settings)
    http = client(wire)
    try:
        sync.full(http, scope=("2026-09-07", "2026-09-08"))
        before = {
            (r["resource_type"], r["external_id"]): (r["revision"], r["content_hash"])
            for r in sync.entities(True)
        }
        RefreshService(db, settings).refresh(
            http, "reservation", "R1", sync.state()["context_id"]
        )
        after = {
            (r["resource_type"], r["external_id"]): (r["revision"], r["content_hash"])
            for r in sync.entities(True)
        }
        assert before == after
    finally:
        http.close()


def test_relation_snapshots_and_immutable_generation(db, wire):
    sync = SyncService(db, SettingsService(db))
    http = client(wire)
    try:
        sync.full(http, scope=("2026-09-07", "2026-09-08"))
    finally:
        http.close()
    with db.connect() as c:
        assert (
            c.execute(
                "SELECT count(*) FROM helper_link l JOIN helper_snapshot s ON s.id=l.snapshot_id WHERE s.projection_kind!='RELATION_EDGE'"
            ).fetchone()[0]
            == 0
        )
        assert (
            c.execute(
                "SELECT count(*) FROM helper_observation WHERE origin='RELATION'"
            ).fetchone()[0]
            > 0
        )
        assert (
            c.execute(
                "SELECT count(*) FROM helper_observation o JOIN helper_snapshot s ON s.id=o.snapshot_id WHERE s.projection_kind='MERGED_ENTITY'"
            ).fetchone()[0]
            == 0
        )
        with pytest.raises(sqlite3.IntegrityError):
            c.execute("UPDATE helper_current SET active=0")


def test_parent_conflict_keeps_pointer(db, wire):
    wire = copy.deepcopy(wire)
    wire["/reservation/R1/bill"] = {"data": [{"id": "B1"}]}
    wire["/bill/B1"] = {"id": "B1", "currency": "EUR", "reservation_id": "R1"}
    wire["/bill/B1/bill-item"] = {"data": [{"id": "X"}]}
    wire["/bill-item/X"] = {
        "id": "X",
        "bill_id": "B1",
        "currency": "EUR",
        "amount": "1",
    }
    settings = SettingsService(db)
    sync = SyncService(db, settings)
    http = client(wire)
    try:
        sync.full(http, scope=("2026-09-07", "2026-09-08"))
    finally:
        http.close()
    st = sync.state()
    wire["/bill-item/X"]["bill_id"] = "OTHER"
    http = client(wire)
    try:
        with pytest.raises(AppError):
            RefreshService(db, settings).refresh(
                http, "bill_item", "X", st["context_id"]
            )
        assert (
            sync.state()["published_generation_id"] == st["published_generation_id"]
            and sync.state()["status"] == "STALE"
        )
    finally:
        http.close()


def test_selected_export_ignores_filter(importer, fixtures):
    importer.commit(
        importer.preflight([ImportInput("BOOKING", str(fixtures / "booking_a.csv"))]).id
    )
    work = WorkService(importer.db)
    sid = work.query()["ids"][0]
    data = ReportService(importer.db).build("unresolved", [sid], {"text": "no-match"})
    assert [r["object_id"] for r in data["work_objects"]] == [sid]
    assert (
        dict((r["key"], r["value_json"]) for r in data["metadata"])["selection_mode"]
        == "SELECTION"
    )


def test_helper_historical_scope_and_closure(db, wire):
    settings = SettingsService(db)
    sync = SyncService(db, settings)
    http = client(wire)
    try:
        sync.full(http, scope=("2026-09-07", "2026-09-08"))
    finally:
        http.close()
    st = sync.state()
    report = ReportService(db)
    data = report.build("helpers", ["R1"])
    assert {"R1", "I1"} <= {r["external_id"] for r in data["helper_entities"]}
    assert all(r["projection_kind"] == "MERGED_ENTITY" for r in data["helper_entities"])
    with db.transaction() as c:
        c.execute("UPDATE helper_state SET status='STALE'")
    data = report.build("helpers", ["R1"])
    assert not any(r["usable_for_new_auto"] for r in data["helper_entities"])
    assert all(
        r["resolution_status"] != "INACTIVE_CONTEXT_OR_ENTITY"
        for r in data["helper_references"]
    )
    assert {
        tuple(r["value_json"][0].values())
        for r in data["metadata"]
        if r["key"] == "selected_helper_graphs"
    } == {(st["context_id"], st["published_generation_id"])}


def test_all_report_values_and_empty_schemas(db, wire, tmp_path):
    sync = SyncService(db, SettingsService(db))
    http = client(wire)
    try:
        sync.full(http, True, scope=("2026-09-07", "2026-09-08"))
    finally:
        http.close()
    with db.connect() as c:
        run = c.execute("SELECT id FROM api_compatibility_run").fetchone()[0]
    for report in REPORTS:
        if report == "group_evidence":
            continue
        data = ReportService(db).build(
            report, [run] if report == "api_compatibility" else None
        )
        for dataset, rows in data.items():
            for row in rows:
                values(dataset, row)
        export(data, "zip", tmp_path / (report + ".zip"))


def test_export_cancel_preserves_existing(db, tmp_path):
    data = ReportService(db).build("unresolved")
    target = tmp_path / "out.zip"
    target.write_bytes(b"previous")
    event = threading.Event()
    event.set()
    with pytest.raises(AppError):
        export(data, "zip", target, cancel=event)
    assert target.read_bytes() == b"previous"


def test_settings_atomic_and_proxy_secrets(db):
    class Protector:
        def encrypt(self, b):
            return b[::-1]

        def decrypt(self, b):
            return b[::-1]

    settings = SettingsService(db, Protector())
    with pytest.raises(AppError):
        settings.save_all({"sync.block_days": 8}, ("bad\ntoken", "b"))
    assert settings.get()["sync.block_days"] == 7
    old = SyncService(db, settings).state()["context_id"]
    settings.save_all(
        {"sync.block_days": 8},
        ("access-secret", "client-secret"),
        ("user", "proxy-secret"),
    )
    assert settings.tokens() == (
        "access-secret",
        "client-secret",
    ) and settings.proxy_auth() == ("user", "proxy-secret")
    assert SyncService(db, settings).state()["context_id"] != old
    with db.connect() as c:
        assert "proxy-secret" not in canonical(
            [dict(r) for r in c.execute("SELECT * FROM audit_event")]
        )
        assert not any(
            "secret" in r["value_json"] for r in c.execute("SELECT * FROM setting")
        )


def test_move_verified_and_original_kept(importer, fixtures, tmp_path):
    importer.commit(
        importer.preflight([ImportInput("BOOKING", str(fixtures / "booking_a.csv"))]).id
    )
    target = tmp_path / "new-workspace"
    pointer = tmp_path / "pointer.json"
    WorkspaceService(importer.db, pointer).move(target)
    assert importer.db.path.is_file() and json.loads(
        pointer.read_text(encoding="utf-8")
    )["data_directory"] == str(target)
    moved = Database(target / "kajovokarty.sqlite")
    assert len(WorkService(moved).query()["ids"]) == 21
    with pytest.raises(AppError):
        WorkspaceService(importer.db, pointer).move(target)


def test_recovery_of_corrupted_database(importer, fixtures, tmp_path):
    importer.commit(
        importer.preflight([ImportInput("BOOKING", str(fixtures / "booking_a.csv"))]).id
    )
    backup = tmp_path / "recover.zip"
    BackupService(importer.db).backup(backup)
    damaged = tmp_path / "broken"
    damaged.mkdir()
    (damaged / "kajovokarty.sqlite").write_bytes(b"damaged database")
    recover_backup(backup, damaged)
    recovered = Database(damaged / "kajovokarty.sqlite")
    assert len(WorkService(recovered).query()["ids"]) == 21
    assert (
        list(damaged.glob("before-recovery-*/kajovokarty.sqlite"))[0].read_bytes()
        == b"damaged database"
    )


def test_v1_migration_creates_verified_backup(tmp_path, fixtures):
    import zipfile

    # The input delivery contains schema v1; make a v1 database with that code in a subprocess.
    path = tmp_path / "old.sqlite"
    c = sqlite3.connect(path)
    c.executescript(
        (Path(__file__).parents[1] / "src/kajovokarty/migrations/001.sql").read_text(
            encoding="utf-8"
        )
    )
    ctx = uid()
    c.execute("INSERT INTO helper_context VALUES(?,'CURRENT',0,?,NULL)", (ctx, now()))
    c.execute(
        "INSERT INTO helper_state VALUES(1,?,NULL,'UNAVAILABLE',NULL,0,0,1,NULL,'{}',NULL,NULL)",
        (ctx,),
    )
    c.execute("PRAGMA user_version=1")
    c.commit()
    c.close()
    migrated = Database(path)
    with migrated.connect() as c:
        assert c.execute("PRAGMA user_version").fetchone()[0] == 2
    archives = list(tmp_path.glob("before-migration*.zip"))
    assert len(archives) == 1
    with zipfile.ZipFile(archives[0]) as z:
        assert json.loads(z.read("manifest.json"))["schema"] == 1


def test_work_filters_or_literal_and_sources_all(importer, fixtures):
    importer.commit(
        importer.preflight(
            [
                ImportInput("BOOKING", str(fixtures / "booking_a.csv")),
                ImportInput("BANK_CARD", str(fixtures / "terminal.xlsx")),
            ]
        ).id
    )
    work = WorkService(importer.db)
    rows = work.query({"status": "all"}, page_size=0)["rows"]
    euro = [r for r in rows if r["currency"] == "EUR"]
    a = next(r for r in euro if r["kinds"] == ["BOOKING"])
    b = next(r for r in euro if r["kinds"] == ["BANK_CARD"])
    group = work.create_group([a["id"], b["id"]], {a["id"]: 1, b["id"]: 1})
    assert work.query(
        {"status": "all", "kind": ["BOOKING", "BANK_CARD"], "kind_mode": "all"}
    )["ids"] == [group["id"]]
    assert work.query({"text": "%_not_a_wildcard"})["total"] == 0
    refs = [r["primary_identifier"] for r in rows if r["kinds"] == ["BOOKING"]][:2]
    assert len(work.query({"status": "all", "booking_reference": refs})["ids"]) == 2


def test_parent_currency_and_helper_code_not_guessed(db, wire):
    wire = copy.deepcopy(wire)
    wire["/invoice"]["data"][0].pop("code")
    wire["/invoice/I1"]["data"].pop("code")
    http = client(wire)
    sync = SyncService(db, SettingsService(db))
    try:
        sync.full(http, scope=("2026-09-07", "2026-09-08"))
    finally:
        http.close()
    assert "code" not in json.loads(
        next(r for r in sync.entities() if r["external_id"] == "I1")["payload_json"]
    )


def test_membership_fault_rolls_back_all(importer, fixtures, monkeypatch):
    importer.commit(
        importer.preflight([ImportInput("BOOKING", str(fixtures / "booking_a.csv"))]).id
    )
    work = WorkService(importer.db)
    rows = work.query()["rows"][:2]
    before = work.query()["ids"]

    def fault(c):
        raise OSError("injected disk failure before commit")

    monkeypatch.setattr(importer.db, "validate", fault)
    with pytest.raises(OSError):
        work.create_group([r["id"] for r in rows], {r["id"]: 1 for r in rows})
    assert work.query()["ids"] == before
    with importer.db.connect() as c:
        assert c.execute("SELECT count(*) FROM membership").fetchone()[0] == 0


def test_export_rename_failure_preserves_previous(db, tmp_path, monkeypatch):
    import kajovokarty.infrastructure.export as module

    path = tmp_path / "out.zip"
    path.write_bytes(b"old")

    def fail(*args):
        raise OSError("injected rename failure")

    monkeypatch.setattr(module.os, "replace", fail)
    with pytest.raises(OSError):
        module.export(ReportService(db).build("unresolved"), "zip", path)
    assert path.read_bytes() == b"old" and not list(tmp_path.glob(".kk-export-*"))


def test_context_and_snapshot_identity_guards(db, wire):
    http = client(wire)
    sync = SyncService(db, SettingsService(db))
    try:
        sync.full(http, scope=("2026-09-07", "2026-09-08"))
    finally:
        http.close()
    with db.connect() as c:
        before = c.execute("SELECT count(*) FROM helper_current").fetchone()[0]
        with pytest.raises(sqlite3.IntegrityError):
            c.execute("UPDATE helper_state SET credential_revision=999")
        with pytest.raises(sqlite3.IntegrityError):
            c.execute(
                "UPDATE helper_current SET snapshot_id=(SELECT snapshot_id FROM helper_current WHERE resource_type='currency' LIMIT 1) WHERE resource_type='invoice'"
            )
        assert c.execute("SELECT count(*) FROM helper_current").fetchone()[0] == before


def test_diagnostic_sanitizes_technical_logs(db, tmp_path):
    from kajovokarty.application.backup import BackupService
    import zipfile, json

    folder = db.path.parent / "logs"
    folder.mkdir()
    (folder / "2026-09-10.jsonl").write_text(
        json.dumps(
            {
                "endpoint_template": "/invoice",
                "http_status": 200,
                "elapsed_ms": 12,
                "error_code": "API_SCHEMA",
                "payload": "SECRET_PERSON",
                "token": "SECRET_TOKEN",
                "correlation_id": "SECRET_PATH",
            }
        )
        + "\n"
    )
    out = tmp_path / "diagnostic.zip"
    BackupService(db).diagnostic(out)
    with zipfile.ZipFile(out) as z:
        data = b"".join(z.read(n) for n in z.namelist())
        assert b"SECRET" not in data
        assert b"API_SCHEMA" in data and b"domain_invariants" in data
