# Import plateb z Bookingu

V nabídce **Importovat → Booking CSV** můžete vybrat více CSV souborů najednou (Ctrl nebo Shift). Po potvrzení tlačítkem **Načíst vybrané soubory** program postupně zpracuje každý soubor zvlášť.

Výsledek ukáže celkový počet načtených plateb a u každého souboru vysvětlí:

- kolik plateb přibylo;
- kolik plateb už bylo uloženo a nebylo potřeba je ukládat znovu;
- kolik plateb nebylo zařazeno kvůli neuhrazenému stavu nebo nulové částce;
- kolik dalších plateb se nenačetlo a proč, včetně řádku souboru, pokud je známý.

Chyba v jednom souboru nebrání načtení dalších. Soubor s chybou se neukládá ani částečně. Již úspěšně načtené soubory zůstanou uložené i při zastavení importu. Pokud soubor nelze přečíst, program výslovně uvede, že počet jeho plateb nelze určit.

Výsledky zůstávají dostupné také v přehledu Importy a v detailu jednotlivého importu. Samotný import nespouští automatické párování.

Stav pobytu (včetně `no_show`), jméno hosta, poskytovatel a data pobytu jsou doplňující údaje. Neznámý stav či nečitelné datum pobytu neblokují platbu. Rozdíly v těchto údajích mezi exporty nezpůsobují odmítnutí již známé platby; původně uložená platba zůstane zachována. Nadále se kontroluje číslo rezervace, označení a datum výplaty, měna, částka a platební údaje. Platby označené jako neuhrazené se nezařazují.
