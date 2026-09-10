"""Audited, revision-checked decisions over actual extracted candidates only."""

import json
from kajovokarty.domain.core import canonical, now, require, uid
from kajovokarty.domain.helpers import extract_references, reference_decision
from kajovokarty.application.work import WorkService


class OverrideService:
    def __init__(self, db):
        self.db = db
        self.work = WorkService(db)

    def _current(self, c, context, reservation):
        st = c.execute("SELECT * FROM helper_state").fetchone()
        require(
            st["context_id"] == context and st["status"] != "REFRESHING",
            "STALE_STATE",
            "Rozhodnutí vyžaduje aktuální ověřený kontext.",
        )
        row = c.execute(
            "SELECT s.payload_json FROM helper_current h JOIN helper_snapshot s ON s.id=h.snapshot_id WHERE h.context_id=? AND h.generation_id=? AND h.resource_type='reservation' AND h.external_id=? AND h.active=1 AND h.complete=1",
            (context, st["published_generation_id"], reservation),
        ).fetchone()
        require(row, "STALE_STATE", "Rezervace není aktivní a úplná.")
        payload = json.loads(row[0])
        channel = payload.get("reservation_source") or {}
        ref = extract_references(
            payload.get("reservation_note"),
            channel.get("name") if isinstance(channel, dict) else None,
        )
        previous = c.execute(
            "SELECT * FROM helper_override WHERE context_id=? AND reservation_id=?",
            (context, reservation),
        ).fetchone()
        return ref, dict(previous) if previous else None

    def inspect(self, context, reservation):
        with self.db.connect() as c:
            ref, previous = self._current(c, context, reservation)
            return {
                "reference": ref,
                "override": previous,
                "decision": reference_decision(ref, previous),
            }

    def decide(
        self, context, reservation, action, candidate, expected_revision, candidate_hash
    ):
        require(
            action in ("ACCEPT", "REJECT", "CLEAR"),
            "OVERRIDE_INVALID",
            "Neznámé rozhodnutí.",
        )
        with self.db.transaction() as c:
            ref, previous = self._current(c, context, reservation)
            require(
                (previous["revision"] if previous else 0) == expected_revision
                and ref["candidate_set_hash"] == candidate_hash,
                "STALE_STATE",
                "Podklady rozhodnutí se změnily.",
            )
            require(
                action != "ACCEPT" or candidate in ref["candidates"],
                "OVERRIDE_INVALID",
                "Potvrdit lze jen skutečně nalezené číslo.",
            )
            before = {
                "context_id": context,
                "reservation_id": reservation,
                "value": previous,
            }
            cmd = self.work._new_command(c, "HELPER_OVERRIDE", "MANUAL", {}, {})
            revision = expected_revision + 1
            c.execute(
                "INSERT INTO helper_override VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(context_id,reservation_id) DO UPDATE SET candidate=excluded.candidate,candidate_set_hash=excluded.candidate_set_hash,accepted=excluded.accepted,active=excluded.active,command_id=excluded.command_id,revision=excluded.revision",
                (
                    context,
                    reservation,
                    candidate if action == "ACCEPT" else None,
                    ref["candidate_set_hash"],
                    int(action == "ACCEPT"),
                    int(action != "CLEAR"),
                    cmd,
                    revision,
                ),
            )
            current = dict(
                c.execute(
                    "SELECT * FROM helper_override WHERE context_id=? AND reservation_id=?",
                    (context, reservation),
                ).fetchone()
            )
            after = {**before, "value": current}
            c.execute(
                "UPDATE command SET inverse_json=?,expected_revisions_json=? WHERE id=?",
                (
                    canonical({"before": before, "after": after}),
                    canonical({"override_revision": revision}),
                    cmd,
                ),
            )
            self.db.audit(
                c, "HELPER_OVERRIDE", [context, reservation], before, after, command=cmd
            )
            return cmd

    def compensate(self, c, r, redo):
        inverse = json.loads(r["inverse_json"])
        target = inverse["after" if redo else "before"]
        context = target["context_id"]
        reservation = target["reservation_id"]
        st = c.execute("SELECT * FROM helper_state").fetchone()
        require(
            st["context_id"] == context and st["status"] != "REFRESHING",
            "UNDO_CONFLICT",
            "Historické připojení nelze měnit.",
        )
        row = c.execute(
            "SELECT * FROM helper_override WHERE context_id=? AND reservation_id=?",
            (context, reservation),
        ).fetchone()
        require(
            row
            and row["revision"]
            == json.loads(r["expected_revisions_json"])["override_revision"],
            "UNDO_CONFLICT",
            "Rozhodnutí bylo mezitím změněno.",
        )
        cmd = uid()
        pos = r["history_position"]
        c.execute(
            "INSERT INTO command VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                cmd,
                "REDO" if redo else "UNDO",
                "SYSTEM",
                "{}",
                "{}",
                "{}",
                "{}",
                "{}",
                "{}",
                r["id"],
                "APPLIED",
                now(),
                pos,
                1,
            ),
        )
        value = target["value"]
        revision = row["revision"] + 1
        c.execute(
            "UPDATE helper_override SET candidate=?,candidate_set_hash=?,accepted=?,active=?,command_id=?,revision=? WHERE context_id=? AND reservation_id=?",
            (
                value["candidate"] if value else None,
                value["candidate_set_hash"] if value else row["candidate_set_hash"],
                value["accepted"] if value else 0,
                value["active"] if value else 0,
                cmd,
                revision,
                context,
                reservation,
            ),
        )
        c.execute(
            "UPDATE command SET state=?,expected_revisions_json=? WHERE id=?",
            (
                "APPLIED" if redo else "UNDONE",
                canonical({"override_revision": revision}),
                r["id"],
            ),
        )
        self.db.audit(
            c,
            "REDO" if redo else "UNDO",
            [context, reservation],
            dict(row),
            target,
            command=cmd,
        )
        return cmd
