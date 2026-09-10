# KájovoKarty

Česká desktopová aplikace Python 3.12 / PySide6 pro rekonsiliaci pokladních karet, terminálových transakcí a výplat Booking.com. Finanční data zůstávají v lokální SQLite databázi, BetterHotel se pouze čte přes GET.

**Verze 0.3.2** přidává živé průběhové okno automatiky: aktuální krok, dokončené a zbývající jednotky kroku, uložené shody po měnách, čas a bezpečné zrušení. Podrobnosti: [docs/AUTO_PROGRESS.md](docs/AUTO_PROGRESS.md).

Verze 0.3.1 opravuje automatické párování: pouze výslovné tlačítko, kontrola platnosti důkazů při každém zápisu, bezpečné zrušení, trvalý výsledek po měnách a zachování starších zákazů spojení. Forenzní nálezy a testy: [docs/AUTO_AUDIT.md](docs/AUTO_AUDIT.md). Přetahování plateb a Excelové sloupcové filtry z 0.3.0 zůstávají popsané v [docs/UI_WORKFLOW.md](docs/UI_WORKFLOW.md).

Dodávka obsahuje zdrojový repozitář a předpis sestavení Windows instalátoru. Sestavený EXE není součástí ZIPu. Testování na čistém Windows profilu a s živým BetterHotel API dosud neproběhlo; úplná akceptace SSOT proto není prohlášena.

## Obsah

- `src/kajovokarty/domain`: přesné částky, normalizace, Booking reference a kandidátní grafy.
- `src/kajovokarty/application`: atomické importy, finanční skupiny, Undo/Redo, automatika, synchronizace a cílená obnova, reference, sestavy a zálohy.
- `src/kajovokarty/infrastructure`: přísné XLS/CSV/XLSX parsery, SQLite a migrace, DPAPI, GET klient a exportní formáty.
- `src/kajovokarty/ui`: skutečné české PySide6 rozhraní, tabulkové modely a background workery.
- `docs/SSOT.md`: zadání s aktualizací ovládání 0.3.0 v oddílech 9.4 a 11.6.
- `fixtures`: všech pět přesně rekonstruovaných souborů přílohy B.
- `tests`: integrační, doménové, HTTP, vlastnostní a Qt testy.
- `requirements.lock`, `requirements-dev.lock`: úplné verze závislostí s SHA-256 hashi.
- `tools/build_windows.ps1`, `KajovoKarty.spec`, `tools/installer.iss`: sestavení offline Windows produktu a instalátoru bez administrátorských práv.
- `LICENSES`: licence skutečně použitých knihoven a vloženého fontu.

## Spuštění zdrojové verze vývojářem

Windows, Python 3.12 x64:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements-dev.lock
.\.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .
.\.venv\Scripts\python.exe -m kajovokarty
```

Testy:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Linux slouží pro lokální testy a prohlídku rozhraní. Ukládání skutečných tokenů je záměrně dostupné pouze přes Windows DPAPI; žádný plaintext fallback se nepoužívá.

## Windows distribuce

Na Windows s Pythonem 3.12 x64 a Inno Setup 6 spusťte:

```powershell
powershell -ExecutionPolicy Bypass -File tools\build_windows.ps1
```

Skript instaluje hashově zamčené vývojové závislosti, spouští testy, sbírá licence, vytvoří PyInstaller onedir a potom EXE instalátor v `dist/installer`. Při chybě kteréhokoli kroku skončí. To není instalace závislostí při startu aplikace: výsledný onedir produkt obsahuje Python, Qt, parsery, font i tzdata.

Aplikace nepoužívá `.env`, aplikační účty ani povinné CLI argumenty. Výchozí data jsou v `LocalAppData/KajovoKarty/data`; odinstalátor je nemaže. Pro nové čtení API se oba tokeny zadávají v Nastavení. Import, start ani filtr samy nespouštějí párování nebo API synchronizaci.

## Základní pracovní postup

1. Importovat → typ zdroje → soubory → náhled → Importovat.
2. Nastavení → uložit Access Token a Client Token → Načíst BetterHotel.
3. Výslovně spustit automatické párování, nebo doplňovat pracovní výběr.
4. Vytvořit skupinu: nulový rozdíl znamená Vyřízeno, jiný rozdíl otevřenou skupinu. CZK a EUR nelze spojit.
5. Přetáhnout platbu na jinou platbu nebo skupinu. Párovací plocha ukáže členy a rozdíl; přetažením člena do zóny Rozpárovat jej vyjmete. Každý přesun vrátí Ctrl+Z.
6. Detail obsahuje jedinečné listy, původní částky, JSON důkaz a audit. Rozložení zachovává podskupiny.
7. Sestavy lze uložit jako CSV ZIP, XLSX nebo PDF. Nastavení obsahuje zálohu, obnovu, přesun datové složky a anonymní diagnostiku.

Původní testovací soubory obsahují údaje z uživatelem dodaného SSOT. Produkční prázdná databáze se těmito daty automaticky neplní.

## Přechod z 0.1.0

Spusťte 0.3.2 nad existující datovou složkou. Před migrací ze schématu 1 vznikne ověřená záloha bez tokenů. Migrace 002 je atomická a zachová finanční zdroje i historii. Pomocný graf se označí STALE; před novým použitím v automatice proveďte úplné načtení BetterHotel. Při chybě umístění nebo databáze se otevře zotavení, prázdná náhradní databáze se tiše nevytváří.

Přesun se provádí přes Nastavení a restartuje aplikaci. Původní složka zůstává zachována. Záloha neobsahuje přihlašovací tajemství; na jiném počítači je nutné tokeny znovu zadat. Ruční editace SQLite ani bootstrap souboru není běžný pracovní postup.

Verze 0.3.0 používá stejné databázové schéma 2 jako 0.2.0. Nové přesuny využívají existující příkazy, historii a audit; finanční zdroje se nepřepisují.

Automatika běží jen po stisku **Automaticky spárovat vše**, vždy nad celou databází. Výsledek je dostupný i později v Nastavení → operace AUTO_MATCH → detail. Po zrušení zůstanou dokončené skupiny zachovány; pokračování vyžaduje další výslovný stisk tlačítka.
