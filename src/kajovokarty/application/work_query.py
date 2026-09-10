"""Bound, paged SQLite read projection. Financial commands never trust this view."""

import json
from kajovokarty.domain.core import checked, search_tokens, search_normalize, require
from kajovokarty.domain.columns import sql_token, display_value, sort_value

FIELDS = (
    "invoice_code",
    "booking_reference",
    "payout_id",
    "seq_id",
    "terminal_id",
    "authorization_code",
    "arn",
    "variable_symbol",
    "variable_symbol_2",
    "cashbook_number",
)


def choices(value):
    return list(value) if isinstance(value, (list, tuple, set)) else [value]


def query(c, filters, sort, page, page_size):
    f = filters or {}
    tokens = search_tokens(f.get("text", ""))
    c.create_function(
        "normalize", 1, lambda v: search_normalize(str(v or "")), deterministic=True
    )
    # Only groups need a traversal/aggregate. Free sources use indexed direct joins.
    c.execute("DROP TABLE IF EXISTS temp.work_projection")
    c.execute("""CREATE TEMP TABLE work_projection AS
    WITH RECURSIVE roots AS (
      SELECT w.* FROM work_object w WHERE lifecycle='ACTIVE'
      AND NOT EXISTS(SELECT 1 FROM membership m WHERE m.child_id=w.id AND m.active=1)
    ), tree(root,id) AS (
      SELECT id,id FROM roots WHERE type='GROUP'
      UNION ALL SELECT t.root,m.child_id FROM tree t JOIN membership m ON m.parent_id=t.id AND m.active=1
    ), aggregate_rows AS (
      SELECT t.root, count(*) leaf_count,
      sum(CASE WHEN f.kind='CASHBOOK_CARD' THEN f.signed_amount_minor ELSE -f.signed_amount_minor END) difference,
      min(f.local_date) date,max(f.local_date) date_end,
      group_concat(DISTINCT f.kind) kinds, json_group_array(f.id) leaves
      FROM tree t JOIN work_object w ON w.id=t.id AND w.type='SOURCE'
      JOIN financial_source f ON f.id=w.source_id GROUP BY t.root
    )
    SELECT r.*, a.difference, abs(a.difference) amount, a.leaf_count,a.kinds,a.date,a.date_end,
      'G'||substr(r.id,1,10) primary_identifier,g.note description,g.note,a.leaves,
      (a.difference=0) resolved, CASE WHEN a.difference=0 THEN '' ELSE 'OPEN_AGGREGATE' END reason,g.method
      FROM roots r JOIN aggregate_rows a ON a.root=r.id JOIN reconciliation_group g ON g.object_id=r.id
    UNION ALL
    SELECT r.*,CASE WHEN f.kind='CASHBOOK_CARD' THEN f.signed_amount_minor ELSE -f.signed_amount_minor END,
      f.signed_amount_minor,1,f.kind,f.local_date,f.local_date,f.primary_identifier,f.description,'',json_array(f.id),0,'Dosud nepárováno',NULL
      FROM roots r JOIN financial_source f ON f.id=r.source_id WHERE r.type='SOURCE'
    """)
    c.execute("CREATE UNIQUE INDEX temp.projection_id ON work_projection(id)")
    c.execute("""UPDATE work_projection SET reason=(SELECT r.code FROM work_reason r WHERE r.object_id=work_projection.id)
       WHERE type='SOURCE' AND id IN (SELECT object_id FROM work_reason WHERE domain_revision=(SELECT revision FROM domain_clock) AND helper_revision=(SELECT revision FROM helper_state) AND settings_revision=(SELECT coalesce(sum(revision),0) FROM setting))""")
    clauses, params = [], []
    status = f.get("status", "unresolved")
    if status != "all":
        vals = choices(status)
        clauses.append("resolved IN (" + ",".join("?" for _ in vals) + ")")
        params.extend(int(v == "resolved") for v in vals)
    for key in ("currency", "type", "reason"):
        if f.get(key):
            vals = choices(f[key])
            clauses.append(key + " IN (" + ",".join("?" for _ in vals) + ")")
            params.extend(vals)
    if f.get("kind"):
        vals = choices(f["kind"])
        join = " AND " if f.get("kind_mode") == "all" else " OR "
        clauses.append("(" + join.join("instr(kinds,?)>0" for _ in vals) + ")")
        params.extend(vals)
    for key, field, op in (
        ("date_from", "date_end", ">="),
        ("date_to", "date", "<="),
        ("amount", "amount", "="),
        ("amount_min", "amount", ">="),
        ("amount_max", "amount", "<="),
        ("difference", "difference", "="),
    ):
        if f.get(key) is not None and f[key] != "":
            vals = choices(f[key])
            clauses.append("(" + " OR ".join(field + op + "?" for _ in vals) + ")")
            params.extend(vals)
    if f.get("side"):
        vals = choices(f["side"])
        clauses.append(
            "(CASE WHEN difference>0 THEN 'NEED' WHEN difference<0 THEN 'SURPLUS' ELSE 'BALANCED' END) IN ("
            + ",".join("?" for _ in vals)
            + ")"
        )
        params.extend(vals)
    for key in FIELDS:
        if f.get(key):
            vals = [search_normalize(str(v)) for v in choices(f[key])]
            clauses.append(
                "EXISTS(SELECT 1 FROM json_each(p.leaves) leaf JOIN financial_source s ON s.id=leaf.value WHERE ("
                + " OR ".join(
                    "substr(normalize(json_extract(s.canonical_json,'$."
                    + key
                    + "')),1,length(?))=?"
                    for _ in vals
                )
                + "))"
            )
            for v in vals:
                params.extend((v, v))
    for token in tokens:
        clauses.append(
            "((instr(p.id,?)>0 OR (p.type='GROUP' AND instr(normalize(p.note),?)>0)) OR EXISTS(SELECT 1 FROM json_each(p.leaves) leaf JOIN source_search s ON s.source_id=leaf.value WHERE instr(s.local_search_text,?)>0))"
        )
        params.extend((token, token, token))
    allowed = {
        "id",
        "type",
        "currency",
        "revision",
        "difference",
        "amount",
        "leaf_count",
        "date",
        "date_end",
        "primary_identifier",
        "description",
        "note",
        "resolved",
        "reason",
        "method",
        "kinds",
    }
    columns = f.get("column_filters", {})
    require(
        isinstance(columns, dict) and all(k in allowed for k in columns),
        "FILTER_INVALID",
        "Neznámý sloupec filtru.",
    )
    c.create_function("column_token", 2, sql_token, deterministic=True)
    facet = f.get("_facet")
    for key, values in columns.items():
        require(
            isinstance(values, list) and all(isinstance(v, str) for v in values),
            "FILTER_INVALID",
            "Neplatné hodnoty filtru.",
        )
        if key == facet:
            continue
        clauses.append(
            "column_token('"
            + key
            + "',p."
            + key
            + ") IN (SELECT value FROM json_each(?))"
        )
        params.append(json.dumps(values))
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    if facet is not None:
        require(facet in allowed, "FILTER_INVALID", "Neznámý sloupec.")
        values = [
            r[0]
            for r in c.execute(
                "SELECT DISTINCT column_token('"
                + facet
                + "',p."
                + facet
                + ") FROM work_projection p"
                + where,
                params,
            )
        ]
        return {
            "facets": [
                (display_value(facet, json.loads(t)) or "(Prázdné)", t)
                for t in sorted(values, key=lambda t: sort_value(json.loads(t)))
            ]
        }
    order = []
    for field, direction in sort or []:
        if field in allowed:
            order.append("(" + field + " IS NULL OR " + field + "='') ASC")
            order.append(field + (" DESC" if direction == "desc" else " ASC"))
    order.append("id ASC")
    ordered = " ORDER BY " + ",".join(order)
    ids = [
        r[0]
        for r in c.execute("SELECT id FROM work_projection p" + where + ordered, params)
    ]
    sql = "SELECT * FROM work_projection p" + where + ordered
    args = list(params)
    if page_size:
        page = min(page, max(0, (len(ids) - 1) // page_size))
        sql += " LIMIT ? OFFSET ?"
        args.extend((page_size, page * page_size))
    rows = []
    for row in c.execute(sql, args):
        r = dict(row)
        r["leaves"] = json.loads(r["leaves"])
        r["kinds"] = sorted(r["kinds"].split(","))
        r["resolved"] = bool(r["resolved"])
        checked(r["difference"])
        r["matched_leaves"] = []
        if tokens:
            for start in range(0, len(r["leaves"]), 400):
                leaves = r["leaves"][start : start + 400]
                marks = ",".join("?" for _ in leaves)
                for source in c.execute(
                    "SELECT * FROM source_search WHERE source_id IN (" + marks + ")",
                    leaves,
                ):
                    if any(t in source["local_search_text"] for t in tokens):
                        r["matched_leaves"].append(source["source_id"])
        rows.append(r)
    kpi = {cur: {"need": 0, "surplus": 0, "roots": 0} for cur in ("CZK", "EUR")}
    for r in c.execute(
        "SELECT currency,sum(max(difference,0)) need,sum(max(-difference,0)) surplus,count(*) roots FROM work_projection WHERE resolved=0 GROUP BY currency"
    ):
        kpi[r["currency"]] = {
            "need": checked(r["need"]),
            "surplus": checked(r["surplus"]),
            "roots": r["roots"],
        }
    totals = {
        r["currency"]: checked(r["total"])
        for r in c.execute(
            "SELECT p.currency,sum(p.difference) total FROM work_projection p JOIN work_selection s ON s.object_id=p.id GROUP BY p.currency"
        )
    }
    stale = [
        r[0]
        for r in c.execute(
            "SELECT s.object_id FROM work_selection s LEFT JOIN work_projection p ON p.id=s.object_id WHERE p.id IS NULL OR p.revision!=s.expected_revision"
        )
    ]
    return {
        "rows": rows,
        "page": page,
        "ids": ids,
        "total": len(ids),
        "kpi": kpi,
        "selection_totals": totals,
        "selection_stale": stale,
    }
