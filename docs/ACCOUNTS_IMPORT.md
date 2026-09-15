# Účty: ruční import a párování

Tento kontrakt verze 0.4.0 nahrazuje části staršího SSOT popisující živé BetterHotel API, tokeny, automatické pravidlo B a pravidla C_WEAK/D závislá na API. Historické protokoly API zůstávají archivními záznamy.

## Import

V Importech nebo v nabídce Importovat zvolte Účty (XLS). Export musí obsahovat jednou každou hlavičku Variabilní symbol, Číslo rezervace a Original ID; pořadí sloupců se může lišit. Další sloupce se nevytěžují. Původní soubor se uchovává pro audit stejně jako ostatní importy.

Řádky bez některého ze tří identifikátorů se přeskočí. Okolní mezery se odstraní, textové počáteční nuly zůstanou. První přijaté Original ID pro číslo rezervace BetterHotelu platí trvale. Přesné duplicity se ignorují. Stejnou dvojici s dalším VS lze doplnit; jiný Booking identifikátor pro známou rezervaci se ignoruje včetně nového VS. Pořadí při prvním importu je pořadí vybraných souborů a řádků.

Náhled ukazuje nové vazby, duplicity, konflikty a neúplné řádky. Potvrzení atomicky znovu vyhodnotí duplicity proti aktuální databázi. Import neprovádí párování ani nerozpojuje existující skupiny. Pomocná data a sestava Pomocná data zobrazují importované vazby a původ.

## Automatika

Pravidlo B použije VS volné položky pokladny k vyhledání právě jedné rezervace v Účtech. Original ID musí odpovídat číslu rezervace volné Booking platby. Částka včetně znaménka musí být přesně stejná v nejmenší měnové jednotce a měna musí být shodná. Nevytvářejí se součtové kombinace. Při více vhodných protějšcích na kterékoli straně zůstává případ ruční.

Zůstává pořadí nezávislých pravidel: bankovní storna, terminál podle dne/měny/částky, Booking přes Účty, banka podle VS. Stávající pravidlo terminálu se nemění. Pravidla slabé bankovní shody a Booking protizápisů vyžadující API důkazy se již nespouštějí.

Důkaz nové Booking skupiny obsahuje použitý VS, obě rezervace, soubor, import, list a řádek. Dokončené skupiny, ruční zásahy a zákazy opětovného automatického spojení zůstávají zachované.

## Migrace a ověření

Schéma 3 přidává append-only tabulky account_reservation a account_symbol. Před aktualizací existující databáze vzniká ověřená záloha. Migrace odstraní uložená přihlašovací tajemství; staré finanční důkazy zachová. Záloha a obnova zahrnují nové tabulky.

Online klient nemá síťovou implementaci; zůstal jen odmítající kompatibilitní vstup a metadata potřebná pro historická data. Rozhraní a provozní skripty online synchronizaci nenabízejí. Staré testy online přenosu a nahrazených součtových pravidel byly odstraněny; nová pravidla ověřuje tests/test_accounts.py spolu se zachovanými finančními, databázovými a Qt regresními testy.

Ověření 11. 9. 2026 ve Windows, Python 3.12.9: `python -m pytest -q -p no:cacheprovider --tb=short` — **176 testů prošlo**. Ověřen byl také překlad Python modulů a `git diff --check`. Qt test prošel výběrem skutečného `ucty.xls`, náhledem a potvrzením importu; vizuální kontrola přehledu potvrdila 14 VS vazeb na 11 dvojic rezervací. Instalátor v tomto ověření sestaven nebyl.
