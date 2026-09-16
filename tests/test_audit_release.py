"""Regression evidence for the 0.4.5 source audit; isolated data only."""
import json
import sqlite3
import zipfile

import pytest

from kajovokarty.application.backup import BackupService
from kajovokarty.application.matching import MatchingService
from kajovokarty.application.settings import SettingsService
from kajovokarty.domain.core import AppError
from kajovokarty.infrastructure.database import Database
from test_acceptance_traces import seed
from test_accounts import import_sample, add_references


@pytest.mark.parametrize('manifest', [None, [], 'text', 42, {'schema': 4, 'files': []}])
def test_malformed_backup_manifest_preserves_database(db, tmp_path, manifest):
    identity = seed(db, 'CASHBOOK_CARD')
    archive = tmp_path / 'bad.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        z.writestr('manifest.json', json.dumps(manifest))
        z.writestr('database.sqlite', b'not a database')
    with pytest.raises(AppError) as error:
        BackupService(db).restore(archive)
    assert error.value.code == 'BACKUP_INVALID'
    with db.connect() as c:
        assert c.execute('SELECT id FROM financial_source').fetchone()[0] == identity


def test_booking_exact_amount_outside_window_has_date_reason(db):
    import_sample(db)
    add_references(db, [('20260001', 'R1', '1234567890')])
    cash = seed(db, 'CASHBOOK_CARD')
    seed(db, 'BOOKING', departure='2026-09-15')
    assert MatchingService(db, SettingsService(db)).run()['created_groups'] == 0
    with db.connect() as c:
        assert c.execute('SELECT code FROM work_reason WHERE object_id=?', (cash,)).fetchone()[0] == 'MATCH_DATE_OUTSIDE_WINDOW'


def schema_three(db):
    with db.connect() as c:
        c.execute('DROP TRIGGER membership_source_only_INSERT')
        c.execute('DROP TRIGGER membership_source_only_UPDATE')
        c.execute('DELETE FROM schema_migration WHERE version=4')
        c.execute('PRAGMA user_version=3')


def test_schema_three_is_backed_up_before_upgrade(db, tmp_path):
    identity = seed(db, 'CASHBOOK_CARD')
    schema_three(db)
    Database(db.path)
    archive, = db.path.parent.glob('before-migration-3-*.zip')
    manifest, raw = BackupService(db).inspect(archive)
    assert manifest['schema'] == 3
    original = tmp_path / 'original.sqlite'
    original.write_bytes(raw)
    with sqlite3.connect(original) as c:
        assert c.execute('PRAGMA user_version').fetchone()[0] == 3
        assert c.execute('SELECT id FROM financial_source').fetchone()[0] == identity
    with db.connect() as c:
        assert c.execute('PRAGMA user_version').fetchone()[0] == 4
        assert c.execute('SELECT id FROM financial_source').fetchone()[0] == identity


def test_migration_backup_failure_leaves_old_schema(db, monkeypatch):
    schema_three(db)
    def fail(*args):
        raise OSError('simulated backup failure')
    monkeypatch.setattr(Database, '_migration_backup', fail)
    with pytest.raises(OSError):
        Database(db.path)
    with db.connect() as c:
        assert c.execute('PRAGMA user_version').fetchone()[0] == 3
        assert c.execute("SELECT count(*) FROM sqlite_master WHERE name='membership_source_only_INSERT'").fetchone()[0] == 0


def test_cash_reversal_scan_can_be_cancelled():
    from kajovokarty.domain.matching_windows import cash_reversals
    from test_matching_windows import row
    rows = [row(str(i), 'CASHBOOK_CARD', 100) for i in range(100)]
    calls = []
    def cancel():
        calls.append(True)
        if len(calls) == 2:
            raise AppError('CANCELLED', 'test')
    with pytest.raises(AppError) as error:
        cash_reversals(rows, cancel)
    assert error.value.code == 'CANCELLED' and len(calls) == 2


@pytest.mark.parametrize('name', ['data.db', 'data.sqlite3', 'data.sqlite-wal', 'app.log', 'debug.jsonl', '.env', '.env.local', 'cert.pfx'])
def test_source_package_excludes_private_artifacts(name):
    import importlib.util
    from pathlib import Path
    path = Path(__file__).parents[1] / 'tools/package_repo.py'
    spec = importlib.util.spec_from_file_location('package_repo', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.private_artifact(Path(name))
    assert not module.private_artifact(Path('src/application.py'))


def test_daily_retention_preserves_unrelated_zip(db, tmp_path):
    from datetime import date
    backup = BackupService(db)
    valid = tmp_path / 'auto-2020-01-01.zip'
    keep = tmp_path / 'auto-2026-09-16.zip'
    unrelated = tmp_path / 'auto-2020-01-02.zip'
    backup.backup(valid)
    backup.backup(keep)
    with zipfile.ZipFile(unrelated, 'w') as archive:
        archive.writestr('family.txt', 'not application data')
    original = unrelated.read_bytes()
    assert backup.prune_daily(tmp_path, date(2026, 9, 1), keep) == [valid.name]
    assert unrelated.read_bytes() == original and keep.exists()


def test_duplicate_rows_inside_single_transfer_are_ignored():
    from PySide6.QtWidgets import QApplication
    from kajovokarty.ui.pairing_panel import PairingPanel
    app = QApplication.instance() or QApplication([])
    panel = PairingPanel('test')
    row = {'id': 'one', 'currency': 'EUR', 'difference': 5000}
    panel.add_rows([row, row])
    assert panel.model.rowCount() == 1 and len(panel.draft_rows) == 1
    panel.dirty = False
    panel.close()
    app.processEvents()


def test_release_versions_and_error_reference_agree():
    import importlib.util
    from pathlib import Path
    import tomllib
    from kajovokarty import __version__
    root = Path(__file__).parents[1]
    assert tomllib.loads((root / 'pyproject.toml').read_text())['project']['version'] == __version__
    assert f'#define AppVersion "{__version__}"' in (root / 'tools/installer.iss').read_text()
    spec = importlib.util.spec_from_file_location('error_catalog', root / 'tools/error_catalog.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert (root / 'docs/ERROR_CATALOG.md').read_text(encoding='utf-8') == module.render()


def test_snapshot_cleanup_failure_does_not_report_committed_import_as_failed(db, fixtures, monkeypatch):
    from pathlib import Path
    from kajovokarty.application.import_batch import ImportBatchService
    from kajovokarty.application.imports import ImportInput
    batch = ImportBatchService(db)
    original_discard = batch.importer.discard
    def fail_cleanup(preview_id):
        # A failure after commit, such as antivirus temporarily locking a snapshot.
        original_discard(preview_id)
        raise PermissionError('simulated cleanup failure')
    monkeypatch.setattr(batch.importer, 'discard', fail_cleanup)
    result = batch.run([ImportInput('BOOKING', str(Path(fixtures) / 'booking_a.csv'))])
    assert result[0]['state'] == 'COMPLETED'
    assert result[0]['added'] == 21
    assert result[0]['warnings']
    with db.connect() as c:
        assert c.execute('SELECT count(*) FROM financial_source').fetchone()[0] == 21
        assert c.execute("SELECT state FROM operation WHERE type='IMPORT'").fetchone()[0] == 'COMPLETED'


def test_incomplete_selftest_arguments_never_open_standard_workspace(monkeypatch):
    import sys
    from kajovokarty.bootstrap.main import main
    monkeypatch.setattr(sys, 'argv', ['KajovoKarty', '--self-test-report'])
    assert main() == 2
