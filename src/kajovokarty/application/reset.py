"""Explicit workspace erasure. Call only while holding the application lock,
after stopping UI timers and joining every worker. Never traverse junctions.
"""

from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import zipfile

from kajovokarty.application.workspace import atomic_json
from kajovokarty.domain.core import AppError, bytehash, require, uid
from kajovokarty.infrastructure.database import Database
from kajovokarty.infrastructure.file_storage import publish_staged_file


RESET_EXIT = 24


def plain_path(path):
    path = Path(path).absolute()
    for parent in (path, *path.parents):
        require(not parent.is_symlink() and not parent.is_junction(),
                "RESET_FAILED", "Odkazovanou složku nelze mazat.")
    return path.resolve()


def owned_archive(path):
    """Recognize product archives by their internal contract, not filename."""
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            if names == {"database.sqlite", "manifest.json"}:
                info = archive.getinfo("manifest.json")
                if info.file_size > 65536:
                    return False
                manifest = json.loads(archive.read(info))
                return (manifest.get("schema") in (1, 2, 3, 4)
                        and isinstance(manifest.get("app_build"), str)
                        and set(manifest.get("files", {})) == {"database.sqlite"})
            if "diagnostics.json" in names:
                info = archive.getinfo("diagnostics.json")
                if info.file_size > 1024 * 1024:
                    return False
                value = json.loads(archive.read(info))
                return isinstance(value, dict) and "schema_versions" in value and "app_build" in value
    except (ValueError, TypeError, AttributeError, zipfile.BadZipFile, RuntimeError):
        pass
    return False


def owned_database(path):
    # An unreadable candidate must stop preparation, not silently survive reset.
    with path.open("rb") as stream:
        if stream.read(16) != b"SQLite format 3\x00":
            return False
    try:
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True)) as c:
            tables = {row[0] for row in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            return ({"financial_source", "source_file", "schema_migration"} <= tables or
                    {"schema_migration", "app_setting", "booking_payment_line", "card_transaction",
                     "match_group", "api_raw_snapshot", "audit_event"} <= tables)
    except sqlite3.Error:
        return False


class ResetService:
    def __init__(self, data, base):
        self.data = plain_path(data)
        self.base = plain_path(base)
        self.marker = self.data / ".reset.json"
        self.database = self.data / "kajovokarty.sqlite"

    @property
    def pending(self):
        return self.marker.exists()

    def _files(self, folder):
        if not folder.exists():
            return
        plain_path(folder)
        for item in folder.iterdir():
            # Links are never followed, including Windows directory junctions.
            if item.is_symlink() or item.is_junction():
                continue
            if item.is_dir():
                yield from self._files(item)
            elif item.is_file():
                yield item.resolve()

    def prepare(self, backup_directory):
        """Prepare an empty replacement and a durable deletion list; no erasure."""
        require(not self.pending, "RESET_FAILED", "Reset již čeká na dokončení.")
        backup = plain_path(backup_directory)
        targets = set()
        roots = {self.base, self.data, backup}
        for root in (self.base, self.data):
            for name in ("credentials.dat", "kajovokarty.sqlite3"):
                p = root / name
                if p.is_file():
                    targets.add(plain_path(p))
                    if name.endswith("sqlite3"):
                        targets.update(plain_path(p.with_name(p.name + suffix))
                                       for suffix in ("-wal", "-shm")
                                       if p.with_name(p.name + suffix).exists())
            for p in root.iterdir():
                if p.is_file() and not p.is_symlink() and p.suffix == ".zip" and owned_archive(p):
                    targets.add(plain_path(p))
                elif (p.is_file() and not p.is_symlink() and p != self.database
                      and p.suffix in {".sqlite", ".sqlite3"} and owned_database(p)):
                    targets.add(plain_path(p))
            # Recovery deliberately retains damaged database bytes. They may not
            # have a readable schema, so recognize the exact recovery layout.
            for folder in root.glob("before-recovery-*"):
                suffix = folder.name.removeprefix("before-recovery-")
                if (len(suffix) != 32 or any(ch not in "0123456789abcdef" for ch in suffix)
                        or not folder.is_dir() or folder.is_symlink() or folder.is_junction()):
                    continue
                for name in ("kajovokarty.sqlite", "kajovokarty.sqlite-wal", "kajovokarty.sqlite-shm"):
                    p = folder / name
                    if p.is_file():
                        targets.add(plain_path(p))
            for folder_name in ("logs", "diagnostics", "backups"):
                for p in self._files(root / folder_name):
                    if (folder_name == "logs" and
                        (p.match("????-??-??.jsonl") or p.match("kajovokarty-????????-???.jsonl")
                         or p.name in {"kajovokarty.log", "app.log"})):
                        targets.add(p)
                    elif p.suffix == ".zip" and owned_archive(p):
                        targets.add(p)
                    elif folder_name == "backups" and p.suffix in {".sqlite", ".sqlite3"} and owned_database(p):
                        targets.add(p)
        # A user may select a shared folder or even a drive root for backups.
        # Inspect that directory only, never recursively scan the drive.
        for p in backup.iterdir() if backup.exists() else ():
            if not p.is_file() or p.is_symlink() or p.is_junction():
                continue
            if ((p.suffix == ".zip" and owned_archive(p)) or
                (p.suffix in {".sqlite", ".sqlite3"} and owned_database(p))):
                targets.add(plain_path(p))
        # A configured backup directory can contain the current database.
        targets.discard(self.database)
        for p in list(targets):
            if p.suffix in {".sqlite", ".sqlite3"}:
                targets.update(plain_path(p.with_name(p.name + suffix))
                               for suffix in ("-wal", "-shm")
                               if p.with_name(p.name + suffix).exists())
        candidate = self.data / (".reset-new-" + uid() + ".sqlite")
        try:
            with tempfile.TemporaryDirectory(dir=self.data, prefix="kk-reset-") as temp:
                fresh = Database(Path(temp) / "kajovokarty.sqlite")
                with fresh.connect() as c:
                    c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                    c.execute("PRAGMA journal_mode=DELETE")
                    require(c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
                            and not c.execute("PRAGMA foreign_key_check").fetchall(),
                            "RESET_FAILED", "Prázdná data neprošla kontrolou.")
                publish_staged_file(fresh.path, candidate)
            with candidate.open("r+b") as stream:
                os.fsync(stream.fileno())
            atomic_json(self.marker, {
                "version": 1, "data": str(self.data), "base": str(self.base),
                "roots": sorted(str(p) for p in roots),
                "targets": sorted(str(p) for p in targets),
                "candidate": candidate.name, "sha256": bytehash(candidate.read_bytes()),
            })
        finally:
            if not self.pending:
                candidate.unlink(missing_ok=True)

    def finish(self):
        """Idempotently finish a confirmed reset, including after process death."""
        try:
            record = json.loads(plain_path(self.marker).read_text(encoding="utf-8"))
            require(record["version"] == 1 and record["data"] == str(self.data)
                    and record["base"] == str(self.base), "RESET_FAILED", "Nesouhlasí pracovní prostor.")
            candidate_name = record["candidate"]
            require(Path(candidate_name).name == candidate_name
                    and candidate_name.startswith(".reset-new-") and candidate_name.endswith(".sqlite"),
                    "RESET_FAILED", "Neplatná příprava resetu.")
            candidate = plain_path(self.data / candidate_name)
            roots = [plain_path(p) for p in record["roots"]]
            targets = [plain_path(p) for p in record["targets"]]
            for p in targets:
                require(any(p.is_relative_to(root) and p != root for root in roots)
                        and p not in {self.database, candidate, self.marker, self.data / "application.lock"},
                        "RESET_FAILED", "Soubor není součástí resetu.")
            expected = record["sha256"]
            require(bytehash((candidate if candidate.exists() else self.database).read_bytes()) == expected,
                    "RESET_FAILED", "Připravená prázdná data nejsou dostupná.")
            for p in targets:
                p.unlink(missing_ok=True)
            if candidate.exists():
                for suffix in ("-wal", "-shm"):
                    plain_path(self.database.with_name(self.database.name + suffix)).unlink(missing_ok=True)
                os.replace(candidate, plain_path(self.database))
            # Keep only the location, no previous workspace or user preferences.
            pointer = plain_path(self.base / "workspace.json")
            if pointer.exists() or self.data != self.base / "data":
                atomic_json(pointer, {"data_directory": str(self.data)})
            self.marker.unlink()
        except (OSError, ValueError, KeyError, TypeError, AppError) as error:
            raise AppError("RESET_FAILED", "Reset se nepodařilo dokončit.") from error
