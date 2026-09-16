> Historický dokument; aktuální pravidla a výsledky jsou v [SSOT](SSOT.md) a [auditu 0.4.5](AUDIT_0_4_5.md). Níže zachovaný obsah popisuje tehdejší stav.

# Chyba otevření databáze — 0.4.4

## Zjištění z 15. 9. 2026

Program spuštěný přes `start.bat` skončil po události `DATABASE_OPEN` v dialogu obnovy. Výjimka při tomto startu nebyla ve starší verzi zaznamenaná, takže původní nízkoúrovňový text chyby není dostupný.

Kontrola aktuální databáze jen pro čtení prokázala:

- `integrity_check`: **ok**, žádná porušená cizí vazba, schéma 3.
- Zachováno **627 plateb Booking.com**.
- Start zdrojového kódu na izolované kopii fungoval i s proměnnými TEMP/TMP ze `start.bat`.
- Datová složka poskytovala běžnému účtu plný přístup, ale databázový soubor měl chráněná oprávnění bez dědění. Přístup obsahoval pouze vlastníka, SYSTEM a Administrators; vlastníkem byla skupina Administrators.
- Proces uživatele neměl zvýšená oprávnění. Diagnostika běžící se zvýšenými oprávněními proto databázi přečetla, zatímco běžnému účtu přístup chyběl.

Tento stav vysvětluje selhání otevření a neznamená poškození uložených plateb. Přesný historický krok, který chráněná oprávnění zavedl, původní log nedokládá. Regresní test reprodukuje přenos soukromých oprávnění při původním přesunu souboru z dočasné složky.

## Oprava současného souboru

Před změnou vznikla databázová záloha `backups/before-permission-repair-20260915-203558.sqlite`, ověřená kontrolou integrity a vazeb. Původní bezpečnostní popis a kontrolní součet byly uloženy do soukromých diagnostických podkladů mimo distribuovaný archiv.

Na jediném databázovém souboru bylo obnoveno dědění oprávnění datové složky. Běžný účet tak získal stejný přístup jako ke složce. SHA-256 před změnou a po ní zůstal stejný: oprava nezměnila obsah databáze. Reset ani obnova starších plateb neproběhly.

## Oprava programu

Reset, obnova, přesun prostoru, záchranná obnova a vytváření záloh už nepřesouvají přímo soubor s oprávněními soukromé dočasné složky. Nový soubor vzniká v cílové složce, zdědí její oprávnění, obsah se zapíše a synchronizuje a teprve potom se atomicky nahradí cíl. Při neúspěchu zůstává původní cíl zachovaný.

Chyba startu se zaznamená jako `DATABASE_START_FAILED`, včetně bezpečného názvu SQLite chyby nebo čísla systémové chyby. Soukromé cesty a text výjimky se do logu nekopírují. Nedostupnost databázového souboru má vlastní lidské vysvětlení. Spojení se zavře i při selhání jeho konfigurace.

Testy ověřují rozdílná oprávnění dočasné a cílové složky, reset i opakovaný start, zálohy, obnovu a přesun, selhání publikace bez poškození původního cíle, vysvětlení a log chyby startu a uzavření neúspěšného spojení. **260 testů prošlo**, bez chyb. [Celkový testovací protokol](windows-test-results.xml). Sestavená aplikace byla zkontrolována proti zdrojům: [kontrola balíčku](startup-permissions-package-verification.json).

Není potřeba spouštět aplikaci trvale jako správce. Oprava zdrojového kódu se při dalším spuštění použije také přes `start.bat`.
