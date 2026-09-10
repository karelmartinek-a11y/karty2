"""Snapshot report materialization. Schema is copied verbatim from SSOT 14.3."""

from pathlib import Path
import json
from kajovokarty.domain.core import (
    canonical,
    checked,
    digest,
    now,
    require,
    search_normalize,
    search_tokens,
    uid,
)
from kajovokarty.application.helper_report import build_helpers
from kajovokarty.application.work_query import choices, FIELDS
from kajovokarty.application.work import WorkService

SCHEMA = json.loads(
    (Path(__file__).parents[1] / "assets/export_schema.json").read_text()
)
REPORTS = {
    "unresolved": ["work_objects", "currency_totals"],
    "resolved": [
        "work_objects",
        "group_summary",
        "group_leaves",
        "group_edges",
        "source_occurrences",
        "currency_totals",
    ],
    "group_evidence": [
        "group_summary",
        "group_leaves",
        "group_edges",
        "source_occurrences",
        "currency_totals",
    ],
    "cashbook_cards": [
        "financial_sources",
        "cashbook_rows",
        "source_occurrences",
        "currency_totals",
    ],
    "terminal": [
        "financial_sources",
        "bank_rows",
        "source_occurrences",
        "currency_totals",
    ],
    "booking": [
        "financial_sources",
        "booking_rows",
        "booking_payouts",
        "source_occurrences",
        "currency_totals",
    ],
    "helpers": ["helper_entities", "helper_links", "helper_references"],
    "audit": ["audit_events"],
    "import_errors": ["import_diagnostics"],
    "api_compatibility": ["api_compatibility"],
}


class ReportService:
    def __init__(self, db):
        self.db = db
        self.work = WorkService(db)

    def partition_work_selection(self, ids):
        """Explicit roots are partitioned without silently discarding the other status."""
        wanted = set(ids)
        rows = self.work.query({"status": "all"}, page_size=0)["rows"]
        selected = [r for r in rows if r["id"] in wanted]
        require(
            wanted and {r["id"] for r in selected} == wanted,
            "STALE_STATE",
            "Výběr obsahuje objekt, který již není aktivním kořenem.",
        )
        return {
            name: [r["id"] for r in selected if r["resolved"] == resolved]
            for name, resolved in (("unresolved", False), ("resolved", True))
            if any(r["resolved"] == resolved for r in selected)
        }

    def build(self, report_id, ids=None, filters=None, sort=None):
        filters = dict(filters or {})
        effective_filters = {} if ids is not None else dict(filters)
        if report_id not in (
            "unresolved",
            "resolved",
            "cashbook_cards",
            "terminal",
            "booking",
        ):
            effective_filters.pop("column_filters", None)
        require(report_id in REPORTS, "EXPORT_INVALID", "Neznámý typ sestavy.")
        data = {k: [] for k in ["metadata", *REPORTS[report_id]]}
        with self.db.gate, self.db.connect() as c:
            c.execute("BEGIN")
            st = dict(c.execute("SELECT * FROM helper_state").fetchone())
            objects, groups, children, parents, sources = self.work._graph(c)
            projected = self.work.query(
                {
                    **effective_filters,
                    "status": "resolved"
                    if report_id == "resolved"
                    else "all"
                    if report_id not in ("unresolved",)
                    else "unresolved",
                },
                page_size=0,
                sort=sort,
                _connection=c,
            )["rows"]
            chosen = [r for r in projected if ids is None or r["id"] in ids]
            source_ids = set()
            group_ids = []
            for r in chosen:
                if report_id in ("unresolved", "resolved"):
                    payloads = [
                        json.loads(sources[i]["canonical_json"]) for i in r["leaves"]
                    ]
                    data["work_objects"].append(
                        {
                            "object_id": r["id"],
                            "object_type": r["type"],
                            "status": "RESOLVED" if r["resolved"] else "UNRESOLVED",
                            "method": r["method"],
                            "source_kinds": r["kinds"],
                            "date_from": r["date"],
                            "date_to": r["date_end"],
                            "primary_identifier": r["primary_identifier"],
                            "description": r["description"],
                            "leaf_count": r["leaf_count"],
                            "side": "NEED"
                            if r["difference"] > 0
                            else "SURPLUS"
                            if r["difference"] < 0
                            else "BALANCED",
                            "amount_minor": r["amount"],
                            "difference_minor": r["difference"],
                            "currency": r["currency"],
                            "booking_references": sorted(
                                {
                                    p["booking_reference"]
                                    for p in payloads
                                    if p.get("booking_reference")
                                }
                            ),
                            "invoice_codes": sorted(
                                {
                                    p["invoice_code"]
                                    for p in payloads
                                    if p.get("invoice_code")
                                }
                            ),
                            "reason_codes": [r["reason"]] if r["reason"] else [],
                            "note": r["note"],
                        }
                    )
                    if report_id == "resolved":
                        group_ids.append(r["id"])
            if report_id == "group_evidence":
                require(
                    ids and len(ids) == 1 and ids[0] in groups,
                    "EXPORT_INVALID",
                    "Vyberte právě jednu skupinu.",
                )
                group_ids = list(ids)
            for gid in group_ids:
                evidence = self.work.evidence(gid, _connection=c)
                g = groups[gid]
                leaves = [s["id"] for s in evidence["leaves"]]
                proof = json.loads(g["evidence_json"])
                hp = proof.get("helper_provenance") or []
                hp = [hp] if isinstance(hp, dict) else hp
                data["group_summary"].append(
                    {
                        "group_id": gid,
                        "lifecycle": objects[gid]["lifecycle"],
                        "status": "RESOLVED"
                        if evidence["difference"] == 0
                        else "UNRESOLVED",
                        "created_at": g["created_at"],
                        "method": g["method"],
                        "currency": objects[gid]["currency"],
                        "difference_minor": evidence["difference"],
                        "leaf_count": len(leaves),
                        "evidence_hash": proof.get("evidence_hash") or digest(proof),
                        "note": g["note"],
                        "evidence_context_ids": sorted({p["context_id"] for p in hp}),
                        "evidence_generation_ids": sorted(
                            {p["generation_id"] for p in hp}
                        ),
                    }
                )
                for sid in leaves:
                    s = sources[sid]
                    p = json.loads(s["canonical_json"])
                    source_ids.add(sid)
                    data["group_leaves"].append(
                        {
                            "group_id": gid,
                            "source_id": sid,
                            "source_kind": s["kind"],
                            "source_identity": s["source_identity"],
                            "source_hash": s["content_hash"],
                            "primary_identifier": s["primary_identifier"],
                            "local_date": s["local_date"],
                            "signed_amount_minor": s["signed_amount_minor"],
                            "contribution_minor": s["signed_amount_minor"]
                            * (1 if s["kind"] == "CASHBOOK_CARD" else -1),
                            "currency": s["currency"],
                            "invoice_codes": [p["invoice_code"]]
                            if p.get("invoice_code")
                            else [],
                            "reservation_ids": sorted(
                                {
                                    e["external_id"]
                                    for h in hp
                                    for e in h["entities"]
                                    if e["resource_type"] == "reservation"
                                }
                            ),
                            "booking_references": [p["booking_reference"]]
                            if p.get("booking_reference")
                            else [],
                            "helper_entity_keys": sorted(
                                [
                                    {
                                        "context_id": h["context_id"],
                                        "generation_id": h["generation_id"],
                                        "resource_type": e["resource_type"],
                                        "external_id": e["external_id"],
                                    }
                                    for h in hp
                                    for e in h["entities"]
                                ],
                                key=canonical,
                            ),
                        }
                    )
                if evidence.get("edges") is not None:
                    for e in evidence["edges"]:
                        data["group_edges"].append(
                            {
                                "group_id": gid,
                                "membership_id": e["id"],
                                "parent_object_id": e["parent_id"],
                                "child_object_id": e["child_id"],
                                "child_type": objects[e["child_id"]]["type"],
                                "child_position": e["child_position"],
                            }
                        )
                stack = [] if evidence.get("edges") is not None else [gid]
                seen = set()
                while stack:
                    parent = stack.pop()
                    if parent in seen:
                        continue
                    seen.add(parent)
                    edges = c.execute(
                        "SELECT * FROM membership WHERE parent_id=?"
                        + (
                            " AND active=1"
                            if objects[parent]["lifecycle"] == "ACTIVE"
                            else ""
                        )
                        + " ORDER BY created_at,id",
                        (parent,),
                    ).fetchall()
                    used = set()
                    for e in edges:
                        if e["child_id"] in used:
                            continue
                        used.add(e["child_id"])
                        data["group_edges"].append(
                            {
                                "group_id": gid,
                                "membership_id": e["id"],
                                "parent_object_id": parent,
                                "child_object_id": e["child_id"],
                                "child_type": objects[e["child_id"]]["type"],
                                "child_position": len(used),
                            }
                        )
                        if objects[e["child_id"]]["type"] == "GROUP":
                            stack.append(e["child_id"])
            kinds = {
                "cashbook_cards": "CASHBOOK_CARD",
                "terminal": "BANK_CARD",
                "booking": "BOOKING",
            }
            if report_id in kinds:
                kind = kinds[report_id]
                source_ids = {
                    sid
                    for sid, s in sources.items()
                    if s["kind"] == kind and (ids is None or sid in ids)
                }
                if ids is None and filters:
                    tokens = search_tokens(filters.get("text", ""))
                    source_ids = {
                        sid
                        for sid in source_ids
                        if (
                            not filters.get("currency")
                            or sources[sid]["currency"] in filters["currency"]
                        )
                        and (
                            not filters.get("date_from")
                            or sources[sid]["local_date"] >= filters["date_from"]
                        )
                        and (
                            not filters.get("date_to")
                            or sources[sid]["local_date"] <= filters["date_to"]
                        )
                        and (
                            filters.get("amount") is None
                            or sources[sid]["signed_amount_minor"] == filters["amount"]
                        )
                        and all(
                            t in search_normalize(sources[sid]["canonical_json"])
                            for t in tokens
                        )
                    }
                if ids is None:

                    def matches(sid):
                        row = sources[sid]
                        payload = json.loads(row["canonical_json"])
                        if (
                            filters.get("amount_min") is not None
                            and row["signed_amount_minor"] < filters["amount_min"]
                        ):
                            return False
                        if (
                            filters.get("amount_max") is not None
                            and row["signed_amount_minor"] > filters["amount_max"]
                        ):
                            return False
                        return all(
                            not filters.get(k)
                            or any(
                                search_normalize(str(payload.get(k) or "")).startswith(
                                    search_normalize(str(v))
                                )
                                for v in choices(filters[k])
                            )
                            for k in FIELDS
                        )

                    source_ids = {sid for sid in source_ids if matches(sid)}
                for sid in sorted(source_ids):
                    s = sources[sid]
                    p = json.loads(s["canonical_json"])
                    root = sid
                    while root in parents:
                        root = parents[root]
                    diff = self.work._difference(
                        self.work._leaves(root, objects, children), sources
                    )
                    data["financial_sources"].append(
                        {
                            "source_id": sid,
                            "source_kind": s["kind"],
                            "source_identity": s["source_identity"],
                            "source_hash": s["content_hash"],
                            "primary_identifier": s["primary_identifier"],
                            "description": s["description"],
                            "local_date": s["local_date"],
                            "occurred_at_utc": s["occurred_at_utc"],
                            "time_precision": s["time_precision"],
                            "signed_amount_minor": s["signed_amount_minor"],
                            "contribution_minor": s["signed_amount_minor"]
                            * (1 if kind == "CASHBOOK_CARD" else -1),
                            "currency": s["currency"],
                            "root_object_id": root,
                            "root_status": "RESOLVED" if diff == 0 else "UNRESOLVED",
                            "created_at": s["created_at"],
                        }
                    )
                    dataset = {
                        "CASHBOOK_CARD": "cashbook_rows",
                        "BANK_CARD": "bank_rows",
                        "BOOKING": "booking_rows",
                    }[kind]
                    detail = {"source_id": sid, **p}
                    if kind == "BOOKING":
                        detail["payout_key"] = digest(
                            [p[k] for k in ("payout_id", "payout_date", "currency")]
                        )
                        detail["row_hash"] = digest(
                            [
                                p[k]
                                for k in (
                                    "payout_id",
                                    "booking_reference",
                                    "currency",
                                    "signed_amount_minor",
                                    "payout_date",
                                    "arrival",
                                    "departure",
                                    "invoice_type",
                                    "payment_status",
                                )
                            ]
                        )
                    data[dataset].append(detail)
                if report_id == "booking":
                    payouts = {}
                    for r in data["booking_rows"]:
                        payouts.setdefault(r["payout_key"], []).append(r)
                    for key, rs in sorted(payouts.items()):
                        allcount = c.execute(
                            "SELECT count(*) FROM booking_detail WHERE payout_key=?",
                            (key,),
                        ).fetchone()[0]
                        amount = checked(sum(r["signed_amount_minor"] for r in rs))
                        r = rs[0]
                        data["booking_payouts"].append(
                            {
                                "payout_key": key,
                                "payout_id": r["payout_id"],
                                "payout_date": r["payout_date"],
                                "currency": r["currency"],
                                "scope": "FULL"
                                if len(rs) == allcount
                                else "FILTERED_PARTIAL",
                                "included_line_count": len(rs),
                                "all_payout_line_count": allcount,
                                "signed_amount_minor": amount,
                                "contribution_minor": -amount,
                                "booking_references": sorted(
                                    {r["booking_reference"] for r in rs}
                                ),
                            }
                        )
            if "source_occurrences" in data:
                for r in c.execute(
                    "SELECT o.*,f.sha256,i.original_name,i.input_mode FROM source_occurrence o JOIN source_file f ON f.id=o.file_id JOIN import_file i ON i.run_id=o.run_id AND i.file_id=o.file_id AND i.sheet_name=o.sheet ORDER BY o.source_id,o.run_id,o.file_id,o.sheet,o.row_start"
                ):
                    if r["source_id"] in source_ids:
                        data["source_occurrences"].append(
                            {
                                **dict(r),
                                "file_hash": r["sha256"],
                                "sheet": "" if r["sheet"] == "CSV" else r["sheet"],
                            }
                        )
            if report_id == "audit":
                data["audit_events"] = [
                    {**dict(r), "event_id": r["id"], "event_type": r["type"]}
                    for r in c.execute(
                        "SELECT * FROM audit_event ORDER BY timestamp,id"
                    )
                    if (ids is None or r["id"] in ids)
                    and (
                        ids is not None or event_matches(dict(r), filters, "timestamp")
                    )
                ]
            if report_id == "import_errors":
                import_files = import_runs = None
                if ids is None and filters.get("import_columns"):
                    from kajovokarty.domain.columns import filter_rows

                    imports = [
                        dict(r)
                        for r in c.execute(
                            "SELECT i.run_id,i.file_id,i.original_name,i.sheet_name,"
                            "i.input_mode,i.authoritative_snapshot_hash AS sha256,"
                            "o.started_at,o.state,i.counters_json FROM import_file i "
                            "JOIN operation o ON o.id=i.run_id"
                        )
                    ]
                    matching = filter_rows(imports, filters["import_columns"])
                    import_files = {r["file_id"] for r in matching}
                    import_runs = {r["run_id"] for r in matching}
                data["import_diagnostics"] = [
                    {
                        **dict(r),
                        "diagnostic_id": r["id"],
                        "operation_id": r["run_id"],
                        "file_hash": r["sha256"],
                        "source_identity": r["identity"],
                        "raw_value_json": json.loads(r["raw_value_json"])
                        if r["raw_value_json"]
                        else None,
                    }
                    for r in c.execute(
                        "SELECT d.*,f.sha256,f.original_name FROM import_diagnostic d LEFT JOIN source_file f ON f.id=d.file_id ORDER BY d.created_at,d.id"
                    )
                    if (ids is None or r["run_id"] in ids)
                    and (
                        import_files is None
                        or r["file_id"] in import_files
                        or r["file_id"] is None
                        and r["run_id"] in import_runs
                    )
                    and r["severity"] in filters.get("severity", ["ERROR", "WARNING"])
                    and (
                        ids is not None or event_matches(dict(r), filters, "created_at")
                    )
                ]
            if report_id == "api_compatibility":
                require(
                    ids and len(ids) == 1, "EXPORT_INVALID", "Vyberte běh ověření API."
                )
                data["api_compatibility"] = [
                    {
                        **dict(r),
                        "overall_status": r["status"],
                        "endpoint_status": r["state"],
                    }
                    for r in c.execute(
                        "SELECT r.*,e.* FROM api_compatibility_run r JOIN api_compatibility_endpoint e ON e.run_id=r.id WHERE r.id=? ORDER BY e.endpoint_template",
                        (ids[0],),
                    )
                ]
            if report_id == "helpers":
                data.update(build_helpers(c, st, ids, filters))
            if "currency_totals" in data:
                base = (
                    "work_objects"
                    if "work_objects" in data
                    else "group_leaves"
                    if "group_leaves" in data
                    else "financial_sources"
                )
                for cur in ("CZK", "EUR"):
                    rs = [r for r in data[base] if r["currency"] == cur]
                    if not rs:
                        continue
                    t = {
                        "dataset": base,
                        "currency": cur,
                        "row_count": len(rs),
                        "signed_amount_minor": None,
                        "contribution_minor": None,
                        "need_minor": None,
                        "surplus_minor": None,
                        "difference_minor": None,
                    }
                    if base == "work_objects":
                        t.update(
                            need_minor=checked(
                                sum(max(r["difference_minor"], 0) for r in rs)
                            ),
                            surplus_minor=checked(
                                sum(max(-r["difference_minor"], 0) for r in rs)
                            ),
                            difference_minor=checked(
                                sum(r["difference_minor"] for r in rs)
                            ),
                        )
                    else:
                        t.update(
                            signed_amount_minor=checked(
                                sum(r["signed_amount_minor"] for r in rs)
                            ),
                            contribution_minor=checked(
                                sum(r["contribution_minor"] for r in rs)
                            ),
                        )
                    if base == "group_leaves":
                        t["difference_minor"] = t["contribution_minor"]
                    data["currency_totals"].append(t)
            sort_datasets(data, sort)
            metadata = {
                "report_schema_id": "KAJOVOKARTY-EXPORT-1",
                "report_id": report_id,
                "app_build": "0.3.0",
                "exported_at": now(),
                "database_snapshot_id": uid(),
                "selection_mode": "SINGLE_OBJECT"
                if report_id in ("group_evidence", "api_compatibility")
                else "SELECTION"
                if ids is not None
                else "FILTER",
                "selected_ids": ids or [],
                "filters": filters or {},
                "sort": [{"field": f, "direction": d} for f, d in (sort or [])],
                "helper_state": st["status"],
                "helper_context_id": st["context_id"],
                "helper_generation_id": st["published_generation_id"],
                "helper_evidence_epoch": st["evidence_epoch"],
                "selected_helper_graphs": selected_graphs(data, groups, group_ids),
                "row_counts": {k: len(v) for k, v in data.items() if k != "metadata"},
                "currency_policy": "NO_CONVERSION_SEPARATE_CZK_EUR",
                "csv_text_escape": "APOSTROPHE_FOR_UNTRUSTED_FORMULA_PREFIX",
            }
            data["metadata"] = [
                {"key": k, "value_json": v} for k, v in metadata.items()
            ]
        return data


SORT_KEYS = {
    "work_objects": ("object_id",),
    "financial_sources": ("source_id",),
    "cashbook_rows": ("source_id",),
    "bank_rows": ("source_id",),
    "booking_rows": ("source_id",),
    "booking_payouts": ("payout_key",),
    "group_summary": ("group_id",),
    "group_leaves": ("group_id", "source_id"),
    "group_edges": ("group_id", "parent_object_id", "child_position"),
    "source_occurrences": ("source_id", "run_id", "file_id", "sheet", "row_start"),
    "helper_entities": ("context_id", "generation_id", "resource_type", "external_id"),
    "helper_links": ("link_id",),
    "helper_references": (
        "context_id",
        "generation_id",
        "reservation_id",
        "candidate",
        "reference_id",
    ),
    "audit_events": ("timestamp", "event_id"),
    "import_diagnostics": ("created_at", "diagnostic_id"),
    "api_compatibility": ("endpoint_template",),
    "currency_totals": ("dataset", "currency"),
}


def sort_datasets(data, sort):
    main = next(k for k in data if k != "metadata")
    aliases = {
        "id": SORT_KEYS[main][0],
        "date": "date_from" if main == "work_objects" else "local_date",
        "amount": "amount_minor" if main == "work_objects" else "signed_amount_minor",
        "difference": "difference_minor",
        "type": "object_type",
    }

    def key(v):
        return (v is not None, canonical(v) if isinstance(v, (list, dict)) else v)

    for name, rows in data.items():
        if name == "metadata":
            continue
        rows.sort(key=lambda r: tuple(key(r.get(k)) for k in SORT_KEYS[name]))
        if name == main:
            for field, direction in reversed(sort or []):
                field = aliases.get(field, field)
                if field in {x.split(":")[0] for x in SCHEMA[name]}:
                    rows.sort(
                        key=lambda r: key(r.get(field)), reverse=direction == "desc"
                    )


def selected_graphs(data, groups, ids):
    found = {
        (r["context_id"], r["generation_id"]) for r in data.get("helper_entities", [])
    }
    for gid in ids:
        proofs = json.loads(groups[gid]["evidence_json"]).get("helper_provenance") or []
        if isinstance(proofs, dict):
            proofs = [proofs]
        found.update((p["context_id"], p["generation_id"]) for p in proofs)
    return [{"context_id": ctx, "generation_id": gen} for ctx, gen in sorted(found)]


def event_matches(row, filters, date_field):
    from kajovokarty.domain.columns import matches

    if not matches(row, filters.get("column_filters", {})):
        return False
    stamp = row[date_field][:10]
    if filters.get("date_from") and stamp < filters["date_from"]:
        return False
    if filters.get("date_to") and stamp > filters["date_to"]:
        return False
    if filters.get("event_type") and row.get("type") not in choices(
        filters["event_type"]
    ):
        return False
    if filters.get("run_id") and row.get("run_id") not in choices(filters["run_id"]):
        return False
    text = search_normalize(canonical(row))
    return all(t in text for t in search_tokens(filters.get("text", "")))
