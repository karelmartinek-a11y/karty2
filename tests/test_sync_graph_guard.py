import sqlite3
import pytest
from kajovokarty.application.snapshots import save_snapshot, relation_record
from kajovokarty.domain.core import canonical, now, uid


def staged_graph(db, size=8, problem=None):
    op = db.start_operation("SYNC")
    generation = uid()
    with db.transaction() as c:
        context, revision = c.execute("SELECT context_id,credential_revision FROM helper_state").fetchone()
        c.execute("""INSERT INTO helper_generation
            (id,context_id,credential_revision,kind,state,operation_id,plan_json,created_at)
            VALUES(?,?,?,'FULL','STAGING',?,?,?)""",
            (generation, context, revision, op, canonical({"start": "2026-01-01", "end": "2026-09-11"}), now()))
        extra = 2 if problem in ("orphan_cycle", "inactive_orphan") else 0
        for index in range(size + extra):
            eid = str(index)
            sid = save_snapshot(c, context, op, ("node", eid, "MERGED_ENTITY", "shape", "LOCAL_MERGE", {"id": eid}))
            active = int(not (problem == "inactive_orphan" and index >= size))
            complete = 1
            c.execute("INSERT INTO helper_current VALUES(?,?,?,?,?,1,?,?,?,NULL,'')",
                      (context, generation, "node", eid, sid, active, complete, int(index == 0)))
        edges = [(i, i + 1) for i in range(size - 1)] + [(size - 1, 1)]
        if problem == "orphan_cycle":
            edges += [(size, size + 1), (size + 1, size)]
        for index, (a, b) in enumerate(edges):
            edge = ("node", str(a), "CHILD", "node", str(b))
            sid = save_snapshot(c, context, op, relation_record(edge, "/reservation", {"id": str(b)}))
            c.execute("INSERT INTO helper_link VALUES(?,?,?,?,?,?,?,?,1,?,?)",
                      (uid(), context, generation, *edge, int(not (problem == "incomplete_edge" and index == 0)), sid))
        if problem == "incomplete_target":
            c.execute("UPDATE helper_current SET complete=0 WHERE generation_id=? AND external_id='1'", (generation,))
        for kind in ("invoice", "reservation"):
            if problem == "missing_coverage" and kind == "reservation":
                continue
            c.execute("INSERT INTO sync_coverage VALUES(?,?,?,?,?,?,?,1)",
                      (context, generation, kind, "2026-01-01", "2026-09-11", op, now()))
    return generation


@pytest.mark.parametrize("problem,error", [
    (None, None), ("inactive_orphan", None),
    ("orphan_cycle", "NO_ACTIVE_ROOT_PATH"),
    ("incomplete_edge", "HELPER_EDGE_INCOMPLETE"),
    ("incomplete_target", "HELPER_EDGE_INCOMPLETE"),
    ("missing_coverage", "COVERAGE_INCOMPLETE"),
])
def test_publication_guard_keeps_all_graph_checks(db, problem, error):
    generation = staged_graph(db, problem=problem)
    with db.transaction() as c:
        if error:
            with pytest.raises(sqlite3.IntegrityError, match=error):
                c.execute("UPDATE helper_generation SET state='SEALED' WHERE id=?", (generation,))
        else:
            c.execute("UPDATE helper_generation SET state='SEALED' WHERE id=?", (generation,))
            c.execute("UPDATE helper_generation SET state='PUBLISHED' WHERE id=?", (generation,))


def test_large_graph_does_not_recompute_reachability_per_entity(db):
    generation = staged_graph(db, size=1000)
    with db.transaction() as c:
        ticks = 0
        def budget():
            nonlocal ticks
            ticks += 1
            return int(ticks > 1000)
        # Bound SQLite work, rather than asserting machine-dependent wall time.
        c.set_progress_handler(budget, 1000)
        try:
            c.execute("UPDATE helper_generation SET state='SEALED' WHERE id=?", (generation,))
            c.execute("UPDATE helper_generation SET state='PUBLISHED' WHERE id=?", (generation,))
        finally:
            c.set_progress_handler(None, 0)
