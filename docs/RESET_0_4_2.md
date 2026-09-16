> Historický dokument; aktuální pravidla a výsledky jsou v [SSOT](SSOT.md) a [auditu 0.4.5](AUDIT_0_4_5.md). Níže zachovaný obsah popisuje tehdejší stav.

# Úplný reset — verze 0.4.2

## Použití

V Nastavení zvolte **Resetovat celý program**, přečtěte si rozsah mazání, napište přesně **VYMAZAT** a stiskněte **Vymazat vše a restartovat**. Reset nelze spustit během jiné úlohy. Při opuštění potvrzení se nic nemaže.

Zmizí veškerý obsah aktuálního pracovního prostoru včetně uložených importních souborů, pomocných vazeb, historie, přihlašovacích údajů a nastavení. Odstraní se také rozpoznané zálohy, diagnostické archivy, staré logy a známé kopie po obnově. Nová záloha před resetem nevznikne. Původní vstupní soubory mimo aplikaci, uložené exporty a cizí soubory zůstanou zachované.

Externí složka záloh se kontroluje přímo, bez prohledávání jejích podsložek nebo celého disku. Libovolné kopie uložené jinde se nevyhledávají. Aktuální umístění pracovních dat se nemění. Po restartu se používají výchozí volby, proto opět mohou vznikat nové provozní záznamy a denní zálohy.

## Ochrana před neúplným resetem

Prázdná databáze se připraví a ověří před prvním mazáním. Aplikace zastaví časovače, dokončí pracovní vlákna a uzavře okno; po dobu resetu drží zámek pracovního prostoru. Odstranění probíhá podle trvalého seznamu. Při zamčeném souboru nebo přerušení zůstane záznam pro dokončení resetu. Běžná práce s daty je do dokončení zablokována.

Hlásí se odděleně probíhající jiná činnost, neúspěšná příprava a neúplný reset. Významy jsou součástí společného číselníku chyb. Závazný popis je v [SSOT, oddíl 9](SSOT.md#9-úplný-reset).

## Ověření na Windows 10 / Python 3.12

- Celá sada: **239 testů prošlo**, bez chyb; [výsledky](windows-test-results.xml).
- Závěrečná samostatná sada resetu: **18 testů prošlo**; [výsledky](reset-test-results.xml).
- Skutečné Qt ovládání: Nastavení → potvrzení slovem → restart → prázdné okno s výchozími volbami.
- Ověřeny všechny počty tabulek vůči nové databázi, nový import a automatické párování po resetu, vlastní i sdílené složky záloh, starší kopie a logy, kopie po obnově, zachování cizích souborů, nedostatek místa, uzamčený soubor, přerušení po výměně databáze, neplatný cíl a přesměrovaná složka.
- Potvrzení, blokování běžících úloh a odmítnutí otevřít běžné okno při nedokončeném resetu mají regresní testy. Nastavení a potvrzovací dialog byly také vykresleny a vizuálně zkontrolovány.
- Statická kontrola změněných modulů a `git diff --check` prošly.
- Sestavena Windows aplikace a instalátor 0.4.2. Obsah přibalených modulů resetu, startu, Nastavení, hlavního okna a číselníku byl porovnán se zdrojovým kódem; [ověření balíčku](reset-package-verification.json), [SHA-256 instalátoru](windows-installer-sha256.txt).

Testy použily pouze dočasné zkušební prostory. Provozní data nebyla resetována. Instalátor se sestavuje pro Windows; instalace do provozního prostředí ani odinstalace nejsou součástí této kontroly.
