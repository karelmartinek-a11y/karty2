import os
from pathlib import Path
import tempfile
import pytest

from kajovokarty.infrastructure.file_storage import publish_staged_file


def test_failed_publish_keeps_original_and_cleans_pending(tmp_path, monkeypatch):
    source, target = tmp_path / "source", tmp_path / "target"
    source.write_bytes(b"new")
    target.write_bytes(b"old")
    def fail(*args):
        raise PermissionError("locked")
    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(PermissionError):
        publish_staged_file(source, target)
    assert target.read_bytes() == b"old"
    assert source.read_bytes() == b"new"
    assert not list(tmp_path.glob(".*.tmp"))


def windows_dacl(path):
    import ctypes
    from ctypes import wintypes as w
    api = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    api.GetNamedSecurityInfoW.argtypes = [w.LPWSTR, ctypes.c_int, w.DWORD,
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p)]
    api.GetNamedSecurityInfoW.restype = w.DWORD
    api.ConvertSecurityDescriptorToStringSecurityDescriptorW.argtypes = [ctypes.c_void_p,
        w.DWORD, w.DWORD, ctypes.POINTER(w.LPWSTR), ctypes.c_void_p]
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    descriptor = ctypes.c_void_p()
    text = w.LPWSTR()
    try:
        error = api.GetNamedSecurityInfoW(str(path), 1, 4, None, None, None, None, ctypes.byref(descriptor))
        if error:
            raise ctypes.WinError(error)
        if not api.ConvertSecurityDescriptorToStringSecurityDescriptorW(descriptor, 1, 4, ctypes.byref(text), None):
            raise ctypes.WinError(ctypes.get_last_error())
        return text.value
    finally:
        if text:
            kernel.LocalFree(text)
        if descriptor:
            kernel.LocalFree(descriptor)


@pytest.mark.skipif(os.name != "nt", reason="Windows file ACL regression")
def test_published_file_inherits_destination_permissions(tmp_path):
    import subprocess
    user = os.environ["USERDOMAIN"] + "\\" + os.environ["USERNAME"]
    # pytest's own temp root is private too. Give only this test's directory
    # the explicit user access that a normal LocalAppData directory has.
    subprocess.run(["icacls", str(tmp_path), "/grant", user + ":(OI)(CI)F"],
                   check=True, capture_output=True)
    target = tmp_path / "database.sqlite"
    reference = tmp_path / "normal-file"
    reference.write_bytes(b"normal")
    expected = windows_dacl(reference)
    with tempfile.TemporaryDirectory(dir=tmp_path) as folder:
        source = Path(folder) / "database.sqlite"
        source.write_bytes(b"payment data")
        # Reproduce the old rename: it carries the private temporary ACL.
        old = tmp_path / "old-behavior.sqlite"
        os.replace(source, old)
        assert windows_dacl(old) != expected
        publish_staged_file(old, target)
    assert target.read_bytes() == b"payment data"
    assert windows_dacl(target) == expected


@pytest.mark.skipif(os.name != "nt", reason="Windows file ACL regression")
def test_reset_and_backups_preserve_directory_access(tmp_path):
    from kajovokarty.infrastructure.database import Database
    from kajovokarty.application.reset import ResetService
    from kajovokarty.application.backup import BackupService
    from kajovokarty.application.workspace import WorkspaceService, recover_backup
    base = tmp_path / "app"
    data = base / "data"
    db = Database(data / "kajovokarty.sqlite")
    expected = windows_dacl(db.path)
    archive = data / "saved.zip"
    BackupService(db).backup(archive)
    assert windows_dacl(archive) == expected
    BackupService(db).restore(archive)
    assert windows_dacl(db.path) == expected
    target = tmp_path / "moved"
    WorkspaceService(db, base / "workspace.json").move(target)
    reference = target / "reference"
    reference.write_bytes(b"reference")
    assert windows_dacl(target / "kajovokarty.sqlite") == windows_dacl(reference)
    recover_backup(archive, target)
    assert windows_dacl(target / "kajovokarty.sqlite") == windows_dacl(reference)
    reset = ResetService(data, base)
    reset.prepare(data)
    reset.finish()
    assert windows_dacl(db.path) == expected
    # A second launch still validates the database.
    Database(db.path).recover()


def test_startup_access_failure_is_logged_and_explained(tmp_path, monkeypatch):
    import importlib
    import json
    import sqlite3
    from PySide6.QtWidgets import QApplication
    from kajovokarty.domain.errors import user_text
    bootstrap = importlib.import_module("kajovokarty.bootstrap.main")
    app = QApplication.instance() or QApplication([])
    def denied(*args):
        error = sqlite3.OperationalError("private-path-must-not-be-logged")
        error.sqlite_errorcode = sqlite3.SQLITE_CANTOPEN
        error.sqlite_errorname = "SQLITE_CANTOPEN"
        raise error
    messages = []
    monkeypatch.setattr(bootstrap, "Database", denied)
    monkeypatch.setattr("kajovokarty.ui.recovery.recovery_dialog",
                        lambda parent, data, pointer, message: messages.append(message) or False)
    assert bootstrap.run_workspace(app, tmp_path) == 1
    assert messages == [user_text("DATABASE_ACCESS_DENIED")]
    raw = next((tmp_path / "logs").glob("*.jsonl")).read_text(encoding="utf-8")
    event = json.loads(raw.splitlines()[-1])
    assert event["event"] == "DATABASE_START_FAILED"
    assert event["sqlite_error_name"] == "SQLITE_CANTOPEN"
    assert "private-path" not in raw


def test_failed_connection_setup_closes_handle(tmp_path, monkeypatch):
    import sqlite3
    from kajovokarty.infrastructure.database import Database
    class BrokenConnection:
        closed = False
        def create_function(self, *args, **kwargs):
            pass
        def execute(self, *args):
            raise sqlite3.OperationalError("locked")
        def close(self):
            self.closed = True
    connection = BrokenConnection()
    db = Database.__new__(Database)
    db.path = tmp_path / "database.sqlite"
    monkeypatch.setattr(sqlite3, "connect", lambda *a, **k: connection)
    with pytest.raises(sqlite3.OperationalError):
        with db.connect():
            pytest.fail("Connection setup must fail")
    assert connection.closed
