"""Explicit graph scopes and recursive evidence closure for helper reports."""

import json
from kajovokarty.domain.core import require, search_tokens
from kajovokarty.domain.helpers import extract_references, reference_decision
from kajovokarty.domain.columns import matches


def build_helpers(c, st, ids, filters):
    graphs = filters.get("helper_graphs") or [
        {"context_id": st["context_id"], "generation_id": st["published_generation_id"]}
    ]
    historical = bool(filters.get("include_history"))
    result = {
        key: [] for key in ("helper_entities", "helper_links", "helper_references")
    }
    for graph in graphs:
        ctx, gen = graph["context_id"], graph["generation_id"]
        current = (ctx, gen) == (st["context_id"], st["published_generation_id"])
        require(
            current or historical,
            "EXPORT_INVALID",
            "Historický graf vyžaduje explicitní historický rozsah.",
        )
        if gen is None:
            continue
        generation = c.execute(
            "SELECT * FROM helper_generation WHERE context_id=? AND id=? AND state='PUBLISHED'",
            (ctx, gen),
        ).fetchone()
        require(generation, "EXPORT_INVALID", "Zvolený publikovaný graf neexistuje.")
        entities = {}
        for r in c.execute(
            "SELECT h.*,s.projection_kind,s.request_shape_hash,s.content_hash,s.fetched_at,s.payload_json FROM helper_current h JOIN helper_snapshot s ON s.id=h.snapshot_id WHERE h.context_id=? AND h.generation_id=?",
            (ctx, gen),
        ):
            if not r["active"] and not historical:
                continue
            entities[(r["resource_type"], r["external_id"])] = dict(r)
        edges = []
        adjacency = {}
        for r in c.execute(
            "SELECT l.*,s.content_hash,s.fetched_at FROM helper_link l JOIN helper_snapshot s ON s.id=l.snapshot_id WHERE l.context_id=? AND l.generation_id=?",
            (ctx, gen),
        ):
            if not r["active"] and not historical:
                continue
            a, b = (r["from_type"], r["from_id"]), (r["to_type"], r["to_id"])
            if a not in entities or b not in entities:
                continue
            edges.append(dict(r))
            adjacency.setdefault(a, set()).add(b)
            adjacency.setdefault(b, set()).add(a)
        tokens = search_tokens(filters.get("text", ""))
        seeds = set()
        for key, e in entities.items():
            identity = {
                "context_id": ctx,
                "generation_id": gen,
                "resource_type": key[0],
                "external_id": key[1],
            }
            if ids is not None:
                if (
                    identity in ids
                    or ":".join((ctx, gen, *key)) in ids
                    or (key[1] in ids and len(graphs) == 1)
                ):
                    seeds.add(key)
            elif (
                (not filters.get("resource_type") or key[0] in filters["resource_type"])
                and all(t in e["local_search_text"] for t in tokens)
                and matches(e, filters.get("column_filters", {}))
            ):
                seeds.add(key)
        selected = set()
        pending = list(seeds)
        while pending:
            key = pending.pop()
            if key in selected:
                continue
            selected.add(key)
            pending.extend(adjacency.get(key, ()))
        for key in sorted(selected):
            e = entities[key]
            result["helper_entities"].append(
                {
                    **e,
                    "usable_for_new_auto": current
                    and st["status"] == "READY"
                    and bool(e["active"] and e["complete"]),
                    "helper_state": st["status"] if current else "HISTORICAL",
                    "helper_state_revision": st["revision"],
                    "evidence_epoch": generation["evidence_epoch"],
                }
            )
        for r in edges:
            if (r["from_type"], r["from_id"]) in selected and (
                r["to_type"],
                r["to_id"],
            ) in selected:
                result["helper_links"].append(
                    {
                        **r,
                        "link_id": r["id"],
                        "snapshot_hash": r["content_hash"],
                        "helper_state": st["status"] if current else "HISTORICAL",
                        "usable_for_new_auto": current
                        and st["status"] == "READY"
                        and bool(r["active"] and r["complete"]),
                    }
                )
        for r in c.execute(
            "SELECT * FROM helper_reference WHERE context_id=? AND generation_id=?",
            (ctx, gen),
        ):
            key = ("reservation", r["reservation_id"])
            if key not in selected:
                continue
            entity = entities[key]
            p = json.loads(entity["payload_json"])
            channel = p.get("reservation_source") or {}
            ref = extract_references(p.get("reservation_note"), channel.get("name"))
            row = c.execute(
                "SELECT * FROM helper_override WHERE context_id=? AND reservation_id=?",
                (ctx, r["reservation_id"]),
            ).fetchone()
            override = dict(row) if row else None
            decision = reference_decision(
                ref,
                override,
                active=current and bool(entity["active"] and entity["complete"]),
            )
            result["helper_references"].append(
                {
                    **dict(r),
                    **decision,
                    "reference_id": r["id"],
                    "override_candidate": override["candidate"] if override else None,
                    "override_accepted": bool(override["accepted"])
                    if override
                    else None,
                    "override_active": bool(override and override["active"]),
                    "helper_state": st["status"] if current else "HISTORICAL",
                }
            )
    return result
