from __future__ import annotations
from contextlib import contextmanager
from pathlib import Path
import sqlite3, threading, time
from kajovokarty.domain.core import (
    AppError,
    bytehash,
    canonical,
    now,
    require,
    uid,
    search_normalize,
)


class Database:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.gate = threading.RLock()
        with self.connect() as c:
            version = c.execute("PRAGMA user_version").fetchone()[0]
            require(
                version <= 2,
                "SCHEMA_NEWER",
                "Databáze pochází z novější verze programu.",
            )
            if version == 0:
                sql = (Path(__file__).parents[1] / "migrations/001.sql").read_text()
                c.executescript("BEGIN IMMEDIATE;\n" + sql)
                for table in (
                    "financial_source",
                    "cashbook_detail",
                    "bank_detail",
                    "booking_detail",
                    "source_file",
                    "audit_event",
                    "group_history",
                ):
                    for action in ("UPDATE", "DELETE"):
                        c.execute(
                            f"CREATE TRIGGER immutable_{table}_{action} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT,'IMMUTABLE'); END"
                        )
                for action in ("INSERT", "UPDATE"):
                    c.execute(f"""CREATE TRIGGER membership_guard_{action} BEFORE {action} ON membership WHEN NEW.active=1 BEGIN
                    SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM work_object p,work_object c WHERE p.id=NEW.parent_id AND c.id=NEW.child_id AND p.type='GROUP' AND p.lifecycle='ACTIVE' AND c.lifecycle='ACTIVE' AND p.currency=c.currency) THEN RAISE(ABORT,'MEMBERSHIP_INVALID') END;
                    SELECT CASE WHEN EXISTS(WITH RECURSIVE descendants(id) AS (SELECT NEW.child_id UNION SELECT m.child_id FROM membership m JOIN descendants d ON m.parent_id=d.id WHERE m.active=1) SELECT 1 FROM descendants WHERE id=NEW.parent_id) THEN RAISE(ABORT,'CYCLE_DETECTED') END;
                    END""")
                for table in (
                    "helper_current",
                    "helper_link",
                    "helper_reference",
                    "sync_coverage",
                ):
                    for action in ("INSERT", "UPDATE", "DELETE"):
                        ref = "NEW" if action == "INSERT" else "OLD"
                        c.execute(
                            f"CREATE TRIGGER sealed_{table}_{action} BEFORE {action} ON {table} WHEN (SELECT state FROM helper_generation WHERE id={ref}.generation_id) IN ('SEALED','PUBLISHED') BEGIN SELECT RAISE(ABORT,'GENERATION_IMMUTABLE'); END"
                        )
                for action in ("UPDATE", "DELETE"):
                    c.execute(
                        f"CREATE TRIGGER immutable_helper_snapshot_{action} BEFORE {action} ON helper_snapshot BEGIN SELECT RAISE(ABORT,'IMMUTABLE'); END"
                    )
                c.execute(
                    "INSERT INTO schema_migration VALUES(1,?,?,?)",
                    (now(), "0.1.0", bytehash(sql.encode())),
                )
                ctx = uid()
                c.execute(
                    "INSERT INTO helper_context VALUES(?,?,0,?,NULL)",
                    (ctx, "CURRENT", now()),
                )
                c.execute(
                    "INSERT INTO helper_state VALUES(1,?,NULL,'UNAVAILABLE',NULL,0,0,1,NULL,'{}',NULL,NULL)",
                    (ctx,),
                )
                c.execute("PRAGMA user_version=1")
                c.commit()
            if version == 1:
                self._migration_backup(c)
            if version < 2:
                sql = (Path(__file__).parents[1] / "migrations/002.sql").read_text()
                try:
                    c.executescript("BEGIN IMMEDIATE;\n" + sql)
                    c.execute(
                        "INSERT INTO schema_migration VALUES(2,?,?,?)",
                        (now(), "0.2.0", bytehash(sql.encode())),
                    )
                    c.execute("PRAGMA user_version=2")
                    c.commit()
                except BaseException:
                    c.rollback()
                    raise
            require(
                c.execute("PRAGMA quick_check").fetchone()[0] == "ok",
                "DATABASE_INVALID",
                "Databáze neprošla kontrolou integrity; použijte obnovu zálohy.",
            )

    def _migration_backup(self, source):
        import json, os, tempfile, zipfile

        with tempfile.TemporaryDirectory(dir=self.path.parent) as folder:
            candidate = Path(folder) / "database.sqlite"
            with sqlite3.connect(candidate) as dest:
                source.backup(dest)
                dest.execute("PRAGMA journal_mode=DELETE")
                dest.execute("PRAGMA secure_delete=ON")
                dest.execute("DELETE FROM secret")
                dest.commit()
                dest.execute("VACUUM")
                require(
                    dest.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
                    and not dest.execute("PRAGMA foreign_key_check").fetchall(),
                    "DATABASE_INVALID",
                    "Předmigrační zálohu nelze ověřit.",
                )
            raw = candidate.read_bytes()
            manifest = {
                "schema": 1,
                "app_build": "0.2.0",
                "created_at": now(),
                "files": {"database.sqlite": bytehash(raw)},
                "secrets_included": False,
            }
            archive = Path(folder) / "backup.zip"
            with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
                z.writestr("database.sqlite", raw)
                z.writestr("manifest.json", json.dumps(manifest))
            os.replace(
                archive, self.path.parent / ("before-migration-1-2-" + uid() + ".zip")
            )

    @contextmanager
    def connect(self):
        c = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        c.row_factory = sqlite3.Row
        c.create_function(
            "kk_search_normalize", 1, search_normalize, deterministic=True
        )
        c.execute("PRAGMA foreign_keys=ON")
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=FULL")
        c.execute("PRAGMA busy_timeout=5000")
        try:
            yield c
        finally:
            c.close()

    @contextmanager
    def operation_gate(self, cancel=None, progress=None):
        start = time.monotonic()
        announced = False
        while not self.gate.acquire(timeout=0.1):
            require(
                not (cancel and cancel.is_set()),
                "CANCELLED",
                "Čekání na operaci bylo zrušeno.",
            )
            require(
                time.monotonic() - start < 5,
                "DB_BUSY",
                "Probíhá jiná operace. Zkuste akci znovu po jejím dokončení.",
            )
            if progress and not announced:
                progress("Čekám na dokončení jiné operace…")
                announced = True
        try:
            require(
                not (cancel and cancel.is_set()), "CANCELLED", "Operace byla zrušena."
            )
            yield
        finally:
            self.gate.release()

    @contextmanager
    def transaction(self):
        with self.operation_gate(), self.connect() as c:
            try:
                c.execute("BEGIN IMMEDIATE")
                before = c.execute(
                    "SELECT revision FROM domain_clock WHERE id=1"
                ).fetchone()[0]
                yield c
                if (
                    c.execute(
                        "SELECT revision FROM domain_clock WHERE id=1"
                    ).fetchone()[0]
                    != before
                ):
                    self.validate(c)
                c.commit()
            except sqlite3.OperationalError as e:
                c.rollback()
                if "locked" in str(e):
                    raise AppError(
                        "DB_BUSY", "Databáze je zaneprázdněna.", retryable=True
                    ) from e
                if "full" in str(e):
                    raise AppError("DISK_FULL", "Na disku není dostatek místa.") from e
                raise
            except BaseException:
                c.rollback()
                raise

    def validate(self, c):
        invalid = c.execute(
            "SELECT w.id FROM work_object w LEFT JOIN membership m ON m.parent_id=w.id AND m.active=1 WHERE w.type='GROUP' AND w.lifecycle='ACTIVE' GROUP BY w.id HAVING count(m.id)<2 LIMIT 1"
        ).fetchone()
        require(
            not invalid, "GROUP_INVALID", "Aktivní skupina musí mít alespoň dvě děti."
        )
        missing = c.execute(
            "SELECT f.id FROM financial_source f LEFT JOIN cashbook_detail a ON a.source_id=f.id LEFT JOIN bank_detail b ON b.source_id=f.id LEFT JOIN booking_detail k ON k.source_id=f.id LEFT JOIN work_object w ON w.source_id=f.id WHERE w.id IS NULL OR (f.kind='CASHBOOK_CARD' AND a.source_id IS NULL) OR (f.kind='BANK_CARD' AND b.source_id IS NULL) OR (f.kind='BOOKING' AND k.source_id IS NULL) LIMIT 1"
        ).fetchone()
        require(
            not missing,
            "SOURCE_INVALID",
            "Finanční zdroj nemá úplný podtyp a pracovní objekt.",
        )

        overflow = c.execute("""WITH RECURSIVE tree(root,id) AS (
            SELECT id,id FROM work_object WHERE type='GROUP' AND lifecycle='ACTIVE'
            UNION ALL SELECT t.root,m.child_id FROM tree t JOIN membership m ON m.parent_id=t.id AND m.active=1)
            SELECT root FROM tree t JOIN work_object w ON w.id=t.id AND w.type='SOURCE' JOIN financial_source f ON f.id=w.source_id
            GROUP BY root HAVING abs(sum(CASE WHEN f.kind='CASHBOOK_CARD' THEN f.signed_amount_minor ELSE -f.signed_amount_minor END))>9000000000000000 LIMIT 1""").fetchone()
        require(
            not overflow, "MONEY_OVERFLOW", "Rozdíl skupiny překračuje povolený rozsah."
        )

    def audit(
        self,
        c,
        event,
        refs=(),
        before=None,
        after=None,
        method="SYSTEM",
        command=None,
        operation=None,
    ):
        c.execute(
            "INSERT INTO audit_event VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                uid(),
                operation,
                command,
                event,
                canonical(list(refs)),
                canonical(before),
                canonical(after),
                "{}",
                method,
                None,
                now(),
            ),
        )

    def start_operation(self, kind):
        op = uid()
        with self.transaction() as c:
            c.execute(
                "INSERT INTO operation(id,type,state,started_at,heartbeat_at,correlation_id) VALUES(?,?,?,?,?,?)",
                (op, kind, "RUNNING", now(), now(), uid()),
            )
            self.audit(c, kind + "_STARTED", operation=op)
        return op

    def finish_operation(self, op, error=None):
        with self.transaction() as c:
            c.execute(
                "UPDATE operation SET state=?,finished_at=?,safe_error_json=? WHERE id=?",
                (
                    "FAILED" if error else "COMPLETED",
                    now(),
                    canonical(error.as_dict()) if error else None,
                    op,
                ),
            )
            self.audit(
                c, "OPERATION_FAILED" if error else "OPERATION_COMPLETED", operation=op
            )

    def invalidate_redo(self, c):
        c.execute("UPDATE command SET redo_valid=0 WHERE state='UNDONE'")

    def recover(self):
        with self.transaction() as c:
            c.execute(
                "UPDATE operation SET state='INTERRUPTED',finished_at=? WHERE state='RUNNING'",
                (now(),),
            )
            c.execute(
                "UPDATE helper_state SET status='STALE',failure_code='INTERRUPTED',revision=revision+1 WHERE status='REFRESHING'"
            )
