# BetterHotel: položky faktur a průběh importu

## Zjištěná příčina

Produkční běh 11. 9. 2026 skončil ve 13:16 místního času po 1 373 odpovědích
HTTP 200 při zpracování detailu faktury. Jeho chyba neměla žádné podrobnosti
a první blok ještě neuložil snapshots. Konkrétní konfliktní fakturu tohoto
běhu proto nelze z logu zpětně jednoznačně určit.

Ve dříve zachycené odpovědi byla reprodukována přesně stejná chyba:
jedna faktura obsahuje běžný řádek a odečet `Deposit` se stejným API ID,
ale odlišným popisem, jednotkovou cenou a částkou. Původní klíč zaměňoval
tyto dva výskyty za jednu entitu.

Ukazatel průběhu sčítal všechny přijaté řádky, včetně detailů a vazeb,
ale jako celkový počet používal součet metadat seznamů. Po dokončení
seznamu proto ukazoval 100 % a dále zvyšoval oba počty.

## Oprava

První čistě živé ověření nové implementace odhalilo také rozdíl projekcí:
seznam faktur vrací historický číselný odkaz měny `154`, zatímco detail téže
faktury vrací `EUR`. Číselník obsahuje UUID a ISO kódy, nikoliv tento číselný
odkaz. Neznámý odkaz se proto uchovává v `currency_reference` a vyžádá se
detail, ze kterého se převezme skutečný ISO kód. Není použito pevné mapování
čísla na měnu. Explicitní rozpor dvou ISO kódů nadále selže. Prázdný volitelný
text `note` se nepovažuje za rozpor s obsahem doplněným detailem; finanční
částky ani identity tímto pravidlem nejsou změněné.

- Položky mají interní identitu výskytu v konkrétní faktuře. Původní ID
  zůstává v `source_item_id`, raw odpovědi se zachovávají.
- Záloha nepřepisuje běžnou položku. Pořadí řádků nemění množinu identit;
  identické opakované řádky zůstávají samostatnými výskyty.
- Úplný import i obnova detailu používají stejná pravidla. Skutečný rozdíl
  reprezentací celé faktury nadále import zastaví a uloží soukromou
  diagnostiku s oběma podklady a názvy rozdílných polí.
- Seznam rezervací se načítá jednou za celé nastavené období. Doklady
  zůstávají rozdělené na časové bloky.
- UI dostává strukturované události. Seznamy, výběr pobytů, dokončené
  rezervace, ukládání a statistiky mají oddělené fáze; API volání jsou
  samostatný čítač. Neznámý či nesprávný počet nevede k falešným procentům.
- Checkpointy se ukládají po blocích dokladů, dokončeném seznamu a výběru
  a po dávkách 25 rezervací. Starý importní kontrakt nelze obnovit.

## Výběr dat a Booking klíč

Datum začátku je v Nastavení uložené pod `sync.start_date`, výchozí hodnota
pro dosud nenastavenou databázi je 2026-01-01. Konec nového importu je aktuální
den. Načítá se číselník měn, doklady v časových blocích, jediný seznam rezervací
s rozšířeními `reservation_source` a `reservation_note`, detaily vybraných
rezervací, jejich doklady, účty s položkami, kauce a doplňkové statistiky.
Pobyt se zahrne při `arrival <= konec` a `departure >= začátek`, včetně hranic.
Související doklady vybraného pobytu mohou být i mimo zadané období.

Booking číslo se extrahuje z pole `channel` v `reservation_note`. Po odstranění
HTML se hledá `Original ID` nebo `Channel reservation id` následované 6–20
číslicemi. Číslo zůstává textem, včetně případných úvodních nul. Automatické
potvrzení vyžaduje zdroj rezervace `booking.com` a jediného odlišného kandidáta;
více různých čísel je konflikt vyžadující platné ruční rozhodnutí.

Párování používá klíč **(potvrzené Booking číslo, měna)** a na straně Booking
plateb **(`booking_reference`, měna)**. Interní UUID BetterHotel rezervace není
tímto Booking číslem. Pokladní platba k němu dochází přes ověřený doklad a
vazbu dokladu na rezervaci. Shoda klíče pouze sestavuje kandidáty; následně se
kontrolují částky a jednoznačnost kombinace. Import pomocných dat sám párování
nespouští.

## Ověření

Úplné přehrání skutečných odpovědí pro období 2026-01-01 až 2026-09-11
úspěšně skončilo: `READY`, operace `COMPLETED`, `PRAGMA integrity_check = ok`.
Výsledek obsahuje 19 219 pomocných entit a 18 093 vazeb; mezi entitami je
2 053 rezervací vybraných podle překryvu pobytu. Závěrečný běh nevyžadoval
žádný nový síťový požadavek, protože všechny odpovědi včetně opravených
statistik již byly zachycené. Není vydáván za samostatný čistě živý import.

- Přehrání skutečné zachycené faktury bez sítě: `READY`, zachovány všechny
  čtyři řádky, úspěšná obnova detailu se zachováním všech řádků.
- Regresní sada API, období, dřívějších aliasů a GUI: 61 testů prošlo.
- Celá sada: 201 prošlo, 11 selhalo. Jeden test ještě předpokládal seznam
  rezervací opakovaný v blocích; byl převeden na přesun mezi stránkami a
  následně prošel. Zbývajících 10 selhání párování a jeho UI bylo znovu
  reprodukováno i s původní synchronizací načtenou z Git HEAD. Celá sada
  není zelená; tato selhání nejsou vydávána za opravená.
- Nové testy zahrnují kolizi ID a zálohy, identické výskyty, změnu pořadí,
  skutečný konflikt s diagnostikou, 20 001 doplňkových odpovědí, chybný
  `total_count`, jediný seznam přes více bloků a obnovu od 25. rezervace.
- První čistě živé ověření období 2026-01-01 až 2026-09-11 na izolované
  kopii odhalilo výše uvedený odkaz měny a prázdnou poznámku. Z 15 509
  vrácených rezervací do období zasahuje 2 053 pobytů. Následovalo přehrávání
  zachycených odpovědí s živým doplňováním a výše uvedené úspěšné dokončení.
- Rozšířená cílená sada po opravě měn: 84 testů prošlo.
- Závěrečný běh celé sady včetně převzetí dat a ekvivalentních zápisů vazby:
  221 prošlo, 10 selhalo
  ve výše uvedených již reprodukovaných problémech párování a jeho UI.
- Normalizace vložených řádků se vztahuje pouze na faktury; strukturovaný
  rozpis kauce se zachovává. Výslovný odkaz faktury na chybějící položku účtu
  se doplní jejím detailem, aniž se rozšíří výběr rezervací mimo období.
- Regresní kontrola vazeb odhalila ještě porovnávání původního zápisu řádku:
  `label: null` proti prázdnému řetězci a `10.000` proti `10` nesmí vytvořit
  konflikt vazby při shodném normalizovaném obsahu. Úplný import i obnova nyní
  na vazbě faktury k řádku používají stejnou normalizaci jako řádek samotný;
  oba původní podklady zůstávají uložené.
- Závěrečné ukládání skutečného objemu dat odhalilo pomalou databázovou kontrolu:
  dosažitelnost se počítala v korelovaném poddotazu pro každou entitu znovu a
  rekurzivní spojení opakovaně procházelo vazby. Kompatibilní úprava schématu 2
  v `sync_graph_guard.sql` zachovává všechny kontroly publikace, materializuje
  dosažitelné entity jednou a pro návazné vazby používá index od aktuálního uzlu.
  Sedm regresních testů ověřuje cykly, osiřelé uzly, neúplné vazby/cíle, pokrytí
  období a omezený počet instrukcí SQLite pro graf s 1 000 uzly. Ukládání entit
  také používá předem sestavený index projekcí místo opakovaného průchodu všemi
  reprezentacemi. Původní testovací zápis byl zastaven a data přehrána z evidence.
- Po úspěšné publikaci grafu API odmítlo původní parametry doplňkových statistik
  odpovědí HTTP 400 `missingParam`: vyžaduje `from` a `to`, nikoliv `date_from`
  a `date_to`. Opravený dotaz pro celé období byl živě potvrzen HTTP 200 a
  doplněn regresním testem. Poslední cílená sada: 65 testů prošlo.

Produkční databáze se v izolované ověřovací fázi otevírá pouze pro čtení. Testovací
databáze i zachycené odpovědi jsou v ignorovaném `.tmp` a obsahují soukromá
data. Nejsou součástí repozitáře. Nástroj `tools/verify_live_sync.py`
podporuje pokračování pomocí `--resume-folder`; použití `--replay` je vždy
označeno jako přehrávání s případným živým doplněním, nikoliv čistý živý běh.

Na následnou výslovnou žádost uživatele byla ověřená data ponechána v databázi
programu. Převzetí úspěšně skončilo `READY / COMPLETED`: 19 219 entit, 18 093
vazeb, integrita `ok`, kontrola cizích klíčů bez chyby. Kontrolní součty všech
sledovaných finančních a párovacích tabulek i nastavení zůstaly stejné. Nebyl
potřeba žádný nový síťový požadavek. Před převzetím vznikla ověřená záloha
`before-verified-sync-e7dcaa0530ce4c2a981a6e736988ff95.zip` v adresáři záloh programu.

`tools/publish_verified_sync.py` před převzetím kontroluje dokončený ověřovací
import, shodu připojení a období a zámek aplikace, vytvoří ověřenou zálohu bez
tokenů a zpracuje zachycené odpovědi standardním importérem nad aktuální databází.
Neobnovuje starou kopii databáze. Kontrolní součty finančních tabulek, párovacích
skupin, členství, zákazů párování, ručních referencí a nastavení musí zůstat stejné.
Chybějící odpovědi se mohou doplnit běžným GET; režim se uvádí v protokolu.
Všech 65 cílených testů importu, období, průběhu a převzetí dat prošlo. Test převzetí
vytváří nové platby a párovací skupinu až po pořízení ověřovací kopie a kontroluje,
že se neztratí. Další testy odmítají nedokončené ověření, změněné připojení či
období a převzetí při zámku otevřené aplikace.
