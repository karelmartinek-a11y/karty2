# BetterHotel: ověření opravy 11. 9. 2026

Historický průběžný protokol před dokončením oprav. Konečný výsledek ověření
a uložení dat do programu je v [navazujícím protokolu](betterhotel-import-fix-2026-09-11.md).

Stav v době tohoto průběžného zápisu: opravy implementované, úplné ověření dosud NEDOKONČENO.

## Zachycené příčiny

1. `source` obsahuje UUID, zatímco `reservation_source` obsahuje objekt
   s týmž ID a lidským názvem. Původní kód interpretoval UUID jako název
   a vyvolal `API_SNAPSHOT_CONFLICT`, pole `name`. Normalizace nyní rozlišuje
   UUID od názvu; skutečně odlišné identity/názvy stále odmítá.
2. Detail faktury obsahuje platné `id` současně s prázdným `uuid`.
   Prázdný alias se nyní nepokouší nahradit známou identitu.
3. Položka účtu má `archived: false`, nikoli časové razítko.
   Boolean tohoto pole zůstává booleanem pouze pro položky účtu.
4. Odpověď kaucí obsahuje `items: []`, `deposit: []`.
   Strukturovaný rozpis zůstává zachován, není převáděn na částku.

## Důkazy a rozsah testů

- Původní kód načtený z Git HEAD selhal na zachyceném UUID tvaru;
  upravený kód stejný vstup přijal se správným ID a názvem.
- Cílené testy: 86 prošlo (API, doména, dokončení a nové regrese).
- Integrační test provádí celý import nad mock API a ověřuje `READY`
  i `COMPLETED`. Není vydáván za živý import.
- Celá sada před posledními dvěma rozšířeními: 163 prošlo, 10 selhalo.
  Pět selhání párovací logiky bylo reprodukováno i s původní normalizací
  z HEAD. Další selhání jsou v testech párovacího UI; celá sada není zelená.
- Dva čistě živé průchody po počáteční opravě odhalily postupně chyby
  položek účtu a kaucí. Následný průchod přehrává zaznamenané odpovědi
  a chybějící požadavky stahuje živě. Nejde o nový čistě živý průchod.
- Úspěšná normalizace seznamu sama o sobě nedokazuje publikaci grafu.

## Izolace a reprodukce

`tools/verify_live_sync.py` vytváří SQLite backup produkční databáze přes
read-only spojení. Import mění pouze tuto kopii; BetterHotel je volán GET.
Přihlašovací údaje se neuvádějí do výstupu. Testovací databáze a odpovědi
obsahují soukromá data a zůstávají v ignorovaném adresáři `.tmp`, nikoli v Git.

Čistě živý běh:

```powershell
.\.venv\Scripts\python.exe tools/verify_live_sync.py C:\Users\admin\AppData\Local\KajovoKarty\data\kajovokarty.sqlite D:\karty2\.tmp
```

Volitelný `--replay cesta\responses.sqlite` používá zachycené odpovědi
a stahuje pouze chybějící. Pro konečný čistě živý test tento přepínač nepoužívat.

## Zjištění o rozsahu

API pro rezervace vrací 15 507 záznamů jak s původním rozsahem
2025-09-11 až 2025-09-17, tak s daty 2099-01-01 až 2099-01-02.
Stejný výsledek má zkusmé vnořené `filter[date_from]` / `filter[date_to]`.
Mezi vrácenými pobyty jsou i zářijové termíny 2026.
Lokální časový filtr zatím nebyl přidán: bez určení významu filtru by mohl
neoprávněně vyřadit potřebné rezervace. Úplný průchod všemi vazbami je dlouhý.
