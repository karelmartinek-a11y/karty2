# KájovoKarty 0.4.5

Lokální česká aplikace Windows / Python 3.12 / PySide6 pro párování karetní pokladny, terminálu a Booking.com. Pracuje s CZK a EUR bez převodů měn. Data jsou v SQLite, pomocné vazby se importují z Účtů (XLS); provoz nepotřebuje API token.

## Aktuální dokumentace

- [SSOT — závazná pravidla](docs/SSOT.md)
- [Pracovní postup a kompaktní tabulky](docs/WORKFLOW_CURRENT.md)
- [Audit 0.4.5, výsledky a omezení](docs/AUDIT_0_4_5.md)
- [Import Účtů](docs/ACCOUNTS_IMPORT.md), [Booking](docs/BOOKING_IMPORT.md), [průběh všech importů](docs/IMPORT_PROGRESS.md)
- [Katalog chyb](docs/ERROR_CATALOG.md)
- [Přehled dokumentace a historických protokolů](docs/INDEX.md)

Verzované starší protokoly popisují tehdejší stav, nikoli aktuální chování. Aktuální schéma databáze je **4**, aplikační verze **0.4.5**. Úspěšný test není záruka neexistence dalších vad.

## Pracovní postup

1. Importovat → vybrat zdroj a soubory → sledovat průběh → zkontrolovat výsledek → Hotovo. Každý soubor se ukládá atomicky; chyba jednoho nevrací dříve dokončené soubory.
2. Volitelně importovat Účty (XLS): Variabilní symbol, Číslo rezervace, Original ID.
3. Výslovně spustit Automaticky spárovat vše. Pořadí a ochrany stanovuje SSOT.
4. Ručně přidat platby do párovací plochy tlačítkem nebo přetažením. Návrh nic neukládá. Tlačítko Uložit skupinu vytvoří jednu vyrovnanou skupinu; všechny pohledy se aktualizují.
5. Vyhledat kandidáty nastaví zdrojový filtr na ostatní zdroje podle první položky návrhu. Filtr lze změnit.
6. Uložené operace lze podle jejich aktuálnosti vracet přes Ctrl+Z / Ctrl+Y. Import se nevrací. Exporty jsou CSV ZIP, XLSX a PDF.

Automatika zahrnuje jednoznačné dvojice a doložené součtové skupiny. Výchozí tolerance je dva pracovní dny bez víkendů a českých svátků. Booking používá datum odjezdu; pomocné Booking ID neblokuje terminálové párování. Pokladní storno se hledá proti normálnímu záznamu s opačnou částkou do dvou kalendářních dnů. Přesné podmínky, priority a limity jsou v SSOT.

## Vývoj a ověření

Windows, Python 3.12 x64:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements-dev.lock
.\.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .
.\.venv\Scripts\python.exe -m kajovokarty
.\.venv\Scripts\python.exe -m ruff check src tests tools --select F --no-cache
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

Zdrojové složky: domain (finanční pravidla), application (operace), infrastructure (SQLite, import/export, soubory), ui (Qt), migrations (schéma). Testy používají izolované databáze. Historické API moduly existují pro kompatibilitu a testy; současný pracovní postup je nevyžaduje.

## Sestavení a distribuce

```powershell
powershell -ExecutionPolicy Bypass -File tools\build_windows.ps1
```

Vyžaduje Python 3.12 x64 a Inno Setup 6. Skript používá oddělené prostředí .tmp/build-venv, kontroluje závislosti a testy, sbírá licence, sestaví PyInstaller onedir, provede izolovaný test skutečného EXE a vytvoří instalátor v dist/installer. Selhání zastaví sestavení. Výsledná aplikace obsahuje Python, Qt, parsery, font i tzdata a při spuštění nic neinstaluje. Pomocný start.bat slouží ke spuštění zdrojů a může instalovat hashově zamčené vývojové závislosti.

Zdrojový manifest, distribuční hash a auditní protokoly musejí odpovídat stejnému finálnímu stavu. Sestavení instalátoru není dokladem jeho instalace na čistém počítači; skutečný rozsah ověření uvádí audit.

## Data, zálohy a přechod

Výchozí data jsou v LocalAppData/KajovoKarty/data. Odinstalátor je nemaže. Při přechodu ze schématu 3 se před migrací na 4 vytvoří ověřená záloha bez tajemství; starší migrační cesty jsou zachované. Aktivní skupiny ve schématu 4 mají přímé zdrojové členy, historický audit zůstává zachován.

Záloha, obnova a přesun jsou dostupné v Nastavení. Úplný reset vyžaduje samostatné potvrzení VYMAZAT a odstraňuje také rozpoznané zálohy. Není nástrojem pro opravu chybějících oprávnění. Původní importy mimo pracovní prostor a cizí soubory nesmí odstranit.

Toto vydání se ověřuje na izolovaných datech; audit nesmí automaticky opravovat provozní databázi ani instalovat přes používanou aplikaci.
