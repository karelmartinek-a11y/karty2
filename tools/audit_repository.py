"""Inventory and parse every owned Python module without opening application data."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import platform
import subprocess
from datetime import datetime, timezone


def inventory(root):
    files = {}
    for folder in ('src', 'tests', 'tools', 'docs'):
        for path in sorted((root / folder).rglob('*')):
            if not path.is_file() or '__pycache__' in path.parts:
                continue
            raw = path.read_bytes()
            item = {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
            if path.suffix == '.py':
                tree = ast.parse(raw, filename=str(path.relative_to(root)))
                item.update(lines=len(raw.splitlines()),
                            functions=sum(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                                          for n in ast.walk(tree)))
            files[path.relative_to(root).as_posix()] = item
    for path in sorted(root.iterdir()):
        if path.is_file():
            raw = path.read_bytes()
            files[path.name] = {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
    return {'created_at': datetime.now(timezone.utc).isoformat(),
            'python': platform.python_version(), 'platform': platform.platform(),
            'git_status': subprocess.check_output(['git', 'status', '--short'], cwd=root, text=True),
            'files': files}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = inventory(Path(__file__).resolve().parents[1])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f"Inventoried {len(report['files'])} files; all Python files parsed.")


if __name__ == '__main__':
    main()
