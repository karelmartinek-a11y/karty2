"""Generate the Czech error reference from the runtime catalog, or check for drift."""
import argparse
from pathlib import Path
from kajovokarty.domain.errors import CATALOG


def render():
    lines = ['# Přehled chyb a upozornění', '',
             'Generováno z `domain/errors.py`. Ruční úpravy přepište v číselníku, nikoli zde.', '',
             '| Kód | Závažnost | Název | Vysvětlení | Další krok |',
             '|---|---|---|---|---|']
    for code, item in sorted(CATALOG.items()):
        cells = [code, item.severity, item.name, item.description, item.action]
        lines.append('| ' + ' | '.join(c.replace('|', '\\|').replace('\n', ' ') for c in cells) + ' |')
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    target = Path(__file__).resolve().parents[1] / 'docs/ERROR_CATALOG.md'
    expected = render()
    if args.check:
        if target.read_text(encoding='utf-8') != expected:
            raise SystemExit('Error catalog is stale. Run tools/error_catalog.py.')
    else:
        target.write_text(expected, encoding='utf-8')
