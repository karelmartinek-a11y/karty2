# KájovoKarty — SSOT 0.4.5

Závazná specifikace aktuální aplikace, sjednocená podle schválených změn při auditu 0.4.5. Tento dokument nahrazuje starší zadání. Původní API kontrakty a vložené vzorové soubory zůstávají v [historickém archivu](SSOT_0_3_ARCHIVE.md); archiv není zadáním současné funkčnosti. Důkazy a meze ověření: [audit 0.4.5](AUDIT_0_4_5.md).

## 1. Účel a pojmy

Lokální česká desktopová aplikace Windows / Python 3.12 / PySide6 porovnává karetní pokladnu, terminál a Booking.com. Používá CZK a EUR, nepřevádí měny, neprovádí platby a nevyžaduje online API ani tokeny.

- **Párování dvojice** znamená jednoznačné spojení 1:1, automatické nebo ruční.
- **Párování ve skupinách** znamená 1:N, N:1 nebo N:N. Automatika smí vytvářet doložené vyrovnané součtové skupiny. Aktivní skupiny obsahují přímo zdrojové platby, nikoli podskupiny.
- Pokladna (`CASHBOOK_CARD`) představuje očekávaný karetní příjem nebo výdaj.
- Terminál (`BANK_CARD`) představuje skutečnou karetní transakci, prodej, vratku či storno.
- Booking (`BOOKING`) představuje jednotlivou platbu nebo odečet z výplaty.
- Účty (`ACCOUNTS`) představují pomocnou vazbu VS → rezervace BetterHotel → Original ID Bookingu; nikdy finanční platbu.

Vnitřní tabulka `reconciliation_group` a pole `created_groups` počítají skupiny včetně dvojic; počet skupin není počet jejich členů.

## 2. Finanční a datové invarianty

Částky jsou celá čísla v nejmenší měnové jednotce, se znaménkem. Výpočty nepoužívají binární desetinná čísla a nezaokrouhlují rozdíl k nule. Příspěvek pokladny je její částka, příspěvek terminálu a Bookingu opačný. Vyřízené spojení má přesně nulový rozdíl v jedné měně.

Původní finanční obsah, vstupní soubory, historie skupin a audit jsou neměnné. Identický opakovaný import nevytváří další finanční položku. Konflikt platebních údajů stejné identity odmítá celý právě zpracovávaný soubor. Opravy se dokládají novým importem nebo zaznamenanou operací, nikoli přepisem historie.

Položka může mít nejvýše jedno aktivní nadřazené spojení. Zakázány jsou cykly, smíšené měny, opakované členství a aktivní skupiny s méně než dvěma členy. Potvrzení ověřuje aktuální verze položek a databázové invarianty. Aktualizace zachovává ruční spojení, poznámky a zákazy automatiky.

## 3. Importy

### Společná cesta

Výběr druhu a souborů → průběhové okno → načtení a uchování původních bytů → kontrola → atomické uložení každého souboru → výsledek, historie a tlačítko Hotovo. Import ani změna filtrů nespouštějí párování.

Podporovány jsou pokladna XLS, terminál CSV/XLS/XLSX, Booking CSV a Účty XLS. Formát, hlavičky, datové typy a povinné údaje se kontrolují podle druhu. Nejasný list volí uživatel. Ukládání znovu ověřuje uložený podklad, změnu externího souboru a duplicity vůči aktuálním datům.

Každý řádek má vysvětlitelný výsledek: nově uložen, již známý, záměrně vynechán, odmítnut nebo nezpracován. Prázdné a souhrnné řádky nejsou platby. Počty vycházejí ze skutečných zápisů, nikoli pouze z náhledu. Pokud soubor nelze přečíst, počet je neznámý, nikoli vymyšlená nula.

Soubor s chybou nezanechá částečný finanční zápis. Úspěšný zápis a stav dokončeného importu se potvrzují společně. Zrušení uživatelem je CANCELLED, chyba FAILED, přerušený proces INTERRUPTED. Historické nepřesné stavy se vysvětlují doplňujícím auditním záznamem.

### Pokladna

Hlavička: Vystaveno, Pohyb, Číslo, Označení, Klient, Příjem, Výdaj, Měna, Forma úhrady, Variabilní symbol, Vystavil. Finanční položky vznikají jen z karetních pohybů. Hotovost a převod jsou doložené vynechané řádky. Číslo dokladu a VS jsou samostatné údaje a nemusejí být shodné.

Přesný případ rozděleného `&amp;` v názvu klienta lze opravit spojením dvou sousedních buněk, pouze pokud následně odpovídají všechny ostatní sloupce, částky, měna, forma úhrady a VS. Oprava nesmí záviset na názvu konkrétní firmy. Jiný přesah je chyba. Nesouhlas souhrnu pokladního exportu je varování; autoritou jsou jednotlivé pohyby, nikoli přizpůsobení částek patičce.

### Terminál

Čtou se údaje transakce, terminál/POS, časy, částka, cashback, spropitné, měna, ARN, DCC, maskované označení karty, autorizace, VS/VS2, SEQ a údaje obchodního místa podle úplné hlavičky BANK_HEADERS v parseru. Identita je odvozena z terminálu, SEQ a třídy události; prodej a storno mají různé identity. Technické řádky nejsou finanční platby. Souhrny počtů a částek musejí odpovídat řádkům, jinak se import odmítne.

### Booking

Podporovány jsou české a anglické hlavičky BOOK_CZ a BOOK_HEADERS v parseru. Identitu tvoří výplata, rezervace, měna, datum výplaty a druh položky. Konflikt platebních údajů zahrnuje také částku a platební stav. Jméno hosta a údaje pobytu nejsou důvodem konfliktu platební identity; první uložený obsah zůstává zachován a nový výskyt má vlastní původní soubor.

Neuhrazené a nulové platby jsou vysvětlené vynechané řádky. Nepřičítá se provize ani nedopočítává cena pobytu. Více CSV se zpracovává postupně v pořadí výběru, každý samostatně. Chyba jednoho neruší dokončené soubory, zrušení zastaví další. Dialog a historie mají shodné výsledky. Viz [postup importu](BOOKING_IMPORT.md).

### Účty

XLS musí obsahovat jednou hlavičky Variabilní symbol, Číslo rezervace a Original ID; pořadí je volné. Ostatní sloupce se nevytěžují. Odstraňují se okolní mezery, textové počáteční nuly zůstávají. Neúplné řádky se vynechají s číslem řádku a vysvětlením.

První přijaté Original ID pro rezervaci BetterHotelu platí trvale. Stejnou dvojici rezervací lze doplnit dalším VS. Přesná duplicita je známá vazba. Odlišné Original ID pro známou rezervaci se vynechá včetně nového VS a zobrazí jako konflikt. První přijetí určuje pořadí souborů a řádků. Vazba uchovává soubor, import, list a řádek. Výsledky jednotlivých řádků jsou také v auditu.

## 4. Automatické párování

Spouští se výslovným tlačítkem nad všemi volnými aktivními nenulovými položkami, nezávisle na filtrech obrazovky. Souběžné spuštění je blokované. Každé kolo dodržuje pořadí:

1. Pokladní storno: dva pokladní záznamy stejné měny, nenulové přesně opačné částky, právě jeden označený jako storno, nejvýše dva kalendářní dny od sebe. Nejednoznačnost se neřeší výběrem podle pořadí.
2. Jednoznačný prodej a storno stejného terminálu/SEQ s opačnou částkou a stejnou měnou; storno není před prodejem a následuje nejvýše do 7 dní. Musejí souhlasit také vyplněné maskované označení karty a autorizační kód.
3. **Booking přes Účty:** VS pokladny určí právě jednu pomocnou rezervaci. Její Original ID odpovídá rezervaci Booking platby. Částka včetně znaménka i měna jsou přesně shodné; datum odpovídá nastavenému oknu pracovních dnů. Dvojice je jednoznačná na obou stranách.
4. Nejdříve ve stejný den, poté v celém pracovním okně: Booking/pokladna jednoznačné dvojice a vyrovnané součty, následně terminál/pokladna jednoznačné dvojice a vyrovnané součty. Každý krok používá aktuální zbývající volné platby. Rozporné vyplněné VS terminálu a pokladny vylučují shodu i uvnitř součtové skupiny.

Pomocná vazba Účtů slouží pouze pro párování Booking → pokladna a sama neblokuje terminál → pokladna. U Booking fallbacku se pokladní položka s existující pomocnou vazbou nepoužije proti jiné rezervaci. Booking datum je check-out, pokladní datum vystavení a terminálové datum transakce. Výchozí tolerance je 2 pracovní dny bez víkendů a českých svátků, symetricky mezi nejčasnějším a nejpozdnějším datem celé skupiny. Souvislý řetězec sousedních dat nesmí obejít celkový limit.

Součty se hledají odděleně podle měny a znaménka, mezi pokladnou a jedním druhým zdrojem. Celá vyrovnaná komponenta může tvořit jednu skupinu, například dvě stejné terminálové a dvě stejné pokladní platby. Nevyrovnané nebo nejednoznačné překryvy zůstávají ruční. Platí limity velikosti komponenty, kombinace a počtu stavů; neúplně prohledaná oblast se nesmí svévolně spojit. Automatika nespojuje existující skupiny, nevybírá podle pořadí identifikátorů a další kolo provádí pouze po skutečném zápisu. Opakovaný běh je idempotentní. Ruční zákaz nelze obejít jiným pravidlem ani vložením zakázaných členů do větší skupiny.

Důkaz obsahuje pravidlo, kontrakt KK-MATCH-3, běh, zdroje, otisk obsahu, párovací data, okno a součty zdrojů; u párování přes Účty také použitou vazbu. Před zápisem se kontrolují zdroje, vlastnictví, nastavení a pomocné vazby proti vstupnímu stavu. Zrušení/chyba ponechá dokončené skupiny a výsledek to výslovně uvede. Historické důkazy starších kontraktů se nepřepisují.

Průběh ukazuje krok, dokončené a zbývající jednotky, čas, uložené skupiny a výsledky po měnách. Důvody nespárování rozlišují chybějící vazbu, chybějící platbu, jinou částku, jinou měnu, nejednoznačnost a ruční zákaz. Nejednoznačnost se uvede i u protějšku, který má jediného kandidáta, pokud je tento kandidát sdílen jinou položkou.

## 5. Ruční práce a rozhraní

Ruční dvojice i skupiny používají párovací plochu. Přetažení a přidání tlačítkem upravují pracovní návrh, nikoli databázi. Uložit skupinu je možné pouze při přesném nulovém rozdílu v jedné měně. Uložení atomicky vytvoří plochou skupinu zdrojových plateb a aktualizuje otevřené i následně vybrané pohledy. Historické otevřené skupiny zůstávají čitelné. Vyřízené skupiny nelze automaticky použít znovu.

V horní tabulce i kandidátech je pořadí Zdroj, Datum, Částka, Měna, Identifikátor, Položka. Zdrojové buňky zobrazují T/P/B, datum DD.MM.YYYY, plné hodnoty zůstávají v nápovědě a filtrech. Interní hodnoty ani exportní formát se tím nemění. Vyhledat kandidáty nastaví vratný filtr všech ostatních zdrojů podle první položky návrhu. Přetažení načte úplné údaje ze stejného databázového snímku a ověří revize i měnu; zastaralá odpověď nesmí přepsat změněný návrh. Vyjmutí z návrhu není finanční rozpojení před uložením.

Undo/Redo kontroluje aktuální stav a zachovává zdrojové částky. Ruční rozpojení automatiky zakazuje její opakování, které lze výslovně povolit. Filtry, výběr a řazení mění pohled, nikoli data. Dlouhé operace běží v pracovním vlákně, widgety se mění jen v GUI vlákně.

## 6. Chyby, DEBUG log a historie

Přehledy plateb a tabulka protějšků nezobrazují sloupce Důvod, Poznámka, Rozdíl, Stav, Objekt ani Počet plateb. Nelze je zapnout nabídkou sloupců a skrytí se vynucuje i po načtení starého rozložení. Staré sloupcové filtry a řazení těchto polí se při otevření platebního přehledu odstraní; výslovné rozšířené filtry a rozdělení na vyřízené/nevyřízené přehledy fungují dál. Ostatních obrazovek se skrytí netýká. Data, podrobnosti, výpočty a souhrny párovací plochy zůstávají zachované.

Buňky tabulek zobrazují kompaktní datum **07.09.2026**; nabídka filtru a nápověda mohou používat český dlouhý formát. U Booking.com je datem přehledu check-out z uloženého údaje departure, včetně řazení, filtrů, párovacího přehledu a rozsahů skupin. Přehledové sestavy používají stejné datum. Datum výplaty a identita zdroje zůstávají uložené beze změny; pravidla automatického párování se nemění. Nový import bez platného check-outu skončí chybou BOOKING_CHECKOUT_INVALID. U historicky poškozeného údaje se datum výplaty nepoužije jako náhrada. Při filtru pouze na BOOKING (včetně uloženého filtru) je záhlaví identifikátoru **Booking.com ID**; ostatní a smíšené přehledy používají **Identifikátor**. Interní identifikátor skupiny se ve sloupci Booking.com ID nezobrazuje. Počet koncových plateb zůstává dostupný v podrobnostech a souhrnech, nikoli jako sloupec tabulky.

Výchozí stav plateb bez aktuálního výsledku párování má kód `NOT_YET_MATCHED`, název **Dosud nepárováno** a informační závažnost. Starší text stejného významu se překládá kompatibilně. Tento běžný stav nikdy nesmí spadnout do obecného hlášení neočekávané chyby.

Jediný číselník je domain/errors.py: stabilní kód, český název, lidské vysvětlení, další krok a závažnost. Je dostupný v Nastavení → Přehled chyb a upozornění a v [přehledu hlášení](ERROR_CATALOG.md). Dialogy, importy, přehledy a sestavy používají stejný význam. Kód je identifikátor k dohledání. Neznámá chyba má srozumitelný obecný popis, ne SQL či obsah výjimky.

Provozní log běží standardně na DEBUG: start, pracovní úlohy, operace, fáze, řádky importu, kandidáti, důvody rozhodnutí, potvrzení/vrácení transakcí a neočekávané chyby. Obsahuje čas a vazbu na operaci nebo interní zdroj. Výjimky mají očištěné místo vzniku bez textu výjimky a místních proměnných.

Logy jsou místní denní JSONL soubory se souběžně chráněným zápisem. Výchozí uchování 30 dní lze nastavit. Trvalý databázový audit se při běžné práci nemaže; výjimkou je výslovně potvrzený úplný reset podle oddílu 9. Do logů nepatří tokeny, celé vstupní řádky, osobní cesty, jména ani syrové odpovědi API. Selhání logu nesmí změnit potvrzenou platbu na hlášení o vrácené transakci; uživatel dostane upozornění na nedostupný záznam.

Finanční audit rozlišuje ruční, automatické a systémové zásahy. Technická událost před potvrzením transakce není důkazem úspěchu; rozhodující je commit/rollback a databázová historie. Historické záznamy nelze vydávat za úplný DEBUG průběh, pokud jej tehdejší program nevytvářel.

## 7. Sestavy, zálohy, kompatibilita

Sestavy CSV/XLSX/PDF/ZIP používají sdílené assets/export_schema.json, doložené zdroje a součty po měnách. Vnoření ani více importních výskytů nesmí zdvojit finanční součet. Export vzniká do dočasného souboru; cílový se nahrazuje až po dokončení. Selhání zápisu historie po vytvoření souboru nesmí tvrdit, že soubor nevznikl.

Záloha zahrnuje ověřenou databázovou kopii včetně Účtů a historie, manifest a kontrolní součet, bez přihlašovacích tajemství. Obnova kontroluje integritu i vazby na izolované kopii a před nahrazením vytváří další zálohu. Diagnostický ZIP obsahuje očištěné logy, souhrnné počty, verze a kontroly; ne celou databázi nebo vstupy. Nikam se sám neodesílá.

Databázové schéma zůstává ve verzi 3. Staré API tabulky a kompatibilitní kód slouží historii a obnově; současný klient síťové použití odmítá. Windows aplikaci a instalátor sestavuje tools/build_windows.ps1 se zamčenými závislostmi. Aktualizace nesmaže pracovní data.

Databáze a zálohy publikované z dočasné složky musí zdědit oprávnění cílové složky. Přímý přesun z chráněné dočasné složky může ve Windows zachovat omezená oprávnění a znemožnit další spuštění běžným účtem. Reset, obnova, přesun pracovního prostoru i zálohování proto nejprve vytvoří nový soubor přímo v cílové složce, zapíší a synchronizují jeho obsah a až poté jej atomicky přejmenují. Při chybě zůstává původní cíl zachovaný. Nejde o důvod spouštět program trvale jako správce.

Selhání otevření databáze se zaznamenává událostí `DATABASE_START_FAILED` včetně bezpečného názvu SQLite chyby nebo čísla chyby systému, bez obsahu dat a osobních cest. Nedostupný soubor či chybějící oprávnění se vysvětlují zvlášť a samy neznamenají poškození dat. Databázové spojení se uzavírá také při selhání jeho počáteční konfigurace.

## 8. Převzetí a forenzní opravy

Každá prokázaná chyba vyžaduje reprodukci, opravu příčiny a regresní scénář. Kontrolují se všechny importy, znaménka, měny, duplicity, konflikty, změna souboru po náhledu, zrušení, chyba zápisu, priorita Bookingu, nejednoznačnost na obou stranách, ruční skupiny, Undo/Redo a opakovaný běh bez změn.

Ověření zahrnuje skutečné Qt ovládací prvky, výsledky a historii, sestavenou Windows aplikaci a obnovu zálohy. Provozní opravy se nejprve ověří na kopii: původní finanční obsah a ruční práce musejí zůstat shodné. Ostrý zásah vyžaduje čerstvou ověřenou zálohu a zámek aplikace. Zasahuje pouze doložené vady nebo výslovně změněná pravidla a přidává auditní stopu.

Auditní protokol odlišuje prokázané výsledky, historicky neověřitelné skutečnosti a neprovedené kontroly. Úspěšné testy samy nedokazují bezchybnost celé aplikace.

## 9. Úplný reset

Nastavení → **Resetovat celý program** otevře samostatné potvrzení s popisem následků. Vymazání vyžaduje přesné slovo **VYMAZAT** a tlačítko **Vymazat vše a restartovat**. Obnova výchozích voleb formuláře a reset rozložení tabulek zůstávají samostatnými nedestruktivními funkcemi.

Reset odstraní celý obsah aktuální databáze: platby, uložené vstupní soubory, importy, Účty a starší pomocná data, ruční i automatická spárování, historii, tajemství, nastavení, výběry a pohledy. Ověřená nová databáze se vytvoří stejnou inicializací jako při prvním spuštění; ochrany historie se neobcházejí přímými DELETE příkazy. Schéma je ve verzi 4 a zachovává se umístění aktuálního pracovního prostoru.

Bez vytvoření další zálohy se odstraní rozpoznané zálohy a diagnostické archivy ve složkách aplikace i v nastavené složce záloh, staré denní logy a rozpoznané databázové kopie ze starších verzí. Archiv se rozpoznává podle vnitřního manifestu, databázová kopie podle tabulek programu. Vlastní složky logs/diagnostics/backups se kontrolují včetně podsložek; externí nastavená záložní složka pouze přímo, bez procházení celého disku. Odkazy a Windows junctions se nenásledují. Původní vstupní soubory mimo aplikaci, uložené exporty a cizí soubory zůstávají zachované. Libovolné kopie uložené mimo tyto známé složky se nevyhledávají.

Reset vyžaduje dokončení všech úloh včetně čtení a zálohování. Potvrzení znovu ověří stav úloh, zastaví časovače a nové úlohy a před výměnou dat ukončí okno i pracovní vlákna. Zámek pracovního prostoru zůstává držený během mazání. Nová prázdná databáze a seznam mazání se nejprve připraví a ověří; teprve potom začíná nevratné odstranění souborů.

Trvalý záznam `.reset.json` umožňuje pokračovat po přerušení nebo selhání mazání. Dokud není reset dokončen, program neotevře běžné okno ani nehlásí úspěch. Při příštím spuštění nabídne dokončení již potvrzeného resetu nebo ukončení programu. Po úspěchu se záznam odstraní a aplikace se otevře prázdná s výchozími volbami. Nové DEBUG logy a další zálohy mohou vznikat běžným provozem. Implementace a její testy resetují pouze izolované zkušební prostory, nikoli provozní data.


## Jednotné okno importu

Všechny vstupy BOOKING, BANK_CARD, CASHBOOK_CARD a ACCOUNTS, včetně opakování uloženého souboru, používají automatický postup výběr souborů → průběhové okno → výsledek → Hotovo. Běžný náhled ani zvláštní potvrzení Booking dávky se nezobrazují. Výběr listu je jedinou podmíněnou otázkou při více vhodných listech; probíhá v hlavním GUI vlákně během jedné operace.

Každý soubor se kontroluje a finančně ukládá samostatně v pořadí výběru. Vadný soubor se celý odmítne a dávka pokračuje dalším. Chybné řádky nejsou totéž co všechny položky neuložené kvůli odmítnutí souboru. Počet již uložených, vynechaných, chybných a nově uložených položek se vykazuje odděleně. Účty vykazují vazby; ostatní vstupy platby. Nečitelné soubory mají neznámý počet, nikoli nulu.

Modální okno vůči hlavnímu oknu vzniká před spuštěním úlohy, nezavírá se automaticky a po ukončení přejde do výsledku s tlačítkem Hotovo. Ukazuje soubor N z M, aktuální fázi, zpracováno X z Y řádků této fáze, zbývající počet a skutečně uložené položky celé dávky. Hlavičky se nepočítají, prázdné a souhrnné řádky jsou vynechané. Počty uložených se zvýší až po potvrzení transakce. Před zjištěním rozsahu je průběh neurčitý; časový odhad se týká výslovně aktuálního kroku, ne celé dávky. Průběhové události nesou strukturovaná data; průběžné aktualizace jsou omezeny na přibližně 10/s s výjimkou hranic fází a konečných stavů.

Zastavit, Escape i zavření běžícího okna požádají o bezpečné zrušení, ponechají okno otevřené a počkají na výsledek. Nedokončená transakce se vrátí, dřívější soubory zůstávají uložené, další jsou nezahájené. Souhrn v okně a historii sdílí stejné výsledky. Starší booking_result je nadále čitelný; nové import_result a batch_summary se ukládají do stávajícího row_counts_json bez migrace schématu. Historie zahrnuje také nečitelné soubory bez uloženého vstupu. DEBUG log obsahuje fáze a skutečné konečné počty bez názvů souborů a osobních údajů.
