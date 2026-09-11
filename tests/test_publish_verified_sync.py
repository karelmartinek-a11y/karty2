import sqlite3
import json
import httpx
import sys
from pathlib import Path

import pytest
from PySide6.QtCore import QLockFile
from kajovokarty.application.settings import SettingsService
from kajovokarty.application.sync import SyncService
from kajovokarty.application.work import WorkService
from kajovokarty.domain.core import AppError
from kajovokarty.infrastructure.database import Database
from test_acceptance_traces import seed
from test_sync_period import mock_client

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
from publish_verified_sync import publish, preserved_hashes
from verify_live_sync import RecordedClient


def test_replayed_evidence_is_durable_after_close(tmp_path):
    source = tmp_path / "recorded.sqlite"
    target = tmp_path / "replayed.sqlite"
    body = {"data": [{"id": "1", "iso_code": "EUR"}]}
    with sqlite3.connect(source) as c:
        c.execute("CREATE TABLE response(key TEXT PRIMARY KEY,body TEXT)")
        c.execute("INSERT INTO response VALUES(?,?)", (json.dumps(["/currency", None, None]), json.dumps(body)))
    client = RecordedClient("access", "client", evidence=target, replay=source,
                            transport=httpx.MockTransport(lambda r: pytest.fail("Must use recorded response")))
    try:
        assert client.get("/currency") == body
        assert client.evidence_class == "RECORDED_API_WITH_LIVE_MISSES"
    finally:
        client.close()
    with sqlite3.connect(target) as c:
        assert json.loads(c.execute("SELECT body FROM response").fetchone()[0]) == body


@pytest.fixture
def verified(db, wire, tmp_path, monkeypatch):
    monkeypatch.setattr(SyncService, "scope", lambda self: ("2026-09-07", "2026-09-08"))
    monkeypatch.setattr(SettingsService, "tokens", lambda self: ("access", "client"))
    folder = tmp_path / "verified"
    folder.mkdir()
    with db.connect() as source, sqlite3.connect(folder / "verification.sqlite") as target:
        source.backup(target)
    isolated = Database(folder / "verification.sqlite")
    http = mock_client(wire, [])
    try:
        SyncService(isolated, SettingsService(isolated)).full(http)
    finally:
        http.close()
    (folder / "responses.sqlite").touch()
    return folder, isolated


def test_publication_preserves_changes_made_after_verification(db, verified, wire):
    folder, isolated = verified
    # These financial rows and this group never existed in the verification copy.
    a = seed(db, "CASHBOOK_CARD")
    b = seed(db, "BANK_CARD")
    WorkService(db).create_group([a, b], {a: 1, b: 1})
    before = preserved_hashes(db)
    result = publish(db.path, folder, lambda *args, **kwargs: mock_client(wire, []))
    assert result["status"] == "READY" and result["operation_state"] == "COMPLETED"
    assert result["integrity"] == "ok" and result["foreign_keys_ok"]
    assert result["preserved_tables_unchanged"] and before == preserved_hashes(db)
    assert Path(result["backup"]).is_file()
    with db.connect() as c:
        assert c.execute("SELECT count(*) FROM reconciliation_group").fetchone()[0] == 1
        assert c.execute("SELECT count(*) FROM helper_current WHERE active=1").fetchone()[0] > 0


@pytest.mark.parametrize("problem,code", [
    ("unfinished", "STALE_STATE"), ("context", "API_CONTEXT_CHANGED"),
    ("scope", "STALE_STATE"), ("locked", "DB_BUSY"),
])
def test_publication_rejects_unverified_or_changed_target(db, verified, problem, code):
    folder, isolated = verified
    lock = None
    if problem == "locked":
        lock = QLockFile(str(db.path.parent / "application.lock"))
        assert lock.tryLock(0)
    else:
        with isolated.transaction() as c:
            if problem == "unfinished":
                c.execute("UPDATE operation SET state='RUNNING' WHERE type='SYNC'")
            elif problem == "context":
                with db.transaction() as current:
                    current.execute("UPDATE helper_context SET credential_revision=credential_revision+1")
                    current.execute("UPDATE helper_state SET credential_revision=credential_revision+1")
            else:
                c.execute("UPDATE helper_state SET planned_scope_json='{}'")
    before = preserved_hashes(db)
    try:
        with pytest.raises(AppError) as error:
            publish(db.path, folder, lambda *a, **k: pytest.fail("Must not start import"))
        assert error.value.code == code
        assert before == preserved_hashes(db)
        assert SyncService(db, SettingsService(db)).state()["published_generation_id"] is None
    finally:
        if lock:
            lock.unlock()
