"""Verify live read-only BetterHotel access on an isolated database backup."""
import json
import sqlite3
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from kajovokarty.infrastructure.database import Database
from kajovokarty.application.settings import SettingsService
from kajovokarty.application.sync import SyncService
from kajovokarty.infrastructure.betterhotel import BetterHotelClient


class RecordedClient(BetterHotelClient):
    """Keep private response evidence for deterministic offline regression replay."""
    def __init__(self, *args, evidence, replay=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.evidence = sqlite3.connect(evidence)
        self.evidence.execute('CREATE TABLE IF NOT EXISTS response (key TEXT PRIMARY KEY, body TEXT)')
        self.pending_evidence = 0
        paths = replay if isinstance(replay, list) else [replay] if replay else []
        self.replays = [sqlite3.connect(p.resolve().as_uri() + '?mode=ro', uri=True) for p in paths]
        if self.replays:
            self.evidence_class = 'RECORDED_API_WITH_LIVE_MISSES'

    def get(self, template, ids=None, params=None):
        key = json.dumps([template, ids, params], sort_keys=True)
        cached = next((row for db in self.replays
                       if (row := db.execute('SELECT body FROM response WHERE key=?', (key,)).fetchone())), None)
        body = json.loads(cached[0]) if cached else super().get(template, ids, params)
        self.evidence.execute('INSERT OR REPLACE INTO response VALUES (?,?)',
                              (key, json.dumps(body)))
        self.pending_evidence += 1
        # Live responses must survive interruption immediately. Replayed responses
        # already exist durably in the input file, so copy them in batches.
        if not cached or self.pending_evidence >= 100:
            self.evidence.commit()
            self.pending_evidence = 0
        return body

    def close(self):
        self.evidence.commit()
        for db in self.replays:
            db.close()
        self.evidence.close()
        super().close()


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--replay', type=Path, action='append', help='Replay recorded responses (repeatable, first file wins); fetch missing requests live. Not a fresh live verification.')
    parser.add_argument('--resume-folder', type=Path, help='Resume the last checkpoint in an existing isolated verification folder.')
    args = parser.parse_args()
    folder = args.resume_folder.resolve() if args.resume_folder else Path(tempfile.mkdtemp(prefix='verify-sync-', dir=args.output))
    if not folder.resolve().is_relative_to(args.output.resolve()):
        raise ValueError('Verification folder must be inside the specified output directory')
    target = folder / 'verification.sqlite'
    if args.resume_folder:
        if not target.is_file():
            raise ValueError('Verification database does not exist')
    else:
        with sqlite3.connect(args.source.resolve().as_uri() + '?mode=ro', uri=True) as src:
            with sqlite3.connect(target) as dst:
                src.backup(dst)
    db = Database(target)
    settings = SettingsService(db)
    class ReadOnlySource:
        path = args.source.resolve()
        @contextmanager
        def connect(self):
            connection = sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True)
            connection.row_factory = sqlite3.Row
            try:
                yield connection
            finally:
                connection.close()
    source_db = ReadOnlySource()
    if args.resume_folder:
        with source_db.connect() as source, db.connect() as isolated:
            query = 'SELECT context_id,credential_revision FROM helper_state'
            if tuple(source.execute(query).fetchone()) != tuple(isolated.execute(query).fetchone()):
                raise ValueError('Connection changed; start a new isolated verification')
    credentials = SettingsService(source_db) if args.resume_folder else settings
    access, token = credentials.tokens()
    proxy = credentials.proxy_auth()
    config = settings.get()
    with db.connect() as c:
        # Keep the verification database free of stored credentials.
        c.execute('DELETE FROM secret')
        previous = c.execute("SELECT planned_scope_json FROM helper_state").fetchone()[0]
    scope = json.loads(previous)
    scope = (scope['start'], scope['end']) if 'start' in scope else SyncService(db, settings).scope()
    print('Verification folder:', folder, 'scope:', scope, flush=True)
    last = 0.0
    latest = {}
    def progress(event):
        nonlocal last, latest
        if isinstance(event, dict) and event.get('type') == 'sync_progress':
            latest = event
        if time.monotonic() - last > 30:
            print('Live requests:', sum(len(s['status_codes']) for s in http.stats.values()),
                  'responses:', sum(s['response_count'] for s in http.stats.values()),
                  'phase:', latest.get('phase'), latest.get('completed'), '/', latest.get('total'), flush=True)
            (folder / 'progress.json').write_text(json.dumps(latest), encoding='utf-8')
            last = time.monotonic()
    http = RecordedClient(access, token, config, proxy_auth=proxy, progress=progress,
                          evidence=folder / 'responses.sqlite', replay=args.replay)
    try:
        sync = SyncService(db, settings)
        if args.resume_folder:
            with db.connect() as c:
                operation = c.execute("SELECT id FROM operation WHERE type='SYNC' ORDER BY started_at DESC LIMIT 1").fetchone()[0]
            result = sync.resume(http, operation, progress)
        else:
            result = sync.full(http, scope=scope, progress=progress)
        with db.connect() as c:
            result['operation_state'] = c.execute('SELECT state FROM operation WHERE id=?', (result['operation_id'],)).fetchone()[0]
            result['integrity'] = c.execute('PRAGMA integrity_check').fetchone()[0]
        result['verification_mode'] = 'replay-with-live-misses' if args.replay else ('live-resumed' if args.resume_folder else 'live')
        (folder / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result), flush=True)
        assert result['status'] == 'READY' and result['operation_state'] == 'COMPLETED'
        assert result['integrity'] == 'ok'
    except Exception as error:
        failure = {'failure': type(error).__name__,
                          'code': getattr(error, 'code', None),
                          'details': getattr(error, 'details', {})}
        (folder / 'failure.json').write_text(json.dumps(failure), encoding='utf-8')
        print(json.dumps(failure), flush=True)
        raise
    finally:
        http.close()


if __name__ == '__main__':
    main()
