"""Business-language import summaries shared by the dialog and stored history."""

from pathlib import Path


def reason(diagnostic):
    code = diagnostic.get("code")
    messages = {
        "HEADER_INVALID": "Chybí potřebné názvy sloupců. Použijte export plateb z Bookingu.",
        "FORMAT_INVALID": "Soubor nemá podporovaný formát nebo je poškozený.",
        "FILE_CHANGED": "Soubor nelze přečíst nebo se během načítání změnil.",
        "FILE_TOO_LARGE": "Soubor je větší než povolená velikost v nastavení.",
        "SOURCE_CONFLICT": "Platba už v programu je, ale tento soubor o ní uvádí jiné údaje. Uloženou platbu jsme nepřepsali.",
        "UNKNOWN_ENUM": "Některý údaj o druhu nebo stavu platby má hodnotu, kterou program zatím neumí přečíst.",
        "MONEY_INVALID": "Částku platby se nepodařilo přečíst.",
        "DATE_INVALID": "Datum platby nebo pobytu se nepodařilo přečíst.",
        "IDENTITY_MISSING": "Chybí platné číslo rezervace nebo označení výplaty.",
        "ROW_SHAPE_INVALID": "Řádek nemá očekávaný počet sloupců.",
        "CANCELLED": "Načítání bylo zastaveno na váš pokyn.",
    }
    message = messages.get(code, diagnostic.get("message", "Soubor se nepodařilo načíst."))
    details = diagnostic.get("details") or {}
    if code == "SOURCE_CONFLICT" and isinstance(details, dict):
        old, new = details.get("old", {}), details.get("new", {})
        changed = [k for k in set(old) | set(new) if old.get(k) != new.get(k)]
        if changed == ["guest_name"]:
            message = "Platba už v programu je, ale v souboru je jinak napsané jméno hosta. Uloženou platbu jsme nepřepsali."
        booking = new.get("booking_reference") or old.get("booking_reference")
        if booking:
            message = f"Rezervace {booking}: " + message
    if diagnostic.get("row_start"):
        message = f"Řádek {diagnostic['row_start']}: " + message
    return message


def file_report(request, preview, state, outcome=None):
    parsed = preview.files[0].parsed if preview and preview.files else None
    counters = parsed.counters if parsed else {}
    data_rows = sum(v for k, v in counters.items() if k not in ("BLANK", "SUMMARY")) if parsed else None
    already = (outcome or {}).get("known", preview.known if preview else 0)
    added = (outcome or {}).get("new", 0)
    excluded = {k: counters.get(k, 0) for k in ("UNPAID", "ZERO_AMOUNT") if counters.get(k)}
    diagnostics = preview.diagnostics if preview else []
    errors = list(dict.fromkeys(reason(d) for d in diagnostics if d.get("severity") == "ERROR"))
    return {
        "name": Path(request.original_name or request.path or (preview.files[0].name if preview and preview.files else "Soubor")).name,
        "state": state,
        "added": added,
        "already_saved": already,
        "excluded": excluded,
        "not_loaded": max(0, data_rows - added - already - sum(excluded.values())) if data_rows is not None else None,
        "errors": errors,
    }


def file_text(report):
    lines = [report["name"]]
    if report["state"] == "NOT_STARTED":
        return report["name"] + "\nTento soubor jsme ještě nezačali načítat, protože jste import zastavili."
    if report["state"] == "COMPLETED":
        lines.append(f"Načtené platby: {report['added']}.")
    elif report["state"] == "CANCELLED":
        lines.append("Načítání tohoto souboru jste zastavili. Žádnou platbu z něj jsme nepřidali.")
    else:
        lines.append("Tento soubor se nepodařilo načíst. Žádnou platbu z něj jsme nepřidali.")
    if report["already_saved"]:
        lines.append(f"Platby, které už v programu byly: {report['already_saved']}. Podruhé jsme je neukládali.")
    if report["excluded"].get("UNPAID"):
        lines.append(f"Nezařazené platby označené jako neuhrazené: {report['excluded']['UNPAID']}.")
    if report["excluded"].get("ZERO_AMOUNT"):
        lines.append(f"Nezařazené platby s nulovou částkou: {report['excluded']['ZERO_AMOUNT']}.")
    if report["not_loaded"]:
        lines.append(f"Další nenačtené platby: {report['not_loaded']}. Kvůli chybě se neuložil celý soubor, ani jeho ostatní řádky.")
    if report["not_loaded"] is None:
        lines.append("Počet plateb nelze určit, protože se soubor nepodařilo přečíst.")
    if report["errors"]:
        lines.append("Proč se soubor nepodařilo načíst:")
        lines.extend("• " + message for message in report["errors"])
    return "\n".join(lines)


def batch_text(reports):
    added = sum(r["added"] for r in reports)
    already = sum(r["already_saved"] for r in reports)
    done = sum(r["state"] == "COMPLETED" for r in reports)
    failed = sum(r["state"] == "FAILED" for r in reports)
    stopped = sum(r["state"] in ("CANCELLED", "NOT_STARTED") for r in reports)
    lines = [f"Načtené platby celkem: {added}.", f"Platby, které už v programu byly a nebylo je potřeba ukládat znovu: {already}.",
             f"Úspěšně zpracované soubory: {done} z {len(reports)}."]
    if failed:
        lines.append(f"Soubory, které se nepodařilo načíst: {failed}. Důvody najdete níže u jejich názvů.")
    if stopped:
        lines.append(f"Zastavené nebo dosud nezpracované soubory: {stopped}. Již načtené platby zůstávají uložené.")
    return "\n".join(lines) + "\n\n" + "\n\n".join(file_text(r) for r in reports)
