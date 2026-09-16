"""Regression tests for the SSOT completion work; all API data is synthetic."""

import json, sqlite3, threading
from pathlib import Path
import pytest
from kajovokarty.domain.core import AppError, canonical, uid, now
from kajovokarty.infrastructure.database import Database
from kajovokarty.application.settings import SettingsService
from kajovokarty.application.sync import SyncService
from kajovokarty.application.imports import ImportInput
from kajovokarty.application.work import WorkService
from kajovokarty.application.reports import ReportService, REPORTS
from kajovokarty.infrastructure.export import export, values
from kajovokarty.application.workspace import WorkspaceService, recover_backup
from kajovokarty.application.backup import BackupService


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


def test_all_report_values_and_empty_schemas(db, wire, tmp_path):
    for report in REPORTS:
        if report in ("group_evidence", "api_compatibility"):
            continue
        data = ReportService(db).build(
            report
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
        assert c.execute("PRAGMA user_version").fetchone()[0] == 4
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


def test_diagnostic_sanitizes_technical_logs(db, tmp_path):
    from kajovokarty.application.backup import BackupService
    import zipfile, json

    folder = db.path.parent / "logs"
    folder.mkdir(exist_ok=True)
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
