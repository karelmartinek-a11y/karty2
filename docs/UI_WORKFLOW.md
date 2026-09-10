# Párování a sloupcové filtry — verze 0.3.0

## Výchozí stav a návrh

Cílový repozitář je `karelmartinek-a11y/karty2`, výchozí commit `a242d0f9345f93edcfa32403dc1130fd6a85d43e`. Repozitář s přesným názvem KajovoKarty2 nebyl nalezen; tento repozitář obsahuje KájovoKarty 0.2.0 a Windows spouštěč.

Původní ruční postup vyžadoval pracovní výběr, další dialog a při opravě členů rozložení celé skupiny. Drag-and-drop nepokrýval přímé vyjmutí či přesun člena. Tabulky neměly jednotné filtry jednotlivých sloupců. Hlavní finanční tabulka je stránkovaná, takže samotný Qt proxy filtr by chybně filtroval jen načtených 500 řádků.

Reference `karelmartinek-a11y/kajovovydaje2`, strom `deb8d73fe8a4d644d33177d70257888c37753eaf`, soubor `app/ui/models.py` (blob `0fc02c0659bd6f6f4faac016462ddc56d129959d`) byla pouze přečtena. Převzat je princip nabídky záhlaví, hledání hodnot a zaškrtávacích voleb. Cílová implementace navíc rozlišuje zrušený filtr od prázdného výběru a filtruje před stránkováním. V referenčním repozitáři nebyla provedena žádná změna.

## Ovládání párování

1. **Automaticky spárovat vše** výslovně spustí původní algoritmy A–D nad celou databází. Výsledek uvádí počet vytvořených skupin, kola a omezené komponenty. Import, filtr ani přetažení automatiku samy nespouštějí.
2. **Platbu přetáhnout na platbu:** vznikne skupina. **Na skupinu:** přidání či přesun členů do ní. Cíl a předpokládaný rozdíl se ukazují při přetahování.
3. **Párovací plocha** vpravo ukazuje vybraný objekt, měnu, stav, rozdíl a přímé členy. Přetažení do horní zóny přidá platby do otevřeného detailu. Dvojklik na člena otevře jeho podrobnosti, tlačítko Nadřazená skupina umožní návrat.
4. **Vyjmout označené** nebo přetažení člena do zóny **Rozpárovat / vrátit jednotlivě** jej uvolní. Člena lze přetáhnout také rovnou do jiné skupiny. **Rozpárovat celou skupinu** uvolní její přímé členy a zachová podskupiny.
5. **Nová skupina** přijme alespoň dvě označené platby, i členy různých skupin. Prázdné či jednočlenné původní skupiny se automaticky uklidí; zbývající člen převezme místo zrušené skupiny.
6. Každý přesun je **jeden příkaz Zpět/Znovu**. Pokladna přispívá kladně svou signed částkou, terminál a Booking opačně. Vyřízeno znamená přesný nulový rozdíl v jedné měně. Ruční úprava členů může dříve vyřízenou skupinu znovu otevřít.

Tlačítka zůstávají alternativou k přetahování. Pro velký pracovní výběr lze dál použít Ctrl+M s náhledem. Drag výběru obsahujícího nenačtené stránky se výslovně odmítne s návodem na hromadné seskupení; nikdy se potichu nepřenese pouze načtená část.

## Pravidla správnosti

`PairingService.move` ověřuje aktivitu, měnu, revize členů i jejich rodičů, duplicity, cykly a vlastní cíl. Skupiny se nerozplošťují a každé dítě má nejvýše jednoho aktivního rodiče. Všechny přesuny, úklid rodičů, historie, audit a suppression proběhnou v jedné SQLite transakci. Selhání nezanechá částečný přesun. Finanční zdroje a jejich částky jsou neměnné.

Před ruční změnou automatické skupiny se archivuje původní strom a důkaz, změněná aktivní skupina přejde na MANUAL a původní automatická shoda se potlačí. Undo obnoví také metodu a důkaz. **Znovu povolit původní automatické shody** pouze zruší příslušné potlačení; nové párování se spustí až výslovným tlačítkem.

## Filtry a řazení

Každý sloupec má stále viditelnou šipku. Nabídka obsahuje vzestupné/sestupné řazení, zrušení řazení, hledání hodnot, zaškrtávací seznam, výběr/odebrání nalezených hodnot, Použít a zrušení filtrů. Kliknutí na název cykluje vzestupně → sestupně → původní pořadí. Shift přidává další klíč v tabulkách; strom řadí sourozence jedním klíčem.

Sloupce se kombinují AND, vybrané hodnoty jednoho sloupce OR. Prázdný zaškrtávací výběr vrací nula řádků; Zrušit filtr vrací všechny hodnoty. Chybějící dříve vybraná hodnota se neztratí. Částky se řadí numericky, ID textově včetně počátečních nul. Prázdné buňky mají samostatnou volbu a při řazení jsou na konci.

Finanční filtry, nabídky hodnot, počty a stránkování používají SQL nad celým výsledkem. Ostatní přehledy filtrují úplný katalog před stránkováním. Nabídka hodnot respektuje ostatní sloupce a vynechává vlastní podmínku. Delší seznam hodnot se plní po dávkách bez blokujícího jednorázového vytvoření všech widgetů. Filtry jsou oddělené podle pohledu a Uložit filtr je uloží spolu s řazením. Filtrování nemění pracovní výběr ani členství plateb.

| Zobrazení | Pokrytí |
|---|---|
| Nevyřízené, Vyřízené, Vyhledávání | Všech 12 sloupců; SQL, pro kombinovanou historii společná projekce |
| Importy a BetterHotel | Všechny sloupce souborů a běhů |
| Pomocná data | Všechny sloupce aktuálního i explicitně historického pohledu |
| Sestavy | Sloupce katalogu; jeho filtry se nepřenášejí na datové sestavy |
| Audit | Všechny sloupce událostí |
| Nastavení / operace | Všechny sloupce přehledu operací |
| Možné protějšky | Všechny sloupce výsledků; výběr po řazení odkazuje na správný objekt |
| Párovací plocha | Všech šest sloupců přímých členů |
| Strom důkazu | Všechny čtyři sloupce; předci shod zůstávají jako kontext |

## Implementace a ověření

Nové moduly: `application/pairing.py`, `domain/columns.py`, `ui/column_filters.py`, `ui/pairing_panel.py`, `ui/evidence_tree.py`. Upraveny jsou hlavní UI, tabulkový model a drag přenos, SQL dotazy, rozsahy sestav a obnova metody/důkazu při Undo. Verze produktu je 0.3.0; databázové schéma zůstává 2. SSOT oddíly 9.4, 11.6 a související akce byly aktualizovány podle nového požadavku. Algoritmy A–D, exportní schéma a původní přílohy se nemění.

Nové testy pokrývají vytváření skupin, úpravu uzavřené skupiny, přesun mezi rodiči, vyjmutí a úklid skupin, podskupiny, stale revize, odmítnutí vlastního cíle, rollback při chybě, neměnnost finančních bajtů, archivaci automatického důkazu a Undo/Redo. Qt test používá skutečné události drop a nabídku záhlaví; ověřuje prázdný výběr hodnot, zachování výběru při řazení a všechny sloupce všech osmi hlavních pohledů. SQL test filtruje i řádky za první stránkou v datasetu 1 055 plateb.

Opravené chyby nalezené během testů: Ctrl+A vybíral pouze stránku, focus po drop bránil finančnímu Undo, nativní Qt styl zakrýval kreslené šipky, opakované obnovování šířek zbytečně přepočítávalo rozložení a obnova velkého výběru opakovaně vyhodnocovala akce pro každý řádek. Při zavření okna se nyní zastaví časovače a odpojí globální sledování focusu. Filtry sestav jsou nyní oddělené podle schématu pohledu. Snímek `ui-pairing.png` je zachycený běžící program se syntetickými daty.

Finální společný běh: **120 testů prošlo za 118,55 s; 0 chyb, 0 selhání, 0 skip**. Strojový záznam: `ui-regression-results.xml`. Ruff F nad src/tools/tests i `git diff --check` prošly. Jeden předchozí běh skončil časovým limitem GUI scénáře při souběžném ověřování; následný samostatný GUI běh a celý společný běh prošly. Příkazy pro opakování v připraveném vývojovém prostředí:

```bash
QT_QPA_PLATFORM=offscreen python -m pytest -q --junitxml=docs/ui-regression-results.xml
ruff check src tools tests --select F
python tools/build_manifest.py
python tools/package_repo.py
```

Ověření používá Linux, CPython 3.12.14 a PySide6 6.8.3 z hashově uzamčených závislostí. HTTP scénáře jsou lokální kontraktní testy. Windows instalátor, nativní přetažení mezi okny Windows, DPI a živé BetterHotel API v této změně ověřeny nebyly. Starší zátěžový protokol 0.2.0 není novým měřením výkonu sloupcových filtrů. Úplná historická akceptační matice SSOT tím není prohlášena za uzavřenou.
