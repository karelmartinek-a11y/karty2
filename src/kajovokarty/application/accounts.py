"""Append-only reservation references from the manual Účty import."""

from kajovokarty.domain.core import now, require


def classify(c, files):
    reservations = dict(c.execute("SELECT reservation,booking_reference FROM account_reservation"))
    symbols = set(tuple(r) for r in c.execute("SELECT variable_symbol,reservation FROM account_symbol"))
    accepted = []
    counts = dict(new=0, known=0, conflicts=0, incomplete=0)
    for f in files:
        if not f.parsed or f.request.kind != "ACCOUNTS":
            continue
        local = dict(new=0, known=0, conflicts=0, incomplete=f.parsed.counters.get("incomplete", 0))
        for row in f.parsed.accounts:
            vs, reservation, booking = (row[k] for k in ("variable_symbol", "reservation", "booking_reference"))
            if reservation in reservations and reservations[reservation] != booking:
                local["conflicts"] += 1
            elif (vs, reservation) in symbols:
                local["known"] += 1
            else:
                reservations[reservation] = booking
                symbols.add((vs, reservation))
                accepted.append((f, row))
                local["new"] += 1
        f.parsed.counters.update(local)
        for key in counts:
            counts[key] += local[key]
    return accepted, counts


def commit(c, files, run_id, cancel=None):
    accepted, counts = classify(c, files)
    for f, row in accepted:
        require(not (cancel and cancel.is_set()), "CANCELLED", "Import byl zrušen.")
        c.execute(
            "INSERT OR IGNORE INTO account_reservation VALUES(?,?,?)",
            (row["reservation"], row["booking_reference"], now()),
        )
        c.execute(
            "INSERT INTO account_symbol VALUES(?,?,?,?,?,?)",
            (row["variable_symbol"], row["reservation"], f.file_id, run_id, f.parsed.sheet, row["row"]),
        )
    if accepted:
        c.execute("UPDATE domain_clock SET revision=revision+1 WHERE id=1")
    return counts


def rows(db):
    with db.connect() as c:
        return [dict(r) for r in c.execute('''
            SELECT s.variable_symbol AS "Variabilní symbol", s.reservation AS "Číslo rezervace",
                   r.booking_reference AS "Original ID", f.original_name AS "Soubor",
                   s.sheet AS "List", s.row_number AS "Řádek"
            FROM account_symbol s JOIN account_reservation r USING(reservation)
            JOIN source_file f ON f.id=s.file_id ORDER BY s.variable_symbol,s.reservation
        ''')]
