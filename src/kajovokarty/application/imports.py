from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import json, tempfile, copy
from kajovokarty.domain.core import (
    AppError,
    bytehash,
    canonical,
    checked,
    digest,
    now,
    require,
    uid,
)
from kajovokarty.infrastructure.parsers import parse, Parsed

PARSER = "KK-IMPORT-1"


@dataclass(frozen=True)
class ImportInput:
    kind: str
    path: str | None = None
    source_file_id: str | None = None
    sheet: str | None = None
    original_run_id: str | None = None
    original_name: str | None = None


@dataclass
class PreparedFile:
    request: ImportInput
    file_id: str
    name: str
    sha256: str
    snapshot: Path
    parsed: Parsed | None


@dataclass
class ImportPreview:
    id: str
    files: list = field(default_factory=list)
    diagnostics: list = field(default_factory=list)
    new: int = 0
    known: int = 0
    totals: dict = field(default_factory=dict)

    @property
    def valid(self):
        return not any(d.get("severity") == "ERROR" for d in self.diagnostics)


class ImportService:
    def __init__(self, db):
        self.db = db
        self.previews = {}

    def preflight(
        self, inputs: list[ImportInput], max_megabytes=100, cancel=None, progress=None
    ):
        require(inputs, "FORMAT_INVALID", "Vyberte vstupní soubory.")
        p = ImportPreview(self.db.start_operation("IMPORT"))
        self.previews[p.id] = p
        with self.db.transaction() as c:
            c.execute(
                "INSERT INTO import_run VALUES(?,?,?,?,?)",
                (p.id, PARSER, "{}", "{}", canonical([i.kind for i in inputs])),
            )
        for request in inputs:
            fid = None
            name = request.original_name or request.path
            try:
                if request.source_file_id:
                    with self.db.connect() as c:
                        row = c.execute(
                            "SELECT * FROM source_file WHERE id=?",
                            (request.source_file_id,),
                        ).fetchone()
                    require(row is not None, "SNAPSHOT_INVALID", "Uložený vstup chybí.")
                    raw = row["bytes"]
                    name = request.original_name or row["original_name"]
                    require(
                        len(raw) == row["byte_size"] and bytehash(raw) == row["sha256"],
                        "SNAPSHOT_INVALID",
                        "Uložená kopie je poškozena.",
                    )
                else:
                    path = Path(request.path)
                    require(
                        not path.is_symlink(),
                        "FORMAT_INVALID",
                        "Symbolický odkaz není podporován.",
                    )
                    require(
                        path.stat().st_size <= max_megabytes * 1024**2,
                        "FILE_TOO_LARGE",
                        "Soubor překračuje nastavený limit.",
                    )
                    with path.open("rb") as f:
                        raw = f.read(max_megabytes * 1024**2 + 1)
                    name = path.name
                require(
                    len(raw) <= max_megabytes * 1024**2,
                    "FILE_TOO_LARGE",
                    "Soubor překračuje nastavený limit.",
                )
                sha = bytehash(raw)
                with self.db.transaction() as c:
                    row = c.execute(
                        "SELECT id FROM source_file WHERE sha256=?", (sha,)
                    ).fetchone()
                    fid = row["id"] if row else uid()
                    if not row:
                        c.execute(
                            "INSERT INTO source_file VALUES(?,?,?,?,?,?)",
                            (fid, sha, name, raw, len(raw), now()),
                        )
                f = tempfile.NamedTemporaryFile(
                    prefix="kajovokarty-", suffix=".snapshot", delete=False
                )
                f.write(raw)
                f.close()
                prepared = PreparedFile(request, fid, name, sha, Path(f.name), None)
                p.files.append(prepared)
                prepared.parsed = parse(
                    raw, name, request.kind, request.sheet, cancel, progress
                )
                for d in prepared.parsed.diagnostics:
                    p.diagnostics.append(
                        {
                            **d,
                            "file_id": fid,
                            "file": name,
                            "sheet": prepared.parsed.sheet,
                            "input_mode": "STORED_SNAPSHOT"
                            if request.source_file_id
                            else "EXTERNAL_FILE",
                        }
                    )
            except (AppError, OSError) as e:
                err = (
                    e
                    if isinstance(e, AppError)
                    else AppError("FILE_CHANGED", "Soubor nelze úplně načíst.")
                )
                p.diagnostics.append(
                    dict(
                        severity="ERROR",
                        file=request.path,
                        file_id=fid,
                        input_mode="STORED_SNAPSHOT"
                        if request.source_file_id
                        else "EXTERNAL_FILE",
                        **err.as_dict(),
                    )
                )
        self._compare(p)
        with self.db.transaction() as c:
            for f in p.files:
                c.execute(
                    "INSERT OR IGNORE INTO import_file VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        p.id,
                        f.file_id,
                        f.parsed.sheet if f.parsed else f.request.sheet or "",
                        "STORED_SNAPSHOT"
                        if f.request.source_file_id
                        else "EXTERNAL_FILE",
                        f.request.original_run_id,
                        f.sha256,
                        f.name,
                        canonical(f.parsed.header_map if f.parsed else {}),
                        canonical(f.parsed.counters if f.parsed else {}),
                    ),
                )
            for d in p.diagnostics:
                c.execute(
                    "INSERT INTO import_diagnostic VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        uid(),
                        p.id,
                        d.get("file_id"),
                        d.get("input_mode", "EXTERNAL_FILE"),
                        d.get("sheet"),
                        d.get("row_start"),
                        d.get("row_end"),
                        d["severity"],
                        d["code"],
                        d.get("column_key"),
                        canonical(d.get("raw_value")),
                        d.get("identity"),
                        None,
                        canonical(d.get("details", {})),
                        d["message"],
                        now(),
                    ),
                )
        return copy.deepcopy(p)

    def _compare(self, p, c=None):
        if c is None:
            with self.db.connect() as connection:
                return self._compare(p, connection)
        known = {
            (r["kind"], r["source_identity"]): r
            for r in c.execute(
                "SELECT kind,source_identity,canonical_json,content_hash FROM financial_source"
            )
        }
        seen = {}
        p.new = p.known = 0
        p.totals = {}
        for f in p.files:
            if not f.parsed:
                continue
            for s in f.parsed.sources:
                key = (s.kind, s.identity)
                value = canonical(s.content)
                old = seen.get(key) or (
                    known[key]["canonical_json"] if key in known else None
                )
                if old is not None:
                    if old != value:
                        p.diagnostics.append(
                            dict(
                                severity="ERROR",
                                code="SOURCE_CONFLICT",
                                message="Stejná identita obsahuje odlišná data.",
                                identity=s.identity,
                                file_id=f.file_id,
                                details={"old": json.loads(old), "new": s.content},
                            )
                        )
                    else:
                        p.known += 1
                else:
                    p.new += 1
                    p.totals[s.currency] = checked(
                        p.totals.get(s.currency, 0) + s.amount
                    )
                seen[key] = value

    def commit(self, preview_id, expected_snapshot_hashes=None, cancel=None):
        require(preview_id in self.previews, "STALE_STATE", "Náhled již není dostupný.")
        p = self.previews[preview_id]
        require(
            p.valid,
            "IMPORT_INVALID",
            "Import obsahuje chyby; finanční zápis není dovolen.",
        )
        try:
            for f in p.files:
                code = (
                    "SNAPSHOT_INVALID" if f.request.source_file_id else "FILE_CHANGED"
                )
                try:
                    require(
                        bytehash(f.snapshot.read_bytes()) == f.sha256,
                        code,
                        "Dočasný snapshot byl změněn.",
                    )
                    if expected_snapshot_hashes is not None:
                        require(
                            expected_snapshot_hashes.get(f.file_id) == f.sha256,
                            code,
                            "Náhled neodpovídá potvrzeným hashům.",
                        )
                    if not f.request.source_file_id:
                        require(
                            bytehash(Path(f.request.path).read_bytes()) == f.sha256,
                            code,
                            "Originál se po náhledu změnil.",
                        )
                except OSError:
                    raise AppError(code, "Autoritativní vstup již není dostupný.")
            with self.db.transaction() as c:
                for f in p.files:
                    row = c.execute(
                        "SELECT bytes,sha256,byte_size FROM source_file WHERE id=?",
                        (f.file_id,),
                    ).fetchone()
                    require(
                        row
                        and len(row["bytes"]) == row["byte_size"]
                        and bytehash(row["bytes"]) == f.sha256,
                        "SNAPSHOT_INVALID",
                        "Uložený snapshot není platný.",
                    )
                self._compare(p, c)
                require(
                    p.valid,
                    "SOURCE_CONFLICT",
                    "Konflikt identity proti aktuální databázi.",
                )
                inserted = 0
                lookup = {}
                for f in p.files:
                    for s in f.parsed.sources:
                        require(
                            not (cancel and cancel.is_set()),
                            "CANCELLED",
                            "Import byl zrušen před dokončením transakce.",
                        )
                        row = c.execute(
                            "SELECT id FROM financial_source WHERE kind=? AND source_identity=?",
                            (s.kind, s.identity),
                        ).fetchone()
                        sid = row["id"] if row else uid()
                        lookup[(s.kind, s.identity)] = sid
                        if row:
                            continue
                        payload = canonical(s.content)
                        c.execute(
                            "INSERT INTO financial_source VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (
                                sid,
                                s.kind,
                                s.identity,
                                payload,
                                s.content_hash,
                                s.local_date,
                                s.occurred_at_utc,
                                s.time_precision,
                                s.amount,
                                s.currency,
                                s.primary,
                                s.description,
                                now(),
                            ),
                        )
                        if s.kind == "CASHBOOK_CARD":
                            c.execute(
                                "INSERT INTO cashbook_detail VALUES(?,?,?,?,?)",
                                (
                                    sid,
                                    s.content["cashbook_number"],
                                    s.content["invoice_code"],
                                    int(s.content["storno_marker"]),
                                    payload,
                                ),
                            )
                        elif s.kind == "BANK_CARD":
                            c.execute(
                                "INSERT INTO bank_detail VALUES(?,?,?,?,?)",
                                (
                                    sid,
                                    s.content["terminal_id"],
                                    s.content["seq_id"],
                                    s.content["event_class"],
                                    payload,
                                ),
                            )
                        else:
                            c.execute(
                                "INSERT INTO booking_detail VALUES(?,?,?,?,?)",
                                (
                                    sid,
                                    digest(
                                        [
                                            s.content[k]
                                            for k in (
                                                "payout_id",
                                                "payout_date",
                                                "currency",
                                            )
                                        ]
                                    ),
                                    s.content["payout_id"],
                                    s.content["booking_reference"],
                                    payload,
                                ),
                            )
                        c.execute(
                            "INSERT INTO work_object VALUES(?,'SOURCE',?,?,'ACTIVE',1)",
                            (sid, sid, s.currency),
                        )
                        inserted += 1
                    for occurrence in f.parsed.occurrences:
                        o = occurrence
                        sid = lookup.get((f.request.kind, o["source_identity"]))
                        c.execute(
                            "INSERT OR IGNORE INTO source_occurrence VALUES(?,?,?,?,?,?,?,?,?,?)",
                            (
                                p.id,
                                f.file_id,
                                f.parsed.sheet,
                                o["row_start"],
                                o["row_end"],
                                sid,
                                o["disposition"],
                                o["repair_code"],
                                canonical(o["raw_cells"]),
                                canonical(o["raw_types"]),
                            ),
                        )
                if inserted:
                    self.db.invalidate_redo(c)
                c.execute(
                    "UPDATE import_run SET totals_json=?,row_counts_json=? WHERE id=?",
                    (
                        canonical(p.totals),
                        canonical({"new": inserted, "known": p.known}),
                        p.id,
                    ),
                )
                self.db.audit(
                    c,
                    "IMPORT_COMMITTED",
                    after={"new": inserted, "known": p.known, "totals": p.totals},
                    method="IMPORT",
                    operation=p.id,
                )
            self.db.finish_operation(p.id)
            return {"new": inserted, "known": p.known, "totals": p.totals}
        except AppError as e:
            self.db.finish_operation(p.id, e)
            raise
        finally:
            self.discard(preview_id)

    def discard(self, preview_id):
        p = self.previews.pop(preview_id, None)
        if p:
            with self.db.transaction() as c:
                c.execute(
                    "UPDATE operation SET state='CANCELLED',finished_at=? WHERE id=? AND state='RUNNING'",
                    (now(), preview_id),
                )
            for f in p.files:
                f.snapshot.unlink(missing_ok=True)
