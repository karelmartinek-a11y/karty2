"""Context-bound evidence, projection merging and Booking decisions."""

import re, html, unicodedata
from datetime import datetime, timezone
from uuid import UUID
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from kajovokarty.domain.core import (
    AppError,
    decimal_money,
    digest,
    identifier,
    money,
    parse_date,
    require,
    text,
)

REFERENCE_VERSION = "BOOKING-NOTE-1"
INVOICE_ROW_VERSION = "INVOICE-ROW-1"


def api_currency(value, currencies):
    value = identifier(value)
    if not value:
        return None
    resolved = currencies.get(value, value).upper()
    return resolved if re.fullmatch(r"[A-Z]{3}", resolved) else None


def invoice_rows(invoice_id, items, currencies, parent_currency):
    """Parent-owned occurrences; API IDs may be reused for a Deposit row."""
    occurrences = {}
    for raw in ([items] if isinstance(items, dict) else items):
        normalized = normalize_entity("invoice_item", raw, currencies, parent_currency)
        fingerprint = digest(normalized)
        occurrence = occurrences.get(fingerprint, 0)
        occurrences[fingerprint] = occurrence + 1
        row_id = digest([INVOICE_ROW_VERSION, invoice_id, normalized["id"],
                         fingerprint, occurrence])
        yield raw, row_id


def api_reservation_source(value):
    """Normalize BetterHotel source and reservation_source aliases."""
    if value is None:
        return None
    if isinstance(value, dict):
        value = dict(value)
        for canonical_key, aliases, normalize in (
            ("id", ("id", "uuid", "source_id"), source_identity),
            ("name", ("name", "source_name"), text),
        ):
            present = [key for key in aliases if key in value]
            values = [normalize(value.pop(key)) for key in present]
            known = [v for v in values if v is not None]
            require(len(set(known)) <= 1, "API_SNAPSHOT_CONFLICT",
                    "Konfliktní aliasy zdroje rezervace.",
                    {"field": "reservation_source." + canonical_key, "values": known})
            if known:
                value[canonical_key] = known[0]
        return value
    value = text(value)
    if value is None:
        return None
    if re.fullmatch(r"[0-9]+", value):
        return {"id": source_identity(value)}
    try:
        return {"id": str(UUID(value))}
    except ValueError:
        pass
    return {"name": value}


def source_identity(value):
    if value is None:
        return None
    result = api_id(value)
    try:
        return str(UUID(result))
    except ValueError:
        return result


def api_money(value):
    """Normalize BetterHotel helper amounts to cents.

    BetterHotel can return calculated helper totals with more than two decimal
    places. These are informational values, not financial source amounts, so
    they are rounded half-up at the API boundary before canonicalization.
    """
    try:
        amount = Decimal(str(value))
        amount = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return decimal_money(int(amount * 100))
    except (InvalidOperation, ValueError, TypeError, OverflowError):
        raise AppError("API_SCHEMA", "Neplatná částka z API.")


def extract_references(notes, channel):
    origins = []
    for note in notes or []:
        raw = note.get("channel")
        if raw is None:
            continue
        s = unicodedata.normalize("NFC", html.unescape(str(raw)))
        s = re.sub(r"(?i)<br\s*/?>", "\n", s)
        s = re.sub(r"<[^>]*>", " ", s).replace("\r\n", "\n").replace("\r", "\n")
        s = re.sub(r"[^\S\n]+", " ", s)
        for m in re.finditer(
            r"(?i)(Original\s*ID|Channel\s*reservation\s*id)\s*[:=]?\s*([0-9]{6,20})(?![0-9])",
            s,
        ):
            origins.append(
                {
                    "candidate": m[2],
                    "label": m[1],
                    "start_offset": m.start(2),
                    "end_offset": m.end(2),
                    "normalized_text": s,
                    "raw_hash": digest(raw),
                }
            )
    candidates = sorted({r["candidate"] for r in origins})
    channel_name = (text(channel) or "").casefold() or None
    return {
        "candidates": candidates,
        "origins": origins,
        "channel_name": channel_name,
        "parser_version": REFERENCE_VERSION,
        "candidate_set_hash": digest(
            {
                "parser_version": REFERENCE_VERSION,
                "channel_name": channel_name,
                "candidates": candidates,
            }
        ),
        "status": "MISSING"
        if not candidates
        else "CONFIRMED"
        if len(candidates) == 1
        else "CONFLICT",
    }


def reference_decision(ref, override=None, active=True):
    valid = bool(
        active
        and override
        and override["active"]
        and override["candidate_set_hash"] == ref["candidate_set_hash"]
        and (not override["accepted"] or override["candidate"] in ref["candidates"])
    )
    candidate = None
    if not active:
        status = "INACTIVE_CONTEXT_OR_ENTITY"
    elif override and override["active"] and not valid:
        status = "REVIEW_REQUIRED"
    elif valid and not override["accepted"]:
        status = "REJECTED"
    elif ref["channel_name"] != "booking.com":
        status = "CHANNEL_BLOCKED"
    elif valid:
        status = "MANUAL_ACCEPT"
        candidate = override["candidate"]
    elif len(ref["candidates"]) == 1:
        status = "AUTO_CONFIRMED"
        candidate = ref["candidates"][0]
    else:
        status = ref["status"]
    return {
        "resolution_status": status,
        "effective_candidate": candidate,
        "override_valid": valid,
        "candidate_set_hash": ref["candidate_set_hash"],
    }


def merge(a, b, _path=""):
    result = dict(a)
    for k, v in b.items():
        if k not in result:
            result[k] = v
        elif k == 'reservation_source' and result[k] is None:
            result[k] = v
        elif k == 'reservation_source' and v is None:
            continue
        elif isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = merge(result[k], v, _path + k + ".")
        else:
            require(
                result[k] == v,
                "API_SNAPSHOT_CONFLICT",
                "Projekce stejné entity obsahují rozdílné hodnoty.",
                {"field": _path + k},
            )
    return result


def api_id(v):
    if isinstance(v, dict):
        v = v.get("id", v.get("uuid"))
    val = identifier(v)
    require(val, "API_SCHEMA", "Entita nemá stabilní ID.")
    return val


def api_timestamp(v):
    if v is None:
        return None
    try:
        dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (
            dt.astimezone(timezone.utc)
            .isoformat(timespec="microseconds")
            .replace("+00:00", "Z")
        )
    except ValueError:
        raise AppError("API_SCHEMA", "Neplatný API timestamp.")


def normalize_entity(kind, raw, currencies, parent_currency=None):
    require(isinstance(raw, dict), "API_SCHEMA", "Entita není JSON objekt.")
    aliases = {"uuid": "id"}
    if kind == "invoice":
        aliases.update(number="code", invoice_item="items", invoice_items="items")
    if kind == "reservation":
        aliases.update(
            source="reservation_source", date_from="arrival", date_to="departure"
        )
    if kind == "bill":
        aliases.update(
            reservation_uuid="reservation_id",
            saldo="balance",
            closed="is_closed",
            locked="is_locked",
        )
    if kind == "bill_item":
        aliases.update(bill_uuid="bill_id", total="amount")
    if kind == "invoice_item":
        aliases.update(
            uuid="id",
            bill_item="bill_item_id",
            amount="signed_amount",
            total="signed_amount",
            date_from="service_from",
            date_to="service_to",
        )
    if kind == "security_deposit":
        aliases.update(total="amount")
    result = {}
    raw = dict(raw)
    # A detail may carry a valid id and an empty legacy uuid alias.
    if text(raw.get('id')) and not text(raw.get('uuid')):
        raw.pop('uuid', None)
    elif text(raw.get('uuid')) and not text(raw.get('id')):
        raw.pop('id', None)
    if kind == "invoice" and "payed" in raw:
        if "paid" not in raw:
            raw["paid"] = raw["payed"]
        elif raw["paid"] is not None and raw["payed"] is not None:
            a = api_timestamp(raw["paid"])
            b = api_timestamp(raw["payed"])
            if (
                abs(
                    (
                        datetime.fromisoformat(a.replace("Z", "+00:00"))
                        - datetime.fromisoformat(b.replace("Z", "+00:00"))
                    ).total_seconds()
                )
                <= 0.001
            ):
                raw["paid"] = min(a, b)
        raw.pop("payed")
    for key, value in raw.items():
        k = aliases.get(key, key)
        if (
            k in ("id", "bill_id", "reservation_id", "bill_item_id")
            and value is not None
        ):
            value = api_id(value)
        if k == "currency":
            reference = identifier(value)
            value = api_currency(value, currencies)
            if value is None:
                if reference:
                    result["currency_reference"] = reference
                continue
        if k in ("note", "label"):
            # Optional descriptive text: null, empty and whitespace are equivalent.
            value = text(value)
            if value is None:
                continue
        if k == "reservation_source":
            value = api_reservation_source(value)
        if (
            k in ("total", "subtotal", "deposit", "amount", "balance", "signed_amount")
            and value is not None
            # This endpoint also returns a reservation-level deposit breakdown.
            and not (kind == "security_deposit" and k == "deposit"
                     and isinstance(value, (list, dict)))
        ):
            value = api_money(value)
        if (
            k in ("date", "due_date", "vat_date", "archived", "paid", "payed")
            and value is not None
            # Bill items expose an archive flag, unlike invoice timestamps.
            and not (kind == "bill_item" and k == "archived" and type(value) is bool)
        ):
            value = api_timestamp(value)
        if (
            k in ("arrival", "departure", "service_from", "service_to")
            and value is not None
        ):
            value = parse_date(str(value)[:10])
        if k in ("code", "number") and value is not None:
            value = identifier(value)
        if k in ("pay_method", "print_format") and value is not None:
            value = identifier(value)
            require(
                re.fullmatch(r"-?[0-9]+", value), "API_SCHEMA", "Očekáváno celé číslo."
            )
            value = int(value)
        if k in ("is_closed", "is_locked") and value is not None:
            norm = str(value).casefold()
            value = (
                True
                if norm in ("true", "1", "yes", "ano", "closed", "locked")
                else False
                if norm in ("false", "0", "no", "ne", "open", "unlocked")
                else None
            )
        if kind == "invoice" and k == "items":
            require(
                isinstance(value, (list, dict)),
                "API_SCHEMA",
                "Položky dokladu mají neplatný formát.",
            )
            value = [
                normalize_entity(
                    "invoice_item",
                    item,
                    currencies,
                    # Inherited currency belongs to the extracted child entity,
                    # not the parent's raw item projection (which may be sparse).
                    None,
                )
                for item in (value if isinstance(value, list) else [value])
            ]
            value = sorted(value, key=lambda x: (x.get("id", ""), digest(x)))
        if k == "reservation_note":
            require(
                isinstance(value, list) and all(isinstance(n, dict) for n in value),
                "API_SCHEMA",
                "Neplatné poznámky rezervace.",
            )
            value = sorted(
                value, key=lambda x: (identifier(x.get("id")) or "", digest(x))
            )
        if k == "reservation_source" and k in result:
            try:
                result[k] = merge(result[k] or {}, value or {}) or None
            except AppError as error:
                error.details = {"field": "reservation_source." + error.details.get("field", "unknown"),
                                 "left": result[k], "right": value}
                raise
            continue
        if k in result:
            require(
                result[k] == value,
                "API_SNAPSHOT_CONFLICT",
                "Konfliktní aliasy API pole.",
                {"field": k},
            )
        result[k] = value
    if "id" not in result and kind == "currency":
        result["id"] = api_id(raw.get("code"))
    require(result.get("id"), "API_SCHEMA", "Chybí ID entity.")
    if (
        kind == "invoice"
        and result.get("print_format") == 3
        and result.get("total") is not None
    ):
        result["total"] = decimal_money(-abs(money(result["total"])))
    if (
        kind in ("invoice_item", "bill_item")
        and not result.get("currency")
        and parent_currency
    ):
        result["currency"] = parent_currency
    return result
