"""Explicit distribution smoke test. All application data lives in a temporary directory."""
import csv
import json
from pathlib import Path
import sys
import tempfile
import time

from kajovokarty import __version__


def run(report_path):
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QDropEvent, QFontDatabase
    from PySide6.QtWidgets import QApplication
    from kajovokarty.application.backup import BackupService
    from kajovokarty.application.imports import ImportInput, ImportService
    from kajovokarty.application.reports import ReportService
    from kajovokarty.application.settings import SettingsService
    from kajovokarty.application.work import WorkService
    from kajovokarty.infrastructure.database import Database
    from kajovokarty.infrastructure.export import export
    from kajovokarty.infrastructure.parsers import BOOK_HEADERS
    from kajovokarty.ui.main import MainWindow

    report_path = Path(report_path).resolve()
    # Never overwrite a caller's file. No option to supply an application workspace.
    if report_path.exists() or not report_path.parent.is_dir():
        return 2
    app = QApplication.instance() or QApplication(['KajovoKarty self-test'])
    QFontDatabase.addApplicationFont(str(Path(__file__).parents[1] / 'assets/DejaVuSans.ttf'))
    result = {'version': __version__, 'frozen': bool(getattr(sys, 'frozen', False)), 'checks': []}
    window = None

    def wait():
        deadline = time.monotonic() + 30
        while window.jobs and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.01)
        if window.jobs:
            raise TimeoutError('GUI jobs did not finish')

    try:
        with tempfile.TemporaryDirectory(prefix='kajovokarty-selftest-') as temporary:
            folder = Path(temporary)
            db = Database(folder / 'data.sqlite')
            SettingsService(db).save({'backup.daily': False})
            source = folder / 'booking.csv'
            with source.open('w', encoding='utf-8', newline='') as stream:
                writer = csv.writer(stream)
                writer.writerow(BOOK_HEADERS)
                for reference, amount in [('1000000001', '50.00'), ('1000000002', '-50.00')]:
                    writer.writerow(['Reservation', reference, '2026-09-07', '2026-09-08',
                                     'Synthetic QA', 'Booking.com', 'ok', 'EUR', 'Paid Online',
                                     amount, '2026-09-10', 'QA'])
            importer = ImportService(db)
            preview = importer.preflight([ImportInput('BOOKING', str(source))])
            assert preview.valid
            assert importer.commit(preview.id)['new'] == 2
            result['checks'].append('import')
            work = WorkService(db)
            window = MainWindow(db)
            errors = []
            window.show_error = errors.append
            window.show()
            wait()
            rows = work.query(page_size=0)['rows']
            mime = window.table.mime_for_rows(rows)
            event = QDropEvent(QPointF(5, 5), Qt.MoveAction, mime, Qt.LeftButton, Qt.NoModifier)
            window.pair_panel.table.dropEvent(event)
            wait()
            assert event.isAccepted() and window.pair_panel.model.rowCount() == 2
            assert window.pair_panel.model.data(window.pair_panel.model.index(0, 0)) == 'B'
            for width in (1100, 1366, 1700):
                window.resize(width, 900)
                app.processEvents()
                snapshot = window.grab()
                assert not snapshot.isNull()
                image_path = report_path.with_name(report_path.stem + f'-{width}.png')
                if not image_path.exists():
                    assert snapshot.save(str(image_path))
            window.pair_panel.save.click()
            wait()
            assert work.query({'status': 'resolved'})['total'] == 1 and not errors
            result['checks'].extend(['qt_drag_details', 'save_group_live_views'])
            result['checks'].append('qt_render_1100_1366_1700')
            for format in ('zip', 'xlsx', 'pdf'):
                target = folder / ('report.' + format)
                export(ReportService(db).build('booking'), format, target)
                assert target.stat().st_size
            result['checks'].append('exports')
            backup = BackupService(db)
            backup.backup(folder / 'backup.zip')
            work.undo()
            assert work.query({'status': 'resolved'})['total'] == 0
            backup.restore(folder / 'backup.zip')
            assert work.query({'status': 'resolved'})['total'] == 1
            result['checks'].extend(['undo', 'backup_restore'])
            wait()
            window.pair_panel.dirty = False
            window.close()
            app.processEvents()
            result['status'] = 'PASS'
    except Exception as error:
        result.update(status='FAIL', exception_type=type(error).__name__)
        if window is not None:
            window.pair_panel.dirty = False
            wait()
            window.close()
    with report_path.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
    return 0 if result['status'] == 'PASS' else 1
