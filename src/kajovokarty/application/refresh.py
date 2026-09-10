"""Targeted refresh with a copied immutable predecessor and reachability pruning."""

import json, copy
from kajovokarty.domain.core import (
    AppError,
    canonical,
    digest,
    identifier,
    now,
    require,
    search_normalize,
    uid,
)
from kajovokarty.domain.helpers import (
    REFERENCE_VERSION,
    api_id,
    extract_references,
    normalize_entity,
)
from kajovokarty.application.sync import SyncService
from kajovokarty.application.generations import graph_hash
from kajovokarty.application.snapshots import save_snapshot, observe, relation_record
from kajovokarty.infrastructure.betterhotel import request_shape


class RefreshService:
    def __init__(self, db, settings):
        self.db = db
        self.settings = settings
        self.sync = SyncService(db, settings)

    def refresh(self, client, kind, eid, context):
        with self.db.operation_gate(client.cancel):
            return self._refresh(client, kind, eid, context)

    def _refresh(self, client, kind, eid, context):
        st = self.sync.state()
        require(
            st["context_id"] == context,
            "API_CONTEXT_CHANGED",
            "Nelze obnovovat historické připojení.",
        )
        require(
            kind
            in (
                "invoice",
                "reservation",
                "bill",
                "bill_item",
                "invoice_item",
                "security_deposit",
            ),
            "API_DETAIL_REQUIRES_FULL_SYNC",
            "Tento typ vyžaduje úplné načtení.",
        )
        oldgen = st["published_generation_id"]
        entities = {}
        links = set()
        raws = []
        edge_records = {}
        old_links = {}
        changed = set()
        cache = set()
        with self.db.connect() as c:
            for r in c.execute(
                "SELECT h.*,s.payload_json,s.content_hash FROM helper_current h JOIN helper_snapshot s ON s.id=h.snapshot_id WHERE h.context_id=? AND h.generation_id=?",
                (context, oldgen),
            ):
                entities[(r["resource_type"], r["external_id"])] = {
                    **dict(r),
                    "payload": json.loads(r["payload_json"]),
                }
            for r in c.execute(
                "SELECT * FROM helper_link WHERE context_id=? AND generation_id=?",
                (context, oldgen),
            ):
                key = tuple(
                    r[k]
                    for k in ("from_type", "from_id", "relation", "to_type", "to_id")
                )
                old_links[key] = dict(r)
            links = {k for k, v in old_links.items() if v["active"]}
        old_entities = copy.deepcopy(entities)
        deposit_only = kind == "security_deposit"
        target = (kind, eid)
        require(
            target in entities,
            "API_DETAIL_REQUIRES_FULL_SYNC",
            "ID není známo v aktuálním připojení.",
        )
        original_active = entities[target]["active"]
        roots = {k for k, e in entities.items() if e["root_observed"] and e["active"]}
        currencies = {
            i: identifier(
                e["payload"].get(
                    "iso_code", e["payload"].get("code", e["payload"].get("name"))
                )
            )
            for (k, i), e in entities.items()
            if k == "currency" and e["active"]
        }
        if kind in ("invoice_item", "security_deposit"):
            parents = {(ft, fi) for ft, fi, rel, tt, ti in links if (tt, ti) == target}
            require(
                len(parents) == 1,
                "API_DETAIL_REQUIRES_FULL_SYNC",
                "Chybí jednoznačný aktivní rodič entity.",
            )
            kind, eid = next(iter(parents))
        op = self.db.start_operation("REFRESH_DETAIL")
        gen = uid()
        from kajovokarty.infrastructure.technical_log import TechnicalLog

        client.logger = TechnicalLog(
            self.db.path.parent / "logs",
            self.settings.get()["diagnostics.log_retention_days"],
        )
        client.correlation_id = op

        def guard(c):
            cur = c.execute("SELECT * FROM helper_state").fetchone()
            require(
                cur["context_id"] == context
                and cur["credential_revision"] == st["credential_revision"]
                and cur["published_generation_id"] == oldgen,
                "API_CONTEXT_CHANGED",
                "Předchozí graf nebo kontext byl změněn.",
            )

        with self.db.transaction() as c:
            guard(c)
            c.execute(
                "INSERT INTO helper_generation VALUES(?,?,?,'DETAIL',?,'STAGING',?,?,NULL,NULL,?,NULL,NULL)",
                (
                    gen,
                    context,
                    st["credential_revision"],
                    oldgen,
                    op,
                    canonical({"target": [kind, eid]}),
                    now(),
                ),
            )
            c.execute(
                "UPDATE helper_state SET previous_status=status,status='REFRESHING',revision=revision+1,operation_id=? WHERE id=1",
                (op,),
            )

        def put(k, raw, template, parent_currency=None, projection="DETAIL_ENTITY"):
            client.last_template = template
            p = normalize_entity(k, raw, currencies, parent_currency)
            key = (k, p["id"])
            old = entities.get(key)
            if key in changed:
                require(
                    entities[key]["payload"] == p,
                    "API_SNAPSHOT_CONFLICT",
                    "Detail obsahuje konfliktní opakovanou entitu.",
                )
            else:
                entities[key] = {
                    **(old or {}),
                    "payload": p,
                    "active": 1,
                    "complete": 1,
                    "root_observed": int(key in roots),
                    "revision": (old or {}).get("revision", 1),
                }
                changed.add(key)
            raws.append(
                (k, p["id"], projection, request_shape(template), template, raw)
            )
            return p

        def get(k, i, template, keyname, parent_currency=None):
            key = (k, i)
            if key in cache:
                return entities[key]["payload"]
            raw = client.detail(template, {keyname: i})
            require(
                api_id(raw.get("id", raw.get("uuid"))) == i,
                "API_SCHEMA",
                "ID detailu nesouhlasí s URL.",
            )
            p = put(k, raw, template, parent_currency)
            cache.add(key)
            return p

        def edge(ft, fi, relation, tt, ti, raw, template):
            key = (ft, fi, relation, tt, ti)
            record = relation_record(key, template, raw)
            require(
                key not in edge_records or edge_records[key][-1] == raw,
                "API_SNAPSHOT_CONFLICT",
                "Vztah změnil obsah.",
            )
            edge_records[key] = record
            raws.append(record)
            links.add(key)

        def active_parent(k, i, parent_kind):
            parents = {
                fi
                for ft, fi, rel, tt, ti in links
                if ft == parent_kind and (tt, ti) == (k, i)
            }
            require(
                len(parents) == 1,
                "API_DETAIL_REQUIRES_FULL_SYNC",
                "Chybí jednoznačný aktivní rodič. Spusťte úplné načtení.",
            )
            return next(iter(parents))

        def outgoing(k, i):
            nonlocal links
            links = {l for l in links if l[:2] != (k, i)}

        def invoice(i):
            p = get("invoice", i, "/invoice/{invoice_id}", "invoice_id")
            require(
                p.get("date"),
                "API_SCHEMA",
                "Neúplný doklad.",
            )
            outgoing("invoice", i)
            parent_raw = next(
                s[5]
                for s in reversed(raws)
                if s[0] == "invoice" and s[1] == i and s[2] == "DETAIL_ENTITY"
            )
            embedded = parent_raw.get(
                "invoice_item",
                parent_raw.get("invoice_items", parent_raw.get("items", [])),
            )
            embedded = [embedded] if isinstance(embedded, dict) else embedded
            for item in embedded:
                q = put(
                    "invoice_item",
                    item,
                    "/invoice/{invoice_id}",
                    p["currency"],
                    "EMBEDDED_ENTITY",
                )
                edge(
                    "invoice",
                    i,
                    "ITEM",
                    "invoice_item",
                    q["id"],
                    item,
                    "/invoice/{invoice_id}",
                )
                outgoing("invoice_item", q["id"])
                if q.get("bill_item_id"):
                    target = ("bill_item", q["bill_item_id"])
                    require(
                        target in entities and entities[target]["active"],
                        "API_DETAIL_REQUIRES_FULL_SYNC",
                        "Nová vazba vyžaduje úplné načtení.",
                    )
                    edge(
                        "invoice_item",
                        q["id"],
                        "BILL_ITEM",
                        *target,
                        {"bill_item_id": q["bill_item_id"]},
                        "/invoice/{invoice_id}",
                    )

        def bill(i, parent=None):
            p = get("bill", i, "/bill/{bill_id}", "bill_id")
            require(
                not parent
                or not p.get("reservation_id")
                or p["reservation_id"] == parent,
                "API_SCHEMA",
                "Účet patří jiné rezervaci.",
            )
            if parent:
                p["reservation_id"] = parent
            outgoing("bill", i)
            for raw in client.collection("/bill/{bill_id}/bill-item", {"bill_id": i}):
                iid = api_id(raw.get("bill_item_id", raw.get("id")))
                q = get(
                    "bill_item",
                    iid,
                    "/bill-item/{item_id}",
                    "item_id",
                    p.get("currency"),
                )
                require(
                    not q.get("bill_id") or q["bill_id"] == i,
                    "API_SCHEMA",
                    "Položka patří jinému účtu.",
                )
                q["bill_id"] = i
                edge(
                    "bill",
                    i,
                    "ITEM",
                    "bill_item",
                    iid,
                    raw,
                    "/bill/{bill_id}/bill-item",
                )

        try:
            if kind == "invoice":
                invoice(eid)
            elif kind == "bill":
                bill(eid, active_parent(kind, eid, "reservation"))
            elif kind == "bill_item":
                parent = active_parent(kind, eid, "bill")
                q = get(
                    kind,
                    eid,
                    "/bill-item/{item_id}",
                    "item_id",
                    entities[("bill", parent)]["payload"].get("currency"),
                )
                require(
                    not q.get("bill_id") or q["bill_id"] == parent,
                    "API_SCHEMA",
                    "Položka patří jinému účtu.",
                )
                q["bill_id"] = parent
            elif kind == "reservation":
                if deposit_only:
                    links = {
                        l
                        for l in links
                        if not (l[:2] == (kind, eid) and l[2] == "DEPOSIT")
                    }
                else:
                    get(kind, eid, "/reservation/{reservation_id}", "reservation_id")
                    outgoing(kind, eid)
                    for raw in client.collection(
                        "/reservation/{reservation_id}/invoice", {"reservation_id": eid}
                    ):
                        iid = api_id(raw.get("invoice_id", raw.get("id")))
                        invoice(iid)
                        edge(
                            kind,
                            eid,
                            "INVOICE",
                            "invoice",
                            iid,
                            raw,
                            "/reservation/{reservation_id}/invoice",
                        )
                    for raw in client.collection(
                        "/reservation/{reservation_id}/bill", {"reservation_id": eid}
                    ):
                        bid = api_id(raw.get("bill_id", raw.get("id")))
                        bill(bid, eid)
                        edge(
                            kind,
                            eid,
                            "BILL",
                            "bill",
                            bid,
                            raw,
                            "/reservation/{reservation_id}/bill",
                        )
                for raw in client.collection(
                    "/reservation/{reservation_id}/security-deposit",
                    {"reservation_id": eid},
                ):
                    p = put(
                        "security_deposit",
                        raw,
                        "/reservation/{reservation_id}/security-deposit",
                        projection="LIST_ENTITY",
                    )
                    require(
                        not p.get("reservation_id") or p["reservation_id"] == eid,
                        "API_SCHEMA",
                        "Kauce patří jiné rezervaci.",
                    )
                    p["reservation_id"] = eid
                    edge(
                        kind,
                        eid,
                        "DEPOSIT",
                        "security_deposit",
                        p["id"],
                        raw,
                        "/reservation/{reservation_id}/security-deposit",
                    )
            client.check_cancel()
            publish = st["status"] == "READY" and bool(original_active)
            reachable = set()
            stack = list(roots)
            outgoing_map = {}
            for ft, fi, rel, tt, ti in links:
                outgoing_map.setdefault((ft, fi), []).append((tt, ti))
            while stack:
                key = stack.pop()
                if key in reachable:
                    continue
                require(
                    key in entities and entities[key]["complete"],
                    "API_DETAIL_REQUIRES_FULL_SYNC",
                    "Graf není úplný.",
                )
                reachable.add(key)
                stack.extend(outgoing_map.get(key, []))
            with self.db.transaction() as c:
                guard(c)

                def snapshot(k, i, projection, shape, template, payload):
                    return save_snapshot(
                        c, context, op, (k, i, projection, shape, template, payload)
                    )

                for index, record in enumerate(raws):
                    observe(c, context, gen, op, record, "DETAIL", index)
                if publish:
                    for (k, i), e in sorted(entities.items()):
                        active = (k, i) in reachable
                        sid = (
                            snapshot(
                                k,
                                i,
                                "MERGED_ENTITY",
                                digest(
                                    sorted(
                                        {
                                            (projection, shape)
                                            for kk, ii, projection, shape, t, p in raws
                                            if (kk, ii) == (k, i)
                                        }
                                    )
                                ),
                                "LOCAL_MERGE",
                                e["payload"],
                            )
                            if (k, i) in changed
                            else e["snapshot_id"]
                        )
                        e["snapshot_id"] = sid
                        c.execute(
                            "INSERT INTO helper_current VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                            (
                                context,
                                gen,
                                k,
                                i,
                                sid,
                                old_entities[(k, i)]["revision"]
                                + int(
                                    old_entities[(k, i)]["content_hash"]
                                    != digest(e["payload"])
                                    or bool(old_entities[(k, i)]["active"]) != active
                                    or old_entities[(k, i)]["complete"] != e["complete"]
                                )
                                if (k, i) in old_entities
                                else 1,
                                int(active),
                                e["complete"],
                                int((k, i) in roots),
                                None if active else "NO_ACTIVE_ROOT_PATH",
                                search_normalize(canonical(e["payload"])),
                            ),
                        )
                        if k == "reservation":
                            channel = e["payload"].get("reservation_source") or {}
                            ref = extract_references(
                                e["payload"].get("reservation_note"),
                                channel.get("name"),
                            )
                            for origin in ref["origins"] or [{}]:
                                c.execute(
                                    "INSERT INTO helper_reference VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                                    (
                                        uid(),
                                        context,
                                        gen,
                                        i,
                                        sid,
                                        origin.get("candidate"),
                                        origin.get("label"),
                                        origin.get("start_offset"),
                                        origin.get("end_offset"),
                                        REFERENCE_VERSION,
                                        ref["status"],
                                    ),
                                )
                    for key in sorted(set(old_links) | links):
                        ft, fi, rel, tt, ti = key
                        active = (
                            key in links
                            and (ft, fi) in reachable
                            and (tt, ti) in reachable
                        )
                        sid = (
                            save_snapshot(c, context, op, edge_records[key])
                            if key in edge_records
                            else old_links[key]["snapshot_id"]
                        )
                        c.execute(
                            "INSERT INTO helper_link VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                            (
                                uid(),
                                context,
                                gen,
                                *key,
                                int(active),
                                1 if key in links else old_links[key]["complete"],
                                sid,
                            ),
                        )
                    for row in c.execute(
                        "SELECT * FROM sync_coverage WHERE context_id=? AND generation_id=?",
                        (context, oldgen),
                    ).fetchall():
                        c.execute(
                            "INSERT INTO sync_coverage VALUES(?,?,?,?,?,?,?,?)",
                            (
                                context,
                                gen,
                                row["resource_type"],
                                row["range_start"],
                                row["range_end"],
                                row["successful_run_id"],
                                row["completed_at"],
                                row["complete"],
                            ),
                        )
                    gh = graph_hash(c, context, gen)
                    c.execute(
                        "UPDATE helper_generation SET state='PUBLISHED',graph_hash=?,sealed_at=?,published_at=?,evidence_epoch=? WHERE id=?",
                        (gh, now(), now(), st["evidence_epoch"] + 1, gen),
                    )
                    c.execute(
                        "UPDATE helper_state SET published_generation_id=?,status='READY',evidence_epoch=evidence_epoch+1,revision=revision+1,failure_code=NULL WHERE id=1",
                        (gen,),
                    )
                    self.db.invalidate_redo(c)
                else:
                    c.execute(
                        "UPDATE helper_generation SET state='ABORTED' WHERE id=?",
                        (gen,),
                    )
                    c.execute(
                        "UPDATE helper_state SET status=?,revision=revision+1 WHERE id=1",
                        (st["status"],),
                    )
                self.db.audit(
                    c,
                    "DETAIL_PUBLISHED" if publish else "DETAIL_PREVIEW",
                    after={
                        "context_id": context,
                        "generation_id": gen if publish else None,
                        "target": [kind, eid],
                    },
                    operation=op,
                )
            self.db.finish_operation(op)
            return {"published": publish, "target": entities[(kind, eid)]["payload"]}
        except Exception as error:
            e = (
                error
                if isinstance(error, AppError)
                else AppError(
                    "SYNC_FAILED", "Obnova detailu byla přerušena interní chybou."
                )
            )
            client.fail(client.last_template, e.code)
            with self.db.transaction() as c:
                cur = c.execute("SELECT context_id FROM helper_state").fetchone()[0]
                if cur == context:
                    c.execute(
                        "UPDATE helper_state SET status='STALE',revision=revision+1,failure_code=? WHERE id=1",
                        (e.code,),
                    )
                    c.execute(
                        "UPDATE helper_generation SET state='ABORTED' WHERE id=?",
                        (gen,),
                    )
            self.db.finish_operation(op, e)
            raise e from None
