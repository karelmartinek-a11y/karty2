# Forenzní audit zdrojového projektu — 0.4.5

## Rozsah a ochrana dat

Audit navazuje na schválené změny párování a tabulek. Výchozí inventář a otisky 170 souborů včetně necommitovaných změn byly zaznamenány v místním `.tmp/audit-0.4.5/baseline.json`. Existující práce byla zachována. Provozní databáze, používaná instalace ani provozní skupiny nebyly tímto auditem měněny.

Celoplošné kontroly zahrnují parsování všech vlastních Python modulů, statickou analýzu, testy, inventář a distribuční manifesty. Ruční kontrola se soustředila na finanční pravidla, transakční hranice, vlastnictví členů, obnovu/reset, souborové cesty, logování, přenos do GUI a distribuční předpis. Nejde o důkaz ručního ověření každého možného průchodu každým řádkem ani o záruku bezchybnosti. Kód třetích stran nebyl řádek po řádku auditován.

## Potvrzené nálezy a náprava

| ID / význam | Příčina a oprava | Regresní důkaz |
|---|---|---|
| A01 / vysoký — ochrana migrace | Migrace 3 → 4 mění skupiny, ale chyběla předmigrační záloha. Nyní vzniká ověřený archiv před změnou schématu; selhání zálohy zastaví migraci. | Zachování zdrojové platby a schématu 3 v archivu, přechod na 4, simulované selhání zálohy. |
| A02 / vysoký — cizí soubory | Denní retence mazala ZIP jen podle názvu auto-datum. Nyní kontroluje strukturu a hash vlastní zálohy a přeskočí odkazy. | Platný starý archiv se odstraní; cizí ZIP shodného vzoru a ponechaná záloha zůstanou byte-for-byte zachované. |
| A03 / střední — poškozená záloha | JSON manifest jiného typu způsobil neočekávanou chybu atributu. Kontrola tvaru vrací BACKUP_INVALID před změnou dat. | Pět chybných tvarů manifestu, nezměněná původní platba. |
| A04 / střední — chybný důvod | Booking platba se shodnou částkou a měnou mimo datumové okno byla označena AMOUNT_MISMATCH. Nový informační kód MATCH_DATE_OUTSIDE_WINDOW vysvětluje skutečný důvod. | Přesná reference/částka/měna, vzdálený check-out, žádná vytvořená skupina a správný kód. |
| A05 / střední — odezva zrušení | Vnitřní dlouhé smyčky storen a dvojic neměly dostatečné body kontroly zrušení. Přidán pulse po nejvýše 1024 porovnáních. Finanční pravidla nezměněna. | Přerušení syntetického hledání a stávající testy atomického zrušení. |
| A06 / nízký — návrh skupiny | Duplicitní ID uvnitř jedné dávky se porovnávala jen s původním návrhem. Deduplikace nyní zahrnuje i právě přidávané položky. | Jedna dávka se dvěma stejnými řádky vytvoří jedinou položku. |
| A07 / střední — distribuce | Zdrojový ZIP nevylučoval alternativní databázové přípony, logy a některá tajemství; BAT instaloval nezamčené závislosti. Doplněny výluky, odmítnutí junctions a hashově zamčené spuštění. | Testy osmi citlivých názvů a pozitivní kontrola běžného zdrojového souboru; kontrola finálního archivu. |
| A08 / střední — dokumentace | SSOT/README popisovaly 1:1 automatiku, opačný význam pomocného Booking ID, staré datum, vnořování a schéma 3. Aktuální dokumenty sjednoceny; historické výsledky označeny, nikoli přepsány. | Test shody verze a generovaného katalogu, ruční porovnání se schválenými pravidly. |
| A09 / údržba | Ruff hlásil 13 nepoužitých importů/proměnných. Odstraněny bez oslabování testovaných požadavků. | Ruff F nad src/tests/tools. |
| A10 / dodavatelský řetězec | PyPI hlásilo známé vady pytest 8.3.5, setuptools 78.1.0 a wheel 0.45.1. Cílená aktualizace na 9.0.3 / 83.0.0 / 0.46.2, nově uzamčené hashe. | Kontrola 36 zamčených distribucí, pip check, následné testy a sestavení. |
| A11 / střední — reprodukovatelné sestavení | Build se pokoušel přepsat používané .venv a selhal na oprávnění. Nově používá oddělené .tmp/build-venv, ověřuje Python 3.12 x64 a neukončuje běžící aplikaci. | Nové sestavení z odděleného prostředí a zaznamenaný původní neúspěšný pokus. |
| A12 / vysoký — pravdivý výsledek importu | Výjimka při úklidu po potvrzení importu překryla úspěšný výsledek; dávka se mohla přerušit navzdory uloženým platbám. Nyní se zachová výsledek a přidá IMPORT_CLEANUP_FAILED; úklid nemůže nahradit původní chybu ani vrátit potvrzená data. | Reprodukované selhání před opravou, následně COMPLETED, 21 uložených plateb, upozornění a shodný databázový stav. |

Závažnost je prioritou nápravy v tomto projektu, nikoli CVSS. A01 a A02 jsou preventivní opravy doložené na izolovaných datech; audit netvrdí, že v provozu již nastala ztráta dat.

## Mapa kontrol

| Oblast | Implementace a ověřovací rodiny |
|---|---|
| Peníze, data, storna, součty | domain/core, payment_dates, matching_windows; test_domain, test_matching_windows, test_booking_checkout, test_group_amount |
| Priorita a bezpečnost automatiky | application/matching, auto_run, work; test_accounts, test_auto_forensic, test_forensic_regressions, test_auto_progress |
| Importní formáty, duplicity, chyby | parsers, accounts_parser, imports, import_batch; test_imports, test_import_batch_progress, test_import_formats_ui, test_booking_batch |
| Vlastnictví, návrh, Undo/Redo, živé pohledy | pairing, work, ui/main, pairing_panel; test_work, test_pairing_drag, test_pairing_ui, test_payment_presentation |
| SQL, migrace, zálohy, reset, oprávnění | database, migrations, backup, reset, workspace, file_storage; test_completion, test_reports_backup, test_reset, test_file_permissions, test_audit_release |
| Logy a export | technical_log, reports, export; test_forensic_regressions, test_reports_backup, test_completion |
| Historická kompatibilita | helper/sync/refresh moduly a archivní kontrakt; zachované test_sync_* a test_acceptance_traces |
| Distribuce a dokumentace | build_windows, package_repo, audit_* nástroje, error_catalog; test_audit_release a explicitní frozen self-test |

## Stav ověření

Finální ověření dne 16. 9. 2026 na Windows 10 x64, Python 3.12.9, v odděleném sestavovacím prostředí:

- **340 testů prošlo za 450,75 s**, žádné selhání. Jde o úplný běh po poslední opravě A12, nikoli starší předběžný výsledek 338 testů. [JUnit protokol](audit-0.4.5-tests.xml).
- Ruff F nad src/tests/tools, kontrola generovaného katalogu chyb, pip check, relativních odkazů dokumentace a git diff --check prošly.
- Kontrola 36 zamčených distribucí nevrátila známá bezpečnostní hlášení ani chyby dotazování. [Protokol závislostí](audit-0.4.5-dependencies.json). Rozsah této kontroly je omezen na metadata PyPI.
- Skutečné sestavené EXE 0.4.5 prošlo izolovaným importem, drag-and-drop s viditelnými detaily, uložením skupiny a živými pohledy, vykreslením při šířkách 1100/1366/1700, exporty, Undo a obnovou zálohy. [Běhový protokol](audit-0.4.5-frozen.json), [snímek párovací plochy](audit-0.4.5-pairing.png).
- Porovnání sestaveného EXE se zdroji potvrdilo shodu všech 55 zahrnutých vlastních modulů a 8 datových souborů. [Protokol shody](audit-0.4.5-frozen-code.json).
- Vytvořen instalátor `dist/installer/KajovoKarty-Setup-0.4.5.exe`, 40 909 143 bajtů. [SHA-256 instalátoru](audit-0.4.5-installer-sha256.txt). Instalace na čistém Windows profilu nebyla ověřena; běžící provozní instalace nebyla nahrazena.

Reprodukční nástroje jsou součástí zdrojového projektu. Zdrojový manifest eviduje otisky vstupů a balicí nástroj ověřuje obsah výsledného ZIP proti MANIFEST.sha256.

## Optimalizace k samostatnému rozhodnutí

Naměřeno na tomto Windows stroji, tři vzorky na případ; hodnoty jsou mediány. [Syntetický protokol](audit-0.4.5-performance.json). Nejde o produkční zátěž ani o porovnání před/po optimalizaci.

- **Priorita 1 — SQL přehledy:** první stránka při 100 / 1000 / 5000 platbách přibližně 23 / 90 / 397 ms. Prověřit opakovanou tvorbu celé dočasné projekce, plán dotazu a invalidaci po revizi dat. Přínos: plynulejší filtry při velké databázi; riziko: zastaralý pohled, proto bez neověřené cache.
- **Priorita 2 — pokladní storna:** 100 / 500 / 1000 položek přibližně 4 / 86 / 366 ms. Párové porovnávání roste kvadraticky. Navržen index podle měny, absolutní částky, storno příznaku a data; nutné zachovat celou množinu kandidátů a nejednoznačnost. V auditu opravena odezva zrušení, nikoli změněn algoritmus.
- **Priorita 3 — součty:** vyrovnané komponenty 20 / 40 / 80 položek přibližně 0,6 / 2,7 / 13,2 ms. Jde o snadné případy; obtížné nevyrovnané kombinace mohou být výrazně dražší. Před optimalizací měřit také husté nejednoznačné komponenty a chování při limitech. Limity nezvyšovat naslepo.
- **Nižší priorita — přetažení:** načtení 50 řádků přibližně 20–23 ms v databázích až 5000 položek. Hromadné načtení grafu by snížilo počet SQL dotazů, současné měření však neukazuje naléhavý problém.
- **Údržba:** hlavní Qt okno spojuje mnoho odpovědností. Samostatný následný refaktoring řadiče návrhu, načítání pohledů a importního toku může zjednodušit testování. Neprovádět jej současně se změnou finančních pravidel.

## Meze a kompatibilita

Finanční importní identity, exportní schéma ani schválené párovací priority se tímto auditem nemění. Nový informační kód chyby je aditivní. Schéma zůstává 4. Opravené vydání 0.4.5 se nesmí zaměňovat s historickou chybnou značkou 0.5.0 v záznamu migrace; existující historické záznamy se nepřepisují.

Nový volitelný argument `--self-test-report` spouští izolované syntetické ověření. Standardní start nemění. Test neakceptuje provozní pracovní prostor a nepřepisuje existující report. Podrobnosti jsou v [indexu dokumentace](INDEX.md).

Zdrojový projekt zachovává původně dodané testovací přílohy včetně ucty.xls. Audit je nevydává za anonymizované podklady a zdrojový ZIP není určen k automatickému veřejnému publikování. Provozní databáze a místní pracovní logy jsou z balení vyloučené.

PyPI kontrola používá [verzované metadata](https://pypi.org/pypi/setuptools/83.0.0/json); původní vadu setuptools dokumentuje [upstream advisory](https://github.com/pypa/setuptools/security/advisories/GHSA-5rjg-fvgr-3xxf). Absence hlášení v databázi není zárukou bezpečnosti. Nativní Qt DLL, OS, podpis instalátoru a čistý Windows profil vyžadují samostatné posouzení. Windows Sandbox na tomto stroji nebyl nalezen; instalace přes běžně používanou aplikaci není součástí tohoto auditu.

Inno Setup 6.7.3 při sestavení zobrazil „Non-commercial use only“. Audit neověřoval zakoupenou licenci a nemění ji; režim pro komerční sestavování a distribuci je potřeba posoudit podle [informací výrobce](https://jrsoftware.org/isorder.php). Samotný banner zde není vydáván za právní závěr.

PyInstaller hlásil nenalezené krátké názvy pomocných mypyc modulů chardet a volitelné/platformní moduly. Příslušné chardet pipeline knihovny jsou ve výsledném balíčku přítomné pod skutečnými cestami; distribuční self-test prošel i exportem PDF. Nevyužívané volitelné funkce třetích stran tím nejsou všechny ověřené.
