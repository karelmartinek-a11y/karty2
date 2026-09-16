"""One undoable transaction for drag/drop, member transfer and partial unpairing."""

import json
from contextlib import nullcontext
from kajovokarty.domain.payment_dates import payment_date
from kajovokarty.application.work import WorkService
from kajovokarty.domain.core import now, require, uid


class PairingService:
    def __init__(self, db):
        self.db = db
        self.work = WorkService(db)

    def _roots(self, c, ids):
        roots = set()
        for identity in ids:
            seen = set()
            while identity not in seen:
                seen.add(identity)
                row = c.execute(
                    "SELECT parent_id FROM membership WHERE child_id=? AND active=1",
                    (identity,),
                ).fetchone()
                if row is None:
                    roots.add(identity)
                    break
                identity = row[0]
        return roots

    def _suppressed(self, c, identity):
        found = set()
        for record in c.execute(
            "SELECT cmd.before_json FROM group_history h JOIN command cmd ON cmd.id=h.command_id WHERE h.group_id=?",
            (identity,),
        ):
            group = (json.loads(record[0]).get(identity) or {}).get("group")
            fingerprint = (
                json.loads(group["evidence_json"]).get("fingerprint") if group else None
            )
            if (
                fingerprint
                and c.execute(
                    "SELECT 1 FROM auto_suppression WHERE fingerprint=? AND active=1",
                    (fingerprint,),
                ).fetchone()
            ):
                found.add(fingerprint)
        return sorted(found)

    def allow_previous_auto(self, identity):
        with self.db.transaction() as c:
            fingerprints = self._suppressed(c, identity)
            require(
                fingerprints,
                "STALE_STATE",
                "Pro tuto skupinu již není automatika potlačena.",
            )
            before = self.work._supp(c, fingerprints)
            cmd = self.work._new_command(c, "ALLOW_AUTO", "MANUAL", {}, before)
            for fingerprint in fingerprints:
                self.work._set_supp(c, fingerprint, False, cmd)
            self.work._finish(
                c, cmd, "ALLOW_AUTO", {}, {}, before, self.work._supp(c, fingerprints)
            )
            return cmd

    def resolve_draft_rows(self, rows):
        """Resolve transfer IDs against one current read snapshot."""
        with self.db.connect() as c:
            c.execute('BEGIN')
            resolved = []
            for incoming in rows:
                row = self.panel(incoming['id'], _connection=c)['object']
                require(row['revision'] == incoming.get('revision'), 'STALE_STATE',
                        'Přetahovaná položka se změnila. Vyberte ji znovu.')
                require(row['currency'] == incoming.get('currency'), 'MIXED_CURRENCY',
                        'Měna přetahované položky se změnila.')
                resolved.append(row)
            require(len({r['currency'] for r in resolved}) <= 1, 'MIXED_CURRENCY',
                    'Nelze spojit různé měny.')
            return resolved

    def panel(self, identity, _connection=None):
        with (nullcontext(_connection) if _connection is not None else self.db.connect()) as c:
            if _connection is None:
                c.execute("BEGIN")
            objects, groups, children, parents, sources = self.work._graph(
                c, self._roots(c, [identity])
            )
            require(
                identity in objects and objects[identity]["lifecycle"] == "ACTIVE",
                "STALE_STATE",
                "Skupina již není aktivní.",
            )

            def row(i):
                leaves = self.work._leaves(i, objects, children)
                source = sources.get(i)
                difference = self.work._difference(leaves, sources)
                cash_leaves = [n for n in leaves if sources[n]['kind'] == 'CASHBOOK_CARD']
                amount = sum(sources[n]['signed_amount_minor'] for n in (cash_leaves or leaves))
                parent = parents.get(i)
                return {
                    **objects[i],
                    "parent_id": parent,
                    "parent_revision": objects[parent]["revision"] if parent else None,
                    "primary_identifier": source["primary_identifier"]
                    if source
                    else "G" + i[:10],
                    "description": source["description"]
                    if source
                    else groups[i]["note"],
                    "kinds": sorted({sources[n]["kind"] for n in leaves}),
                    "date": min((d for n in leaves if (d := payment_date(sources[n]["kind"], sources[n]["local_date"], sources[n]["canonical_json"])) is not None), default=None),
                    "amount": source["signed_amount_minor"]
                    if source
                    else amount,
                    "difference": difference,
                    "leaf_count": len(leaves),
                    "resolved": i in groups and difference == 0,
                    "method": groups[i]["method"] if i in groups else None,
                }

            return {
                "object": row(identity),
                "rows": [row(i) for i in children.get(identity, [identity])],
                "parent_id": parents.get(identity),
                "suppressed_auto": self._suppressed(c, identity),
            }

    def save_draft(self, rows):
        """Atomically replace all groups represented by a draft with one flat group."""
        require(len(rows) >= 2, "GROUP_INVALID", "Vyberte alespoň dvě platby.")
        ids = [r.get("id") for r in rows]
        require(all(ids) and len(ids) == len(set(ids)), "SELECTION_INVALID", "Návrh obsahuje duplicitní položku.")
        revisions = {r["id"]: r.get("revision") for r in rows}
        with self.db.transaction() as c:
            roots = self._roots(c, ids)
            objects, groups, children, parents, sources = self.work._graph(c, roots)
            self.work._check(objects, ids, revisions)
            currencies = {objects[i]["currency"] for i in ids}
            require(len(currencies) == 1, "MIXED_CURRENCY", "CZK a EUR nelze spojit.")

            old_groups = set()
            leaves = []
            for identity in ids:
                node = identity
                if objects[node]["type"] == "GROUP":
                    old_groups.add(node)
                if node in parents:
                    old_groups.add(parents[node])
                current = node
                while current in parents:
                    old_groups.add(parents[current])
                    current = parents[current]
                leaves.extend(self.work._leaves(node, objects, children))
            leaves = list(dict.fromkeys(leaves))
            require(len(leaves) >= 2, "GROUP_INVALID", "Skupina musí obsahovat alespoň dvě platby.")
            require(all(objects[i]["type"] == "SOURCE" for i in leaves), "GROUP_INVALID", "Skupiny mohou obsahovat pouze platby.")
            difference = self.work._difference(leaves, sources)
            require(difference == 0, "NONZERO_DIFFERENCE", "Návrh není přesně vyrovnaný.")

            new_group = uid()
            touched = [new_group, *leaves, *old_groups]
            before = self.work._snapshot(c, touched)
            fingerprints = []
            for gid in old_groups:
                record = groups.get(gid)
                if record:
                    fingerprint = json.loads(record["evidence_json"]).get("fingerprint")
                    if fingerprint:
                        fingerprints.append(fingerprint)
            suppression_before = self.work._supp(c, fingerprints)
            command = self.work._new_command(c, "REPLACE_GROUP", "MANUAL", before, suppression_before)

            for gid in old_groups:
                self.work._archive(c, gid, command)
                c.execute(
                    "UPDATE membership SET active=0,ended_by_command=?,ended_at=? WHERE parent_id=? AND active=1",
                    (command, now(), gid),
                )
                c.execute("UPDATE work_object SET lifecycle='DISSOLVED' WHERE id=?", (gid,))
            c.execute(
                "INSERT INTO work_object VALUES(?,'GROUP',NULL,?,'ACTIVE',1)",
                (new_group, next(iter(currencies))),
            )
            c.execute(
                "INSERT INTO reconciliation_group VALUES(?,?,?,?,?,?)",
                (new_group, "MANUAL", "", now(), now(), "{}"),
            )
            for leaf in leaves:
                c.execute(
                    "INSERT INTO membership VALUES(?,?,?,1,?,NULL,?,NULL)",
                    (uid(), new_group, leaf, command, now()),
                )
            for identity in set(leaves) | old_groups:
                c.execute("UPDATE work_object SET revision=revision+1 WHERE id=?", (identity,))
                c.execute("DELETE FROM work_selection WHERE object_id=?", (identity,))
            self.work._finish(
                c,
                command,
                "REPLACE_GROUP",
                before,
                self.work._snapshot(c, [new_group, *leaves, *old_groups]),
                suppression_before,
                self.work._supp(c, fingerprints),
            )
            return {
                "id": new_group,
                "command_id": command,
                "difference": difference,
                "moved": len(leaves),
                "dissolved": sorted(old_groups),
            }

    def move(
        self,
        ids,
        revisions,
        *,
        target=None,
        target_revision=None,
        parent_revisions=None,
    ):
        require(
            ids and len(ids) == len(set(ids)),
            "SELECTION_INVALID",
            "Vyberte různé finanční objekty.",
        )
        require(target not in ids, "CYCLE_DETECTED", "Objekt nelze přetáhnout na sebe.")
        expected_parents = parent_revisions or {}
        with self.db.transaction() as c:
            roots = self._roots(c, [*ids, *([target] if target else [])])
            objects, groups, children, parents, sources = self.work._graph(c, roots)
            self.work._check(objects, ids, revisions)
            if target:
                self.work._check(objects, [target], {target: target_revision})
            for i in ids:
                parent = parents.get(i)
                expectation = expected_parents.get(i)
                require(
                    expectation
                    == ([parent, objects[parent]["revision"]] if parent else None),
                    "STALE_STATE",
                    "Členství ve skupině se změnilo; obnovte pohled.",
                )
                ancestor = parents.get(i)
                while ancestor:
                    require(
                        ancestor not in ids,
                        "ALREADY_OWNED",
                        "Výběr obsahuje skupinu i jejího člena.",
                    )
                    ancestor = parents.get(ancestor)
            involved = [*ids, *([target] if target else [])]
            require(
                len({objects[i]["currency"] for i in involved}) == 1,
                "MIXED_CURRENCY",
                "CZK a EUR nelze spojit ani společně rozpárovat. Proveďte každou měnu zvlášť.",
            )
            if target:
                ancestor = target
                while ancestor:
                    require(
                        ancestor not in ids,
                        "CYCLE_DETECTED",
                        "Skupinu nelze vložit do jejího potomka.",
                    )
                    ancestor = parents.get(ancestor)
                if target not in groups and target in parents:
                    parent = parents[target]
                    require(
                        expected_parents.get(target)
                        == [parent, objects[parent]["revision"]],
                        "STALE_STATE",
                        "Cílová platba změnila členství.",
                    )
            changed_groups = set()

            def affect(i):
                while i:
                    if i in groups:
                        changed_groups.add(i)
                    i = parents.get(i)

            moved = []
            for i in ids:
                if target is None and i in groups and i not in parents:
                    # Dropping a root in the unpair area releases direct members, not nested leaves.
                    affect(i)
                    moved.extend(children[i])
                else:
                    if target and i in groups and not parents.get(i):
                        require(
                            self.work._difference(
                                self.work._leaves(i, objects, children), sources
                            )
                            != 0,
                            "NONZERO_DIFFERENCE",
                            "Vyřízenou skupinu nejprve rozpojte nebo upravte její členy v panelu.",
                        )
                    moved.append(i)
            moved = [i for i in moved if parents.get(i) != target or target is None]
            require(
                moved and (target or any(i in parents for i in moved)),
                "GROUP_INVALID",
                "Není co přesunout: položky již jsou na tomto místě.",
            )
            for i in moved:
                affect(parents.get(i))
            if target:
                affect(target if target in groups else parents.get(target))
            old_children = {k: list(v) for k, v in children.items()}
            original_groups = set(groups)
            new_group = None
            if target and target not in groups:
                new_group = uid()
                groups[new_group] = {
                    "object_id": new_group,
                    "method": "MANUAL",
                    "note": "",
                    "evidence_json": "{}",
                }
                objects[new_group] = {
                    "id": new_group,
                    "type": "GROUP",
                    "currency": objects[target]["currency"],
                    "lifecycle": "ACTIVE",
                    "revision": 1,
                }
                children[new_group] = [target]
                old_parent = parents.get(target)
                if old_parent:
                    children[old_parent].remove(target)
                parents[target] = new_group
                target = new_group
                changed_groups.add(target)
            for i in moved:
                parent = parents.pop(i, None)
                if parent:
                    children[parent].remove(i)
                if target:
                    children.setdefault(target, []).append(i)
                    parents[i] = target
            dissolved = set()
            while True:
                collapsing = next(
                    (
                        g
                        for g in changed_groups
                        if g not in dissolved and len(children.get(g, [])) < 2
                    ),
                    None,
                )
                if collapsing is None:
                    break
                g = collapsing
                remaining = list(children.get(g, []))
                parent = parents.pop(g, None)
                if parent:
                    position = children[parent].index(g)
                    children[parent][position : position + 1] = remaining
                    changed_groups.add(parent)
                for child in remaining:
                    if parent:
                        parents[child] = parent
                    else:
                        parents.pop(child, None)
                children[g] = []
                dissolved.add(g)
            touched = set(ids) | set(moved) | changed_groups
            if target:
                touched.add(target)
            for g in changed_groups:
                touched.update(old_children.get(g, []))
                touched.update(children.get(g, []))
            # All old/new direct members participate in revision checking and compensation.
            before = self.work._snapshot(c, touched)
            fingers = {
                json.loads(groups[g]["evidence_json"]).get("fingerprint")
                for g in changed_groups
                if g in original_groups
            }
            fingers.discard(None)
            sb = self.work._supp(c, fingers)
            cmd = self.work._new_command(c, "REARRANGE_GROUPS", "MANUAL", before, sb)
            for g in changed_groups & original_groups:
                self.work._archive(c, g, cmd)
            if new_group:
                c.execute(
                    "INSERT INTO work_object VALUES(?,'GROUP',NULL,?,'ACTIVE',1)",
                    (new_group, objects[new_group]["currency"]),
                )
                c.execute(
                    "INSERT INTO reconciliation_group VALUES(?,'MANUAL','',?,?,'{}')",
                    (new_group, now(), now()),
                )
            for g in changed_groups:
                c.execute(
                    "UPDATE membership SET active=0,ended_by_command=?,ended_at=? WHERE parent_id=? AND active=1",
                    (cmd, now(), g),
                )
                c.execute(
                    "UPDATE work_object SET lifecycle=? WHERE id=?",
                    ("DISSOLVED" if g in dissolved else "ACTIVE", g),
                )
                if g not in dissolved:
                    c.execute(
                        "UPDATE reconciliation_group SET method='MANUAL',evidence_json='{}',updated_at=? WHERE object_id=?",
                        (now(), g),
                    )
            for g in changed_groups - dissolved:
                for child in children[g]:
                    c.execute(
                        "INSERT INTO membership VALUES(?,?,?,1,?,NULL,?,NULL)",
                        (uid(), g, child, cmd, now()),
                    )
            for i in touched:
                c.execute("UPDATE work_object SET revision=revision+1 WHERE id=?", (i,))
                c.execute("DELETE FROM work_selection WHERE object_id=?", (i,))
            for fingerprint in fingers:
                self.work._set_supp(c, fingerprint, True, cmd)
            self.work._finish(
                c,
                cmd,
                "REARRANGE_GROUPS",
                before,
                self.work._snapshot(c, touched),
                sb,
                self.work._supp(c, fingers),
            )
            result_target = target if target not in dissolved else None
            difference = (
                self.work._difference(
                    self.work._leaves(target, objects, children), sources
                )
                if result_target
                else None
            )
            return {
                "id": result_target,
                "command_id": cmd,
                "difference": difference,
                "moved": len(moved),
                "dissolved": sorted(dissolved),
            }
