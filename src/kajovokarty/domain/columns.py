"""Shared typed column semantics for SQLite, tables, export and filter menus."""

import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from kajovokarty.domain.core import canonical, display_money, search_normalize

MONEY_FIELDS = {"amount", "difference", "pair_difference", "contribution"}
KIND_NAMES = {
    "CASHBOOK_CARD": "Pokladna",
    "BANK_CARD": "Terminál",
    "BOOKING": "Booking",
}


def value_token(value):
    if value is None or value == "":
        return "null"
    if isinstance(value, (tuple, set)):
        value = sorted(value)
    if isinstance(value, (date, datetime, Decimal)):
        value = str(value)
    return canonical(value)


def sql_token(field, value):
    if field == "kinds":
        value = sorted(value.split(",")) if value else []
    elif field == "resolved":
        value = bool(value)
    return value_token(value)


REASON_NAMES = {
    "AUTO_SUPPRESSED": "Automatické spojení ručně zakázáno",
    "AUTO_SEARCH_LIMIT": "Dosažen limit hledání kombinací",
    "MULTIPLE_CANDIDATES": "Více možných shod — vyberte ručně",
    "HELPER_DATA_NOT_SYNCED": "Pomocná data nejsou ověřena pro toto období",
    "HELPER_ENTITY_NOT_OBSERVED": "Vazba obsahuje neaktivní nebo neúplná pomocná data",
    "HELPER_CHAIN_UNVERIFIED": "Nelze ověřit nepřítomnost vazby na pokladnu",
    "CURRENCY_MISMATCH": "Nesouhlasí měna dokladového řetězce",
    "CASHBOOK_NO_DOCUMENT": "Pokladní položka nemá jednoznačný doklad",
    "DOCUMENT_NO_RESERVATION": "Doklad nemá jednoznačnou rezervaci",
    "RESERVATION_NO_BOOKING_REFERENCE": "Neznámý kanál nebo chybějící Booking reference",
    "BOOKING_REFERENCE_REJECTED": "Booking reference byla ručně odmítnuta",
    "BOOKING_REFERENCE_REVIEW_REQUIRED": "Booking reference vyžaduje nové rozhodnutí",
    "BOOKING_REFERENCE_NOT_FOUND": "Pro Booking referenci chybí importovaná platba",
    "CASHBOOK_NO_COUNTERPART": "Pokladna: nenalezen protějšek",
    "BANK_NO_COUNTERPART": "Terminál: nenalezen protějšek",
    "BOOKING_NO_COUNTERPART": "Booking: nenalezen protějšek",
    "RUN_NOT_COMPLETED": "Běh byl přerušen — zbývající položky vyžadují nový běh",
    "OPEN_AGGREGATE": "Otevřená skupina — zbývá rozdíl",
    "NO_COUNTERPART": "Nenalezen protějšek",
    "NO_HELPER": "Chybí aktuální pomocná data",
    "HELPER_UNAVAILABLE": "Pomocná data nejsou dostupná",
    "HELPER_MISSING": "Chybí důkaz z BetterHotel",
    "AMBIGUOUS": "Více možných shod — vyberte ručně",
    "SEARCH_LIMIT": "Dosažen limit hledání kombinací",
    "SUPPRESSED": "Automatické spojení ručně zakázáno",
    "AMOUNT_MISMATCH": "Nesouhlasí částky",
    "REJECTED": "Reference ručně odmítnuta",
    "REVIEW_REQUIRED": "Reference vyžaduje kontrolu",
}


def display_value(key, value):
    if value is None or value == "":
        return ""
    if key == "reason":
        return REASON_NAMES.get(value, str(value))
    if key == "resolved":
        return "Vyřízeno" if value else "Nevyřízeno"
    if key == "type" and value in ("SOURCE", "GROUP"):
        return "Položka" if value == "SOURCE" else "Skupina"
    if (key in MONEY_FIELDS or key.endswith("_minor")) and isinstance(value, int):
        return display_money(value)
    if key == "kinds" and isinstance(value, (list, tuple)):
        return " + ".join(KIND_NAMES.get(k, k) for k in sorted(value))
    if isinstance(value, (dict, list, tuple)):
        return canonical(value)
    if isinstance(value, bool):
        return "Ano" if value else "Ne"
    return str(value)


def sort_value(value):
    if isinstance(value, bool):
        return (0, int(value))
    if isinstance(value, (int, float, Decimal)):
        try:
            n = Decimal(str(value))
            if n.is_finite():
                return (0, n)
        except InvalidOperation:
            pass
    return (1, search_normalize(display_value("", value)))


def matches(row, filters, excluded=None):
    return all(
        key == excluded or value_token(row.get(key)) in selected
        for key, selected in filters.items()
    )


def filter_rows(rows, filters=None, sort=None):
    result = [r for r in rows if matches(r, filters or {})]
    # Python stable ordering preserves original order as final tie breaker.
    for key, direction in reversed(sort or []):
        populated = [r for r in result if r.get(key) is not None and r.get(key) != ""]
        blank = [r for r in result if r.get(key) is None or r.get(key) == ""]
        result = (
            sorted(
                populated,
                key=lambda r: sort_value(r.get(key)),
                reverse=direction == "desc",
            )
            + blank
        )
    return result


def filter_options(rows, field, filters=None):
    values = {
        value_token(r.get(field)) for r in rows if matches(r, filters or {}, field)
    }
    return [
        (display_value(field, json.loads(token)) or "(Prázdné)", token)
        for token in sorted(values, key=lambda t: sort_value(json.loads(t)))
    ]
