> Historický dokument; aktuální pravidla a výsledky jsou v [SSOT](SSOT.md) a [auditu 0.4.5](AUDIT_0_4_5.md). Níže zachovaný obsah popisuje tehdejší stav.

# Přehledy plateb — verze 0.4.3

## Změny

- V přehledech všech plateb a tabulce protějšků jsou skryté sloupce Důvod, Poznámka, Rozdíl, Stav a Objekt. Nabídka sloupců je nenabízí a staré uložené rozložení je nezobrazí.
- Staré sloupcové filtry a řazení skrytých polí se při zobrazení plateb odstraní. Výslovné rozšířené filtry, vyřízené/nevyřízené přehledy, detaily a souhrny párovací plochy zůstávají funkční.
- Datum má český formát **07. září 2026**, také v nabídce hodnot filtru. Vnitřní data, chronologické řazení, hodnoty filtrů a formát exportů zůstávají zachované.
- Při filtru pouze na Booking, včetně uloženého filtru, se sloupec jmenuje **Booking.com ID**. Ve smíšeném přehledu a u ostatních zdrojů zůstává **Identifikátor**. Interní označení skupiny se nevydává za číslo rezervace.
- **Počet listů** se nově jmenuje **Počet plateb**. Šířka sloupce pojme celý název.
- Výchozí stav má samostatný informační kód `NOT_YET_MATCHED` a text **Dosud nepárováno**. Původní text stejného významu je podporovaný i v rozšířeném filtru. Nespadá do obecného hlášení chyby.

## Ověření

Samostatných **16 regresních testů** ověřuje české měsíce, přestupný den, řazení a hodnoty filtrů, původní stav a jeho kompatibilitu, zachování skutečných chyb, obnovu starého rozložení, přepínání zdrojů a obrazovek, restart a označení skupin. [Výsledky](payment-ui-test-results.xml).

Skutečné Qt tabulky byly vykresleny a vizuálně zkontrolovány pro Booking, smíšené zdroje a prázdný výsledek. Testy filtrování používají viditelné sloupce a přetažení platby používá skutečnou viditelnou buňku. Celá sada: **255 testů prošlo**, bez chyb; [celkový protokol](windows-test-results.xml).

Sestavená aplikace obsahuje moduly shodné se zdrojovým kódem; [kontrola balíčku](payment-ui-package-verification.json). [Kontrolní součet instalátoru](windows-installer-sha256.txt).

Testování proběhlo na dočasných datech. Provozní platby nebyly měněny. Instalátor nebyl instalován do provozního prostředí.
