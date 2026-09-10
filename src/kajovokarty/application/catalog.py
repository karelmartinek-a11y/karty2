"""Read-only UI queries and persisted view preferences."""

import json
from kajovokarty.domain.core import bytehash, canonical, now, require, uid


class CatalogService:
    def __init__(self, db):
        self.db = db

    def rows(self, kind):
        queries = {
            "generations": "SELECT id,context_id,kind,state,published_at FROM helper_generation WHERE state='PUBLISHED' ORDER BY published_at DESC",
            "imports": "SELECT i.run_id,i.file_id,i.original_name,i.sheet_name,i.input_mode,i.authoritative_snapshot_hash AS sha256,o.started_at,o.state,i.counters_json FROM import_file i JOIN operation o ON o.id=i.run_id ORDER BY o.started_at DESC",
            "audit": "SELECT id,timestamp,type,method,object_refs_json,before_json,after_json FROM audit_event ORDER BY timestamp DESC",
            "operations": "SELECT id,type,state,started_at,finished_at FROM operation ORDER BY started_at DESC",
            "compatibility": "SELECT r.id,r.status,r.started_at,r.range_start,r.range_end,coalesce(json_extract(o.recovery_json,'$.evidence_class'),'UNKNOWN') AS evidence_class FROM api_compatibility_run r JOIN operation o ON o.id=r.id ORDER BY r.started_at DESC",
        }
        require(kind in queries, "QUERY_INVALID", "Neznámá tabulka.")
        with self.db.connect() as c:
            return [dict(r) for r in c.execute(queries[kind])]

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
