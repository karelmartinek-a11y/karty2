# Check-out v přehledech Booking.com

## Chování

Datum plateb Booking.com v pracovním přehledu, filtrech, řazení, párovací ploše a rozsazích skupin vychází z uloženého `departure`. Buňky zobrazují kompaktní 07.09.2026; dlouhý český formát zůstává v nápovědě a nabídkách filtrů. Přehledové sestavy sdílející pracovní projekci používají stejné datum. Původní datum výplaty, finanční evidence a identita importu zůstávají zachovány. Samotná změna zobrazení nevyžaduje opakovaný import. Současná párovací pravidla a datumová okna stanovuje [SSOT 0.4.5](SSOT.md).

Sloupec Počet plateb je skryt ve všech platebních tabulkách a nabídce sloupců, včetně obnovení starého rozložení. Jeho staré sloupcové filtry a řazení se odstraní. Počty v podrobnostech a souhrnech zůstávají zachované.

Nový import bez platného check-outu skončí chybou BOOKING_CHECKOUT_INVALID s lidským vysvětlením a záznamem v historii i logu; platí stávající atomické uložení souboru. Datum příjezdu zůstává nepovinným popisným údajem. Historicky poškozené datum odjezdu nemá náhradu datem výplaty.

## Historické ověření 15. září 2026

Níže jsou zachované výsledky tehdejší změny. Současné výsledky jsou v [auditu 0.4.5](AUDIT_0_4_5.md).

- Před změnou mělo všech 627 uložených Booking plateb platné datum odjezdu.
- Následná kontrola aktuální databáze pouze pro čtení: projekce obsahovala 626 pracovních řádků, z toho 625 samostatných Booking plateb; u všech datum odpovídalo uloženému check-outu. Zbývající řádek představoval skupinu. Kontrola SQLite: ok. Provozní data nebyla změněna.
- Celá sada: 263 úspěšných testů a jeden starý test očekávající přijetí neplatného check-outu. Tento test byl upraven na změnu platného check-outu, aby nadále ověřoval zachování identity a původního obsahu při opakovaném importu.
- Následná cílená sada: 27 úspěšných testů včetně opraveného testu, tří vadných check-outů, zápisu chyby do logu, datumových filtrů, řazení, rozsahu skupiny a skutečného Qt rozložení. Celá sada nebyla po úpravě testu opakována.
- Statická kontrola F821/F822/F823/F841 a kontrola whitespace prošly.
- PyInstaller dokončil sestavení v `.tmp/booking-checkout/dist/KajovoKarty`; kontrola archivu potvrdila přítomnost všech pěti dotčených modulů. Instalační balíček nebyl nahrazen. Spouštění přes start.bat používá aktualizované zdrojové soubory po restartu.
