# Průběhové okno automatického párování — 0.3.2

Po stisku **Automaticky spárovat vše** se ihned otevře samostatné okno. Během načítání nebo čekání na databázi používá neurčitý ukazatel; počet vstupů před jejich načtením zobrazuje jako neznámý. Spuštění automatiky zůstává výhradně na tlačítko.

Okno zobrazuje aktuální kolo a krok, počet dokončených a zbývajících jednotek **aktuálního kroku**, vstupní počet zdrojových položek, počet nově spárovaných položek, počet již uložených skupin a zbytek nespárovaných položek. CZK a EUR jsou oddělené. U kombinací Bookingu uvádí počet prohledaných stavů v aktuální komponentě a počet komponent s dosaženým limitem. Dále je dostupná doba běhu a přehled posledních 100 změn kroku.

Jednotka kroku je výslovně popsaná: doklad/rezervace, vazba, zdrojová/pokladní položka, skupina kandidátů nebo dvojice. Změna kroku či nové kolo obnovuje jeho ukazatel. Nejde o odhad procent celého běhu; konečný počet kol závisí na nalezených shodách. Nespárované položky nejsou automaticky neprověřené — některé nelze jednoznačně spojit. Vstupní a zbývající počty se vztahují k volným nenulovým zdrojovým položkám tohoto běhu, nikoli k členům již existujících ručních skupin.

Tlačítko **Zrušit párování**, Escape i zavírací křížek požádají o bezpečné zrušení. Okno zůstává viditelné do dokončení rozpracovaného kroku. Dokončené transakce zůstanou uložené. Při úspěchu, zrušení i chybě se průběh zavře a otevře existující okno skutečného výsledku. Neaktivuje se další běh ani potvrzování jednotlivých shod.

## Implementace a ověření

- `AutoRun` posílá strukturované snímky průběhu, přitom zachovává kompatibilitu textových callbacků. Průběžné události jsou omezené na 5/s; změna kroku a skutečně uložená skupina se oznamují okamžitě. Heartbeat databáze zůstává samostatný.
- `MatchingService` měří dokončené kroky nad skutečnými iteracemi. Doménová enumerace má jen volitelné pozorovatele průběhu; pravidla, limity a pořadí shod se nemění.
- `Job` předává události signálem do GUI vlákna. `AutoProgressDialog` nepřistupuje k databázi a nepoužívá sdílené měnitelné pracovní čítače.
- `tests/test_auto_progress.py` používá skutečný pracovní běh a skutečné okno, pozastaví jej po první uložené skupině a kontroluje databázi, hodnoty, 50% ukazatel, oddělení měn, zrušovací tlačítko, zavírání i ukončení při výjimce.
- Celá lokální sada: 153 testů, bez selhání a vynechání (`progress-regression-results.xml`). Nativní Windows CI je dohledatelné u commitu na GitHubu.
- `auto-progress.png` je snímek skutečného okna nad čtyřmi syntetickými zdrojovými položkami po uložení první skupiny.

Při prvním nativním Windows ověření (`34524481710`) prošly všechny nové testy průběhu, ale starší sekvenční undo/redo odhalilo závislost sémantického porovnání členů skupiny na pořadí nových membership UUID při shodném času. Deterministická reprodukce s pevnou časovou značkou a obráceným pořadím UUID před opravou selhala. Porovnání nyní kanonicky řadí členy; nemění členství, částky ani kontroly revizí. Reprodukce je v `tests/test_work.py`.
