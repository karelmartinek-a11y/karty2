# Jednotný průběh importů

Aktuální celkové výsledky vydání jsou v [auditu 0.4.5](AUDIT_0_4_5.md). Níže uvedené provozní počty a původní ověřovací běhy jsou historické; popis společného importního toku zůstává platný.

## Kontrola provozních záznamů

Kontrola 15. září 2026 proběhla pouze pro čtení. Terminálový import od 23:24:42 do 23:24:47 místního času zpracoval 7 souborů: 369 nových plateb, žádné duplicity a žádná diagnostická chyba ani upozornění. Evidence obsahovala 369 různých odkazovaných plateb. Vynecháno bylo 167 řádků bez plateb, 14 prázdných a 14 souhrnných řádků.

Posledních 40 Booking souborů v kontrolovaném intervalu skončilo COMPLETED: 699 známých výskytů a žádné nové platby. Následný import Účtů přidal 762 vazeb; 674 neúplných řádků bylo vynecháno s upozorněním. V kontrolovaném intervalu nebyly v provozním logu události úrovně ERROR.

Původní UI směrovalo průběh pouze do stavového řádku. Terminál neměl závěrečné výsledkové okno a Booking používal samostatné nemodální okno. Log nedokládá, proč uživatel Booking okno neviděl.

## Implementace

Společná služba ImportBatchService zpracovává všechny čtyři druhy po jednotlivých souborech. Zachovává atomické finanční transakce, kontrolu původního podkladu, identifikaci duplicit a pravidla párování. Běžná cesta v UI nevyžaduje potvrzení náhledu. Výběr více vhodných listů probíhá přes signál do GUI vlákna v rámci stejné operace.

ImportProgress je textově kompatibilní událost se strukturovaným snapshotem. Čtení, kontrola, ukládání plateb, ukládání vazeb a dokončení sdílejí jeden dialog. Průběžné aktualizace jsou omezené na přibližně 10/s. Rozsah neznámého kroku se nevymýšlí; odhad času se výslovně týká aktuálního kroku. Uložené položky přibývají až po potvrzení transakce.

Závěrečný stav ukazuje nové platby/vazby, již uložené, vynechané a chybné řádky, neuložené položky a stav každého souboru. Zůstává otevřený do Hotovo. Zrušení během zápisu vrátí rozpracovaný soubor a zachová předchozí dokončené soubory. Duplicita uvnitř odmítnutého souboru ani opakovaný konfliktní řádek se neoznačují jako skutečně uložená platba.

Historie sdílí stejné textové výsledky a zahrnuje i nečitelné soubory bez uložené kopie. Nová pole import_result, batch_id a batch_summary využívají stávající JSON záznam; migrace schématu není potřebná. Starší Booking výsledky zůstávají čitelné. Selhání zápisu souhrnu je upozornění, které nemění úspěšně dokončený import.

Také selhání úklidu dočasného podkladu po potvrzení transakce zachová stav Dokončeno a skutečný počet uložených plateb. Zobrazí upozornění IMPORT_CLEANUP_FAILED v souhrnu a zapíše technický záznam; uživatel nemá kvůli tomuto upozornění import opakovat. Při původním selhání importu nesmí druhotná chyba úklidu překrýt jeho příčinu.

## Historické ověření implementace

Regresní scénáře zahrnují všechny čtyři druhy, opakované importy, skutečný výběr souborů, pomalý i rychlý průběh, konečný dialog čekající na Hotovo, nečitelné soubory v historii, výběr listu i jeho zrušení, zastavení během zápisu a chybu před potvrzením transakce. Počty se kontrolují proti databázi, historii a logu. Poslední cílená sada 17 testů prošla, včetně obou regresí duplicit v odmítnutém souboru.

Windows aplikace byla úspěšně sestavena pomocí PyInstalleru; všech devět dotčených modulů ve výsledném archivu bylo porovnáno s konečným zdrojovým kódem. Ověřovací sestavení je v `.tmp/import-progress/dist/KajovoKarty`, log v `.tmp/import-progress-build-final.log`. Vizuálně byly zkontrolovány snímky průběhu a výsledku. Statická kontrola F821/F822/F823/F841 prošla.

Provozní data nebyla měněna. Instalační balíček nebyl nahrazen. Pro spuštění aktualizace přes start.bat stačí ukončit a znovu spustit aplikaci.

Závěrečný úplný běh: **280 testů prošlo, 0 chyb, 555,43 s**; záznam je v `import-progress-test-results.xml`. Tento běh byl spuštěn před posledním zpřesněním počítání opakovaných konfliktních řádků. Konečnou úpravu následně pokryla výše uvedená cílená sada 17 testů včetně dodatečné regrese; sestavení odpovídá konečnému kódu.
