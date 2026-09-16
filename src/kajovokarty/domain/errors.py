"""One Czech vocabulary for errors, warnings and unresolved payments.

Stable machine codes remain compatible with historical evidence. User text must
never interpolate exception messages, SQL, source rows or local personal paths.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Explanation:
    name: str
    description: str
    action: str
    severity: str = "ERROR"


CATALOG = {}


def _add(codes, name, description, action, severity="ERROR"):
    for code in codes.split():
        CATALOG[code] = Explanation(name, description, action, severity)


_add("INTERNAL_ERROR", "Operaci se nepodařilo dokončit", "Program narazil na neočekávanou chybu. Některé již dokončené kroky mohou být uložené.", "Zkontrolujte výsledek v historii. Pokud se chyba opakuje, předejte číslo chyby správci programu.")
_add("FORMAT_INVALID", "Soubor nelze přečíst", "Soubor nemá podporovaný formát nebo je poškozený.", "Vytvořte nový export v podporovaném formátu pro zvolený druh importu.")
_add("HEADER_INVALID", "Chybí potřebné sloupce", "Chybí potřebné názvy sloupců pro zvolený druh importu.", "Vyberte správný druh importu a původní export se všemi potřebnými sloupci.")
_add("SHEET_AMBIGUOUS", "Je potřeba vybrat list", "Soubor obsahuje více vhodných listů.", "Vyberte list, ze kterého chcete údaje načíst.")
_add("ROW_SHAPE_INVALID", "Nesprávně rozdělený řádek", "Řádek nemá očekávaný počet nebo uspořádání údajů.", "Zkontrolujte uvedený řádek a vytvořte nový export. Žádné údaje z vadného souboru se nepřidají.")
_add("MONEY_INVALID", "Částku nelze přečíst", "Částku platby se nepodařilo přečíst.", "Opravte částku v původním zdroji; používejte nejvýše dvě desetinná místa.")
_add("MONEY_OVERFLOW", "Částka je příliš vysoká", "Částka nebo součet překračuje podporovanou velikost.", "Zkontrolujte částky a vybraný rozsah položek.")
_add("BOOKING_CHECKOUT_INVALID", "Chybí platné datum odjezdu", "U platby Booking.com chybí datum konce pobytu nebo jej nelze přečíst. Import nebyl uložen.", "Zkontrolujte datum check-outu v uvedeném řádku původního souboru a import opakujte.")
_add("DATE_INVALID", "Datum nelze přečíst", "Datum platby nebo pobytu se nepodařilo přečíst.", "Zkontrolujte datum v uvedeném řádku původního souboru.")
_add("IDENTITY_MISSING CASHBOOK_REFERENCE_INVALID", "Chybí označení dokladu", "Chybí platné číslo dokladu, rezervace, výplaty nebo variabilní symbol.", "Doplňte potřebné označení v původním zdroji a vytvořte nový export.")
_add("UNKNOWN_ENUM", "Nerozpoznaný druh platby", "Druh nebo stav platby program zatím neumí zpracovat.", "Zkontrolujte zvolený import a hodnotu v uvedeném řádku; nejasný údaj svévolně neměňte.")
_add("CURRENCY_UNSUPPORTED", "Nepodporovaná měna", "Program zpracovává pouze koruny a eura.", "Použijte export v CZK nebo EUR. Program měny nepřevádí.")
_add("SOURCE_CONFLICT", "Uložená platba má jiné údaje", "Platba už v programu je, ale soubor o ní uvádí jiné platební údaje. Uloženou platbu jsme nepřepsali.", "Porovnejte původní a nový doklad a opravte zdroj nesprávného údaje.")
_add("IMPORT_INVALID", "Import obsahuje chyby", "Žádné nové položky ani vazby z tohoto importu nebyly uloženy.", "Opravte chyby uvedené u souborů a import opakujte.")
_add("IMPORT_REPORT_FAILED", "Souhrn se nepodařilo uložit", "Podrobný souhrn importu se nepodařilo zapsat do historie. Tím se nemění výše uvedené počty již uložených plateb.", "Zkontrolujte uložené položky a dostupnost datové složky.", "WARNING")
_add("IMPORT_CLEANUP_FAILED", "Import je uložen, úklid nebyl dokončen", "Import byl úspěšně uložen, ale úklid dočasného podkladu se nepodařilo dokončit.", "Import neopakujte kvůli tomuto upozornění. Zkontrolujte oprávnění a volné místo; při opakování kontaktujte správce.", "WARNING")
_add("FILE_CHANGED", "Soubor se změnil nebo není dostupný", "Soubor nelze přečíst nebo se během načítání změnil.", "Vyberte dostupný soubor znovu a vytvořte nový náhled.")
_add("FILE_TOO_LARGE", "Soubor je příliš velký", "Soubor je větší než povolená velikost v nastavení.", "Zmenšete rozsah exportu nebo upravte povolenou velikost v Nastavení.")
_add("SNAPSHOT_INVALID", "Uložený podklad nelze použít", "Uložená kopie vstupního souboru chybí nebo je poškozená.", "Vyberte původní soubor nebo obnovte ověřenou zálohu.")
_add("SUMMARY_MISMATCH", "Nesouhlasí souhrn souboru", "Počet nebo součet uvedený v souboru nesouhlasí s jeho řádky.", "Zkontrolujte úplnost exportu a vytvořte jej znovu.")
_add("CASHBOOK_FOOTER_MISMATCH", "Nesouhlasí souhrn pokladny", "Souhrn na konci exportu nesouhlasí s jednotlivými pohyby. Program používá jednotlivé pohyby.", "Porovnejte souhrn s původním pokladním deníkem.", "WARNING")
_add("SPLIT_CLIENT_ENTITY", "Opravené rozdělení názvu", "Export rozdělil znak & v názvu do dvou sloupců. Program obnovil původní rozdělení řádku.", "Řádek byl zkontrolován běžnými pravidly importu.", "INFO")
_add("XLS_COMPATIBILITY", "Starší podoba souboru", "Soubor byl načten s podporou staršího způsobu uložení.", "Zkontrolujte náhled a výsledné počty.", "WARNING")
_add("ACCOUNTS_INCOMPLETE", "Neúplná vazba v Účtech", "Řádek nemá variabilní symbol, číslo rezervace nebo Original ID a byl vynechán.", "Doplňte chybějící označení v původním zdroji, pokud má být vazba použita.", "WARNING")
_add("ACCOUNTS_CONFLICT", "Jiné číslo Bookingu pro známou rezervaci", "První uložená vazba zůstává platná; odlišná vazba z nového řádku byla vynechána.", "Ověřte správné číslo rezervace v původních podkladech.", "WARNING")
_add("CANCELLED", "Operace byla zastavena", "Operace byla zastavena na váš pokyn. Dříve dokončené kroky zůstávají uložené.", "Výsledek ověřte v historii; pokračovat můžete novým spuštěním.", "INFO")
_add("INTERRUPTED RUN_NOT_COMPLETED", "Operace nedoběhla", "Program byl přerušen před dokončením všech kroků.", "Zkontrolujte historii a spusťte operaci znovu.", "WARNING")
_add("DB_BUSY DIRECTORY_BUSY", "Probíhá jiná operace", "Pracovní data právě používá jiná operace.", "Počkejte na její dokončení a zkuste akci znovu.")
_add("DATABASE_INVALID SOURCE_INVALID", "Pracovní data nejsou v pořádku", "Uložená data neprošla kontrolou úplnosti nebo návazností.", "Nepřepisujte soubory ručně. Použijte ověřenou zálohu nebo požádejte správce o kontrolu.")
_add("BACKUP_INVALID", "Zálohu nelze použít", "Zálohu nelze přečíst nebo neprošla kontrolou.", "Vyberte jinou ověřenou zálohu; současná data ponechte zachovaná.")
_add("SCHEMA_NEWER", "Je potřeba novější program", "Data byla uložena novější verzí programu.", "Použijte stejnou nebo novější verzi programu.")
_add("DIRECTORY_UNAVAILABLE DIRECTORY_INVALID", "Složka není dostupná", "Vybranou složku nelze použít pro tuto operaci.", "Vyberte dostupnou místní složku s oprávněním pro čtení a zápis.")
_add("DIRECTORY_OCCUPIED", "Složka už obsahuje data", "Cílová složka již obsahuje jiný pracovní prostor.", "Vyberte prázdnou složku.")
_add("DISK_FULL", "Na disku není místo", "Operaci nelze dokončit, protože na disku není dostatek volného místa.", "Uvolněte místo a zkontrolujte výsledek operace v historii.")
_add("EXPORT_INVALID", "Sestavu nelze vytvořit", "Výběr nebo údaje nestačí pro požadovanou sestavu.", "Zkontrolujte vybrané položky, druh sestavy a místo uložení.")
_add("EXPORT_AUDIT_FAILED", "Sestava vznikla, zápis do historie selhal", "Soubor byl vytvořen, ale záznam o jeho vytvoření se nepodařilo uložit.", "Ověřte cílový soubor; při opakování hlídejte jeho přepsání.")
_add("FILTER_INVALID QUERY_INVALID SELECTION_INVALID NOT_FOUND", "Výběr není dostupný", "Požadovaný přehled nebo vybrané položky nejsou dostupné v tomto stavu.", "Obnovte přehled a vyberte položky znovu.")
_add("STALE_STATE UNDO_CONFLICT", "Data se mezitím změnila", "Vybrané položky nebo pravidla už neodpovídají původnímu výběru.", "Obnovte přehled a zkontrolujte aktuální stav před opakováním akce.")
_add("ALREADY_OWNED", "Položka už je spojená", "Položka už patří do jiného spojení nebo je ve výběru vícekrát.", "Zkontrolujte její aktuální spojení a výběr upravte.")
_add("GROUP_INVALID CYCLE_DETECTED", "Tyto položky nelze spojit", "Výběr neumožňuje platné spojení položek.", "Vyberte alespoň dvě různé položky; skupinu nelze vložit do ní samotné.")
_add("AUTO_GROUP_FORBIDDEN", "Chybí ověření součtové skupiny", "Automatická součtová skupina musí vzniknout v ověřeném běhu párování.", "Spusťte automatické párování nebo vytvořte skupinu ručně v párovací ploše.")
_add("MIXED_CURRENCY", "Položky mají různé měny", "Koruny a eura nelze spojit do jedné dvojice ani skupiny.", "Párujte každou měnu samostatně.")
_add("NONZERO_DIFFERENCE", "Částky nejsou vyrovnané", "Výběr nesplňuje požadované vyrovnání částek nebo již obsahuje vyřízené spojení.", "Zkontrolujte rozdíl a členy v párovací ploše.")
_add("NOTE_INVALID", "Poznámka je příliš dlouhá", "Poznámka může mít nejvýše 10 000 znaků.", "Zkraťte poznámku.")
_add("SETTING_INVALID", "Nastavení nelze uložit", "Některá hodnota nastavení není platná.", "Zkontrolujte vyplněné hodnoty a jejich povolený rozsah.")
_add("OVERRIDE_INVALID", "Volbu nelze potvrdit", "Vybrané označení není mezi doloženými možnostmi.", "Obnovte podklady a vyberte doloženou možnost.")
_add("API_REMOVED API_AUTH API_CONTEXT_CHANGED API_DETAIL_REQUIRES_FULL_SYNC API_SCHEMA API_SNAPSHOT_CONFLICT SYNC_FAILED DPAPI_FAILED DPAPI_UNAVAILABLE", "Staré připojení už se nepoužívá", "Tento záznam nebo požadavek se týká dřívějšího online připojení BetterHotel.", "Pro současné párování použijte ruční import Účty (XLS).")
_add("MULTIPLE_CANDIDATES AMBIGUOUS", "Více možných protějšků", "Pro položku existuje více stejně vhodných shod.", "Vyberte správný protějšek ručně podle podkladů.", "INFO")
_add("ACCOUNTS_REFERENCE_MISSING", "Chybí vazba v Účtech", "Pro variabilní symbol pokladny není uložená vazba na rezervaci.", "Importujte příslušné Účty nebo položku dořešte ručně.", "INFO")
_add("BOOKING_REFERENCE_NOT_FOUND", "Chybí platba z Bookingu", "Pro doloženou Booking rezervaci není volná importovaná platba.", "Importujte odpovídající Booking výplatu nebo prověřte již spojené platby.", "INFO")
_add("CURRENCY_MISMATCH", "Nesouhlasí měna", "Platby ke stejné rezervaci mají jinou měnu.", "Zkontrolujte původní doklady; automatika měny nepřevádí.", "INFO")
_add("AMOUNT_MISMATCH", "Nesouhlasí částka", "Platba ke stejné rezervaci nemá přesně stejnou částku včetně znaménka.", "Zkontrolujte podklady; případné párování ve skupinách proveďte ručně.", "INFO")
_add("AUTO_SUPPRESSED SUPPRESSED", "Automatické spojení je zakázané", "Předchozí ruční zásah zakázal opakování tohoto automatického spojení.", "Ponechte ruční rozhodnutí, nebo výslovně povolte nové automatické spojení.", "INFO")
_add("CASHBOOK_NO_COUNTERPART BANK_NO_COUNTERPART BOOKING_NO_COUNTERPART NO_COUNTERPART NOT_MATCHED", "Nenalezen odpovídající protějšek", "Mezi volnými položkami není doložená shoda podle pravidel párování.", "Zkontrolujte úplnost importů a podklady; případ dořešte ručně.", "INFO")
_add("OPEN_AGGREGATE", "Ve skupině zbývá rozdíl", "Součet položek ruční skupiny není vyrovnaný.", "Zkontrolujte nebo doplňte členy skupiny.", "INFO")
_add("AUTO_SEARCH_LIMIT SEARCH_LIMIT", "Hledání nebylo úplné", "Běh dosáhl nastaveného limitu hledání kombinací. Neúplně prohledaná oblast nebyla automaticky spojena.", "Zkontrolujte kandidáty a případně vytvořte vyrovnanou skupinu ručně.", "INFO")
_add("MATCH_DATE_OUTSIDE_WINDOW", "Datum je mimo párovací okno", "Platba ke stejné rezervaci má shodnou měnu a částku, ale datum je mimo povolený počet pracovních dnů.", "Porovnejte datum vystavení pokladny s datem odjezdu Booking.com; případný nesoulad dořešte ručně.", "INFO")
_add("HELPER_DATA_NOT_SYNCED HELPER_ENTITY_NOT_OBSERVED HELPER_CHAIN_UNVERIFIED CASHBOOK_NO_DOCUMENT DOCUMENT_NO_RESERVATION RESERVATION_NO_BOOKING_REFERENCE BOOKING_REFERENCE_REJECTED BOOKING_REFERENCE_REVIEW_REQUIRED NO_HELPER HELPER_UNAVAILABLE HELPER_MISSING REJECTED REVIEW_REQUIRED", "Pomocná vazba vyžaduje kontrolu", "Starší podklady neumožnily doložit jednoznačnou vazbu.", "Použijte aktuální Účty a zkontrolujte původní rozhodnutí.", "INFO")


_add("RESET_BUSY", "Reset zatím nelze spustit", "Program právě dokončuje jinou činnost.", "Počkejte na dokončení importu, párování nebo zálohování a spusťte reset znovu.")
_add("RESET_PREPARE_FAILED", "Reset nezačal", "Prázdný pracovní prostor se nepodařilo připravit. Původní data nebyla resetem vymazána.", "Zkontrolujte volné místo a přístup ke složkám programu a záloh. Potom program znovu spusťte.")
_add("RESET_FAILED", "Reset není dokončen", "Některé soubory se nepodařilo vymazat nebo připravit prázdný program. Část dat už může být odstraněná.", "Zavřete jiné programy používající tyto soubory a zkontrolujte volné místo a přístup ke složkám. Zvolte Opakovat, nebo program znovu spusťte a dokončete reset.")


_add("NOT_YET_MATCHED", "Dosud nepárováno", "Platba zatím nemá aktuální výsledek párování.", "Spusťte automatické párování nebo platbu spárujte ručně.", "INFO")
CATALOG["Dosud nepárováno"] = CATALOG["NOT_YET_MATCHED"]


_add("DATABASE_ACCESS_DENIED", "K uloženým datům nelze přistoupit", "Program nemůže otevřít soubor s uloženými daty. Soubor může být nedostupný nebo k němu účet nemá potřebná oprávnění.", "Zkontrolujte dostupnost datové složky a oprávnění ke čtení i zápisu. Toto hlášení samo o sobě neznamená poškození dat; neprovádějte reset.")


def explain(code):
    return CATALOG.get(code, CATALOG["INTERNAL_ERROR"])


def user_text(code):
    item = explain(code)
    return item.description + " " + item.action
