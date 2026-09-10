> Historický protokol verze 0.2.0. Aktuální změny a nové ověření 0.3.0: [UI_WORKFLOW.md](UI_WORKFLOW.md).

# Ověřovací protokol — KájovoKarty 0.2.0

## Stav

**Lokální testy PASS; úplná akceptace SSOT NOT_VERIFIED.** Implementace byla rozšířena proti 0.1.0. Níže se uvádějí skutečné výsledky, ne domnělá konformance všech požadavků. Zdrojový ZIP není Windows instalátor.

## Automatické ověření

Linux, CPython 3.12.14, připnuté závislosti původního prostředí. Finální běh: **91 testovacích případů prošlo za 31.69 s**, bez skip/xfail; strojový výstup test-results.xml. Ruff F nad src, tools a tests prošel. Přesné příkazy obsahuje ../DELIVERY_SUMMARY.md.

| Oblast | Provedené scénáře |
|---|---|
| Import | Pět skutečných příloh B; roční/týdenní překryv v obou pořadích; deduplikace; všechny soubory jedné operace; chybná smíšená sada; změna souboru po náhledu; opakování z BLOB; SQL neměnnost |
| Peníze a skupiny | Celočíselné částky, znaménka, limit, DST, homogenní měna, vnoření, rozložení, stale revision, Undo/Redo, historické listy, rollback při selhání membership |
| Automatika | Kandidátní grafy, negativní kombinace a limit, terminálové storno, A.7 pevný bod, A.8 Undo a suppression, silná oboustranná nejednoznačnost C |
| HTTP | GET/prefix/dvě tokenové hlavičky/expand, 401/403/302/204, deadline, burst a refill, Retry-After, cursor cyklus, semantický FAIL, prázdné grafy |
| Helper graf | Konfliktní projekce bez publikace, checkpoint a resume, raw/RELATION_EDGE provenance, identita a ochrany snapshotů, A→B→A kontext, A.9 přesunutý kořen a neaktivní větev, identický DETAIL a revize, rodičovská měna, cílené kauce, override a kompenzace |
| Sestavy | CSV ZIP/XLSX/PDF, textové identifikátory, úplná prázdná schémata, výběr mimo filtr, historický helper uzávěr, zrušení/selhání rename zachová původní export |
| Provoz | Záloha/obnova a odmítnutí poškozeného ZIPu, ověřená záloha migrace v1, přesun se zachováním originálu, obnova poškozené DB, atomické nastavení/proxy, sanitizace technických logů |
| Qt | Import přes skutečný dialog, výběr/skupina/hledání/Undo, inline validace nastavení a vzhled, Ctrl+A přes 1 055 výsledků při stránce 500, přednost textového Undo |

HTTP důkazy těchto testů mají třídu **LOCAL_CONTRACT_TEST**. Nejsou zachyceným provozem BetterHotel. Testování DPAPI používá lokální náhradu; nepředstírá šifrování Windows.

| Vstup | Finanční řádky | CZK signed minor | EUR signed minor |
|---|---:|---:|---:|
| cashbook_year.xls | 1 055 | 125 987 613 | 14 127 070 |
| cashbook_week.xls | 9 | 520 000 | 108 374 |
| terminal.xlsx | 56 | 21 672 903 | 125 510 |
| booking_a.csv | 21 | 0 | 395 564 |
| booking_b.csv | 25 | 0 | 451 069 |

## Zátěž

Skutečný lokální syntetický dataset: 100 000 finančních listů a 20 000 skupin, z toho jedna s 1 000 listy. Skupiny jsou zátěžová fixture vytvořená SQL transakcí; import, dotazy, výběr a detail jsou měřeny přes produkční služby. p95 je 19. hodnota z 20 seřazených vzorků.

| Metrika | Naměřeno |
|---|---:|
| Filtrovaná první stránka, p95 | 0,951 s |
| Změna výběru, p95 | 0,00162 s |
| Detail skupiny s 1 000 listy | 0,0210 s |
| Import 100 000 řádků | 26,876 s |
| První stránka bez filtru | 0,813 s |
| Maximální RSS procesu | 568 848 KiB |

Úplné vzorky a prostředí jsou v load-probe.json. Nejde o měření na referenčním Windows stroji a nepokrývá všechny operace kapitoly 18. Sestavy i část matching/evidence cest stále materializují širší graf do paměti; p95 přehledu není zárukou jejich maximální paměti či času.

## Zbývající ověření a hranice dodávky

1. **Windows:** sestavit a spustit výsledný instalátor na čistém Windows profilu. Ověřit DPAPI, proxy v reálné síti, IPC, restart po přesunu, DPI 100–200 %, upgrade/odinstalaci a zachování dat. tools/build_windows.ps1 a GitHub Actions jsou předpisy, ne důkaz provedení. V tomto ZIPu není sestavený EXE.
2. **Živé API:** zadat provozní dvojici tokenů v UI a provést FULL/kompatibilitu všech 12 šablon. Bez přístupu nebyla získána LIVE_OBSERVATION, žádný živý endpoint není prohlášen za PASSED. Ověřit reálné limity, nestandardní odpovědi a proxy.
3. **Úplná akceptační matice 17–18:** 91 testů není úplným přiřazením každého acceptance ID. Dosud není systematicky proveden kill procesu/power-loss/disk-full na každé hranici transakce, publikace, přesunu a obnovy; neproběhla všechna souběhová a migrační historická uspořádání ani každý průchod GUI přes všechny alternativní vstupy.
4. **UI a sestavy:** základní widgetové průchody a servisní exportní kontrakty byly ověřeny. Kompletní vizuální akceptace každé sestavy, klávesová přístupnost všech modalit nejsou uzavřeny. Smíšený pracovní výběr se v exportním dialogu výslovně rozděluje na dvě samostatné sestavy s příponami _unresolved a _resolved; servisní test ověřuje, že se žádný vybraný kořen neztratí.

Bez těchto kroků nelze vydat konečný akceptační verdikt ani prohlásit úplné splnění SSOT. Neověřené scénáře nejsou v testovacím protokolu nahrazeny úspěšnými zástupnými testy.

## XLS footer

Původní XLS obsahují BIFF FORMULA v souhrnném footeru (roční řádek 1686, týdenní řádek 21; Příjem/Výdaj). Parser čte uložené souhrnné hodnoty jako technický footer dle 5.3, nic nevykonává. Vzorce v běžných finančních řádcích odmítá. Finanční částky se tím nemění.
