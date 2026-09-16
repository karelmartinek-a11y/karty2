# Přehled chyb a upozornění

Generováno z `domain/errors.py`. Ruční úpravy přepište v číselníku, nikoli zde.

| Kód | Závažnost | Název | Vysvětlení | Další krok |
|---|---|---|---|---|
| ACCOUNTS_CONFLICT | WARNING | Jiné číslo Bookingu pro známou rezervaci | První uložená vazba zůstává platná; odlišná vazba z nového řádku byla vynechána. | Ověřte správné číslo rezervace v původních podkladech. |
| ACCOUNTS_INCOMPLETE | WARNING | Neúplná vazba v Účtech | Řádek nemá variabilní symbol, číslo rezervace nebo Original ID a byl vynechán. | Doplňte chybějící označení v původním zdroji, pokud má být vazba použita. |
| ACCOUNTS_REFERENCE_MISSING | INFO | Chybí vazba v Účtech | Pro variabilní symbol pokladny není uložená vazba na rezervaci. | Importujte příslušné Účty nebo položku dořešte ručně. |
| ALREADY_OWNED | ERROR | Položka už je spojená | Položka už patří do jiného spojení nebo je ve výběru vícekrát. | Zkontrolujte její aktuální spojení a výběr upravte. |
| AMBIGUOUS | INFO | Více možných protějšků | Pro položku existuje více stejně vhodných shod. | Vyberte správný protějšek ručně podle podkladů. |
| AMOUNT_MISMATCH | INFO | Nesouhlasí částka | Platba ke stejné rezervaci nemá přesně stejnou částku včetně znaménka. | Zkontrolujte podklady; případné párování ve skupinách proveďte ručně. |
| API_AUTH | ERROR | Staré připojení už se nepoužívá | Tento záznam nebo požadavek se týká dřívějšího online připojení BetterHotel. | Pro současné párování použijte ruční import Účty (XLS). |
| API_CONTEXT_CHANGED | ERROR | Staré připojení už se nepoužívá | Tento záznam nebo požadavek se týká dřívějšího online připojení BetterHotel. | Pro současné párování použijte ruční import Účty (XLS). |
| API_DETAIL_REQUIRES_FULL_SYNC | ERROR | Staré připojení už se nepoužívá | Tento záznam nebo požadavek se týká dřívějšího online připojení BetterHotel. | Pro současné párování použijte ruční import Účty (XLS). |
| API_REMOVED | ERROR | Staré připojení už se nepoužívá | Tento záznam nebo požadavek se týká dřívějšího online připojení BetterHotel. | Pro současné párování použijte ruční import Účty (XLS). |
| API_SCHEMA | ERROR | Staré připojení už se nepoužívá | Tento záznam nebo požadavek se týká dřívějšího online připojení BetterHotel. | Pro současné párování použijte ruční import Účty (XLS). |
| API_SNAPSHOT_CONFLICT | ERROR | Staré připojení už se nepoužívá | Tento záznam nebo požadavek se týká dřívějšího online připojení BetterHotel. | Pro současné párování použijte ruční import Účty (XLS). |
| AUTO_GROUP_FORBIDDEN | ERROR | Chybí ověření součtové skupiny | Automatická součtová skupina musí vzniknout v ověřeném běhu párování. | Spusťte automatické párování nebo vytvořte skupinu ručně v párovací ploše. |
| AUTO_SEARCH_LIMIT | INFO | Hledání nebylo úplné | Běh dosáhl nastaveného limitu hledání kombinací. Neúplně prohledaná oblast nebyla automaticky spojena. | Zkontrolujte kandidáty a případně vytvořte vyrovnanou skupinu ručně. |
| AUTO_SUPPRESSED | INFO | Automatické spojení je zakázané | Předchozí ruční zásah zakázal opakování tohoto automatického spojení. | Ponechte ruční rozhodnutí, nebo výslovně povolte nové automatické spojení. |
| BACKUP_INVALID | ERROR | Zálohu nelze použít | Zálohu nelze přečíst nebo neprošla kontrolou. | Vyberte jinou ověřenou zálohu; současná data ponechte zachovaná. |
| BANK_NO_COUNTERPART | INFO | Nenalezen odpovídající protějšek | Mezi volnými položkami není doložená shoda podle pravidel párování. | Zkontrolujte úplnost importů a podklady; případ dořešte ručně. |
| BOOKING_CHECKOUT_INVALID | ERROR | Chybí platné datum odjezdu | U platby Booking.com chybí datum konce pobytu nebo jej nelze přečíst. Import nebyl uložen. | Zkontrolujte datum check-outu v uvedeném řádku původního souboru a import opakujte. |
| BOOKING_NO_COUNTERPART | INFO | Nenalezen odpovídající protějšek | Mezi volnými položkami není doložená shoda podle pravidel párování. | Zkontrolujte úplnost importů a podklady; případ dořešte ručně. |
| BOOKING_REFERENCE_NOT_FOUND | INFO | Chybí platba z Bookingu | Pro doloženou Booking rezervaci není volná importovaná platba. | Importujte odpovídající Booking výplatu nebo prověřte již spojené platby. |
| BOOKING_REFERENCE_REJECTED | INFO | Pomocná vazba vyžaduje kontrolu | Starší podklady neumožnily doložit jednoznačnou vazbu. | Použijte aktuální Účty a zkontrolujte původní rozhodnutí. |
| BOOKING_REFERENCE_REVIEW_REQUIRED | INFO | Pomocná vazba vyžaduje kontrolu | Starší podklady neumožnily doložit jednoznačnou vazbu. | Použijte aktuální Účty a zkontrolujte původní rozhodnutí. |
| CANCELLED | INFO | Operace byla zastavena | Operace byla zastavena na váš pokyn. Dříve dokončené kroky zůstávají uložené. | Výsledek ověřte v historii; pokračovat můžete novým spuštěním. |
| CASHBOOK_FOOTER_MISMATCH | WARNING | Nesouhlasí souhrn pokladny | Souhrn na konci exportu nesouhlasí s jednotlivými pohyby. Program používá jednotlivé pohyby. | Porovnejte souhrn s původním pokladním deníkem. |
| CASHBOOK_NO_COUNTERPART | INFO | Nenalezen odpovídající protějšek | Mezi volnými položkami není doložená shoda podle pravidel párování. | Zkontrolujte úplnost importů a podklady; případ dořešte ručně. |
| CASHBOOK_NO_DOCUMENT | INFO | Pomocná vazba vyžaduje kontrolu | Starší podklady neumožnily doložit jednoznačnou vazbu. | Použijte aktuální Účty a zkontrolujte původní rozhodnutí. |
| CASHBOOK_REFERENCE_INVALID | ERROR | Chybí označení dokladu | Chybí platné číslo dokladu, rezervace, výplaty nebo variabilní symbol. | Doplňte potřebné označení v původním zdroji a vytvořte nový export. |
| CURRENCY_MISMATCH | INFO | Nesouhlasí měna | Platby ke stejné rezervaci mají jinou měnu. | Zkontrolujte původní doklady; automatika měny nepřevádí. |
| CURRENCY_UNSUPPORTED | ERROR | Nepodporovaná měna | Program zpracovává pouze koruny a eura. | Použijte export v CZK nebo EUR. Program měny nepřevádí. |
| CYCLE_DETECTED | ERROR | Tyto položky nelze spojit | Výběr neumožňuje platné spojení položek. | Vyberte alespoň dvě různé položky; skupinu nelze vložit do ní samotné. |
| DATABASE_ACCESS_DENIED | ERROR | K uloženým datům nelze přistoupit | Program nemůže otevřít soubor s uloženými daty. Soubor může být nedostupný nebo k němu účet nemá potřebná oprávnění. | Zkontrolujte dostupnost datové složky a oprávnění ke čtení i zápisu. Toto hlášení samo o sobě neznamená poškození dat; neprovádějte reset. |
| DATABASE_INVALID | ERROR | Pracovní data nejsou v pořádku | Uložená data neprošla kontrolou úplnosti nebo návazností. | Nepřepisujte soubory ručně. Použijte ověřenou zálohu nebo požádejte správce o kontrolu. |
| DATE_INVALID | ERROR | Datum nelze přečíst | Datum platby nebo pobytu se nepodařilo přečíst. | Zkontrolujte datum v uvedeném řádku původního souboru. |
| DB_BUSY | ERROR | Probíhá jiná operace | Pracovní data právě používá jiná operace. | Počkejte na její dokončení a zkuste akci znovu. |
| DIRECTORY_BUSY | ERROR | Probíhá jiná operace | Pracovní data právě používá jiná operace. | Počkejte na její dokončení a zkuste akci znovu. |
| DIRECTORY_INVALID | ERROR | Složka není dostupná | Vybranou složku nelze použít pro tuto operaci. | Vyberte dostupnou místní složku s oprávněním pro čtení a zápis. |
| DIRECTORY_OCCUPIED | ERROR | Složka už obsahuje data | Cílová složka již obsahuje jiný pracovní prostor. | Vyberte prázdnou složku. |
| DIRECTORY_UNAVAILABLE | ERROR | Složka není dostupná | Vybranou složku nelze použít pro tuto operaci. | Vyberte dostupnou místní složku s oprávněním pro čtení a zápis. |
| DISK_FULL | ERROR | Na disku není místo | Operaci nelze dokončit, protože na disku není dostatek volného místa. | Uvolněte místo a zkontrolujte výsledek operace v historii. |
| DOCUMENT_NO_RESERVATION | INFO | Pomocná vazba vyžaduje kontrolu | Starší podklady neumožnily doložit jednoznačnou vazbu. | Použijte aktuální Účty a zkontrolujte původní rozhodnutí. |
| DPAPI_FAILED | ERROR | Staré připojení už se nepoužívá | Tento záznam nebo požadavek se týká dřívějšího online připojení BetterHotel. | Pro současné párování použijte ruční import Účty (XLS). |
| DPAPI_UNAVAILABLE | ERROR | Staré připojení už se nepoužívá | Tento záznam nebo požadavek se týká dřívějšího online připojení BetterHotel. | Pro současné párování použijte ruční import Účty (XLS). |
| Dosud nepárováno | INFO | Dosud nepárováno | Platba zatím nemá aktuální výsledek párování. | Spusťte automatické párování nebo platbu spárujte ručně. |
| EXPORT_AUDIT_FAILED | ERROR | Sestava vznikla, zápis do historie selhal | Soubor byl vytvořen, ale záznam o jeho vytvoření se nepodařilo uložit. | Ověřte cílový soubor; při opakování hlídejte jeho přepsání. |
| EXPORT_INVALID | ERROR | Sestavu nelze vytvořit | Výběr nebo údaje nestačí pro požadovanou sestavu. | Zkontrolujte vybrané položky, druh sestavy a místo uložení. |
| FILE_CHANGED | ERROR | Soubor se změnil nebo není dostupný | Soubor nelze přečíst nebo se během načítání změnil. | Vyberte dostupný soubor znovu a vytvořte nový náhled. |
| FILE_TOO_LARGE | ERROR | Soubor je příliš velký | Soubor je větší než povolená velikost v nastavení. | Zmenšete rozsah exportu nebo upravte povolenou velikost v Nastavení. |
| FILTER_INVALID | ERROR | Výběr není dostupný | Požadovaný přehled nebo vybrané položky nejsou dostupné v tomto stavu. | Obnovte přehled a vyberte položky znovu. |
| FORMAT_INVALID | ERROR | Soubor nelze přečíst | Soubor nemá podporovaný formát nebo je poškozený. | Vytvořte nový export v podporovaném formátu pro zvolený druh importu. |
| GROUP_INVALID | ERROR | Tyto položky nelze spojit | Výběr neumožňuje platné spojení položek. | Vyberte alespoň dvě různé položky; skupinu nelze vložit do ní samotné. |
| HEADER_INVALID | ERROR | Chybí potřebné sloupce | Chybí potřebné názvy sloupců pro zvolený druh importu. | Vyberte správný druh importu a původní export se všemi potřebnými sloupci. |
| HELPER_CHAIN_UNVERIFIED | INFO | Pomocná vazba vyžaduje kontrolu | Starší podklady neumožnily doložit jednoznačnou vazbu. | Použijte aktuální Účty a zkontrolujte původní rozhodnutí. |
| HELPER_DATA_NOT_SYNCED | INFO | Pomocná vazba vyžaduje kontrolu | Starší podklady neumožnily doložit jednoznačnou vazbu. | Použijte aktuální Účty a zkontrolujte původní rozhodnutí. |
| HELPER_ENTITY_NOT_OBSERVED | INFO | Pomocná vazba vyžaduje kontrolu | Starší podklady neumožnily doložit jednoznačnou vazbu. | Použijte aktuální Účty a zkontrolujte původní rozhodnutí. |
| HELPER_MISSING | INFO | Pomocná vazba vyžaduje kontrolu | Starší podklady neumožnily doložit jednoznačnou vazbu. | Použijte aktuální Účty a zkontrolujte původní rozhodnutí. |
| HELPER_UNAVAILABLE | INFO | Pomocná vazba vyžaduje kontrolu | Starší podklady neumožnily doložit jednoznačnou vazbu. | Použijte aktuální Účty a zkontrolujte původní rozhodnutí. |
| IDENTITY_MISSING | ERROR | Chybí označení dokladu | Chybí platné číslo dokladu, rezervace, výplaty nebo variabilní symbol. | Doplňte potřebné označení v původním zdroji a vytvořte nový export. |
| IMPORT_CLEANUP_FAILED | WARNING | Import je uložen, úklid nebyl dokončen | Import byl úspěšně uložen, ale úklid dočasného podkladu se nepodařilo dokončit. | Import neopakujte kvůli tomuto upozornění. Zkontrolujte oprávnění a volné místo; při opakování kontaktujte správce. |
| IMPORT_INVALID | ERROR | Import obsahuje chyby | Žádné nové položky ani vazby z tohoto importu nebyly uloženy. | Opravte chyby uvedené u souborů a import opakujte. |
| IMPORT_REPORT_FAILED | WARNING | Souhrn se nepodařilo uložit | Podrobný souhrn importu se nepodařilo zapsat do historie. Tím se nemění výše uvedené počty již uložených plateb. | Zkontrolujte uložené položky a dostupnost datové složky. |
| INTERNAL_ERROR | ERROR | Operaci se nepodařilo dokončit | Program narazil na neočekávanou chybu. Některé již dokončené kroky mohou být uložené. | Zkontrolujte výsledek v historii. Pokud se chyba opakuje, předejte číslo chyby správci programu. |
| INTERRUPTED | WARNING | Operace nedoběhla | Program byl přerušen před dokončením všech kroků. | Zkontrolujte historii a spusťte operaci znovu. |
| MATCH_DATE_OUTSIDE_WINDOW | INFO | Datum je mimo párovací okno | Platba ke stejné rezervaci má shodnou měnu a částku, ale datum je mimo povolený počet pracovních dnů. | Porovnejte datum vystavení pokladny s datem odjezdu Booking.com; případný nesoulad dořešte ručně. |
| MIXED_CURRENCY | ERROR | Položky mají různé měny | Koruny a eura nelze spojit do jedné dvojice ani skupiny. | Párujte každou měnu samostatně. |
| MONEY_INVALID | ERROR | Částku nelze přečíst | Částku platby se nepodařilo přečíst. | Opravte částku v původním zdroji; používejte nejvýše dvě desetinná místa. |
| MONEY_OVERFLOW | ERROR | Částka je příliš vysoká | Částka nebo součet překračuje podporovanou velikost. | Zkontrolujte částky a vybraný rozsah položek. |
| MULTIPLE_CANDIDATES | INFO | Více možných protějšků | Pro položku existuje více stejně vhodných shod. | Vyberte správný protějšek ručně podle podkladů. |
| NONZERO_DIFFERENCE | ERROR | Částky nejsou vyrovnané | Výběr nesplňuje požadované vyrovnání částek nebo již obsahuje vyřízené spojení. | Zkontrolujte rozdíl a členy v párovací ploše. |
| NOTE_INVALID | ERROR | Poznámka je příliš dlouhá | Poznámka může mít nejvýše 10 000 znaků. | Zkraťte poznámku. |
| NOT_FOUND | ERROR | Výběr není dostupný | Požadovaný přehled nebo vybrané položky nejsou dostupné v tomto stavu. | Obnovte přehled a vyberte položky znovu. |
| NOT_MATCHED | INFO | Nenalezen odpovídající protějšek | Mezi volnými položkami není doložená shoda podle pravidel párování. | Zkontrolujte úplnost importů a podklady; případ dořešte ručně. |
| NOT_YET_MATCHED | INFO | Dosud nepárováno | Platba zatím nemá aktuální výsledek párování. | Spusťte automatické párování nebo platbu spárujte ručně. |
| NO_COUNTERPART | INFO | Nenalezen odpovídající protějšek | Mezi volnými položkami není doložená shoda podle pravidel párování. | Zkontrolujte úplnost importů a podklady; případ dořešte ručně. |
| NO_HELPER | INFO | Pomocná vazba vyžaduje kontrolu | Starší podklady neumožnily doložit jednoznačnou vazbu. | Použijte aktuální Účty a zkontrolujte původní rozhodnutí. |
| OPEN_AGGREGATE | INFO | Ve skupině zbývá rozdíl | Součet položek ruční skupiny není vyrovnaný. | Zkontrolujte nebo doplňte členy skupiny. |
| OVERRIDE_INVALID | ERROR | Volbu nelze potvrdit | Vybrané označení není mezi doloženými možnostmi. | Obnovte podklady a vyberte doloženou možnost. |
| QUERY_INVALID | ERROR | Výběr není dostupný | Požadovaný přehled nebo vybrané položky nejsou dostupné v tomto stavu. | Obnovte přehled a vyberte položky znovu. |
| REJECTED | INFO | Pomocná vazba vyžaduje kontrolu | Starší podklady neumožnily doložit jednoznačnou vazbu. | Použijte aktuální Účty a zkontrolujte původní rozhodnutí. |
| RESERVATION_NO_BOOKING_REFERENCE | INFO | Pomocná vazba vyžaduje kontrolu | Starší podklady neumožnily doložit jednoznačnou vazbu. | Použijte aktuální Účty a zkontrolujte původní rozhodnutí. |
| RESET_BUSY | ERROR | Reset zatím nelze spustit | Program právě dokončuje jinou činnost. | Počkejte na dokončení importu, párování nebo zálohování a spusťte reset znovu. |
| RESET_FAILED | ERROR | Reset není dokončen | Některé soubory se nepodařilo vymazat nebo připravit prázdný program. Část dat už může být odstraněná. | Zavřete jiné programy používající tyto soubory a zkontrolujte volné místo a přístup ke složkám. Zvolte Opakovat, nebo program znovu spusťte a dokončete reset. |
| RESET_PREPARE_FAILED | ERROR | Reset nezačal | Prázdný pracovní prostor se nepodařilo připravit. Původní data nebyla resetem vymazána. | Zkontrolujte volné místo a přístup ke složkám programu a záloh. Potom program znovu spusťte. |
| REVIEW_REQUIRED | INFO | Pomocná vazba vyžaduje kontrolu | Starší podklady neumožnily doložit jednoznačnou vazbu. | Použijte aktuální Účty a zkontrolujte původní rozhodnutí. |
| ROW_SHAPE_INVALID | ERROR | Nesprávně rozdělený řádek | Řádek nemá očekávaný počet nebo uspořádání údajů. | Zkontrolujte uvedený řádek a vytvořte nový export. Žádné údaje z vadného souboru se nepřidají. |
| RUN_NOT_COMPLETED | WARNING | Operace nedoběhla | Program byl přerušen před dokončením všech kroků. | Zkontrolujte historii a spusťte operaci znovu. |
| SCHEMA_NEWER | ERROR | Je potřeba novější program | Data byla uložena novější verzí programu. | Použijte stejnou nebo novější verzi programu. |
| SEARCH_LIMIT | INFO | Hledání nebylo úplné | Běh dosáhl nastaveného limitu hledání kombinací. Neúplně prohledaná oblast nebyla automaticky spojena. | Zkontrolujte kandidáty a případně vytvořte vyrovnanou skupinu ručně. |
| SELECTION_INVALID | ERROR | Výběr není dostupný | Požadovaný přehled nebo vybrané položky nejsou dostupné v tomto stavu. | Obnovte přehled a vyberte položky znovu. |
| SETTING_INVALID | ERROR | Nastavení nelze uložit | Některá hodnota nastavení není platná. | Zkontrolujte vyplněné hodnoty a jejich povolený rozsah. |
| SHEET_AMBIGUOUS | ERROR | Je potřeba vybrat list | Soubor obsahuje více vhodných listů. | Vyberte list, ze kterého chcete údaje načíst. |
| SNAPSHOT_INVALID | ERROR | Uložený podklad nelze použít | Uložená kopie vstupního souboru chybí nebo je poškozená. | Vyberte původní soubor nebo obnovte ověřenou zálohu. |
| SOURCE_CONFLICT | ERROR | Uložená platba má jiné údaje | Platba už v programu je, ale soubor o ní uvádí jiné platební údaje. Uloženou platbu jsme nepřepsali. | Porovnejte původní a nový doklad a opravte zdroj nesprávného údaje. |
| SOURCE_INVALID | ERROR | Pracovní data nejsou v pořádku | Uložená data neprošla kontrolou úplnosti nebo návazností. | Nepřepisujte soubory ručně. Použijte ověřenou zálohu nebo požádejte správce o kontrolu. |
| SPLIT_CLIENT_ENTITY | INFO | Opravené rozdělení názvu | Export rozdělil znak & v názvu do dvou sloupců. Program obnovil původní rozdělení řádku. | Řádek byl zkontrolován běžnými pravidly importu. |
| STALE_STATE | ERROR | Data se mezitím změnila | Vybrané položky nebo pravidla už neodpovídají původnímu výběru. | Obnovte přehled a zkontrolujte aktuální stav před opakováním akce. |
| SUMMARY_MISMATCH | ERROR | Nesouhlasí souhrn souboru | Počet nebo součet uvedený v souboru nesouhlasí s jeho řádky. | Zkontrolujte úplnost exportu a vytvořte jej znovu. |
| SUPPRESSED | INFO | Automatické spojení je zakázané | Předchozí ruční zásah zakázal opakování tohoto automatického spojení. | Ponechte ruční rozhodnutí, nebo výslovně povolte nové automatické spojení. |
| SYNC_FAILED | ERROR | Staré připojení už se nepoužívá | Tento záznam nebo požadavek se týká dřívějšího online připojení BetterHotel. | Pro současné párování použijte ruční import Účty (XLS). |
| UNDO_CONFLICT | ERROR | Data se mezitím změnila | Vybrané položky nebo pravidla už neodpovídají původnímu výběru. | Obnovte přehled a zkontrolujte aktuální stav před opakováním akce. |
| UNKNOWN_ENUM | ERROR | Nerozpoznaný druh platby | Druh nebo stav platby program zatím neumí zpracovat. | Zkontrolujte zvolený import a hodnotu v uvedeném řádku; nejasný údaj svévolně neměňte. |
| XLS_COMPATIBILITY | WARNING | Starší podoba souboru | Soubor byl načten s podporou staršího způsobu uložení. | Zkontrolujte náhled a výsledné počty. |
