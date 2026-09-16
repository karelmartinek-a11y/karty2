"""Small reproducible synthetic probes, not a production/reference-machine benchmark."""
import argparse
import csv
import json
from pathlib import Path
import platform
import statistics
import tempfile
import time

from kajovokarty.application.imports import ImportInput, ImportService
from kajovokarty.application.pairing import PairingService
from kajovokarty.application.work import WorkService
from kajovokarty.domain.matching_windows import cash_reversals, sum_candidates
from kajovokarty.infrastructure.database import Database
from kajovokarty.infrastructure.parsers import BOOK_HEADERS


def timed(fn, count=3):
    samples = []
    for _ in range(count):
        start = time.perf_counter()
        fn()
        samples.append(time.perf_counter() - start)
    return {'samples_seconds': samples, 'median_seconds': statistics.median(samples)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    results = {'platform': platform.platform(), 'python': platform.python_version(), 'probes': []}
    for size in (100, 500, 1000):
        rows = [dict(id=str(i), kind='CASHBOOK_CARD', currency='EUR', signed_amount_minor=100,
                     local_date='2026-09-07', payload={'storno_marker': False}) for i in range(size)]
        results['probes'].append(dict(name='cash_reversals_no_match', size=size, **timed(lambda: cash_reversals(rows))))
    for size in (20, 40, 80):
        rows = [dict(id=str(i), kind='CASHBOOK_CARD' if i % 2 else 'BANK_CARD', currency='EUR',
                     signed_amount_minor=100, local_date='2026-09-07', payload={}) for i in range(size)]
        results['probes'].append(dict(name='sum_candidates_balanced', size=size, **timed(lambda: sum_candidates(rows, 2))))
    for size in (100, 1000, 5000):
        with tempfile.TemporaryDirectory(prefix='kk-performance-') as directory:
            folder = Path(directory)
            source = folder / 'source.csv'
            with source.open('w', newline='', encoding='utf-8') as stream:
                writer = csv.writer(stream)
                writer.writerow(BOOK_HEADERS)
                for i in range(size):
                    writer.writerow(['Reservation', str(1000000000+i), '2026-09-07', '2026-09-08',
                                     'Synthetic', 'Booking.com', 'ok', 'EUR', 'Paid Online', '50.00', '2026-09-10', 'QA'])
            db = Database(folder / 'data.sqlite')
            importer = ImportService(db)
            preview = importer.preflight([ImportInput('BOOKING', str(source))])
            importer.commit(preview.id)
            work = WorkService(db)
            results['probes'].append(dict(name='query_first_page', size=size, **timed(lambda: work.query())))
            rows = work.query(page_size=50)['rows']
            results['probes'].append(dict(name='hydrate_50_rows', size=size,
                                         **timed(lambda: PairingService(db).resolve_draft_rows(rows))))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2), encoding='utf-8')
    for probe in results['probes']:
        print(probe['name'], probe['size'], round(probe['median_seconds'], 4))


if __name__ == '__main__':
    main()
