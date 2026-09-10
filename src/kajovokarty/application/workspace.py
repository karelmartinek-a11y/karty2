"""Verified workspace relocation and recovery; never silently initialize lost data."""

from pathlib import Path
import os, shutil, sqlite3, tempfile
from kajovokarty.domain.core import AppError, bytehash, canonical, now, require, uid


def local_directory(path):
    path = Path(path).expanduser().resolve()
    require(
        not str(path).startswith(("\\\\", "//")),
        "DIRECTORY_INVALID",
        "Datová složka musí být na místním disku.",
    )
    if os.name == "nt":
        import ctypes

        require(
            ctypes.windll.kernel32.GetDriveTypeW(str(path.anchor)) != 4,
            "DIRECTORY_INVALID",
            "Síťový disk nelze použít pro databázi.",
        )
    return path


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uid() + ".tmp")
    try:
        with temp.open("x", encoding="utf-8") as f:
            f.write(canonical(data))
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


class WorkspaceService:
    def __init__(self, db, pointer):
        self.db, self.pointer = db, Path(pointer)

    def move(self, target):
        target = local_directory(target)
        require(
            target != self.db.path.parent.resolve(),
            "DIRECTORY_INVALID",
            "Pracovní prostor již používá tuto složku.",
        )
        target.mkdir(parents=True, exist_ok=True)
        require(
            not (target / "kajovokarty.sqlite").exists()
            and not (target / "application.lock").exists(),
            "DIRECTORY_OCCUPIED",
            "Cíl již obsahuje pracovní prostor.",
        )
        marker = target / ".moving"
        try:
            with marker.open("x") as f:
                f.write(uid())
        except FileExistsError:
            raise AppError(
                "DIRECTORY_OCCUPIED", "V cíli právě probíhá přesun."
            ) from None
        try:
            with self.db.gate, tempfile.TemporaryDirectory(dir=target) as folder:
                candidate = Path(folder) / "kajovokarty.sqlite"
                from contextlib import closing

                with (
                    self.db.connect() as source,
                    closing(sqlite3.connect(candidate)) as dest,
                ):
                    source.backup(dest)
                    dest.execute("PRAGMA journal_mode=DELETE")
                    require(
                        dest.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
                        and not dest.execute("PRAGMA foreign_key_check").fetchall(),
                        "DATABASE_INVALID",
                        "Kopie dat neprošla kontrolou.",
                    )
                    for row in dest.execute("SELECT sha256,bytes FROM source_file"):
                        require(
                            bytehash(row[1]) == row[0],
                            "SNAPSHOT_INVALID",
                            "Zdrojový soubor v kopii má chybný hash.",
                        )
                    self.db.audit(
                        dest, "DATA_DIRECTORY_MOVED", after={"workspace_changed": True}
                    )
                    dest.commit()
                final = target / "kajovokarty.sqlite"
                expected = bytehash(candidate.read_bytes())
                os.replace(candidate, final)
                require(
                    bytehash(final.read_bytes()) == expected,
                    "DATABASE_INVALID",
                    "Zapsaná kopie nesouhlasí.",
                )
                atomic_json(
                    self.pointer,
                    {
                        "data_directory": str(target),
                        "previous_directory": str(self.db.path.parent.resolve()),
                        "changed_at": now(),
                    },
                )
            return str(target)
        finally:
            marker.unlink(missing_ok=True)


def recover_backup(backup, target):
    """Recover even when current SQLite cannot be opened. Preserve damaged bytes."""
    from kajovokarty.application.backup import BackupService
    from kajovokarty.infrastructure.database import Database

    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target) as folder:
        db = Database(Path(folder) / "kajovokarty.sqlite")
        service = BackupService(db)
        service.restore(backup)
        with db.connect() as c:
            c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            c.execute("PRAGMA journal_mode=DELETE")
        damaged = target / ("before-recovery-" + uid())
        damaged.mkdir()
        for name in (
            "kajovokarty.sqlite",
            "kajovokarty.sqlite-wal",
            "kajovokarty.sqlite-shm",
        ):
            old = target / name
            if old.exists():
                shutil.copy2(old, damaged / name)
        os.replace(db.path, target / "kajovokarty.sqlite")
        for suffix in ("-wal", "-shm"):
            (target / ("kajovokarty.sqlite" + suffix)).unlink(missing_ok=True)
    return str(target)
