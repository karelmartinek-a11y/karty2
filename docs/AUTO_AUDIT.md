# Forenzní revize automatického párování — 0.3.1

Výchozí stav: `karelmartinek-a11y/karty2`, commit `491dbd46dd8b14cc126fa48ed21f1553fa285673`, navazující na PR #1. Rozsah: automatika A → B → C_STRONG → C_WEAK → D, její dokladové důkazy, výhradní běh, zápis skupin, zrušení/chyba, výsledky a vstup z UI. Reference KajovoVydaje2 se v této revizi nemění. Databázové schéma zůstává 2; SSOT pravidla automatického párování se nerozvolňují.

## Závěr a ovládání

Automatika se spouští pouze výslovným tlačítkem **Automaticky spárovat vše**. Start, import, vyhledávání, filtr, ruční párování, synchronizace ani otevření výsledku ji nespouštějí. Spouští se nad celou databází, bez ohledu na zobrazený filtr. Během běhu je tlačítko zakázané; druhý klik nevytvoří další běh.

Každá platná jednoznačná skupina se uloží samostatnou atomickou transakcí. Běh pokračuje do ustálení; žádné potvrzování jednotlivých shod. Nejednoznačnost, chybějící důkaz, odlišná měna či nenulový rozdíl nikdy nejsou důvodem ke zmírnění pravidel. Úspěšný běh neznamená, že lze automaticky vyřídit každou položku.

Po dokončení, zrušení i zachytitelné chybě se otevře nezablokující výsledek. Rozlišuje analyzované zdrojové listy, nově vyřízené listy, vytvořené skupiny a zbývající nevyřízené řádky; uvádí CZK a EUR samostatně, počty podle pravidel a důvody zbývajících samostatných položek. Výsledek je trvale uložen v operaci a znovu dostupný přes **Nastavení → operace AUTO_MATCH → detail**. Zrušení zachová již zapsané skupiny a označí výsledek jako neustálený. Nový běh vyžaduje další stisk tlačítka.

## Doložené nálezy a opravy

| ID | Nález ve výchozím kódu | Oprava a ověření |
|---|---|---|
| AUTO-01 | Příprava nastavení/helperu i odmítnutí REFRESHING byly mimo obsluhu chyby; po startu mohl zůstat stav RUNNING. `MatchingService._run`. | `AutoRun.execute` spravuje celý zahájený běh. Testy přípravné výjimky a REFRESHING původně selhaly, nyní končí FAILED se sanitizovanou chybou. |
| AUTO-02 | Zrušení se zapisovalo jako FAILED a bez výsledku již dokončených skupin. | Samostatný CANCELLED, `reached_fixed_point=false`, počty dokončených skupin/listů a uložené `recovery_json`. Test zruší po první ze dvou skupin, další výslovný běh dokončí druhou, následující vytvoří nulu. |
| AUTO-03 | Neočekávané výjimky po částečném úspěchu neuzavíraly běh bezpečně. | Zachycení běžných výjimek, bezpečný popis bez zdrojového obsahu, částečný výsledek. Test selhání druhého zápisu zachová pouze první skupinu. |
| AUTO-04 | Samotný `WorkService.create_group` kontroloval členství a revize, nikoli úplný snímek automatiky. | Kontrola uvnitř finanční transakce: doménové hodiny, helper stav, aktuální kontext, publikovaná generace, matching nastavení, suppression a zdrojové hashe. Zrušení se kontroluje i těsně před zápisem. Testy mění podklady až na poslední hranici volání. |
| AUTO-05 | Každá instance `Database` měla vlastní logický zámek i pro stejný soubor. | Zámek je společný podle normalizované skutečné cesty. Vláknový test dokládá blokování finanční mutace druhou instancí po dobu běhu. Čtecí spojení nejsou zamknuta na celý běh. |
| AUTO-06 | `_helper` zahazoval neaktivní/neúplné vztahy ještě před rozhodnutím, zda je absence Booking řetězce skutečně prokázaná. To mohlo otevřít C_WEAK. | Aktuální projekce zachovává i informaci o nepoužitelném vztahu; ten vede na UNKNOWN. Integrační test nejprve synchronizuje rezervaci, pak ji odstraní z úplného seznamu a ověří, že nevznikne slabé bankovní párování. |
| AUTO-07 | Kontrolovala se měna invoice, nikoli explicitní odlišná měna navázané rezervace. | Měnový rozpor řetězec zablokuje. Cílený test odmítne B při CZK rezervaci a EUR finančních listech. |
| AUTO-08 | Normalizace přes `header` slučovala vnitřní mezery identifikátorů nad rámec přesné NFKC + casefold shody. | Kódy se porovnávají přesně podle smluvené normalizace. Test dvou různých kódů s různým počtem mezer nesmí vytvořit B. |
| AUTO-09 | B prohledával i komponenty bez jedné ze dvou nutných stran; samotný velký Booking seznam mohl vyvolat limit a falešně blokovat D. | Chybějící strana dokazuje nemožnost B bez kombinatorického hledání. Test 42 Booking položek bezpečně provede jediný jednoznačný protizápis. Pro skutečnou oboustrannou B komponentu zůstává úplný limit závazný a při překročení blokuje i D. |
| AUTO-10 | Pole helper důkazů bylo řazeno podle náhodných UUID; D zahrnovalo v důkazu absence také jiné měny. | Nové otisky používají kanonické pořadí zdrojů a relevantní měnu. Kontrola současně respektuje starší otisk 0.3.0, aby upgrade neobnovil už zakázané spojení. Test úmyslně obrací pořadí UUID proti pořadí zdrojů a ověřuje původní suppression. |
| AUTO-11 | Důvody nejednoznačnosti nepočítaly kandidáty A; Booking při neověřených helperech mohl uvádět pouze chybějící protějšek. | Závěrečné důvody zahrnují A a rozlišují neověřená pomocná data. Skutečné kódy automatiky mají české popisy v tabulkách i souhrnu. |
| AUTO-12 | Chyběl trvalý podrobný výsledek po měnách a průběžný heartbeat. UI při chybě nemuselo obnovit již změněná data. | Heartbeat, počty a terminální stav jsou u operace; úspěch i přerušení obnoví UI. Qt test skutečným tlačítkem potvrzuje celý rozsah navzdory filtru vracejícímu nula řádků, zákaz dvojkliku a zobrazení částečného výsledku. |
| AUTO-13 | Opakované hledání invoice a vztahů pro každý cashbook a každou podfázi zbytečně procházelo celý helper graf. | Index přesných kódů, index vazeb a cache řetězců nad neměnným snímkem běhu. Referenční enumerace kombinací a její logický čítač se nemění. |
| WIN-01 | Předchozí skutečný Windows běh selhal na implicitním systémovém kódování SSOT a nezavřených kopírovacích SQLite spojeních při migraci/přesunu. | Explicitní UTF‑8 pro textové podklady a bootstrap; `closing` u dočasných SQLite kopií. Linux testy obou cest znovu prošly. Další výsledek Windows CI je uveden níže podle skutečného stavu. |

## Zachovaná pravidla a testy

A vyžaduje správnou SALE/REVERSAL dvojici, terminal/SEQ, maskovanou kartu a autorizaci, přesně opačnou částku, správnou chronologii a sedmidenní hranici. Samostatný REFUND se neodhaduje podle podobnosti. Existující importní/regresní testy A a jeho suppression zůstávají zapojené.

B je ověřeno na 1:1, 1:N, N:1, N:N a záporných částkách. Dvě stejně možné shody zůstávají nevyřízené; rozdíl jednoho centu se nepřijme. Při limitu se zahodí celá neúplně prohledaná komponenta. C_STRONG stále vyžaduje stupeň 1 na obou stranách; nejednoznačná silná hrana se neobchází C_WEAK. D vyžaduje prokázanou absenci B, READY a jednoznačný opačný pár. Ruční skupiny ani jejich potomci nejsou vstupy automatiky.

Nové testy: `tests/test_auto_forensic.py` (27 případů) a `tests/test_auto_ui.py` (2 případy). Původní tři reprodukce chyb lifecycle/cancel skutečně selhaly před opravou. Celá lokální sada poté: **149 PASS, 0 fail, 0 error, 0 skip, 145,03 s** (`auto-regression-results.xml`). Po následné opravě Windows uzavírání spojení a UTF‑8 znovu prošly cílené testy migrace a přesunu. Prošly Ruff F a `git diff --check`.

```bash
QT_QPA_PLATFORM=offscreen python -m pytest -q --junitxml=docs/auto-regression-results.xml
ruff check src tools tests --select F
python tools/build_manifest.py
python tools/package_repo.py
```

Ověřeno lokálně na Linuxu, CPython 3.12.14, PySide6 6.8.3; helper testy používají lokální kontraktní HTTP data, nikoli živý BetterHotel. Výsledky nenahrazují provozní akceptaci živého hotelového API. Při selhání disku, které znemožní i zápis terminálního stavu, aplikace nehlásí úspěch; zbytek RUNNING označí existující obnova při příštím startu jako INTERRUPTED. Oprava nemění finanční částky, ruční členství mimo explicitní operace ani obsah původních fixtures.

Předchozí Windows CI 0.3.0: běh `34507136528` skončil 3 fail / 19 error (kódování, otevřené kopie databáze a timeout GUI). Nebyl vydáván za úspěšný instalátor. Stav CI verze 0.3.1 bude ověřen po publikaci tohoto commitu.
