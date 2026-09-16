"""Compare the actual executable's owned Python code and data with the source tree."""
import argparse
import hashlib
import json
from pathlib import Path
from PyInstaller.archive.readers import CArchiveReader


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('executable', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    archive = CArchiveReader(str(args.executable))
    pyz = archive.open_embedded_archive(next(name for name in archive.toc if name.endswith('.pyz')))
    checked, mismatches = [], []
    for name in sorted(pyz.toc):
        if name != 'kajovokarty' and not name.startswith('kajovokarty.'):
            continue
        path = root / 'src' / name.replace('.', '/')
        path = path / '__init__.py' if path.is_dir() else path.with_suffix('.py')
        frozen = pyz.extract(name)
        if frozen != compile(path.read_bytes(), frozen.co_filename, 'exec', dont_inherit=True, optimize=0):
            mismatches.append(name)
        checked.append(name)
    data_checked = []
    for folder in ('assets', 'migrations'):
        for path in sorted((root / 'src/kajovokarty' / folder).rglob('*')):
            if not path.is_file() or path.suffix in ('.py', '.pyc'):
                continue
            relative = path.relative_to(root / 'src')
            packaged = args.executable.parent / '_internal' / relative
            if not packaged.is_file() or path.read_bytes() != packaged.read_bytes():
                mismatches.append(relative.as_posix())
            data_checked.append(relative.as_posix())
    result = dict(status='PASS' if checked and not mismatches else 'FAIL',
                  executable_sha256=hashlib.sha256(args.executable.read_bytes()).hexdigest(),
                  modules=checked, data=data_checked, mismatches=mismatches)
    args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(result['status'], len(checked), 'owned modules;', len(data_checked), 'data files')
    if result['status'] != 'PASS':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
