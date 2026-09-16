# Dokumentace projektu

## Aktuální autorita

- [SSOT 0.4.5](SSOT.md): finanční pravidla, priority, invarianty, schéma a bezpečnost.
- [Pracovní postup](WORKFLOW_CURRENT.md): současné importy a párovací plocha.
- [Audit 0.4.5](AUDIT_0_4_5.md): reprodukce, opravy, ověření, rizika a optimalizace.
- [Účty](ACCOUNTS_IMPORT.md), [Booking](BOOKING_IMPORT.md), [datum Booking plateb](BOOKING_CHECKOUT.md), [průběh importu](IMPORT_PROGRESS.md).
- [Katalog chyb](ERROR_CATALOG.md): generovaný přímo z běhového číselníku.

## Historické protokoly

UI_WORKFLOW, VALIDATION, AUTO_AUDIT, AUTO_PROGRESS, SSOT_0_3_ARCHIVE a datované či verzované protokoly zachycují tehdejší stav. Jejich testovací počty, hashe, screenshoty a omezení nejsou automaticky platné pro současné vydání. Při rozporu platí aktuální SSOT a audit 0.4.5, nikoli nejvyšší počet testů uvedený ve starém souboru.

Historické XML/JSON výsledky a obrázky zůstávají jako důkazy minulých běhů. Pro nové ověření vznikají samostatné soubory; staré úspěchy se nevydávají za nové testování.

## Reprodukce kontrol

Příkazy spouštějte z kořene projektu v připraveném vývojovém prostředí:

```powershell
.venv\Scripts\python.exe -m pip check
.venv\Scripts\python.exe -m ruff check src tests tools --select F --no-cache
.venv\Scripts\python.exe tools/error_catalog.py --check
.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --junitxml=docs/audit-0.4.5-tests.xml
.venv\Scripts\python.exe tools/audit_dependencies.py --output docs/audit-0.4.5-dependencies.json
.venv\Scripts\python.exe tools/audit_repository.py --output .tmp/audit-inventory.json
```

Kontrola závislostí odesílá na veřejné PyPI pouze názvy a verze veřejných balíčků. Neotevírá provozní data. Nepokrývá samostatný audit všech nativních knihoven Qt.

Volitelný distribuční test: `KajovoKarty.exe --self-test-report C:\existujici-testovaci-slozka\novy-report.json`. Report nesmí existovat. Test používá nový dočasný prostor, syntetické Booking platby a nikdy neotevírá standardní provozní umístění. Ověřuje běhové závislosti a základní cestu aplikace, nenahrazuje plnou testovací sadu ani instalaci na čistém Windows profilu.
