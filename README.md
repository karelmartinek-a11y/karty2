# KájovoKarty

Česká desktopová aplikace Python 3.12 / PySide6 pro rekonsiliaci pokladních karet, terminálových transakcí a výplat Booking.com. Data zůstávají v lokální SQLite databázi. BetterHotel API je nahrazeno ručním importem **Účty (XLS)**.

**Verze 0.4.0:** Účty načtou pouze Variabilní symbol, Číslo rezervace a Original ID. Podle VS pokladny se vyhledá Original ID a jednotlivá Booking platba se stejnou rezervací, měnou a přesnou částkou. Součty ani zaokrouhlení se nepoužívají. První dvojice rezervací zůstává neměnná; další VS ke stejné dvojici lze doplnit. Nejednoznačné případy zůstávají ruční. Podrobnosti: [docs/ACCOUNTS_IMPORT.md](docs/ACCOUNTS_IMPORT.md).

**Verze 0.3.2** přidává živé průběhové okno automatiky: aktuální krok, dokončené a zbývající jednotky kroku, uložené shody po měnách, čas a bezpečné zrušení. Podrobnosti: [docs/AUTO_PROGRESS.md](docs/AUTO_PROGRESS.md).

Verze 0.3.1 opravuje automatické párování: pouze výslovné tlačítko, kontrola platnosti důkazů při každém zápisu, bezpečné zrušení, trvalý výsledek po měnách a zachování starších zákazů spojení. Forenzní nálezy a testy: [docs/AUTO_AUDIT.md](docs/AUTO_AUDIT.md). Přetahování plateb a Excelové sloupcové filtry z 0.3.0 zůstávají popsané v [docs/UI_WORKFLOW.md](docs/UI_WORKFLOW.md).

Dodávka obsahuje zdrojový repozitář a předpis sestavení Windows instalátoru. Sestavený EXE není součástí ZIPu. Zjištění z živého BetterHotel API, opravy importu a stav jejich ověření popisuje [protokol z 11. 9. 2026](docs/betterhotel-import-fix-2026-09-11.md). Testování na čistém Windows profilu dosud neproběhlo; úplná akceptace SSOT není prohlášena.

## Obsah

- `src/kajovokarty/domain`: přesné částky, normalizace, Booking reference a kandidátní grafy.
- `src/kajovokarty/application`: atomické importy, finanční skupiny, Undo/Redo, automatika, reference, sestavy a zálohy; historický pomocný model kvůli starým důkazům.
- `src/kajovokarty/infrastructure`: XLS/CSV/XLSX parsery, SQLite a migrace a exportní formáty.
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

Linux slouží také pro lokální testy a prohlídku rozhraní. Aplikace nevyžaduje API tokeny.

## Windows distribuce

Na Windows s Pythonem 3.12 x64 a Inno Setup 6 spusťte:

```powershell
powershell -ExecutionPolicy Bypass -File tools\build_windows.ps1
```

Skript instaluje hashově zamčené vývojové závislosti, spouští testy, sbírá licence, vytvoří PyInstaller onedir a potom EXE instalátor v `dist/installer`. Při chybě kteréhokoli kroku skončí. To není instalace závislostí při startu aplikace: výsledný onedir produkt obsahuje Python, Qt, parsery, font i tzdata.

Aplikace nepoužívá `.env`, aplikační účty ani povinné CLI argumenty. Výchozí data jsou v `LocalAppData/KajovoKarty/data`; odinstalátor je nemaže. Import, start ani filtr samy nespouštějí párování.

## Základní pracovní postup

Booking CSV umožňuje vybrat více souborů najednou a načítá je postupně. Výsledek srozumitelně uvádí počty načtených a vynechaných plateb i důvody. Podrobnosti: [Import plateb z Bookingu](docs/BOOKING_IMPORT.md).

1. Importovat → typ zdroje → soubory → náhled → Importovat.
2. Importovat → Účty (XLS) → náhled → Importovat. Uložené vazby jsou v Pomocných datech.
3. Výslovně spustit automatické párování, nebo doplňovat pracovní výběr.
4. Vytvořit skupinu: nulový rozdíl znamená Vyřízeno, jiný rozdíl otevřenou skupinu. CZK a EUR nelze spojit.
5. Přetáhnout platbu na jinou platbu nebo skupinu. Párovací plocha ukáže členy a rozdíl; přetažením člena do zóny Rozpárovat jej vyjmete. Každý přesun vrátí Ctrl+Z.
6. Detail obsahuje jedinečné listy, původní částky, JSON důkaz a audit. Rozložení zachovává podskupiny.
7. Sestavy lze uložit jako CSV ZIP, XLSX nebo PDF. Nastavení obsahuje zálohu, obnovu, přesun datové složky a anonymní diagnostiku.

Původní testovací soubory obsahují údaje z uživatelem dodaného SSOT. Produkční prázdná databáze se těmito daty automaticky neplní.

## Přechod ze starších verzí

Spusťte 0.4.0 nad existující datovou složkou. Před migrací ze schématu 1 nebo 2 vznikne ověřená záloha bez tokenů. Migrace na schéma 3 zachová finanční zdroje, existující skupiny i historii a přidá prázdnou databázi vazeb Účtů. Starý API graf se pro nové párování nepoužívá. Při chybě umístění nebo databáze se otevře zotavení, prázdná náhradní databáze se tiše nevytváří.

Přesun se provádí přes Nastavení a restartuje aplikaci. Původní složka zůstává zachována. Záloha zahrnuje vazby z Účtů a jejich importní původ. Ruční editace SQLite ani bootstrap souboru není běžný pracovní postup.

Verze 0.3.0 používá stejné databázové schéma 2 jako 0.2.0. Nové přesuny využívají existující příkazy, historii a audit; finanční zdroje se nepřepisují.

Automatika běží jen po stisku **Automaticky spárovat vše**, vždy nad celou databází. Výsledek je dostupný i později v Nastavení → operace AUTO_MATCH → detail. Po zrušení zůstanou dokončené skupiny zachovány; pokračování vyžaduje další výslovný stisk tlačítka.
