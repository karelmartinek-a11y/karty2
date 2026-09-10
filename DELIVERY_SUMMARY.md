# Dodávka KájovoKarty 0.2.0

Vstup: KajovoKarty_repozitar_0.1.0(1).zip. Závazné zadání: nezměněný docs/SSOT.md. Výstup je celý repozitář, nikoli patch. Verze zdrojů a instalačního předpisu je 0.2.0; schéma databáze 2.

## Provedené změny

- HTTP klient: přesné expand parametry, token bucket s kapacitou 10, deadline celého pokusu, rušení, Retry-After, proxy autentizace, trvalé selhání semanticky neplatné šablony a rozlišení lokálního kontraktu od živého pozorování.
- Databáze: zálohovaná atomická migrace 001→002, úplná dostupnost polí finančních subtypů přes generované sloupce nad neměnným payloadem, doplňující ochrany identit, kontextů, publikovaných generací a uzavřenosti grafu. Neměnné finanční částky se nepřepisují.
- FULL/DETAIL: průběžné raw snapshoty a observations, samostatné RELATION_EDGE důkazy, přesné request-shape hashe, uchování neaktivních hran, kontrola rodičů, stabilní revize stejného obsahu, cílená obnova kaucí a bezpečné chování při neúspěchu.
- Párování a přehledy: indexované kandidáty, průběžná kontrola rušení, pevný bod A.7, silná oboustranná nejednoznačnost C, důvody nevyřízených položek a SQL filtrování/stránkování nad 100 000 listy a 20 000 skupinami.
- UI: všechny filtrované výsledky přes Ctrl+A, zachování vícevýběru, lokální i historické hledání, OR/AND filtry, vnořený detail skupiny, protějšky, přetažení do skupiny, klávesové a kontextové cesty registru akcí.
- Nastavení: atomické uložení, DPAPI proxy tajemství, maskování s časovým limitem, adresáře, kontrast, velikost textu a hustota řádků. Přesun datové složky s kontrolou BLOB a restartem; zotavení po poškození databáze.
- Sestavy: jediný read snapshot, výběr nezávislý na filtru, explicitní historické helper grafy a uzávěry, určené pořadí sad a řádků, PDF s opakovanými hlavičkami a plnými důkazovými detaily, atomická publikace a zrušení exportu. Diagnostický ZIP filtruje technické logy pomocí allowlistu.

## Ověření

Příkazy spuštěné z kořene pracovního repozitáře na Linuxu (Python prostředí bylo převzato z rozbalené původní dodávky):

```sh
QT_QPA_PLATFORM=offscreen ../KajovoKarty/.venv/bin/python -m pytest -q --junitxml=docs/test-results.xml
../KajovoKarty/.venv/bin/ruff check src tools tests --select F
../KajovoKarty/.venv/bin/ruff format src tools tests
PYTHONPATH=src ../KajovoKarty/.venv/bin/python tools/benchmark.py
../KajovoKarty/.venv/bin/python tools/build_manifest.py
../KajovoKarty/.venv/bin/python tools/package_repo.py
```

Celá sada: **91 passed in 31.69s**, bez vynechaných testů. Ruff F: **All checks passed**. Benchmark obsahuje skutečné Linux měření; detaily v docs/load-probe.json. Obrázek docs/ui-overview.png zachycuje skutečné Qt okno s 21 importovanými řádky vzoru Booking. Testy běžely i po opravě provenance, diagnostiky a rozdělení smíšeného exportu. Benchmark byl proveden před závěrečnou opravou reference statusu a sanitizace logů; měřená SQL cesta se tím nezměnila.

V běžném čistém checkoutu nahraďte cestu k Pythonu vlastní .venv podle README. Přesný protokol, nepokryté scénáře a externí akceptační brány jsou v docs/VALIDATION.md. Nativní Windows instalátor ani živé endpointy nebyly v tomto prostředí spuštěny. Tato dodávka není označena za akceptované splnění všech bodů kapitol 17–18.

## Integrita balíku

MANIFEST.sha256 obsahuje hashe všech distribuovaných souborů kromě sebe. docs/source-build-manifest.json identifikuje zdrojové/build vstupy; není to hash Windows EXE. Archiv neobsahuje virtuální prostředí, cache, lokální pracovní databáze ani provozní tokeny. Vzory fixtures jsou přesné vstupy z uživatelova SSOT a obsahují jeho ukázková data.

Archivaci lze zopakovat příkazem `python tools/package_repo.py`. Cesty jsou řazeny, časové značky ZIPu pevné a každý soubor je po zápisu kontrolován proti manifestu. Stejné vstupní bajty vytvoří shodný archiv.
