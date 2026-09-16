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


from kajovokarty.domain.errors import CATALOG, explain

REASON_NAMES = {code: item.name for code, item in CATALOG.items()}


def display_value(key, value):
    if value is None or value == "":
        return ""
    if key == "reason":
        return explain(value).name
    if key in {"date", "date_end"} and isinstance(value, (str, date)):
        try:
            day = date.fromisoformat(value) if isinstance(value, str) else value
        except ValueError:
            return str(value)
        months = ("ledna", "února", "března", "dubna", "května", "června",
                  "července", "srpna", "září", "října", "listopadu", "prosince")
        return f"{day.day:02d}. {months[day.month - 1]} {day.year:04d}"
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
