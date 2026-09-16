> Historický dokument; aktuální pravidla a výsledky jsou v [SSOT](SSOT.md) a [auditu 0.4.5](AUDIT_0_4_5.md). Níže zachovaný obsah popisuje tehdejší stav.

# Forenzní audit KájovoKarty 0.4.1

## Rozsah a podklady

Audit zahrnuje importy, automatické párování, ruční zásahy a jejich ochranu, hlášení, logování, provozní historii, zdrojové důkazy a aktuálnost SSOT. Výchozí zdrojový commit: `0e90b59`. Provozní databáze byla otevřena nejprve pouze pro čtení a před opravami byla zálohována přes SQLite backup; obnovená kopie prošla kontrolou integrity a cizích klíčů.

Výchozí stav: 46 uložených vstupních souborů, 2 051 finančních položek, 762 pomocných vazeb VS, 56 dokončených importů, 3 historicky zrušené importy a 12 dokončených běhů automatiky. Aktivních ručních skupin bylo 45; včetně rozložené historie existuje 46 ručních skupin. Historické automatické dvojice: 540 Booking, 307 terminál a 1 bankovní storno.

Staré technické logy obsahují 8 876 událostí online API. Neobsahují podrobný průběh importů ani párování. Výsledky importů proto byly rekonstruovány z původních uložených bytů, výskytů řádků, finančních identit a auditní historie; chybějící historický DEBUG záznam nebyl domýšlen.

## Nálezy a opravy

| Nález | Dopad | Oprava / ověření |
|---|---|---|
| Terminál vybíral dvojice podle pořadí identifikátorů | Při více stejných částkách mohl vytvořit nedoložené spojení | Úplná množina kandidátů a oboustranná jednoznačnost; testy 1:2, 2:1, 2:2 |
| Terminál měl přednost před Bookingem | 93 historických terminálových dvojic mělo pokladní vazbu v Účtech | Odsouhlasená přednost Bookingu a zákaz náhradního terminálového/bankovního spojení |
| Důvod nejednoznačnosti chyběl na druhé straně | Položka s jediným sdíleným kandidátem hlásila chybějící protějšek | Vyhodnocení nejednoznačnosti celé kandidátní dvojice |
| Jiná měna se popisovala jako jiná částka | Zavádějící vysvětlení nespárování | Samostatné důvody chybějící platby, jiné měny a jiné částky |
| Oprava rozděleného `&amp;` znala jedinou firmu | Odmítnutí pokladního exportu kvůli jinému názvu se stejnou strukturou | Obecná oprava pouze tohoto strukturálního případu; ostatní sloupce nadále podléhají validaci |
| Opakované výskyty měly označení NEW | Historie řádků neodpovídala deduplikaci | Označení NEW/KNOWN podle skutečného zápisu a správné souhrny po souborech |
| Stav dokončení importu se zapisoval až po finančním commitu | Selhání druhého zápisu mohlo zkreslit výsledek | Stav COMPLETED se zapisuje ve stejné transakci jako finanční data |
| Neočekávaná chyba náhledu mohla zanechat rozpracovanou operaci | Nepravdivý stav RUNNING a neuklizený náhled | Evidence selhání a úklid dočasných podkladů |
| Selhání uložení souhrnu Bookingu mohlo skrýt dokončené importy | Uživatel nedostal pravdivý výsledek již potvrzených souborů | Zachování výsledků a samostatné upozornění na zápis souhrnu |
| Zrušení potvrzení se evidovalo jako chyba | Nerozlišené zastavení uživatelem a skutečné selhání | Stav CANCELLED pro zrušení; stará historie se nepřepisuje |
| Finanční audit označoval automatické vytvoření jako MANUAL | Zkreslení původu operace | Původ se přebírá z příslušného příkazu |
| Ruční párování četlo poznámku z dialogu v pracovním vlákně | Po zavření dialogu mohla operace selhat na zrušeném widgetu | Text se zachytí v GUI vlákně před spuštěním operace; skutečný Qt průchod znovu ověřen |
| Chyběl společný DEBUG záznam a český číselník | Nedostatečná dohledatelnost, technické a někdy nepřesné chyby | Denní strukturovaný log, očištěné výjimky, jednotný číselník v aplikaci a sestavách |
| SSOT obsahoval staré online a součtové požadavky | Nejednoznačné aktuální zadání | Nový SSOT 0.4.1 a výslovně nezávazný historický archiv |
| Balení zdrojů nevylučovalo `.tmp` | Do balíčku mohly vstoupit pracovní diagnostické podklady | Doplněné vyloučení pracovní složky |

## Rekonstrukce importů a oprava dat

Původ všech 2 051 finančních položek byl nalezen v uložených souborech. Jejich uložené obsahové otisky odpovídají obsahu. Zjištěných 225 odlišných výskytů se liší pouze jménem hosta; nejde o odlišnou platební částku nebo identitu. Původní finanční obsah zůstává beze změny.

Opakováním dvou prokazatelně dříve odmítnutých souborů na ověřené kopii přibylo 5 pokladních položek a 46 Booking plateb. Dalších 1 055 pokladních a 627 Booking položek bylo správně rozpoznáno jako již uložených. Nedošlo k jejich duplikaci. Nové přírůstky činí 1 550,00 CZK a 454,80 EUR v pokladně a 10 176,30 EUR u Bookingu.

Podle nově odsouhlasených pravidel bylo na kopii rozpojeno 104 nedoložených nebo nově nepřípustných automatických terminálových dvojic. Následně vzniklo 43 doložených Booking dvojic. Ruční skupiny, jejich členství a všechny původní finanční obsahy zůstaly shodné. Opakovaný běh vytvořil 0 dvojic a opakované posouzení nenašlo zbývající automatické dvojice k opravě.

Opravy používají běžné aplikační služby. Každý opravovaný import a každé rozpojení dostává dodatečný forenzní auditní záznam. Historické operace a původní důkazy se nepřepisují. Zákazy dříve stanovené uživatelem se zachovávají; technické rozpojení kvůli změně pravidla nevytváří nový zákaz, který by bránil správnému přepárování.

Po opravě má kopie 2 102 finančních položek. Kontrola všech řádkových výskytů dokončených importů a jejich návaznosti na zdroje nenašla chybu. Kontrola původu vazeb v Účtech rovněž nenašla chybu.

## Vazba SSOT na ověření

| Požadavek SSOT | Implementace | Ověřovací scénáře |
|---|---|---|
| Přesné částky, identity, měny | domain/core, infrastruktura parserů | test_domain, test_imports, test_booking_metadata |
| Jednotný import, kontrola souboru, atomický commit | application/imports | test_imports, test_forensic_regressions |
| Dávka Booking a pravdivý výsledek | application/booking_import, import_messages | test_booking_batch, test_import_feedback, test_gui |
| Účty a původ vazeb | application/accounts, accounts_parser | test_accounts, test_accounts_ui, kontrola provozních důkazů |
| Přednost Bookingu a zákaz náhradního spojení | application/matching | test_forensic_regressions |
| Jednoznačné dvojice, žádná automatická skupina | domain/matching, application/work | test_forensic_regressions, test_acceptance_traces |
| Průběh, zrušení, ruční zákazy, opakovaný běh | application/auto_run, matching, UI | test_auto_progress, test_auto_ui, test_auto_forensic, opakování na kopii |
| Ruční párování a Undo/Redo | application/work, pairing | test_work, test_pairing_drag, test_pairing_ui, test_group_amount |
| České chyby a bezpečný DEBUG log | domain/errors, technical_log, pracovní úlohy | test_forensic_regressions, test_completion |
| Export, záloha a obnova | application/reports, backup, infrastructure/export | test_reports_backup, test_completion, obnovení provozní zálohy |

## Stav závěrečného ověření

- **221 testů prošlo**, 0 chyb, 0 selhání; úplná sada trvala 256,53 s. Výsledek je v `windows-test-results.xml`.
- Kontrola nedefinovaných jmen a chybných vazeb proměnných přes Ruff i kontrola změn přes Git prošly.
- Qt průchody ověřily pokladnu XLS, terminál CSV/XLS/XLSX, Booking CSV, Účty XLS, potvrzování importu, ruční párování, spuštění automatiky, zrušení a historii. Vykreslený přehled Účtů byl vizuálně zkontrolován.
- PyInstaller vytvořil samostatnou aplikaci 0.4.1. Ta byla spuštěna v odděleném pracovním prostoru, vytvořila hlavní okno, zapsala DEBUG události bez chyb a po běžném zavření skončila kódem 0. Test nejprve čekal na pomocné okno Qt namísto hlavního okna; po opravě čekání v testovacím ovladači proběhlo normální ukončení úspěšně.
- Vytvořen instalátor `dist/installer/KajovoKarty-Setup-0.4.1.exe`; SHA-256: `11d5d99a147a84037fae4bf95085339722c97d733e63b1f0c1c08bf1c1bd0c31`. Bylo doplněno hledání kompilátoru Inno Setup také v uživatelské instalaci. Instalátor byl sestaven, nikoli nainstalován přes existující aplikaci.
- Opravy byly aplikovány také na **provozní databázi**, po čerstvé záloze `forensic-pre-apply-20260915-202553.sqlite` a ověření její obnovené kopie. Přibylo 51 plateb, bylo rozpojeno 104 automatických dvojic a vytvořeno 43 Booking dvojic.
- Závěrečné porovnání potvrdilo nezměněný obsah všech 2 051 původních finančních položek a všech 46 ručních skupin včetně historické rozložené skupiny. Finanční obsah i složení automatických dvojic v provozní databázi přesně odpovídají ověřené kopii. Kontrola cizích klíčů, všech importních řádků i původu vazeb Účtů nehlásí chybu.
- Podrobné pracovní protokoly a obnovené kopie jsou místně v `.tmp/forensic-20260915`; nepatří do zdrojového balíčku. Zálohy provozních dat jsou v jejich původní datové složce `backups`.

Ověřovací počítač používá Windows 10 build 19045 a Python 3.12.9. Samostatný průchod na jiném počítači s Windows 11 nebyl proveden. Stejně tak sestavení a test spuštění nejsou tvrzením o ověření instalátoru na všech čistých počítačích.

## Meze důkazů

Nelze zpětně prokázat každý krok tehdejšího běhu bez tehdejšího DEBUG záznamu. Lze ověřit uložené vstupy, jejich importované řádky, neměnné finanční údaje, existující důkazy a výsledek opakování aktuálním kódem. Nesouhlas patičky pokladního exportu zůstává doloženým varováním zdrojového exportu; částky se podle patičky svévolně neopravují. Historické online API není součástí současné funkce a jeho síťový provoz nebyl obnovován.
