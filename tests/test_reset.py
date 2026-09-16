import json
import os
from pathlib import Path
import shutil
import sqlite3

import pytest

from kajovokarty.application.backup import BackupService
from kajovokarty.application.imports import ImportService, ImportInput
from kajovokarty.application.matching import MatchingService
from kajovokarty.application.reset import ResetService
from kajovokarty.application.settings import SettingsService
from kajovokarty.domain.core import AppError
from kajovokarty.infrastructure.database import Database
from test_acceptance_traces import seed
from test_accounts import import_sample


@pytest.fixture
def workspace(tmp_path):
    base = tmp_path / "app"
    data = base / "data"
    db = Database(data / "kajovokarty.sqlite")
    backups = tmp_path / "shared"
    backups.mkdir()
    return db, ResetService(data, base), backups


def test_full_reset_all_tables_and_artifacts(workspace, fixtures):
    db, service, backups = workspace
    import_sample(db)
    seed(db, "CASHBOOK_CARD")
    seed(db, "BANK_CARD")
    MatchingService(db, SettingsService(db)).run()
    SettingsService(db).save({"ui.text_scale": 130, "backup.daily": False})
    backup = backups / "my-backup.zip"
    BackupService(db).backup(backup)
    diagnostics = service.data / "diagnostics"
    diagnostics.mkdir()
    report = diagnostics / "report.zip"
    BackupService(db).diagnostic(report)
    raw = service.base / "backups" / "forensic.sqlite"
    raw.parent.mkdir()
    with db.connect() as c:
        c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    shutil.copy2(db.path, raw)
    credential = service.base / "credentials.dat"
    credential.write_bytes(b"private")
    original = backups / "original.csv"
    original.write_text("untouched", encoding="utf-8")
    export = service.base / "exports" / "report.csv"
    export.parent.mkdir()
    export.write_text("export", encoding="utf-8")
    unrelated = backups / "another.sqlite"
    with sqlite3.connect(unrelated) as c:
        c.execute("CREATE TABLE unrelated(value)")
    nested = backups / "unrelated-folder"
    nested.mkdir()
    shutil.copy2(backup, nested / "preserved.zip")
    logs = list((service.data / "logs").glob("*.jsonl"))
    service.prepare(backups)
    assert backup.exists() and credential.exists()
    service.finish()
    assert not service.pending
    assert not any(p.exists() for p in [backup, raw, credential, report, *logs])
    assert original.read_text(encoding="utf-8") == "untouched"
    assert export.read_text(encoding="utf-8") == "export"
    assert unrelated.exists() and (nested / "preserved.zip").exists()
    fresh = Database(db.path)
    baseline = Database(service.base / "baseline" / "kajovokarty.sqlite")
    with fresh.connect() as actual, baseline.connect() as expected:
        for (table,) in expected.execute("SELECT name FROM sqlite_master WHERE type='table'"):
            assert actual.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0] == expected.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0], table
    assert SettingsService(fresh).get()["ui.text_scale"] == 100
    assert SettingsService(fresh).get()["backup.daily"] is True
    imports = ImportService(fresh)
    preview = imports.preflight([ImportInput("BANK_CARD", str(fixtures / "terminal.xlsx"))])
    assert preview.valid
    imports.commit(preview.id)
    seed(fresh, "CASHBOOK_CARD")
    seed(fresh, "BANK_CARD")
    assert MatchingService(fresh, SettingsService(fresh)).run()["created_groups"] >= 1


def test_failed_delete_remains_pending_and_resumes(workspace, monkeypatch):
    db, service, backups = workspace
    seed(db, "CASHBOOK_CARD")
    backup = backups / "saved.zip"
    BackupService(db).backup(backup)
    service.prepare(backups)
    unlink = Path.unlink
    def locked(path, *args, **kwargs):
        if path == backup:
            raise PermissionError("locked")
        return unlink(path, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", locked)
        with pytest.raises(AppError) as caught:
            service.finish()
        assert caught.value.code == "RESET_FAILED"
    assert service.pending
    ResetService(service.data, service.base).finish()
    assert not backup.exists() and not service.pending
    with Database(db.path).connect() as c:
        assert c.execute("SELECT count(*) FROM financial_source").fetchone()[0] == 0


def test_interruption_after_replacement_resumes(workspace, monkeypatch):
    db, service, backups = workspace
    seed(db, "CASHBOOK_CARD")
    service.prepare(backups)
    replace = os.replace
    def interrupted(src, dst):
        replace(src, dst)
        if Path(dst) == db.path:
            raise OSError("power loss after replacement")
    with monkeypatch.context() as patch:
        patch.setattr(os, "replace", interrupted)
        with pytest.raises(AppError):
            service.finish()
    assert service.pending
    service.finish()
    with Database(db.path).connect() as c:
        assert c.execute("SELECT count(*) FROM financial_source").fetchone()[0] == 0


def test_full_disk_preparation_preserves_old_data(workspace, monkeypatch):
    db, service, backups = workspace
    source = seed(db, "CASHBOOK_CARD")
    def full_disk(*args, **kwargs):
        raise OSError(28, "full")
    monkeypatch.setattr("kajovokarty.application.reset.atomic_json", full_disk)
    with pytest.raises(OSError):
        service.prepare(backups)
    assert not service.pending
    assert not list(service.data.glob(".reset-new-*"))
    with db.connect() as c:
        assert c.execute("SELECT id FROM financial_source WHERE id=?", (source,)).fetchone()


def test_custom_location_preserved_without_old_pointer_metadata(workspace, tmp_path):
    db, _, backups = workspace
    base = tmp_path / "application-location"
    base.mkdir()
    pointer = base / "workspace.json"
    pointer.write_text(json.dumps({"data_directory": str(db.path.parent), "previous_directory": "old"}))
    service = ResetService(db.path.parent, base)
    service.prepare(backups)
    service.finish()
    assert json.loads(pointer.read_text()) == {"data_directory": str(db.path.parent)}


def test_invalid_deletion_target_is_rejected(workspace, tmp_path):
    _, service, backups = workspace
    protected = tmp_path / "protected.txt"
    protected.write_text("keep")
    service.prepare(backups)
    record = json.loads(service.marker.read_text())
    record["targets"].append(str(protected))
    service.marker.write_text(json.dumps(record))
    with pytest.raises(AppError):
        service.finish()
    assert protected.read_text() == "keep"


@pytest.mark.parametrize("text,accepted", [("", False), ("vymazat", False), ("VYMAZAT ", False), ("VYMAZAT", True)])
def test_confirmation_requires_exact_word(text, accepted):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QLineEdit, QPushButton
    from kajovokarty.ui.settings_dialog import confirm_full_reset
    app = QApplication.instance() or QApplication([])
    checked = []
    def interact():
        dialog = app.activeModalWidget()
        entry = dialog.findChild(QLineEdit, "resetConfirmation")
        erase = dialog.findChild(QPushButton, "confirmErase")
        entry.setText(text)
        checked.append(erase.isEnabled())
        if erase.isEnabled():
            erase.click()
        else:
            dialog.reject()
    QTimer.singleShot(0, interact)
    assert confirm_full_reset(None) is accepted
    assert checked == [accepted]


@pytest.mark.parametrize("mode", ["busy", "worker", "started_during_confirmation"])
def test_settings_reset_blocks_running_jobs(workspace, monkeypatch, mode):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QPushButton, QLabel
    from kajovokarty.ui.main import MainWindow
    import importlib
    module = importlib.import_module("kajovokarty.ui.settings_dialog")
    from test_gui import spin
    db, _, _ = workspace
    app = QApplication.instance() or QApplication([])
    window = MainWindow(db)
    spin(lambda: not window.jobs)
    fake_job = object()
    if mode == "busy":
        window.busy = True
    elif mode == "worker":
        window.jobs.add(fake_job)
    def confirm(parent):
        assert mode == "started_during_confirmation"
        window.jobs.add(fake_job)
        return True
    monkeypatch.setattr(module, "confirm_full_reset", confirm)
    errors = []
    def interact():
        dialog = app.activeModalWidget()
        dialog.findChild(QPushButton, "resetApplication").click()
        errors.extend(label.text() for label in dialog.findChildren(QLabel) if "dokončuje jinou" in label.text())
        dialog.reject()
    QTimer.singleShot(0, interact)
    module.settings_dialog(window)
    assert errors
    assert not getattr(window, "shutting_down", False)
    window.jobs.discard(fake_job)
    window.busy = False
    window.close()


def test_reset_button_restart_and_first_launch(workspace):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QPushButton, QLineEdit
    from kajovokarty.bootstrap.main import run_workspace
    from kajovokarty.ui.main import MainWindow
    from kajovokarty.ui.settings_dialog import settings_dialog
    db, service, backups = workspace
    seed(db, "CASHBOOK_CARD")
    SettingsService(db).save({"backup.daily": False, "data.backup_directory": str(backups)})
    backup = backups / "saved.zip"
    BackupService(db).backup(backup)
    app = QApplication.instance() or QApplication([])
    stage = []
    errors = []
    def drive():
        try:
            modal = app.activeModalWidget()
            if modal:
                if modal.objectName() == "confirmFullReset":
                    modal.findChild(QLineEdit, "resetConfirmation").setText("VYMAZAT")
                    modal.findChild(QPushButton, "confirmErase").click()
                else:
                    button = modal.findChild(QPushButton, "resetApplication")
                    if button:
                        QTimer.singleShot(0, button.click)
                return
            windows = [w for w in app.topLevelWidgets() if isinstance(w, MainWindow)
                       and w.isVisible() and w.db.path == db.path]
            if not windows or windows[0].jobs:
                return
            window = windows[0]
            if not stage:
                stage.append("reset")
                # Use a separate callback: this timer must keep driving modal dialogs.
                QTimer.singleShot(0, lambda: settings_dialog(window))
            elif stage == ["reset", "restarted"]:
                with window.db.connect() as c:
                    assert c.execute("SELECT count(*) FROM financial_source").fetchone()[0] == 0
                assert window.settings.get()["backup.daily"] is True
                stage.append("empty")
                window.close()
        except Exception as error:
            errors.append(error)
            app.exit(99)
    timer = QTimer()
    timer.timeout.connect(drive)
    timer.start(20)
    watchdog = QTimer()
    watchdog.setSingleShot(True)
    watchdog.timeout.connect(lambda: app.exit(99))
    watchdog.start(20000)
    try:
        assert run_workspace(app, service.base) == 23
        assert not backup.exists()
        stage.append("restarted")
        assert run_workspace(app, service.base) == 0
        assert stage == ["reset", "restarted", "empty"]
        assert not errors
    finally:
        timer.stop()
        watchdog.stop()


def test_legacy_copies_and_logs_removed(workspace):
    _, service, backups = workspace
    legacy = backups / "old-copy.sqlite3"
    with sqlite3.connect(legacy) as c:
        for table in ("schema_migration", "app_setting", "booking_payment_line", "card_transaction",
                      "match_group", "api_raw_snapshot", "audit_event"):
            c.execute(f"CREATE TABLE {table}(value)")
    c.close()
    log = service.data / "logs" / "kajovokarty-20260802-000.jsonl"
    log.write_text('{"private":"old"}')
    recovery = service.data / ("before-recovery-" + "a" * 32)
    recovery.mkdir()
    damaged = recovery / "kajovokarty.sqlite"
    damaged.write_bytes(b"damaged old user data")
    service.prepare(backups)
    service.finish()
    assert not legacy.exists() and not log.exists() and not damaged.exists()


def test_changed_folder_to_junction_blocks_deletion(workspace, monkeypatch):
    _, service, backups = workspace
    backup = backups / "saved.zip"
    BackupService(Database(service.database)).backup(backup)
    service.prepare(backups)
    original = Path.is_junction
    monkeypatch.setattr(Path, "is_junction", lambda p: p == backups or original(p))
    with pytest.raises(AppError):
        service.finish()
    assert backup.exists()


@pytest.mark.parametrize("answer", ["close", "retry_failed"])
def test_pending_reset_never_opens_normal_window(workspace, monkeypatch, answer):
    from PySide6.QtWidgets import QApplication, QMessageBox
    from kajovokarty.bootstrap.main import run_workspace
    db, service, backups = workspace
    app = QApplication.instance() or QApplication([])
    service.prepare(backups)
    calls = []
    def warning(*args):
        calls.append(args[1])
        return QMessageBox.Yes if len(calls) == 1 and answer == "retry_failed" else QMessageBox.Close
    monkeypatch.setattr(QMessageBox, "warning", warning)
    def forbidden(*args):
        pytest.fail("Incomplete reset must not open the main window")
    monkeypatch.setattr("kajovokarty.ui.main.MainWindow", forbidden)
    if answer == "retry_failed":
        def fail(*args):
            raise AppError("RESET_FAILED", "locked")
        monkeypatch.setattr(ResetService, "finish", fail)
    assert run_workspace(app, service.base) == 1
    assert service.pending
    assert len(calls) == (1 if answer == "close" else 2)
