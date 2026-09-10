"""Strict file adapters; original bytes and every physical row are retained."""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import PurePosixPath
import csv, io, re, struct, zipfile
import xlrd
import openpyxl
from decimal import InvalidOperation
from kajovokarty.domain.core import (
    AppError,
    Source,
    checked,
    currency,
    digest,
    enum,
    header,
    identifier,
    local_time,
    money,
    parse_date,
    require,
    text,
)

CASH_HEADERS = "Vystaveno|Pohyb|Číslo|Označení|Klient|Příjem|Výdaj|Měna|Forma úhrady|Variabilní symbol|Vystavil".split(
    "|"
)
CASH_FIELDS = "issued_local movement cashbook_number label client income_minor expense_minor currency payment_form variable_symbol issued_by".split()
BANK_HEADERS = "Typ transakce|ID Terminálu|ID POS|Datum a čas vzniku|Čas připsání na server|Datum zaúčtování|Částka|Cashback|Spropitné|Měna|ARN kód|DCC|Číslo karty/Číslo účtu|Autoriz. kód|Var. symbol|Var. symbol 2|SEQ ID|Vydavatel karty|Způsob načtení karty|Obchodní místo|Adresa obchodního místa".split(
    "|"
)
BANK_FIELDS = "event_class terminal_id pos_id occurred_local server_local booked_date signed_amount_minor cashback_minor tip_minor currency arn dcc masked_account authorization_code variable_symbol variable_symbol_2 seq_id issuer entry_method merchant merchant_address".split()
BOOK_HEADERS = "Type|Booking number|Check-in|Checkout|Guest name|Payments service provider|Reservation status|Currency|Payment status|Amount|Payout date|Payout ID".split(
    "|"
)
BOOK_CZ = "Typ faktury|Číslo rezervace|Datum příjezdu|Checkout|Jméno hosta|Poskytovatel platebních služeb|Status rezervace|Měna|Status platby|Částka|Datum vyplacení částky|ID platby".split(
    "|"
)
BOOK_FIELDS = "invoice_type booking_reference arrival departure guest_name provider reservation_status currency payment_status signed_amount_minor payout_date payout_id".split()
SCHEMAS = {
    "CASHBOOK_CARD": (CASH_HEADERS, CASH_FIELDS),
    "BANK_CARD": (BANK_HEADERS, BANK_FIELDS),
    "BOOKING": (BOOK_HEADERS, BOOK_FIELDS),
}


@dataclass
class Parsed:
    sheet: str
    header_map: list
    occurrences: list = field(default_factory=list)
    sources: list = field(default_factory=list)
    diagnostics: list = field(default_factory=list)
    counters: dict = field(default_factory=dict)


def safe_raw(v):
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, float) and (v != v or abs(v) == float("inf")):
        return str(v)
    return v


def map_header(cells, kind):
    cells = list(cells)
    while cells and not header(cells[-1]):
        cells.pop()
    names, fields = SCHEMAS[kind]
    aliases = {header(n): f for n, f in zip(names, fields)}
    if kind == "BOOKING":
        aliases.update({header(n): f for n, f in zip(BOOK_CZ, fields)})
    if kind == "BANK_CARD":
        aliases.update(
            {
                header(n): f
                for n, f in zip(
                    [
                        "Číslo karty / Číslo účtu",
                        "Autorizační kód",
                        "Variabilní symbol",
                        "Variabilní symbol 2",
                    ],
                    [
                        "masked_account",
                        "authorization_code",
                        "variable_symbol",
                        "variable_symbol_2",
                    ],
                )
            }
        )
    mapped = [aliases.get(header(v)) for v in cells]
    require(
        len(mapped) == len(fields)
        and None not in mapped
        and set(mapped) == set(fields),
        "HEADER_INVALID",
        "Hlavička neodpovídá úplnému schématu.",
    )
    return mapped


def validate_zip(raw):
    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
        infos = z.infolist()
        require(
            len(infos) <= 100000 and sum(i.file_size for i in infos) <= 1024**3,
            "FILE_TOO_LARGE",
            "Překročeny limity rozbaleného XLSX.",
        )
        for i in infos:
            p = PurePosixPath(i.filename)
            require(
                not p.is_absolute()
                and ".." not in p.parts
                and "\\" not in i.filename
                and not (i.external_attr >> 16 & 0o170000) == 0o120000,
                "FORMAT_INVALID",
                "Nebezpečná cesta v XLSX.",
            )
            require(
                i.file_size <= 1000 * max(1, i.compress_size),
                "FILE_TOO_LARGE",
                "Příliš vysoký kompresní poměr.",
            )
            require(
                not i.filename.lower().endswith((".zip", ".xlsm", "vbaproject.bin"))
                and "externallinks/" not in i.filename.lower(),
                "FORMAT_INVALID",
                "Makra, externí odkazy a vnořené archivy nejsou povoleny.",
            )
        require(
            "xl/workbook.xml" in z.namelist(), "FORMAT_INVALID", "Chybí OOXML workbook."
        )
        return z
    except zipfile.BadZipFile:
        raise AppError("FORMAT_INVALID", "Poškozený XLSX.")


def biff_safe(book, kind):
    # Scan BIFF records in the workbook stream, never binary-search arbitrary bytes.
    buf = book.mem
    start = book.base
    end = start + book.stream_len
    pos = start
    while pos + 4 <= end:
        code, length = struct.unpack_from("<HH", buf, pos)
        pos += 4
        require(pos + length <= end, "FORMAT_INVALID", "Zkrácený BIFF záznam.")
        require(code != 0x002F, "FORMAT_INVALID", "Šifrovaný XLS není povolen.")
        if code in (0x0006, 0x0206, 0x0406):
            row, col = struct.unpack_from("<HH", buf, pos)
            valid = False
            if kind == "CASHBOOK_CARD":
                for sh in book.sheets():
                    if row == sh.nrows - 1 and col in (5, 6):
                        valid = all(
                            not text(sh.cell_value(row, c))
                            for c in range(sh.row_len(row))
                            if c not in (5, 6)
                        )
            require(
                valid, "FORMAT_INVALID", "Vzorce v datových řádcích nejsou povoleny."
            )
        if code == 0x0085 and length >= 6:
            require(buf[pos + 5] != 1, "FORMAT_INVALID", "Makrolist není povolen.")
        if code == 0x01AE and length >= 4:
            marker = struct.unpack_from("<H", buf, pos + 2)[0]
            require(
                marker in (0x0401, 0x3A01),
                "FORMAT_INVALID",
                "Externí odkazy nejsou povoleny.",
            )
        pos += length


def sheets(raw, name, kind):
    ext = name.rsplit(".", 1)[-1].lower()
    if ext == "csv":
        require(
            kind != "CASHBOOK_CARD"
            and not raw.startswith((b"PK", bytes.fromhex("D0CF11E0"))),
            "FORMAT_INVALID",
            "Nesprávný formát vstupu.",
        )
        encs = (
            ["utf-8-sig"]
            if kind == "BOOKING"
            else (
                ["utf-16"]
                if raw.startswith((b"\xff\xfe", b"\xfe\xff"))
                else ["utf-8-sig", "cp1250"]
            )
        )
        decoded = None
        for enc in encs:
            try:
                decoded = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        require(
            decoded is not None and "\x00" not in decoded,
            "FORMAT_INVALID",
            "Neplatné kódování CSV.",
        )
        candidates = []
        for delim in (",", ";"):
            try:
                reader = csv.reader(
                    io.StringIO(decoded, newline=""), delimiter=delim, strict=True
                )
                rows = []
                previous = 0
                for row in reader:
                    rows.append((previous + 1, reader.line_num, row))
                    previous = reader.line_num
                first = next((r for r in rows if any(header(v) for v in r[2])), None)
                if first:
                    map_header(first[2], kind)
                    candidates.append(("CSV", rows))
            except (AppError, csv.Error):
                continue
        require(
            len(candidates) == 1,
            "HEADER_INVALID",
            "CSV nemá jednoznačnou podporovanou hlavičku a oddělovač.",
        )
        return candidates
    if ext == "xls":
        require(
            raw.startswith(bytes.fromhex("D0CF11E0A1B11AE1")),
            "FORMAT_INVALID",
            "XLS musí být OLE/BIFF8, ne HTML.",
        )
        log = io.StringIO()
        try:
            book = xlrd.open_workbook(
                file_contents=raw,
                on_demand=True,
                ragged_rows=True,
                ignore_workbook_corruption=True,
                logfile=log,
            )
            biff_safe(book, kind)
            result = []
            for sh in book.sheets():
                if sh.visibility:
                    continue
                rows = []
                for ri in range(sh.nrows):
                    cells = []
                    for c in sh.row(ri):
                        require(
                            c.ctype != xlrd.XL_CELL_ERROR,
                            "FORMAT_INVALID",
                            "Chybová Excel buňka.",
                        )
                        v = c.value
                        if c.ctype == xlrd.XL_CELL_DATE:
                            require(
                                not (book.datemode == 0 and 60 <= v < 61),
                                "DATE_INVALID",
                                "Excel den 60 roku 1900 neexistuje.",
                            )
                            v = xlrd.xldate_as_datetime(v, book.datemode)
                        cells.append(v)
                    rows.append((ri + 1, ri + 1, cells))
                result.append((sh.name, rows))
            book.release_resources()
            return result
        except (xlrd.XLRDError, IndexError, struct.error) as e:
            raise AppError("FORMAT_INVALID", "XLS nelze úplně načíst.") from e
    require(
        ext == "xlsx" and kind == "BANK_CARD",
        "FORMAT_INVALID",
        "Nepodporovaný typ souboru.",
    )
    validate_zip(raw).close()
    try:
        book = openpyxl.load_workbook(
            io.BytesIO(raw), read_only=True, data_only=False, keep_links=True
        )
        result = []
        for sh in book:
            if sh.sheet_state != "visible":
                continue
            rows = []
            for ri, row in enumerate(sh.iter_rows(), 1):
                require(
                    not any(c.data_type in ("f", "e") for c in row),
                    "FORMAT_INVALID",
                    "Vzorce a chybové buňky nejsou povoleny.",
                )
                rows.append((ri, ri, [c.value for c in row]))
            result.append((sh.title, rows))
        book.close()
        return result
    except (ValueError, KeyError, TypeError) as e:
        raise AppError("FORMAT_INVALID", "Poškozený OOXML workbook.") from e


def cash(d):
    d = {k: text(v) for k, v in d.items()}
    d["payment_form"] = enum(
        d["payment_form"], {"kartou": "CARD", "hotově": "CASH", "převodem": "TRANSFER"}
    )
    for k in ("income_minor", "expense_minor"):
        d[k] = money(d[k], True)
    require(
        d["income_minor"] >= 0 and d["expense_minor"] >= 0,
        "MONEY_INVALID",
        "Příjem a výdaj nesmí být záporné.",
    )
    if d["payment_form"] != "CARD":
        return None, d["payment_form"], d
    require(
        not (d["income_minor"] and d["expense_minor"]),
        "MONEY_INVALID",
        "Příjem a výdaj nelze vyplnit současně.",
    )
    d["movement"] = enum(d["movement"], {"příjem": "INCOME", "výdaj": "EXPENSE"})
    local, precision, utc, candidates = local_time(d["issued_local"])
    d["issued_local"] = local
    d["time_precision"] = precision
    d["currency"] = currency(d["currency"])
    d["signed_amount_minor"] = checked(d["income_minor"] - d["expense_minor"])
    require(
        not d["signed_amount_minor"]
        or (d["signed_amount_minor"] > 0) == (d["movement"] == "INCOME"),
        "MONEY_INVALID",
        "Směr pohybu nesouhlasí se znaménkem.",
    )
    for k in ("variable_symbol", "cashbook_number"):
        d[k] = identifier(d[k])
    codes = set(re.findall(r"(?i)(?<![A-Z0-9])FA[0-9]+(?![A-Z0-9])", d["label"] or ""))
    codes = {c.upper() for c in codes}
    require(
        len(codes) == 1 and d["variable_symbol"],
        "CASHBOOK_REFERENCE_INVALID",
        "Karetní řádek musí mít právě jeden FA kód a variabilní symbol.",
    )
    d["invoice_code"] = next(iter(codes))
    d["storno_marker"] = (d["label"] or "").upper().startswith("[STORNO]")
    ident = digest(
        [
            d[k]
            for k in (
                "issued_local",
                "movement",
                "invoice_code",
                "variable_symbol",
                "storno_marker",
            )
        ]
    )
    return (
        Source("CASHBOOK_CARD", ident, d, local[:10], utc, precision)
        if d["signed_amount_minor"]
        else None,
        "NEW" if d["signed_amount_minor"] else "ZERO_AMOUNT",
        d,
    )


def bank(d):
    event = enum(
        d["event_class"],
        {
            "prodej": "SALE",
            "storno": "REVERSAL",
            "návrat zboží": "REFUND",
            "navrat zbozi": "REFUND",
            "refundace": "REFUND",
            "refund": "REFUND",
            "vrácení": "REFUND",
            "vraceni": "REFUND",
            "uzávěrka": "TECHNICAL",
            "uzaverka": "TECHNICAL",
        },
    )
    if event == "TECHNICAL":
        return None, "TECHNICAL", d
    d = {
        k: identifier(v)
        if k
        in (
            "terminal_id",
            "pos_id",
            "seq_id",
            "authorization_code",
            "variable_symbol",
            "variable_symbol_2",
            "arn",
        )
        else text(v)
        for k, v in d.items()
    }
    d["event_class"] = event
    require(
        d["terminal_id"] and d["seq_id"],
        "IDENTITY_MISSING",
        "Chybí terminál nebo SEQ ID.",
    )
    local, precision, utc, _ = local_time(d["occurred_local"])
    d["occurred_local"] = local
    d["occurred_time_precision"] = precision
    if d["server_local"]:
        d["server_local"], d["server_time_precision"], _, _ = local_time(
            d["server_local"]
        )
    else:
        d["server_time_precision"] = None
    d["booked_date"] = parse_date(d["booked_date"]) if d["booked_date"] else None
    for k in ("signed_amount_minor", "cashback_minor", "tip_minor"):
        d[k] = money(d[k], k != "signed_amount_minor")
    if event == "SALE":
        require(
            d["signed_amount_minor"] >= 0,
            "MONEY_INVALID",
            "Prodej nesmí mít zápornou částku.",
        )
    else:
        d["signed_amount_minor"] = -abs(d["signed_amount_minor"])
    d["currency"] = currency(d["currency"])
    ident = digest([d[k] for k in ("terminal_id", "seq_id", "event_class")])
    return (
        Source("BANK_CARD", ident, d, local[:10], utc, precision)
        if d["signed_amount_minor"]
        else None,
        "NEW" if d["signed_amount_minor"] else "ZERO_AMOUNT",
        d,
    )


def booking(d):
    d = {k: text(v) for k, v in d.items()}
    d["invoice_type"] = enum(
        d["invoice_type"], {"reservation": "RESERVATION", "rezervace": "RESERVATION"}
    )
    d["reservation_status"] = enum(
        d["reservation_status"],
        {
            **dict.fromkeys(["ok", "valid", "platná", "platna"], "OK"),
            **dict.fromkeys(["cancelled", "canceled", "zrušeno"], "CANCELLED"),
            **dict.fromkeys(["no-show", "noshow", "nedojezd"], "NO_SHOW"),
        },
    )
    d["payment_status"] = enum(
        d["payment_status"],
        {
            **dict.fromkeys(["paid online", "paid", "uhrazeno online"], "PAID"),
            **dict.fromkeys(
                ["pending", "unpaid", "čeká na platbu", "neuhrazeno"], "UNPAID"
            ),
        },
    )
    d["booking_reference"] = identifier(d["booking_reference"])
    d["payout_id"] = identifier(d["payout_id"])
    require(
        bool(re.fullmatch("[0-9]{6,20}", d["booking_reference"] or ""))
        and d["payout_id"],
        "IDENTITY_MISSING",
        "Chybí platná Booking reference nebo Payout ID.",
    )
    for k in ("arrival", "departure", "payout_date"):
        d[k] = parse_date(d[k]) if d[k] else None
    require(d["payout_date"], "DATE_INVALID", "Chybí datum výplaty.")
    require(
        not (d["arrival"] and d["departure"]) or d["departure"] >= d["arrival"],
        "DATE_INVALID",
        "Odjezd předchází příjezdu.",
    )
    d["currency"] = currency(d["currency"])
    d["signed_amount_minor"] = money(d["signed_amount_minor"])
    ident = digest(
        [
            d[k]
            for k in (
                "payout_id",
                "booking_reference",
                "currency",
                "payout_date",
                "invoice_type",
            )
        ]
    )
    disposition = (
        "UNPAID"
        if d["payment_status"] == "UNPAID"
        else ("NEW" if d["signed_amount_minor"] else "ZERO_AMOUNT")
    )
    return (
        Source("BOOKING", ident, d, d["payout_date"]) if disposition == "NEW" else None,
        disposition,
        d,
    )


def parse(raw, name, kind, sheet=None, cancel=None, progress=None):
    require(kind in SCHEMAS, "FORMAT_INVALID", "Neznámý zdroj.")
    candidates = []
    all_sheets = sheets(raw, name, kind)
    for title, rows in all_sheets:
        if sheet and title != sheet:
            continue
        first = next((r for r in rows if any(header(v) for v in r[2])), None)
        if not first:
            continue
        try:
            mapping = map_header(first[2], kind)
            candidates.append((title, rows, first, mapping))
        except AppError:
            if kind == "CASHBOOK_CARD" and title == "Worksheet":
                raise
    if kind == "CASHBOOK_CARD" and any(c[0] == "Worksheet" for c in candidates):
        candidates = [c for c in candidates if c[0] == "Worksheet"]
    require(
        len(candidates) == 1,
        "SHEET_AMBIGUOUS" if candidates else "HEADER_INVALID",
        "Vyberte právě jeden list s úplným schématem.",
        {"sheets": [c[0] for c in candidates]},
    )
    title, rows, first, mapping = candidates[0]
    result = Parsed(title, mapping)
    footer = False
    income = expense = raw_sum = count = 0
    footer_values = None
    for start, end, original in rows:
        require(not (cancel and cancel.is_set()), "CANCELLED", "Import byl zrušen.")
        if progress and start % 100 == 0:
            progress(f"{name}: řádek {start} / {len(rows)}")
        if start <= first[0]:
            continue
        cells = list(original)
        repair = None
        source = None
        disposition = "ERROR"
        detail = None
        try:
            while cells and (cells[-1] is None or str(cells[-1]).strip() == ""):
                cells.pop()
            if not cells:
                disposition = "BLANK"
            else:
                if kind == "CASHBOOK_CARD" and len(cells) == 12:
                    require(
                        mapping == CASH_FIELDS
                        and str(cells[4]).strip() == "H&amp"
                        and str(cells[5]).strip() == "H security s.r.o."
                        and str(cells[8]).strip() in ("CZK", "EUR")
                        and str(cells[9]).strip() in ("Kartou", "Hotově", "Převodem")
                        and isinstance(cells[11], str),
                        "ROW_SHAPE_INVALID",
                        "Nepovolený přesah řádku.",
                    )
                    money(cells[6], True)
                    money(cells[7], True)
                    identifier(cells[10])
                    cells = cells[:4] + [cells[4] + ";" + cells[5]] + cells[6:]
                    repair = "SPLIT_CLIENT_ENTITY"
                require(
                    len(cells) <= len(mapping),
                    "ROW_SHAPE_INVALID",
                    "Hodnota za posledním sloupcem.",
                )
                cells += [None] * (len(mapping) - len(cells))
                d = dict(zip(mapping, cells))
                if kind == "CASHBOOK_CARD" and all(
                    not text(v)
                    for k, v in d.items()
                    if k not in ("income_minor", "expense_minor")
                ):
                    require(not footer, "ROW_SHAPE_INVALID", "Více souhrnných řádků.")
                    footer = True
                    footer_values = (d["income_minor"], d["expense_minor"])
                    disposition = "SUMMARY"
                elif kind == "BANK_CARD" and header(cells[0]) in (
                    "počet transakcí:",
                    "pocet transakci:",
                    "suma částek:",
                    "suma castek:",
                ):
                    values = [v for v in cells[1:] if text(v)]
                    require(
                        len(values) == 1,
                        "SUMMARY_MISMATCH",
                        "Nejednoznačný terminálový souhrn.",
                    )
                    target = (
                        count
                        if header(cells[0]).startswith(("počet", "pocet"))
                        else raw_sum
                    )
                    actual = (
                        int(identifier(values[0]))
                        if header(cells[0]).startswith(("počet", "pocet"))
                        else money(values[0])
                    )
                    require(
                        actual == target,
                        "SUMMARY_MISMATCH",
                        "Souhrn terminálu nesouhlasí s řádky.",
                    )
                    disposition = "SUMMARY"
                else:
                    require(
                        not footer, "ROW_SHAPE_INVALID", "Pohyb za souhrnným řádkem."
                    )
                    # Preserve numeric identifiers before generic text normalization.
                    ids = (
                        ("variable_symbol", "cashbook_number")
                        if kind == "CASHBOOK_CARD"
                        else ()
                    )
                    for k in ids:
                        d[k] = identifier(d[k])
                    source, disposition, detail = {
                        "CASHBOOK_CARD": cash,
                        "BANK_CARD": bank,
                        "BOOKING": booking,
                    }[kind](d)
                    if kind == "CASHBOOK_CARD":
                        income += detail["income_minor"]
                        expense += detail["expense_minor"]
                    if kind == "BANK_CARD":
                        count += 1
                        raw_sum += money(
                            d["signed_amount_minor"], disposition == "TECHNICAL"
                        )
            if source:
                result.sources.append(source)
        except AppError as e:
            result.diagnostics.append(
                dict(
                    severity="ERROR",
                    row_start=start,
                    row_end=end,
                    raw_value=original,
                    column_key=e.details.get("field")
                    if isinstance(e.details, dict)
                    else None,
                    **e.as_dict(),
                )
            )
        if repair:
            result.diagnostics.append(
                dict(
                    severity="INFO",
                    row_start=start,
                    row_end=end,
                    code=repair,
                    message="Opraveno rozdělení HTML entity klienta.",
                )
            )
        result.occurrences.append(
            dict(
                row_start=start,
                row_end=end,
                raw_cells=[safe_raw(v) for v in original],
                raw_types=[type(v).__name__ for v in original],
                repair_code=repair,
                disposition=disposition,
                source_identity=source.identity if source else None,
            )
        )
        result.counters[disposition] = result.counters.get(disposition, 0) + 1
    if footer_values:
        try:
            amounts = [
                int(
                    (
                        Decimal(str(v or 0)).quantize(
                            Decimal(".01"), rounding=ROUND_HALF_UP
                        )
                    )
                    * 100
                )
                for v in footer_values
            ]
            if amounts != [income, expense]:
                result.diagnostics.append(
                    dict(
                        severity="WARNING",
                        code="CASHBOOK_FOOTER_MISMATCH",
                        message="Exportní footer nesouhlasí; autoritou jsou jednotlivé pohyby.",
                    )
                )
        except InvalidOperation:
            result.diagnostics.append(
                dict(severity="ERROR", code="MONEY_INVALID", message="Neplatný footer.")
            )
    return result
