from __future__ import annotations
from pathlib import Path
import json, os, sqlite3, tempfile, zipfile, platform, re
from kajovokarty.domain.core import AppError, bytehash, canonical, now, require, uid


class BackupService:
    def __init__(self, db):
        self.db = db

    def backup(self, target):
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        with (
            self.db.gate,
            tempfile.TemporaryDirectory(dir=target.parent, prefix="kk-backup-") as temp,
        ):
            dbpath = Path(temp) / "database.sqlite"
            with self.db.connect() as source:
                dest = sqlite3.connect(dbpath)
                source.backup(dest)
                dest.execute("PRAGMA journal_mode=DELETE")
                dest.execute("PRAGMA secure_delete=ON")
                dest.execute("DELETE FROM secret")
                dest.commit()
                dest.execute("VACUUM")
                require(
                    dest.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
                    and not dest.execute("PRAGMA foreign_key_check").fetchall(),
                    "BACKUP_INVALID",
                    "Kopie databáze neprošla kontrolou.",
                )
                dest.close()
            raw = dbpath.read_bytes()
            manifest = {
                "schema": 2,
                "app_build": "0.3.1",
                "created_at": now(),
                "files": {"database.sqlite": bytehash(raw)},
                "secrets_included": False,
            }
            tmp = Path(temp) / "backup.zip"
            with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
                z.writestr("database.sqlite", raw)
                z.writestr("manifest.json", canonical(manifest))
            with zipfile.ZipFile(tmp) as z:
                require(
                    z.testzip() is None,
                    "BACKUP_INVALID",
                    "Záloha se nepodařila ověřit.",
                )
            os.replace(tmp, target)
            with self.db.transaction() as c:
                self.db.audit(
                    c, "BACKUP_CREATED", after={"sha256": bytehash(target.read_bytes())}
                )
        return str(target)

    def inspect(self, path):
        try:
            with zipfile.ZipFile(path) as z:
                require(
                    set(z.namelist()) == {"database.sqlite", "manifest.json"}
                    and len(z.infolist()) == 2,
                    "BACKUP_INVALID",
                    "Neplatný obsah zálohy.",
                )
                require(
                    sum(i.file_size for i in z.infolist()) <= 4 * 1024**3,
                    "BACKUP_INVALID",
                    "Záloha překračuje 4 GiB.",
                )
                manifest = json.loads(z.read("manifest.json"))
                raw = z.read("database.sqlite")
                require(
                    manifest.get("schema") in (1, 2)
                    and manifest.get("files", {}).get("database.sqlite")
                    == bytehash(raw),
                    "BACKUP_INVALID",
                    "Nesouhlasí verze nebo kontrolní součet.",
                )
                return manifest, raw
        except (OSError, zipfile.BadZipFile, KeyError, ValueError):
            raise AppError("BACKUP_INVALID", "Zálohu nelze přečíst.")

    def restore(self, path):
        manifest, raw = self.inspect(path)
        with self.db.gate, tempfile.TemporaryDirectory(dir=self.db.path.parent) as temp:
            candidate = Path(temp) / "restored.sqlite"
            candidate.write_bytes(raw)
            from kajovokarty.infrastructure.database import Database

            # Validate and migrate the isolated copy before any current file changes.
            candidate_db = Database(candidate)
            with candidate_db.connect() as candidate_connection:
                require(
                    candidate_connection.execute("PRAGMA user_version").fetchone()[0]
                    == 2,
                    "BACKUP_INVALID",
                    "Nepodporované schéma zálohy.",
                )
            c = sqlite3.connect(candidate)
            try:
                require(
                    c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
                    and not c.execute("PRAGMA foreign_key_check").fetchall()
                    and c.execute("PRAGMA user_version").fetchone()[0] in (1, 2),
                    "BACKUP_INVALID",
                    "Obnovovaná databáze není platná.",
                )
                require(
                    c.execute("SELECT count(*) FROM secret").fetchone()[0] == 0,
                    "BACKUP_INVALID",
                    "Záloha nesmí obsahovat tokeny.",
                )
                with self.db.connect() as current:
                    revision = current.execute(
                        "SELECT credential_revision FROM helper_state"
                    ).fetchone()[0]
                    secrets = current.execute("SELECT * FROM secret").fetchall()
                revision = (
                    max(
                        revision,
                        c.execute(
                            "SELECT max(credential_revision) FROM helper_context"
                        ).fetchone()[0],
                    )
                    + 1
                )
                ctx = uid()
                c.execute(
                    "UPDATE helper_context SET status='RETIRED',retired_at=? WHERE status='CURRENT'",
                    (now(),),
                )
                c.execute(
                    "INSERT INTO helper_context VALUES(?,'CURRENT',?,?,NULL)",
                    (ctx, revision, now()),
                )
                c.execute(
                    "UPDATE helper_state SET context_id=?,credential_revision=?,published_generation_id=NULL,status='UNAVAILABLE',evidence_epoch=0,revision=revision+1,operation_id=NULL,last_full_success_at=NULL WHERE id=1",
                    (ctx, revision),
                )
                for secret in secrets:
                    c.execute("INSERT INTO secret VALUES(?,?,?,?)", tuple(secret))
                c.commit()
                c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                c.execute("PRAGMA journal_mode=DELETE")
            finally:
                c.close()
            self.backup(self.db.path.parent / ("before-restore-" + uid() + ".zip"))
            with self.db.connect() as current:
                current.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            os.replace(candidate, self.db.path)
            for suffix in ("-wal", "-shm"):
                Path(str(self.db.path) + suffix).unlink(missing_ok=True)
            with self.db.transaction() as c:
                self.db.audit(
                    c,
                    "BACKUP_RESTORED",
                    after={
                        "backup_sha256": bytehash(Path(path).read_bytes()),
                        "context_id": ctx,
                    },
                )
        return manifest

    def diagnostic(self, path):
        from kajovokarty.infrastructure.betterhotel import TEMPLATES

        with self.db.connect() as c:
            self.db.validate(c)
            info = {
                "domain_invariants": "PASS",
                "app_build": "0.3.1",
                "os": platform.system(),
                "python": platform.python_version(),
                "integrity": c.execute("PRAGMA quick_check").fetchone()[0],
                "foreign_key_errors": len(
                    c.execute("PRAGMA foreign_key_check").fetchall()
                ),
                "counts": {
                    t: c.execute("SELECT count(*) FROM " + t).fetchone()[0]
                    for t in (
                        "financial_source",
                        "reconciliation_group",
                        "helper_snapshot",
                        "audit_event",
                    )
                },
                "schema_versions": [
                    r[0] for r in c.execute("SELECT version FROM schema_migration")
                ],
                "operation_states": [
                    dict(r)
                    for r in c.execute(
                        "SELECT type,state,count(*) AS count FROM operation GROUP BY type,state"
                    )
                ],
            }
        path = Path(path)
        tmp = path.with_name(path.name + "." + uid() + ".tmp")
        try:
            with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
                z.writestr("diagnostics.json", canonical(info))
                for log in sorted(
                    (self.db.path.parent / "logs").glob("????-??-??.jsonl")
                ):
                    safe_lines = []
                    with log.open(encoding="utf-8", errors="replace") as source:
                        for line in source:
                            try:
                                event = json.loads(line)
                            except ValueError:
                                continue
                            if not isinstance(event, dict):
                                continue
                            clean = {}
                            if event.get("endpoint_template") in TEMPLATES:
                                clean["endpoint_template"] = event["endpoint_template"]
                            for key in ("http_status", "elapsed_ms"):
                                value = event.get(key)
                                if (
                                    isinstance(value, (int, float))
                                    and 0 <= value <= 1e9
                                ):
                                    clean[key] = value
                            code = event.get("error_code", "")
                            if isinstance(code, str) and re.fullmatch(
                                r"[A-Z][A-Z0-9_]{0,63}", code
                            ):
                                clean["error_code"] = code
                            stamp = event.get("timestamp", "")
                            if isinstance(stamp, str) and re.fullmatch(
                                r"[0-9T:.+Z-]{10,40}", stamp
                            ):
                                clean["timestamp"] = stamp
                            if clean:
                                safe_lines.append(canonical(clean))
                    z.writestr("logs/" + log.name, "\n".join(safe_lines))
            os.replace(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)
        return str(path)
