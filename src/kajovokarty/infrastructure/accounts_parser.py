"""Read only the three identifying columns of BetterHotel's account XLS export."""

from kajovokarty.domain.import_progress import notify
import io
import struct
import xlrd
from kajovokarty.domain.core import AppError, header, identifier, require


def parse_accounts(raw, name, sheet=None, cancel=None, progress=None):
    from kajovokarty.infrastructure.parsers import Parsed

    require(name.lower().endswith(".xls") and raw.startswith(bytes.fromhex("D0CF11E0A1B11AE1")),
            "FORMAT_INVALID", "Účty vyžadují soubor XLS (OLE/BIFF).")
    log = io.StringIO()
    book = None
    try:
        book = xlrd.open_workbook(file_contents=raw, on_demand=True, ragged_rows=True,
                                  ignore_workbook_corruption=True, logfile=log)
        labels = {"variabilní symbol": "variable_symbol", "číslo rezervace": "reservation", "original id": "booking_reference"}
        candidates = []
        for sh in book.sheets():
            if sh.visibility or (sheet and sh.name != sheet):
                continue
            for ri in range(sh.nrows):
                values = sh.row_values(ri)
                if not any(header(v) for v in values):
                    continue
                mapping = {key: [i for i, v in enumerate(values) if header(v) == label] for label, key in labels.items()}
                if all(len(v) == 1 for v in mapping.values()):
                    candidates.append((sh, ri, {k: v[0] for k, v in mapping.items()}))
                break
        require(len(candidates) == 1, "SHEET_AMBIGUOUS" if candidates else "HEADER_INVALID",
                "Vyberte list se sloupci Variabilní symbol, Číslo rezervace a Original ID.",
                {"sheets": [s.name for s, _, _ in candidates]})
        sh, first, mapping = candidates[0]
        result = Parsed(sh.name, mapping)
        result.counters = {"incomplete": 0, "complete": 0}
        notify(progress, "Kontrola", 0, sh.nrows - first - 1)
        for ri in range(first + 1, sh.nrows):
            require(not (cancel and cancel.is_set()), "CANCELLED", "Import byl zrušen.")
            notify(progress, "Kontrola", ri - first - 1, sh.nrows - first - 1)
            cells = {k: sh.cell(ri, col) if col < sh.row_len(ri) else None for k, col in mapping.items()}
            if any(cell is None or not str(cell.value).strip() for cell in cells.values()):
                result.counters["incomplete"] += 1
                result.diagnostics.append(dict(severity="WARNING", code="ACCOUNTS_INCOMPLETE",
                    row_start=ri+1, row_end=ri+1, message="Řádek nemá všechna tři potřebná označení a byl vynechán."))
                continue
            require(all(cell.ctype in (xlrd.XL_CELL_TEXT, xlrd.XL_CELL_NUMBER) for cell in cells.values()),
                    "FORMAT_INVALID", "Identifikátor v Účtech musí být text nebo celé číslo.")
            row = {k: identifier(cell.value) for k, cell in cells.items()}
            row["row"] = ri + 1
            result.accounts.append(row)
            result.counters["complete"] += 1
        if log.getvalue():
            result.diagnostics.append(dict(severity="WARNING", code="XLS_COMPATIBILITY",
                message="XLS byl načten v kompatibilním režimu.", details={"reader": log.getvalue()}))
        notify(progress, "Kontrola", sh.nrows - first - 1, sh.nrows - first - 1)
        return result
    except (xlrd.XLRDError, IndexError, struct.error) as e:
        raise AppError("FORMAT_INVALID", "Účty XLS nelze úplně načíst.") from e
    finally:
        if book is not None:
            book.release_resources()
