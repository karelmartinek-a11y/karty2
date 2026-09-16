# Pracovní postup 0.4.5

Autoritou pro přesné podmínky je [SSOT](SSOT.md). Tento postup nahrazuje historický UI_WORKFLOW 0.3.0.

## Import a automatika

Vyberte zdroj a soubory. Import začne automaticky, ukáže průběh a konečný výsledek; potvrzení Hotovo pouze zavře výsledky. Vadný soubor se neuloží, dříve dokončené soubory zůstanou zachované. Účty jsou pomocné vazby, ne platby.

Automaticky spárovat vše pracuje nad celou databází, ne jen nad právě zobrazeným filtrem. Výsledek obsahuje vytvořené skupiny a jejich měny. Limitem hledání nebo nejednoznačností se nesmí obejít finanční pravidla. Zastavení zachová již dokončené skupiny.

## Párovací plocha

- Přidat do párovací plochy a přetažení načítají zvolené položky do pracovního návrhu. Přetažení samo neukládá ani nemaže platby.
- Horní tabulka i kandidáti: **Zdroj, Datum, Částka, Měna, Identifikátor, Položka**. T = terminál, P = pokladna, B = Booking. Nápověda po najetí myší zobrazí celé hodnoty.
- Datum má v buňce formát DD.MM.YYYY; Booking používá check-out. Interní data, přesné částky, řazení a exportní hodnoty zůstávají nezměněné.
- Vyhledat kandidáty nastaví zdrojový filtr na všechny ostatní zdroje podle první položky návrhu. Například pro T nabídne P a B. Filtr je vratný.
- Vyjmout označené nebo přesun do vyjímacího rámečku odebere položku z návrhu. Opakované přetažení nevytvoří duplikát.
- Uložit skupinu vyžaduje nejméně dvě různé platby, jednu měnu a přesný nulový rozdíl. Uložení znovu ověří aktuálnost položek. Změna se projeví ve všech pohledech bez ručního obnovení.
- Chyba aktuálnosti znamená znovu vybrat položky, nikoli přepsat cizí změnu. Undo/Redo se týká uložených příkazů, ne samotného pohybu v návrhu.

Šířky horních a dolních sloupců jsou sladěné. Popis využívá zbývající prostor a může být zkrácený. Ve velmi úzkém okně nebo při velkém písmu je dostupný vodorovný posun; úplné zobrazení libovolně dlouhých hodnot se neslibuje. Staré široké rozložení hlavního přehledu je odděleno verzovaným klíčem od nového kompaktního nastavení.

## Zálohy a bezpečnost

Zálohu před obnovou aplikace ověřuje. Denní údržba odstraňuje jen ověřené prošlé archivy vlastního formátu, ne libovolný ZIP shodného názvu. Úplný reset je samostatná destruktivní operace s potvrzením VYMAZAT. Nepoužívejte jej k řešení chybějících oprávnění.
