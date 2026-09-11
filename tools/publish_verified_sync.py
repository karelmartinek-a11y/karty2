"""Publish recorded BetterHotel responses through the current importer, after backup.

This is an explicitly invoked maintenance action, never part of verification.
It replays API data into the current database instead of restoring an old copy.
"""
import json
import sqlite3
import time
from pathlib import Path

from PySide6.QtCore import QLockFile
from kajovokarty.application.backup import BackupService
from kajovokarty.application.settings import SettingsService
from kajovokarty.application.sync import SyncService
from kajovokarty.domain.core import digest, require, uid
from kajovokarty.infrastructure.database import Database
from verify_live_sync import RecordedClient


PRESERVED_TABLES = (
    "financial_source", "cashbook_detail", "bank_detail", "booking_detail",
    "work_object", "reconciliation_group", "membership", "auto_suppression",
    "helper_override", "setting",
)


def preserved_hashes(db):
    with db.connect() as c:
        return {table: digest([list(row) for row in c.execute(
            f'SELECT * FROM "{table}" ORDER BY 1'
        )]) for table in PRESERVED_TABLES}


def publish(source, verification, client_factory=RecordedClient):
    source, verification = Path(source).resolve(), Path(verification).resolve()
    verified_db = verification / "verification.sqlite"
    require(source.is_file() and verified_db.is_file() and source != verified_db,
            "STALE_STATE", "Chybí samostatná ověřená databáze nebo cílová databáze.")
    require((verification / "responses.sqlite").is_file(),
            "STALE_STATE", "Chybí zachycené odpovědi API.")
    lock = QLockFile(str(source.parent / "application.lock"))
    lock.setStaleLockTime(0)
    require(lock.tryLock(0), "DB_BUSY", "Před uložením dat zavřete program KájovoKarty.")
    try:
        with sqlite3.connect(verified_db.as_uri() + "?mode=ro", uri=True) as c:
            c.row_factory = sqlite3.Row
            verified = dict(c.execute("SELECT * FROM helper_state").fetchone())
            operation = c.execute("SELECT state FROM operation WHERE id=?",
                                  (verified["operation_id"],)).fetchone()
            require(verified["status"] == "READY" and operation
                    and operation[0] == "COMPLETED", "STALE_STATE",
                    "Ověřovací import ještě není úspěšně dokončený.")
        db = Database(source)
        settings = SettingsService(db)
        sync = SyncService(db, settings)
        current = sync.state()
        require(all(current[key] == verified[key] for key in
                    ("context_id", "credential_revision")), "API_CONTEXT_CHANGED",
                "Připojení se od ověření změnilo; zachycená data nelze převzít.")
        require(current["status"] != "REFRESHING", "DB_BUSY", "Probíhá jiný import.")
        scope = sync.scope()
        require(json.loads(verified["planned_scope_json"]) == dict(zip(("start", "end"), scope)),
                "STALE_STATE", "Nastavené období se od ověření změnilo.")
        before = preserved_hashes(db)
        backup = source.parent / "backups" / ("before-verified-sync-" + uid() + ".zip")
        BackupService(db).backup(backup)
        folder = source.parent / "diagnostics" / ("verified-sync-" + uid())
        folder.mkdir(parents=True)
        last = 0.0

        def progress(event):
            nonlocal last
            if isinstance(event, dict) and event.get("type") == "sync_progress":
                if time.monotonic() - last > 30 or event["phase"] == "completed":
                    print(event["phase"], event["completed"], "/", event.get("total"), flush=True)
                    last = time.monotonic()

        access, token = settings.tokens()
        client = client_factory(access, token, settings.get(), proxy_auth=settings.proxy_auth(),
                                progress=progress, evidence=folder / "responses.sqlite",
                                replay=verification / "responses.sqlite")
        try:
            result = sync.full(client, progress=progress)
        finally:
            client.close()
        with db.connect() as c:
            result["operation_state"] = c.execute("SELECT state FROM operation WHERE id=?",
                                                   (result["operation_id"],)).fetchone()[0]
            result["integrity"] = c.execute("PRAGMA integrity_check").fetchone()[0]
            result["foreign_keys_ok"] = not c.execute("PRAGMA foreign_key_check").fetchall()
        result["preserved_tables_unchanged"] = before == preserved_hashes(db)
        result["backup"] = str(backup)
        result["verification_mode"] = "recorded-api-with-live-misses"
        result["live_requests"] = sum(len(s.get("status_codes", [])) for s in client.stats.values())
        (folder / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        require(result["status"] == "READY" and result["operation_state"] == "COMPLETED"
                and result["integrity"] == "ok" and result["foreign_keys_ok"]
                and result["preserved_tables_unchanged"], "DATABASE_INVALID",
                "Závěrečná kontrola převzetí dat selhala.")
        return result
    finally:
        lock.unlock()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("verification", type=Path)
    args = parser.parse_args()
    print(json.dumps(publish(args.source, args.verification)), flush=True)
