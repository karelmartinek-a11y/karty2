"""Replay proven rejected inputs and re-evaluate untouched automatic pairs.

Use on a verified copy first. Explicit --apply is required; caller must hold the
application workspace lock and make a verified backup before applying to live data.
"""
import argparse
from collections import defaultdict
import json
from pathlib import Path

from kajovokarty.application.imports import ImportInput, ImportService
from kajovokarty.application.matching import MatchingService
from kajovokarty.application.settings import SettingsService
from kajovokarty.application.work import WorkService
from kajovokarty.domain.matching import bank_edges, isolated, reversals, terminal_edges
from kajovokarty.infrastructure.database import Database


def proposed_pairs(db):
    """Project the new rules without altering existing financial evidence."""
    with db.connect() as c:
        # Revision one, direct source children and no parent: no manual edits.
        groups = [dict(r) for r in c.execute("""SELECT g.*,w.revision FROM reconciliation_group g
            JOIN work_object w ON w.id=g.object_id WHERE g.method='AUTO' AND w.lifecycle='ACTIVE'
            AND w.revision=1 AND NOT EXISTS(SELECT 1 FROM membership WHERE child_id=g.object_id AND active=1)
            AND NOT EXISTS(SELECT 1 FROM membership m JOIN work_object child ON child.id=m.child_id
                WHERE m.parent_id=g.object_id AND m.active=1 AND child.type!='SOURCE')""")]
        group_members = {g["object_id"]: frozenset(r[0] for r in c.execute(
            "SELECT child_id FROM membership WHERE parent_id=? AND active=1", (g["object_id"],))) for g in groups}
        included = set().union(*group_members.values()) if group_members else set()
        included.update(r[0] for r in c.execute("""SELECT f.id FROM financial_source f JOIN work_object w ON w.source_id=f.id
            WHERE w.lifecycle='ACTIVE' AND NOT EXISTS(SELECT 1 FROM membership WHERE child_id=w.id AND active=1)"""))
        rows = [dict(r) for r in c.execute("SELECT * FROM financial_source") if r["id"] in included]
        refs = defaultdict(list)
        for r in c.execute("SELECT s.variable_symbol,a.booking_reference FROM account_symbol s JOIN account_reservation a USING(reservation)"):
            refs[r[0]].append(r[1])
    for r in rows:
        r["payload"] = json.loads(r["canonical_json"])
    expected = set()
    window = SettingsService(db).get()["matching.bank_window_days"]
    while True:
        before = len(expected)
        def accept(edges):
            nonlocal rows
            pairs = isolated(edges)
            expected.update(pairs)
            used = set().union(*pairs) if pairs else set()
            rows = [r for r in rows if r["id"] not in used]
        accept(reversals([r for r in rows if r["kind"] == "BANK_CARD"]))
        index = defaultdict(list)
        for r in rows:
            if r["kind"] == "BOOKING":
                index[(r["payload"]["booking_reference"], r["currency"], r["signed_amount_minor"])].append(r)
        booking = []
        for r in rows:
            links = refs.get(r["payload"].get("variable_symbol"), [])
            if r["kind"] == "CASHBOOK_CARD" and len(links) == 1:
                booking.extend(frozenset((r["id"], b["id"])) for b in index[(links[0], r["currency"], r["signed_amount_minor"])])
        accept(booking)
        def terminal_inputs():
            return ([r for r in rows if r["kind"] == "CASHBOOK_CARD" and not refs.get(r["payload"].get("variable_symbol"))],
                    [r for r in rows if r["kind"] == "BANK_CARD"])
        accept(terminal_edges(*terminal_inputs()))
        accept(bank_edges(*terminal_inputs(), window))
        if len(expected) == before:
            break
    return [dict(group_id=g["object_id"], revision=g["revision"],
                 fingerprint=json.loads(g["evidence_json"]).get("fingerprint"),
                 rule=json.loads(g["evidence_json"]).get("rule_id"),
                 members=sorted(group_members[g["object_id"]]))
            for g in groups if group_members[g["object_id"]] not in expected]


def repair(db, retry_files):
    result = {"imports": [], "dissolved": [], "matching": None}
    for file_id in retry_files:
        with db.connect() as c:
            row = c.execute("""SELECT i.*,r.selected_sources_json,o.state FROM import_file i
                JOIN import_run r ON r.id=i.run_id JOIN operation o ON o.id=r.id WHERE i.file_id=?
                ORDER BY o.started_at DESC LIMIT 1""", (file_id,)).fetchone()
            kinds = json.loads(row["selected_sources_json"])
            if len(kinds) != 1:
                raise ValueError("The input must have one proven import kind")
        importer = ImportService(db)
        preview = importer.preflight([ImportInput(kinds[0], source_file_id=file_id,
            sheet=row["sheet_name"] or None, original_run_id=row["run_id"], original_name=row["original_name"])])
        if not preview.valid:
            importer.discard(preview.id)
            raise ValueError("Replayed input still contains errors; no repair was applied for this file")
        outcome = importer.commit(preview.id)
        result["imports"].append(dict(file_id=file_id, original_run=row["run_id"], new_run=preview.id, **outcome))
        with db.transaction() as c:
            db.audit(c, "FORENSIC_IMPORT_REVIEW", operation=preview.id,
                     before={"operation_id": row["run_id"], "state": row["state"]},
                     after={"replacement_operation": preview.id, "new": outcome["new"], "contract": "KK-IMPORT-2"})
    changes = proposed_pairs(db)
    work = WorkService(db)
    for change in changes:
        with db.connect() as c:
            suppression = c.execute("SELECT active FROM auto_suppression WHERE fingerprint=?", (change["fingerprint"],)).fetchone()
        command = work.dissolve(change["group_id"], change["revision"])
        # This is a rule correction, not a user's prohibition. Preserve any pre-existing ban.
        if change["fingerprint"] and not (suppression and suppression[0]):
            work.allow_auto(change["fingerprint"])
        with db.transaction() as c:
            db.audit(c, "FORENSIC_MATCH_REVIEW", refs=[change["group_id"]], command=command,
                     before=change, after={"contract": "KK-MATCH-2", "reason": "PAIR_NOT_PROVEN_UNDER_CURRENT_RULES"})
        result["dissolved"].append(change)
    result["matching"] = MatchingService(db, SettingsService(db)).run()
    with db.connect() as c:
        db.validate(c)
        assert not c.execute("PRAGMA foreign_key_check").fetchall()
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--retry-file", action="append", default=[])
    parser.add_argument("--apply", action="store_true", required=True)
    args = parser.parse_args()
    # Same cross-process lock as the desktop application, including stale-process detection.
    from PySide6.QtCore import QLockFile
    lock = QLockFile(str(args.database.parent / "application.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(0):
        raise SystemExit("Pracovní prostor používá aplikace; oprava nebyla spuštěna.")
    try:
        result = repair(Database(args.database), args.retry_file)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"added": sum(r["new"] for r in result["imports"]), "dissolved": len(result["dissolved"]),
                          "created": result["matching"]["created_groups"]}))
    finally:
        lock.unlock()
