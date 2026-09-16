"""Check pinned distributions against PyPI version metadata; no credentials/data sent."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from urllib.request import urlopen


def inspect(pin):
    name, version = pin
    url = f'https://pypi.org/pypi/{name}/{version}/json'
    try:
        with urlopen(url, timeout=30) as response:
            data = json.load(response)
        return dict(name=name, version=version, source=url,
                    vulnerabilities=data.get('vulnerabilities', []),
                    yanked=bool(data['urls']) and all(f['yanked'] for f in data['urls']))
    except Exception as error:
        return dict(name=name, version=version, source=url, error=type(error).__name__)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    pins = set(re.findall(r'^([\w.-]+)==([^\s;]+)',
                         (root / 'requirements-dev.lock').read_text(encoding='utf-8'), re.M))
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(inspect, sorted(pins)))
    report = dict(checked_at=datetime.now(timezone.utc).isoformat(), packages=results,
                  scope='PyPI advisories for locked Python packages; not a native DLL security audit')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    for row in results:
        if row.get('error') or row.get('vulnerabilities') or row.get('yanked'):
            print(row['name'], row['version'], row.get('error'),
                  [v['id'] for v in row.get('vulnerabilities', [])], 'yanked=', row.get('yanked'))
    print(f'Checked {len(results)} pinned distributions.')


if __name__ == '__main__':
    main()
