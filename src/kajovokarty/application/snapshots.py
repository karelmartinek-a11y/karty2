"""Immutable raw evidence and per-reception provenance, shared by FULL and DETAIL."""

from kajovokarty.domain.core import canonical, digest, now, uid
from kajovokarty.infrastructure.betterhotel import request_shape


def save_snapshot(c, context, operation, record):
    kind, eid, projection, shape, template, payload = record
    h = digest(payload)
    found = c.execute(
        "SELECT id FROM helper_snapshot WHERE context_id=? AND resource_type=? AND external_id=? AND projection_kind=? AND request_shape_hash=? AND content_hash=?",
        (context, kind, eid, projection, shape, h),
    ).fetchone()
    if found:
        return found[0]
    sid = uid()
    c.execute(
        "INSERT INTO helper_snapshot VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (
            sid,
            context,
            kind,
            eid,
            projection,
            shape,
            template,
            canonical(payload),
            h,
            now(),
            operation,
        ),
    )
    return sid


def observe(c, context, generation, operation, record, block, index):
    sid = save_snapshot(c, context, operation, record)
    origin = {
        "LIST_ENTITY": "LIST",
        "DETAIL_ENTITY": "DETAIL",
        "RELATION_EDGE": "RELATION",
        "EMBEDDED_ENTITY": "EMBEDDED",
    }[record[2]]
    c.execute(
        "INSERT INTO helper_observation VALUES(?,?,?,?,?,?,?,?,?)",
        (uid(), context, generation, operation, block, index, sid, now(), origin),
    )
    return sid


def relation_record(edge, template, raw):
    # The identity identifies the exact edge; the payload is the received evidence.
    return (
        "relation_edge",
        digest(edge),
        "RELATION_EDGE",
        request_shape(template),
        template,
        raw,
    )
