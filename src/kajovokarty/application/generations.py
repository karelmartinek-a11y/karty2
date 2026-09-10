"""Canonical generation hash, shared by FULL and DETAIL publication."""

from kajovokarty.domain.core import digest


def graph_hash(c, context, generation):
    entities = []
    links = []
    coverage = []
    for r in c.execute(
        "SELECT h.*,s.content_hash FROM helper_current h JOIN helper_snapshot s ON s.id=h.snapshot_id WHERE h.context_id=? AND h.generation_id=? ORDER BY h.resource_type,h.external_id",
        (context, generation),
    ):
        entities.append(
            {
                k: r[k]
                for k in (
                    "resource_type",
                    "external_id",
                    "content_hash",
                    "active",
                    "complete",
                    "root_observed",
                    "inactive_reason",
                )
            }
        )
    for r in c.execute(
        "SELECT l.*,s.content_hash AS snapshot_hash FROM helper_link l JOIN helper_snapshot s ON s.id=l.snapshot_id WHERE l.context_id=? AND l.generation_id=? ORDER BY l.from_type,l.from_id,l.relation,l.to_type,l.to_id",
        (context, generation),
    ):
        links.append(
            {
                k: r[k]
                for k in (
                    "from_type",
                    "from_id",
                    "relation",
                    "to_type",
                    "to_id",
                    "active",
                    "complete",
                    "snapshot_hash",
                )
            }
        )
    for r in c.execute(
        "SELECT * FROM sync_coverage WHERE context_id=? AND generation_id=? ORDER BY resource_type,range_start,range_end",
        (context, generation),
    ):
        coverage.append(
            {k: r[k] for k in ("resource_type", "range_start", "range_end", "complete")}
        )
    return digest(
        {
            "context_id": context,
            "entities": entities,
            "links": links,
            "coverage": coverage,
        }
    )
