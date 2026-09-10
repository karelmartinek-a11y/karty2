"""Exact financial primitives. This module has no infrastructure dependencies."""

from __future__ import annotations
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import html
import json
import re
import unicodedata
import uuid
from zoneinfo import ZoneInfo

LIMIT = 9_000_000_000_000_000
KINDS = ("CASHBOOK_CARD", "BANK_CARD", "BOOKING")


class AppError(Exception):
    def __init__(self, code: str, message: str, details=None, retryable=False):
        super().__init__(message)
        self.code, self.message, self.details = code, message, details or {}
        self.retryable = retryable
        self.operation_id = None

    def as_dict(self):
        return dict(
            code=self.code,
            message=self.message,
            details=self.details,
            retryable=self.retryable,
            operation_id=self.operation_id,
        )


def require(ok, code, message, details=None):
    if not ok:
        raise AppError(code, message, details)


def uid():
    return uuid.uuid4().hex


def now():
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def canonical(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def bytehash(value):
    return hashlib.sha256(value).hexdigest()


def checked(n):
    require(
        type(n) is int and abs(n) <= LIMIT,
        "MONEY_INVALID",
        "Částka nebo součet překračuje povolený rozsah.",
    )
    return n


def text(value):
    if value is None:
        return None
    s = (
        unicodedata.normalize("NFKC", html.unescape(str(value)))
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .strip()
    )
    return s or None


def identifier(value):
    if value is None:
        return None
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        try:
            d = Decimal(str(value))
        except InvalidOperation:
            raise AppError("IDENTITY_MISSING", "Neplatný číselný identifikátor.")
        require(
            d.is_finite() and d == d.to_integral_value() and abs(d) < 10**15,
            "IDENTITY_MISSING",
            "Identifikátor musí být celé číslo nejvýše s 15 číslicemi.",
        )
        return str(int(d))
    return unicodedata.normalize("NFKC", str(value)).strip() or None


def header(value):
    return " ".join(
        unicodedata.normalize("NFKC", str(value or "").replace("\ufeff", "")).split()
    ).casefold()


def currency(value):
    v = (identifier(value) or "").upper()
    require(v in ("CZK", "EUR"), "CURRENCY_UNSUPPORTED", "Měna musí být CZK nebo EUR.")
    return v


def money(value, empty_zero=False):
    if value is None or (isinstance(value, str) and not value.strip()):
        require(empty_zero, "MONEY_INVALID", "Chybí částka.")
        return 0
    require(not isinstance(value, bool), "MONEY_INVALID", "Boolean není částka.")
    s = str(value).strip().replace("\u00a0", " ").replace("\u202f", " ")
    require(
        bool(
            re.fullmatch(r"[+-]?(?:[0-9]+|[0-9]{1,3}(?: [0-9]{3})+)(?:[.,][0-9]+)?", s)
        ),
        "MONEY_INVALID",
        "Neplatný formát částky.",
    )
    try:
        d = Decimal(s.replace(" ", "").replace(",", ".")) * 100
    except InvalidOperation:
        raise AppError("MONEY_INVALID", "Neplatná částka.")
    require(
        d.is_finite() and d == d.to_integral_value(),
        "MONEY_INVALID",
        "Částka nesmí vyžadovat zaokrouhlení.",
    )
    return checked(int(d))


def decimal_money(n):
    checked(n)
    return ("-" if n < 0 else "") + str(abs(n) // 100) + "." + f"{abs(n) % 100:02d}"


def display_money(n):
    return (
        ("−" if n < 0 else "")
        + f"{abs(n) // 100:,}".replace(",", " ")
        + ","
        + f"{abs(n) % 100:02d}"
    )


def parse_date(value):
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    s = str(value or "").strip()
    m = re.fullmatch(r"([A-Za-z]{3})\s+(\d{1,2}),\s*(\d{4})", s)
    try:
        if m:
            months = {
                v: i + 1
                for i, v in enumerate(
                    "jan feb mar apr may jun jul aug sep oct nov dec".split()
                )
            }
            return date(int(m[3]), months[m[1].lower()], int(m[2])).isoformat()
        for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
            try:
                return datetime.strptime(s, fmt).date().isoformat()
            except ValueError:
                continue
    except (ValueError, KeyError):
        pass
    raise AppError("DATE_INVALID", "Neplatné kalendářní datum.")


def local_time(value):
    if isinstance(value, datetime):
        dt = value
    else:
        s = str(value or "").strip()
        require("T" in s or " " in s, "DATE_INVALID", "Je požadováno datum i čas.")
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            try:
                dt = datetime.strptime(s, "%d.%m.%Y %H:%M:%S")
            except ValueError:
                raise AppError("DATE_INVALID", "Neplatné datum a čas.")
    tz = ZoneInfo("Europe/Prague")
    if dt.tzinfo:
        local = dt.astimezone(tz).replace(tzinfo=None)
        return (
            local.isoformat(),
            "EXACT",
            dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            [],
        )
    candidates = []
    for fold in (0, 1):
        utc = dt.replace(tzinfo=tz, fold=fold).astimezone(timezone.utc)
        if utc.astimezone(tz).replace(tzinfo=None) == dt:
            v = utc.isoformat().replace("+00:00", "Z")
            if v not in candidates:
                candidates.append(v)
    require(candidates, "DATE_INVALID", "Čas neexistuje při přechodu na letní čas.")
    return (
        dt.isoformat(),
        "AMBIGUOUS_LOCAL" if len(candidates) > 1 else "EXACT",
        candidates[0] if len(candidates) == 1 else None,
        candidates,
    )


def enum(value, mapping):
    v = header(value)
    require(v in mapping, "UNKNOWN_ENUM", "Neznámá hodnota typu nebo stavu.")
    return mapping[v]


def search_normalize(s):
    return "".join(
        c
        for c in unicodedata.normalize("NFKD", s.casefold())
        if not unicodedata.combining(c)
    )


def search_tokens(s):
    require(
        s.count('"') % 2 == 0, "FILTER_INVALID", "Neuzavřené uvozovky ve vyhledávání."
    )
    return [search_normalize(a or b) for a, b in re.findall(r'"([^"]*)"|(\S+)', s)]


@dataclass(frozen=True)
class Source:
    kind: str
    identity: str
    content: dict
    local_date: str
    occurred_at_utc: str | None = None
    time_precision: str = "DATE"

    @property
    def amount(self):
        return self.content["signed_amount_minor"]

    @property
    def currency(self):
        return self.content["currency"]

    @property
    def contribution(self):
        return self.amount if self.kind == "CASHBOOK_CARD" else -self.amount

    @property
    def content_hash(self):
        return digest(self.content)

    @property
    def primary(self):
        return (
            self.content.get("invoice_code")
            or self.content.get("seq_id")
            or self.content.get("booking_reference")
        )

    @property
    def description(self):
        return (
            self.content.get("label")
            or self.content.get("guest_name")
            or self.content.get("merchant")
        )
