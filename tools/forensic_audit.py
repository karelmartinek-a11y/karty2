"""Read-only reconciliation of stored input evidence; never opens the app database writer."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sqlite3

from kajovokarty.domain.core import AppError, digest
from kajovokarty.infrastructure.parsers import parse


def audit(path):
    connection = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    with connection as c:
        sources = {(r["kind"], r["source_identity"]): dict(r) for r in c.execute("SELECT * FROM financial_source")}
        inputs, discrepancies, occurrence_errors = [], [], []
        parsed_files = {}
        for source in sources.values():
            assert digest(json.loads(source["canonical_json"])) == source["content_hash"]
        covered = set()
        for f in c.execute("SELECT * FROM source_file ORDER BY created_at,id").fetchall():
            assert len(f["bytes"]) == f["byte_size"]
            assert hashlib.sha256(f["bytes"]).hexdigest() == f["sha256"]
            uses = c.execute("""SELECT i.*,o.state,r.selected_sources_json FROM import_file i
                JOIN import_run r ON r.id=i.run_id JOIN operation o ON o.id=r.id
                WHERE file_id=? ORDER BY o.started_at""", (f["id"],)).fetchall()
            variants = {(kind, u["sheet_name"]): u for u in uses for kind in json.loads(u["selected_sources_json"])}
            for (kind, sheet), use in variants.items():
                item = dict(file_id=f["id"], kind=kind, sheet=sheet, historical_states=sorted({u["state"] for u in uses}))
                try:
                    parsed = parse(f["bytes"], use["original_name"], kind, sheet or None)
                except AppError as e:
                    item.update(error=e.code)
                    inputs.append(item)
                    continue
                item.update(counters=parsed.counters, errors=[d["code"] for d in parsed.diagnostics if d["severity"] == "ERROR"],
                            warnings=[d["code"] for d in parsed.diagnostics if d["severity"] == "WARNING"],
                            parsed_sources=len(parsed.sources), accounts=len(parsed.accounts))
                parsed_files[(f["id"], kind, sheet)] = parsed
                for use_row in uses:
                    if use_row["state"] != "COMPLETED" or use_row["sheet_name"] != sheet or kind == "ACCOUNTS":
                        continue
                    stored_rows = {r["row_start"]: r for r in c.execute("""SELECT o.*,s.source_identity
                        FROM source_occurrence o LEFT JOIN financial_source s ON s.id=o.source_id
                        WHERE o.run_id=? AND o.file_id=? AND o.sheet=?""", (use_row["run_id"], f["id"], sheet))}
                    if len(stored_rows) != len(parsed.occurrences):
                        occurrence_errors.append(dict(run_id=use_row["run_id"], file_id=f["id"], error="ROW_COUNT"))
                    for occurrence in parsed.occurrences:
                        old = stored_rows.get(occurrence["row_start"])
                        if old is None or old["source_identity"] != occurrence["source_identity"] or old["row_end"] != occurrence["row_end"]:
                            occurrence_errors.append(dict(run_id=use_row["run_id"], file_id=f["id"],
                                                          row=occurrence["row_start"], error="SOURCE_LINK"))
                counts = Counter()
                for s in parsed.sources:
                    key = (s.kind, s.identity)
                    stored = sources.get(key)
                    if not stored:
                        counts["not_stored"] += 1
                        continue
                    covered.add(stored["id"])
                    old = json.loads(stored["canonical_json"])
                    changed = sorted(k for k in set(old) | set(s.content) if old.get(k) != s.content.get(k))
                    counts["identical" if not changed else "different"] += 1
                    if changed:
                        discrepancies.append(dict(file_id=f["id"], source_id=stored["id"], fields=changed))
                item["comparison"] = dict(counts)
                inputs.append(item)
        account_errors = []
        for symbol in c.execute("SELECT s.*,a.booking_reference FROM account_symbol s JOIN account_reservation a USING(reservation)"):
            parsed = parsed_files.get((symbol["file_id"], "ACCOUNTS", symbol["sheet"]))
            if not parsed or not any(r["row"] == symbol["row_number"] and all(r[k] == symbol[k]
                    for k in ("variable_symbol", "reservation", "booking_reference")) for r in parsed.accounts):
                account_errors.append(dict(file_id=symbol["file_id"], row=symbol["row_number"]))
        report = dict(inputs=inputs, discrepancies=discrepancies, occurrence_errors=occurrence_errors,
                      account_provenance_errors=account_errors,
                      sources=len(sources), sources_without_reparsed_evidence=sorted(r["id"] for r in sources.values() if r["id"] not in covered),
                      operations=[dict(r) for r in c.execute("SELECT type,state,count(*) AS count FROM operation GROUP BY type,state")],
                      diagnostics=[dict(r) for r in c.execute("SELECT severity,code,count(*) AS count FROM import_diagnostic GROUP BY severity,code")],
                      groups=[dict(r) for r in c.execute("SELECT method,count(*) AS count FROM reconciliation_group g JOIN work_object w ON w.id=g.object_id WHERE w.lifecycle='ACTIVE' GROUP BY method")])
    connection.close()
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    report = audit(args.database)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"inputs": len(report["inputs"]), "sources": report["sources"],
                      "discrepancies": len(report["discrepancies"]),
                      "without_evidence": len(report["sources_without_reparsed_evidence"])}))
