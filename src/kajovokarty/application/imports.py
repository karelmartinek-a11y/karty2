from __future__ import annotations
from kajovokarty.domain.import_progress import notify
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

PARSER = "KK-IMPORT-2"


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
    existing_known: int = 0
    totals: dict = field(default_factory=dict)
    accounts: dict = field(default_factory=dict)

    @property
    def valid(self):
        return not any(d.get("severity") == "ERROR" for d in self.diagnostics)


class ImportService:
    def __init__(self, db):
        self.db = db
        self.previews = {}

    def preflight(
        self, inputs: list[ImportInput], max_megabytes=100, cancel=None, progress=None, choose_sheet=None
    ):
        before = set(self.previews)
        try:
            return self._preflight(inputs, max_megabytes, cancel, progress, choose_sheet)
        except Exception as cause:
            error = cause if isinstance(cause, AppError) else AppError("INTERNAL_ERROR", "Náhled importu se nepodařilo připravit.")
            for operation in set(self.previews) - before:
                error.operation_id = operation
                self.db.log.exception("IMPORT_PREVIEW_FAILED", cause, operation_id=operation)
                try:
                    self.db.finish_operation(operation, error)
                finally:
                    self.discard(operation)
            raise error from cause

    def _preflight(self, inputs, max_megabytes, cancel, progress, choose_sheet):
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
                self.db.log.event("IMPORT_FILE_BEGIN", operation_id=p.id, file_id=fid, kind=request.kind)
                try:
                    prepared.parsed = parse(raw, name, request.kind, request.sheet, cancel, progress)
                except AppError as error:
                    if error.code != "SHEET_AMBIGUOUS" or choose_sheet is None:
                        raise
                    selected = choose_sheet(name, error.details["sheets"])
                    require(selected is not None, "CANCELLED", "Výběr listu byl zrušen.")
                    prepared.parsed = parse(raw, name, request.kind, selected, cancel, progress)

                for occurrence in prepared.parsed.occurrences:
                    self.db.log.event("IMPORT_ROW_PARSED", operation_id=p.id, file_id=fid,
                                      row_start=occurrence["row_start"], disposition=occurrence["disposition"])
                self.db.log.event("IMPORT_FILE_PARSED", operation_id=p.id, file_id=fid, counts=prepared.parsed.counters)
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
                self.db.log.exception("IMPORT_FILE_FAILED", e, operation_id=p.id, file_id=fid)
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
                self.db.log.event("IMPORT_DIAGNOSTIC", operation_id=p.id, file_id=d.get("file_id"),
                                  row_start=d.get("row_start"), error_code=d["code"], state=d["severity"])
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
        self.db.log.event("IMPORT_PREVIEW", operation_id=p.id, state="READY" if p.valid else "INVALID", counts={"new": p.new, "known": p.known, "errors": sum(d["severity"] == "ERROR" for d in p.diagnostics)})
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
        p.new = p.known = p.existing_known = 0
        p.totals = {}
        for f in p.files:
            if not f.parsed:
                continue
            for s in f.parsed.sources:
                key = (s.kind, s.identity)
                value = canonical(s.content)
                if key in known:
                    saved = json.loads(known[key]["canonical_json"])
                    identity_fields = ("booking_reference", "payout_id", "payout_date", "currency",
                                       "signed_amount_minor", "invoice_type", "payment_status")
                    saved_matches = (all(saved.get(k) == s.content.get(k) for k in identity_fields)
                                     if s.kind == "BOOKING" else known[key]["canonical_json"] == value)
                    p.existing_known += int(saved_matches)
                old = seen.get(key) or (
                    known[key]["canonical_json"] if key in known else None
                )
                if old is not None:
                    # Booking names/stay details can differ between exports.
                    # Only payment facts determine whether an existing payment conflicts.
                    old_content = json.loads(old)
                    payment_fields = ("booking_reference", "payout_id", "payout_date",
                                      "currency", "signed_amount_minor", "invoice_type", "payment_status")
                    differs = (any(old_content.get(k) != s.content.get(k) for k in payment_fields)
                               if s.kind == "BOOKING" else old != value)
                    if differs:
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
        from kajovokarty.application.accounts import classify
        _, p.accounts = classify(c, p.files)
        p.diagnostics[:] = [d for d in p.diagnostics if d["code"] != "ACCOUNTS_CONFLICT"]
        for f in p.files:
            if not f.parsed:
                continue
            for d in f.parsed.diagnostics:
                if d["code"] == "ACCOUNTS_CONFLICT":
                    p.diagnostics.append({**d, "file_id": f.file_id, "file": f.name,
                                          "sheet": f.parsed.sheet})
        if any(f.request.kind == "ACCOUNTS" for f in p.files):
            saved_links = set(tuple(r) for r in c.execute(
                "SELECT s.variable_symbol,s.reservation,r.booking_reference FROM account_symbol s JOIN account_reservation r USING(reservation)"
            ))
            p.existing_known += sum(
                (row["variable_symbol"], row["reservation"], row["booking_reference"]) in saved_links
                for f in p.files if f.parsed and f.request.kind == "ACCOUNTS"
                for row in f.parsed.accounts
            )
        p.new += p.accounts["new"]
        p.known += p.accounts["known"]

    def commit(self, preview_id, expected_snapshot_hashes=None, cancel=None, progress=None):
        require(preview_id in self.previews, "STALE_STATE", "Náhled již není dostupný.")
        p = self.previews[preview_id]
        require(
            p.valid,
            "IMPORT_INVALID",
            "Import obsahuje chyby; finanční zápis není dovolen.",
        )
        committed_result = None
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
                new_ids, recorded_ids = set(), set()
                source_total = sum(len(f.parsed.sources) for f in p.files)
                source_done = 0
                notify(progress, "Ukládání plateb", 0, source_total)
                for f in p.files:
                    for s in f.parsed.sources:
                        notify(progress, "Ukládání plateb", source_done, source_total)
                        source_done += 1
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
                        self.db.log.event("IMPORT_SOURCE", operation_id=p.id, file_id=f.file_id, source_id=sid, disposition="KNOWN" if row else "NEW")
                        if row:
                            continue
                        new_ids.add(sid)
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
                    notify(progress, "Ukládání plateb", source_done, source_total)
                    notify(progress, "Ukládání historie")
                    actual_counts = {}
                    for occurrence in f.parsed.occurrences:
                        o = occurrence
                        sid = lookup.get((f.request.kind, o["source_identity"]))
                        disposition = o["disposition"]
                        if sid:
                            disposition = "NEW" if sid in new_ids and sid not in recorded_ids else "KNOWN"
                            recorded_ids.add(sid)
                        actual_counts[disposition] = actual_counts.get(disposition, 0) + 1
                        self.db.log.event("IMPORT_ROW_COMMIT", operation_id=p.id, file_id=f.file_id,
                                          row_start=o["row_start"], source_id=sid, disposition=disposition)
                        c.execute(
                            "INSERT OR IGNORE INTO source_occurrence VALUES(?,?,?,?,?,?,?,?,?,?)",
                            (
                                p.id,
                                f.file_id,
                                f.parsed.sheet,
                                o["row_start"],
                                o["row_end"],
                                sid,
                                disposition,
                                o["repair_code"],
                                canonical(o["raw_cells"]),
                                canonical(o["raw_types"]),
                            ),
                        )
                    if f.request.kind != "ACCOUNTS":
                        f.parsed.counters = actual_counts
                from kajovokarty.application.accounts import commit as commit_accounts
                p.accounts = commit_accounts(c, p.files, p.id, cancel, progress)
                inserted += p.accounts["new"]
                require(not (cancel and cancel.is_set()), "CANCELLED", "Import byl zrušen.")
                notify(progress, "Dokončování zápisu")
                for f in p.files:
                    if f.request.kind == "ACCOUNTS":
                        for outcome in f.parsed.account_outcomes:
                            self.db.log.event("ACCOUNTS_ROW_COMMIT", operation_id=p.id, file_id=f.file_id, **outcome)
                        self.db.audit(c, "ACCOUNTS_IMPORT_ROWS", operation=p.id,
                                      after={"file_id": f.file_id, "rows": f.parsed.account_outcomes})
                    c.execute(
                        "UPDATE import_file SET counters_json=? WHERE run_id=? AND file_id=? AND sheet_name=?",
                        (canonical(f.parsed.counters), p.id, f.file_id, f.parsed.sheet),
                    )
                if inserted:
                    self.db.invalidate_redo(c)
                c.execute(
                    "UPDATE import_run SET totals_json=?,row_counts_json=? WHERE id=?",
                    (
                        canonical(p.totals),
                        canonical({"new": inserted, "known": p.known, "accounts": p.accounts}),
                        p.id,
                    ),
                )
                self.db.audit(
                    c,
                    "IMPORT_COMMITTED",
                    after={"new": inserted, "known": p.known, "totals": p.totals, "accounts": p.accounts},
                    method="IMPORT",
                    operation=p.id,
                )
                c.execute("UPDATE operation SET state='COMPLETED',finished_at=?,safe_error_json=NULL WHERE id=?", (now(), p.id))
                self.db.audit(c, "OPERATION_COMPLETED", operation=p.id)
            committed_result = {"new": inserted, "known": p.known, "totals": p.totals, "accounts": p.accounts}
            return committed_result
        except Exception as cause:
            self.db.log.exception("IMPORT_FAILED", cause, operation_id=p.id)
            error = cause if isinstance(cause, AppError) else AppError("INTERNAL_ERROR", "Import se nepodařilo dokončit.")
            error.operation_id = p.id
            self.db.finish_operation(p.id, error)
            raise error from cause
        finally:
            try:
                self.discard(preview_id)
            except Exception as cleanup_error:
                self.db.log.exception('IMPORT_CLEANUP_FAILED', cleanup_error, operation_id=p.id)
                # Cleanup cannot roll back committed data or replace the original failure.
                if committed_result is not None:
                    committed_result['warnings'] = ['IMPORT_CLEANUP_FAILED']

    def discard(self, preview_id):
        p = self.previews.pop(preview_id, None)
        if p:
            errors = [d for d in p.diagnostics if d.get("severity") == "ERROR"
                      and d.get("code") not in ("SHEET_AMBIGUOUS", "CANCELLED")]
            error = AppError("IMPORT_INVALID", "Import obsahuje chyby. Žádné nové položky ani vazby nebyly uloženy.",
                             {"error_count": len(errors)}) if errors else None
            with self.db.transaction() as c:
                changed = c.execute(
                    "UPDATE operation SET state=?,finished_at=?,safe_error_json=? WHERE id=? AND state='RUNNING'",
                    ("FAILED" if error else "CANCELLED", now(),
                     canonical(error.as_dict()) if error else None, preview_id),
                )
                if changed.rowcount and error:
                    self.db.audit(c, "IMPORT_REJECTED", after=error.as_dict(), operation=preview_id)
            for f in p.files:
                f.snapshot.unlink(missing_ok=True)
