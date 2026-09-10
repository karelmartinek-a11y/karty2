"""One transactional command boundary for all financial tree mutations."""

from __future__ import annotations
import json
from contextlib import nullcontext
from kajovokarty.domain.core import (
    canonical,
    checked,
    now,
    require,
    uid,
)


class WorkService:
    def __init__(self, db):
        self.db = db

    def _graph(self, c, roots=None):
        if roots is not None:
            return self._subgraph(c, roots)
        objects = {r["id"]: dict(r) for r in c.execute("SELECT * FROM work_object")}
        groups = {
            r["object_id"]: dict(r)
            for r in c.execute("SELECT * FROM reconciliation_group")
        }
        children = {}
        parents = {}
        for r in c.execute(
            "SELECT * FROM membership WHERE active=1 ORDER BY created_at,id"
        ):
            children.setdefault(r["parent_id"], []).append(r["child_id"])
            parents[r["child_id"]] = r["parent_id"]
        sources = {
            r["id"]: dict(r) for r in c.execute("SELECT * FROM financial_source")
        }
        return objects, groups, children, parents, sources

    def _subgraph(self, c, roots):
        objects, groups, children, parents, sources = {}, {}, {}, {}, {}
        pending = list(dict.fromkeys(roots))
        seen = set()
        while pending:
            batch = [i for i in pending[:400] if i not in seen]
            pending = pending[400:]
            if not batch:
                continue
            seen.update(batch)
            marks = ",".join("?" for _ in batch)
            objects.update(
                {
                    r["id"]: dict(r)
                    for r in c.execute(
                        "SELECT * FROM work_object WHERE id IN (" + marks + ")", batch
                    )
                }
            )
            groups.update(
                {
                    r["object_id"]: dict(r)
                    for r in c.execute(
                        "SELECT * FROM reconciliation_group WHERE object_id IN ("
                        + marks
                        + ")",
                        batch,
                    )
                }
            )
            sources.update(
                {
                    r["id"]: dict(r)
                    for r in c.execute(
                        "SELECT * FROM financial_source WHERE id IN (" + marks + ")",
                        batch,
                    )
                }
            )
            for row in c.execute(
                "SELECT child_id,parent_id FROM membership WHERE active=1 AND child_id IN ("
                + marks
                + ")",
                batch,
            ):
                parents[row["child_id"]] = row["parent_id"]
            for row in c.execute(
                "SELECT parent_id,child_id FROM membership WHERE active=1 AND parent_id IN ("
                + marks
                + ") ORDER BY created_at,id",
                batch,
            ):
                children.setdefault(row["parent_id"], []).append(row["child_id"])
                pending.append(row["child_id"])
        return objects, groups, children, parents, sources

    def _leaves(self, node, objects, children):
        stack = [node]
        seen = set()
        leaves = []
        while stack:
            n = stack.pop()
            require(n not in seen, "CYCLE_DETECTED", "Strom obsahuje opakovaný objekt.")
            seen.add(n)
            if objects[n]["type"] == "SOURCE":
                leaves.append(n)
            else:
                stack.extend(reversed(children.get(n, [])))
        return leaves

    def _difference(self, leaves, sources):
        return checked(
            sum(
                sources[n]["signed_amount_minor"]
                * (1 if sources[n]["kind"] == "CASHBOOK_CARD" else -1)
                for n in leaves
            )
        )

    def _snapshot(self, c, ids):
        result = {}
        for i in sorted(set(ids)):
            o = c.execute("SELECT * FROM work_object WHERE id=?", (i,)).fetchone()
            if not o:
                result[i] = None
                continue
            g = c.execute(
                "SELECT * FROM reconciliation_group WHERE object_id=?", (i,)
            ).fetchone()
            result[i] = {
                "object": dict(o),
                "group": dict(g) if g else None,
                "children": [
                    r[0]
                    for r in c.execute(
                        "SELECT child_id FROM membership WHERE parent_id=? AND active=1 ORDER BY created_at,id",
                        (i,),
                    )
                ],
            }
        return result

    def _supp(self, c, fingerprints):
        return {
            f: (
                dict(r)
                if (
                    r := c.execute(
                        "SELECT * FROM auto_suppression WHERE fingerprint=?", (f,)
                    ).fetchone()
                )
                else None
            )
            for f in fingerprints
        }

    def _new_command(self, c, kind, method, before, supp_before):
        self.db.invalidate_redo(c)
        cmd = uid()
        pos = c.execute(
            "SELECT coalesce(max(history_position),0)+1 FROM command"
        ).fetchone()[0]
        c.execute(
            "INSERT INTO command VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                cmd,
                kind,
                method,
                canonical(before),
                "{}",
                canonical(supp_before),
                "{}",
                "{}",
                "{}",
                None,
                "APPLIED",
                now(),
                pos,
                1,
            ),
        )
        return cmd

    def _finish(self, c, cmd, kind, before, after, supp_before, supp_after):
        c.execute(
            "UPDATE command SET after_json=?,suppression_after_json=?,expected_revisions_json=? WHERE id=?",
            (
                canonical(after),
                canonical(supp_after),
                canonical(
                    {
                        "objects": {
                            i: s["object"]["revision"] if s else None
                            for i, s in after.items()
                        },
                        "suppression": {
                            f: s["revision"] if s else None
                            for f, s in supp_after.items()
                        },
                    }
                ),
                cmd,
            ),
        )
        self.db.audit(c, kind, after.keys(), before, after, "MANUAL", cmd)

    def _check(self, objects, ids, revisions):
        require(
            len(ids) == len(set(ids)),
            "ALREADY_OWNED",
            "Výběr obsahuje opakovaný objekt.",
        )
        for i in ids:
            require(
                i in objects and objects[i]["lifecycle"] == "ACTIVE",
                "STALE_STATE",
                "Objekt již není aktivní.",
            )
            require(
                revisions.get(i) == objects[i]["revision"],
                "STALE_STATE",
                "Výběr je zastaralý; obnovte náhled.",
            )

    def create_group(
        self,
        ids,
        revisions,
        note="",
        require_zero=False,
        method="MANUAL",
        evidence=None,
    ):
        require(len(ids) >= 2, "GROUP_INVALID", "Vyberte alespoň dva různé kořeny.")
        require(
            len(note) <= 10000, "NOTE_INVALID", "Poznámka smí mít nejvýše 10 000 znaků."
        )
        with self.db.transaction() as c:
            objects, groups, children, parents, sources = self._graph(c, ids)
            self._check(objects, ids, revisions)
            require(
                all(i not in parents for i in ids),
                "ALREADY_OWNED",
                "Vybraný objekt již má rodiče.",
            )
            require(
                len({objects[i]["currency"] for i in ids}) == 1,
                "MIXED_CURRENCY",
                "Nelze spojit CZK a EUR.",
            )
            leaves = []
            for i in ids:
                ls = self._leaves(i, objects, children)
                require(
                    self._difference(ls, sources) != 0,
                    "NONZERO_DIFFERENCE",
                    "Vyřízená skupina se nesmí znovu seskupit.",
                )
                leaves.extend(ls)
            diff = self._difference(leaves, sources)
            require(
                not require_zero or diff == 0,
                "NONZERO_DIFFERENCE",
                "Výběr není přesně vyrovnaný.",
            )
            gid = uid()
            before = self._snapshot(c, [gid, *ids])
            finger = (evidence or {}).get("fingerprint")
            sb = self._supp(c, [finger]) if finger else {}
            cmd = self._new_command(c, "CREATE_GROUP", method, before, sb)
            c.execute(
                "INSERT INTO work_object VALUES(?,'GROUP',NULL,?,'ACTIVE',1)",
                (gid, objects[ids[0]]["currency"]),
            )
            c.execute(
                "INSERT INTO reconciliation_group VALUES(?,?,?,?,?,?)",
                (gid, method, note, now(), now(), canonical(evidence or {})),
            )
            for i in ids:
                c.execute(
                    "INSERT INTO membership VALUES(?,?,?,1,?,NULL,?,NULL)",
                    (uid(), gid, i, cmd, now()),
                )
                c.execute("UPDATE work_object SET revision=revision+1 WHERE id=?", (i,))
                c.execute("DELETE FROM work_selection WHERE object_id=?", (i,))
            after = self._snapshot(c, [gid, *ids])
            self._finish(c, cmd, "CREATE_GROUP", before, after, sb, self._supp(c, sb))
            return {"id": gid, "difference": diff, "command_id": cmd}

    def add_to_group(self, gid, ids, revisions):
        require(ids and gid not in ids, "GROUP_INVALID", "Vyberte další kořeny.")
        with self.db.transaction() as c:
            objects, groups, children, parents, sources = self._graph(c, [gid, *ids])
            allids = [gid, *ids]
            self._check(objects, allids, revisions)
            require(
                gid in groups and all(i not in parents for i in allids),
                "ALREADY_OWNED",
                "Cílem musí být otevřená kořenová skupina.",
            )
            require(
                len({objects[i]["currency"] for i in allids}) == 1,
                "MIXED_CURRENCY",
                "Nelze spojit měny.",
            )
            for i in allids:
                require(
                    self._difference(self._leaves(i, objects, children), sources) != 0,
                    "NONZERO_DIFFERENCE",
                    "Vyřízenou skupinu nejprve rozložte.",
                )
            checked(
                sum(
                    self._difference(self._leaves(i, objects, children), sources)
                    for i in allids
                )
            )
            before = self._snapshot(c, allids)
            cmd = self._new_command(c, "ADD_TO_GROUP", "MANUAL", before, {})
            for i in ids:
                c.execute(
                    "INSERT INTO membership VALUES(?,?,?,1,?,NULL,?,NULL)",
                    (uid(), gid, i, cmd, now()),
                )
            for i in allids:
                c.execute("UPDATE work_object SET revision=revision+1 WHERE id=?", (i,))
                c.execute("DELETE FROM work_selection WHERE object_id=?", (i,))
            self._finish(
                c, cmd, "ADD_TO_GROUP", before, self._snapshot(c, allids), {}, {}
            )
            return cmd

    def dissolve(self, gid, revision):
        with self.db.transaction() as c:
            objects, groups, children, parents, sources = self._graph(c, [gid])
            self._check(objects, [gid], {gid: revision})
            require(
                gid in groups and gid not in parents,
                "ALREADY_OWNED",
                "Vnořenou skupinu nejprve odpojte od rodiče.",
            )
            ids = [gid, *children[gid]]
            before = self._snapshot(c, ids)
            e = json.loads(groups[gid]["evidence_json"])
            finger = e.get("fingerprint")
            fingers = [finger] if finger else []
            sb = self._supp(c, fingers)
            cmd = self._new_command(c, "DISSOLVE_GROUP", "MANUAL", before, sb)
            self._archive(c, gid, cmd)
            c.execute(
                "UPDATE membership SET active=0,ended_by_command=?,ended_at=? WHERE parent_id=? AND active=1",
                (cmd, now(), gid),
            )
            c.execute("UPDATE work_object SET lifecycle='DISSOLVED' WHERE id=?", (gid,))
            for i in ids:
                c.execute("UPDATE work_object SET revision=revision+1 WHERE id=?", (i,))
                c.execute("DELETE FROM work_selection WHERE object_id=?", (i,))
            if finger:
                self._set_supp(c, finger, True, cmd)
            self._finish(
                c,
                cmd,
                "DISSOLVE_GROUP",
                before,
                self._snapshot(c, ids),
                sb,
                self._supp(c, fingers),
            )
            return cmd

    def unlink_parent(self, child, parent_revision):
        with self.db.connect() as c:
            r = c.execute(
                "SELECT parent_id FROM membership WHERE child_id=? AND active=1",
                (child,),
            ).fetchone()
        require(r, "ALREADY_OWNED", "Objekt nemá rodiče.")
        return self.dissolve(r[0], parent_revision)

    def edit_note(self, gid, revision, note):
        require(
            len(note) <= 10000, "NOTE_INVALID", "Poznámka smí mít nejvýše 10 000 znaků."
        )
        with self.db.transaction() as c:
            o = c.execute(
                "SELECT * FROM work_object WHERE id=? AND type='GROUP'", (gid,)
            ).fetchone()
            require(
                o and o["lifecycle"] == "ACTIVE" and o["revision"] == revision,
                "STALE_STATE",
                "Skupina se změnila.",
            )
            before = self._snapshot(c, [gid])
            cmd = self._new_command(c, "EDIT_NOTE", "MANUAL", before, {})
            c.execute(
                "UPDATE reconciliation_group SET note=?,updated_at=? WHERE object_id=?",
                (note, now(), gid),
            )
            c.execute("UPDATE work_object SET revision=revision+1 WHERE id=?", (gid,))
            self._finish(c, cmd, "EDIT_NOTE", before, self._snapshot(c, [gid]), {}, {})
            return cmd

    def _archive(self, c, gid, cmd):
        objects, groups, children, parents, sources = self._graph(c, [gid])
        leaves = self._leaves(gid, objects, children)
        stack = [gid]
        edges = []
        seen = set()
        while stack:
            parent = stack.pop()
            if parent in seen:
                continue
            seen.add(parent)
            for pos, r in enumerate(
                c.execute(
                    "SELECT * FROM membership WHERE parent_id=? AND active=1 ORDER BY created_at,id",
                    (parent,),
                ),
                1,
            ):
                edge = dict(r)
                edge["child_position"] = pos
                edges.append(edge)
                if objects[r["child_id"]]["type"] == "GROUP":
                    stack.append(r["child_id"])
        snapshot = {
            "children": children.get(gid, []),
            "leaves": [sources[i] for i in leaves],
            "edges": edges,
            "difference": self._difference(leaves, sources),
        }
        c.execute(
            "INSERT INTO group_history VALUES(?,?,?,?,?)",
            (uid(), gid, cmd, canonical(snapshot), now()),
        )

    def _set_supp(self, c, finger, active, cmd):
        c.execute(
            "INSERT INTO auto_suppression VALUES(?,?,?,1,?,?) ON CONFLICT(fingerprint) DO UPDATE SET active=excluded.active,command_id=excluded.command_id,revision=auto_suppression.revision+1,updated_at=excluded.updated_at",
            (finger, cmd, int(active), now(), now()),
        )

    def allow_auto(self, finger):
        with self.db.transaction() as c:
            sb = self._supp(c, [finger])
            require(
                sb[finger] and sb[finger]["active"],
                "STALE_STATE",
                "Potlačení již není aktivní.",
            )
            cmd = self._new_command(c, "ALLOW_AUTO", "MANUAL", {}, sb)
            self._set_supp(c, finger, False, cmd)
            self._finish(c, cmd, "ALLOW_AUTO", {}, {}, sb, self._supp(c, [finger]))
            return cmd

    def history(self):
        with self.db.connect() as c:
            return [
                dict(r)
                for r in c.execute(
                    "SELECT id,type,state,created_at FROM command WHERE compensates_id IS NULL ORDER BY history_position DESC"
                )
            ]

    def undo(self, command_id=None, redo=False):
        with self.db.transaction() as c:
            if command_id:
                r = c.execute(
                    "SELECT * FROM command WHERE id=?", (command_id,)
                ).fetchone()
            else:
                r = c.execute(
                    "SELECT * FROM command WHERE compensates_id IS NULL AND state=? AND redo_valid=1 ORDER BY history_position "
                    + ("ASC" if redo else "DESC")
                    + " LIMIT 1",
                    ("UNDONE" if redo else "APPLIED",),
                ).fetchone()
            require(
                r is not None
                and r["state"] == ("UNDONE" if redo else "APPLIED")
                and r["redo_valid"],
                "UNDO_CONFLICT",
                "Není dostupný platný příkaz.",
            )
            if r["type"] == "HELPER_OVERRIDE":
                from kajovokarty.application.overrides import OverrideService

                return OverrideService(self.db).compensate(c, r, redo)
            expected = json.loads(r["expected_revisions_json"])
            target = json.loads(r["after_json" if redo else "before_json"])
            current = self._snapshot(c, target)
            for i, revision in expected.get("objects", {}).items():
                require(
                    current.get(i) and current[i]["object"]["revision"] == revision,
                    "UNDO_CONFLICT",
                    "Dotčený objekt byl mezitím změněn.",
                )
            for f, revision in expected.get("suppression", {}).items():
                actual = self._supp(c, [f])[f]
                require(
                    (actual["revision"] if actual else None) == revision,
                    "UNDO_CONFLICT",
                    "Potlačení bylo mezitím změněno.",
                )
            cmd = uid()
            c.execute(
                "INSERT INTO command VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    cmd,
                    "REDO" if redo else "UNDO",
                    "SYSTEM",
                    canonical(current),
                    canonical(target),
                    "{}",
                    "{}",
                    "{}",
                    "{}",
                    r["id"],
                    "APPLIED",
                    now(),
                    r["history_position"],
                    1,
                ),
            )
            for i, s in target.items():
                if (
                    s is None
                    and current[i]
                    and current[i]["group"]
                    and current[i]["object"]["lifecycle"] == "ACTIVE"
                ):
                    self._archive(c, i, cmd)
                if s is None or s["group"]:
                    c.execute(
                        "UPDATE membership SET active=0,ended_by_command=?,ended_at=? WHERE parent_id=? AND active=1",
                        (cmd, now(), i),
                    )
            for i, s in target.items():
                lifecycle = s["object"]["lifecycle"] if s else "DISSOLVED"
                c.execute(
                    "UPDATE work_object SET lifecycle=?,revision=revision+1 WHERE id=?",
                    (lifecycle, i),
                )
                if s and s["group"]:
                    c.execute(
                        "UPDATE reconciliation_group SET note=?,method=?,evidence_json=?,updated_at=? WHERE object_id=?",
                        (
                            s["group"]["note"],
                            s["group"]["method"],
                            s["group"]["evidence_json"],
                            now(),
                            i,
                        ),
                    )
            for i, s in target.items():
                if s and s["group"]:
                    for child in s["children"]:
                        require(
                            not c.execute(
                                "SELECT 1 FROM membership WHERE child_id=? AND active=1",
                                (child,),
                            ).fetchone(),
                            "UNDO_CONFLICT",
                            "Dítě již patří jiné skupině.",
                        )
                        c.execute(
                            "INSERT INTO membership VALUES(?,?,?,1,?,NULL,?,NULL)",
                            (uid(), i, child, cmd, now()),
                        )
            supp = json.loads(
                r["suppression_after_json" if redo else "suppression_before_json"]
            )
            if r["type"] == "CREATE_GROUP" and r["method"] == "AUTO":
                after = json.loads(r["after_json"])
                finger = next(
                    (
                        json.loads(s["group"]["evidence_json"]).get("fingerprint")
                        for s in after.values()
                        if s and s["group"]
                    ),
                    None,
                )
                if finger:
                    supp[finger] = {"active": not redo}
            for f, s in supp.items():
                self._set_supp(c, f, bool(s and s["active"]), cmd)
            after = self._snapshot(c, target)
            sa = self._supp(c, supp)
            c.execute(
                "UPDATE command SET state=?,expected_revisions_json=? WHERE id=?",
                (
                    "APPLIED" if redo else "UNDONE",
                    canonical(
                        {
                            "objects": {
                                i: s["object"]["revision"] for i, s in after.items()
                            },
                            "suppression": {f: s["revision"] for f, s in sa.items()},
                        }
                    ),
                    r["id"],
                ),
            )
            # The next adjacent history item may target the same object. Its semantic
            # state is restored, while revisions remain strictly monotonic.
            self._rebase_adjacent(c, r, redo)
            self.db.audit(
                c,
                "REDO" if redo else "UNDO",
                target.keys(),
                current,
                after,
                command=cmd,
            )
            return cmd

    def _rebase_adjacent(self, c, r, redo):
        # Compensation changes revisions; advance the adjacent command only when
        # its entire expected semantic state has actually been restored.
        neighbor = c.execute(
            "SELECT * FROM command WHERE compensates_id IS NULL AND redo_valid=1 AND state=? AND history_position "
            + (">" if redo else "<")
            + " ? ORDER BY history_position "
            + ("ASC" if redo else "DESC")
            + " LIMIT 1",
            ("UNDONE" if redo else "APPLIED", r["history_position"]),
        ).fetchone()
        if not neighbor or neighbor["type"] == "HELPER_OVERRIDE":
            return
        desired = json.loads(neighbor["before_json" if redo else "after_json"])
        actual = self._snapshot(c, desired)

        def semantic(s):
            if s is None:
                return None
            if s["object"]["lifecycle"] == "DISSOLVED":
                return None
            s = json.loads(canonical(s))
            s["object"].pop("revision", None)
            if s["group"]:
                s["group"].pop("updated_at", None)
            return s

        if any(semantic(desired[i]) != semantic(actual[i]) for i in desired):
            return
        expected = json.loads(neighbor["expected_revisions_json"])
        expected["objects"] = {
            i: s["object"]["revision"] if s else None for i, s in actual.items()
        }
        c.execute(
            "UPDATE command SET expected_revisions_json=? WHERE id=?",
            (canonical(expected), neighbor["id"]),
        )

    def selection(self):
        with self.db.connect() as c:
            return {
                r["object_id"]: r["expected_revision"]
                for r in c.execute("SELECT * FROM work_selection ORDER BY position")
            }

    def deselect(self, ids):
        with self.db.transaction() as c:
            c.executemany(
                "DELETE FROM work_selection WHERE object_id=?", [(i,) for i in ids]
            )

    def select(self, ids, clear=False):
        with self.db.transaction() as c:
            if clear:
                c.execute("DELETE FROM work_selection")
            objects, groups, children, parents, sources = self._graph(c, ids)
            pos = c.execute(
                "SELECT coalesce(max(position),0) FROM work_selection"
            ).fetchone()[0]
            for i in ids:
                require(
                    i in objects
                    and objects[i]["lifecycle"] == "ACTIVE"
                    and i not in parents
                    and self._difference(self._leaves(i, objects, children), sources)
                    != 0,
                    "SELECTION_INVALID",
                    "Vybrat lze jen nevyřízený finanční kořen.",
                )
                pos += 1
                c.execute(
                    "INSERT OR IGNORE INTO work_selection VALUES(?,?,?)",
                    (i, objects[i]["revision"], pos),
                )

    def query(self, filters=None, sort=None, page=0, page_size=500, _connection=None):
        from kajovokarty.application.work_query import query

        with (
            nullcontext(_connection)
            if _connection is not None
            else self.db.connect() as c
        ):
            if _connection is None:
                c.execute("BEGIN")
            return query(c, filters, sort, page, page_size)

    def counterparts(self, object_id, revision):
        with self.db.connect() as c:
            c.execute("BEGIN")
            rows = self.query({"status": "unresolved"}, page_size=0, _connection=c)[
                "rows"
            ]
            anchor = next((r for r in rows if r["id"] == object_id), None)
            require(
                anchor and anchor["revision"] == revision,
                "STALE_STATE",
                "Výchozí objekt se změnil. Obnovte pohled.",
            )
            result = []
            for r in rows:
                if r["id"] == object_id or r["currency"] != anchor["currency"]:
                    continue
                difference = anchor["difference"] + r["difference"]
                result.append(
                    {
                        **r,
                        "pair_difference": difference
                        if abs(difference) <= 9000000000000000
                        else None,
                        "reason": "Přesná nula při spojení těchto dvou kořenů"
                        if difference == 0
                        else "Pro vyrovnání je třeba další položka",
                    }
                )
            result.sort(
                key=lambda r: (
                    r["pair_difference"] is None,
                    abs(r["pair_difference"] or 0),
                    r["id"],
                )
            )
            return result

    def evidence(self, gid, _connection=None):
        with (
            nullcontext(_connection)
            if _connection is not None
            else self.db.connect() as c
        ):
            objects, groups, children, parents, sources = self._graph(c, [gid])
            require(gid in objects, "NOT_FOUND", "Objekt nenalezen.")
            if gid in groups and objects[gid]["lifecycle"] == "DISSOLVED":
                archived = c.execute(
                    "SELECT evidence_json FROM group_history WHERE group_id=? ORDER BY created_at DESC,id DESC LIMIT 1",
                    (gid,),
                ).fetchone()
                if archived:
                    return {
                        **json.loads(archived[0]),
                        "object": objects[gid],
                        "group": groups[gid],
                        "parent": None,
                        "audit": [
                            dict(r)
                            for r in c.execute(
                                "SELECT * FROM audit_event WHERE object_refs_json LIKE ? ORDER BY timestamp",
                                ("%" + gid + "%",),
                            )
                        ],
                    }
                edges = c.execute(
                    "SELECT * FROM membership WHERE parent_id=? ORDER BY created_at,id",
                    (gid,),
                ).fetchall()
                children[gid] = list(dict.fromkeys(r["child_id"] for r in edges))
            leaves = self._leaves(gid, objects, children)
            return {
                "object": objects[gid],
                "group": groups.get(gid),
                "children": children.get(gid, []),
                "leaves": [sources[i] for i in leaves],
                "difference": self._difference(leaves, sources),
                "parent": parents.get(gid),
                "parent_revision": c.execute(
                    "SELECT revision FROM work_object WHERE id=?", (parents[gid],)
                ).fetchone()[0]
                if gid in parents
                else None,
                "tree_children": children,
                "audit": [
                    dict(r)
                    for r in c.execute(
                        "SELECT * FROM audit_event WHERE object_refs_json LIKE ? ORDER BY timestamp",
                        ("%" + gid + "%",),
                    )
                ],
            }
