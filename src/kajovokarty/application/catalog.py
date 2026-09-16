"""Read-only UI queries and persisted view preferences."""

import json
from kajovokarty.domain.core import bytehash, canonical, now, require, uid


class CatalogService:
    def __init__(self, db):
        self.db = db

    def import_detail(self, run_id, file_id):
        if file_id is None:
            with self.db.connect() as c:
                row = c.execute("SELECT row_counts_json FROM import_run WHERE id=?", (run_id,)).fetchone()
            require(row, "QUERY_INVALID", "Import nebyl nalezen.")
            from kajovokarty.application.import_batch import file_text
            counts = json.loads(row[0])
            require(counts.get("import_result"), "QUERY_INVALID", "Výsledek není dostupný.")
            return counts.get("batch_summary") or file_text(counts["import_result"])
        with self.db.connect() as c:
            row = c.execute(
                "SELECT i.original_name,i.counters_json,o.state,r.parser_version,r.row_counts_json FROM import_file i JOIN operation o ON o.id=i.run_id JOIN import_run r ON r.id=i.run_id WHERE i.run_id=? AND i.file_id=?",
                (run_id, file_id),
            ).fetchone()
            require(row, "QUERY_INVALID", "Import nebyl nalezen.")
            diagnostics = [dict(r) for r in c.execute(
                "SELECT severity,code,message,row_start FROM import_diagnostic WHERE run_id=? AND file_id=? ORDER BY row_start,id",
                (run_id, file_id),
            )]
        counts = json.loads(row["row_counts_json"])
        if row["parser_version"] == "KK-IMPORT-2":
            per_file = json.loads(row["counters_json"])
            counts.update(new=per_file.get("NEW", per_file.get("new", 0)),
                          known=per_file.get("KNOWN", per_file.get("known", 0)))
        from kajovokarty.application.import_messages import file_text, reason
        if counts.get("import_result"):
            from kajovokarty.application.import_batch import file_text as import_file_text
            return counts.get("batch_summary") or import_file_text(counts["import_result"])
        if counts.get("booking_result"):
            return file_text(counts["booking_result"])
        lines = [row["original_name"]]
        if row["state"] == "COMPLETED":
            lines.append(f"Import dokončen. Uložené položky: {counts.get('new', 0)}. Dalších {counts.get('known', 0)} už v programu bylo a neukládaly se podruhé.")
        elif row["state"] in ("FAILED", "CANCELLED"):
            lines.append("Import nebyl dokončen. Žádné nové položky ani vazby z tohoto běhu nebyly uloženy.")
        else:
            lines.append("Stav importu: " + row["state"])
        lines.extend(["", "Zjištěné chyby a upozornění:"] if diagnostics else [])
        for d in diagnostics:
            lines.append(reason(d))
        return "\n".join(lines)

    def rows(self, kind):
        queries = {
            "generations": "SELECT id,context_id,kind,state,published_at FROM helper_generation WHERE state='PUBLISHED' ORDER BY published_at DESC",
            "imports": "SELECT r.id AS run_id,i.file_id,coalesce(i.original_name,json_extract(r.row_counts_json,'$.import_result.name'),'Soubor') AS original_name,i.sheet_name,i.input_mode,i.authoritative_snapshot_hash AS sha256,o.started_at,o.state,coalesce(i.counters_json,'{}') AS counters_json,r.parser_version,r.row_counts_json,r.selected_sources_json FROM import_run r JOIN operation o ON o.id=r.id LEFT JOIN import_file i ON i.run_id=r.id ORDER BY o.started_at DESC",
            "audit": "SELECT id,timestamp,type,method,object_refs_json,before_json,after_json FROM audit_event ORDER BY timestamp DESC",
            "operations": "SELECT id,type,state,started_at,finished_at FROM operation ORDER BY started_at DESC",
            "compatibility": "SELECT r.id,r.status,r.started_at,r.range_start,r.range_end,coalesce(json_extract(o.recovery_json,'$.evidence_class'),'UNKNOWN') AS evidence_class FROM api_compatibility_run r JOIN operation o ON o.id=r.id ORDER BY r.started_at DESC",
        }
        require(kind in queries, "QUERY_INVALID", "Neznámá tabulka.")
        with self.db.connect() as c:
            rows = [dict(r) for r in c.execute(queries[kind])]
        if kind == "imports":
            for row in rows:
                counts = json.loads(row.pop("row_counts_json"))
                if row.pop("parser_version") == "KK-IMPORT-2":
                    per_file = json.loads(row["counters_json"])
                    counts.update(new=per_file.get("NEW", per_file.get("new", 0)),
                                  known=per_file.get("KNOWN", per_file.get("known", 0)))
                kinds = json.loads(row.pop("selected_sources_json"))
                row["status_label"] = {"COMPLETED": "Zpracováno", "FAILED": "Nepodařilo se načíst", "CANCELLED": "Nenačteno", "RUNNING": "Probíhá načítání", "INTERRUPTED": "Přerušeno"}.get(row["state"], "Nedokončeno")
                if counts.get("import_result"):
                    from kajovokarty.application.import_batch import file_text as import_file_text
                    row["result_text"] = import_file_text(counts["import_result"])
                elif counts.get("booking_result"):
                    report = counts["booking_result"]
                    row["result_text"] = f"Načtené platby: {report['added']}. Již uložené platby: {report['already_saved']}."
                    if report["state"] != "COMPLETED":
                        row["result_text"] = "Žádné platby se nepřidaly. Otevřete podrobnosti pro vysvětlení."
                elif row["state"] == "COMPLETED":
                    what = {"BOOKING": "Platby z Bookingu", "ACCOUNTS": "Vazby rezervací", "CASHBOOK_CARD": "Pokladní pohyby", "BANK_CARD": "Platby z terminálu"}.get(kinds[0] if len(kinds) == 1 else "", "Položky")
                    row["result_text"] = f"{what} — načteno: {counts.get('new', 0)}. Již v programu: {counts.get('known', 0)}."
                else:
                    row["result_text"] = "Z tohoto souboru se zatím nic nepřidalo. Podrobnosti otevřete dvojklikem."
        return rows

    def source_origin(self, sid):
        with self.db.connect() as c:
            return [
                dict(r)
                for r in c.execute(
                    "SELECT o.*,f.original_name,f.sha256 FROM source_occurrence o JOIN source_file f ON f.id=o.file_id WHERE o.source_id=? ORDER BY o.run_id,o.row_start",
                    (sid,),
                )
            ]

    def original(self, fid, path):
        from pathlib import Path

        with self.db.connect() as c:
            r = c.execute(
                "SELECT bytes,sha256 FROM source_file WHERE id=?", (fid,)
            ).fetchone()
        require(
            r and bytehash(r["bytes"]) == r["sha256"],
            "SNAPSHOT_INVALID",
            "Zdrojový soubor není platný.",
        )
        Path(path).write_bytes(r["bytes"])
        return path

    def save_view(self, key, value):
        with self.db.transaction() as c:
            c.execute(
                "INSERT INTO view_state VALUES(?,?,'[]',NULL,1) ON CONFLICT(view_key) DO UPDATE SET columns_json=excluded.columns_json,revision=view_state.revision+1",
                (key, canonical(value)),
            )

    def view(self, key):
        with self.db.connect() as c:
            r = c.execute(
                "SELECT columns_json FROM view_state WHERE view_key=?", (key,)
            ).fetchone()
            return json.loads(r[0]) if r else None

    def save_filter(self, name, scope, filters, sort):
        require(name.strip(), "FILTER_INVALID", "Zadejte název filtru.")
        with self.db.transaction() as c:
            c.execute(
                "INSERT INTO saved_filter VALUES(?,?,?,?,?,?,?,1) ON CONFLICT(name) DO UPDATE SET scope=excluded.scope,filter_json=excluded.filter_json,sort_json=excluded.sort_json,updated_at=excluded.updated_at,revision=saved_filter.revision+1",
                (uid(), name, scope, canonical(filters), canonical(sort), now(), now()),
            )

    def filters(self):
        with self.db.connect() as c:
            return [
                dict(r) for r in c.execute("SELECT * FROM saved_filter ORDER BY name")
            ]

    def delete_filter(self, id):
        with self.db.transaction() as c:
            c.execute("DELETE FROM saved_filter WHERE id=?", (id,))

    def reset_views(self):
        with self.db.transaction() as c:
            c.execute("DELETE FROM view_state")

    def rename_filter(self, id, name):
        require(name.strip(), "FILTER_INVALID", "Zadejte název filtru.")
        with self.db.transaction() as c:
            c.execute(
                "UPDATE saved_filter SET name=?,updated_at=?,revision=revision+1 WHERE id=?",
                (name.strip(), now(), id),
            )

    def global_matches(self, text):
        from kajovokarty.domain.core import search_tokens, search_normalize

        tokens = search_tokens(text)
        rows = []
        with self.db.connect() as c:
            c.execute("BEGIN")
            st = dict(c.execute("SELECT * FROM helper_state").fetchone())
            for r in c.execute(
                "SELECT h.*,s.payload_json FROM helper_current h JOIN helper_snapshot s ON s.id=h.snapshot_id JOIN helper_generation g ON g.id=h.generation_id WHERE g.state='PUBLISHED'"
            ):
                if not all(t in r["local_search_text"] for t in tokens):
                    continue
                current = (r["context_id"], r["generation_id"]) == (
                    st["context_id"],
                    st["published_generation_id"],
                )
                rows.append(
                    {
                        **dict(r),
                        "id": ":".join(
                            (
                                r["context_id"],
                                r["generation_id"],
                                r["resource_type"],
                                r["external_id"],
                            )
                        ),
                        "type": "HELPER",
                        "lifecycle": "ACTIVE"
                        if current and r["active"]
                        else "HISTORICAL",
                        "primary_identifier": r["external_id"],
                        "description": r["resource_type"]
                        + " · "
                        + ("aktuální" if current else "historie"),
                        "reason": "HELPER_CONTEXT_MISMATCH"
                        if not current
                        else "HELPER_ENTITY_NOT_OBSERVED"
                        if not r["active"]
                        else "Pouze identifikace",
                        "amount": None,
                        "difference": None,
                        "kinds": [],
                        "resolved": None,
                    }
                )
            for r in c.execute(
                "SELECT w.*,g.note,g.created_at FROM work_object w JOIN reconciliation_group g ON g.object_id=w.id WHERE w.lifecycle='DISSOLVED'"
            ):
                archive = c.execute(
                    "SELECT evidence_json FROM group_history WHERE group_id=? ORDER BY created_at DESC,id DESC LIMIT 1",
                    (r["id"],),
                ).fetchone()
                raw = archive[0] if archive else "{}"
                hay = search_normalize(r["id"] + " " + (r["note"] or "") + " " + raw)
                if not all(t in hay for t in tokens):
                    continue
                evidence = json.loads(raw)
                difference = evidence.get("difference", 0)
                rows.append(
                    {
                        **dict(r),
                        "primary_identifier": "G" + r["id"][:10],
                        "description": r["note"],
                        "date": r["created_at"][:10],
                        "difference": difference,
                        "amount": abs(difference),
                        "resolved": difference == 0,
                        "leaf_count": len(evidence.get("leaves", [])),
                        "kinds": sorted(
                            {l["kind"] for l in evidence.get("leaves", [])}
                        ),
                        "reason": "Historická rozložená skupina",
                    }
                )
        return rows
