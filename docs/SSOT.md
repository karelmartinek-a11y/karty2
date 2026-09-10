# KájovoKarty — SSOT

**Závazná funkční, datová a technická specifikace programu**  
**Produkt:** KájovoKarty  
**Platforma:** lokální desktop Windows 11 x64  
**Jazyk rozhraní:** čeština  
**Charakter:** jeden lokální pracovní prostor, bez aplikačních účtů, rolí a přihlášení.

## 1. Autorita a definice dokončení

Tento soubor je jediným zadáním implementace. Obsahuje obchodní pravidla, importní kontrakty, HTTP kontrakt, datový model, chování obrazovek, provozní pravidla a ověřovací data. Programátor nepotřebuje další dokument, repozitář ani samostatný vzor vstupu. Binární ověřovací soubory jsou součástí tohoto dokumentu v příloze B; postup jejich rekonstrukce je uveden přímo zde. Skutečné přístupové tokeny nejsou součástí specifikace: provozovatel zadává svou dvojici v Nastavení aplikace.

Slova **musí**, **nesmí** a tabulkové kontrakty jsou závazná. Příklady nejsou výjimkami z pravidel. Neexistuje oprávnění nahradit nedokončenou funkci maketou, neaktivním tlačítkem, ručním zásahem do databáze, skrytou konfigurací nebo odpovědí „testy prošly“.

**Splnění jednotlivých definic, odškrtnutí seznamu požadavků ani úspěch testů samy o sobě neznamenají dokončení úkolu. Úkol je dokončen teprve tehdy, když všechny funkce, vlastnosti a součásti tvoří plně funkční, propracované dílo na nejvyšší úrovni jakosti programování, obstojí při odborném posouzení zdrojového kódu i při skutečné práci s distribuovanou aplikací a nemá známé nedodělky nebo obcházení požadovaného chování.**

Konkrétní důkazy dokončení stanoví kapitola 18. Žádná metrika neuděluje výjimku z odborného posouzení. Zjištěná chyba se opravuje v příčině a ve všech dotčených cestách, nikoli pouze v testovaném příkladu.

## 2. Účel, rozsah a hranice

Program průběžně dokazuje finanční vysvětlení karetních pohybů hotelu. Spojuje tři skutečné finanční zdroje a pomocný graf BetterHotel:

| Oblast | Kód | Význam |
|---|---|---|
| Karetní pohyby pokladního deníku | `CASHBOOK_CARD` | Evidence očekávaného karetního příjmu nebo vrácení v hotelu |
| Transakce terminálu/banky | `BANK_CARD` | Důkaz skutečné karetní transakce; prodej, storno, refundace |
| Výplaty Booking.com | `BOOKING` | Finanční řádky připsané či odečtené prostřednictvím Booking.com |
| Doklady, rezervace, účty, položky účtů, kauce a statistiky BetterHotel | `HELPER` | Identifikace a vysvětlení; nikdy samostatné finanční krytí |

Povinné schopnosti: ruční import pokladny XLS, terminálu CSV/XLS/XLSX a Booking CSV; výslovně spuštěné čtení API; výslovně spuštěné automatické párování; úplná ruční práce 1:1, 1:N, N:1, N:N; otevřené i vyřízené vnořené skupiny; jednotný nevyřízený seznam; filtry, fulltext, historie, CSV/XLSX/PDF sestavy, záloha, obnova, diagnostika a bezpečné Undo/Redo.

Pracuje se pouze v CZK a EUR. Program nepřevádí měny, nesčítá je dohromady, nestahuje kurzy a neprovádí platby. Booking částka se nepřepočítává na cenu pobytu ani se k ní automaticky nepřidává provize. Nepotřebuje OpenAI, SMTP, bankovní API, webový server ani další službu kromě BetterHotel. Žádná změna se nezapisuje do BetterHotel.

Zdrojový řádek nelze ručně upravit, smazat, rozdělit na částečné alokace ani nahradit fiktivní hotovostí. N:N se řeší skupinou celých řádků. Nenulový rozdíl nelze označit za vyřízený tlačítkem. Pomocný doklad nelze označit za finančně uhrazený bez důkazu. Nevyřízenost je legitimní pracovní stav, nikoli důvod doplňovat domnělé peníze.

## 3. Matematika a identita pracovního objektu

### 3.1 Částky

`signed_amount_minor` je celé číslo v haléřích nebo centech; + znamená skutečný příjem, − vrácení. `contribution_minor` je rekonsiliační příspěvek:

```text
CASHBOOK_CARD: contribution_minor = signed_amount_minor
BANK_CARD:    contribution_minor = -signed_amount_minor
BOOKING:      contribution_minor = -signed_amount_minor
HELPER:       neexistuje finanční contribution; do výpočtu se nevkládá
group_difference_minor = SUM(contribution_minor jedinečných listových členů)
```

Vyřízeno znamená aktivní skupinu alespoň dvou přímých dětí, s jednou měnou a přesným rozdílem 0. Tolerance je vždy 0 a není nastavitelná. Všechny aritmetické operace používají integer nebo Decimal; binary float nesmí řídit finanční rozhodnutí. Každá jednotlivá částka a výsledný součet musí být v rozsahu −9 000 000 000 000 000 až +9 000 000 000 000 000 minor units; překročení se odmítá před zápisem. Mezisoučty se počítají pomocí Python integer, nikoli přetékajícího SQL SUM.

Samostatný zdrojový řádek má finanční stav Nevyřízeno. Nulové zdrojové pohyby se do finančního modelu neimportují. Skupina s nenulovým rozdílem je Nevyřízeno; s nulovým rozdílem Vyřízeno. Stav listového člena se pro uživatelské zobrazení odvozuje od aktivního kořene jeho stromu, nikoli od libovolné vnořené skupiny.

### 3.2 Zobrazení částek a součtů

Řádek zdroje ukazuje původní signed částku i samostatný rekonsiliační rozdíl. Skupina ukazuje `abs(group_difference_minor)` jako zbývající částku a rozdíl se znaménkem; nikoli součet všech kladných nominálních částek. Strana je `POTŘEBA KRYTÍ` pro rozdíl > 0, `PŘEBYTEK KRYTÍ` pro < 0 a `VYROVNÁNO` pro 0. Jde o matematický efekt, nikoli tvrzení, že každý kladný zbytek pochází z pokladny.

Příklady v EUR:

| Členové, jejich signed částky | Rozdíl | Výsledek |
|---|---:|---|
| Pokladna +50, Booking +50 | 0 | Vyřízeno |
| Pokladna +50, banka +10, Booking +40 | 0 | Vyřízeno |
| Pokladna +25, pokladna +25, banka +50 | 0 | Vyřízeno |
| Booking +50, Booking −50 | 0 | Vyřízeno |
| Banka +10, Booking +40 | −50 | Jeden nevyřízený agregát, přebytek krytí 50 |
| Pokladna +25, pokladna +25 | +50 | Jeden nevyřízený agregát, potřeba krytí 50 |
| Pokladna +50, Booking +49,99 | +0,01 | Nevyřízeno |
| Pokladna −50, banka −50 | 0 | Vyřízeno |

### 3.3 Stromové vlastnictví

Pracovní objekt je zdrojový řádek nebo skupina. Aktivní skupiny tvoří les orientovaných stromů: každé dítě má nejvýše jednoho aktivního rodiče, neexistuje cyklus, dítě nemůže být současně předkem rodiče. Každý list je započten právě jednou. Kořen je aktivní objekt bez rodiče. Dashboard zobrazuje pouze nevyřízené kořeny. Členové skupiny se v něm znovu samostatně nezobrazují.

Nulové kořeny nelze přidávat do další finanční skupiny. Ručně vytvořené nenulové skupiny lze libovolně skládat s dalšími nevyřízenými kořeny téže měny. Počet ručně vybraných položek nemá obchodní limit; implementace musí pracovat dávkově a bez limitu počtu SQL parametrů. Strom se prochází iterativně, aby hluboké vnoření nezpůsobilo rekurzní pád.

## 4. Společný kontrakt importů

### 4.1 Operace a atomický zápis

Jedním importem je celá sada souborů potvrzená jedním tlačítkem „Importovat“. Při chybě v kterémkoli souboru se z této operace nevloží žádný finanční řádek. Jednotlivý soubor je speciálním případem sady. Importní dávka slouží pouze jako provenance; nevytváří frontu k dokončování.

Postup: vybrat soubory → uzamčený snapshot jejich bytů → detekce formátu → list/hlavička → parsování všech řádků → normalizace a klasifikace → identity a hashe → porovnání uvnitř celé sady i s DB → souhrnný náhled → jeden atomický commit. Uživatel vidí nové, známé, ignorované, chyby a součty po měnách. Jakmile existuje chyba, „Importovat“ je zakázáno. Žádná karanténa, částečný import ani přeskočení neznámého relevantního řádku.

Import má právě jeden z režimů `EXTERNAL_FILE` nebo `STORED_SNAPSHOT` pro každý vstup. Režim se uloží v náhledu a provenance, nesmí se automaticky změnit po chybě. V obou režimech vznikne soukromý dočasný snapshot a hash přesných bytů:

| Režim | Autoritativní vstup a kontrola před commitem | Chybový výsledek |
|---|---|---|
| `EXTERNAL_FILE` — Výběr nového souboru | Zvolený externí soubor; těsně před commitem znovu spočítat hash dočasného snapshotu i aktuálně čtených bytů originálu; oba se musí rovnat hashi z náhledu. Dokončit celý přenos ze síťové složky. | Změna snapshotu nebo změna, nedostupnost či odstranění originálu → FILE_CHANGED; nikdy nepřejít sám na uloženou kopii. |
| `STORED_SNAPSHOT` — Zopakovat uložený import | Konkrétní immutable `source_file.id` a jeho BLOB v DB, byte_size a sha256. Před commitem znovu ověřit shodu BLOB→hash/velikost→náhled a jeho dočasný snapshot. Externí původní cesta se vůbec neotevírá. | Chybějící uložený BLOB nebo porušená integrita → SNAPSHOT_INVALID; nikoli FILE_CHANGED. |

V režimu STORED_SNAPSHOT je odstranění či změna původního externího souboru bez vlivu. Uložení originálu jako source_file je technická evidence a samo nevytváří finanční řádek; i odmítnutý předchozí import lze zopakovat, pokud byl jeho úplný BLOB úspěšně uchován. Neúplný snapshot není opakovatelný. Opakování používá aktuální parser a aktuální DB, vznikne nový import_run a provede se stejný preflight i atomický commit. Náhled uvádí režim, uložené source_file.id/hash a odkaz na původní běh. Nový import_file zachová také původní zobrazovaný název vstupu, i když se source_file deduplikuje podle bytů. Ve finančním commitu se znovu kontrolují identity proti aktuální DB. Audit operace smí zaznamenat zahájení či odmítnutí; při selhání však finanční zdroje, skupiny, členství a jejich předchozí auditní události zůstávají beze změny.

Identický hash celého souboru dovoluje vynechat drahé parsování pouze při existenci kompletního úspěšného importu pod stejným parser kontraktem. Nevytváří nové finanční objekty. Opakované roční exporty jsou běžný podporovaný provoz. Známé řádky se ignorují, přibudou pouze nové; import nikdy nespouští finanční párování.

### 4.2 Obecná normalizace

| Typ | Závazné pravidlo |
|---|---|
| Prázdno | `None`, prázdný řetězec a řetězec pouze whitespace → `null`; nikoli číslo 0 |
| Hlavička | Odstranit U+FEFF, Unicode NFKC, okolní mezery; vnitřní whitespace sloučit na jednu mezeru; casefold pro vyhledání mapy |
| Běžný text | HTML entity dekódovat jednou, NFKC, CRLF/CR → LF, trim; vnitřní text zachovat; HTML nikdy nespouštět |
| Identifikátor | NFKC + trim; nerozbíjet vnitřní znaky, neztratit úvodní nuly; case-sensitive kromě výslovně normalizovaných enumů a pokladního čísla |
| Excel numeric identifikátor | Pouze celé konečné číslo s nejvýše 15 číslicemi → desetinný text bez `.0`; neobnovovat domnělé úvodní nuly |
| Textový identifikátor | `001284002` zůstává `001284002`; text `123.0` zůstává textem, neodstraňovat příponu na základě odhadu |
| Měna | NFKC + trim + uppercase; přesně CZK nebo EUR; nezjištěná měna se nikdy nedoplní podle sousedního řádku |
| Datum bez času | Kalendářní ISO `YYYY-MM-DD`; neprovádět z něj UTC posun |
| Lokální timestamp exportu | Europe/Prague, uložit UTC a místní datum i původní text |
| API timestamp | RFC3339 s offsetem → UTC; API ISO timestamp bez offsetu se explicitně interpretuje jako UTC |

Pokladna a terminál přijímají místní `D.M.YYYY H:MM:SS`, `DD.MM.YYYY HH:MM:SS`, ISO datetime a skutečný Excel datetime. Samostatná data přijímají `D.M.YYYY`, `DD.MM.YYYY`, `YYYY-MM-DD`. Číselný Excel serial se interpretuje pouze u datové buňky se skutečným datovým formátem, podle 1900/1904 epochy sešitu; Excel den 60 v 1900 epoše se odmítá. Terminál vyžaduje čas vzniku, nikoli jen datum.

Neexistující lokální čas při přechodu na letní čas je chyba řádku. U dvojznačného podzimního času se uloží místní hodnota a oba UTC kandidáti; `occurred_at_utc=null`, `time_precision=AMBIGUOUS_LOCAL`. Import nesmí odhadnout offset. Párování používá místní kalendářní datum, proto může pokračovat. CSV ani XLS se nesmí měnit kvůli opravě času. Pro API bez časové zóny platí výslovné UTC pravidlo výše.

### 4.3 Parsování peněz

Povolené textové tvary: `717`, `717,00`, `717.00`, `1 250,50`, `1 250,50` (NBSP), `-83.49`, `+50,00`. Mezera/NBSP/thin NBSP smí být pouze správný třímístný oddělovač tisíců v celočíselné části. Tečka nebo čárka je desetinný oddělovač; jejich současný výskyt, exponent, symbol měny, závorky, NaN, Infinity a zápis s více než dvěma nenulovými desetinnými pozicemi jsou chyby. Koncové nuly nad dvě desetinná místa jsou nevýznamné (`50.000` = 50). Číslo se nezaokrouhluje. Částka = `Decimal(normalized_text) * 100`, výsledek musí být celočíselný. `-0` se normalizuje na 0.

Excel číslo převést přes nejkratší desetinnou reprezentaci vrácené hodnoty (`Decimal(str(value))`), nikoli `Decimal(float)`; u BIFF ověřit, že po přepisu odpovídá původní uložené numeric hodnotě s přesností typu. Hodnota `1.005` se neakceptuje jako `1.00` nebo `1.01`. Peníze v prázdných příjmech/výdajích, cashbacku a spropitném se interpretují jako 0; prázdná hlavní částka terminálu nebo Bookingu je chyba.

### 4.4 Hlavičky, obsah a bezpečnost parseru

První neprázdný řádek listu/CSV musí být hlavička. Sloupce lze přeskupit pomocí mapy přesných významů. Každý požadovaný sloupec se musí objevit právě jednou; dva aliasy téhož sloupce znamenají chybu. Chybějící sloupec nebo neprázdný neznámý sloupec znamená chybu schématu. Prázdné koncové sloupce se ignorují. Neprázdná hodnota za posledním deklarovaným sloupcem je chyba. Řádek s chybějícími koncovými nepovinnými buňkami lze doplnit null; neprázdný řádek bez hodnot povinných polí je chyba. Neprovádět posouvání buněk heuristikou; jediná povolená strukturální oprava pokladny je přesně definována v kapitole 5.2.

Formát určuje přípona a signatura dohromady: `.xls` OLE/BIFF8 `D0 CF 11 E0 A1 B1 1A E1`; `.xlsx` ZIP s platným OOXML workbookem; `.csv` skutečný dekódovatelný text. HTML pod příponou XLS, XLSM, zaheslované soubory, makra, externí datové odkazy a vzorce v datech se odmítají. Parser nic nespouští a nevolá Excel. XLSX se otevře s `data_only=False`, aby se vzorec nezaměnil za hodnotu z cache; pro XLS se přítomnost BIFF FORMULA v použitém rozsahu kontroluje při čtení. Text CSV začínající `=` je běžný text jen v textovém poli, nikdy vzorec.

Pro exporty BetterHotel se musí podporovat varianta OLE, kterou striktní xlrd odmítá chybou `Workbook corruption: seen[...]`. Použít `xlrd.open_workbook(file_contents=bytes, on_demand=True, ragged_rows=True, ignore_workbook_corruption=True)`; varování zachytit do diagnostiky. Tato kompatibilita neomlouvá nečitelný workbook, neplatné buňky, chybějící povinná pole ani částečné čtení. Oba XLS v příloze B se musí načíst celé. Nesmí se vyžadovat jejich ruční otevření a přeuložení v Excelu.

Zdrojové řádky se validují všechny podle jejich klasifikace, včetně skrytých řádků zvoleného listu. Hidden sheet se automaticky nevybírá. Limity: výchozí 100 MiB na soubor, nastavitelné 1–2048 MiB; OOXML nejvýše 100 000 ZIP entries, nejvýše 1 GiB rozbaleného obsahu a poměr komprese 1000:1; překročení se explicitně odmítá. Symbolické odkazy, vnořené archivy a zip-slip cesty se nerozbalují. Limity nesmějí způsobit tiché oříznutí řádků.

### 4.5 Kanonické hashe a tvrdý konflikt

Kanonický JSON: UTF-8, klíče lexikograficky řazené, bez mezer mimo textové hodnoty, `ensure_ascii=False`, null pro prázdná nepovinná pole, částky jako integer minor units, data ISO, měny uppercase, enumy podle kontraktu. Žádné `default=str` maskující neznámé typy. Pole mimo kanonický slovník se nepřidávají. Hash = lowercase hex SHA-256 bytů JSON. Složené identity se hashují jako JSON pole hodnot; nikoli neescapovaným spojováním s oddělovačem.

Stejná source identity a stejný canonical hash = známý řádek bez nové doménové identity. Stejná identity a odlišný canonical hash = tvrdý konflikt a odmítnutí celé operace. Platí i uvnitř jednoho souboru a mezi právě vybranými soubory. Jiný hash se nesmí uložit jako druhá aktivní revize. Hash není náhradou přirozené identity. Při shodě hashů se pro vyloučení programové chyby porovná i kanonický JSON.

Název souboru, číslo řádku, název listu, datum importu a styl buněk nepatří do identity ani finančního content hash. Syrový řádek, datové typy a všechny hodnoty včetně souhrnných footerů jsou zachovány v provenance. Přejmenování souboru, přeuspořádání řádků či jiný počáteční stav ročního exportu nezakládají nové transakce.

## 5. Pokladní pohyby BetterHotel

### 5.1 Autoritativní schéma

Jediný podporovaný pokladní kontrakt tvoří dva XLS `cashbook_year.xls` a `cashbook_week.xls` vložené v příloze B. Jde o přehled pohybů `pos_records`, nikoli o jiný třináctisloupcový deník. **Importuje se výhradně Forma úhrady = Kartou. Hotově a Převodem se finančně ignorují.**

Formát je OLE/BIFF8 XLS; list `Worksheet`. Je-li přítomen a viditelný, musí splnit schéma; neplatný stejnojmenný list znamená chybu. Pokud chybí, musí právě jeden viditelný list splnit celé schéma. Po odstranění prázdných koncových hlaviček je přesně 11 významových sloupců:

| # | Hlavička | Kanonické pole | Pravidlo |
|---:|---|---|---|
| 1 | `Vystaveno` | `issued_local` | Povinný timestamp pohybu; úvodní mezera se odstraní |
| 2 | `Pohyb` | `movement` | Přesně Příjem / Výdaj |
| 3 | `Číslo` | `cashbook_number` | Text/null; u všech doložených karetních pohybů prázdné; nesmí být vyžadováno PPD/PVD |
| 4 | `Označení` | `label` | Povinný text; obsahuje číslo faktury FA a případný marker [STORNO] |
| 5 | `Klient` | `client` | Text/null; podléhá přesně popsané opravě rozdělené entity |
| 6 | `Příjem` | `income_minor` | Nezáporná částka; prázdno = 0 |
| 7 | `Výdaj` | `expense_minor` | Nezáporná částka; prázdno = 0 |
| 8 | `Měna` | `currency` | CZK/EUR |
| 9 | `Forma úhrady` | `payment_form` | Kartou / Hotově / Převodem |
| 10 | `Variabilní symbol` | `variable_symbol` | U karetních řádků povinný identifikátor; numeric 20266155.0 → text 20266155 |
| 11 | `Vystavil` | `issued_by` | Text/null; zdrojový údaj, nikoli aplikační uživatel |

Nesmí se očekávat `Stav pokladny` ani `Pokladna`. Dvanáctá prázdná hlavička a prázdné koncové buňky ročního exportu nejsou významovým sloupcem. Přítomnost jiného třináctisloupcového schématu je chyba formátu. Nad konkrétními vzory musí projít parsování bez ručního zásahu do souboru.

### 5.2 Deterministická oprava rozdělené HTML entity

Roční XLS má 12 fyzických sloupců. Na dvou řádcích byl text `H&amp;H security s.r.o.` rozdělen v místě středníku do dvou sousedních buněk, a proto jsou všechny další hodnoty o jednu buňku vpravo. Oprava je součástí parser kontraktu, ne obecné hádání posunu.

Před mapováním hodnot, filtrem formy úhrady a čtením částek:

1. Zjistit, zda má řádek 12 fyzických pozic s neprázdnou poslední buňkou a hlavička přesně základní pořadí 11 sloupců tabulky. Řádky s 12. prázdnou buňkou jsou normální a pouze se zkrátí na 11. Pro přeskupenou hlavičku se oprava nepoužívá a nesplněné schéma se odmítne.
2. Opravu povolit výhradně při `cell[4] == "H&amp"` po trim, `cell[5] == "H security s.r.o."` po trim, `cell[8] ∈ {CZK,EUR}`, `cell[9] ∈ {Kartou,Hotově,Převodem}`, validních peněžních `cell[6]`/`cell[7]`, identifikátoru nebo prázdné `cell[10]` a textové `cell[11]`. Indexy zde začínají nulou.
3. Vytvořit přesně `cells[:4] + [cells[4] + ";" + cells[5]] + cells[6:]`. Výsledkem musí být 11 buněk. Poté se HTML entity dekódují jednou, takže klient je `H&H security s.r.o.`.
4. Uchovat původních 12 buněk, opravených 11 buněk a repair_code=`SPLIT_CLIENT_ENTITY` v provenance. Žádné přepisování originálního XLS. Oprava nemění částky ani účetní význam.
5. Jakýkoli jiný neprázdný přesah nebo jiný posun se odmítá `ROW_SHAPE_INVALID`; nesmí se zkoušet více posunů a vybrat ten, který „vypadá dobře“.

Ověřovací řádek 1116 je hotovost 600 CZK a musí se po opravě ignorovat. Řádek 1150 je karta 135,71 EUR, doklad FA20265707, a musí se po opravě importovat. Ignorovat ho jako neznámý řádek by ztratilo skutečné karetní peníze.

### 5.3 Prázdné řádky, footer a relevantnost

Prázdný řádek: po normalizaci všechny buňky prázdné. Footer: `Vystaveno`, `Pohyb`, `Číslo`, `Označení`, `Klient`, `Měna`, `Forma úhrady`, `Variabilní symbol` a `Vystavil` jsou prázdné, pouze Příjem/Výdaj mohou obsahovat souhrnné numeric hodnoty. Footer je dovolen nejvýše jeden, po něm mohou následovat jen prázdné řádky. Footer se nesmí považovat za karetní pohyb ani podle něj určovat měnu. Tato struktura se rozpozná před parsováním peněz; hodnoty jako 3533744.290000003 jsou surovým exportním souhrnem, nikoli přesnou finanční částkou zdrojového řádku.

Footerové součty Příjem/Výdaj se pro kontrolu úplnosti porovnají s agregací všech běžných pohybů všech forem po normalizaci a opravě, po zaokrouhlení pouze těchto dvou footerových hodnot na 2 desetinná místa ROUND_HALF_UP. Souhrn směšuje měny, a proto je výhradně technickou kontrolou. Není obchodním KPI. Rozdíl proti přesným agregovaným sloupcům po tomto zaokrouhlení → diagnostické upozornění `CASHBOOK_FOOTER_MISMATCH`, nikoli odmítnutí jinak platných řádků. Roční vzor obsahuje právě takový rozpor: součet jednotlivých pohybů je Příjem 3534480.00 a Výdaj 560054.56, zatímco footer uvádí po zaokrouhlení 3533744.29 a 560790.27. Autoritou jsou jednotlivé pohyby, ne footer; parser je kvůli souhrnu nesmí přeúčtovat. Týdenní footer 25670.74 / 6981.00 souhlasí. Toto pravidlo není finanční tolerance; jednotlivé karetní částky se nikdy nezaokrouhlují.

Po strukturní opravě a detekci footeru se enum normalizuje NFKC + trim + casefold:

| Přesná hodnota | Kanonický význam | Chování |
|---|---|---|
| kartou | CARD | Validovat všechny karetní kontrakty a importovat |
| hotově | CASH | Nefinanční provenance + ignorovaný počet; žádný pracovní objekt |
| převodem | TRANSFER | Nefinanční provenance + ignorovaný počet; žádný pracovní objekt |
| ostatní včetně prázdna u běžného řádku | UNKNOWN | Odmítnout celou operaci; žádné odhady aliasů |

Tyto tři hodnoty jsou přímo doložené vzory. Není potřeba uživatelské mapování. U nekaretních řádků se validuje struktura a čísla nutná ke kontrole footeru, ale nevyžaduje se karetní dokumentový identifikátor. Hotovost a převod nejsou k dispozici pro ruční párování ani jako zdroj krytí. Slovo Payment či Úhrada v Označení se nikdy nepoužije pro ignorování karty. Vzory zahrnují české, anglické, německé, ruské, francouzské, italské a maďarské texty; import nesmí záviset na jejich jazyku.

### 5.4 Směr, storna a dokumentový odkaz

`signed_amount_minor=income_minor-expense_minor`. Obě kladné hodnoty, záporný příjem/výdaj nebo rozpor Pohyb s výsledným znaménkem jsou chyby. Obě nuly → ignorovaný nulový karetní pohyb po ověření ostatních povinných polí. `Příjem` znamená kladné, `Výdaj` záporné. Prefix `[STORNO]` je metadata události, nikoli náhrada znaménka.

`storno_marker` je true právě při prefixu `[STORNO]` po trim, case-insensitive. Příjem s tímto markerem je stále kladný. Řádky 1103 a 1104 ročního exportu tvoří příjem +24,74 a výdaj −24,74 CZK se stejným FA20265667 a časem 30.6.2026 10:30:00. Řádek 1105 je další příjem +600 CZK bez markeru. Všechny tři jsou odlišné pohyby; nic se při importu automaticky nezapočítává.

Číslo souvisejícího dokladu se extrahuje z Označení pomocí `(?i)(?<![A-Z0-9])FA[0-9]+(?![A-Z0-9])`. Po uppercase musí existovat právě jeden různý kód. Variabilní symbol je samostatný identifikátor a nemusí být číselnou částí FA; například doložené FA20264805 má VS 120267135, FA20265018 a FA20265678 mají VS 120267524 a FA20265706 má VS 120268352. Tyto řádky jsou platné. Více různých FA kódů nebo chybějící reference/VS u karetního pohybu je `CASHBOOK_REFERENCE_INVALID`, nikoli odhad podle jména hosta. Nulové prefixy se neodstraňují. Extrahovaný FA kód propojuje cashbook s invoice.code, zatímco VS zůstává samostatným identifikátorem.

### 5.5 Identita pohybu bez PPD/PVD

Vzory neposkytují stabilní technické ID karetní události. Číslo je u všech 1 055 karetních řádků prázdné. Nesmí se proto použít prázdné číslo jako identita, vymyslet PPD ani identitu založit na pořadí řádku či názvu souboru.

```text
cashbook_identity = SHA256(canonical_json([
  issued_local, movement, invoice_code, variable_symbol, storno_marker
]))
```

`issued_local` je ISO místní timestamp s přesností skutečného exportu; `movement` INCOME/EXPENSE; `invoice_code` uppercase FA…; VS text; marker JSON boolean. Tato složená identita je jednoznačná v celém doloženém ročním exportu a stabilní mezi ročním a týdenním překryvem. Měna, částka, klient ani vystavil nejsou částí identity: jejich změna u stejného klíče vytvoří tvrdý konflikt. `cashbook_number`, pokud někdy přijde neprázdné, je kontext v canonical obsahu; nemění režim identity.

Canonical content: `issued_local`, `time_precision`, `movement`, `cashbook_number`, `label`, `client`, `income_minor`, `expense_minor`, `signed_amount_minor`, `currency`, `payment_form`=`CARD`, `variable_symbol`, `issued_by`, `invoice_code`, `storno_marker`. Datum importu, raw numeric `.0`, fyzická pozice a repair_code do hashe nepatří. Opravený a korektně nerozdělený tentýž klient musí mít stejný canonical hash.

**Informační hranice vstupu:** změnu polí tvořících identitu nelze bez externího neměnného ID obecně rozeznat od nové události. Specifikace proto zaručuje idempotenci stejného významového řádku a tvrdý konflikt stejného klíče; nezaručuje nemožné rozpoznání libovolné přepsané identity. Dva zcela identické řádky tohoto formátu se definují jako jeden pohyb. Dvě odlišné částky pod stejným klíčem se odmítnou; parser je nerozliší umělým pořadovým číslem. Uživatel nesmí dostat falešné tvrzení, že export obsahuje stabilní transakční ID.

### 5.6 Povinné výsledky a překryv

| Vlastnost | cashbook_year.xls | cashbook_week.xls |
|---|---:|---:|
| Fyzické řádky včetně hlavičky a footeru | 1686 | 21 |
| Běžné pohyby | 1684 | 19 |
| Kartou → nové finanční objekty v prázdné DB | 1055 | 9 |
| Z toho CZK / EUR | 298 / 757 | 1 / 8 |
| Hotově → ignorovat | 550 | 10 |
| Převodem → ignorovat | 79 | 0 |
| Footer | 1 | 1 |
| Oprava rozděleného klienta | 2 | 0 |
| Kladné / záporné karetní pohyby | 1048 / 7 | 9 / 0 |
| Karetní příjem CZK | 1 272 400,87 | 5 200,00 |
| Karetní výdaj CZK | 12 524,74 | 0,00 |
| Karetní signed saldo CZK | 1 259 876,13 | 5 200,00 |
| Karetní příjem EUR | 141 502,00 | 1 083,74 |
| Karetní výdaj EUR | 231,30 | 0,00 |
| Karetní signed saldo EUR | 141 270,70 | 1 083,74 |

Roční → týdenní: druhý import 0 nových a 9 známých finančních řádků. Týdenní → roční: druhý import 1046 nových a 9 známých. Oba současně do prázdné DB: 1055 nových, 9 duplicitních výskytů; stejný výsledek při obráceném pořadí souborů. Karetní skupiny a jejich členství zůstanou ve všech těchto scénářích beze změny. Hotovostní PPD/PVD se mohou zobrazit v původních souborech/provenance, nikdy v pracovním seznamu.


## 6. Terminál / bankovní karetní export

### 6.1 Formáty a list

CSV, XLS a XLSX mají stejný významový kontrakt. Vzor XLSX obsahuje jediný list `Xlsx file`. Při jednom viditelném listu splňujícím schéma se vybere automaticky, při více kandidátech musí uživatel vybrat list v importním dialogu; výběr není provozní konfigurace. Zvolený list se zpracuje celý. CSV podporuje UTF-8 s/bez BOM, Windows-1250 a UTF-16 LE/BE s BOM; nejprve se zkouší BOM, potom striktní UTF-8, potom CP1250. Oddělovač čárka nebo středník se určí jednoznačnou shodou celé hlavičky; více možností = chyba. RFC4180 uvozování, `""` jako escape, víceřádkové uvozované texty.

| # | Přesná hlavička | Pole | Povinná hodnota u finančního řádku |
|---:|---|---|---|
| 1 | Typ transakce | `event_class` | Ano, viz typy |
| 2 | ID Terminálu | `terminal_id` | Ano |
| 3 | ID POS | `pos_id` | Ne |
| 4 | Datum a čas vzniku | `occurred_local` | Ano |
| 5 | Čas připsání na server | `server_local` | Ne |
| 6 | Datum zaúčtování | `booked_date` | Ne; prázdné = nezaúčtováno ve zdrojovém snapshotu |
| 7 | Částka | `signed_amount_minor` | Ano |
| 8 | Cashback | `cashback_minor` | Prázdno = 0 |
| 9 | Spropitné | `tip_minor` | Prázdno = 0 |
| 10 | Měna | `currency` | Ano |
| 11 | ARN kód | `arn` | Ne |
| 12 | DCC | `dcc` | Ne; čistě textový kontext |
| 13 | Číslo karty/Číslo účtu | `masked_account` | Ne; zachovat maskování |
| 14 | Autoriz. kód | `authorization_code` | Ne; např. `001859`, `I67149` |
| 15 | Var. symbol | `variable_symbol` | Ne |
| 16 | Var. symbol 2 | `variable_symbol_2` | Ne |
| 17 | SEQ ID | `seq_id` | Ano; např. `001269002` |
| 18 | Vydavatel karty | `issuer` | Ne |
| 19 | Způsob načtení karty | `entry_method` | Ne; např. K/L, význam se neodhaduje |
| 20 | Obchodní místo | `merchant` | Ne |
| 21 | Adresa obchodního místa | `merchant_address` | Ne |

Povolené dodatečné hlavičkové aliasy: `Číslo karty / Číslo účtu` → 13; `Autorizační kód` → 14; `Variabilní symbol` → 15; `Variabilní symbol 2` → 16. Všechny ostatní významy se mapují podle přesné tabulky a společné normalizace.

### 6.2 Typy, znaménka a souhrny

| Typ po casefold | Třída | Signed amount |
|---|---|---|
| prodej | SALE | Zdrojová částka; záporná je chyba |
| storno | REVERSAL | `-abs(Částka)` |
| návrat zboží, navrat zbozi, refundace, refund, vrácení, vraceni | REFUND | `-abs(Částka)` |
| uzávěrka, uzaverka | TECHNICAL | Ignorovat před kontrolou částky/SEQ/měny |
| první buňka přesně počet transakcí:, pocet transakci:, suma částek:, suma castek: | SUMMARY | Ignorovat finančně, uchovat raw a ověřit technický součet |
| všechny buňky prázdné | BLANK | Ignorovat |
| ostatní | UNKNOWN | Odmítnout import |

Nulová finanční částka se po kontrole identity a typu ignoruje jako ZERO_AMOUNT. `Částka` je celá částka karetní transakce; Cashback a Spropitné se znovu nepřičítají ani neodečítají, ale ukládají se samostatně. DCC neurčuje účetní měnu; měnu stanoví pouze Měna. Nevytvářet transakci z řádku uzávěrky.

`Počet transakcí:` je počet všech rozpoznaných finančních a uzávěrkových řádků, bez hlavičky, prázdných řádků a footerů. `Suma částek:` je surový algebraický součet sloupce Částka před typovou normalizací; může směšovat měny a nemá finanční význam pro rekonsiliaci. Pokud jsou tyto footery přítomny, musí souhlasit s úplností exportu; rozpor je `SUMMARY_MISMATCH`. V UI se zobrazí pouze jako „Kontrola zdrojového souboru“, nikoli jako celkový příjem.

### 6.3 Přirozená identita finanční události

```text
bank_event_identity = SHA256(canonical_json([terminal_id, seq_id, event_class]))
terminal_sequence_key = [terminal_id, seq_id]  # související transakce, nikoli UNIQUE
```

Třída SALE, REVERSAL nebo REFUND je součást identity. Prodej a jeho storno se stejným terminálem a SEQ jsou dva skutečné pohyby a musí být přijaty. Stejná trojice s rozdílným obsahem je tvrdý konflikt. Částka, datum ani hash obsahu nesmějí být přidány do identity, aby se konflikt skryl. Pokud zdroj pod stejnou trojicí skutečně poskytne více rozdílných událostí bez dalšího ID, import je odmítne jako nedostatečnou identitu; nesmí hádat pořadové číslo.

Canonical content obsahuje všech 21 významových polí z tabulky: normalizovanou třídu, identifikátory, oba místní timestampy + jejich precision, datum zaúčtování, signed částku, cashback, tip, měnu a všechny kontextové texty. Odlišné datum zaúčtování nebo doplněný ARN pod známou identitou tedy znamená konflikt, nikoli tichý refresh. Původní kladná či záporná reprezentace refundace se ukládá do raw, canonical signed je vždy záporné.

### 6.4 Kontrolní vzor

Vložený `terminal.xlsx` má 88 řádků včetně hlavičky, 54 prodejů, 1 storno, 1 návrat zboží, 27 uzávěrek, 2 prázdné a 2 footerové řádky. Import vytvoří **56 finančních objektů**, z toho **42 CZK a 14 EUR**. Signed součty: **216 729,03 CZK a 1 255,10 EUR**. Rekonsiliační příspěvky mají opačná znaménka. Zdrojový footer má 83 transakcí a surový součet 220644.13; tento součet není měnově čistý.

Řádek 49: `Storno`, `M1PAXX2600`, SEQ `001269002`, EUR 80 → signed −8000. Řádek 50: `Prodej`, stejný terminál/SEQ, EUR 80 → signed +8000. Oba mají autorizaci `091991` a maskovanou kartu `532639******1644`; jde o dvě odlišné event identity. Řádek 68: `Návrat zboží`, CZK 1250 → signed −125000; kód `001859` se nesmí zkrátit na `1859`.

## 7. Booking.com CSV

### 7.1 Fyzický a hlavičkový kontrakt

UTF-8 s nebo bez BOM, čárkový oddělovač, CRLF nebo LF, standardní CSV quoting a víceřádkové uvozované buňky. Import navíc přijímá středník, pokud právě tato varianta jednoznačně splní celou hlavičku. Žádné locale systému nesmí rozhodovat o dekódování anglických dat nebo čísel.

| # | Anglická hlavička | Český alias | Kanonické pole |
|---:|---|---|---|
| 1 | Type | Typ faktury | `invoice_type` |
| 2 | Booking number | Číslo rezervace | `booking_reference` |
| 3 | Check-in | Datum příjezdu | `arrival` |
| 4 | Checkout | Checkout | `departure` |
| 5 | Guest name | Jméno hosta | `guest_name` |
| 6 | Payments service provider | Poskytovatel platebních služeb | `provider` |
| 7 | Reservation status | Status rezervace | `reservation_status` |
| 8 | Currency | Měna | `currency` |
| 9 | Payment status | Status platby | `payment_status` |
| 10 | Amount | Částka | `signed_amount_minor` |
| 11 | Payout date | Datum vyplacení částky | `payout_date` |
| 12 | Payout ID | ID platby | `payout_id` |

Payout ID označuje výplatu, nikoli jedinečný řádek. Více rezervací se stejným Payout ID jsou samostatné finanční položky. Hlavičky mohou kombinovat uvedené aliasy, pokud každý význam existuje právě jednou.

Povinné hodnoty finančního řádku: typ, Booking number (`[0-9]{6,20}`, zachovat nuly), status rezervace, měna, status platby, částka, payout date, payout ID (neprázdný text). Příjezd/odjezd, host a provider mohou být null. Při vyplněných obou datech musí odjezd >= příjezd.

### 7.2 Anglická data a finanční relevantnost

Parser explicitně podporuje `Aug 16, 2026` a všech 12 zkratek: Jan=1, Feb=2, Mar=3, Apr=4, May=5, Jun=6, Jul=7, Aug=8, Sep=9, Oct=10, Nov=11, Dec=12; měsíc bez ohledu na velikost písmen. Přijímá také ISO a české datum podle kapitoly 4. Neprovádí `locale.setlocale`, nepoužívá české `%b` k čtení angličtiny. Datum vyplacení je datum transakce pro zobrazení; příjezd a odjezd jsou pouze kontext, nikoli další finanční řádky.

Typ `Reservation` nebo `Rezervace` → `RESERVATION`. Status rezervace `ok`, `valid`, `platná`, `platna` → `OK`; `cancelled`, `canceled`, `zrušeno` → `CANCELLED`; `no-show`, `noshow`, `nedojezd` → `NO_SHOW`. Tyto poslední dva statusy samy o sobě neznamenají nulové peníze: rozhoduje stav platby a signed částka. Jsou to závazně podporované aliasy; reálné vložené řádky obsahují `Reservation`, `ok`, `Paid Online`.

Platba `paid online`, `paid`, `uhrazeno online` → `PAID`; `pending`, `unpaid`, `čeká na platbu`, `neuhrazeno` → `UNPAID`. `PAID` + známý typ a známý status rezervace + nenulová částka → importovat včetně záporné částky. `UNPAID` → ignorovat s počtem a surovou částkou v technickém souhrnu, nikdy nevytvořit krytí. Nula s jinak platnými poli → ignorovat jako ZERO_AMOUNT. Jiný typ/status nebo prázdný povinný stav → chyba celé operace. Kontrola známého schématu a statusů předchází nulovému filtru.

Znaménko Amount je autoritativní; `Reservation` ani `Paid Online` nepřevádí zápornou částku na kladnou. Částka −83.49 ve vloženém exportu tedy znamená signed −8349 a contribution +8349 EUR. Provize, DPH, kurz ani odhad hrubé ceny se nedopočítávají.

### 7.3 Identita a hashe

```text
source_identity = SHA256(canonical_json(
  [payout_id, booking_reference, currency, payout_date, invoice_type]))
payout_key = SHA256(canonical_json([payout_id, payout_date, currency]))
```

Kanonický obsah je všech 12 polí z tabulky po normalizaci. Příjezd, odjezd, host, provider a statusy tedy také podléhají detekci změny. `row_hash` pro diagnostiku je SHA256 JSON pole `[payout_id,booking_reference,currency,signed_amount_minor,payout_date,arrival,departure,invoice_type,payment_status]`; není UNIQUE identitou nahrazující source_identity. `payout_key` pouze sdružuje výplatu v kontextu, nevytváří automatickou rekonsiliační skupinu.

Dva různé řádky pod stejnou source_identity jsou konflikt i tehdy, mají-li opačné znaménko. Program nesmí vymyslet chybějící provider line ID. Vnitrozdrojové započtení Bookingu funguje mezi skutečně různými source_identity (např. jiná výplata nebo její datum).

### 7.4 Výsledky vložených CSV

| Soubor | Finanční řádky | Kladné / záporné | Měna | Signed součet |
|---|---:|---:|---|---:|
| booking_a.csv | 21 | 20 / 1 | EUR | 3 955,64 |
| booking_b.csv | 25 | 25 / 0 | EUR | 4 510,69 |
| Oba dohromady | 46 | 45 / 1 | EUR | 8 466,33 |

Opakovaný import obou vytvoří 0 nových objektů. Každý soubor má společné Payout ID pro všechny své řádky; import je nesmí sloučit na jedinou částku. Jména s diakritikou se musí zobrazit správně.

## 8. BetterHotel — úplný kontrakt čtení API

### 8.1 Připojení a autentizace

Pevná základní adresa: **`https://api.better-hotel.com/api/connector/v/1`**. Všechny níže uvedené relativní endpointy se připojují za celý tento prefix; například měny jsou `https://api.better-hotel.com/api/connector/v/1/currency`, nikoli `https://api.better-hotel.com/currency`. Implementace musí mít test přesné výsledné URL. ID v cestě se percent-encode jako jediný segment; hodnota ID nikdy nesmí změnit host ani prefix.

Všechny požadavky jsou GET s hlavičkami:

```http
Accept: application/json
X-Access-Token: <hodnota Access Token z Nastavení>
X-Client-Token: <hodnota Client Token z Nastavení>
```

Autentizace není Bearer, Basic ani OAuth. Tokeny se neposílají v query, URL nebo JSON těle. Není potřeba ručně zadávat hotel ID, tenant ID, endpoint, scope, callback ani další tajemství. Dvojice tokenů určuje dostupný hotelový kontext. HTTP klient musí odmítat redirecty a nepovolené cílové hosty, ověřovat TLS a ignorovat automatické proxy či tokeny z environmentu (`trust_env=False`). Volitelná explicitní proxy je dostupná pouze přes Nastavení; nikdy se nepřebírá skrytě z `.env`.

### 8.2 Přesná tabulka volání

| Účel | Cesta za prefixem | Query bez stránkování | Přijatá odpověď / použití |
|---|---|---|---|
| Číselník měn, test připojení | `/currency` | žádná | Kolekce currency |
| Seznam dokladů | `/invoice` | `filter[date_from]=YYYY-MM-DD`, `filter[date_to]=YYYY-MM-DD` | Kolekce invoice |
| Detail dokladu | `/invoice/{invoice_id}` | žádná | Jeden invoice; vložené položky |
| Seznam rezervací | `/reservation` | `date_from=YYYY-MM-DD`, `date_to=YYYY-MM-DD`, opakované `expand[]=reservation_source` a `expand[]=reservation_note` | Kolekce reservation |
| Detail rezervace | `/reservation/{reservation_id}` | obě `expand[]` jako u seznamu | Jeden reservation |
| Doklady rezervace | `/reservation/{reservation_id}/invoice` | žádná | Kolekce odkazů `id` nebo `invoice_id` |
| Účty rezervace | `/reservation/{reservation_id}/bill` | žádná | Kolekce odkazů `id` nebo `bill_id` |
| Detail účtu | `/bill/{bill_id}` | žádná | Jeden bill |
| Položky účtu | `/bill/{bill_id}/bill-item` | žádná | Kolekce odkazů `id` nebo `bill_item_id` |
| Detail položky účtu | `/bill-item/{item_id}` | žádná | Jeden bill item |
| Kauce rezervace | `/reservation/{reservation_id}/security-deposit` | žádná | Kolekce security deposit |
| Finanční statistiky | `/financial-stats` | `date_from=YYYY-MM-DD`, `date_to=YYYY-MM-DD` | JSON snapshot, pouze diagnostika |

U `/invoice` se nesmí zaměnit vnořený `filter[...]` za ploché parametry rezervací. Pole expand se kóduje jako dva query páry se stejným názvem, nikoli řetězec Python seznamu. Query hodnoty vždy předává HTTP knihovna jako strukturované parametry.

#### Doložitelnost HTTP kontraktu a provozní kompatibilita

Rozlišují se tři různé úrovně důkazu. Jejich názvy nesmějí být zaměněny v implementačním protokolu ani UI:

| Úroveň | Co konkrétně dokládá | Co nedokládá |
|---|---|---|
| `SOURCE_CONTRACT` | Cesty, X-Access-Token/X-Client-Token, parametry, obálky a pole skutečně používané zdrojovým HTTP klientem a synchronizací. | Že server daný request dnes přijme a vrátí požadovaný obsah pro konkrétní účet. |
| `LOCAL_CONTRACT_TEST` | Že implementace přesně posílá definované žádosti a zpracuje pozitivní/negativní fixture A.4. | Živý přístup, oprávnění účtu ani chování poskytovatele. |
| `LIVE_OBSERVATION` | Konkrétní úspěšný GET a validaci odpovědi skutečného serveru, s časem a rozsahem. | Neověřené endpointy, prázdné větve, jiné účty nebo budoucí dostupnost. |

Zdrojový podklad HTTP kontraktu je immutable revize `c71a88926bbb40bab889740900440834eb2c6916` repozitáře KájovoKarty: [config.py — base URL](https://github.com/karelmartinek-a11y/kajovokarty/blob/c71a88926bbb40bab889740900440834eb2c6916/src/kajovokarty/app/config.py), [client.py — hlavičky a stránkování](https://github.com/karelmartinek-a11y/kajovokarty/blob/c71a88926bbb40bab889740900440834eb2c6916/src/kajovokarty/infrastructure/better_hotel/client.py), [sync.py — endpointy a parametry](https://github.com/karelmartinek-a11y/kajovokarty/blob/c71a88926bbb40bab889740900440834eb2c6916/src/kajovokarty/infrastructure/better_hotel/sync.py), [dto.py — datová pole](https://github.com/karelmartinek-a11y/kajovokarty/blob/c71a88926bbb40bab889740900440834eb2c6916/src/kajovokarty/infrastructure/better_hotel/dto.py). Jde o dohledatelnost důkazu, nikoli další zadání: všechny implementačně potřebné detaily jsou přepsány do kapitoly 8. Odkazy není nutné otevřít pro implementaci. Doklad klienta není dokumentací vydanou poskytovatelem. Přísná validace konfliktů, lokální slučování projekcí a stavové protokoly v této kapitole jsou závazná pravidla aplikace; jejich přítomnost ve specifikaci sama nedokládá chování serveru.

**Součástí tohoto SSOT nejsou zachycené autentizované odpovědi BetterHotel. Provozní kompatibilita není tímto dokumentem prohlášena za ověřenou.** A.4 je výslovně syntetický lokální test. Tuto informační hranici nelze odstranit přejmenováním fixture na reálná data. Uzavřený implementační kontrakt a provedená živá integrace jsou dvě samostatné podmínky předání.

V Nastavení musí být vedle Testu připojení samostatné **Ověřit kompatibilitu BetterHotel**. Test připojení ověří pouze `/currency`; nesmí oznámit „celé API kompatibilní“. Ověření kompatibility provede výslovně spuštěný úplný sync podle 8.6 se stejnými dvěma tokeny, bez požadavku na další ID od uživatele. ID pro detail/vztahové endpointy odvodí výhradně z reálných kolekcí. Navíc u každé objevené invoice načte detail i při úplném seznamovém záznamu, aby ověřil také tuto šablonu; ostatní pravidla úplného sync platí beze změny. Validuje přesné URL/parametry, obálky, číselník, identity, slučování seznam/detail a dostupné vztahy. Nic nezapisuje do BetterHotel. Interní automatický běh při startu není dovolen.

Každá z 12 endpointových šablon tabulky 8.2 dostane stav `NOT_ATTEMPTED`, `PASS_NONEMPTY`, `PASS_EMPTY`, `UNEXERCISED` nebo `FAIL`. PASS_NONEMPTY vyžaduje alespoň jednu platnou neprázdnou odpověď a žádnou chybu této šablony v daném ověření; PASS_EMPTY znamená úspěšné platné prázdné kolekce, avšak neověřená pole entity. UNEXERCISED znamená, že platné rodičovské kolekce neposkytly žádné ID pro tuto šablonu; nesmí se vymýšlet ID ani označit ji PASS. Pro financial-stats je PASS_NONEMPTY úspěšná neprázdná JSON hodnota po odstranění obálky data, pokud existuje; prázdné {} nebo [] je PASS_EMPTY; nedokládá finanční parser, protože se ukládá raw. Celkový stav je FAILED, existuje-li FAIL, jinak PARTIAL, existuje-li jiný stav než PASS_NONEMPTY, jinak PASSED. Prázdná kolekce není chyba synchronizace. Sama o sobě nevyřazuje entity před dokončením všech bloků; po úspěšném FULL rozhoduje celá aktivní množina podle 8.6. Nezjištěný záznam zůstává historicky uložen, nikoli fyzicky vymazán.

Lokální protokol obsahuje app build a wire_contract_id=`BH-CONNECTOR-1`, čas začátku/konce, persistentní credential_revision (čítač, ne hash tokenu), connection_context_id a helper_generation_id skutečně publikovanou tímto během, jinak null; chyba doplňkových stats už publikovanou generation_id nevynuluje, rozsah a pro každou endpointovou šablonu stav, počty odpovědí/řádků, HTTP kódy, hash odpovědi a validované názvy/typy polí. Neobsahuje tokeny ani osobní raw hodnoty; raw zůstává pouze v chráněných helper snapshotech. Neověřené chybové větve retry/rate limit se nadále testují lokálně, nikoli vyvoláváním nadměrné zátěže služby. Změna tokenů invaliduje aktuální live souhrn, nehistorické protokoly. FAIL nikdy nezpůsobí tichou změnu schématu parseru. Při odlišném reálném kontraktu je výsledek explicitní API_SCHEMA/konkrétní chyba a integrace zůstává nedokončená.

### 8.3 Obálky a stránkování

Kolekce používá objekt `{data: [...], meta: {...}}`; `data` jako jediný objekt je přijato jako jednoprvková kolekce. Prázdná `data: []` je platná. Detail přijímá `{data: object}`, `{data: [object]}` s právě jedním objektem nebo přímo objekt obsahující `id`/`uuid`. Více detailových objektů znamená chybu. Odpověď obsahující pouze metadata bez detailu nesmí vymazat již uložená data; označí detail neúplným a brání nové automatické vazbě z tohoto refreshe.

U seznamů `/invoice` a `/reservation` první request přidává `count=25`. Pokud odpověď obsahuje `meta.has_more=true`, další request obsahuje stejné původní query, `count=25` a `cursor=<meta.cursor>`. Po `false` se končí. `meta.total_count` je nezáporný integer pro průběh, ne kritérium předčasného ukončení. Chybějící meta znamená nestránkovanou odpověď, nikoli pokračování odhadnuté podle délky.

Vztahové kolekce a číselník se poprvé čtou bez count podle tabulky; pokud vrátí `has_more=true`, pokračují se stejnými parametry a cursor/count=25. Na všech stránkách se ověřuje forma dat. `has_more` musí být JSON boolean; řetězec `"false"` není true ani platný stav. Další stránka bez neprázdného cursoru, opakovaný cursor nebo zacyklení ukončí běh chybou. Identita doménové entity je `(context_id, resource_type, external_id)`, identita její reprezentace navíc obsahuje `projection_kind` a `request_shape_hash`. Kontextové oddělení platí i pro raw snapshots a měnový číselník; při sloučení se pracuje pouze s projekcemi aktuálního běhu/generace téhož kontextu. Projection kind je LIST_ENTITY, DETAIL_ENTITY, RELATION_EDGE, EMBEDDED_ENTITY nebo MERGED_ENTITY; poslední je lokálně odvozená reprezentace, nikoli přijatá HTTP odpověď. Request shape zahrnuje endpointovou šablonu, expand a filtry projekce, nikoli cursor/count ani časový interval. Odkaz vztahu `{invoice_id:I1}` se porovnává jako hrana, nikoli jako neúplný invoice.

V rámci stejné reprezentace se opakované ID se stejným canonical payloadem deduplikuje. Rozdílný obsah stejné reprezentace při opakování/pages v témže běhu je API_SNAPSHOT_CONFLICT; cíleně se nový detail za účelem rozhodnutí „který je pravdivý“ nedotazuje. Celá rozpracovaná generace se neopublikuje a důkazy mají dostupnost podle 8.8; konflikt se vyhodnocuje i mezi bloky. Mezi různými reprezentacemi seznam/detail se samotné rozdílné hashe nesmějí považovat za konflikt. Sloučení je definováno následující tabulkou:

| Seznam versus detail téže entity | Výsledek |
|---|---|
| Pole v seznamu chybí a detail jej poskytne | Legitimní doplnění, žádný konflikt. |
| Pole v detailu chybí a v seznamu existuje | Zachovat pole seznamu a jeho provenance. |
| Oba poskytují stejnou hodnotu po explicitní typové normalizaci | Jedna sloučená hodnota, oba raw snapshots zachovat. |
| Oba poskytují rozdílnou explicitní hodnotu, včetně null versus neprázdná | API_SNAPSHOT_CONFLICT; žádná tichá přednost detailu. |
| Oba poskytují vnořený objekt | Totéž rekurzivně pro společné klíče; chybějící podklíče lze doplnit. |
| Oba poskytují pole/seznam | Jde o úplnou hodnotu pole, nikoli částečné doplnění; vyžadovat shodu. Pořadí se ignoruje pouze u invoice.items (po mapování aliasů) a reservation.reservation_note: prvky se řadí podle normalizovaného ID, pokud existuje, poté podle canonical JSON hashe; stejné opakované prvky se zachovají. U ostatních polí se pořadí zachová. |

Projekce se slučují podle přítomnosti klíčů ještě před doplněním výchozích null. Aliasové klíče se mapují do jednoho cílového pole dle 8.4; jejich konfliktní hodnoty jsou chyba, kromě výslovně řešené dvojice paid/payed. Metadata obálky a stránkování nejsou pole entity. Číselné entity ID 123 a textové ID `"123"` se po validní ID normalizaci rovnají; normalizace nesmí ztratit významové nuly textových ID. U peněžních polí se srovnává Decimal/minor a měna; `"50.00"` a 50 jsou stejné. Zdrojový LIST snapshot, DETAIL snapshot a sloučený MERGED_ENTITY snapshot mají každý vlastní hash; nelze první přepsat druhým. Pro MERGED_ENTITY je endpoint_template="LOCAL_MERGE" a request_shape_hash je SHA256 canonical JSON seznamu použitých dvojic [projection_kind,request_shape_hash], deduplikovaného a lexikograficky seřazeného. helper_current pro příslušný context_id/generation_id odkazuje na MERGED_ENTITY i tehdy, vznikla-li jen z jediné úplné projekce. Do sloučení se nikdy automaticky nedoplňují pole ze staršího běhu; chybějící aktuální pole se nesmějí maskovat historickou hodnotou. Neznámý datový typ či entita bez stabilního ID se neztrácí tichým filtrováním, ale zapisuje do diagnostiky chyby bloku.

### 8.4 Mapování dat

Neznámá JSON pole se uchovají v immutable raw snapshotu. Následující tabulky určují známá pole. Chybějící nepovinná hodnota je null; chybějící pomocná částka se neprezentuje jako skutečná nula. Helper částky nejsou finanční contribution ani po úspěšném parsování.

| Currency pole | Cíl |
|---|---|
| `id`, jinak `code` | externí identifikátor |
| `iso_code`, jinak `code`, jinak `name` | trim uppercase; CZK/EUR do mapy ID→ISO |

Další měny v číselníku se uchovají raw; nejsou podporované finančně. Konflikt jednoho externího ID se dvěma ISO je chyba. Žádná měna helperu se neodhaduje jako CZK, pokud chybí.

| Invoice pole | Cíl / pravidlo |
|---|---|
| `id` | Povinné externí textové ID |
| `document_uuid` | Nepovinné dokumentové UUID |
| `code`, jinak `number` | Číslo dokladu; pokud chybí, ID je pouze náhradní popisek, nikoli důkaz čísla |
| `date` | Povinný timestamp dokladu |
| `due_date`, `vat_date`, `archived` | Nepovinné timestampy |
| `paid`, `payed` | Pokud existuje paid, má přednost; jinak payed; při rozdílu obou > 1 ms diagnostika; při <= 1 ms dřívější čas |
| `currency` | ISO nebo externí ID přes currency map |
| `total`, `subtotal`, `deposit` | Decimal→minor nebo null; u print_format=3 kladné total převést na záporné |
| `pay_method`, `print_format` | Integer/null; pay_method=2 je kontext karetního dokladu, nikoli finanční důkaz |
| `exchange_rate`, `vat_exchange_rate` | Decimal text/null; nikdy finanční konverze |
| `invoice_item`, jinak `invoice_items`, jinak `items` | Vložené položky jako objekt nebo seznam |

Položka invoice: `id` nebo `uuid` (povinné), `bill_item_id` nebo `bill_item`, `signed_amount` jinak `amount` jinak `total`, `currency` nebo měna rodiče, `vat_type`, `service_from` nebo `date_from`, `service_to` nebo `date_to`; další obsah raw. Prázdné pole currency se dědí z jednoznačného rodiče, nikoli z globální výchozí měny. Rozpor měn zůstává diagnostikou helperu a znemožňuje jeho použití v jednoznačné vazbě.

| Reservation pole | Cíl / pravidlo |
|---|---|
| `id`, jinak `uuid` | Povinné UUID/ID |
| `code` | Interní číslo rezervace jako identifikátor, nikoli Booking number |
| `reservation_source`, jinak objekt `source` | `id`, `name`; název booking.com bez ohledu na case označuje Booking kanál |
| `arrival`, jinak `date_from` | Datum příjezdu/null |
| `departure`, jinak `date_to` | Datum odjezdu/null |
| `bill_id` | Odkaz na účet/null |
| `reservation_note[]` | Ze všech objektů číst text `channel`; ne pouze první poznámku |

Bill: `id`/`uuid`, `reservation_id`/`reservation_uuid` nebo identita z rodičovské URL, `currency`, `total`, `balance`/`saldo`, `is_closed`/`closed`, `is_locked`/`locked`. Boolean přijímá bool, integer 0/1 nebo casefold `true/false`, `yes/no`, `ano/ne`, `closed/open`, `locked/unlocked`; ostatní znamená neznámé/null s diagnostikou, nikoli automaticky false. Jeden reservation může mít více bill; všechny se uloží, nevytváří se výhradní vazba na první.

Bill item: `id`/`uuid`, `bill_id`/`bill_uuid` nebo rodičovská URL, `amount`/`total`, `currency` nebo jednoznačná měna účtu. Security deposit: `id`/`uuid`, reservation z URL, `amount`/`total`, `currency`, `status`. Financial stats se zachovají jako celý JSON s požadovaným obdobím, časem, hashem; aplikace z nich nevyvozuje žádnou samostatnou platbu. Rozpor ID v detailu a URL nebo v rodičovské vazbě je chyba, nikoli oprava ID.

### 8.5 Booking reference z poznámek

Pro každé `reservation_note[].channel`: html.unescape jednou, Unicode NFC, `<br>`/`<br/>`/`<br />` → LF, zbývající HTML tagy → mezera, CRLF/CR→LF, vodorovné whitespace → mezera. Nikdy renderovat jako aktivní HTML. Nad tímto normalizovaným textem vyhledat:

```regex
(?i)(Original\s*ID|Channel\s*reservation\s*id)\s*[:=]?\s*([0-9]{6,20})(?![0-9])
```

Výstup: 0 různých kandidátů = MISSING, právě 1 = CONFIRMED, více různých = CONFLICT. Opakování téhož čísla ve více poznámkách je jeden kandidát. Poslední negativní lookahead brání uříznutí delšího čísla. Uchovat raw hash, normalizovaný text, label, počáteční a koncový offset čísla v normalizovaném textu a verzi parseru. Interní reservation.code se nikdy nesmí použít jako Booking reference bez tohoto důkazu.

Automatické použití vyžaduje `source.name=booking.com` po normalizaci podle 8.4. Chybějící či jiný kanál nelze nahradit ručním rozhodnutím. Surový stav extrakce MISSING/CONFIRMED/CONFLICT zůstává odvozený jen z poznámek a nesmí se přepisovat výsledkem ruční volby.

Pro každou rezervaci a kontext existuje nejvýše jedno aktivní lokální rozhodnutí: **ACCEPT** konkrétního extrahovaného kandidáta, nebo **REJECT** použití Booking reference této rezervace pro automatiku. UI nabízí „Potvrdit tuto referenci“, „Odmítnout reference pro automatiku“ a „Zrušit ruční rozhodnutí“. REJECT je veto celé aktuální množiny, nikoli smazání jednoho kandidáta; candidate=null, accepted=false. ACCEPT má candidate z aktuální neprázdné množiny a accepted=true. Obě akce jsou dostupné i při jednom kandidátu; nelze ručně vložit nové číslo. Zrušení rozhodnutí nastaví active=false, historie a Undo zůstanou zachovány.

`candidate_set_hash` je SHA256 canonical JSON `{parser_version, channel_name, candidates}`, kde channel_name je normalizovaný casefold název kanálu nebo JSON null a candidates je deduplikovaný lexikograficky řazený seznam extrahovaných čísel. Neobsahuje časy načtení, generation_id, pořadí poznámek ani okolní text beze změny extrakce. Rozhodnutí se váže ke konkrétnímu `(context_id,reservation_id,candidate_set_hash)`. Platnost vyžaduje stejný aktuální kontext, rezervaci aktivní/complete v publikované generaci, shodný hash a u ACCEPT přítomnost vybraného kandidáta. REJECT nevyžaduje candidate. `override_valid` označuje platnost i u odmítnutí; **neznamená schválení**.

Vyhodnocení `booking_reference_decision(reservation)` je závazné v tomto pořadí; první splněná větev končí rozhodnutí:

| Pořadí | Podmínka | resolution_status / effective_candidate / dovoleno pro B |
|---|---|---|
| 1 | Jiný kontext, rezervace mimo právě publikovanou generation_id nebo neaktivní/neúplná rezervace | INACTIVE_CONTEXT_OR_ENTITY / null / ne |
| 2 | Aktivní rozhodnutí existuje, ale jeho hash nebo ACCEPT kandidát již neplatí | REVIEW_REQUIRED / null / ne; žádný automatický fallback na jediný nově nalezený kandidát |
| 3 | Aktivní platné REJECT | REJECTED / null / ne; má přednost i před surovým CONFIRMED |
| 4 | Kanál není jednoznačně booking.com | CHANNEL_BLOCKED / null / ne |
| 5 | Aktivní platné ACCEPT | MANUAL_ACCEPT / vybraný kandidát / ano |
| 6 | Žádné aktivní rozhodnutí a právě jeden kandidát, raw status CONFIRMED | AUTO_CONFIRMED / jediný kandidát / ano; override není potřeba |
| 7 | Žádné aktivní rozhodnutí a 0 kandidátů | MISSING / null / ne |
| 8 | Žádné aktivní rozhodnutí a více kandidátů | CONFLICT / null / ne |

Obsahově identický refresh v témže kontextu ponechá rozhodnutí platné. Změna kandidátů, kanálu nebo parser kontraktu vede u aktivního rozhodnutí k REVIEW_REQUIRED; uživatel musí výslovně potvrdit/odmítnout aktuální množinu nebo rozhodnutí zrušit. Staré odmítnutí se nesmí změnou poznámek tiše obejít. REJECTED a REVIEW_REQUIRED nejsou důkazem, že rezervace nepatří Bookingu; nesmějí zpřístupnit C_WEAK ani D náhradou za blokované B. Existující finanční skupiny se žádným rozhodnutím ani jeho zneplatněním nerozpojí.

### 8.6 Synchronizační algoritmus a životní cyklus entit

Synchronizace běží pouze po tlačítku „Načíst / aktualizovat BetterHotel“, případně explicitní akci „Obnovit tento detail“. Import, start aplikace, refresh tabulky ani změna filtrů ji nespustí. Tlačítko otevře souhrn rozsahu a spustí worker; jednotlivé API řádky se nepotvrzují.

#### Rozsah a autorita úplného načtení

Výchozí počáteční datum je minimum z dnešního data minus 365 dní, všech importovaných cashbook dat, bankovních dat, Booking příjezdů a Booking payout dat. Konec je maximum z dneška a vyplněných importovaných odjezdů/dat. Pro tentýž connection_context_id se rozsah navíc rozšíří o celé období poslední úspěšně publikované FULL generace; již pokrytá historie se posunem dneška ani změnou velikosti bloků nesmí zúžit. Kontexty se při výpočtu historického pokrytí nemísí. Uživatel může v Nastavení zadat dřívější počátek; pozdější počátek nesmí skrýt starší importované řádky. Období se čte po nepřekrývajících se blocích, standardně 7 kalendářních dní, včetně obou krajů. Neexistuje pevný historický účetní cutoff.

**Autoritou přítomnosti entity je sjednocení celého úspěšného FULL běhu, nikoli jednotlivý časový blok.** Datumové filtry jsou parametry requestu. Aplikace neodhaduje, podle kterého interního data server rezervaci zařadil, a nesmí odmítnout platnou vrácenou entitu pouze proto, že její arrival leží mimo právě dotazovaný blok. Všem finančně použitelným helperům přísluší connection_context_id a jedna publikovaná generation_id podle 8.8.

Každý FULL běh založí novou generaci ve stavu STAGING. `V_run` je množina jednoznačných klíčů (context_id,resource_type,external_id) úplných entit získaných v tomto běhu; `E_run` je množina potvrzených vztahových hran mezi nimi. Kořeny grafu jsou currency a entity skutečně vrácené úplnými seznamy `/invoice` a `/reservation` napříč **všemi** bloky. Ostatní entity se smějí stát aktivními jen jako úplné entity dosažené z těchto kořenů přes vztahy a vložené položky doložené v témže běhu. Financial-stats nejsou kořen ani finanční důkaz. Dříve známé ID se samo od sebe do V_run nepřidává.

1. Zaznamenat neměnný kontext, credential_revision, plán všech bloků a přejít do REFRESHING. Načíst úplný currency číselník pro tuto generaci; chybějící měnové ID se nedoplňuje z jiného kontextu ani ze starší generace.
2. Pro každý blok načíst všechny invoice stránky. Je-li seznamový invoice úplný, detail není nutný; při chybějícím čísle, datu či měně doplnit detail. Režim Ověřit kompatibilitu načítá detaily navíc dle 8.2.
3. Načíst všechny reservation stránky s oběma expand. Pro každou rezervaci načíst detail, úplné vztahy invoice a jejich potřebné detaily, bill a bill items včetně detailů a security deposits. Cache stejné reprezentace má klíč (context_id,generation_id,resource_type,external_id,projection_kind,request_shape_hash). LIST nikdy nenahradí požadovaný DETAIL pouhou shodou ID.
4. Doklad získaný přes aktuální vztah rezervace se zahrne i mimo rozsah seznamu dokladů. Stejně se zahrnou úplné bill, bill_item, invoice_item a security_deposit dosažené přes aktuální graf. Vztah bez úplné cílové entity není použitelný; selhání požadovaného detailu znamená selhání povinné části. Shodné reprezentace se deduplikují, skutečné konflikty se vyhodnotí podle 8.3 i napříč bloky.
5. Po každém dokončeném bloku uložit snapshots, observations, kandidátní entity/hrany a checkpoint do STAGING generace krátkou transakcí. **Nezměnit publikovaný graf ani jeho aktivní množiny.** GUI může ukázat zvlášť označený průběžný náhled běhu; párování, hledání aktuálních helperů a export aktuálního grafu jej nesmějí zaměnit za publikovaná data.
6. Až uspějí všechny povinné bloky, měny, detaily a vztahy, ověřit uzavřenost V_run/E_run, kontext a úplnost pokrytí. Připravit SEALED generaci: všechny entity V_run active=1, všechny potvrzené hrany E_run active=1; dřívější známé entity téhož kontextu mimo V_run active=0, inactive_reason=NOT_OBSERVED_IN_FULL_SYNC. Jejich poslední snapshot zůstává dostupný jako historie. Staré hrany mimo E_run jsou inactive; aktivní hrana musí mít oba konce aktivní a úplné ve stejné generaci. Nový kontext přitom nikdy nekopíruje historické entity jiného kontextu.
7. Jednou atomickou krátkou transakcí ověřit předpodmínky a přepnout helper_state.published_generation_id na SEALED generaci, označit ji PUBLISHED, zvýšit evidence_epoch a revision, převzít její pokrytí a nastavit READY. Příprava rozsáhlého grafu proběhla předem; publikace není postupné přepisování viditelných entit. Pád před přepnutím ponechá starý graf; po commitu je vidět celý nový graf. Starší publikované generace zůstávají neměnné.
8. Načíst financial-stats pro celé období jako doplňkovou diagnostiku. Jejich chyba či zrušení této doplňkové fáze neodvolá READY již publikované povinné části. Souhrn oddělí úspěch helper grafu od doplňkové chyby a endpointového compatibility výsledku podle 8.2.

Souhrn uvádí kontext/generaci, rozsah, počet dokončených bloků, přidané, změněné, stejné, nově nezjištěné a znovu pozorované entity, změny vztahů, requesty a chyby. „Nově nezjištěné“ nikdy neoznačuje jako „smazané v BetterHotel“: seznam dokládá nepřítomnost v načteném rozsahu a oprávnění, nikoli příčinu.

#### Zmizelé, přesunuté a znovu nalezené entity

| Pozorování v novém FULL běhu | Výsledek po úspěšné publikaci |
|---|---|
| Rezervace R byla v bloku A, nyní chybí v A a je vrácena v B | Jedna aktivní R se stejnou kontextovou identitou a sloučeným aktuálním obsahem; žádné vyřazení při dokončení A. Její nové vztahy pocházejí z celého aktuálního běhu. |
| Dřívější R není v žádném dokončeném bloku ani dosažitelná z aktuálního grafu | R active=0, starý snapshot zachovat; žádný nový důkaz přes R. Vztahy incidentní k R nesmějí být aktivní. |
| Invoice I chybí v `/invoice`, ale je znovu získána úplným detailem přes aktuální `/reservation/R/invoice` | I zůstane aktivní, je-li R aktuální a vazba úplná; nepřítomnost jen v seznamu dokladů tuto skutečnou aktuální vazbu nepřebije. |
| Potomek ztratí jednu vazbu, ale má jinou aktuální cestu od kořene | Potomek zůstane aktivní; zanikne pouze nedoložená hrana. Je-li zároveň sám seznamovým kořenem, nepotřebuje příchozí hranu. |
| Bill/item/deposit ztratí poslední aktuální cestu od kořene | Potomek active=0, historický snapshot zachovat; neaktivní rodič nesmí ponechat aktivní osiřelý podgraf. |
| Jedna povinná stránka nebo blok selže | Nic se nevyřazuje podle neúplné absence. Publikovaný graf zůstane totožný, helper_state=STALE; generace se nepublikuje. |
| Stejné externí ID se po předchozí absenci znovu vrátí v témže kontextu | Stejná doménová identita, nová aktivní generace a nový nebo shodný snapshot; staré finanční skupiny se nemění. |
| Entita se přesunula mimo celý dotázaný rozsah a není získána aktuální vztahovou cestou | active=0 jako NOT_OBSERVED_IN_FULL_SYNC. Aplikace netvrdí smazání ani si nedovymýšlí nový blok. Vrátí se až po skutečném pozorování v dalším úplném běhu, jehož rozsah ji pokryje, nebo přes doloženou aktuální vazbu. |
| Všechny povinné seznamy jsou platné a prázdné | Úplný prázdný graf s případným číselníkem; všechny dřívější obchodní entity téhož kontextu jsou inactive. READY znamená ověřenou úplnost načtení, ne existenci použitelné rezervace. |

Při dotazech pro nové párování se neaktivní entity ani jejich identifikátory nepoužijí jako alternativní protějšek, pozitivní důkaz ani důkaz nepřítomnosti Booking vazby. Historická skupina vždy ukazuje svůj uložený kontext/generaci/snapshots, i když aktuální entita již není aktivní. Fyzické mazání historie není součástí synchronizace.

#### Checkpoint a cílená obnova

Checkpoint zahrnuje context_id, credential_revision, generation_id, neměnný plán rozsahu, parser kontrakt a dokončené kolekce; potvrzuje pouze dokončení části STAGING běhu. Resume je možné jen se stejnými hodnotami a beze změny publikovaného předchůdce. Naváže na stejnou generaci, sloučí všechny její bloky a publish provede až při úplnosti celého původního plánu. Nedokončený blok se načte znovu celý; jeho částečné odpovědi z předchozího pokusu mohou zůstat diagnosticky uložené, ale jsou vyřazeny z kandidátního V_run/E_run a ze srovnávání reprezentací dokončených bloků. Dokončené bloky mají svůj validovaný checkpoint; žádná částečná kolekce se neoznačí za dokončenou. Pokud předpodmínky neplatí, běh označit ABORTED a založit nový FULL; staré staging výsledky se do nového běhu nekopírují. Každý nově zahájený FULL kontroluje celý určený rozsah znovu. Hlavičku `X-Modified: <UTC RFC3339>` adaptér umí, ale normativní FULL ani cílený refresh ji neposílají: pro rozhodnutí absence je nutná úplná odpověď, nikoli delta.

Cílené „Obnovit tento detail“ pracuje pouze s ID z aktuálního kontextu. Nad dříve READY grafem založí DETAIL generaci jako logickou kopii posledního publikovaného grafu; načte požadovaný detail a jeho úplné autoritativní odchozí kolekce dostupné v tabulce 8.2 včetně detailů potomků. Pro invoice jde o vložené invoice items, pro reservation o invoice/bill/security-deposit, pro bill o bill-item; bill-item má vlastní GET detail bez samostatné odchozí kolekce. Invoice-item nemá vlastní GET endpoint: aktualizuje se přes jediného známého aktivního rodiče invoice a jeho vložené položky. Security-deposit se aktualizuje úplnou `/reservation/{id}/security-deposit` kolekcí jediného známého aktivního rodiče; absence vybraného potomka v této úplné kolekci odstraní jeho hranu a přepočítá dosažitelnost. Chybějící/nejednoznačný aktivní rodič vede k API_DETAIL_REQUIRES_FULL_SYNC. Neexistující `/invoice-item/{id}` nebo `/security-deposit/{id}` se nikdy nevymýšlí. Currency a financial-stats se neobnovují tlačítkem detailu, pouze svými popsanými operacemi. Nové odkazy z vložených položek smějí použít jen cíl již aktivní v této generaci nebo cíl ověřený GET v téže obnově. Když kontrakt neposkytuje potřebný GET/vztah k ověření rodiče či cíle, refresh skončí API_DETAIL_REQUIRES_FULL_SYNC, bez publikace, stav STALE a UI nabídne FULL.

DETAIL přepíše pouze nově úplně načtené entity a odchozí sady; jiné ověřené sady převezme ze svého publikovaného předchůdce. Po nahrazení hran znovu spočítá dosažitelnost od nezměněné množiny seznamových kořenů a vyřadí osiřelé potomky. Nesnímá absenci z nenavštívených časových bloků. Dříve neaktivní seznamový kořen nelze samotným GET znovu aktivovat; jeho aktivaci musí doložit FULL seznam nebo aktuální vztahová cesta. Cílený GET takové neaktivní entity pouze uloží raw náhled, generaci nepublikuje, předchozí READY obnoví a nabídne FULL. Při rodičovském konfliktu, chybě detailu nebo neúplné kolekci zůstane starý publikovaný graf a stav přejde do STALE. HTTP 404 je zde chyba čtení, nikoli autoritativní pokyn k vymazání entity.

Při předchozím STALE/UNAVAILABLE se úspěšný cílený GET ukládá pouze pro označený náhled; nepublikuje novou generaci a nezpřístupní žádný nový automatický důkaz. Při předchozím READY a úplné validní DETAIL změně se celá generace publikuje atomicky stejným přepnutím pointeru jako FULL, zvýší epoch a zachová doložené celkové pokrytí. Všechny převzaté entity/hrany jsou pořád ze stejného kontextu a mají výslovnou vazbu na publikovaného předchůdce; pole nově načtené entity se starým payloadem nedoplňují podle 8.3. Importované finanční řádky, členství, jejich rozdíly a historické důkazy se těmito kroky nikdy nemění.

### 8.7 Časové limity, retry a chyby

Výchozí timeout 30 s pro connect/read/write/pool, celkový čas jednoho HTTP pokusu nejvýše 120 s. Retry 3 znamená nejvýše 4 pokusy. Síťová chyba/timeout nebo HTTP 500/502/503/504: po pokusech prodlevy 0,5; 1; 2 s + jitter 0–0,2 s. HTTP 429 respektuje Retry-After jako sekundy nebo HTTP-date; čekání je přerušitelné, při požadovaném čekání nad 60 s běh skončí informací o omezení, nesmí zkusit předčasný request. Při chybějícím/neplatném Retry-After čekat 1 s.

HTTP 401/403: žádný retry, srozumitelná výzva k ověření obou tokenů v Nastavení. Ostatní 4xx, 3xx, neplatný JSON a nesplněné schéma: žádný retry maskující chybu. Obvyklé odpovědi musí být HTTP 200; 204 či prázdné tělo je neúplná odpověď. Neznámý endpoint se nenahrazuje hádanou cestou. Jedna sekvenční HTTP fronta, token bucket 2 requesty/s, capacity 10; hodnoty jsou technické výchozí parametry, nikoli tvrzení o smluvním limitu poskytovatele.

Zrušení se kontroluje před každým requestem, mezi stránkami a nejvýše po 100 ms čekání. Právě běžící synchronní request může doběhnout do svého timeoutu, ale UI už ukazuje „Ruším“. Log obsahuje endpointovou šablonu, HTTP status, dobu a correlation ID, nikoli tokeny, plný query s osobními údaji nebo neanonymizované error body.

### 8.8 Kontext připojení a použitelnost helperů

#### Oddělení připojení

`connection_context_id` (v tabulkách zkráceně `context_id`) je lokální UUID4, nikoli hotel ID z API, hash tokenu nebo údaj vyplňovaný uživatelem. Prázdná instalace založí jeden CURRENT kontext bez tokenů ve stavu UNAVAILABLE. Program nepředpokládá, že dvě dvojice tokenů patří stejnému hotelu; proto každá skutečná změna uloženého Access nebo Client Token, včetně odstranění, atomicky:

1. Označí dosavadní kontext RETIRED. Jeho snapshots, grafy, coverage, references, overrides, compatibility protokoly a historické finanční důkazy zůstanou oddělenou historií.
2. Zvýší persistentní credential_revision o 1 a založí **nový** CURRENT context_id. Přepne helper_state na tento kontext, published_generation_id=null, evidence_epoch=0, status=UNAVAILABLE a vyprázdní aktuální coverage/projekce a cache. Do nového kontextu nepřenese žádný helper snapshot, vztah, currency map, rozhodnutí ani checkpoint.
3. Atomicky uloží novou dvojici tokenů chráněnou DPAPI, stav kontextů a bezpečnou auditní událost. Selhání kteréhokoli zápisu vrací celou změnu. Odstraněné/nahrazené tajemství není součást historie kontextu.

Skutečná změna je rozdíl přesných uložených hodnot po vstupní validaci; porovnání proběhne jen v paměti, bez ukládání/zalohování hashů tokenů. Opětovné uložení naprosto stejné dvojice je no-op, kontext ani revision nemění. Přechod tokeny A→B→A vytvoří tři různé kontexty; starý A se automaticky nereaktivuje ani neslouží jako cache. Pouhý Test připojení neuloženými tokeny žádný kontext nemění. Kontext nemá uživatelsky zadávaný identifikátor a nejde o další povinné nastavení.

Identita helper entity je **(context_id,resource_type,external_id)**. Stejné I1/R1 v jiném kontextu jsou jiné entity, i když mají stejný obsah, kód faktury nebo Booking číslo. Všechny hrany, poznámky, reference, coverage, merge, deduplikace, request cache, fulltext helperů a kandidáti mají explicitní kontext a generaci; overrides mají kontext a reservation_id a svou platnost vždy ověřují proti explicitní publikované generaci; žádný join nebo fallback jen podle external_id není přípustný. Finanční importy nemění své identity a existující finanční skupiny se při změně kontextu nerozpojí; jejich helper důkazy nadále odkazují na historický kontext. Nová automatika však smí číst helpery pouze z aktuálního publikovaného grafu.

Každý synchronizační nebo refrešovací HTTP job nese context_id, credential_revision a generation_id. Samostatný diagnostický Test připojení není job zapisující helper graf a nemá publication oprávnění. Před přijetím výsledku, zápisem staging dat a zejména před publikací se znovu kontrolují proti aktivnímu kontextu. Opožděný výsledek starého jobu je API_CONTEXT_CHANGED, nepublikuje se a **nesmí změnit stav novějšího kontextu** ani jeho cache. Změny tokenů používají výhradní mutační bránu a při běžící operaci se řadí do fronty podle 10.3; tato kontrola zůstává nutná i po zrušení a obnově procesu.

Obnova zálohy vždy založí čerstvý CURRENT kontext s prázdným published_generation_id a UNAVAILABLE. Všechny obnovené kontexty zůstanou RETIRED historií. Nová credential_revision je 1 + maximum z hodnot před obnovou a v obnovených kontextech, aby se nemohla zaměnit generace opožděného requestu. Na stejném počítači lze zachovat současné DPAPI tokeny dle 15, ale žádný obnovený helper graf se tím nestane aktuálním. Na jiném profilu se tokeny zadávají znovu v UI. Teprve FULL načtení vytvoří první publikovaný graf nového kontextu.

#### Stav a publikovaná generace

Immutable raw snapshot, publikovaný graf a oprávnění použít graf jako **nový automatický důkaz** jsou odlišné věci. Autoritou je singleton helper_state se svým kontextem, published_generation_id a stavem. Všechny čtecí projekce aktuálních helperů jsou omezeny oběma ID. Starší publikované generace a STAGING náhledy jsou pouze výslovně označená historie/průběh. Neexistuje volba „použít stará data navzdory chybě“.

| Událost | Stav po události | Publikovaný graf / nový helper důkaz |
|---|---|---|
| Prázdná instalace, skutečná změna tokenů nebo restore | UNAVAILABLE | V novém kontextu žádná publikovaná generace; historie jiných kontextů nesmí být použita. |
| Zahájení FULL nebo cíleného refresh | REFRESHING | Dosavadní publikovaný graf zachovat pro zobrazení; nový helper důkaz do dokončení zakázán. |
| Celá povinná část FULL uspěla a generace byla publikována | READY | Pouze aktivní úplné entity/hrany nové publikované generace; nezjištěné entity jsou neaktivní dle 8.6. |
| Chyba/cancel/pád před dokončením povinné části | STALE | Published pointer a obsah starého grafu beze změny, nový helper důkaz zakázán. STAGING výsledek se nepoužije. |
| Úspěšná úplná DETAIL publikace při předchozím READY | READY | Nová odvozená generace, vyšší epoch, zachované úplné časové pokrytí, upravená dosažitelnost. |
| Úspěšný cílený GET neaktivní entity při předchozím READY | READY | Jen označený raw náhled; stejná published generace a epoch, entita zůstává neaktivní. |
| Úspěšný cílený GET při předchozím STALE/UNAVAILABLE | Předchozí STALE/UNAVAILABLE | Jen raw náhled; použitelnost obnoví výhradně úspěšný FULL. |
| Chyba/cancel samotných financial-stats po publikaci povinné části | READY | Graf zůstane platný; doplňková chyba se vykáže odděleně, nikoli jako PASSED compatibility protokol. |

Přechod do REFRESHING proběhne transakčně před prvním requestem. Zaznamenat previous_status, předchozí published_generation_id, plánovaný rozsah, operation_id a revision. Zrušení před prvním requestem již zahájené obnovy vede do STALE. Samotný Test připojení `/currency` je diagnostika a stav helperů nemění ani při chybě. Ověřit kompatibilitu naopak provádí FULL a řídí se touto tabulkou. Evidence_epoch roste jen při publikaci grafu v jednom kontextu; při změně kontextu začíná od nuly, proto se nikdy neporovnává bez context_id.

#### Přesné predikáty

`helper_usable(chain)` je **strukturální** predikát: helper_state.status=READY; kontext je CURRENT a shodný s kontextem běhu a credential_revision; celý řetězec je v helper_state.published_generation_id; všechny požadované entity jsou active=1 a complete=1, všechny použité hrany active=1 a úplné; potřebné období importovaných finančních řádků je úplně pokryté v téže publikované generaci. Konkrétní helper entita získaná mimo interval seznamu úplným detailem přes aktuální vztahovou cestu je doložena touto cestou; její vlastní datum se nemusí vejít do seznamového intervalu a samo o sobě řetězec neblokuje. Žádný override se v tomto obecném predikátu povinně nevyžaduje.

Pro Booking pravidlo B platí navíc:

```text
booking_chain_usable(chain) = helper_usable(chain)
  AND chain jednoznačně určuje invoice a reservation dle 9.1
  AND booking_reference_decision(reservation).resolution_status
      IN {AUTO_CONFIRMED, MANUAL_ACCEPT}
  AND booking_reference_decision(reservation).effective_candidate
      == reference párovaného Booking řádku
```

Tedy **potvrzená jednoznačná reference bez aktivního override, nebo platné přijímající ruční rozhodnutí**, vždy při správném kanálu a s předností odmítnutí/požadavku na nové rozhodnutí podle 8.5. `override_valid=true` s accepted=false znamená platné veto, nikoli použitelný důkaz. Více různých cest, byť každá sama platná, se nadále posuzuje jako nejednoznačnost dle 9.1–9.3.

Pro C_WEAK a kontrolu absence B před D se používá strukturální helper_usable plus jejich konkrétní pravidla. Neaktivní/chybějící entita, jiný kontext, REJECTED, REVIEW_REQUIRED, MISSING či CONFLICT u Booking kanálu nejsou prokázanou nepřítomností Booking vazby. Tato nejistota slabé/náhradní párování blokuje. Žádná alternativa podle samotného helper_current.complete nebo samotného credential_revision nesmí obejít context_id, generation_id, active a globální stav.

B a D se při neplatné globální dostupnosti nespouštějí. C se v tomto stavu smí spustit jen se silným VS důkazem; A je na helperu nezávislé. Ruční finanční seskupení zůstává dostupné. Historický kontext je viditelně označen „Historické připojení — pouze pro zobrazení důkazu“, neověřený aktuální graf „Pomocná data nejsou ověřena pro nové automatické párování“ a jednotlivá neaktivní entita „V úplném načtení nezjištěna — nepoužitelná pro nové párování“.

Existující finanční skupiny, členství, částky, status a uložený důkaz se žádným přechodem nemění. Chyba jediného povinného bloku blokuje celý nový graf; resume může obnovit READY pouze publikací úplné generace stejného kontextu za podmínek 8.6. PARTIAL endpointový live protokol s platnými prázdnými větvemi neznamená neúplný helper graf; jeho použitelnost určuje tento stavový a datový kontrakt, nikoli název compatibility výsledku.

## 9. Párování a ruční skupiny

### 9.1 Důkaz pokladna → doklad → rezervace

Primární vazbou je přesná shoda extrahovaného cashbook.invoice_code s invoice.code/number, po NFKC + casefold. VS se nesmí zaměnit za celý FA kód; kontroluje se podle kapitoly 5.4. Pro ostatní kontextová hledání se z cashbook `label` a `variable_symbol` vyhledávají přesné hodnoty známých invoice.code/number. Label se rozdělí na maximální tokeny znaků Unicode písmena/číslice a `/ _ -`; porovnání se provede po NFKC + casefold. Samostatná čísla lze porovnat pouze s přesným známým číslem dokladu, nikoli libovolně s invoice interním ID. Proměnný symbol je porovnán jako celé neprázdné pole. Žádné částečné hledání `123` v `1234`, fuzzy shoda, substring jména či substring v názvu klienta. Věta „úhrada dokladu FA2026001“ tedy dovolí token FA2026001. Celý label se navíc porovná jako celek pro kódy s mezerou.

Množina všech odkazovaných invoice ID musí obsahovat právě jeden doklad. Více různých čísel v label, rozpor s VS nebo duplicitní kód více dokladů znamená nejednoznačnost. Invoice→reservation vychází výhradně z úspěšně načtené `/reservation/{id}/invoice` vazby; jedna invoice přiřazená více rezervacím se automaticky nepoužije. Reservation→Booking reference musí projít booking_reference_decision dle 8.5: AUTO_CONFIRMED bez aktivního override nebo MANUAL_ACCEPT; platné REJECT a neplatné aktivní rozhodnutí mají přednost a vazbu blokují. Celý řetězec musí splnit booking_chain_usable podle 8.8. Všechna ID/kódy se hledají pouze mezi aktivními úplnými entitami aktuálního kontextu a publikované generace; historická entita ani shodný kód z jiného kontextu nepřidává kandidáta. Částka helper invoice není částkou finanční povinnosti a nemusí být stejná jako jednotlivá částečná karetní úhrada.

### 9.2 Automatické párování — deterministický rozsah

Spouští se pouze tlačítkem „Spustit automatické párování“, nad celou aktuální databází bez ohledu na filtry. Nezahrnuje ruční skupiny, jejich potomky ani již vyřízené kořeny. Automatika může spojovat pouze volné samostatné zdrojové listy. Otevřené agregáty používá uživatel ručně; není dovoleno rozebírat jejich členy pro automatiku.

Automatika vytvoří snapshot dostupných listů, helper_state, potlačení a nastavení. Pravidla A→B→C→D provádí v opakovaných kolech až do ustálení dle 9.3; nejde o jediný průchod. Před každým commitem znovu validuje aktuální vlastnictví, revision a důkaz. Žádný výběr podle prvního řádku, náhodného UUID nebo nejvyššího skóre při shodě.

**A. Jednoznačné storno terminálu.** Volná SALE a REVERSAL se stejným terminal/SEQ, stejnou měnou a opačnými přesnými signed částkami se spárují, pokud čas storna není před prodejem a nepřekračuje 7 místních kalendářních dní, shoduje se neprázdná maskovaná karta i autorizace a neexistuje další možný pár. Výsledkem je nulová BANK_CARD skupina. Samostatný REFUND se podle podobnosti automaticky nepřiřazuje k prodeji. Toto pravidlo mimo jiné uzavře doložený prodej/storno EUR 80 z přílohy B.

**B. Booking přes doklad.** Pro každou použitelnou Booking reference dle booking_reference_decision a měnu sestavit množinu volných cashbook listů se stejným jednoznačným helper řetězcem splňujícím booking_chain_usable a množinu volných Booking řádků téže reference/měny. Najít přesné minimální nulové kombinace obsahující alespoň jeden cashbook a alespoň jeden Booking. Tím se pokrývá 1:1, 1:N, N:1 i N:N se společnou rezervací. Neomezuje se payout datum na ±7 dní, protože výplata může následovat později. Čas slouží jako zobrazený kontext, rezervaci dokládá reference.

**C. Přímá banka.** Pravidlo má dvě podfáze `C_STRONG` a `C_WEAK` v tomto pořadí; obě vyžadují stejnou měnu, stejnou nenulovou signed částku a rozdíl místních kalendářních dat nejvýše nastavené okno (výchozí 7 dní).

Pro bankovní řádek vytvořit množinu `bank_vs` z neprázdných normalizovaných Var. symbol a Var. symbol 2; duplicitní stejná hodnota se počítá jednou. Dva různé bankovní VS jsou dvě deklarované reference, nejsou samy o sobě chybou. Silná hrana existuje právě tehdy, když neprázdný cashbook VS patří do bank_vs. Pokud jsou cashbook VS i bank_vs neprázdné a jejich průnik je prázdný, jde o rozpor a nevznikne ani slabá hrana. Žádný jiný „společný silný identifikátor“ se v C neodhaduje; cashbook kontrakt neposkytuje autorizaci ani ARN.

`C_STRONG`: nad všemi dostupnými cashbook/bank listy sestavit celý bipartitní graf silných hran. **Spojit pouze hranu, jejíž oba vrcholy mají stupeň právě 1. Toto platí i při shodném VS.** Dvě různé banky se stejným VS, částkou a přípustným datem → cashbook má stupeň 2 → žádnou nespojit. Dva cashbook k jedné bance → totéž. Nejbližší datum, nejnižší SEQ ani pořadí řádků shodu nerozhoduje.

`C_WEAK`: po commitech jednoznačných silných párů použít zbývající volné listy, které nemají **žádnou** incidentní silnou hranu v této podfázi; nejednoznačnou silnou větev nelze obejít slabou shodou. Slabá hrana splňuje částku/měnu/čas a nemá výše definovaný rozpor VS, ale nemá silný důkaz. Navíc vyžaduje helper_state READY a přípustný helper kontext: cashbook nemá použitelný Booking řetězec, jeho datum má úplné pokrytí invoice/reservation v aktuálním kontextu/publikované generaci a všechny nalezené dokladové a rezervační vazby jsou aktivní, úplné a bez konfliktu. Chybějící invoice, nejednoznačný doklad či rezervace, neznámý kanál nebo konfliktní Booking reference slabou shodu blokují. Úplná prázdná sada rezervací doložená synchronizací, nebo jednoznačná rezervace s explicitně jiným kanálem než booking.com, naopak dovoluje prokázat nepřítomnost Booking řetězce. Rezervace kanálu booking.com bez použitelné reference, včetně REJECTED a REVIEW_REQUIRED, C_WEAK blokuje; ruční odmítnutí není důkaz jiného platebního kanálu. I zde se potvrzují pouze hrany stupně 1 na obou koncích v celém slabém grafu. Všechny disjunktní hrany se plánují ze stejného snapshotu podfáze a commitují bez lokálního odstraňování nejednoznačnosti pořadím zápisu.

Ověřený Booking řetězec vylučuje C_WEAK, nikoli C_STRONG. Toto pravidlo priorit neprovádí tolerance, skórování ani převody měn. Potlačené silné kandidáty zůstávají při výpočtu stupně a vyloučení slabé větve viditelné; pouze se necommitují. Potlačení nesmí vytvořit falešnou jednoznačnost konkurenčního kandidáta.

**D. Vnitrozdrojové Booking započtení.** Dva volné Booking řádky různé source_identity se stejnou Booking reference, měnou a přesně opačnými signed částkami lze spojit, pokud je tento pár oboustranně jediný; musí také platit, že žádný z jeho členů nemá kandidáta pravidla B. READY je nutná podmínka; pokud existuje volný cashbook s chybějícím/neaktivním/neúplným/konfliktním helper řetězcem stejné měny nebo s blokovanou Booking referencí včetně REJECTED/REVIEW_REQUIRED, nelze absenci jeho vazby na danou reference dokázat a D se pro tuto měnu nespustí. Úplný jednoznačný řetězec s jiným kanálem či jinou reference tuto překážku nevytváří. Jiné kombinace uvnitř zdroje nebo napříč bankou a Bookingem zůstávají plně dostupné ručně.

### 9.3 Jednoznačnost kombinací a výpočetní limity

Minimální nulová kombinace nemá vlastní menší podmnožinu splňující stejné pravidlo. Rozlišuje se množina zdrojových ID, nikoli jen částek; dvě různé platby 50 jsou dva kandidáti. Pro všechny kandidáty pravidla B vznikne graf překryvů: hrana mezi dvěma kandidáty existuje, sdílejí-li list. Automaticky lze potvrdit jen kandidáta, který nesdílí žádný list s jiným přípustným kandidátem. Překrývající se kandidáti se ponechají celé nevyřízené. Nesnažit se rozbít nejednoznačnost pořadím commitů.

Automatická kombinace B má nejvýše 6 listů celkem, nastavitelně 2–10. Na jednu reference/currency komponentu platí nejvýše 40 vstupních listů a 100 000 prozkoumaných stavů. Při překročení limitu se z dané komponenty neuzavře nic; důvod `AUTO_SEARCH_LIMIT` a ruční práce zůstane dostupná. Algoritmus musí umět záporné částky a nesmí prořezat větev pouze proto, že mezisoučet překročil cíl. Neúplně prohledanou množinu nelze označit za jednoznačnou. Limity jsou viditelné v Nastavení / Pokročilé a nikdy neomezují ruční skupinu.

#### Kola do pevného bodu

Po celou dobu auto běhu drží OperationManager **logický výhradní zámek finančních a důkazových mutací**. Není to dlouhá SQLite transakce: GUI může číst, měnit filtr a pracovní výběr. Importní commity, ruční finanční příkazy, helper publikace/přechody helper_state, override, potlačení, nastavení ovlivňující matching a změny tokenů se řadí do fronty až po běhu. Synchronizace, která již je REFRESHING, se před zahájením automatiky musí dokončit/zrušit; automatika se spustí teprve nad konečným stavem. Žádné skryté přečtení jiné generace helperu uprostřed kola.

Jedno kolo:

1. Z aktuálně volných listů vytvořit kompletní kandidátní graf A a commitnout pouze přípustné disjunktní jednoznačné skupiny.
2. Z obnovované projekce volných listů vytvořit všechny kandidáty B a jejich překryvové komponenty. Commitnout pouze nejednoznačností nezatížené kandidáty. Limity platí pro celou komponentu, ne pro první nalezenou shodu.
3. Z nově volných listů provést C_STRONG a C_WEAK podle jejich dvou grafů.
4. Před D znovu read-only spočítat existenci B kandidátů na stavu po C. Pokud hledání B komponenty narazí na limit, jeho dotčené Booking listy jsou pro D zablokované: „nenalezeno kvůli limitu“ není prokázaná absence. Pak provést D.
5. Jestliže v A/B/C/D vznikla alespoň jedna skupina, začít další celé kolo A→B→C→D. Pokud celé kolo vytvořilo 0 skupin, algoritmus dosáhl pevného bodu a končí.

V každé podfázi se jednoznačnost počítá před jejími commity nad celou přípustnou množinou. Plánované skupiny jsou disjunktní; průběžné odstraňování soupeře v rámci podfáze nesmí vytvořit dodatečný pár. Nová jednoznačnost vyvolaná jiným pravidlem se smí využít až v jeho řádně přepočítané podfázi/kole. Řazení pro deterministické prohledávání je `(source_kind,source_identity)` lexikograficky; referenční enumerace B začne search_states=1 za kořen a pro velikosti k=2 až max_combination navštěvuje všechny k-prvkové kombinace indexů v lexikografickém pořadí. Každá navštívená kombinace zvýší čítač o 1, i když nemá oba zdroje nebo nemá nulovou sumu. Kandidátem je jen nulová kombinace s oběma zdroji, která neobsahuje již nalezenou menší přípustnou nulovou kombinaci. Překročení max_search_states ruší všechny kandidáty příslušné reference/currency množiny. Optimalizovaná implementace musí zachovat přesně tento logický čítač a výsledek; vlastní počet CPU kroků jej nenahrazuje. Žádné náhodné heuristiky ani závislost výsledku na časovém limitu CPU.

Každá vytvořená skupina spotřebuje alespoň 2 volné listy a nepřidává nové volné listy. Pro N0 vstupních volných listů tedy existuje nejvýše floor(N0/2) kol s pokrokem a jedno závěrečné kolo bez pokroku. Obecný libovolný limit počtu kol není povolen. Limitem ukončené komponenty se v dalším kole znovu zkoumají, pokud se jejich vstupní množina změnila; beze změny lze použít deterministický memoizovaný výsledek. Limit nikdy neopravňuje neúplnou kombinaci označit za jednoznačnou.

Pevný bod je definován vůči uloženému nastavení, dostupnému helper stavu a potlačením, nikoli vůči všem matematicky možným kombinacím. Souhrn uvádí počet kol, `reached_fixed_point`, počty komponent s limitem a neplatnými helpery. Běh s deterministicky přeskočenými komponentami může dosáhnout fixed_point, ale nesmí tvrdit „všechny možnosti vyčerpány“. Druhé úspěšné spuštění po dosažení fixed_point bez změny listů/vlastnictví, helper stavu, potlačení a matching nastavení vytvoří 0 skupin. Po předčasném zrušení/pádu/chybě tato záruka neplatí a resumed běh smí dokončit další skupiny.

Před commitem jednotlivé auto skupiny transakce `BEGIN IMMEDIATE` ověří dostupnost, stejné měny, hashe, přesnou nulu, helper revision/stav a platnost kandidátní komponenty. Neočekávaná změna přes výhradní bránu znamená STALE_STATE a ukončení běhu s `reached_fixed_point=false`; nesmí se jen přeskočit komponenta a oznámit úspěšné ustálení. Jedna skupina je atomická; při zrušení běhu již hotové skupiny zůstanou a právě rozpracovaná se nevytvoří. Výsledek uvede analyzované listy, nově vyřízené listy, vytvořené skupiny, zbývající pracovní kořeny a počty důvodů, vše po měnách. Nesmí porovnávat počet listů a počet agregátů pod stejným neoznačeným KPI.

Ruční rozpojení nebo Undo vzniku auto skupiny vytvoří potlačení jejího důkazového fingerprintu. Fingerprint je SHA256 canonical JSON objektu `{rule_id, leaves, evidence_hash}`; leaves je seznam `[source_kind,source_identity,content_hash]` řazený podle prvních dvou polí. evidence_hash zahrnuje jen kanonické hodnoty použitých identifikátorů, helper entit/hran a skutečně použitého přijímajícího override; při použití helper důkazu zahrnuje také context_id jako součást jeho doménové identity, u pravidel bez helperu pouze použité zdrojové důkazové hodnoty. Nezahrnuje čas načtení, sync run ID, helper generation_id/evidence_epoch, revision, operation ID ani skupinové UUID. Identický refresh v témže kontextu nemění otisk; skutečná změna tokenů zakládá jiný kontext a tedy jiný helper důkaz. Pravidla A a C_STRONG context_id do důkazu nezahrnují, protože helper nepoužívají. Technická obnova identického obsahu proto otisk nezmění; revision/epoch se zvlášť používá pouze k validaci souběhu.

V detailu je „Znovu povolit automatické spojení“. Potlačení se vztahuje na přesný otisk a neodstraňuje kandidáta z posuzování nejednoznačnosti ani z kontroly B kandidátů v D; zabraňuje pouze jeho commitu. Jiný skutečný důkaz může mít jiný otisk. Vznik/Undo/Redo potlačení se řídí přesnými pravidly 9.6.

### 9.4 Ruční příkazy

Pracovní výběr je perzistentní sada ID+revision aktuálních nevyřízených kořenů; lze ji doplňovat napříč obrazovkami a filtry. Výběr není finanční členství. Skrytí filtry jej nesmí odstranit. UI vždy ukazuje počet vybraných mimo právě viditelný filtr. Před potvrzením se výběr znovu ověří. Zastaralá položka se označí a akce se odmítne, nikoli tiše vypustí.

| Příkaz | Předpoklady | Atomický výsledek |
|---|---|---|
| Vytvořit skupinu | >=2 různých nevyřízených kořenů jedné měny | Nový MANUAL rodič, děti zachovány; nula = Vyřízeno, jinak Nevyřízeno |
| Spárovat / uzavřít | Totéž + přesný rozdíl 0 | Tentýž doménový příkaz; nenulový výběr nelze označit za vyřízený |
| Přidat do skupiny | Otevřená kořenová skupina + >=1 další nevyřízený kořen stejné měny | Přidat přímé děti, zvýšit revision, přepočítat; žádné rozploštění podskupin |
| Rozpojit nadřazené párování | Zvolený objekt má aktivního rodiče | Rozložit jeho přímého rodiče na všechny přímé děti; vnořené podskupiny zůstanou |
| Rozložit skupinu | Zvolená aktivní kořenová skupina | Deaktivovat její přímá členství, skupinu označit DISSOLVED, děti se stanou kořeny |
| Upravit poznámku | Aktivní skupina a známá revision | Změnit pouze volitelnou poznámku, do 10 000 znaků; prázdná povolena |
| Zobrazit důkaz | Existující nebo historická skupina | Read-only výpis stromu, jedinečných listů a součtu |

Rozložení vnořené skupiny je zakázáno, dokud se explicitně nerozpojí její nadřazené párování; UI nabídne tuto cestu. Tím se nemění vnitřek aktivního rodiče skrytým příkazem. Uzavřená skupina se pro úpravu členů nejprve rozloží; poznámku lze upravit přímo. Neexistuje „odpojit jediné dítě a nechat neplatného rodiče s jedním členem“.

Pro vytvoření nevyřízené skupiny není povinný komentář ani zvláštní schvalovací stav. Po úspěchu se spotřebované objekty odeberou z pracovního výběru, ostatní zůstanou; uživatel dostane krátkou zprávu s ID skupiny a rozdílem. Drag-and-drop mezi výběrem a skupinou používá stejné příkazy, stejný náhled a stejné validační podmínky jako tlačítka.

### 9.5 Undo/Redo

Povinně podporovat vytvoření skupiny, přidání členů, rozložení/rozpojení, změnu poznámky a helper rozhodnutí ACCEPT/REJECT/zrušení. Kompenzace helper rozhodnutí se váže na jeho context_id/reservation_id a revision; v RETIRED kontextu je odmítnuta UNDO_CONFLICT, nesmí zasáhnout stejně pojmenovanou rezervaci aktuálního kontextu. Po korektním Undo se platnost obnoveného rozhodnutí znovu odvozuje od aktuální candidate_set_hash; historická shoda sama nezaručuje platnost. Undo provádí nový auditovaný kompenzační příkaz; nesmaže historii. Nevrací import, synchronizaci, export ani obnovu zálohy. Příkaz obsahuje before/after snapshot relevantních objektů, revision preconditions a inverse payload. Pokud od té doby jiný příkaz změnil dotčené členství/revision, odmítnout `UNDO_CONFLICT`; nesmí se odebrat list z jiné skupiny. Redo je opět validovaný doménový příkaz, ne přehrání syrového SQL. Nová významová mutace po Undo vyprázdní redo větev, její historie zůstane. Významovou mutací pro tuto větev je změna finančních objektů/členství/poznámky, helper obsahu/override, potlačení nebo nastavení. Samotný auditní zápis, běh auto s 0 skupinami, export, změna UI filtru či výběru redo větev nevyprázdní. Revision preconditions se kontrolují i tehdy, když redo větev zůstala dostupná.

### 9.6 Potlačení automatiky jako součást vratného příkazu

Potlačení není vedlejší zápis mimo Undo/Redo. Každý mutační command, který je vytváří/mění, obsahuje `suppression_before` a `suppression_after` pro všechny dotčené fingerprinty: stav ABSENT/ACTIVE/INACTIVE, revision a command_id, který stav naposledy změnil. Stejná transakce zapisuje členství, lifecycle skupiny, potlačení i audit. Failure/Undo conflict vrátí vše, včetně potlačení. Revision je monotónní a při Undo se nevrací na starší číslo; obnovuje se sémantický stav, nové revision se uloží jako předpodmínka Redo.

| Akce | Skupina / členství | Potlačení |
|---|---|---|
| Ruční rozpojení auto skupiny G s otiskem F | G DISSOLVED, uvolnit přímé děti | Uložit předchozí stav F, nastavit ACTIVE, navýšit revision. |
| Undo tohoto rozpojení | Obnovit G a její členství, jen pokud listy stále dostupné | Obnovit přesný předchozí sémantický stav F; předchozí ABSENT se vede jako neaktivní tombstone, nevytváří aktivní zákaz. |
| Redo tohoto rozpojení | Znovu rozpojit G | Znovu ACTIVE pro přesně původní F, nikoli otisk novějšího helperu. |
| Undo vytvoření auto skupiny | Deaktivovat vytvořenou skupinu a členství | Nastavit ACTIVE pro její uložený F, aby další automatika nevrátila právě odvolanou akci. |
| Redo vytvoření auto skupiny | Obnovit přesný historický strom po validaci vlastnictví/měny/nuly | Vrátit sémantický stav potlačení před příslušným Undo, obvykle INACTIVE/ABSENT. Nejde o nové auto hledání; historický helper důkaz se nepřepočítává. |
| Znovu povolit automatické spojení | Finanční data beze změny | Nastavit F INACTIVE; samotná akce nespustí automatiku. Undo vrátí předchozí ACTIVE; Redo opět INACTIVE. |

Jestliže F změnil jiný příkaz po snapshotu kompenzované akce, Undo/Redo skončí UNDO_CONFLICT stejně jako při změně členství. Už existující potlačení se nesmí bez důkazu zrušit. Rozpojení MANUAL skupiny nevytváří nové F: obnoví se jen potlačení, které daný příkaz výslovně měnil. Nová běžná mutace po Undo uzavře redo větev; aktuální potlačení tím samo nemizí. Obnovená historická auto skupina se neprezentuje jako nově provedené live párování a její původní důkaz zůstane zachován.

## 10. Datový model a invarianty persistence

### 10.1 Technologie a tabulky

Použít SQLite se zapnutým `foreign_keys=ON` na každém spojení, `journal_mode=WAL`, `synchronous=FULL`, `busy_timeout=5000`, STRICT tabulkami. Jediná aplikace píše do lokální DB; každý worker má vlastní spojení. Žádné síťové sdílení SQLite souboru. Migrace jsou očíslované, transakční a součástí distribuovaného programu; před změnou schématu vznikne ověřená záloha. Novější nepodporované schéma se nesmí automaticky downgradovat ani inicializovat jako prázdné.

ID interních objektů je UUID4 v lowercase hex bez pomlček. Externí ID se ukládá jako text. Časy technických událostí jsou UTC RFC3339 se 6 desetinnými místy a Z. `revision` je integer >=1, přičítá se při každé významové mutaci. Zdrojové finanční řádky mají neměnnou revision 1; vlastnictví se ukládá samostatně.

| Tabulka | Povinná pole a klíče |
|---|---|
| `schema_migration` | version INTEGER PK, applied_at, app_build, checksum |
| `setting` | key TEXT PK, value_json valid JSON, revision; žádné otevřené tokeny |
| `secret` | key TEXT PK, encrypted_blob BLOB, protection=`DPAPI_USER`, updated_at |
| `operation` | id PK, type, state, started_at, heartbeat_at, finished_at nullable, progress_current/total nullable, safe_error_json, correlation_id, recovery_json |
| `source_file` | id PK, sha256 UNIQUE, original_name, bytes BLOB, byte_size, created_at |
| `import_run` | id PK/FK operation, parser_version, totals_json, row_counts_json, selected_sources_json |
| `import_file` | PK(run_id,file_id,sheet_name), FKs import_run/source_file, input_mode EXTERNAL_FILE/STORED_SNAPSHOT, original_run_id nullable, authoritative_snapshot_hash, original_name, header_map_json, counters_json |
| `financial_source` | id PK, kind enum CASHBOOK_CARD/BANK_CARD/BOOKING, source_identity, canonical_json, content_hash, local_date, occurred_at_utc nullable, time_precision, signed_amount_minor, currency, primary_identifier, description nullable, created_at; UNIQUE(kind,source_identity) |
| `source_occurrence` | run_id/file_id/sheet/row_start, row_end >= row_start, source_id nullable, disposition, repair_code nullable, raw_cells_json, raw_types_json; PK(run_id,file_id,sheet,row_start); zdrojová provenance, ne pracovní objekt |
| `cashbook_detail` | source_id PK/FK, cashbook_number nullable bez UNIQUE, invoice_code, storno_marker, všechna cashbook pole kapitoly 5 |
| `bank_detail` | source_id PK/FK, terminal_id, seq_id, event_class a ostatní pole kapitoly 6; UNIQUE(terminal_id,seq_id,event_class) |
| `booking_detail` | source_id PK/FK, payout_key, payout_id, booking_reference a další pole kapitoly 7; UNIQUE source_identity v rodiči |
| `work_object` | id PK, type SOURCE/GROUP, source_id UNIQUE nullable FK, currency, lifecycle ACTIVE/DISSOLVED, revision; CHECK právě SOURCE má source_id |
| `reconciliation_group` | object_id PK/FK work_object, method AUTO/MANUAL, note nullable, created_at, updated_at, evidence_json; stav a rozdíl odvozené z listů |
| `membership` | id PK, parent_id FK group, child_id FK work_object, active 0/1, created_by_command FK, ended_by_command nullable FK, created_at, ended_at; parent != child |
| `command` | id PK, type, method AUTO/MANUAL/SYSTEM, before_json, after_json, suppression_before_json, suppression_after_json, inverse_json, expected_revisions_json, compensates_id nullable FK, state APPLIED/UNDONE, created_at |
| `audit_event` | id PK, operation_id nullable FK, command_id nullable FK, type, object_refs_json, before_json, after_json, amounts_by_currency_json, method AUTO/MANUAL/IMPORT/SYSTEM, note nullable, timestamp |
| `helper_context` | id PK, status CURRENT/RETIRED, credential_revision UNIQUE, created_at, retired_at nullable; právě jeden CURRENT; žádné historické tokeny |
| `helper_generation` | id PK, context_id FK, credential_revision, kind FULL/DETAIL, predecessor_id nullable FK stejného kontextu, state STAGING/SEALED/PUBLISHED/ABORTED, operation_id FK, plan_json, graph_hash nullable, evidence_epoch nullable, created_at, sealed_at nullable, published_at nullable |
| `helper_snapshot` | id PK, context_id FK, resource_type, external_id, projection_kind, request_shape_hash, endpoint_template, payload_json, content_hash, fetched_at, sync_run_id; UNIQUE(context_id,resource_type,external_id,projection_kind,request_shape_hash,content_hash) |
| `helper_observation` | id PK, context_id/generation_id FKs, operation_id, block_key, request_index, snapshot_id FK stejného kontextu, observed_at, origin LIST/DETAIL/RELATION/EMBEDDED; provenance každého skutečného přijetí i při opětovném použití shodného raw snapshotu |
| `helper_current` | PK(context_id,generation_id,resource_type,external_id), snapshot_id FK stejného kontextu, revision, active 0/1, complete 0/1, root_observed 0/1, inactive_reason nullable NOT_OBSERVED_IN_FULL_SYNC/NO_ACTIVE_ROOT_PATH, local_search_text; generační projekce, nikoli neomezený aktuální pohled |
| `helper_link` | id PK, context_id/generation_id FKs, from_type/from_id, relation, to_type/to_id, active 0/1, complete 0/1, snapshot_id FK stejného kontextu; UNIQUE(context_id,generation_id,from_type,from_id,relation,to_type,to_id) |
| `helper_reference` | id PK, context_id/generation_id FKs, reservation_id, snapshot_id FK stejného kontextu, candidate nullable, label nullable, start_offset/end_offset nullable, parser_version, status MISSING/CONFIRMED/CONFLICT; více kandidátů/původů povoleno |
| `helper_override` | PK(context_id,reservation_id), candidate nullable, candidate_set_hash, accepted 0/1, active 0/1, command_id FK, revision; ACCEPT vyžaduje candidate, REJECT má candidate=null; kontextový tombstone po zrušení |
| `sync_coverage` | PK(context_id,generation_id,resource_type,range_start,range_end), successful_run_id, completed_at, complete 0/1; epoch a aktuálnost určeny publikovanou generací; DETAIL výslovně přebírá coverage předchůdce |
| `helper_state` | singleton id=1, context_id FK CURRENT, published_generation_id nullable FK téhož kontextu, status UNAVAILABLE/REFRESHING/READY/STALE, previous_status nullable, evidence_epoch >=0, credential_revision, revision, operation_id nullable, planned_scope_json, last_full_success_at nullable, failure_code nullable |
| `api_compatibility_run` | id PK/FK operation, context_id FK, helper_generation_id nullable FK stejného kontextu, wire_contract_id, app_build, credential_revision, range_start/end, status NOT_ATTEMPTED/PARTIAL/PASSED/FAILED, started_at, finished_at nullable |
| `api_compatibility_endpoint` | PK(run_id,endpoint_template), state dle 8.2, response_count, item_count, status_codes_json, response_hashes_json, field_types_json, error_codes_json |
| `import_diagnostic` | id PK, run_id FK, file_id nullable FK, input_mode, sheet nullable, row_start/end nullable, severity ERROR/WARNING/INFO, code, column_key nullable, raw_value_json nullable, identity nullable, source_id nullable, field_diff_json, message, created_at |
| `auto_suppression` | fingerprint PK, command_id FK poslední změny, active 0/1, revision >=1, created_at, updated_at; neaktivní tombstone pro logicky ABSENT přípustný |
| `saved_filter` | id PK, name UNIQUE, scope, filter_json, sort_json, created_at, updated_at, revision |
| `view_state` | view_key PK, columns_json, sort_json, scroll_anchor_id nullable, revision |
| `work_selection` | object_id PK/FK, expected_revision, position UNIQUE; žádná finanční částka navíc |

Doménová source identity a content hash mají jedinou implementaci sdílenou preflightem a commitem. Zdrojový BLOB je trvalý, takže lze kdykoli ukázat původní řádek i znovu uložit originál. Známý řádek může mít novou technickou `source_occurrence` odkazující na existující source_id; nesmí dostat nové source/work_object ID. Ignorované řádky mají source_id=null a nikdy se neobjeví mezi finančními objekty.

Helper tabulky se nikdy nečtou jako globální množina bez kontextu a generace. Aktuální read repository vynucuje `context_id=helper_state.context_id AND generation_id=helper_state.published_generation_id`; automatický důkaz navíc active/complete a READY. Historické repository přijímá explicitní dvojici a je read-only. helper_current/helper_link/helper_reference/sync_coverage představují úplné generační projekce: STAGING se může měnit, SEALED/PUBLISHED jsou obsahově neměnné. Staré entity a hrany se fyzicky nevyřazují z historické generace; jejich active=0 patří až projekci následujícího grafu. Přenesené neaktivní entity mohou zachovat poslední snapshot a reference pro zobrazení, ale nikdy nejsou součást V_run ani helper_usable.

Pro FULL se seznamové root_observed odvozuje jen z aktuálních LIST observations, ne z data entity nebo předchozího grafu; pro DETAIL se převezme množina kořenů z publikovaného předchůdce. Úplnost entity znamená splnění povinných polí a dokončení všech jejích požadovaných kolekcí v dané generaci. graph_hash je SHA256 canonical JSON {context_id,entities,links,coverage}: entities je seznam {resource_type,external_id,content_hash,active,complete,root_observed,inactive_reason}, links seznam {from_type,from_id,relation,to_type,to_id,active,complete,snapshot_hash}, coverage seznam {resource_type,range_start,range_end,complete}; každá sada je řazena lexikograficky podle svých identifikačních klíčů. Neobsahuje generation UUID, časy, revision, override ani group data. Generační revision entity navazuje na předchůdce stejného kontextu/identity a zvyšuje se při změně obsahu, active nebo complete; nové identity začínají 1. Neměnnost starší generace tím není porušena.

Každý automatický skupinový evidence_json s použitím helperů ukládá `helper_provenance={context_id,generation_id,evidence_epoch,entities,links,reference_decision}`. entities obsahuje seřazené objekty {resource_type,external_id,snapshot_id,content_hash}, links obsahuje {from_type,from_id,relation,to_type,to_id,snapshot_id}; reference_decision je {resolution_status,effective_candidate,candidate_set_hash,override_command_id} nebo null u strukturálního důkazu bez reference. Při AUTO_CONFIRMED je override_command_id=null. Při hashování důkazu se z override používají pouze accepted, candidate a candidate_set_hash; command_id/revision nejsou obsahovým důkazem. Všechny historické snapshot odkazy zůstanou rozlišitelné po změně kontextu. U důkazu bez helperů je helper_provenance=null. Fingerprint používá obsahové podmnožiny podle 9.3, nikoli celou tuto technickou provenance.

### 10.2 Povinné databázové ochrany

```sql
CREATE UNIQUE INDEX one_active_parent
ON membership(child_id) WHERE active = 1;
CREATE INDEX membership_parent_active ON membership(parent_id, active);
CREATE INDEX source_currency_date ON financial_source(currency, local_date, id);
CREATE INDEX source_kind_identity ON financial_source(kind, source_identity);
CREATE INDEX booking_reference_lookup ON booking_detail(booking_reference);
CREATE INDEX bank_sequence_lookup ON bank_detail(terminal_id, seq_id);
```

Trigger před INSERT/UPDATE aktivního membership odmítne: neaktivní dítě/rodiče, rodiče typu SOURCE, rozdílné měny, self-reference, již vlastněné dítě a cyklus. Cyklus se testuje rekurzivním CTE z potomků navrhovaného dítěte; výskyt rodiče znamená ABORT. Trigger před UPDATE/DELETE financial_source a detailových source tabulek odmítne změnu/mazání; migrace nesmějí použít výjimku k přepsání finančního významu. `currency` má CHECK IN CZK/EUR a peněžní pole CHECK typeof=integer a limit kapitoly 3.

Skupinový rozdíl a stav jsou odvozené, nikoli volně nastavitelné sloupce. Případná cache/projekce se při každé změně invaliduje a není autoritou pro commit. Transakční služba před commitem ověří >=2 děti každé aktivní skupiny, úplnost všech source subtypů, unikátnost listů a soulad měn; rollback při nesplnění. Vnější UI nesmí provádět SQL. Kritická pravidla jsou v DB tam, kde to SQLite umí okamžitě, a společně v jedné doménové transakční bráně pro vícekrokové invarianty.

Kromě finančních ochran musí UNIQUE partial index zajistit jediný CURRENT helper_context. Složené FK/triggery vynucují shodu kontextu generace, snapshotu a obou konců každé helper hrany; reference/override nesmějí mířit do jiného kontextu. Publikace odmítne neúplný plán, jinou credential_revision, neuzavřený aktivní graf a aktivní hranu k neaktivní/neúplné entitě. PUBLISHED obsah nelze UPDATE/DELETE; nové načtení zapisuje novou generaci. Context switch, změna secret a invalidace current pointeru jsou jedna transakce.

Při create: vložit command s předpodmínkami, group/work_object a všechna členství; ověřit strom; vložit audit; commit. Při dissolve: uzamknout transakci, ověřit kořen/revision, deaktivovat přímá členství, lifecycle DISSOLVED, zapsat inverse/audit, commit. Členství se fyzicky nemaže. Finanční řádky se nikdy nesmažou jako důsledek dissolve.

### 10.3 Konzistence a souběh

Každý mutační příkaz předává ID, očekávané revision včetně dotčených potlačení/helper_state a correlation ID. Zastaralý požadavek vrátí `STALE_STATE` s aktuálními objekty; UI obnoví náhled a požaduje nové explicitní spuštění akce. Vznik skupiny z pracovního výběru neprobíhá přes staré částky uložené v UI. DB lock se nikdy nedrží přes HTTP, čekání na uživatele nebo export souboru.

Jeden lokální proces na datový adresář: při spuštění použít nativní zámek a lokální IPC pro aktivaci existujícího okna. Druhá instance nesmí vytvořit jiné skryté datové úložiště. Import, auto matching, obnova a přesun dat se serializují; čtení UI může běžet souběžně. Helper sync může provádět síťovou část souběžně s read-only GUI. Současně může běžet nejvýše jeden helper FULL/DETAIL; nový refresh/resume má předpodmínku stejného kontextu a published předchůdce. S auto během se změny helper_state a publikace nesmějí překrývat: používají výhradní logickou bránu dle 9.3; fyzické DB transakce jsou krátké. Čekání na lock je zobrazené a přerušitelné; nelze nekonečně opakovat mutaci.

Při startu ověřit schéma a SQLite quick_check; při chybě otevřít zotavovací UI s obnovou zálohy a diagnostikou. Nikdy nepřepsat poškozenou DB novou prázdnou. Po pádu se rozpracované operace označí INTERRUPTED; stav zdrojů a skupin plyne z commitnutých transakcí, nikoli z procent progress baru.

## 11. Obrazovky a ovládání

### 11.1 Jednotná struktura aplikace

Levá navigace: Nevyřízené, Vyřízené, Importy a BetterHotel, Pomocná data, Vyhledávání, Sestavy, Audit, Nastavení. Horní lišta: fulltext, Importovat, Načíst BetterHotel, Spustit automatické párování, indikátor běžících operací. Spodní perzistentní lišta: pracovní výběr, počet položek, zdrojové badge, součty a rozdíl zvlášť CZK/EUR, skupinové akce. Prázdná databáze ukáže vysvětlení a přímé tlačítko importu, nikoli demonstrační finanční data.

Žádná hlavní obrazovka nesmí izolovat zdroje do oddělených front. Filtrovaný pohled podle zdroje je jen projekce téhož objektového modelu. Technické interní stavy se ukazují v průběhu operace/auditu; finanční uživatelské stavy jsou pouze Nevyřízeno a Vyřízeno, s doplňkem Skupina, Automaticky nebo Ručně.

### 11.2 Nevyřízené

Jedna virtualizovaná tabulka všech aktivních nenulových kořenů a volných listů, napříč CZK/EUR a všemi třemi zdroji. Výchozí řazení podle místního data vzestupně, potom stabilního ID. Sloupce: Stav; Objekt (položka/skupina); Zdroje; Datum/čas; Hlavní identifikátor; Popis/host/klient; Počet listových členů; Strana; Částka; Měna; Rekonsiliační rozdíl; Booking reference; Doklad FA; Variabilní symbol; Důvod nevyřízenosti; Poznámka.

Položka používá své místní datum, skupina interval min–max dat listů (řadicí klíč minimum), ID skupiny s prefixem G a zkráceným interním ID. List má počet členů 1, skupina počet jedinečných listů. Badge skupiny je množina zdrojů, nikoli jeden odhadnutý zdroj. U více referencí/dokladů se zobrazí počet a tooltip/detail s úplným seznamem.

KPI počítaná z celého nevyřízeného seznamu před filtrem: počet kořenů; počet jednotlivých cashbook/bank/Booking kořenů; počet skupin; `potřeba_krytí(currency)=SUM(max(root_difference,0))`; `přebytek_krytí(currency)=SUM(max(-root_difference,0))`. Čtyři částkové KPI jsou oddělené CZK/EUR. Vedle toho může UI zobrazit stejně definované „Ve filtru“. Nikdy nesmí neoznačeně zaměnit globální a filtrované hodnoty nebo vzájemně odečíst skupiny, které uživatel nespojil.

### 11.3 Vyřízené a detail skupiny

Vyřízené obsahují aktivní nulové kořenové skupiny, datum vytvoření, metodu, měnu, počty zdrojů/listů, poznámku, ID a rozdíl 0. Detail skupiny je společný pro otevřené, uzavřené i historické skupiny: strom přímých dětí; plochý seznam všech jedinečných listů; částky signed/contribution; součet; helper vazby a důkaz; audit. Změna kontextu helperu se ukáže vedle uloženého důkazu vzniku, nepřepisuje jej. Historická DISSOLVED skupina je read-only a má odkaz na aktuální stav dětí.

Rozpojení zobrazí náhled přímých dětí, které budou uvolněny, a zachovaných podskupin. Potvrzení je jedna akce bez povinného důvodu. Detail musí vždy umožnit kopii ID, export důkazu a otevření původních řádků.

### 11.4 Importy a BetterHotel

Tři samostatná tlačítka typů importů s file pickerem a drag-and-drop; možnost společné operace s více soubory a seznamem typu/listu. Po výběru se spustí pouze preflight, po potvrzení commit. Průběh uvádí soubor, fyzický řádek, zpracováno/celkem, krok a možnost zrušení. Chyby se zobrazují tabulkově se všemi zjištěnými řádky; export chyb je read-only sestava import_errors s přesnými datovými sadami; CSV se předává jako ZIP dle 14.5. Zobrazit opravy `SPLIT_CLIENT_ENTITY` i footer varování a skutečné počty forem úhrady.

Historie importů uvádí čas, zdroj, jméno/hash souboru, list, parser kontrakt, výsledné počty a součty po měnách. Neobsahuje „dokončit dávku“. „Zopakovat“ explicitně zvolí STORED_SNAPSHOT dle 4.1, zobrazí uložené source_file.id/název/hash a nečte původní externí cestu; pokud uživatel chce nový export, volí EXTERNAL_FILE a vybírá nový soubor. Snapshot musí být k dispozici i po smazání originálu.

BetterHotel panel ukazuje stav tokenů pouze „vyplněno/nevyplněno“, poslední úspěšné načtení, pokrytí dat, rozpracované/neúplné bloky a Test připojení. Klik na Načíst API nikdy současně neprovádí auto párování. Zrušený nebo neúplný běh nesmí být zeleně označen jako úplný úspěch.

### 11.5 Pomocná data a hledání protějšků

Tabulky dokladů, rezervací, účtů, položek a kaucí jsou pro identifikaci. Výchozí pohled obsahuje jen aktivní entity aktuálního kontextu a publikované generace. Přepínač „Zahrnout nezjištěné entity“ zobrazí neaktivní položky se stavem a časem posledního pozorování; „Historické připojení / generace“ dovoluje jen read-only prohlížení explicitně zvolené historie. Aktuální a historická shoda ID se nikdy neslije do jednoho řádku. Aktualizace starého kontextu, jeho override a použití pro nové kandidáty jsou zakázány; UI žádnou historickou entitu automaticky nepřesměruje do nového kontextu. Uživatel může otevřít JSON jako bezpečný prostý text, zobrazit vazby, čísla, datum/částku/měnu a aktualizovat jednotlivý detail přes GET. „Otevřít související doklad/rezervaci“ znamená lokální detail, ne odhadnutou webovou URL BetterHotel. Pokud dokumentové PDF není v kontraktu, aplikace neslibuje stažení originálního PDF.

Dialog „Najít možné protějšky“ zobrazí volné kořeny stejné měny, jejich částky, data, identifikátory a vysvětlení shody. Přepínače časového rozsahu 7/14/30 dní/všechno, výchozí 7, nemění finanční data. Ruční hledání nemusí splnit automatické důkazy ani časové okno; uživatel vidí rozdíl a může vytvořit otevřený agregát. Měnový zákaz platí vždy. Kandidáti nejsou další pracovní objekty a nezabírají zdrojové řádky.

### 11.6 Datové mřížky a fulltext

Každá hlavní tabulka umožní přesun/sloučení nastavení sloupců, skrýt/zobrazit, změnu šířek, stabilní víceklíčové řazení (Shift+klik), Ctrl+klik/Shift výběr, kopírování hodnot a řádků, zachování scroll/focus při obnově. Částky se řadí numericky, data chronologicky, ID textově. Nastavení pohledu je perzistentní, dostupné i reset z Nastavení. Ctrl+A vybere všechny řádky aktuálního výsledku po filtru, ne pouze načtenou stránku; UI předá množinu ID, nikoli jen viditelné widgety.

Filtry se kombinují AND mezi různými poli, OR uvnitř vícevýběru téhož pole. Pole: měna; zdroj obsahuje libovolný/všechny vybrané; stav; položka/skupina; strana; přesná signed částka nebo zbývající částka skupiny; rozsah částky; datum od/do (u skupiny průnik intervalu); důvod; FA/PPD/PVD; Booking reference; payout ID; SEQ; terminal; autorizace; ARN; VS; rezervace. Prázdný filtr neomezuje. Částkový filtr bez měny se aplikuje na číslo každého řádku, nikdy se nepřepočítává; uživatel vidí měnu výsledku.

Centrální fulltext hledá v číslech pokladních dokladů, FA, interních ID, Booking reference, payout ID, hostech/klientech, label, VS/VS2, terminal/SEQ, ARN/autorizaci, poznámkách skupin a pomocných rezervacích. Textové hledání je case-insensitive a accent-insensitive, ale původní text a identifikátory zůstávají zachovány. Tokeny oddělené mezerou se kombinují AND; text v uvozovkách je přesná normalizovaná fráze. Neuzavřená uvozovka vyvolá inline chybu, ne SQL chybu. ID hledání podporuje celý literal i prefix, včetně počátečních nul. SQL parametry se vždy bindují, LIKE `%`/`_` v uživatelském literálu se escapují.

Vyhledání listu uvnitř skupiny vrátí aktivní kořen a zvýrazní nalezeného člena v detailu; nesmí vytvořit druhý dashboard řádek listu. Globální hledání může zahrnout i vyřízené/historii/helper, rozlišuje je typem a stavem. Přidání helperu nebo historického objektu do finančního výběru je zakázané s důvodem. Filtr ani hledání nemění členství, data, stavy nebo volitelnou poznámku.

Uložený filtr má jméno, rozsah obrazovky, serializovaný filtr a řazení; uložit, přejmenovat, přepsat s náhledem, odstranit. Vymazání filtru nezruší pracovní výběr. Filtry neobsahují syrové SQL.

### 11.7 Jednotný registr akcí

Registr `ActionSpec(id,label,shortcut,allowed_types,predicate,disabled_reason,handler)` je jedinou autoritou povolených akcí. Používají ho menu, toolbar, kontextové nabídky, detail, klávesnice, fulltext i drag-and-drop. Handler znovu validuje doménu; disabled UI není bezpečnostní hranice.

| Akce | Kde / předpoklad | Klávesa |
|---|---|---|
| Otevřít detail | Každý existující objekt | Enter |
| Přidat/odebrat pracovní výběr | Nevyřízený kořen | Ctrl+Space |
| Vyčistit pracovní výběr | Globálně; bez změny dat | Ctrl+Shift+Space |
| Vytvořit skupinu / Spárovat | Platný homogenní výběr; spárovat jen nula | Ctrl+M otevře náhled, Ctrl+Enter potvrdí |
| Přidat do skupiny | Otevřená kořenová skupina a volné kořeny | Z menu |
| Rozpojit rodiče | Člen skupiny | Delete po náhledu |
| Rozložit skupinu | Aktivní kořenová skupina | Shift+Delete po náhledu |
| Upravit poznámku | Aktivní skupina | F2 |
| Najít možné protějšky | Nevyřízený finanční kořen | Ctrl+Shift+F |
| Otevřít zdroj / helper / členy | Dle existence vztahu | Z menu |
| Kopírovat hlavní / všechny ID | Existující objekt | Ctrl+C / Ctrl+Shift+C |
| Exportovat vybrané / důkaz | Existující objekty | Z menu |
| Audit objektu | Existující i historický objekt | Z menu |
| Aktualizovat helper detail | API helper aktuálního kontextu; pravidla aktivní/neaktivní entity dle 8.6 | Z menu |
| Potvrdit / odmítnout reference / zrušit rozhodnutí | Aktivní úplná rezervace aktuální publikované generace, pravidla 8.5; zákaz při REFRESHING | Z menu |
| Ověřit kompatibilitu BetterHotel | Nastavení, uložená dvojice tokenů, žádný běžící sync | Z menu |
| Znovu povolit automatické spojení | Detail důkazu s aktivním potlačením | Z menu |
| Undo / Redo | Platný dostupný příkaz | Ctrl+Z / Ctrl+Y |
| Fulltext | Globálně | Ctrl+F |
| Obnovit pohled | Read-only lokální refresh | F5 |

Delete v tabulce zdrojových řádků nikdy nemaže finanční zdroj. Escape zavře aktuální dialog; sám nezruší finanční operaci, nevymaže výběr ani neprovede Undo. Operace se ruší explicitním tlačítkem Zrušit. V editovaném textu mají standardní textové zkratky přednost před finančními globálními zkratkami.

## 12. Důvody nevyřízenosti a chyby

### 12.1 Důvodové kódy

Důvod je technické vysvětlení, nikoli povinný uživatelský komentář. Více příčin lze uvést současně; primární se volí v pořadí helper neúplnost → chybějící vazba → měna → nejednoznačnost → částka → chybějící protějšek. Není to další finanční stav.

| Kód | Význam | Nabízená akce |
|---|---|---|
| HELPER_DATA_NOT_SYNCED | Potřebný rozsah či entita nemá úplný helper snapshot | Načíst BetterHotel |
| HELPER_ENTITY_NOT_OBSERVED | Dříve známá entita není v aktivní množině publikované generace | Zobrazit historii / úplně načíst BetterHotel |
| HELPER_CONTEXT_MISMATCH | Odkaz patří historickému připojení | Zobrazit historický důkaz; nepoužít pro nové párování |
| BOOKING_REFERENCE_REJECTED | Platné ruční veto reference | Otevřít rozhodnutí a případně je zrušit |
| BOOKING_REFERENCE_REVIEW_REQUIRED | Podklady aktivního rozhodnutí se změnily | Rozhodnout nad aktuální množinou nebo rozhodnutí zrušit |
| CASHBOOK_NO_DOCUMENT | Nenalezen jednoznačný FA doklad | Otevřít helper hledání, ručně seskupit |
| DOCUMENT_NO_RESERVATION | Doklad nemá právě jednu aktivní vazbu | Otevřít doklad a vazby |
| RESERVATION_NO_BOOKING_REFERENCE | Chybí potvrzená Booking reference | Otevřít rezervaci |
| BOOKING_REFERENCE_NOT_FOUND | Reference existuje, finanční Booking řádek chybí | Filtrovat Booking, importovat další export |
| BANK_NO_COUNTERPART | Bankovní řádek nemá krycí protějšek | Najít protějšky |
| BOOKING_NO_COUNTERPART | Booking řádek nemá protějšek | Najít protějšky / ruční skupina |
| CASHBOOK_NO_COUNTERPART | Cashbook zůstává bez krytí | Najít protějšky |
| AMOUNT_MISMATCH | Kandidáti existují, součet není nula | Doplnit pracovní výběr |
| CURRENCY_MISMATCH | Identifikátor ukazuje na jinou měnu | Zobrazit kandidáta, skupinu nepovolit |
| MULTIPLE_CANDIDATES | Více přípustných důkazů nebo kombinací | Ruční výběr |
| OPEN_AGGREGATE | Skupina má nenulový rozdíl | Doplnit/rozložit skupinu |
| AUTO_SEARCH_LIMIT | Nelze úplně prohledat komponentu v limitu | Ruční skupina nebo nastavení limitů |
| AUTO_SUPPRESSED | Uživatel rozpojil identický auto důkaz | Znovu povolit automatiku nebo pracovat ručně |

U volného listu po importu bez spuštěné analýzy lze uvést neutrální „Dosud nepárováno“; absence kandidáta se nesmí tvrdit před jeho vyhledáním. Read-only výpočet důvodů nevytváří skupiny ani žádosti na API.

### 12.2 Chybová odpověď služby

Všechny chyby mají `code`, české `message`, `operation_id`, `details` a příznak retryable. Importní details obsahují soubor/hash/list, fyzické číslo řádku (od 1 včetně hlavičky; CSV také rozsah fyzických linek víceřádkové buňky), název sloupce, bezpečnou surovou hodnotu, důvod a při konfliktu diff staré/nové kanonické hodnoty. UI nezobrazuje pouze traceback. Úplný seznam chyb se stránkuje; žádná chyba se kvůli limitu renderu neztrácí.

Minimální kódy: API_CONTEXT_CHANGED, API_DETAIL_REQUIRES_FULL_SYNC, SNAPSHOT_INVALID, API_SNAPSHOT_CONFLICT, FILE_CHANGED, FILE_TOO_LARGE, FORMAT_INVALID, HEADER_INVALID, SHEET_AMBIGUOUS, ROW_SHAPE_INVALID, MONEY_INVALID, DATE_INVALID, CURRENCY_UNSUPPORTED, UNKNOWN_ENUM, IDENTITY_MISSING, SOURCE_CONFLICT, CASHBOOK_REFERENCE_INVALID, SUMMARY_MISMATCH, DB_BUSY, STALE_STATE, MIXED_CURRENCY, ALREADY_OWNED, CYCLE_DETECTED, NONZERO_DIFFERENCE, UNDO_CONFLICT, API_AUTH, API_SCHEMA, API_CURSOR_CYCLE, API_RATE_LIMIT, DISK_FULL, BACKUP_INVALID, DATA_PATH_UNAVAILABLE. `SPLIT_CLIENT_ENTITY` a `CASHBOOK_FOOTER_MISMATCH` jsou diagnostické kódy úspěšného importu s upozorněním, nikoli karanténní finanční objekty.

## 13. Nastavení a tajemství

### 13.1 Pouze UI jako zdroj provozní konfigurace

**Jediné povinně zadávané hodnoty pro plný běh jsou BetterHotel Access Token a Client Token.** Aplikace bez nich plně umožňuje importy, ruční rekonsiliaci, práci s uloženými daty a exporty; zakázané je pouze nové čtení BetterHotel. Všechny ostatní volby mají funkční výchozí hodnotu. Žádná povinná cesta, hotel ID, heslo, konfigurační soubor, `.env`, environment variable, registry hodnota ručně vytvářená provozovatelem ani CLI argument neexistuje.

Interní uložení nastavení na disk je automatické a neznamená potřebu externí konfigurace. Windows Known Folders a OS ochrana uživatelského profilu jsou platformové služby, nikoli ručně nastavované proměnné. Pokud implementace přidá další provozní parametr, musí současně přidat jeho UI ovládání, validaci, výchozí hodnotu a nápovědu; nesmí vytvořit skrytou závislost.

### 13.2 Přehled nastavení

| Oblast / klíč | Výchozí hodnota | UI / validace |
|---|---|---|
| BetterHotel Access Token | prázdné | Maskované pole, vložit/nahradit, zobrazit dočasně, bez CR/LF |
| BetterHotel Client Token | prázdné | Totéž; ukládat oba tokeny atomicky |
| sync.start_date | automaticky dle kapitoly 8 | Volitelné datum pro dřívější historii; prázdno = automaticky |
| sync.block_days | 7 | Integer 1–31 |
| sync.timeout_seconds | 30 | Integer 5–120 |
| sync.retry_count | 3 | Integer 0–5 |
| sync.requests_per_second | 2.0 | Decimal 0.2–2.0 |
| matching.bank_window_days | 7 | Integer 0–30; pro storno A zůstává pevně 7 |
| matching.max_combination | 6 | Integer 2–10 |
| matching.max_component_items | 40 | Integer 2–100 |
| matching.max_search_states | 100000 | Integer 1000–1000000 |
| matching.warning_age_days | 30 | Integer 1–3650; jen zvýraznění, ne finanční stav |
| imports.max_megabytes | 100 | Integer 1–2048 |
| data.directory | LocalAppData/KajovoKarty/data | Volitelná lokální cesta přes picker; změna bezpečným přesunem |
| data.backup_directory | LocalAppData/KajovoKarty/backups | Volitelná cesta; nesmí být uvnitř DB souboru ani stejného souboru |
| data.export_directory | Windows Documents/KajovoKarty | Volitelná cesta; create directory automaticky |
| imports.last_directory per source | Windows Documents | Volitelná preference, není nutná k importu |
| backup.daily | true | Denní záloha při prvním spuštění v daný místní den |
| backup.retention_days | 30 | Integer 1–3650; jen automatické zálohy |
| diagnostics.log_retention_days | 30 | Integer 1–3650; ne audit či finanční snapshots |
| ui.row_density | normal | compact/normal/comfortable |
| ui.text_scale | 100 | 80–160 % |
| ui.high_contrast | false | Přepínač |
| ui.reduce_motion | true | Přepínač |
| network.proxy_url | prázdné | Volitelné HTTP/HTTPS URL bez userinfo; proxy username/password jen v tomto UI, password DPAPI |

Párovací tolerance, automatické párování po importu, skrytý background sync, měnové přepočty, ruční změna finančních částek a mapování forem nejsou nastavitelné; pravidla jsou pevná. UI nikde nenabízí volbu, která poruší invariant. Proxy není povinná a bez explicitního zadání se nepoužije.

Uložit nastavení atomicky, inline zobrazit všechna neplatná pole, žádné tiché oříznutí. Změna se týká následujících operací; běžící operace používá neměnný snapshot svého nastavení. Obnovit výchozí volby nesmaže data ani tokeny. Odstranit tokeny je samostatná jasně označená akce. Test připojení provede GET /currency se zadanými hodnotami bez jejich ukládání; výsledek testu se odlišuje od uložení i od Ověřit kompatibilitu BetterHotel dle 8.2. Ověřit kompatibilitu používá atomicky uloženou dvojici, context_id a credential_revision; neuložené změny polí se musí nejprve uložit. U tokenů je read-only identifikace aktuálního připojení, čas vytvoření a stav poslední publikace; není nutné zadávat hotel ID ani spravovat kontext ručně. Skutečná změna dvojice automaticky provede oddělení dle 8.8.

### 13.3 Ochrana tokenů

Použít Windows DPAPI v user scope, entropy konstantu `cz.kajovo.kajovokarty`; ciphertext lze uložit do secret tabulky. Tokeny se nikdy nezapisují plaintext do SQLite, logů, auditů, reportů, telemetry, tracebacku nebo diagnostického ZIP. Žádný šifrovací klíč není požadován od uživatele. DPAPI selhání nesmí vést k plaintext fallbacku; zobrazí se nastavení pro nové zadání tokenů a lokální data zůstanou dostupná.

Přístup k dešifrovaným hodnotám má jen API adaptér a explicitní dočasné zobrazení v Nastavení. Po ztrátě focusu se pole znovu maskují. Při ukládání se trimují pouze okolní whitespace, vnitřní bajty tokenu se nemění. Běžná záloha ani diagnostika neobsahují tokeny; po obnově na jiném počítači se obě hodnoty opět zadávají ve stejném UI. Jde o stejné dva údaje, nikoli novou externí konfiguraci.

## 14. Exporty, důkazy a sestavy

### 14.1 Výběr dat a jednotná autorita

Povinné sestavy a jejich přesné datové sady stanoví 14.3–14.4. Všechny jsou read-only. Export „Vybrané“ obsahuje celý explicitní výběr i mimo aktuální filtr, což dialog uvede; export „Aktuální filtr“ obsahuje všechny výsledky aktuálního filtru, nikoli jen stránku UI. Pro historickou skupinu se bere její uložený strom a důkaz, nikoli aktuální přeskupení listů. Žádná sestava nevymýšlí další obchodní sloupce mimo schéma.

Export se vytváří z jednoho konzistentního DB read snapshotu s časem, filtry, řazením, app build ID a report_schema_id=`KAJOVOKARTY-EXPORT-1`. Všechny datové sady v jednom exportu používají stejný snapshot. Prázdná datová sada obsahuje všechny hlavičky a 0 datových řádků. Počet řádků, součet a ukázka se nesmějí počítat jiným dotazem s jiným filtrem než samotný export.

### 14.2 Typy, null, sloupce a peníze

Hlavičky souborů jsou přesně anglické strojové klíče uvedené níže, v uvedeném pořadí; GUI jejich význam vysvětlí českým popiskem. Zkratky typů ve schématu: `S` Unicode text, `I` integer, `B` boolean, `D` ISO datum, `U` UTC RFC3339 se 6 desetinnými místy a Z, `L` lokální ISO timestamp dle 4.2/A.1, `J` canonical JSON. Suffix `?` znamená nullable. Bez `?` hodnota povinná; J pro množinová pole používá `[]`/`{}`, nikdy prázdný text. JSON seznamy identifikátorů se deduplikují a lexikograficky řadí; seřazené UI sort specifikace si naopak zachovají pořadí klíčů.

Datové typy a sloupce jsou vymezeny schématem, ne typem první neprázdné hodnoty. Finanční `_minor` sloupec je přesný integer; **bezprostředně za každý deklarovaný `_minor:I` nebo `_minor:I?` se vždy automaticky vloží sloupec se stejným prefixem a suffixem `_decimal`**, typu S nebo S?. Hodnota je přesně částka/100 s tečkou a dvěma desetinnými místy, bez oddělovačů tisíců a bez zaokrouhlení. Například `difference_minor,difference_decimal,currency`. Toto rozvinutí platí pro všechny datové sady včetně součtů; nikoli pro klíče uvnitř JSON. Pro všechny ostatní deklarované sloupce se žádné další sloupce nevytvářejí.

CSV null se zapisuje jako prázdná buňka; empty string se nepoužívá u nullable skalárních polí. Povinné sheet v source_occurrences používá pro CSV prázdný řetězec; jde o jedinou explicitní výjimku, rozlišenou schématem. JSON může obsahovat explicitní `null`. CSV boolean je `true`/`false`; integer základ 10 bez exponentu; timestamp/data přesný ISO text. XLSX null je prázdná buňka, boolean skutečný boolean, I numeric pokud nejvýše 15 číslic, jinak explicitní text bez ztráty číslic; data/timestamps i identifikátory jsou textové buňky. `_decimal` je v CSV i XLSX přesný text, `_minor` slouží pro přesné výpočty; PDF ukazuje česky formátovanou částku z minor. Povinná měna patří do téhož řádku jako finanční čísla.

Text začínající po whitespace `=`, `+`, `-` nebo `@` se v CSV chrání prefixem apostrofu; peněžní decimal text generovaný pouze z ověřeného integer a číselné sloupce se tímto pravidlem nemění. ID s úvodními nulami lze z CSV číst bezeztrátově jako text, avšak Excel při automatickém otevření může provést vlastní konverzi; pro tabulkové zobrazení je autoritou explicitně typovaný XLSX. XLSX zapisuje každý S/J jako textový typ, nikdy jako vzorec. Raw zdrojová DB hodnota se při exportu neupravuje.

### 14.3 Úplný strojový slovník datových sad

Následující JSON je normativní. Každá položka pole je `název_sloupce:typ`; implementace musí použít přesně toto pořadí a mechanické rozvinutí `_minor` dle 14.2. `source_hash` znamená canonical content_hash, `file_hash` přesný SHA256 bytů vstupu. `active` a `complete` jsou boolean, ne uživatelský finanční stav. Metoda je AUTO/MANUAL/IMPORT/SYSTEM tam, kde je přípustná; status pracovního objektu UNRESOLVED/RESOLVED. Export žádné technické stavy nepřekládá do jiných kódů podle jazyka Windows.

```export-schema-json
{
  "metadata": [
    "key:S",
    "value_json:J"
  ],
  "work_objects": [
    "object_id:S",
    "object_type:S",
    "status:S",
    "method:S?",
    "source_kinds:J",
    "date_from:D",
    "date_to:D",
    "primary_identifier:S",
    "description:S?",
    "leaf_count:I",
    "side:S",
    "amount_minor:I",
    "difference_minor:I",
    "currency:S",
    "booking_references:J",
    "invoice_codes:J",
    "reason_codes:J",
    "note:S?"
  ],
  "financial_sources": [
    "source_id:S",
    "source_kind:S",
    "source_identity:S",
    "source_hash:S",
    "primary_identifier:S",
    "description:S?",
    "local_date:D",
    "occurred_at_utc:U?",
    "time_precision:S",
    "signed_amount_minor:I",
    "contribution_minor:I",
    "currency:S",
    "root_object_id:S",
    "root_status:S",
    "created_at:U"
  ],
  "cashbook_rows": [
    "source_id:S",
    "issued_local:L",
    "movement:S",
    "cashbook_number:S?",
    "label:S",
    "client:S?",
    "income_minor:I",
    "expense_minor:I",
    "signed_amount_minor:I",
    "currency:S",
    "payment_form:S",
    "variable_symbol:S",
    "issued_by:S?",
    "invoice_code:S",
    "storno_marker:B"
  ],
  "bank_rows": [
    "source_id:S",
    "event_class:S",
    "terminal_id:S",
    "pos_id:S?",
    "occurred_local:L",
    "server_local:L?",
    "booked_date:D?",
    "signed_amount_minor:I",
    "cashback_minor:I",
    "tip_minor:I",
    "currency:S",
    "arn:S?",
    "dcc:S?",
    "masked_account:S?",
    "authorization_code:S?",
    "variable_symbol:S?",
    "variable_symbol_2:S?",
    "seq_id:S",
    "issuer:S?",
    "entry_method:S?",
    "merchant:S?",
    "merchant_address:S?"
  ],
  "booking_rows": [
    "source_id:S",
    "invoice_type:S",
    "booking_reference:S",
    "arrival:D?",
    "departure:D?",
    "guest_name:S?",
    "provider:S?",
    "reservation_status:S",
    "currency:S",
    "payment_status:S",
    "signed_amount_minor:I",
    "payout_date:D",
    "payout_id:S",
    "payout_key:S",
    "row_hash:S"
  ],
  "booking_payouts": [
    "payout_key:S",
    "payout_id:S",
    "payout_date:D",
    "currency:S",
    "scope:S",
    "included_line_count:I",
    "all_payout_line_count:I",
    "signed_amount_minor:I",
    "contribution_minor:I",
    "booking_references:J"
  ],
  "group_summary": [
    "group_id:S",
    "lifecycle:S",
    "status:S",
    "created_at:U",
    "method:S",
    "currency:S",
    "difference_minor:I",
    "leaf_count:I",
    "evidence_hash:S",
    "note:S?",
    "evidence_context_ids:J",
    "evidence_generation_ids:J"
  ],
  "group_leaves": [
    "group_id:S",
    "source_id:S",
    "source_kind:S",
    "source_identity:S",
    "source_hash:S",
    "primary_identifier:S",
    "local_date:D",
    "signed_amount_minor:I",
    "contribution_minor:I",
    "currency:S",
    "invoice_codes:J",
    "reservation_ids:J",
    "booking_references:J",
    "helper_entity_keys:J"
  ],
  "group_edges": [
    "group_id:S",
    "membership_id:S",
    "parent_object_id:S",
    "child_object_id:S",
    "child_type:S",
    "child_position:I"
  ],
  "source_occurrences": [
    "source_id:S",
    "run_id:S",
    "file_id:S",
    "file_hash:S",
    "original_name:S",
    "sheet:S",
    "row_start:I",
    "row_end:I",
    "input_mode:S",
    "disposition:S",
    "repair_code:S?"
  ],
  "helper_entities": [
    "context_id:S",
    "generation_id:S",
    "resource_type:S",
    "external_id:S",
    "snapshot_id:S",
    "projection_kind:S",
    "request_shape_hash:S",
    "content_hash:S",
    "fetched_at:U",
    "revision:I",
    "complete:B",
    "active:B",
    "root_observed:B",
    "inactive_reason:S?",
    "usable_for_new_auto:B",
    "helper_state:S",
    "helper_state_revision:I",
    "evidence_epoch:I",
    "payload_json:J"
  ],
  "helper_links": [
    "context_id:S",
    "generation_id:S",
    "link_id:S",
    "from_type:S",
    "from_id:S",
    "relation:S",
    "to_type:S",
    "to_id:S",
    "active:B",
    "complete:B",
    "snapshot_id:S",
    "snapshot_hash:S",
    "fetched_at:U",
    "helper_state:S",
    "usable_for_new_auto:B"
  ],
  "helper_references": [
    "context_id:S",
    "generation_id:S",
    "reference_id:S",
    "reservation_id:S",
    "snapshot_id:S",
    "candidate:S?",
    "label:S?",
    "start_offset:I?",
    "end_offset:I?",
    "parser_version:S",
    "status:S",
    "override_candidate:S?",
    "override_accepted:B?",
    "override_valid:B",
    "helper_state:S",
    "override_active:B",
    "candidate_set_hash:S",
    "resolution_status:S",
    "effective_candidate:S?"
  ],
  "audit_events": [
    "event_id:S",
    "timestamp:U",
    "event_type:S",
    "operation_id:S?",
    "command_id:S?",
    "method:S",
    "object_refs_json:J",
    "before_json:J",
    "after_json:J",
    "amounts_by_currency_json:J",
    "note:S?"
  ],
  "import_diagnostics": [
    "diagnostic_id:S",
    "operation_id:S",
    "run_id:S",
    "file_id:S?",
    "file_hash:S?",
    "original_name:S?",
    "input_mode:S",
    "sheet:S?",
    "row_start:I?",
    "row_end:I?",
    "severity:S",
    "code:S",
    "column_key:S?",
    "raw_value_json:J",
    "source_identity:S?",
    "source_id:S?",
    "field_diff_json:J",
    "message:S",
    "created_at:U"
  ],
  "currency_totals": [
    "dataset:S",
    "currency:S",
    "row_count:I",
    "signed_amount_minor:I?",
    "contribution_minor:I?",
    "need_minor:I?",
    "surplus_minor:I?",
    "difference_minor:I?"
  ],
  "api_compatibility": [
    "run_id:S",
    "context_id:S",
    "helper_generation_id:S?",
    "wire_contract_id:S",
    "app_build:S",
    "credential_revision:I",
    "started_at:U",
    "finished_at:U?",
    "range_start:D",
    "range_end:D",
    "overall_status:S",
    "endpoint_template:S",
    "endpoint_status:S",
    "response_count:I",
    "item_count:I",
    "status_codes_json:J",
    "response_hashes_json:J",
    "field_types_json:J",
    "error_codes_json:J"
  ]
}
```

Význam a kardinalita dalších polí:

- `root_object_id/root_status` jsou aktuální kořen a jeho odvozený stav ve zvoleném snapshotu. financial_sources obsahuje každý source_id právě jednou, i když byl importován opakovaně. cashbook_rows, bank_rows a booking_rows mají právě jeden odpovídající detailový řádek na source_id daného typu.
- `group_summary.evidence_context_ids/evidence_generation_ids` jsou deduplikované seznamy kontextů/generací použitých v uložených důkazech cílového stromu; bez helperu []. `group_leaves.helper_entity_keys` je seznam objektů {context_id,resource_type,external_id} skutečně použitých v důkazu daného listu, řazený lexikograficky podle této trojice; prosté invoice/reservation ID sloupce jsou pouze zobrazovací projekce. `group_leaves` má jeden řádek pro každý pár cílové group_id/source_id, nezapočítává podskupinu jako list. `group_edges` obsahuje úplný strom dané cílové skupiny z příslušného evidence snapshotu; child_position je od nuly, podle kanonického pořadí přímých dětí. Přímé děti jsou závazně řazeny lexikograficky podle child_object_id; stejný snapshot má vždy stejné pořadí. Invoice/reservation/Booking reference jsou JSON seznamy, takže více helper vazeb nenásobí finanční řádky.
- `source_occurrences` obsahuje všechny známé relevantní výskyty vybraných source_id v exportním snapshotu. Mnoho výskytů nemění finanční součet. row_start/end jsou 1-based v originálu; v XLS/XLSX jsou shodné; v CSV zahrnují všechny fyzické řádky víceřádkového záznamu, sheet je prázdný řetězec. original_name pochází z příslušného import_file. raw buňky nejsou součást této datové sady, původní soubor je k dispozici přes detail importu.
- `booking_payouts` agreguje pouze exportované booking_rows po payout_key. scope je COMPLETE, pokud included_line_count=all_payout_line_count v DB snapshotu, jinak FILTERED_PARTIAL. Nikdy nepředstírá celou výplatu při filtru jen na část rezervací. all_payout_line_count je diagnostický počet celé výplaty, částky zůstávají součty exportovaných řádků.
- `helper_entities` je sloučená reprezentace vybraných helperů z explicitní context_id/generation_id včetně přesného JSON. active/root_observed/complete/inactive_reason popisují tuto generaci; usable_for_new_auto je true pouze při aktuálním kontextu, aktuální publikované generaci, READY a active+complete. Stejný sloupec na historické generaci je vždy false. `helper_links` je jeden řádek na uloženou hranu; podporované relation jsou RESERVATION_INVOICE, RESERVATION_BILL, BILL_ITEM, RESERVATION_SECURITY_DEPOSIT, INVOICE_ITEM, INVOICE_ITEM_BILL_ITEM. Směr je rodič→dítě podle názvu. `usable_for_new_auto` pro hranu znamená CURRENT kontext + aktuální publikovanou generaci + READY + její aktivitu/úplnost + active/complete koncových entit + odpovídající credential_revision; samo o sobě nezaručuje jednoznačnost celého řetězce. Currency map ani financial-stats se nepovažují za finanční hranu.
- `helper_references` MISSING má jeden řádek s null candidate/label/offsety; CONFLICT má všechny kandidáty. Override je rozhodnutí rezervace podle 8.5. Chybějící nebo zrušený override = null override_candidate/override_accepted, override_active=false, override_valid=false. Aktivní REJECT = null override_candidate, override_accepted=false; override_valid může být true. candidate_set_hash a resolution_status/effective_candidate se počítají podle 8.5; AUTO_CONFIRMED tedy nevyžaduje override_valid. V historické generaci je resolution_status=INACTIVE_CONTEXT_OR_ENTITY a effective_candidate=null; override_candidate/override_accepted jsou null a override_active/override_valid=false. Pozdější rozhodnutí se do historického helper exportu nedoplňuje. Přesné rozhodnutí z okamžiku vzniku finanční skupiny se čte z jejího uloženého evidence_json, nikoli z dnešní helper_override tabulky. Historické raw kandidáty zůstávají viditelné. Nikdy se nereplikuje domnělá ruční reference.
- `audit_events.before_json/after_json` je přesně uložený safe snapshot události; chybějící strana je JSON null, nikoli sloupec vynechaný z exportu. amounts_by_currency_json je objekt pouze s klíči CZK/EUR, kde každá přítomná měna má `{signed_minor,contribution_minor,difference_minor}` s integer/null hodnotami; událost bez finančního efektu má `{}`. Vnořené částky různých měn se nesčítají. Neobsahuje autora, uživatelský účet ani token.
- `import_diagnostics` zachycuje chyby i varování před odmítnutým commitem, bez nutnosti existence financial_source. Input mode je vždy známý; identifikátory a řádek jsou null, pokud chyba vznikla před jejich načtením. field_diff_json je řazený seznam objektů `{field,old,new}`; bez konfliktu `[]`. raw_value_json je hodnota buňky, seznam buněk nebo JSON null, nikdy nehodnocený text vzorce. Zachování bezpečné hodnoty znamená odstranit tajemství a kontext nepatřící k importu, nikoli nahradit finanční konflikt neurčitým popisem.
- `api_compatibility` má právě 12 řádků na vybraný compatibility_run, i pro NOT_ATTEMPTED/UNEXERCISED. Neobsahuje hodnotu tokenu ani ID hostů z raw odpovědi. status_codes_json je vzestupně řazený seznam unikátních HTTP integer kódů; response_hashes_json je seznam {request_index,sha256} v pořadí přijatých HTTP odpovědí včetně retry, bez hashů neexistujících odpovědí. response_count počítá přijaté HTTP odpovědi včetně neúspěšných; item_count počítá platné položky po deduplikaci identit v této šabloně. field_types_json je seznam {path,types}, řazený podle path; path je JSON Pointer ke známému poli s * místo indexu pole, types je řazená množina z null/boolean/integer/number/string/array/object. Pro neznámá raw pole se názvy neexportují. error_codes_json je lexikograficky řazený seznam unikátních bezpečných chybových kódů.

### 14.4 Pevná skladba jednotlivých sestav

CSV datové sady mají název `<dataset>.csv`. XLSX sheet names odpovídají přesně dataset klíčům (všechny do 31 znaků). V tomto pořadí se přidávají datové sady; metadata je vždy první, currency_totals vždy poslední, pokud je předepsána:

| report_id / UI název | Datové sady po metadata | Rozsah řádků |
|---|---|---|
| unresolved / Nevyřízené | work_objects, currency_totals | Vybrané nebo filtrované nevyřízené kořeny. |
| resolved / Vyřízené skupiny | work_objects, group_summary, group_leaves, group_edges, source_occurrences, currency_totals | Vybrané/filtrované aktivní vyřízené kořeny a jejich úplné důkazy. |
| group_evidence / Důkaz skupiny | group_summary, group_leaves, group_edges, source_occurrences, currency_totals | Právě jedna zvolená aktuální nebo historická skupina. |
| cashbook_cards / Karty pokladny | financial_sources, cashbook_rows, source_occurrences, currency_totals | Vybrané/filtrované listy CASHBOOK_CARD, nikoli hotovost/převody. |
| terminal / Terminálové transakce | financial_sources, bank_rows, source_occurrences, currency_totals | Vybrané/filtrované listy BANK_CARD. |
| booking / Booking platby | financial_sources, booking_rows, booking_payouts, source_occurrences, currency_totals | Vybrané/filtrované listy BOOKING. |
| helpers / Pomocné doklady a vazby | helper_entities, helper_links, helper_references | Vybrané/filtrované helper entity a související hrany/koncové entity rekurzivně až do uzavřenosti; visited set podle context_id/generation_id/typu/ID brání cyklu; žádná hrana nesmí překročit kontext/generaci. Neaktivní entity/hrany a staré generace pouze při explicitním historickém filtru. |
| audit / Audit | audit_events | Vybrané/filtrované auditní události; bez finančních součtů událostí přes čas. |
| import_errors / Importní chyby | import_diagnostics | Všechny diagnostiky z vybrané operace nebo explicitního filtru, default severity ERROR+WARNING. |
| api_compatibility / Ověření BetterHotel | api_compatibility | Právě jeden explicitně vybraný compatibility_run. |

Rozšíření výběru o potřebné listy/provenance v důkazu není aplikací filtru na děti: důkaz nikdy nevynechá člena skupiny jen proto, že jeho datum leží mimo filtr rodičů. Metadata uloží zvolený rozsah a odvozené počty. U general „Exportovat vybrané“ je report určen typem výběru: finanční kořeny unresolved/resolved dle jejich stejného statusu, smíšený stav vyžádá výběr dvou samostatných sestav v exportním dialogu; source listy jednoho druhu příslušný zdrojový report; helper/audit/import typ příslušný report. Pracovní výběr obsahuje jen nevyřízené kořeny, proto jeho export vždy unresolved. Neexistuje skrytý mix nesouvisejících schémat v jedné tabulce.

Pořadí řádků hlavní datové sady odpovídá uloženému UI sort; poslední tie-break je její stabilní klíč. Bez explicitního sort platí vzestupně: work_objects object_id; financial_sources a zdrojové detaily source_id; booking_payouts payout_key; group_summary group_id; group_leaves (group_id,source_id); group_edges (group_id,parent_object_id,child_position); source_occurrences (source_id,run_id,file_id,sheet,row_start); helper_entities (context_id,generation_id,resource_type,external_id); helper_links link_id; helper_references (context_id,generation_id,reservation_id,candidate,reference_id); audit_events (timestamp,event_id); import_diagnostics (created_at,diagnostic_id); api_compatibility endpoint_template; currency_totals (dataset,currency). Doprovodné sady vždy používají tyto klíče. Textové klíče se řadí binárně podle Unicode code points bez locale, integer číselně, null před nenulovým údajem.

Metadata má povinné řádky v tomto pořadí: report_schema_id, report_id, app_build, exported_at, database_snapshot_id, selection_mode, selected_ids, filters, sort, helper_state, helper_context_id, helper_generation_id, helper_evidence_epoch, selected_helper_graphs, row_counts, currency_policy, csv_text_escape. value_json obsahuje JSON scalar/objekt/seznam dle významu; helper_context_id/generation_id jsou aktuální pointery v exportním snapshotu (generation_id může být null), selected_helper_graphs je seřazený deduplikovaný seznam {context_id,generation_id} skutečně zahrnutých helper grafů a důkazů, bez nich []; selection_mode = SELECTION/FILTER/SINGLE_OBJECT, selected_ids `[]` při FILTER, filters `{}` bez filtru, sort seznam `{field,direction}`. database_snapshot_id je UUID exportní operace označující jediný read snapshot, nikoli tvrzení o SQLite snapshot API. row_counts je objekt dataset→počet datových řádků (bez samotných metadata). currency_policy="NO_CONVERSION_SEPARATE_CZK_EUR". csv_text_escape="APOSTROPHE_FOR_UNTRUSTED_FORMULA_PREFIX".

`currency_totals` obsahuje jen přítomné měny, při 0 řádcích žádné zástupné peníze. Pro work_objects jeden řádek na měnu: row_count počet kořenů, need=sum(max(difference,0)), surplus=sum(max(-difference,0)), difference=sum(difference), signed/contribution=null. Pro finanční zdrojové sestavy se sčítá pouze financial_sources, dataset="financial_sources", row_count=počet unikátních source_id, signed/contribution jejich sumy, ostatní částky null. Pro group_evidence dataset="group_leaves", jedna měna, signed=sum(signed listů), contribution=sum(contribution listů), difference=contribution, need/surplus=null. Pro resolved se uvádějí jen součty work_objects, nikoli ještě další součet týchž listů. Neagregovat zároveň financial_sources a jeho detailové řádky ani booking_payouts; byly by to duplicitní peníze. Audit a helpers žádnou currency_totals sadu nemají.

### 14.5 Formáty a atomické vytvoření

**CSV**: každá sada má svůj řádný UTF-8 BOM / CRLF / čárkový RFC4180 CSV soubor s přesnými hlavičkami. Jelikož sestava obsahuje metadata a více rozdílných schémat, UI nabízí „Export CSV (ZIP)“: jeden ZIP `<report_id>.zip` s přesně předepsanými `<dataset>.csv` v kořeni, bez dalších volných souborů. Nesmí vložit nekompatibilní hlavičky za sebe do jediného CSV ani vynechat metadata. Každý jednotlivý CSV lze standardně otevřít samostatně. Pole s čárkou, novým řádkem nebo uvozovkou se standardně uvozuje/escapuje.

**XLSX**: jeden `<report_id>.xlsx` se sadami jako listy v pořadí 14.4 a s přesnými sloupci 14.3; tučná hlavička, auto filter, freeze A2, přiměřené šířky, zalomení textu, explicitní datové typy. Je-li datová sada větší než 1 048 575 řádků, rozdělí se deterministicky na listy `<dataset>_001`, `_002` atd., každý se stejnou hlavičkou; řazení řádků se nemění, žádné oříznutí. Metadata row_counts uvádí celou datovou sadu před rozdělením. Jména základních sad se volí tak, aby i suffix zůstal do 31 znaků.

**PDF**: A4 na šířku; vložený font s češtinou, opakované hlavičky a stránkování. report ID/název, čas, filtr a měnové součty vycházejí ze stejného snapshotu jako CSV. Významové pořadí sad je 14.4. Dlouhé JSON a seznamové buňky se zobrazí v zalamovaném detailu pod řádkem, ne jako nečitelné miniaturní sloupce; žádný důkazový list se nevypustí. PDF je prezentační doplněk, nenahrazuje předepsaná datová schémata CSV/XLSX.

Všechny formáty se nejprve dokončí do dočasného souboru vedle cíle; případný ZIP se uzavře a zkontroluje před atomickým rename. Standardní save dialog potvrdí přepsání. Zrušení/disk full zachová předchozí cílový soubor. EXPORT_COMPLETED se audituje až po úspěšném přejmenování; selhání auditu po úspěšném souboru musí být zobrazeno jako chyba evidence exportu, nikoli tvrzení, že soubor nevznikl.


## 15. Audit, provoz, zálohy a obnova

Audit neobsahuje „kdo“, protože aplikace nemá uživatele ani role. `issued_by` z cashbook je původní údaj exportu a nesmí být zaměněn za autora aplikační operace. Každá významová mutace má čas, typ, ID objektů/zdrojů, before/after, částky a měny, metodu, rodičovskou operaci a volitelnou poznámku. Import start/finish/reject, sync start/blok/finish, auto start/skupina/finish, ruční skupiny, přidání, rozpojení, dissolve, poznámky, helper overrides, Undo/Redo, export, nastavení, záloha a obnova se auditují. Změna tokenu se audituje jako „token nahrazen/odstraněn“ a starý/nový lokální context_id, bez hodnot nebo hashe tokenu. Publikace grafu eviduje context_id/generation_id, přidané/změněné/znovu zjištěné/nově nezjištěné identity a změny hran. Tyto seznamy jsou kontextové klíče, nikoli smíchaná externí ID.

Audit je append-only pro běžnou aplikaci a nesmí být čištěn retenčním nastavením technických logů. Není deklarován jako kryptograficky nefalšovatelný proti vlastníkovi počítače. Read-only prohlížení, filtrování a kopírování nemusí vytvářet tisíce zbytečných finančních auditních událostí.

Denní a ruční záloha použije SQLite online backup API do dočasného souboru, odstraní z kopie secret tabulku/obsah a provede integrity_check i foreign_key_check. Záloha ZIP obsahuje DB včetně source_file BLOBů, manifest (schema/app verze, čas, SHA256 každého souboru) a žádné tokeny. Automatická záloha při startu nesmí blokovat UI déle než inicializační minimum. Selhání je viditelná informace, nikoli důvod zničit nebo přepsat data. Automatická retence nikdy nemaže poslední úspěšnou zálohu ani ručně vytvořené zálohy.

Obnova je kompletní návrat lokálních dat do snapshotu, nikoli merge s aktuální DB. UI před potvrzením ukáže datum zálohy a varování, že pozdější lokální změny budou nahrazeny. Nejprve zastavit nové mutace, vytvořit bezpečnostní zálohu aktuálních dat, ověřit checksum/schema/SQLite a neexistenci path traversal, extrahovat do odděleného umístění, provést případnou kompatibilní migraci kopie, pak atomicky přepnout DB a znovu otevřít spojení. Chyba v kterémkoli kroku ponechá původní DB. Na stejném počítači lze po obnově zachovat aktuálně uložené DPAPI tokeny mimo obnovovaný snapshot; nesmějí se přepsat tokeny ze zálohy. Součástí dokončení obnovy je vždy vyřazení obnovených kontextů z aktuálního použití a založení prázdného CURRENT kontextu dle 8.8. Po obnově audit zaznamená hash zálohy, čas obnovy a nový context_id v obnovené DB.

Přesun datové složky probíhá pouze z Nastavení: cílová složka musí být lokální a zapisovatelná; nesmí obsahovat jiný pracovní prostor. Zastavit operace, online backup/copy včetně immutable zdrojů, ověřit hashe a DB, atomicky přepnout automatický bootstrap pointer uložený v Known Folder, restartovat. Původní složku neodstraňovat, dokud není nové otevření úspěšné. Nedostupný nakonfigurovaný adresář vyvolá zotavovací UI, nikdy tiché založení prázdné DB. Změna cesty nevyžaduje editaci souboru uživatelem.

Diagnostický ZIP vytvářený explicitně v Nastavení obsahuje app/OS verzi, seznam migračních verzí, anonymní počty dat a invariant checks, safe error kódy, sanitized technické logy a poslední operace bez raw buněk. Neobsahuje source_file, DB, klienty, jména hostů, karty, booking čísla, tokeny ani syrové API odpovědi. Nikam se sám neodesílá. Zobrazené cesty k osobním složkám se pseudonymizují. Zdrojové důkazy a audit se uchovávají trvale; snapshot retention nesmí vymazat důkaz existující finanční skupiny.

## 16. Architektura a distribuce

Závazný stack: Python 3.12, PySide6/Qt6, SQLite, httpx, xlrd pro XLS, openpyxl pro čtení/export XLSX, standardní csv/Decimal/hashlib/json/zoneinfo; tzdata zabalit pro Windows. PDF renderer s vloženými fonty, například ReportLab. Konkrétní kompatibilní patch verze všech závislostí programátor uzamkne v lockfile s hashi a jejich licence přiloží k distribuci. Toto určení není tvrzení o nejnovějších verzích knihoven; rozhoduje otestovaný reprodukovatelný build. Program nesmí při startu instalovat Python, pip balíčky nebo čekat na internet kvůli UI.

Oddělení vrstev: `domain` (Money, identity, skupiny, invarianty, matching), `application` (příkazy, query, import orchestrace, operace, audit, zálohy), `infrastructure` (SQLite, souborové parsery, BetterHotel GET, DPAPI, exporty), `ui` (Qt view/model a registr akcí), `bootstrap` (paths, migrace, dependency injection, jednoprocesový zámek). Doména neimportuje Qt ani httpx; UI neprovádí SQL a nepočítá vlastní finanční pravdu. API helper model je oddělený od financial_source. Výchozí config a validační schema nastavení jsou jediné a sdílené UI/službami.

Veřejné aplikační operace mají typované vstupy/výstupy: `PreflightImport(files)->ImportPreview`, `CommitImport(preview_id,expected_snapshot_hashes)->ImportResult`, `SyncHelpers(scope)->OperationId`, `RunAutoMatching()->OperationId`, `CreateGroup(selection,expected_revisions,note)->GroupResult`, `AddToGroup(group,selection,revisions)->GroupResult`, `DissolveGroup(group,revision)->Result`, `UnlinkParent(child,parent_revision)->Result`, `EditNote(group,revision,note)`, `Undo(command_id)`, `Redo(command_id)`, `QueryWorkObjects(filter,sort,page)->Page`, `GetEvidence(group_id)->Evidence`, `Export(query_or_selection,format,path)->OperationId`. Všechny mutace používají společnou transakční bránu a normalizovaný error model.

Qt event loop nesmí provádět import, HTTP, rozsáhlé SQL, PDF rendering ani zálohování. Použít worker pool a thread-safe signály s immutable DTO; widgety měnit jen v GUI threadu. Tabulky QAbstractTableModel s stránkováním/virtualizací a stabilními ID, nikoli widget na každou buňku. Aktualizace modelu má zachovat výběr a scroll, nevykonávat neustále úplný reset.

Distribuce: offline instalátor x64 pro běžného Windows uživatele bez administrátorských práv, například zabalený PyInstaller onedir produkt s instalátorem do LocalAppData/Programs/KajovoKarty, nabídkou Start a odinstalací. Python/Qt/runtime/fonty/tzdata i parser závislosti jsou součástí. Datové soubory neleží vedle executable. Odinstalace automaticky nemaže finanční data. Aktualizační instalátor zachová data a provede bezpečnou migraci; žádný updater nestahuje/spouští cizí kód bez výslovné operace uživatele.

Bez externích grafických assetů je závazný wordmark **KájovoKarty** a jednoduchá vektorová ikona dvou překrývajících se obdélníkových karet vytvořená přímo v kódu. Font UI Segoe UI z Windows; pro PDF zabalit volně distribuovatelný font s českými znaky. Bílé pozadí, tmavý text, jasně oddělené zdrojové badge s textem i barvou, čitelný focus, žádné stavy sdělované pouze barvou. Minimální okno 1100×700, podpora 100–200 % systémového DPI a 1366×768 s dostupnými posuvníky. Všechny ovládací prvky mají accessibleName a tooltip odpovídající skutečné funkci. Čísla se zobrazují česky se dvěma desetinnými místy, měna explicitně.

## 17. Ověřovací scénáře

Příloha B obsahuje přesné byty pěti vstupů (dva cashbook XLS, dva Booking CSV, terminál XLSX). Příloha A definuje syntetické doplňky pro hraniční větve. Všechny testy mají prokazovat chování, nikoli jen výskyt názvů funkcí ve zdrojáku.

| ID | Scénář | Povinný výsledek |
|---|---|---|
| IMP-01 | Roční cashbook do prázdné DB | 1055 karet, 298 CZK/757 EUR; hotovost/převody pouze ignorované; součty kapitoly 5 |
| IMP-02 | Týden po roce | 0 nových, 9 známých; nulová změna členství |
| IMP-03 | Rok po týdnu | 1046 nových, 9 známých; stejný konečný stav |
| IMP-04 | Oba cashbook současně v obou pořadích | 1055 source IDs, žádná duplicita |
| IMP-05 | Posunuté řádky 1116/1150 | Oprava 2×, 600 CZK hotovost ignorovat, 135.71 EUR karta vložit |
| IMP-06 | Roční footer | Upozornění o rozdílu; správné karetní částky zachovány |
| IMP-07 | FA != VS u čtyř doložených karet | Platný import; vazba na doklad přes FA |
| IMP-08 | Příjem se [STORNO] + výdaj + původní příjem | Tři samostatné správně podepsané pohyby |
| IMP-09 | Změna částky, měny či klienta stejného cashbook klíče | Celá operace rollback; diff polí |
| IMP-10 | Booking oba soubory | 46 EUR objektů, signed 846633 minor; záporný řádek zachován |
| IMP-11 | Anglické hlavičky/datum při českém Windows locale | Shodný výsledek bez změny locale |
| IMP-12 | Stejná Booking identity jiná Amount | Celá operace rollback, žádná source revision |
| IMP-13 | Terminál přesný vzor | 56 finančních objektů, správná znaménka a součty kapitoly 6 |
| IMP-14 | Terminál sale+storno stejné SEQ | Dva event IDs; žádný source conflict |
| IMP-15 | Stejný terminal/SEQ/event_class jiná částka | Celá operace rollback |
| IMP-16 | Znovu stejné/rename/reorder všech vstupů | Žádné nové finanční objekty a žádná změna skupin |
| IMP-17 | Jeden vadný soubor v sadě tří | Žádný finanční zápis z celé operace |
| IMP-18 | Unknown forma/status/typ, mixed decimal, vzorec, zkrácený XLS | Srozumitelná chyba, bez částečného zápisu |
| IMP-19 | Přerušený import před/during commit | Před commitem žádná změna; transakce buď celá, nebo žádná |
| IMP-20 | EXTERNAL_FILE: originál změněn/odstraněn nebo poškozen dočasný snapshot během náhledu | FILE_CHANGED; žádný finanční commit, žádný tichý fallback |
| IMP-21 | STORED_SNAPSHOT: původní soubor odstraněn i nahrazen jinými byty | Opakování čte jen uložený BLOB, 0 nových zdrojů při stejném parseru; nový run a správná provenance |
| IMP-22 | STORED_SNAPSHOT: po náhledu chybí BLOB nebo nesedí hash/velikost/dočasná kopie | SNAPSHOT_INVALID; žádný finanční commit |
| IMP-23 | Opakování uloženého odmítnutého importu | Nový preflight nad aktuální DB/parserem, původní odmítnutí beze změny; bez úplného BLOB akce zakázána |
| REC-01 | Cash +50 / Booking +50 EUR | Nula, Vyřízeno |
| REC-02 | Cash +50 / bank +10 / Booking +40 | Nula, jedinečné tři listy |
| REC-03 | Cash +25 +25 / bank +50 | Nula, ruční N:1 |
| REC-04 | Booking +50 a −50 různé identity | Nula, vnitrozdrojově vyřízeno |
| REC-05 | Bank +1 a −1 CZK | Nula |
| REC-06 | Bank +10 + Booking +40 | Jeden otevřený kořen, rozdíl −50; přidat cash +50 → nula |
| REC-07 | Cash +50 / Booking +49.99 | 1 cent; nikdy Vyřízeno |
| REC-08 | EUR+CZK výběr | Oddělené součty; UI i služba i DB odmítnou společnou skupinu |
| REC-09 | Rozpojení rodiče cash + podskupina bank/Booking | Podskupina zachována jako jeden kořen |
| REC-10 | Rozložení této podskupiny | Původní bank/Booking listy opět volné |
| REC-11 | Dvojí vlastnictví, cyklus, ancestor+descendant | Odmítnout a rollback |
| REC-12 | Změna revision během náhledu | STALE_STATE; zachovat aktuální data |
| REC-13 | Undo po konfliktující následné akci | UNDO_CONFLICT, žádné odcizení listu |
| AUTO-01 | Import, start, refresh, filtr | 0 automaticky vytvořených skupin |
| AUTO-02 | Výslovné auto a jednoznačný helper řetězec | Vytvořit nulovou skupinu bez potvrzování po položkách |
| AUTO-03 | Dva kandidáti, dvě stejné částky nebo překryv komponent | Nic z nejednoznačné komponenty neuzavřít |
| AUTO-04 | Ruční otevřená skupina | Automatika nemění skupinu ani členy |
| AUTO-05 | Limit kombinací/search a záporné částky | Žádný falešný závěr jednoznačnosti z neúplného hledání |
| AUTO-06 | Opakované auto po reached_fixed_point=true při nezměněných vstupech dle 9.3 | 0 nových skupin; zrušený/přerušený běh tuto předpodmínku nesplňuje |
| AUTO-07 | Rozpojit auto a znovu spustit | Identický potlačený důkaz se znovu neuzavře |
| AUTO-08 | A.7: C odstraní dřívější nejednoznačnost B | V jediném spuštění vzniknou 2 skupiny, třetí kolo potvrdí ustálení, druhé spuštění 0 |
| AUTO-09 | 1 cashbook a 2 banky se stejným VS/částkou a přípustným datem | 0 C skupin, žádná volba podle data/SEQ; oba bankovní vrcholy soupeří o tentýž cashbook |
| AUTO-10 | 2 cashbook a 1 banka se stejným VS/částkou a přípustným datem | 0 C skupin, oboustrannost platí i pro silný VS |
| AUTO-11 | Potlačený kandidát soupeří s jiným kandidátem | Potlačení neodstraní nejednoznačnost a nedovolí slabý bypass ani D |
| AUTO-12 | B search limit před D, další kolo se změnou množiny | D nepovažuje neprohledání za absenci; přepočet pouze podle přesné referenční enumerace |
| AUTO-13 | STALE helper, současně nezávislé A a C_STRONG | B/C_WEAK/D zakázány; jednoznačné A/C_STRONG mohou vzniknout |
| UNDO-01 | Rozpojit auto → Undo → Redo dle A.8 | Členství i potlačení se mění atomicky; revision roste, otisk zůstává původní |
| UNDO-02 | Undo vytvoření auto → další auto, samostatně Undo vytvoření → Redo | První větev potlačí opětovný vznik; druhá obnoví historickou skupinu a stav F před Undo |
| UNDO-03 | Externě změněná suppression revision před kompenzací | UNDO_CONFLICT, žádná změna členství ani potlačení |
| UNDO-04 | Znovu povolit F → Undo → Redo | INACTIVE → ACTIVE → INACTIVE bez automatického spuštění a s monotónní revision |
| API-01 | Test připojení | Přesný URL prefix, GET /currency, obě X hlavičky, žádný Bearer |
| API-02 | Doklady a rezervace | Přesné rozdílné query namespace, obě expand[] |
| API-03 | Více stránek a duplicitní ID v téže reprezentaci | Stejný canonical payload deduplikovat; jiný payload téže reprezentace API_SNAPSHOT_CONFLICT |
| API-04 | Cursor cycle nebo has_more bez cursor | Ukončit chybou, ne nekonečné čekání |
| API-05 | 401/403, 429, timeout, 503, redirect | Chování kapitoly 8; žádný únik tokenu |
| API-06 | Konflikt reference ve dvou poznámkách | CONFLICT; žádná automatická volba prvního čísla |
| API-07 | Refresh helperu po uzavření skupiny | Finanční source hashes/členství/rozdíl beze změny |
| API-08 | Neúplný vztahový blok či prázdný detail | Stejný publikovaný graf, žádné vyřazení podle absence, globální STALE; staging se nepoužije |
| API-09 | LIST R1 jen id/code, DETAIL doplní arrival/source/notes | Legitimní doplnění; raw obě projekce a MERGED_ENTITY mají samostatné hashe |
| API-10 | Stejné společné pole rozdílné; explicitní null proti hodnotě | API_SNAPSHOT_CONFLICT; chybějící klíč proti hodnotě je naopak doplnění |
| API-11 | READY → refresh → timeout/cancel/crash | REFRESHING před requestem, potom STALE; staré snapshots a finanční skupiny zachovány |
| API-12 | STALE → úspěšný detail → úplný úspěšný sync | Detail sám ponechá STALE; pouze úplný sync vrátí READY |
| API-13 | Úplný povinný sync uspěje, financial-stats selže | Helper READY, doplňková chyba viditelná, compatibility FAILED; žádné tvrzení PASSED |
| API-14 | Test připojení selže oproti selhání Ověřit kompatibilitu | Samotný /currency test helper_state nemění; úplné ověření řídí 8.8 |
| API-15 | Mock, prázdné live kolekce a nevyužité detailové šablony | Mock nikdy LIVE_OBSERVATION; protokol 12 šablon rozlišuje PASS_EMPTY/UNEXERCISED/PARTIAL |
| API-16 | Identický úspěšný refresh po rozpojení auto | Vyšší epoch/revision, stejný obsahový fingerprint a stále účinné potlačení |
| API-17 | Změna tokenů nebo restore zálohy | Nový CURRENT context_id, prázdný published pointer a UNAVAILABLE; historie RETIRED, bez převzetí starého grafu |
| API-18 | R chybí v dřívějším bloku A, objeví se v B téhož FULL | Jedna aktivní R po celé publikaci, žádné průběžné vyřazení |
| API-19 | R chybí ve všech úplných blocích | R inactive a staré incidentní hrany inactive; historie i finanční skupiny zachovány |
| API-20 | Po prázdném bloku A selže blok B | Žádná nová generace ani změna active; původní published graf stejný, stav STALE |
| API-21 | Invoice chybí v seznamu, je načtena přes aktuální rezervaci | Aktivní úplná invoice a aktuální hrana; žádný falešný tombstone |
| API-22 | Potomek ztratí jednu / poslední aktuální cestu od kořene | Při jiné cestě zůstane active; bez jakékoli cesty inactive, i celý osiřelý podgraf |
| API-23 | Entity přesunuty mimo celý rozsah; později se znovu objeví | Nezjištěné inactive bez tvrzení serverového smazání; pozdější FULL je může znovu aktivovat |
| API-24 | A→B tokeny, shodná I1/R1 i kódy, v B chybí původní vztahy | READY B nesmí najít ani jednu entitu/hranu/override/currency map z A |
| API-25 | A→B→A tokeny a uložení shodné dvojice | Tři odlišné kontexty; shodné opětovné uložení poslední dvojice je no-op |
| API-26 | Opožděná odpověď nebo resume ze starého kontextu | API_CONTEXT_CHANGED/odmítnutí resume; beze změny current grafu, stavu i cache |
| API-27 | Jediná reference bez override, platné ACCEPT, platné REJECT | AUTO_CONFIRMED / MANUAL_ACCEPT / REJECTED dle A.11; REJECT blokuje i jediný kandidát |
| API-28 | Podklady aktivního ACCEPT nebo REJECT se změní na jediného kandidáta | REVIEW_REQUIRED; žádný fallback na automatické potvrzení |
| API-29 | Zrušení rozhodnutí a Undo v původním / jiném kontextu | Zrušení vrátí vyhodnocení raw kandidátů; Undo kontextové, v RETIRED UNDO_CONFLICT |
| API-30 | Neaktivní entita nebo REJECTED/REVIEW_REQUIRED reference | B/C_WEAK/D nesmějí použít neplatnou vazbu jako důkaz absence |
| API-31 | Cílený GET dříve neaktivní R při READY | Jen raw náhled, stejné active/published/epoch; žádná reaktivace bez FULL nebo aktuální vztahové cesty |
| API-32 | FULL prázdné platné seznamy, shodný obsah v opakovaných bězích | Nový prázdný graf READY, staré obchodní entity inactive; raw snapshots deduplikované jen v témže kontextu |
| API-33 | Pád před / po atomickém přepnutí generation pointeru | Viditelný celý původní / celý nový graf, nikdy směs generací |
| UI-01 | Jednotný seznam+fulltext+historie | Tytéž objekty a tytéž akce z registru |
| UI-02 | Filtr skrývá vybranou položku | Výběr trvá, UI uvádí skryté vybrané |
| UI-03 | Vyhledání člena skupiny | Jeden kořen s odkazem na nalezený list |
| UI-04 | CZK/EUR KPI a agregáty | Žádné směšování měn ani dvojí započtení |
| UI-05 | Tokeny pouze v Nastavení, čistý Windows účet | Instalace/spuštění/import bez externí konfigurace |
| EXP-01 | CSV/XLSX důkaz víceúrovňové skupiny | Každý list jednou, contribution součet správný, ID s nulami zachována |
| EXP-02 | Prázdný export/aktuální filtr/selection mimo filtr | Hlavičky vždy, správná explicitní množina |
| EXP-03 | Text =HYPERLINK a česká diakritika | Bez vykonatelného vzorce, čitelný PDF/XLSX |
| EXP-04 | Všech 18 datových sad, včetně 0 řádků | Přesně hlavičky 14.3 včetně mechanického _decimal a typů; žádné ad hoc sloupce |
| EXP-05 | Audit bez finanční mutace; chyba před vytvořením source_id | Předepsané nullable/JSON hodnoty, úplné audit_events/import_diagnostics schéma |
| EXP-06 | Více helper hran a 2 importní výskyty téhož finančního listu | Více provenance řádků, finanční list a součet právě jednou |
| EXP-07 | CSV ZIP, XLSX a filtrovaná část Booking payout | Přesné sady, pořadí, row_counts; FILTERED_PARTIAL a součty jen vybraných řádků |
| EXP-08 | Stejné externí ID ve dvou kontextech/generacích a historický skupinový důkaz | Explicitní kontexty/generace ve schématu, žádné sloučení řádků, historie usable_for_new_auto=false |
| EXP-09 | REJECT s override_valid=true a CONFIRMED bez override | Export rozlišuje REJECTED/effective_candidate=null od AUTO_CONFIRMED se skutečnou referencí |
| OPS-01 | Pád procesu ve všech transakčních hranicích | Žádný osiřelý finanční objekt nebo půl skupiny |
| OPS-02 | Backup→restore do čistého profilu | Finanční data, skupiny, filtry a audit shodné; tokeny pouze znovu v UI |
| OPS-03 | Poškozená záloha, disk full, nedostupná složka | Původní data nepoškozena, zotavovací cesta v UI |
| OPS-04 | Druhá instance | Aktivovat původní okno, žádný druhý writer |

## 18. Kvalita, výkonnost a předání programu

Povinné testy: jednotkové pro normalizaci/identity/money/reference/stromy; integrační nad skutečnou SQLite pro celé transakce, duplicate/conflict a obnovu; HTTP kontraktní s přesným mock transportem; vlastnostní testy idempotence, měnové homogenity, zachování sum a kompenzačních příkazů; GUI end-to-end přes skutečné PySide widgety; test zabaleného instalátoru na čistém Windows profilu. Mock API ověřuje klienta, nepředstírá live úspěch. Čtení API se ověří s provozní dvojicí tokenů zadanou do UI, tokeny se nepřikládají k test reportu.

Referenční zátěž: Windows 11 x64, 4 CPU jádra, 16 GiB RAM, SSD, 100 000 finančních listů a 20 000 skupin. První stránka filtrovaného seznamu do 1 s p95, změna výběru/průběžný součet do 200 ms p95, otevření skupiny s 1000 listy do 2 s; GUI bez blokace event loop delší než 100 ms v běžné práci. Import 100 000 tabulkových řádků do 120 s a do 2 GiB RAM; velmi velký soubor nevyvolá pád procesu. Automatické párování poskytuje průběh nejméně každou sekundu a lze přerušit mezi komponentami. Latence externí API se do lokálních limitů nepočítá a musí být v měření oddělená. Tyto hodnoty jsou akceptační limity, nikoli zde naměřená tvrzení.

Programátor předá: úplný zdrojový kód, reprodukovatelný lock/build, Windows instalátor, migrační mechanismus, automatické testy, ověřovací protokol s přesnými výsledky a build hashem a stručnou nápovědu přímo v UI. Tento SSOT zůstává autoritou; pomocné build/test soubory nesmějí zavést jiné obchodní pravidlo. Žádná migrace z jiné aplikace ani přístup k externímu repozitáři není podmínkou instalace nové prázdné aplikace.

Odborné posouzení musí ověřit: srozumitelné moduly a rozhraní; jednu autoritu každého pravidla; korektní transaction boundaries; žádné široké `except: pass`; bezpečné chyby a obnovu; omezení paměti/souběhu; úplnou dostupnost funkcí z UI; absenci mrtvých handlerů, TODO v produkčních cestách, placeholderů a hardcoded úspěchů; čitelný a udržovatelný kód. Kritická větev nesmí být netestovaná jen proto, že nesnižuje číselný coverage pod zvolený práh.

Převzetí vyžaduje všechny scénáře kapitoly 17, ověřený skutečný import dat přílohy B, kladný výsledek obnovy zálohy, prokázané živé GET připojení a pravdivý endpointový protokol podle 8.2 a praktický průchod celým pracovním tokem v instalované aplikaci. Živý protokol PASSED pro všech 12 šablon je podmínkou tvrzení o ověření celého BetterHotel kontraktu. PARTIAL může doložit funkční prázdné větve a umožnit používání aplikace s úplnými helpery, ale nepředstavuje úplné ověření polí všech endpointů. Bez provozních tokenů nebo dat pro konkrétní větev zůstává její živé ověření neprovedené; programátor je nesmí označit za splněné lokálním mockem. Jakýkoli neprovedený test nebo neověřené live spojení je v protokolu výslovně označeno; nesmí být nahrazeno tvrzením „hotovo“. Známý problém bránící splnění zde stanoveného chování znamená nedokončený úkol, i kdyby formální checklist byl vyplněný.

## Příloha A — samostatné kontraktní příklady

### A.1 Karetní pohyby pro malé end-to-end testy

Následující JSON představuje řádky XLS listu Worksheet v pořadí 11 sloupců. Jde o syntetické doplnění testů hraničního chování stejného schématu; autoritou skutečného formátu zůstávají dva XLS v příloze B. Tato data lze uložit do BIFF8 testovacím generátorem, bez závislosti na dalším vzoru. Nejde o soubor, který uživatel musí vytvářet ručně.

```json
[
 ["Vystaveno","Pohyb","Číslo","Označení","Klient","Příjem","Výdaj","Měna","Forma úhrady","Variabilní symbol","Vystavil"],
 ["7.9.2026 12:00:00","Příjem","","Úhrada dokladu FA20260001","Testovací host","50,00",0,"EUR","Kartou","20260001","Recepce"],
 ["7.9.2026 12:01:00","Příjem","","Úhrada dokladu FA20260002","Testovací host","25,00",0,"EUR","Kartou","20260002","Recepce"],
 ["7.9.2026 12:02:00","Příjem","","Úhrada dokladu FA20260002","Testovací host","25,00",0,"EUR","Kartou","20260002","Recepce"],
 ["7.9.2026 12:03:00","Výdaj","","[STORNO] Úhrada dokladu FA20260003","Testovací host",0,"10,00","EUR","Kartou","20260003","Recepce"],
 ["7.9.2026 12:04:00","Příjem","PPD20269999","Hotovostní příjem","Testovací host","500,00",0,"CZK","Hotově","","Recepce"]
]
```

Výsledek: čtyři finanční listy, signed částky 5000, 2500, 2500, −1000 EUR minor; jeden hotovostní ignorovaný. První cashbook identity se hashují přes přesný JSON:

```json
["2026-09-07T12:00:00","INCOME","FA20260001","20260001",false]
```

Peníze v canonical content jsou integer; `issued_local` má zde sekundy bez frakce, datumové sloupce ISO, `time_precision="SECOND"`, prázdné cashbook_number=null. Každý XLS/CSV timestamp s explicitními sekundami používá tento stejný tvar. Nenulová frakce sekundy, pokud ji formát dodá, se ukládá s šesti pozicemi a precision MICROSECOND; při nulové frakci je SECOND. Oprava/název souboru ani fyzické číslo řádku identitu nemění.

### A.2 Booking CSV a refundace

```csv
Type,Booking number,Check-in,Checkout,Guest name,Payments service provider,Reservation status,Currency,Payment status,Amount,Payout date,Payout ID
Reservation,1234567890,"Sep 7, 2026","Sep 8, 2026",Test Guest,Booking.com B.V.,ok,EUR,Paid Online,50.00,"Sep 10, 2026",TEST-PAYOUT-A
Reservation,1234567891,"Sep 7, 2026","Sep 8, 2026",Test Guest,Booking.com B.V.,ok,EUR,Paid Online,50.00,"Sep 10, 2026",TEST-PAYOUT-A
Reservation,1234567892,"Sep 7, 2026","Sep 8, 2026",Test Guest,Booking.com B.V.,ok,EUR,Paid Online,10.00,"Sep 10, 2026",TEST-PAYOUT-A
Reservation,1234567892,"Sep 7, 2026","Sep 8, 2026",Test Guest,Booking.com B.V.,ok,EUR,Paid Online,-10.00,"Sep 17, 2026",TEST-PAYOUT-B
```

Čtyři různé source_identity; signed součet 10000 EUR minor; dva poslední řádky mohou být vnitrozdrojová nulová skupina. Změna Amount prvního řádku na 49.99 při stejné identitě musí odmítnout celý import. Změna payout ID je jiná identita; takto je formát definován, nejedná se o revizi známého řádku.

### A.3 Terminál CSV

```csv
Typ transakce,ID Terminálu,ID POS,Datum a čas vzniku,Čas připsání na server,Datum zaúčtování,Částka,Cashback,Spropitné,Měna,ARN kód,DCC,Číslo karty/Číslo účtu,Autoriz. kód,Var. symbol,Var. symbol 2,SEQ ID,Vydavatel karty,Způsob načtení karty,Obchodní místo,Adresa obchodního místa
Prodej,TEST-TERM,TEST-POS,07.09.2026 12:00:00,07.09.2026 12:00:01,08.09.2026,50.00,,,EUR,,,411111******1111,000001,20260001,,000001,VISA,K,Test Hotel,Test Adresa
Prodej,TEST-TERM,TEST-POS,07.09.2026 13:00:00,07.09.2026 13:00:01,08.09.2026,1.00,,,CZK,,,411111******1111,000002,,,000002,VISA,K,Test Hotel,Test Adresa
Storno,TEST-TERM,TEST-POS,07.09.2026 13:05:00,07.09.2026 13:05:01,08.09.2026,1.00,,,CZK,,,411111******1111,000002,,,000002,VISA,K,Test Hotel,Test Adresa
```

Tři finanční listy, bank contribution −5000 EUR, −100 a +100 CZK. Dvojice terminal/SEQ `TEST-TERM/000002` vytváří dvě event identity SALE/REVERSAL. Identita prvního se hashují přes JSON `["TEST-TERM","000001","SALE"]`. Neexistující ARN a prázdný DCC nejsou chyby.

### A.4 Mock BetterHotel — úplný malý řetězec

ID a tokeny v této ukázce jsou testovací zástupné hodnoty. Mock musí odmítat jakýkoli non-GET požadavek a kontrolovat, že nepřišel Bearer. Tato syntetická mapa stanoví minimální odpovědi endpointů pouze pro LOCAL_CONTRACT_TEST, nikdy LIVE_OBSERVATION; pro oba rezervované ID se používají stejné obálky a prázdné doplňkové kolekce, pokud není uvedeno jinak.

```json
{
 "/currency": {"data":[{"id":"1","iso_code":"CZK"},{"id":"2","iso_code":"EUR"}]},
 "/invoice": {"data":[
   {"id":"I1","code":"FA20260001","date":"2026-09-07T10:00:00Z","currency":"2","total":"50.00","pay_method":2},
   {"id":"I2","code":"FA20260002","date":"2026-09-07T10:01:00Z","currency":"2","total":"50.00","pay_method":2}
 ],"meta":{"has_more":false,"total_count":2}},
 "/invoice/I1": {"data":{"id":"I1","code":"FA20260001","date":"2026-09-07T10:00:00Z","currency":"2","total":"50.00","pay_method":2}},
 "/invoice/I2": {"data":{"id":"I2","code":"FA20260002","date":"2026-09-07T10:01:00Z","currency":"2","total":"50.00","pay_method":2}},
 "/reservation": {"data":[{"id":"R1","code":"101"},{"id":"R2","code":"102"}],"meta":{"has_more":false,"total_count":2}},
 "/reservation/R1": {"data":{"id":"R1","code":"101","arrival":"2026-09-07","departure":"2026-09-08","reservation_source":{"id":"B","name":"Booking.com"},"reservation_note":[{"channel":"Original ID: 1234567890"}]}},
 "/reservation/R2": {"data":{"id":"R2","code":"102","arrival":"2026-09-07","departure":"2026-09-08","reservation_source":{"id":"B","name":"Booking.com"},"reservation_note":[{"channel":"Channel reservation id = 1234567891"}]}},
 "/reservation/R1/invoice": {"data":[{"id":"I1"}]},
 "/reservation/R2/invoice": {"data":[{"id":"I2"}]},
 "/reservation/R1/bill": {"data":[]},
 "/reservation/R2/bill": {"data":[]},
 "/reservation/R1/security-deposit": {"data":[]},
 "/reservation/R2/security-deposit": {"data":[]},
 "/financial-stats": {"data":{}}
}
```

Po A.1+A.2+helper sync: prvních 50 EUR cashbook se propojí přes I1/R1 na Booking 1234567890. Dva cashbook po 25 EUR přes I2/R2 na Booking 1234567891 vytvoří skupinu N:1. Samotný −10 EUR cashbook bez helper I3 se nedopočítává; zůstává nevyřízený. Pro izolované testy pravidla C použít A.1+A.3 bez pomocné Booking reference; automatika páruje přes přesný VS.

Stránkovací fixture: první `/invoice?...&count=25` vrátí `data:[I1],meta:{has_more:true,cursor:"NEXT",total_count:2}`, druhý se stejnými filtry a `cursor=NEXT` vrátí `[I2],has_more:false`. Varianta druhé odpovědi s `has_more:true,cursor:"NEXT"` musí vyvolat API_CURSOR_CYCLE. Opakované I1 ve stejné LIST reprezentaci se stejným obsahem je duplicate; s jiným total je nekonzistentní blok. LIST rezervace `{id:"R1",code:"101"}` a DETAIL stejného R1 s dalšími poli jsou legitimní doplnění podle 8.3; DETAIL s code="999" by proti seznamu code="101" byl API_SNAPSHOT_CONFLICT. Samotný rozdílný raw hash LIST a DETAIL není chyba. Nepředávat reálné tokeny do mock logu.

Rozšířené helper fixture pro bill: odpověď `/reservation/R1/bill` je `{data:[{id:"B1"}]}`; `/bill/B1` vrátí `{id:"B1",currency:"2",total:"50.00",balance:"0.00",is_closed:true}`; `/bill/B1/bill-item` vrátí `{data:[{id:"BI1"}]}`; `/bill-item/BI1` vrátí `{id:"BI1",amount:"50.00",currency:"2"}`; `/reservation/R1/security-deposit` vrátí `{data:[{id:"SD1",amount:"20.00",currency:"2",status:"held"}]}`. Rodičovská identita se bere z URL. Po této synchronizaci se počet finančních listů ani jejich součet nezmění.

### A.5 Závazné negativní varianty

Základní fixture měnit vždy právě v jedné věci: chybějící měna; 1.005; dvě současně nenulové income/expense; rozdílná měna téže identity; neznámá forma úhrady; rozdílný klient téže identity; dvě reference v channel; chybějící currency map; více detailových objektů; kombinace EUR/CZK; použitý člen; cyklus; nenulová skupina při Close; ztráta přístupových práv k datové složce. Očekávané chyby vyplývají přímo z kapitol 4–15 a musí být testovány přes stejnou aplikační cestu jako GUI.

### A.6 Testy vlastností

Pro libovolnou platnou sadu zdrojů musí platit `import(import(DB,S),S)` má stejnou finanční projekci jako `import(DB,S)`. Permutace řádků a souborů nemění množinu source_identity ani výsledné součty. Přidání identického výskytu nesmí změnit žádný finanční součet. Seskupení a jeho korektní Undo zachovává všechny zdrojové hashe a součet listů po měnách. Při libovolné sekvenci příkazů neexistuje list ve dvou kořenech. Vnořování/rozložení mění projekci kořenů, ale ne množinu a hodnotu finančních listů.


### A.7 Pevný bod a oboustrannost — úplný malý scénář

Izolovaná prázdná finanční DB. Všechny čtyři listy jsou EUR, jejich datum je 2026-09-07; cashbook časy 12:00 a 12:01, banka 12:02. Částky níže jsou signed minor, nikoli contribution. Číselník a všechny helper kolekce jsou úspěšně dokončené, helper_state=READY, žádné override ani potlačení. Pro B existují dva různé jednoznačné doklady I1 a I2, každý přes potvrzenou vztahovou hranu patří do téže rezervace R1, kanál booking.com a jediná reference 1234567890. Jiné listy ani kandidáty nejsou.

| List | Typ | signed_amount_minor | VS | Doklad / Booking reference |
|---|---|---:|---|---|
| C1 | CASHBOOK_CARD | 5000 | 20260001 | FA20260001 → I1 → R1 |
| C2 | CASHBOOK_CARD | 5000 | 20260002 | FA20260002 → I2 → R1 |
| B1 | BOOKING | 5000 | nepoužívá se | 1234567890, payout TEST-FIXPOINT |
| T1 | BANK_CARD SALE | 5000 | 20260001 | terminal TEST-FP, SEQ 000001 |

První kolo: A nic; B najde {C1,B1} a {C2,B1}, tedy nic neuzavře; C_STRONG vytvoří {C1,T1}; C_WEAK/D nic. Druhé kolo: B má právě {C2,B1} a vytvoří ji. Třetí kolo: 0 nových, reached_fixed_point=true. Celkem 2 vyřízené skupiny, 4 listy, po měně rozdíl 0. Následující spuštění má jedno kolo a 0 skupin.

Pro izolovanou nejednoznačnost silného C použít pouze C1 a dvě banky T1/T2 s různými SEQ, obě signed=5000, VS=20260001 a datem v okně. Výsledek je 0 skupin bez ohledu na pořadí/importní historii. Obrácená varianta má dva cashbook s různým vydaným časem a tedy různou source_identity, oběma VS=20260001 a signed=5000, a jedinou T1: také 0. Žádná z těchto nejednoznačností není slabým kandidátem.

### A.8 Potlačení a vratnost — závazná stavová stopa

Výchozí auto skupina G je aktivní, otisk F uložen v jejím důkazu a potlačení F logicky ABSENT. Číselné revision níže jsou pro zcela nový řádek potlačení; existující řádek používá svůj dosavadní čítač.

| Krok | G | Aktivní členství | F | suppression revision |
|---|---|---|---|---:|
| Počáteční stav | ACTIVE | původní děti | ABSENT | neexistuje |
| Ruční rozpojení | DISSOLVED | žádné | ACTIVE | 1 |
| Undo rozpojení | ACTIVE | přesně původní děti | INACTIVE tombstone pro ABSENT | 2 |
| Redo rozpojení | DISSOLVED | žádné | ACTIVE | 3 |
| Nový běh automatiky se stejnými důkazovými hodnotami | DISSOLVED | žádné | ACTIVE | 3 |

Poslední krok vytvoří 0 skupin a není Redo. Platí i po úspěšném obsahově identickém helper refreshe; načítací čas/epoch není součást F. Samostatná větev začíná z počátečního stavu: Undo vzniku G vytvoří ACTIVE F revision=1; okamžité Redo obnoví G a logicky původní ABSENT jako INACTIVE revision=2. Změní-li mezi dvěma kroky jiný příkaz F nebo členství, celý kompenzační krok se odmítne. Všechny existující finanční source hashes zůstávají po celou stopu stejné.


### A.9 Přesun a zmizení — závazná stavová stopa

Kontext K1, FULL generace G1, dva bloky [2026-09-01,2026-09-07] a [2026-09-08,2026-09-14]. G1 má kořeny R1 a I1; R1 byla vrácena prvním blokem, má invoice hranu na I1 a bill hranu na B1. B1 nemá jiného rodiče ani seznamový kořen. V G2 první blok R1 nevrátí, druhý vrátí stejnou R1 s arrival=2026-09-10; její aktuální invoice kolekce obsahuje I1 a bill kolekce je prázdná. I1 v seznamu invoice chybí, ale její vztahový detail uspěje. Všechny ostatní povinné kolekce jsou platné a úplné.

Po prvním bloku: published stále G1, stav REFRESHING, žádné vyřazení. Po celé G2: R1 i I1 active=true, hrana R1→I1 active=true, B1 a R1→B1 inactive. G1 a finanční důkazy na ni zůstávají beze změny. Varianta s chybou druhého bloku: G2 se nepublikuje, G1 zůstane obsahově stejná, stav STALE; R1 ani B1 se na základě prvního bloku nevyřadí. Následující úplná G3 s oběma prázdnými seznamy vyřadí R1/I1/B1 z aktivní množiny. Nové pozorování R1 v G4 stejného K1 obnoví tutéž doménovou identitu; do jejího nového obsahu se nepřimíchají chybějící pole G1.

### A.10 Kontexty — stejná ID nejsou stejný důkaz

K1 má READY graf: currency ID 2=EUR, invoice I1/code FA20260001, reservation R1/kanál booking.com, hranu R1→I1, reference 1234567890 a ACCEPT této reference. Skupina G si uložila K1 a jeho generation_id. Uložení odlišné dvojice tokenů založí K2 UNAVAILABLE s prázdným grafem. FULL K2 vrátí currency ID 2=CZK, invoice I1/code FA20260001 a R1 stejného externího ID, ale prázdnou invoice kolekci a žádnou Booking poznámku.

Po READY K2 jsou jeho měna 2=CZK, žádná R1→I1 hrana, reference MISSING, žádný aktivní override. Ani shodné externí ID ani FA kód nesmějí doplnit vazbu, měnu nebo ACCEPT z K1. G se nadále zobrazuje se svým historickým důkazem K1, bez přepočtu a bez vydávání za aktuální helper vazbu. Opětovné uložení první dvojice tokenů založí K3; neaktivuje K1. Pozdní odpověď jobu K1 se odmítne bez změny K2/K3.

### A.11 Rozhodovací příklady Booking reference

Všechny varianty jsou samostatné, rezervace je aktivní/complete v CURRENT publikovaném READY grafu a má kanál booking.com, pokud řádek neurčuje jinak. Čísla jsou 1234567890 a 1234567891. `H` je přesný candidate_set_hash aktuální množiny; `H_old` je odlišný hash. „Dovoleno“ znamená použitelnou referenci, nikoli automaticky splněnou částku nebo jednoznačnost finanční kombinace.

| Kandidáti | Aktivní override | Výsledek | Dovoleno |
|---|---|---|---|
| [1234567890] | žádný | AUTO_CONFIRMED, effective=1234567890 | ano |
| [1234567890,1234567891] | ACCEPT 1234567891, hash H | MANUAL_ACCEPT, effective=1234567891 | ano |
| [1234567890] | REJECT, candidate=null, hash H | REJECTED, override_valid=true, effective=null | ne |
| [1234567890,1234567891] | REJECT, candidate=null, hash H | REJECTED, effective=null | ne pro oba kandidáty |
| [1234567890] | dřívější ACCEPT, hash H_old | REVIEW_REQUIRED, effective=null | ne |
| [1234567890] | dřívější REJECT, hash H_old | REVIEW_REQUIRED, effective=null | ne |
| [1234567890] | zrušený REJECT, active=false | AUTO_CONFIRMED, effective=1234567890 | ano |
| [1234567890,1234567891] | žádný | CONFLICT, effective=null | ne |
| [] | žádný | MISSING, effective=null | ne |
| [1234567890], jiný kanál | žádný | CHANNEL_BLOCKED, effective=null | ne |
| [1234567890], historický kontext či neaktivní entita | libovolný | INACTIVE_CONTEXT_OR_ENTITY, effective=null | ne |

U všech zamítavých výsledků historické raw reference zůstávají viditelné. REJECTED ani REVIEW_REQUIRED neopravňuje přesunout cashbook do C_WEAK nebo uvolnit Booking pro D. Změna textu poznámky, která zachová kandidáty, kanál a parser_version, zachová H; rozhodnutí přežije takový refresh bez nového potvrzení.

## Příloha B — vložené ověřovací soubory

Tato příloha obsahuje úplné původní byty autoritativních vstupů. Kódování gzip+base64 slouží pouze ke kompaktnímu vložení binárních XLS/XLSX a CSV do jediného Markdownu. Po dekódování vzniknou přesné soubory pro test skutečného parseru, včetně zvláštností OLE, fyzických buněk a původních znaků. Originální osobní údaje jsou součástí testovacích podkladů; nesmějí být kopírovány do veřejné dokumentace, telemetry nebo diagnostiky.

| Vložený název | Význam |
|---|---|
| cashbook_year.xls | Pokladní pos_records, 1.1.2026–9.9.2026 |
| cashbook_week.xls | Pokladní pos_records, 7.9.2026–13.9.2026 |
| booking_a.csv | Výplata Booking z 20.8.2026 |
| booking_b.csv | Výplata Booking z 27.8.2026 |
| terminal.xlsx | Terminálové transakce červenec 2026 |

Žádné jiné pokladní vzory nejsou součástí kontraktu. Následující samostatný standard-library Python skript lze zkopírovat do `extract_ssot_fixtures.py` a spustit `python extract_ssot_fixtures.py KajovoKarty_SSOT.md fixtures`. Nemá síťové požadavky a nevyžaduje tokeny. Pět bloků `fixture-json` níže je jeho jediný vstup. Shoda SHA-256 se kontroluje před uložením.

```python
import base64
import gzip
import hashlib
import json
from pathlib import Path
import re
import sys

ssot = Path(sys.argv[1]).read_text(encoding="utf-8")
destination = Path(sys.argv[2])
blocks = re.findall(r"^```fixture-json\n(.*?)^```$", ssot, re.M | re.S)
expected = {"cashbook_year.xls", "cashbook_week.xls", "booking_a.csv",
            "booking_b.csv", "terminal.xlsx"}
records = [json.loads(block) for block in blocks]
if len(records) != 5 or {r["filename"] for r in records} != expected:
    raise ValueError("SSOT neobsahuje právě všech pět různých ověřovacích souborů")
prepared = []
for record in records:
    if record["encoding"] != "gzip+base64":
        raise ValueError("Neznámé kódování")
    compressed = base64.b64decode("".join(record["data"]), validate=True)
    raw = gzip.decompress(compressed)
    if len(raw) != record["size_bytes"]:
        raise ValueError("Neshodná velikost: " + record["filename"])
    if hashlib.sha256(raw).hexdigest() != record["sha256"]:
        raise ValueError("Neshodný hash: " + record["filename"])
    prepared.append((record["filename"], raw))
destination.mkdir(parents=True, exist_ok=True)
for name, raw in prepared:
    target = destination / name
    if target.exists() and target.read_bytes() != raw:
        raise FileExistsError("Cíl obsahuje jiná data: " + str(target))
    target.write_bytes(raw)
    print(name, len(raw), hashlib.sha256(raw).hexdigest())
```

### B. cashbook_year.xls

```fixture-json
{
  "filename": "cashbook_year.xls",
  "encoding": "gzip+base64",
  "size_bytes": 445440,
  "sha256": "740a03d474b07b3bffabb59d232126a766eddde6ddc5afcbb3a771b08161c4c7",
  "data": [
    "H4sIAAAAAAACA+y9a4xl13Umdi5ZbJJSd5OUSEojylRZlt8kp877HFsasapf1V39clezyWbgiW5X3e66Xbfvbd1bVVQ1YkF5+FeA",
    "IJlBPGGQIJgkCBAEMJwHEAMzP6wf+WFARmYQDIIYMeIOnEGEAQEnToTMQDSz97fWPo97z9773H3KQBCYzequ+zhrrf1eez2+9Y/+",
    "+1f+9O//l1956s399+ves95ffvaid6ry3vPi5zef5Rcv0z898fOXn332mfz9b4vP/mXx8x3x0xc/98TPjvjZFT+f/fV//5/8T47f",
    "M+LnWR7H58S/p3is//Kvu+f/9//9pVi5p3rPzC9/rOs//e3/6P/85zf2Xv4v/p0XvF/9xf/6f1oT7/0+zw35+bs8dzbFz4r42RM/",
    "L4ifH4if0+Ln3xM/Z8TPfyp+vih+fo+//2fiy2+Kf78sft4bHwwPRoPd1e3H00F/d7Y3GBxI/m/yFvPeeH88+Wi8ek58ejCZat+X",
    "svzg1/638L9690961d+f9cz/mdr/zD/5o3/yH7zzxst/9++J9r/1z39Xtv8fcht73O4viZ+b4ufz4ucDlu073F7ZH6+Ln8fcD9/j",
    "fvm3Kv1A8p3G8x7Tafr3zZeJ5+fEz/uT6T511OmXidKbzPHi4HA4Gg1mq7uD1Z3+aOdwBAY9fftffEGQOPWc9w/O/Oj5fyy+eErI",
    "tCFo/t7Kt7wv4Bv/8Oenr2XcJx8883Xw8wXH/xk98W8z7ed757y+N/KG3j1vKv7+U+9VvP9/f7bqeX9QcFv56/f/at7veYb3/1T+",
    "JZfowvunaDa/uPJ3n1mRC/ezv+P9rx6NtjzUcazzX/KMxzviF7nC1V8/+AH+9uQvf/AHfyD++YH38cefeR+H98VXf+T9SHz/vvjz",
    "mfziffH6R5/huc+YJtH7AZP7ATEU35HP/Ug8/9lnH3sfi9effSyeFXQ/+9HHXnj/My/80Y/E++Lb8udj8XNfkL//sfc7v/M7nviC",
    "F34s3gjF/+LnY/yI90LxrHjjt72veP/5fytn8ou9972JmLH73kys14H4c+D9sPeC+PG8B/+05/1ub0X0VW/lS6Kf1DL6sveG97Oi",
    "Cz9fLq0zvy7//ndPyQX7z7w17yXP+/Nfwien/lxuc2dWaKGe4Ud6/PtLXu/P5bd+6q2urvxNz/uPX5ZLvLfq3fGOhUQHYk0dCZnG",
    "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",
    "2BpZrYm2NO2YYnA2eEceoHEzmF4VvEeporXoLK6hsg5dinDPyWJxiE4qYy+Gpg6LbIAhEbZTh9YGZqYWmCb5/FyApMImWmMsvxhu",
    "aw2TFnGEkSr1be9pXP0+xMj1i3J0lOb2sFruPnM77mW8+SkJGKDwgFbLEltNl/IyWbeV9DHVQR5CGxiB/DUoXEP2n/Uks895nvfi",
    "Cy973qmXvX9w5kfP/2Px9qkVz/sV7xnxya/i739N/N3zfuC94Kn//lXxzg9XXvWeFb/3XqN//nV899/A378gvnsf//3Tb/9i5fdf",
    "Kmj879/+5crvf19CvgkRe/jzjPfBMx88E+K//+Hb6t+e0I+fEc/8lrgoyf++8eJL+Fe+lk9VXz8j/lRfPyv+VF+viD/V18+JP9XX",
    "p8Sf6uvnxZ/q6xfEn+rrF8Wf6uvPiT/V158Xf9Tr/1DIJlrwzFm8+nunRNeJw8bzPsVYeEKj8IpXPalfFK+eEa+eKV49K149W7xa",
    "Ea9WilfPiVfPFa9OiVenilfPi1fPF69eEK9eKF69KF69WLz6nHgFKZ6RT39evJLvS3leEq88ftUTr54rXj0rXp0uXq2IV7Jtz4rW",
    "9sS3XvJ++5/9xu+/+Sf336V3TnkvFXOKnnhevHO2ePWCePVS8fyL9O3f++72bJ0+/5x452X+9jOQ65XiVVWuZyDXF4pXUq4vMt1n",
    "INe//7H475cfvkvvzMv1TE2uZ2pyPaPk+gMl1zM1uZ6tyfVsTa5nIderxSsp12tM91nIhYXz5F95l96Zl+vZmlzP1uR6Vsn1j5Rc",
    "z9bkWoFcrxevqnKtQK4vFa+kXF9muiuQ63P/43/y+Fv/2d95l96Zl2ulJtdKTa4VJdefK7lWanI9V5PruZpcz0Guv1G8knJ9hek+",
    "B7mwWezceZfemZfruZpcz9Xkek7J5U1Zrudqcp2qyXWqJtcpyPVG8UrK9VWme6qcX9/9zrv0zrxcp2pynarJdUrJ9bKS61RNruch",
    "188Ur6pyPQ+53ixeSbm+xnSfh1yv/u6lp0/+r7/9Lr0zL9fzNbmer8n1vJJrVcn1fE2uFyDXavGqKtcLkOtni1dSrq8z3Rcg163f",
    "f1NsFR+8S+/My/VCTa4XanK9oORaU3K9UJPrRcj1c8WrqlwvQq5vFK+kXD/PdF+EXN+SE/8P/8136Z15uV6syfXi/0vWXYdtUTVh",
    "AOepV+nu7u7upbu7U0QRpERABKS7EURQkG5UlFQRFJEQUBADBQUVExBQ7O/bOWdm597jf7Pj8/K75mzMxtkFV3J2eexKDq4U5Coi",
    "ke9Kkij6/6io/UspSJksWY/OL5ZtVd/kfWkxySeUyywR6YdrPfMLX1pc/r4vLSGRdqUkV0mJtCsluUrZfyWlcU3ed4ldKcGV0nGl",
    "DFw3nvPML7QrJbhSgisVuUpLpMcxFUnKSOQrytp/MxUpjt0r1nNhjTGeWRIex1QwjqlgHFPxOLblcUwFrtTkKieRdqUmV3mJfFcF",
    "+3dTk4tW+5XTPLMk7EoNrtTgSs2uvuxKDa404EoDrjTkqiiR76pk/26aoF7j+3lmSdiVBlxpwJWGXcPZlQZcaclVWSLtSkuuKhL5",
    "rqr276YN1qYTz3lmSdiVFtamtOBKy67J7EoLrnTkqiaRdqUjV3WJfFcN+3fTkWuEv6M419IzS8KudFCvdOBKx65F7EoHrvTkqimR",
    "dqUnVy2JfFdt+3fTB/1X6oWeWRJ2pQdXenCll/6LXenBlQFcGcCVgVx1JPJdde3fzUAuv51I0WWwZ5aEXRnAlQFcGaT/YlcGcGUE",
    "V0ZwZSSXJ5Hvqmf/bsagz7HrfUbHlRFcGcGVUfovdmUEVyZy1ZdIuzKRq4FEvquh/buZyPXb/zfHo58O98ySsCsTuDKBKxO7rrIr",
    "E7gygyszuDKTq5FEvqux/buZg+N2vyGeWRJ2ZQZXZnBllr6QXZnBlQVcWcCVhVxNJPJdTe3fzRL0OelMvbI4rizgygKuLNIXjrKu",
    "LODKCq6s4MpKrmYS+a7m9u9mJddTPuxke88sCbuygisruLJKX8iurODKBq5s4MpGrhYS+a6W9u9mC/roDuY8LZvjygaubODKJn0h",
    "u7KBKzu4soMrO7laSeS7Wtu/m51cG/6/m7h0c7JnloRd2cGVHVzZpS9kV3Zw5SBXG4m0Kwe52krku9rZv5sjqNeoYZ5ZEnblAFcO",
    "cOWQvpBdOcCVk1ztJdKunOTqIJHv6mj/bs7g+DhrqWeWhF054fiYE1w5pc9hV05w5SJXJ4m0Kxe5Okvku7rYv5tLdYGtPbMk7MoF",
    "9coFrlzS57ArF7hyk6urRNqVm1zdJPJd3e3fzR24tjzrmSVhV26oV25w5ZY+h125wZWHXD0k0q481Ef3lMhX9pLIV/a2/0qeQDnm",
    "uGeWhJV5QJlHemjzf3PXw8o8oMxLyj4S6W4/Lyn72r+U156FlCy11nb7eaHbz+t0+3kDacv1nvmFluaFbj8vuPKRq59E2pWPXP3t",
    "v5LPuu5MYFc+cOVzXPkC16DNnvmFduUDVz5w5SfXAIm0Kz+5Btp/Jb9xeeerT903rr7J+66HJB925Q9cXVd45hfalR9c+cFVgFyD",
    "JNJrWwGSPCyRrxhs/80CpPh/b3GvWK7GnlkSXr8KwNZZALaCAtK98vpVAFwFwVUQXAXJ9YhEvutR+3cLBmffTzfxzJKwqyC4CoKr",
    "ILvWsqsguAqBqxC4CpFriES+6zH7dws5R/FCjqsQuAqBq5B01ewqBK7C5BoqkXYVJtcwiXzX4/bvFg666pQjPbMk7CoMrsLgKixd",
    "NbsKg6sIuIqAqwi5hkvku0bYv1skOFouHeeZJWFXEXAVAVcR6arZVQRcRck1UiLtKkquURL5rtH27xZ11vuijqsouIqCq6h01ewq",
    "Cq5i4CoGrmLkekIi3zXG/t1iQbe/dZRnloRdxcBVDFzFpKtmVzFwFSfXkxLp/Vdx2n+NtX+puL26UyXZB/vN/qs47L+KO/uv4oE0",
    "1RLP/ELvv4rD/qs4uEqQa5xEul4lyDVeIt/1lES+aYIVlAhMw1d4Zkm4eiXAVAKOliWklx1tq1cClCVJ+bREWlmSlBMl8pWTJPKV",
    "k+2/UtLp1Eo6ypKgLAnKktLZsrIkKZ+x/3cpUk6RSCtLkWuqRL5rmv27pQJXt7OeWRJ2lQJXKVj3Sklny65S4CpNrukSaVdpcs2Q",
    "yHfNtH+3dHBF/dOHPLMk7CoN20RpcJWWzpZdpcFVhlyzJNKuMuSaLZHvmmP/bplgW+1kXGUcVxlwlQFXGels2VUGXGXJNVci7SpL",
    "rnkS+a759u+WDc7Mn+nvmSVhV1lwlQVXWels2VUWtoJy5FogkXaVI9dCiXzXIvt3y5GruL/T7drBM0vCrnLgKgeuctLLsqscuMqT",
    "a7FE2lWets4lEvnKpRL5ymX2Xymv9iEzPbMkrCwPW0F52DrLy/UDVpYHZQVQVgBlBVIul8hXPmv/bgVn31bBcVUAVwVwVZDrB+yq",
    "AK6K5FohkXZVJMlKifx6PWf/bkVy+QfSnmfN/dSKjqsijGpFGNWK0kGyqyK4KpFrlUTaVYnq9bxEvnK1RL5yjf1XKjn73EqOshJU",
    "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",
    "KdtFONLKceRqbyXjAskR89zwOEcyDiTjoF7j5I4qS8aBZDxJOkQ40pLxJOloJeOdbn+8IxkPkvEgGS/nSiwZD0eep8xcxghHWvKU",
    "mcsoOXr60LqeCp5pSNnUM0vCrqdgjXoKXE/J2RG7ngLXBDOXMcKRdk0wcxklR3MZrWuC8wzIBMc1AVwTwDVBzo7YNQFcT5u5jBGO",
    "tOtpcvWUnO/qZV1Pk6up/xhWYopnloRdT8M4Pg3XeJ6Ws6Ox1vU07Eknkqt3hCPtmkiuPpLzXX3t353odFwTHddEcE2Eek2UsyN2",
    "TQTXJDN7McKRdk0iV3/J+a4B1jVJXRNb75klYdckcE0C1yTp79k1CVyTyTUwwpF2TSbXQ5LzXYOsa3LwNN06846LyY5rMqxfk8E1",
    "Wfp7dk0G1zPkejjCkXY9Q67BkvNdj1jXM+rs2zxb94zjegZcz4DrGeno2fUMuKaQ69EIR9o1xcwSlBzNErSuKeqI+LhnloRdU2Ac",
    "p4BrinT07JoCrqlmNl6EI+2aamYJSo5mCVrX1GBOva3XVMc1Feo1FVxTpaNn11TYT0wj1/AIR9o1jVwjJKfrNS14qvtiI88sCbum",
    "gWsauKZJZ8OuaeCabmbjRTjSrul0pB4lOV85WiL9rMV0dVTa6pklYeV0GNXpcKSeLn0OK6eDcgYpn4hwpJUzyDVGcr7rSVu9GcHe",
    "f4d5BneG45oB1ZsB1ZshfQ67ZoBrJrnGRjjSffRMqt44K5nJb4Raz/39TOjvZzp99EzVRy/2zC90BWdCHz0TtoJZ5Bof4Ui7ZpHr",
    "KeuaZc+HWv/MrlngmuW4ZgWudAs98wvtmgWuWeCaDa7Z4JpNrgnWNZvrVXWTdc0G12zHNVs9473aM7/Qrtngmg2uOWb2YoQjvX7N",
    "IclEyfmKSVY5x9n7z3HWrzmwfs2B9WuOdKi8fs0B11xyTY5wpF1zyfWM5HzXFOua69yhnOu45kJ15oJrrvSr7JoLrnnkmhrhSLvm",
    "kWua5PQ14XmqjzZvTJznuOaBax645kn3yq55sD3ON/MoIxxp13wzj1JydP5oXfOdO6fzHdd8cM0H13y548au+eBaYOZRRjjSrgVm",
    "HqXktGtBsP96zMwRX+C4FsD6tQBcC6SrZtcCcC0k15wIR9q1kFxzJafXr4XO+rXQcS2Eei0E10Lpqtm1EFyLyDUvwpF2LSLXfMn5",
    "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",
    "gnqdAtcpOS9g1ymo12kztzjOkXadpr3GIcn5ysMS+co3bPVOO0+fnXaUp0F5GvYap6UbZ+VpqN4ZM6M3zpFWniHlW5LzlUckoi9s",
    "2X/ljHPEOuMoz4DyDCjPSA/MyjNQyw9I+XacI70P+YCUR229PrDfbdi9ofk5M0/gA5gn8IGzV/kgkC5b7JlfaOkH0B99AK6z5ivJ",
    "cY6066z5SrJ1nbV9m/cZ95NnoW8767jOqvl3z3vmF9p1FlxnwXWOXO/GOdKjeo4kxyXnK96zynPOnJ5zzjieg231HGwT5+QsYY4d",
    "x3PgOk+uE3GOtOu8mcMrOeo8rOu885zSecd1HqpzHu6FnWdX1/n2Ht15uBf2IblOxTnSrg/NrF3J0axd6/pQud7yzJKw60NwfQiu",
    "D6Uj4nuaH4LrIzNrN86Rdn1ErrOS813nrOsjdQ9lp2eWhF0fgesjcH0UXFOzro/AdcHM041zpF0XzDxdydFsLPt3LwSuteb7Gxcc",
    "1wVYvy6A6wK7bvA4XgDXRTNPN86Rdl0k1wXJadfFwJXOrF8XHddFcF0E10V2Hb6w3bgugutjM083zpHeT3xs5unakfvYnnd+Vn6/",
    "3U98DPuJj539xMdqP2Fmmn4MI/sx7Cc+hu3xkpmnG+dI1+uSmacrOZqnKxHN07XmS87XwS851bsE1bsEe/9L0n/zXuMSKD8x83Tj",
    "HGnlJ2aeruR85RcS+covrfITdX1yumeWhJWfQOU+AeUn0n+z8hNQfmpmx8Y50spPSXlVcr7yK4noKqpVfurcXf/UUX4KtfwUlJ/K",
    "lsvKT0H5GSmvxTnSys9IeV1y9H1gieh9elb5mTNf8TNH+RnU8jNQfibXxln5GSg/N98HjnOklZ+T64bkdPU+J9exe/7JjLnX/rnj",
    "+hyq9zkcvz6X3pxdn4PrspkrG+dIuy6bubKSo7my1nVZXVM1x9XLjusyuC6D67L05uy6DK4vzFzZOEfa9QW5fpacdn2h9sePemZJ",
    "2PUFuL4A1xfSm7PrC3B9ab4IHOdIu76kte2m5HzlLYl85W2r/FLNH1/lmSVh5Zewtn0Ja9uX0qmz8ktQXiHlr3GO9N75CinvWMkV",
    "u3ceO5z3zldg73zF2TtfCaSVzBPyV0B6BfbOV8B1lVx34xxp11Vy3bOuq07XexW63quO66rT9V4F11VwXQXXV2bWbpwjPapfkeR3",
    "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",
    "Wdtx1QZXbXDVllFtdtUGVx1ypYpxpF11yJVacr4rjXXVUU8nzDfl6jiuOuCqA646cr9nVx1w1SXXYzGOtKsuuR6XnO9Ka111E+Ub",
    "tUPN6F5dx1UXXHXBVVdGtdlVF1yfkOuJGEfa9Qm50knOd6W3rk+Ct5bGm+9BfeK4PgHXJ+D6REa12fUJuOqR68kYR9pVj1wZJOe7",
    "nrKuekE9md4cX/UcVz1w1QNXPRnVZlc9cNUn19MxjrSrPrkyWkl9p9de35HUhytDfZDUl4qIJfVB0oAkz8Q40pIGJMkkOb+FMltX",
    "g+A9pevmPbgGjqsBtFADcDWQiohdDcDVkFxZYhxpV0NyZZWc78pmXQ0TZZWtJlU9syXe1RBcDcHVUCoidjUEVyNyPRvjSLsakes5",
    "ydGbI9bVKKgg8zzlmS3xrkbgagSuRjKOza5G4GpMrudjHOmeZmO6W75gJY3NXTzXxSvrbplxs8aJeo57Y6fv2TiQNhnkmV/oI64x",
    "jE81hjtPE3A1AVcTcr1oXU3suFm5McPt+GcTGDdr4riaBK4BZg2FJuBqAq4m4GpKrhwxjrSrKblesq6mdlz2keLsagqupo6raeBK",
    "Y7563BRcTcHVFFzNwNUMXM3IldO6mtn2yn9zmHU1A1czx9VMjX+a9+qbgasZuJqBq7lZEyDGkXY1N2sCWFdz62q6mF3NwdXccTUP",
    "XEPMKjXNwdUcXM3B1QJcLcDVglyvWlcLux+P1GVXC3C1cFwtHFcLcLUAVwtwtTSrE8Q40q6WZnUC62rJz2/Ss6sluFo6rpaBK8ME",
    "z/xCu1qCqyW4WpErV4wj7WpFrtzW1YrH/Rduq7S2iMnrcf9WjqtV4Kpnvl7dClytwNUKXK3J9UaMI31dbU2uPJLzXXkl8k35rLm1",
    "Mg31zJb4q2xrMLWGPklrGePmq2xruMq2IeWbMY60sg0p80uO1iqQyFe+ZZVtVM+pt2e2xCvbgLINKNtIv5OVbUDZlpRvxzjSyrak",
    "fEdyvrKgRLSiglW2VTW2mW/b1lG2hTtWW1C2lX7nKqtsC8p2ZoWAGEda2Y6UhSXnKz2JdFu2c97Wa+co20FbtgNlO+mFsrIdHJft",
    "zXoBMY60sj0pi0rOVxaTyFcWt8r2Tl+5vaNsD8r2oGwv49+sbA/KDqQsEeNIKzuQq6TkfFcp6+rguDo4rg7g6gBVSQfpd7KrA7g6",
    "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"
  ]
}
```

### B. cashbook_week.xls

```fixture-json
{
  "filename": "cashbook_week.xls",
  "encoding": "gzip+base64",
  "size_bytes": 12290,
  "sha256": "07fbf36a11a324b228c27b07ca428a07a86c493e93ccc005aabec18ff40d9737",
  "data": [
    "H4sIAAAAAAACA+2aa2wcVxXHz+zOzr7tXdtp2gbcTZ9pU4L34cROmmaTtOmLNCamaYlaKU68jl1v7GA7LSmqaqDpFyQerRRYBIKW",
    "IiGQSngIFbVSXfhUZEQRKqgIpAShqogWWUj9UES7/M+5d67nrrNOssgfWmXGd2b+Z+/jd899zXjm1d9lTz/9k8vPUMO2hcL0fj1O",
    "XsDmIKzyRWbR9n69XufrSxDqF7cP1MbtF0II63aM4MxtHtX64vbh3t7HyPWcUOPwl3F9+sR3/v3untHMj74Wo/XX/ez1Htie132D",
    "fy/rvnM7goswihBDmEVIIXwDIY3wLEInwikd/++I3I3zpQj3TMyMzVQrw7nBo1OVoeHp0Uplhsvv1lPMPRPjE5MPT+R24teZyamm",
    "dmaZ/f4N1/+0/FcneB2m5bfl6h967bevfWvDmsxTX0f9b3z3Oa7/i7qOjq73aoQBhCTCfZrtgK7vqJ4Tj2o/fFb75csBPyi+lKQn",
    "nc/Zzt0ZVWYC4d7JqXHlqFRG5dStS9xVOTZWrVamc8OV3KGh6qFjVSnAaV7/eAxZeBF6IT0f/T0iemDagTxPuVupQ2K8eM3Uqj7t",
    "k/tCV0p5eZT4F/HEV3XeUWcnDVGVxuggTeF4mrrE/k49RzRnSnMv2lfG7tAy9tN84CG6xO6p3hx3nwq5PHDrT9LfSLU2L+qyrOsD",
    "r/FiwQWPcP8wOytH4ou5uTmcZqlWq1OtOIKo8zSP+CPY6xxxBHq+LunqOk+V36zOblYViDicbh7p6/Ua1aDrNaRFvvX5GhVH6lSc",
    "n4cdsTnUEEaQ/UiNTp48SYhAxRoMRfwh1CTAVkRaGE7Q5ZRvE08599Ikeuw4TWO8VrDP0MtODIHo8BsOPee48JXjroaf/GF0Ka2h",
    "tXBhcnFopbfwsUsG6D+ph9qJFtbJL94CT3MpVw3UlE7i6Ot2chY41n/pmURNTyUJcnK0j46DaAZj6iEwTYAxQs4ATqP44SCLlPM2",
    "YlRhAtkeegSRhijtcOS30a7OXTIaWc6wHKBPI8GDMBzh1PvoPRpGggfRLZzdtMbh1Clydok3jkDk6D8obApXwygyy0mGZGgPofwx",
    "ZM7l5IBwHNEPIlmVQYLcHKmDK7OJNlA/QgGeKdBGpOqhXtqM4yY59mCaA+AA3WKi5NF0/di7yOHsGIqdkMMPm9BBixKhF1cbsRcl",
    "pzUkbVlF9BwNoqJTwnAIV9OwpBw+j0sm04CZQphEyGGKxOS1n+5iN90OGxf3EFzSxk7kOleQaY52y/UMaj0By3izquVxtRloPcGq",
    "7bOqVpCf4+ztfWIqIZ8C9jzWC+dWlMb5z6C0SanKuEyt49IoNvo5GPLLM+S5WXvEjRyriB/4rI685/FLga4gZzvKPygunQm48gyu",
    "2TtH6Rh+5e7GjDeeP2VeKPs15WXk/Nl0Oa7rMNKPI1/Wx6B30XaTnOtQQsiQw219EJG4o4wBagJRVcMNScuH2af30F41KlQjTiLD",
    "plgFDaSO6Ffd7jZ3i9vj7kDIUcm92d3s7nRvcnvdrdq2FK2AFdlR3XAUWGPI+W4MjnHpokPSMUcBMb6cfzYCoSjHFv1T5AG0H+YB",
    "VH+7bpqjgrBBrnPn00w8SktmrLaAUeJ+vZfuoJ20B7dN3KerMsiGkHDsQvp1n3gk33zaKLXK2It7NPTzYfqHROMo3FWGZQo9J1Hf",
    "8kT5Vog28oR8JyJMSN+pyBJ1XLr6Mjz9S2efpTyFVng2qdzUksQz4l5EnJAZQWj6mgylohnhHSo9rxgVnXJpMX08Kw0KycNgOoIO",
    "MoWIt+F6GMucGjjnKLJkHNBCPfs5708hwgyWxyFZV3lCUf21KuRqGbngvLldMCvs0OtZRSo3jUr5JVSlwkN+jzuXs3gK7+Rey1Ma",
    "zybsqJ1ydUjAJuHCaRljyzisBFflzSzTpMcUW6ltYflCS6ZjNFmgCsEFqogOuFHGUkEvTyX5pbdZIQWZJ/J2IUtrVjo/T5f4Zm2/",
    "tJxqn0HpmJO4flA6ZY7auCkmdIc54Izh6gwd1lPdmeUxS/qOqKkvirx87YGrH5KBoNuz/yyuLcoMsOn8x1wv9ja+exqTlbEq2e9G",
    "m07L5MxD3eHCEuaBMWM9MN4g97br5fgFHB3czMfMI+bnYXnZ7VJPoqvU6YsS93E5Xou4I7K9se26wPU6k8eb264PXD9NV6KEYUbC",
    "HsJD6X2homx/2OafHaz3IaR5VO6yia6Ot8uZNacK6hD2oA5jD2oXe1BHsAe1hz2oo9iDOoY9qOPYgzqB3dffBgseK0LybCL/PHCk",
    "Bu+J7/3/uirl8L2PUSGokFFhqLBRLpRrVAQqYpQH5RkVhYoaFYOKGRWHihuVgEpo5ciTTNIoBypiVAgqZVQYKm2UC8V1DaPGDtIo",
    "L9DoE2Vl8XyLSRGFpd2oGK4zRiWgslqFhKnDKGbyjGKmTqOYqcsoZlqlmUKLTMZimH74y7JKEWQKWUwhiyksTJcYFWQKC9Nqo5jp",
    "UqOY6TJNEF7CFA74abisUgSZwhZT2GJyhelyo4Jt5wrFGqOY4iO6TFconrvtzCNdd+8pK0tja7lC8VGjmKLbpI+r2K++Mji9Xf0e",
    "5IoI1xVGBbkiwpUzirnW6nwji1x/rJSVpZErYnFFLK6Iz3Xa54pYXJ5wXWlUkMsTrquMYq6rdb7eYqsN/LysLI1cntVqnsXl+VwL",
    "PpdncUWF6xqjglxR4brWKOa6TucbFa63Pvl894n1+8vK0sgVtfwVtbiiPhf9RnNFLa6YcK0zKsgVkz5/vVFMeYNRTLlelxJb9N7c",
    "M2VlaaSMWd6LmT6vYmvKjE8ZsyjjQnmjUUHKuFB+zCim3GAUU35clxJfpHx8vqwsjZRxizJuUcZ9ypxPGbcoE0LZY1SQMiGUeaOY",
    "smAUUxZ1KYlFyh+cLCtLI2XCokxYlAmfssenTFiUSaEsGRWkTApXr1HMtVHnmxQutYA/UFaWRq6k1ROTVk9M+lxlnytpcan/t20y",
    "KsiVEq4+o5irX+ebEq7PbE386XsDe8vK0siVsrhSFlfK5xrwuVIWV9riSltcaeHabBRzbdH5poXr1++su/8rITVy00u40hZX2uJK",
    "+1wHfK60xdVmcbVZXG3CdZNRzLVV59smXN+sYXtlpqwsjVxtFlebxdXmcx31udosrnbhutmoIFe7jIJtRjFlWefbHlg3x8rK0sjV",
    "bvX7dqvft/tcsz5Xu8WVEa7tRgVX94xw7TCKuXYaFVzdM0tW98wi5elqWaUIUmas1T1jMWWF6Rajgr7KCtOtRjHTLqOY6TZNkA0w",
    "lcrK0ui5rNWiWctzWd9z3/U9lxXK23XsDqG8w6ig5zqE8k6jmPIunW/HEl91BLhKZZUiyNVh+arD8lWnUHzCqKCvOqXc3Uaxd+7W",
    "ZXYKxbNHMUFcdX9ZWRq902lRdFr9vdP3zinfO50WV5dw7ZF79augIvjlVxj1P86+XlavD9N0jcMYc5G5HY6ro3mSAbZbX7CjeXOe",
    "RHuLTvF4WRh1+bkithDT7ySSLpcXXhiQsyvvMRyKL2TO8voQ97eSjm8j1R2bu8CvQZ9MKbvjqneWg5Rc4Po+Rq7jOi/J6vySw/ny",
    "Fwi4DqtXm5mFjiXvK5XKynuSB9BDV6HduvgpY20wVkq/2JJ7YHkWIBmDnfSvK1Qu/C6Y787vlThv0YEltKEWaZ0A6dlpQytAG26R",
    "NmTarhlteAVo3RZp/Rf44aa07grQRlqkdXW5blPayArQei3SRnS5kaa03grQRluk9T9F85rSRleANtYibVSXG21KG1sB2niLtP5/",
    "12JNaeMrQJtokTbuf+bQlDaxArTJFmkTutxEU9rk/0l7c6iDfiHDo6zT8PalWAaBAjkR7kCwsnfpIdTFA9w7HFtNh2PBJd2RL8Me",
    "I0N+cfvQbntpUr54yOFBYEI+OTh+QekvweIR/JaU4ur2Qn+KtIsC3+L5Z8e/+5ClZ5CO0RF56cVl3wGKEfMNCr/P5xcszbd18s9c",
    "dXvADGcr/2zbm/rsf/1zUPwwfsH+48eT4PeU51M+x1h7tV//W1DuIfGBej1zYf7oa6F8VyY4//vHet33n6tvBfzvf2N6ik3o7xBT",
    "+jtG9Y8B9TIiKz5QXx926fw4vHfx09oPxPa5R/8Ha0UbdwIwAAA="
  ]
}
```

### B. booking_a.csv

```fixture-json
{
  "filename": "booking_a.csv",
  "encoding": "gzip+base64",
  "size_bytes": 3361,
  "sha256": "c0f37f085ced8d62586d210b1f0518a75be18ee8d8b99c5f6ac944e613756bc1",
  "data": [
    "H4sIAAAAAAACA5WWv2/cNhTH9wL9HwjNCsHfIsf4R+vGOcdw0qDNRusYHysd5VLSAZepRaduWTMFHbt1aIEiRSYju/wflVff+dzg",
    "DndvEUQJevzovS+/772YX7s8O2iayocrFPrppYtZfjhxZfXIh7ubpu/y7OvetR0KduqyPDu386kLXYtaF2e+dOg6NjM/XnyaXbjF",
    "Q9v5JqC2s13fpnh9jC6U8/sv7988njZ96P57nrZBY9st4y9W3xxlX37xIF4utRSccl6YPHvcXyGqcsQIU9lyae6Xz20YR4vOfeia",
    "7P4HcdlM0QF+ibO8qfLjby8WW/kxehZqH9LGnAps9F0wRlbBurPj87MX7tX0+vjSTr/78TMmapSk1BCyhCi2MR3Z4F2Nnto+7o9E",
    "eYEFASIRbYTUSq6Q5DakkY2lqy066l9Xzezmt/25mBFYMhiXooRzZgxhm7nWmfs+qeIKjTx66hw6nABKmCoB59KGGyEKzpcg4v9c",
    "a5U9aVr3Gh3H2l3acgKgkgpTqLAU4YoTLc3mbKmHVex8QM87++mdL6ubj5B0UZwCw8CkNEorXazkxbeBHbgYxihZR+gmDiJ6LbBm",
    "UCqihJZM6l3p+iq6ZFW+6ls0swGd9HXbAdiIwoZDPUIKYzQ1xS6BjXydkM6bN25aWQBUobAWQNUXTAvCuBSbodb5O3LBtxaduTa2",
    "HcwmCo51AXUJw6lWbHVeKNvKFTE6scG5gF7a1tX7YwlJMIeeR2mIUJpTugQh2/NVLqp42MQ4BzQfZrBRUOdSmhFDhdh8FNclHd7f",
    "/nL76/D38AENb4d/hr+GD7c/D38MH4c/b38CCI0xvOq+e0OmRiSMVIbtgrwzMotO47yG6UxRzIBdUvEiNSSiKN8Dq7r5vUtcn965",
    "BFbC2JKZFVA2YnSRXEMu9ZA0t4Xtwo4ri1752qcGDnAMrimWQMeQBZcmmZjgu6hObOwT1mlz1UcHUVc6ltBhRwhK0+DG5Wa7EA/n",
    "rzBHpzZ0kF7EkrTA5dNpHDTJWeVmq1gr7bS2qQ0dLq4ugLCoxAzYuBXThmmdJrBdWKM0FAbvk7DspI+2biHNiHOJKVjwaQbTQugl",
    "2mdD9APQ2v2wmO0b9MTOvIto1KT7O+Nwb/aHfKQ5FnsY2b/2WdyzIQ0AAA=="
  ]
}
```

### B. booking_b.csv

```fixture-json
{
  "filename": "booking_b.csv",
  "encoding": "gzip+base64",
  "size_bytes": 3936,
  "sha256": "2b76de6d3655718566bbf70b594b170fcfeb9709fc17cda9d5151d7a266eeba1",
  "data": [
    "H4sIAAAAAAACA52Xy27jNhSG9wX6DoTWHoH3yzLJDIpc3DHiToDOjrGZmJVMpbq4cHYt0GWeoc1qVn2Bbh2/V49Tx0kHdp2TjSHK",
    "IPnpP79+Hv0wvwm97LCqipiuSeqml6HOekeTMCrexfTvRdW1vey7LjQtSX4asl428PNpSG1DmlDP4iiQm7qaxfFqanYeVjd9G6tE",
    "mta3XQPrdXUd0mi+mbn552Badal9vA/bkLFv1+uvRsfvs2+/ebFeT3OjjeGS2l520F0TznuEU66z9VBthic+edKPy/sCwB7uqtni",
    "Pts8Zz6qpuQwv8izXlX0Pnw6X+0Yx+RjKmOC/TkzueXrNc3Tmqf2s/ssfh6IIRfx+NB9hUapNEoLZ9bz5P+inXYPd6HGYTFtcimR",
    "WEooIwx3T4qx/2KJzfDDzJOBn5WLvwqkWlLm2uKwlHNKU674Xqyz6jb6gvTnxcTHskKo5QS6iMoaaQXjgPM4j+ldWH2fxvW8IBex",
    "9WWMr8dSmuVgBhyWVlZSxQzbbnvxwlt11ZR+RpZ/Lu6vaoRaFiwvkFhSKWlBs6fHobuwDlILaXAw9tPm9UhCqdxRJBKlVAnBBd3n",
    "q3N/5Ze/kUF8+L0NBcLtlOUCSaUN41orKfV2qudyXkAmpFh4AiEx7hpkPnCXO4vNByods0rp7Y5/RjtZ/F3GrgHHX/slJh7AWRxL",
    "xeBZpNBm7Uhmd1GdhQRqXcRy4hMytpTLGcPGljYcqDaFpLu4BqGtybBb3scSE/A85xqbDRaAuHZ7kb6Po6oMcPLUt/4Xj6ASIpcG",
    "SaU4p9ZQp/Y5/u35rkyusL6CcGfcWCa3i/VM+d6nGEoy9D+NEVIBknZIJG2gqzFUrZGY2YX0aKmzVUuDIOJw3BhsiDrmDNjqKUuY",
    "24W0/LUrfHMLMl35ep4wTnfo4injmFZaGrOveB/LOAs1OP3SP9wt7hHprkUusI2fhoMKzLgp4FdqPVMez1ad37DtbqDDQtTQsZwZ",
    "bKxbaK8EfUqT3VAnFSQnYB1N6ti0Ea6AkvS9TyFhupo3ZLxxXDDJ+Hbjv0Rsws0E9iHDMAejtROE/w3PFX9DykOkKrVPvH6sRwFK",
    "GpJvq9nrqSzLqXyD+63Wdi/UMNStX3whP/rlHx7RAsJ5aLFJISVzijkn9kHBlwXE6SkcQIi30djcOGwDKI2AH7b3bTysrsc+vTvy",
    "qwY+QQ3rS59QatFXOP4ft3CCT2APAAA="
  ]
}
```

### B. terminal.xlsx

```fixture-json
{
  "filename": "terminal.xlsx",
  "encoding": "gzip+base64",
  "size_bytes": 17651,
  "sha256": "e720225215ba43778c27bf6db74370bc8ee86050e7018bc3cfb108541f03f00d",
  "data": [
    "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",
    "ncgsUZjTF3uYlDnbvLHKcxtmd/fpg3d1Gy/XlSGVZn62+F/P3DY3MsUw1PbNVu3cWqPvNnk7uV5dUF6N3H1vf3o/nu6cLq43nrZe",
    "dzbK7b96v26+3twOnl3eFdKtnl5rpG6tzrZe001Obm5q6/Ku+yzzrvHqnHTYdSb+mD273LptfpocnEyW28RvbMS/E0DUo+NSUwsc",
    "DVl9tNvnY2rzsI4zujucfV6/NXW7G+y9Xb2eJIlerWyc3L3k82l+fXEeurVfJFnvPd059/N+HVw/2/JK3W58rLyb9DuPz/rKs9ae",
    "6vPS4NX2fGrFcdaZs3G6vqwXvfvqMvJ6jtey/Ho+M9v7vL5zZnF3eJ8z5n1/neLyK3d0evd0nSH+S6dCWpHbfdPzNa+3f6Fy5utJ",
    "TM4Lg9p+QtkjPhk2TnzQ7M2vvejH6POJV5+bq0m+ka8KvxbnD/Ugb/32zzd92+j4tuhLagdPC932X8M3njhxsvQ6/Foxpl7X7Py4",
    "VXz5vDqebdqfW9q9NpIyhffNJlvPD29nr+lWK/VGv/tS7GQvbbq2bgodlFk7o8XpSDa4Vy49XZ7s3M6e4ut9VWvFnz193qebNFnZ",
    "ECnUQyA13xof7LRrkHPLhxqVxmj3FXdtfNTEU7o/rw15vLChFHF+XHzZBw52Um9k8wFjMbf7okX6avX2kKMDUWJy8uzF3XOD5+lc",
    "Kj1Zms8pAb+XV+z+OibXbRr7Z3C7bQT17v2mGYUfXo22zk+xxcAXAriireqfujUJfHo1zjkRto1O81GaxhSPq/hSwGb5i7yj30mB",
    "r+hzpvvtp07hVnFGb6SSrvalkhRWEYtQF3zZBfTp8PXvw1i5c3OTv1/tMzQ9N4eO5Dwrme/S0XlA2Awi485rvjiiSuzECkN+C9bT",
    "7XnEWFfgyhR9O0E4OtDVhodoL2WVjEJQhO/EgZi18ZFEUIyS1YxqOe30mRYo20pWIjX3cUSwjJJ1jMqJ8C2103Oesvq1a0+9eGol",
    "4Bxj+2v3p4RIrsJHS5VNhJXTjLrV5paDulLpzED3Xjo6sdlTHeHxke7dyZb2zvdra7ybHX6PTY8OqrpfRo3lNu16f5B5ojB26v4a",
    "Dcf/8EpV9+Jx6OH2oqzb9eLtd3N7NXn13uluZjuwIbSqn24lJ5DGtk4EQyuyXgRRq28lJ5qGbMXQn6ZgZfuD1lhdP5IWyYrhZ5q9",
    "ygwGzuJDKpmDMtNK5m+zLe750JmLu8Dzvj3gOZNW28xn2dOjRDJn20XgeXyrB/Dzdb16iX1nV7pRuu7LdHn0G/TNzzUuHNX397gH",
    "UyGXIAQ+cJ2APMTvEASZD9WB1VJcDvZH38e6+7qbA4sDUwNhIZMR9hDQESpwtLmaQMQ34/VAsjoIs0cc46YEE02O4ykPYW9ACErf",
    "E/hM2gJm2Ky1g3RKtBn4H9Kke5Y2Mt1uF2NtX8MNC6eofBRMEcimqKKcz4iUIJnEpSDrAOKba/lS6Vzq/Jrvp2AIEpdY+Gd6IB6M",
    "dUDLpk04Dq2/jda4tNOC1LwdpVVS9if6cDEuWAOuUyaFH1s+CxnqcKbwV5ZJYaRypghoPnjSllSJ6VX/2SHnJyp/5gkWfk4f7IN4",
    "F+gq0eRdG2lYnaTy48ptgEYy4J5SN4inI5wLs7UOBbIQYQJHGieDK4UzhaPJ3v5Q/0x/6/tId30gtn+ZpD9LCbVduFZRjbWOHg1I",
    "DSWIY31ZD16UIVwMLSkDf0sC0M4v84xH1yo4CGGl+YESaK7Nmi1Dc91wEEL75iAxkocz+eO41CUxk1MwA8NqDuwEFUlTH4/f60fR",
    "jqokobdQay2qSfmXSflr05RWySXH/VcXDJWAqeeOfB9k0Yun/KOt5B9tY4388/YxCXSePxpYh1higdOFLmR8T2nS5kxR/pbwe5a6",
    "zQ9mtQF5M/XOFk6QsOJSi+kqaLfujtAxo6Q/h3vA1InHHHGbguhHF256wIbejrIe3s2f7JjvjA2Cq3E/U2AAR6+aHwj9c1jqKy2j",
    "C31pD4hPCDrgMKDmzw7xl0tgRBIBGolTH0uBFlIGsi2Ywnda61aOxpwIa6SIa6TyQ9aY6o1zx9w8UJ7Wst8JcSfJ6FD27Bh+0kwD",
    "JPZYGClJMXHja3PFOl7WpTpJwY6N3aAMjl7LZPMsUN6OGopoFi5UEW32OFCmL8pxBuZazcEkFGYicX0XtLSIfFbcC8tXkjJLIkua",
    "oJGhGafWUW+pY26sq3I2OVyZgVecpjTPlS3dhfHBLu8J4KXrDCmEiFT9JGlSPgNS2SVkWsAwZdWiKgvKo3sHyYjbH5jUc9QWDWZY",
    "X9WyNHebbmCqe9kHcn2zaTpBQ0PPJAfiP4IDKEZVtULdUpgPY1mioIGhKruqDcTCk2UwdEnqh+/THWXO/jDKPOCbX9XiW8jqamph",
    "eLg2MzczNhOULyUFtE1KLamCZp0gsWeljwdmkrp+mrLsScoAnFJJNVtRvfRnWvJRrwFeJ7i0UZ6iei8SotJCVos40nrsyNFYMnBY",
    "Nb+HtZViPAKzL1RQVrG5dqul38loUm56NpIwzym5VFlUH1aImhVllatqDyZczi/ydqh40iipiu3Qh8YnHaZxLCNe1tHOH0fSVnjm",
    "7vA96Sc4SZlOoVBxgZSsuKQqpXO84/whApLHSFWVFX/a2DXGSFVkqnqqWrxhq7EDHV1iq4p0kopeC2oPb6wKUK47po5Jv9A/UPAT",
    "SkVj/yBETWVpeDg3k5oflu8kBfSqFEYSLc04DQ21jkZLg3Og8pE1Chsl989V0dLvpOKZ4JSa4JQuDZIhjFT2zAiB7IcZE73GfH1G",
    "mbhDglTCx2Vd97TQfZYmLtXFp2y9DNM3bp8SeEPyxzO0NPVNHxJU+W98Szl1y8sW8npyS0rLukcsFDS69WNGYJTnjtbi0i9SHiUc",
    "ati/m8NVa2rodCphc9UyVzvbWlhamB72zOTnN+cH5VNJLSbZxkia2BhqB7FhrpijWUMWl/GLlPLn16gehu6Z79iniJEyRcVeCXk9",
    "EuJRUk2+FCCVuszf80L33e5e+mCkr/gy4SBnDoMrpjHQ2OytzYAyzd7YgCsfl7DUVulNW6JwUbWRzgqWfvNozwxKqA9PqIdx7kOU",
    "1vhAbFJ+FuKeAa49WkKFh1EJrw4MBA3/KCCA7aW5YflHagHpHI11XWPcsF2XVysA+VRw/c4y1TyWWv+LCWXsek0uKpJSPReREVf0",
    "KeRJUOoom/8SBcCRlM5OTMCMy5jUu6IPAPE/kCQnML3qg0TNDsEdt6LJUpejpkvVLRS/bUlDEzr/Vq/aiRoVKNBAzQZZWzjtJ6En",
    "pMkOwYRQ39RzGpdXLsz39JaUVp5ql39xqY8Zse5q0UTC1hlu9ZjX72a4HetI+k/DKa6S8S6X5dKjYmZDW3jQxKRCa/gAbPwDjcGn",
    "1GgIV+cS5fVRIStrIE6Empu5uGphJUC9HFjXPJsyk3MawfY8nXSOZwJRcBRK60aFU6OsfmxrMJizTHamurSYNw630KJFmJrarekG",
    "a5gbuglGID3PJVqWBp/LbdmQm1afhI4QgZoJUBnXlBo1nTAfm7sMoO90sfzDwoR6UGorMPF7DYwTdWbYwlJb1amJ+SP/x65jDXET",
    "VUC1olkpc/jBKFfwXIBRX8kyvWShhlnTuL16zrJlmeWCiazNXuQAdVo/ExkseMX+2q22/GSNorxMeRo4ZVpQ7/txVodGztO18qm2",
    "l261vByN/Zs1fmvUYUUBFnX7SJ5R6YUb7vpqJikUqf2kgiTTJFpqHc00LU31lhpnm0OI4iI03twWmNWJ9SN/WEI0oJF/zJsKq93y",
    "uThzMHDeDcurDBIGYbhOvohi5E4bhHRQPWjKXPKb6B6P1QDZY+M3e4CcXhNrOfv+asZI52ysy557+g6rT9M4j3zcA5KBiGyPMgoE",
    "yhXM+Hh5Sn0bvSqYdlTUktcHIfu5rTtDpFL/XvJoUFo2GTjQgsL6iwvhhoXHAPXE8psO604s+USaLGbFrpkCIFkefJ5NsAFXN7Fa",
    "pztRN17tez5qcOoUvPZcJtrVAFVMopkqEiL1OXGQTomTu83lHlY9G7iYUq9JIuMXqWFlrWfOFbj0ggz1oMrLf/OzvOWGHXjIGBUU",
    "f/6c4WCZRh6LU5AtFyI1c+XXZSK08RW1FoKGNaxYb/Boo5NUs4YkWZpMjTR1zkbmeuZaZ4PDmZm1mZ6ZxHwrKTZxkXIZ7SpbLgzq",
    "N+S16ANnEF27ihbaFq4beSeFvpOhFX/3W8+Rl467saJ+OTREtSawNn0cN5fmTiaVdrH9Mw70+AHU8aB5bc7+uBHGW87zaEuuZOqL",
    "afri+V2aKHCGxMuO4zuYXkmgVnpnNf/Bn/Vh0As2ZgFBewVvzYzyuwJG5xOjqECuN9wZfnzxfMro9k2Yz9Q+qIBFlKEsY+kmUKUC",
    "1sCZhg/H5yCRFmuvawZmFMlxRFzQBRgrGXogZFf7wI4bmLoFnXI1rAIMysyB+BhmtQEGORl1GjiKNBt+jxDKOCcx1Sf1+f/TFTfJ",
    "WHDAH/PMimo/5Liqgluz4doNjTzOytDdcipdNbVmjl40BlMGDZGamzWnYe+NOYhKk1aepi/EYuugnqNh9pEUqTStniwFSNMClw8D",
    "AfSVIytrzfng+XsqGjg15gtp+kvV5g3/21rTYkDR23sxHEej4xgp+pFG3LSpw5ooYwMT1DLUmVppmmkaLVXOFha2FgaHIzP1+dh5",
    "OQtkZOqNmdDoaelvhkYmaoCk6LfxLGAGEA8wGGYOq8pUHastwGRwsPS+K6wUBFWmKqtvt96DY1LqhOUkPsFfmnsbjekrIFoKxtql",
    "Tyet1LrKKNYaZbV0deIWZjzKuPw0qJpIw97+YRtfHUfoTM22o6RBza3Ij7MLS4mJ2z7WmkWV1IqGDpgdR2A9YXEYz0+a6orfJl8G",
    "pQ4NL1kcfSLk929D2O68lZlH0N5NnMiIE2getUY2sh0VB5l0fANmtfLyM7kc4niS34c4dLiLJXciKwtQZWarN/kzNmaSJAvdmaSv",
    "9BtgnrpbDtWmsTWm1UYL1DNpaMu6XKNUQLgPAuGuOQprSLyh6nTiEMlzzb0wU5z/nxD253AKeoDNjPJ7AnZZsrsjCdkNcYgXYLR8",
    "ro8TPajx0lDVjz0EytCB9bIv0xg1OLocppYuKxDuAh/Taei4aSmq5nfiPKhdqeNsDD1uVjR0vzXHUstTVAGj9cIw+QQFFles5p7M",
    "cNnHiU+yFhcOQYrkGKcWzFClhpa1/tmUP6QNT0por57mD75pawBX5wbLc6ZlW6oGztf5vNW+FxAUsvo+dJH51WuAKGNI2WijdK//",
    "KCTmVvouKV8z3NIXOwSdlPTLd4KqFfW7L+N42AnZWwqqBz4XY8rc5pb5wUFESx+VsrQRqB4DayDeo8IqxmB7nHmTWd2A5hV7fANU",
    "oatbuRsMEi2TBatVZm6hpWEPa/bCGonUfDe/NBUygvqCORhaKVKj0iulZnQ5JFyzcA5kvLKb1rfOJEgiPkrvgf2m+qnhJA4Qdk3h",
    "RSRqPJq3qdp2u1m51/nWnIqi3glrZCILCE466YQGEs3SXpY6Z73zv9OGaPWsl62ep08VU2tAx7gZlKGqX7QCJwXqSzDjR39zmiqV",
    "zgg1j0J3fUW9TKNE/rITVDOmwiRTZsPm/Z7r/smupbfQuxmb7AIsUAjcNNV19Ayj9rNWA7s8qZh6KloyF79OR/TnqpEFmAaLoyuO",
    "LgQvMZ1rohKrDqs+0y6vISFqAd1X+ua+hdO3lGvoOxdDj3szswfkdXIWPksodVKrU9oTdZLVvrOjxtpWwesHoogENOAByxwHjwCt",
    "NBwGfY3H8KiwYDsYBjkQXs8MQhleX12cjwUfhiaVgmb1B4miwaqjRiRgNFQZqVLPfKgt3Zw4AUai4SleCCZVePmAKHGPERQ6Dgp6",
    "f7AC3qLhKJ/xGAQNXnrowrIzdN9IZvJ4hmbadNGvfGG4PaD0OlubCVC8lgrzV6mbnyVleidNk2Oz7XGz6qH7zeM5E0ORonbipblb",
    "fUNZHxg2KbiaUoVJ/4lsXNU6M9fR0tLfAw2NTHwPW61G0sQAwfQFGvgvHhXwJMteJEgigfy+Ths6/1a/SaWcaDcBYM/pXG8gP5na",
    "jln+Bl4Cji4bCgT5+rydmdtvnm+FNfKwgD1MHIMhYPl/AEJ168Ob14BAsPoNhND27WQT+pS78Ejo61FG4FBgrNX0LnrsgSLp/LdI",
    "Ov8tkprPA+Zi19yas5xWnQR4Rn3UWOqfTmmhFmBgQ0jT3oC5+gbMaSCK6VWZYauR4U0ju9ugDaXVmbVuWt39KikgIgzL18GrWxT1",
    "T9+MEzJsjaDnqvsjZoB2lYWDM0mrwnz/HGqYvqTz7OqqZm6L+jZXaP2G1Of00d24vgnYDOfCXMvRV3V0hWUoTYudpinpvIFgRZK/",
    "VRKcOYmczTTW1sfmP1w3G6Pm75KZzWlMU2MvKFwjw13pyzUJlIezQE4yKJM2YkhiSxnUX/448f8QOg9/hk52TYnJKe3YWiwFSAH6",
    "NaCaul/1lHYZB6E1ieJTfesbI9S/BXEmUgsBDdT17dVv6xIakyHLlAKOYuo7eqCR38IG4s0BbbrV4hrV4h6S/nWjq6NeOEqTZUvP",
    "5IhKoD6NEXE76XpACs523DR5o/Ic702RlPNW6ze7yDfdtmI8TGCLxNGVao1jF37pBLr6qpnr8pHyU8bV07kZWCdHlA0yGKCu9/0X",
    "Hp9mMTdzfkPQSjLQZzDUK/o/63GN6DuZUFEKfsQ/k4+nM6JOoC10rIFXaxqcjuo0bMIVrTkpUE9CWx8BlyUU5zYNoNR32uIeqQCl",
    "COP0JuBAbIFOIwGCNxJtWJC6U4F9QJ9XjsFwA96hBn/XIn5nS6RZrvsQP81PmgILdilND4mqVjOdA6jNmPg11ZH2+PiN/ohj5wbQ",
    "MpiKLNpMIvVrWK6KdKI6pk6IhSdBSiWwxvVN+IHbvANB+h3M3PtD0P8UdYp26Sl6ga57wEEdlbN00qse0fTduithwpkCU5UntqiH",
    "p39EsglFGmzZTQeB6lv9pl5Sk+GhRlG7PfUa9kEpKmvKAKM1IOCz/dZCmJM3leLHlNZc11b643R5igaEqswRDVDg0Qz1J6hiKV9D",
    "oX8VLfO+jvtTiF4rJudDy8+XuXRaA9V7n1wf0t5HQ+s/GAWFwd9F0R8/z3xhRW/JKdN0dVnv3WMDhuJ0WW2ALX3SXdwHLxziJI1P",
    "xx6WRv9uuePzWdsgnR1o24SauW8amr3Avb/6D5huRcPpB/1GdKVrbC0GA98Ofb6xeC0qV9Bgqah6Om+Bsgqcpje1Pp1tbIM+mVI2",
    "3vJnLK9Ys9RPwJYo27XJC1KvkEEsZWeCAGVRvYaVvwH1ar24CRXxf82etm1pKXqLp2OVwIXIACyFmnqetkEsgnuqP/14qWFPG2vr",
    "GwDgVxaRAps73i7RcJS9rUzNxZ9W4HzeO4to/inuFk0BUj7glDdoSrWGFkOD0YdXDnc7z6tXembR5xOVqx5635oVynwWgbm0OiXV",
    "rrXIKE4lMsXtNO1EzKPGSqN6IiHdwNLXH7aI8o+Fk6j04i64wcPFn6m52B3oTR0MRVYU+nryhrBXl/WJ17cEUf4aVJ2jPjYWoTXH",
    "IDIYqlJtkCDW7wrBGNXvTlG7AAhUTx1YGQMmG/l7qq/Oku4uo7/XI7nbIYaAUtNSM6lS6gypaWuUdyctbxOHPa75Ds5IpBaJ60eI",
    "IXnK13iRt5Vimd86bK5I9cJlgLpKmc/6KNAPMfcDEfSb7st/mI5N10WpcexuYBlrHb/YXrHK8ZZnojAUU0c0B4EMf51cPchgqLta",
    "42x5ODbTN9OcX5yfmg8rlZy0l4SeVEGto9UiQGlps+2u0+jU9g8BQ5iED4KlVLXmblC35v5tJ18LXd+TonrhOkCdBli/Mbt5813A",
    "XFv8xO9kHHNFy02Fw8jnBqVsBm4/R6SZzXLb7fKmFNlywClJFzR1UzxI7nSRxtgHDr6FNlh6iDx8IQqOMM20A6oGywVP3YbNSFlo",
    "3IUAej6oP4MZ/zNI2SyQ/VRqF656vhwzr05ctTQkveEduBh0JaHSfuvMPBVdfXT036t1RYN0dd3FU+rKqTVldW8DWIxY3271VHT+",
    "E/EFGKRRTRDDFn9Z4KqvYlA3Jq3w90prC5hq2kzg6VbtIOq8XXDl9gPozwn+1AkjEzDV0jBlW0HAtVY6JrBfOGC/4gsfdDGp4soH",
    "XE3MMIEywegsVrzhYSC5gy9wmkjjcQQDD9Onxek3XRGOhlNn0WvEuohlrmbBHmmoGn8ziy3z2YXlQh9mdWgPPtUGhoFvMYBiEjqm",
    "Rgy2zqtfZeG/ZWaTeqLy1G6E3273+SRCaRmkTluFtJroE8n9Bdrp03r0TBtfICSQj2fAWvdgfiv87KsXuNtRr11qm6M3ZqmVgFW3",
    "bYmp2f1tlrpur2vSbzqmoQPSsapRKzIdKn/Vd0wGuyBmYA4197gZweUYLuw3QnnT/4/o4ytuv/kvTQ0G6lry0x+rN10K/rFa0Dzn",
    "4jX9QaIVsqzFqsx9oIjR+HQDXMibgs8v0dqpvV0nqB7nqf7PwDR0g19dBioEimpXNyGgANKKOhVlDKlnD15bD100vMvlbs8h18Lb",
    "+SYR5MKrE6AjFfT7Gl2uQLUfP+51rdYfAWyiKY+bIAvrP1IHkA0FLv8OWawb0bHT8FlWd/ncLr71nW++3HdcNep/F6g2aM2vm2qb",
    "wYp66eVdPbxMKhWodFNYPjw3m0yW02tY3U9f3V+9s+vc9N0wbYz+et7Jk+mz7kuppKeTsOPR9vq0e/F4ffb44kdTnrzpOjnZGtLr",
    "57O84buWNNmio5OQ+H3W9s77V/TonR2d3wme3+bd9cvr3z43MoFLsKkKCQAMELw98/j7FqqzuYmNyR/177unJxrjEdhsqJ0YD3xw",
    "Tm5PLDvRpBvfJ63j10mMMxNw6htOFFSZGOPasFFASTluFMnz8pMF7XgSZvjfwbf/jIYmqTvEn/44vkRcvkuSbi2p6QofIfbSXlh4",
    "l+Xree18OdOe4imWAtsTl6TXIX/FkxG5lEIym+RnxU7O7C0nnhCJbAJtew9L/SS1+tXXEdlmGGpw6d29sPW3JHwJjlVK9H6o4Nim",
    "LlP2T5tkkYPiPcRf0QdxcAM3UtCp8hXLMYnjfukGGMq3DpJwXFXIkRl/fj7Nv+INwnpPMdcVeuWT/8HsPYSrt7oqVDWSzkg7sbAW",
    "7xiT6aCQt9wDnohgDyJNZ97r0/ZtP9HKyOeiNQKrIfifemTJ0JGIVJ6yvDzqMh/ADOStKn9aARKPm3zb9Y4XVR+YAVGiVTNz6Fpm",
    "7TPwjGUgkp2czndH7ZbLPdgPpVasjUI31RcfEo4QFy4CBTDazLdYyPtDrH5VzZ78tH7+kLBtZfXLs3gd9ijJFz6cXAJhcSq/Cijg",
    "1FoDpDHXHXrSDeiL1Bh3OWBqDBJ1LMOhpX4UaEdM6wxAAuT5w0kkuJtTtqA/CKC7IZNCZri3Gn8Q2B6X7wGDS6bMFyiGeZ3/OLXp",
    "LDyNLhpcVwNLjWwlNIInF8meOpzkB173APGjv9ZsEp/X5+WicT8aj8fvlxRro6rJ8Gm2seVI+8PlcWfna8/j8SK+Ls8LWeYDiW7K",
    "r2Q+v/urOz7dQjzVjNbt/kY5XV6fq+3Wypenw2ohr/Tcdyi8JAzoGyzeJ+vGDNRTBny83wvjMUVD1d+Tg64jzPtgaXRZwQrrNCE0",
    "6Linvxtt8k/ed6PRuiPmTe5juJ4nb/D3ipxG2JGF1FZxwsLDm4gv9nLkZXNgQ+Z0HF8XCUP7/uIN8VNSm7IVuWGsTUCBaBr1o7rn",
    "EZtraLWRixtU9VOLmGgGNGvsBu62C5JDi7E4QpnwSJCrOJyDRhPcZ3mtjuXWUxdMl/KWkGhrEmtYYdwBRIb6NXescdJwHcoQ8oKC",
    "XrfYSG3RM7pfQ303QZ/F5RhMdP0ig+yHtferdIkP1D4ZrBls5kYsiTpKIOhwuiEbkdUMIrQih5vJpku8T12a7CPMI7+ypT8MOGfw",
    "CikyC30nyRr8yNqt2rQpDdbory0TfwWm0DnWTJyUzFB7txMgi+RaLZ0+iN7awOFgKmbGW6/ohWEU/mUa0+h8wQwBltPa9J6b7UES",
    "rKwmUCfMBXy5uSQLhbqq8DjNJXyNtEdy2YfbBPtkWSuDIAtc0rCPzaIDQqFREUOW42OibmGuEIp7FP895P2284gLCGfkjzO7GU9i",
    "wYXl/KwgLj2MtfDN1ROGpWQ3uVY6AYivmhChz+U+TMJzaQRyKYQBoL0ijQSGQXwYCvsl6Olcu2S3BeO9gKBYlfM+Eg+jS6ecE+jX",
    "zJpBna4Mge4d1Sfe/AkyyWUOhe/WPc+Qo2l4aR/Z6DNIjjNcdOcz1FheXjtKluuSJ61SrzX32pIc2n18YjTJ6PSya4ZbuVv2Ueys",
    "76Wh8h8dBS4rpnTwQeyYd0DgjlwTziQqNP1roTpM4clg2XbFR90zhifDIm+JmQMX5DXYuAqJlHjQNiKhDzAPDdYl+z86H3fMcm8Y",
    "7dTNatCWVpgeCX4y5tWFUduZyo+jaFGdbHWjumnB55zXWcgHkbxlFsWMXxZVxhWdSw5EClrE+qbmSqbKjKvKnPBgUpSkoN0MKq0l",
    "Aq7bzOOuYHdvEOMa8w0LcvdevZ/ChowutzTAqSB244e0pSkgYWkUboh4XbnBVjtLUyfN0g7ZYhSKeN2aOJI58rsI+6hs7a5vUrXt",
    "HmH9mFKF+lnwWqTnjlCfZuwQtG122DAq8+UXLd/yDz3lI1Djmi9gnAMXLFkCZ1A3C0EHqBU6onGF2C86KSYDQSeEyPkIi3nxNQLS",
    "JHt4pA6jaqN6Ju9kmEPMV0fQCD5HLzSRTY0MmuKArSMwZklfiKcZsIkmFM6K6f9KoMrotLx0g6SSYA2xPxfbMTr3n7iXAaNAXxgd",
    "+WRE9H07O8PTSfo7mbWIscdLJnsK4wpLZY4zQv5O6ARRQiY5WWqhvUwOldPP2RHIAaUGU/uDFljEgiN/n3Olu3Gx+qsMgbT7VIvq",
    "cE6WdeOHLQSP3pInpPoyyWKtTqWIjOM0qYpAYZes93bsLpvb/PTSox9rpZXQK2ertk+s51hP4WBBe1Hq4X21MpFl5dqOhxEdP9aq",
    "4iKNtih+7OhgZLOrX+7WIYjGW8OfKEblTLA3G0dG9TmEN5bErhI5Gy4T/Wy3kRGf5NeJ2hBoS3qCLhlVpQdVIlA8BbU6L8gFV7rr",
    "q057w5kIaV81RE4bcujyDKigPyBqrVvcscK4u7xK2usJ7RcpqPwRsWLv46BXoY5xd8jSxqbMdt0h5u98tkgZaFq/XIyWNn+bjfST",
    "M0qwVusY1bPetp3twKVX1Omi6+4LM7u5WqtA+Sb53Mi6LWFRYsJ9lOk3PGXK0+wN25+Bt4FlkZ8SC3/G3oOulZ6uvPztw285Omv+",
    "TO8AAAjgKfwfadjJ2cPaxOn3w5sqq7Y7rEg+dFN+BEtmQXGGzQ2EFEWnUOr6reQxqAdUpAoIyLpg4RMjWieDJ5A/qW4HOVFNtCzS",
    "pJT4Un7EcDvtjdkn6N4oZkOaclaoBOdGIBEXUOo41Y9enDeKVHUV1SrPK5v3M3rr43aM+D0Rnp4IVKVzDVCDQs2b/JpYcRURV1tn",
    "kGiFXWcE54pijdNUT8M91Ow1X2+WUoxhh9sXVqyoElMfPqIhiEt79MFW1myYu4qDtUV8hy5ao+mzRGFjTuFviT9uHvRgbms4l54b",
    "3/3QF/0jcTrT9gT8+/t15jZDuUPa4bipo0iwoXOh8PfvB6INz8e5Yk37qiDPZkKulU9NCG1CKNvV0Gc8GAk7r79B7HB3D5mZ5FpN",
    "HRZeEMExDCsx6k7OipYyScKBcFGo3Un6qQatXk2dKWe56k29Q9MPwxHND2INLU27gcugyZBRGH5KhUdrY17DwqZsZnd3OoETWo/c",
    "JwmhRkhoQ3zVa1Gi89DiPY5y/2xw0MWBsZ03Q1r0A84DBtwkVQGceoq9k6eOIDZg5c452KkyYwPLM3T7xykGJ437qfoJa6C3qZpp",
    "E7ngL7SgQIqvqwQoIzH8ctaYBCOK6R90b+s+tFHIgVtRf//Q0eqUO19+nVMedDQ5mzabqarclMa+gfkRoMVAaLt2/Jrr8XmdLZ4y",
    "kHebxA18v4Bglf3G3XfrotAczwv0WPF600BhM+PiaytupoSAj5xEpi3xSsP296P1xMemAP41mBQ+QTz8eSuQ13ePs7pJY6hCITgK",
    "kDz8n8LGooV5h4PWSkcuPjY9PafLb74GqHEGR43wYCSV+iFj2R+/ZDRsLWst0oZ8zuIWGLFcmGqvaiwch/u631mTdk4KxZb1EMVn",
    "zsVv/Iv79aCEKo2rWt2Oz3WKWl/Yq5fpaf/mYX/3tiU0UKRJF6xWKgls1LgdPm7ZtH0dfZQegU3vo8yjX93JFvY76AjTUll+Izaj",
    "KuL79Fqa3vigQr42w2ye3Y7I/S06CVSIfhNM8FoOHbCIe5P3qBKodvu1Ny6KJChnw1xaXuI5Q34kOPfGJs3GAaVGFV+w0jQJJaq8",
    "CaEcx8A4/LquO/9W5OL/im0kgAYAEkkBANQ/o8vcwNHEWMnZ0cLW7HeQRWqOKxIPI3dw9ZxPfcvtFb3R08GFw05Jjerf0Fj6lIo5",
    "WQ7iEQsiocr2eQvLFa+rupDj7NNFNxu+N/K17oQli6KCHgy3gLQ/ZyulX+dTjeTq5tPOUU0T1nj6pfOVJUFjXzamjGyh2c6wXCXE",
    "eXTnsxAHeVpDVsZ88uzwwfx31zm4juX7U7uG9AKag3WJa0v7jYZaS3Zr2UkxNZdalswosp8/KmfvVdZnvl5/DR635i2ZTLueLmpv",
    "waEkXLsowZOD6D/86Tkz06E7M7AYf7lZKeY1Gl3HGJh5atpWu36GszkR7qorl/aw7VzHY+3WEHLZfbX1crztztz5QQ5dj7YyNSQE",
    "Uuy+sPL49qGkKCJk0kVpbU1mAONiu3fyp/ntzdcdjdpfjBprGPEt5qJOV6idSzrtvyZ79109ZyX2GRH56DqYT0Uy/TrU2PY/3hyK",
    "vNxPW/NmRq0Oby8+Da+G6JFVjZ214odH9HdO8te384jGP+45amrPXd+6inu6+Lm0BCK6Vq4eens39lc8f8uyQxs/nR/+ybhJ7KFM",
    "Tn86Ht3/YuW+e1vWUbw6vatY/XRZuLzoxzKLAgN6747aO334NQI3IyNLbnJ7h6qmNHNv0m1yL7eAtiDacH82n4D95/P69uh4L51T",
    "5JKWR9PjZa6joHEE4leS/ALJKy1JcjVyHSwNimSq6/Xuy/TziPZzBF18b3LX6Cvx/u2SNA0fSRGx+dndDf39021fWY5bKwfeZtth",
    "WdJ6/IdNKZTP5Aj7Nx46KUSbh/a8PNjP8Ly7p0sSKsmJ1Ylw96UEOY52J1CO/MscAMeX2a/X0eJelT3nLX4L7vaJVTOYqZ2kn5Xz",
    "kUEVT3pfpm1p4bwKWEMnpJe6LCvzNEryMyGx7zI/DtopwiZ5tXo5P+2tb5xxDb2cd3cTyeG/toXKJ07TRaSMx35OUdfyXBzsS2P0",
    "o828QK87Msw5fNXWDsKgkRTOKxoiMvmqkY8BAr9Q+oNOiyKDJhm9eUaA3UVia0D4i4YoLmxbehGVYL6NydY62/nmt/cTj7zzgfAp",
    "RwJao4WcFCDFFSNz5Qtqt69IIEqRahUnPMR1wo2tBGj4VoowRqe16tgXkZoR4mKfKkjcDWniHu03k/K3fUg4XLSzPCM/WSGXkChp",
    "yA+CkSbqmMrZf2hDrrsiRYQIgF3TpJBYPZQUCipOhJorKICY+xjLClqyAlvOgN26QqJDr8vqFDNAohnR5y4x4lY0nggVf51/6DCn",
    "CXn0Po4cUkvUhaeeRXnxxyVYY2l9qDJaYqGAixpRRkuDGK/QGLPf2VBznAyfnmOs7rFgOJK1AZ/Mo559USl60geFCrF9ghVk3Dw9",
    "EnxK5G9kk5coO9sFPj2Qn/FkFpJC9Rgss5Qk29cAC0SMRBqkSKj8YNhdkmBaaQmyt89ruZsBiWkCP8yRL3msAWG0OYrK/ZMHivLf",
    "c6GUmxMnWge3oUiFNSzsQNvm+7MSegR1qEiJIhl0JCT0rnxo08KWE5Q0osyzQuV9k9E4pSCLkXe4mKj3VwupPGnR+ME4FJFAeF6a",
    "KB5s24k+ZZBtGoypEaVok6XgsdRRbsl8KxMRvC6C9cTFJLgNqRcXbop7QNe/kgQT+AKTLcclYQ3VRZry/lORUjI5WxHVp43u8DAo",
    "E/ETdyQ6VIGV5hUo6pkftxs5ikYBkGowwxjvkVVDMQ4CANYZDNHuRLisFwRwhDCwq3XEeXotuWE8C4J6TCMVEqGD7l4yXFcpY7FX",
    "xmKEVEcJSwuMyLIUFFKF6ns7HBtwVDAH43U5wm6uw4Ox361FBLP3c7BoSJGL0CiK7S6nt8UrvHvajCD7tWWEzbOn6+jsoc9x+ESm",
    "wzDjiY7RoL/llcdofPS8IVIvK1UB0HkfvpvsYzelccqJtogJDa1RFPavOlos/Ul0MJwIJbTgfcEjFYuOPMWxN0ubyK6ZVSKF2qdi",
    "P1GLInmOdk78RVsqhTdbOSscSsp2ZBwMOaoQzdjsIATUKJaRvafzIkyIWIwa+/1r6MQLmX1A0pGAOj+fumVYtxRykZ3UdcSZSiJY",
    "zpK3MRR175cSInuyWuVQjmAh+5xG7XDu3DumiWhStKge5jrViJe6zw/SL215G+dL0Jyan9HS5IzhmspEiixzFJYc2GSNB6CxPMlO",
    "QFukuCjct4Ul+opgUbDQPRhjFfyhIJH8BcBoVtjrsPRWBrHiB95bUwjMyo+Z8slQkb8IJw+V61aRhwOssQozZ5/D4uX1HS4EE71V",
    "YxQnOcXVAsQZtoVz3D4G0AxC4cJFv6ujSBLhlSa6GqqH2iX0AKURQXa+t0TLXphBzqJZJ2fBA/N7vJTjw+uW0OpzH4wSD6PtS4e2",
    "rQ77AEq+vBhy8+FqymqEzJUgmsuQo9cGYDobvywEhdDLDxZY78D9jSkijk/QntmPMI/MK/WAOM/ovTABdljZSCK2i3/MbHMIXBu2",
    "BIWzES8Kg0hqKNLk7NgvqzyVaB/F6XHBLJusKaFa5wWHZHixKZoFSvnGKpOg6xqwWDPrIFWjdrTnbIk7RABn/jTYJvWMQ3y6/zC8",
    "9esn2t49F621TOnOFzeH6HVPlxqhQVYHVJGMdfb66bYazvhvtayy5+/3sysamsOCzzJ0W9ykhM0RSLt6rm1Ru1MtiUNY50LyNHMS",
    "Gca6jbJ7mV0RXJjN9FlIEr5iFlde2LOquFGAgoQWSkdHSnG925N3cx7bQBZsxqJdj3XMgBBrY/NgLBFGJhHRDIJP6YvyOCxwXhWc",
    "gp+oIcuiu4Nf3DJIm5Vk72hoxpIDuA02ka7FS2b60qvwg2m97OX6tqRfPnsLsTGxYyHLw2QJ2r8zNlTgjsnjYnVftPxA7Omo+17N",
    "Hyt2AGpygk/4A3KdiKMTv0JE4SWAICy0ONLQVm9GJYkIM2zcehEq3xO/RJGxxWmwFXfAnskwB5bBLu0Jvkwc87uQ3NMBBk4F78tu",
    "tFcItagTU564ug7bLVOyg5xI0aWBojXJJHMAGJld8QMNm13+kbOeLX/XR3W2nI/ypJkRAcXBsgf+iMLJg7jVsF1YP52InGNE4imc",
    "SOpjcTVyw0rv4JQY4BanoDG8WKybPQ7sHy485io6auqaKh0foysqtxejtxsDRDGGZwl9yi33/f5250UgibiNGFBr6YECAMgAKBBj",
    "OyN5Rzt7JzojO0eTPzdK/88eHWBJiNOT6qVH7d8E7xQa9kp3TuQQWt3Chwjv/YTW3xizZtNPBi9Rt9rIZtO48o2Ody/Lye9uTWrm",
    "Xla1GwNTa4FSyEFYHhC+mKOcDteOGmEfDHqc8r6sBM3YHBF9/Pq6NsFqxOodlZIVfQUYtntcTcIxnE3mLKrRaCNBalSbkIeDDvZw",
    "hl8a/EKkXxX8d2hCJepuhm6cXhr6uXfIuDEBiOLPFiUIBOzBMCTkZg44/b8Gj7vEH82ECiMzapy9Tt04+3Brwc/7u9trd/Wt08gs",
    "42iDJ/F3Gnd3nBot1UtuVXHks2Bkm0H2LOP1Hm0akcqyzpS4KRs/lqW4SPmdukBvm37lo+9XfGo9s9D5hQdNdOFgjv9S1EbW6NYP",
    "uovCmBpsjB43GqA9TVLwua3RSO5h1d1HAC/4NcQ9NjJUjH9jl/f5/T3b36LvTvqXjy8QWk9A9CH9M/oM7O3/B3z/KBlxAm/bYoPe",
    "tsVSuiXZEnwuYIaCR4JEimdFWoxp0RJOUq4uZvXlsaUShcxoWvZdGE1OLho9HTCDJ3FmQDXkHhGB6B6YCVIhzEpq/IhBJMT4jZkX",
    "grwPQV77aIeYRa46WBiB3ijCP0gdZV6JYrrCwMi+z1E/P9zCKHS1Lq66JCPo2HyTDUlc9upJuyeJIEE+a85LaJpLFvuh0gLLZjRk",
    "clRnvEtTZ77ebQFpU5GPPZ1oILwmvRy88oe8snQj4DEL59S54keVCqwV99iSutoAMfk9j7yb/srU3gDpXMk3i3dJhiNTPvbWKLHt",
    "Hz6jFyJFSUyAGZa5ltu1rCyKS2xy5WXGld34qCEsBtdzze7Yforo7V/INtPfirE9HHrHq+oUf4C4dInUYHSg4JWBEb1a5phV+fqu",
    "upUe/7b3ZSOIzbsk+XIFyZvUjV05ol5C3nHp0fjuncvgN9LNtLEFsrLsp5V7mrrzpzU/Ux5e/N1CDr4t/YIfd43zX/8PZkFAaQD/",
    "7usl/lr+5ssm/trBv26E/+eS/A5Ixf/YFv/Xhn/dHPyP0gbxf20V/mvjf92X+c/FF/p343+zS/Ov/fx1s94/SjXsv9+699de/nq/",
    "6h/lJ/nf3r36awd/vdL2j+JF/5frbn9t+tfLCP8oy0x/f1Hhrz38a9r850LFAwD8X0n0r83/lff+uRTz/VPzP1lQXgoc4u0zGOCP",
    "P7CFjuDb2f8CaG0kovNEAAA="
  ]
}
```

