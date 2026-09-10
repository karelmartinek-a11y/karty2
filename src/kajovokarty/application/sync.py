from __future__ import annotations
from datetime import date, timedelta
import json
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
    merge,
    normalize_entity,
)
from kajovokarty.infrastructure.betterhotel import TEMPLATES, request_shape
from kajovokarty.application.generations import graph_hash
from kajovokarty.application.snapshots import save_snapshot, observe, relation_record


class SyncService:
    def __init__(self, db, settings):
        self.db = db
        self.settings = settings

    def resume(self, client, operation_id, progress=None):
        with self.db.operation_gate(client.cancel, progress):
            return self._full(client, False, progress, None, resume_id=operation_id)

    def state(self):
        with self.db.connect() as c:
            return dict(c.execute("SELECT * FROM helper_state").fetchone())

    def scope(self):
        today = date.today()
        starts = [today - timedelta(days=365)]
        ends = [today]
        with self.db.connect() as c:
            for r in c.execute(
                "SELECT local_date,canonical_json FROM financial_source"
            ):
                starts.append(date.fromisoformat(r["local_date"]))
                ends.append(date.fromisoformat(r["local_date"]))
                p = json.loads(r["canonical_json"])
                if p.get("arrival"):
                    starts.append(date.fromisoformat(p["arrival"]))
                if p.get("departure"):
                    ends.append(date.fromisoformat(p["departure"]))
            st = self.state()
            for r in c.execute(
                "SELECT range_start,range_end FROM sync_coverage WHERE context_id=? AND generation_id=?",
                (st["context_id"], st["published_generation_id"]),
            ):
                starts.append(date.fromisoformat(r[0]))
                ends.append(date.fromisoformat(r[1]))
        custom = self.settings.get().get("sync.start_date")
        if custom:
            starts.append(date.fromisoformat(custom))
        return min(starts).isoformat(), max(ends).isoformat()

    def full(self, client, compatibility=False, progress=None, scope=None):
        with self.db.operation_gate(client.cancel, progress):
            return self._full(client, compatibility, progress, scope)

    def _full(self, client, compatibility, progress, scope, resume_id=None):
        start, end = scope or self.scope()
        settings = self.settings.get()
        st = self.state()
        ctx = st["context_id"]
        gen = uid()
        entities = {}
        links = []
        snapshots = []
        currencies = {}
        representations = {}
        roots = set()
        cache = {}
        checkpoint = None
        edge_records = {}
        persisted = 0
        if resume_id:
            with self.db.connect() as c:
                previous = c.execute(
                    "SELECT recovery_json FROM operation WHERE id=?", (resume_id,)
                ).fetchone()
            require(previous, "STALE_STATE", "Checkpoint běhu neexistuje.")
            checkpoint = json.loads(previous[0] or "{}")
            valid = (
                checkpoint.get("context_id") == ctx
                and checkpoint.get("credential_revision") == st["credential_revision"]
                and checkpoint.get("predecessor_id") == st["published_generation_id"]
                and checkpoint.get("parser_contract") == "BH-CONNECTOR-1"
                and checkpoint.get("settings") == settings
            )
            if not valid:
                with self.db.transaction() as c:
                    c.execute(
                        "UPDATE helper_generation SET state='ABORTED' WHERE operation_id=? AND state!='PUBLISHED'",
                        (resume_id,),
                    )
                return self._full(client, compatibility, progress, None)
            op = resume_id
            gen = checkpoint["generation_id"]
            start, end = checkpoint["scope"]
            compatibility = checkpoint["compatibility"]
            entities = {tuple(k): v for k, v in checkpoint["entities"]}
            links = [tuple(x) for x in checkpoint["links"]]
            snapshots = [tuple(x) for x in checkpoint["snapshots"]]
            currencies = checkpoint["currencies"]
            representations = {tuple(k): v for k, v in checkpoint["representations"]}
            roots = {tuple(k) for k in checkpoint["roots"]}
            cache = {tuple(k): v for k, v in checkpoint["cache"]}
            client.stats = checkpoint["client_stats"]
            edge_records = {
                tuple(k): tuple(v) for k, v in checkpoint.get("edge_records", [])
            }
            persisted = checkpoint.get("persisted", 0)
        else:
            op = self.db.start_operation("SYNC")

        from kajovokarty.infrastructure.technical_log import TechnicalLog

        client.logger = TechnicalLog(
            self.db.path.parent / "logs", settings["diagnostics.log_retention_days"]
        )
        client.correlation_id = op
        published = False

        def guard(c):
            current = c.execute("SELECT * FROM helper_state").fetchone()
            require(
                current["context_id"] == ctx
                and current["credential_revision"] == st["credential_revision"]
                and current["published_generation_id"]
                == (gen if published else st["published_generation_id"]),
                "API_CONTEXT_CHANGED",
                "Připojení se během operace změnilo.",
            )

        with self.db.transaction() as c:
            guard(c)
            if checkpoint:
                c.execute(
                    "UPDATE helper_generation SET state='STAGING' WHERE id=?", (gen,)
                )
                c.execute(
                    "UPDATE operation SET state='RUNNING',finished_at=NULL,safe_error_json=NULL WHERE id=?",
                    (op,),
                )
            else:
                c.execute(
                    "INSERT INTO helper_generation VALUES(?,?,?,'FULL',?,'STAGING',?,?,NULL,NULL,?,NULL,NULL)",
                    (
                        gen,
                        ctx,
                        st["credential_revision"],
                        st["published_generation_id"],
                        op,
                        canonical({"start": start, "end": end}),
                        now(),
                    ),
                )
            c.execute(
                "UPDATE helper_state SET previous_status=status,status='REFRESHING',operation_id=?,planned_scope_json=?,revision=revision+1 WHERE id=1",
                (op, canonical({"start": start, "end": end})),
            )
            if compatibility and not checkpoint:
                c.execute(
                    "INSERT INTO api_compatibility_run VALUES(?,?,NULL,'BH-CONNECTOR-1','0.3.0',?,?,?,'NOT_ATTEMPTED',?,NULL)",
                    (op, ctx, st["credential_revision"], start, end, now()),
                )

        def add(kind, raw, projection, template, root=False, parent_currency=None):
            client.last_template = template
            normalized = normalize_entity(kind, raw, currencies, parent_currency)
            eid = normalized["id"]
            key = (kind, eid)
            shape = request_shape(template)
            rep = (kind, eid, projection, shape)
            if rep in representations:
                require(
                    representations[rep] == normalized,
                    "API_SNAPSHOT_CONFLICT",
                    "Opakovaná reprezentace změnila obsah.",
                )
            representations[rep] = normalized
            entities[key] = merge(entities.get(key, {}), dict(normalized))
            snapshots.append((kind, eid, projection, shape, template, raw))
            if root:
                roots.add(key)
            return eid

        def edge(ft, fi, relation, tt, ti, raw, template):
            key = (ft, fi, relation, tt, ti)
            record = relation_record(key, template, raw)
            if key in edge_records:
                require(
                    edge_records[key][-1] == raw,
                    "API_SNAPSHOT_CONFLICT",
                    "Opakovaný vztah změnil obsah.",
                )
            edge_records[key] = record
            links.append(key)
            snapshots.append(record)

        def flush(c, block_key):
            nonlocal persisted
            for index in range(persisted, len(snapshots)):
                observe(c, ctx, gen, op, snapshots[index], block_key, index)
            persisted = len(snapshots)

        def detail(kind, eid, template, keyname, parent_currency=None):
            key = (kind, eid, template)
            if key not in cache:
                raw = client.detail(template, {keyname: eid})
                require(
                    api_id(raw.get("id", raw.get("uuid"))) == eid,
                    "API_SCHEMA",
                    "ID detailu neodpovídá URL.",
                )
                add(
                    kind,
                    raw,
                    "DETAIL_ENTITY",
                    template,
                    parent_currency=parent_currency,
                )
                cache[key] = True
            return entities[(kind, eid)]

        def invoice_items(eid):
            inv = entities[("invoice", eid)]
            require(
                inv.get("date"),
                "API_SCHEMA",
                "Doklad nemá povinné datum.",
            )
            # Attribute embedded items to the actual received parent projection.
            origin = next(
                (
                    s
                    for s in reversed(snapshots)
                    if s[0] == "invoice"
                    and s[1] == eid
                    and s[2] in ("LIST_ENTITY", "DETAIL_ENTITY")
                    and any(
                        k in s[5] for k in ("invoice_item", "invoice_items", "items")
                    )
                ),
                None,
            )
            parent_raw = origin[5] if origin else {}
            embedded = parent_raw.get(
                "invoice_item",
                parent_raw.get("invoice_items", parent_raw.get("items", [])),
            )
            embedded = [embedded] if isinstance(embedded, dict) else embedded
            for item in embedded:
                iid = add(
                    "invoice_item",
                    item,
                    "EMBEDDED_ENTITY",
                    origin[4],
                    parent_currency=inv.get("currency"),
                )
                edge(
                    "invoice",
                    eid,
                    "ITEM",
                    "invoice_item",
                    iid,
                    item,
                    origin[4],
                )

        published = False
        try:
            for raw in [] if checkpoint else client.collection("/currency"):
                eid = api_id(raw.get("id", raw.get("code")))
                iso = identifier(raw.get("iso_code", raw.get("code", raw.get("name"))))
                require(iso, "API_SCHEMA", "Měna nemá ISO kód.")
                iso = iso.upper()
                require(
                    eid not in currencies or currencies[eid] == iso,
                    "API_SNAPSHOT_CONFLICT",
                    "Měnový číselník obsahuje konflikt.",
                )
                currencies[eid] = iso
                add("currency", raw, "LIST_ENTITY", "/currency", True)
            cursor = (
                (
                    date.fromisoformat(checkpoint["completed_through"])
                    + timedelta(days=1)
                )
                if checkpoint
                else date.fromisoformat(start)
            )
            last = date.fromisoformat(end)
            block = checkpoint.get("blocks", 0) if checkpoint else 0
            while cursor <= last:
                client.check_cancel()
                block += 1
                stop = min(
                    last, cursor + timedelta(days=settings["sync.block_days"] - 1)
                )
                a, b = cursor.isoformat(), stop.isoformat()
                if progress:
                    progress(f"BetterHotel: {a} až {b}")
                for raw in client.collection(
                    "/invoice",
                    params=[("filter[date_from]", a), ("filter[date_to]", b)],
                ):
                    eid = add("invoice", raw, "LIST_ENTITY", "/invoice", True)
                    inv = entities[("invoice", eid)]
                    if compatibility or not all(
                        inv.get(k) for k in ("code", "date", "currency")
                    ):
                        detail("invoice", eid, "/invoice/{invoice_id}", "invoice_id")
                    invoice_items(eid)
                for raw in client.collection(
                    "/reservation",
                    params=[
                        ("date_from", a),
                        ("date_to", b),
                        ("expand[]", "reservation_source"),
                        ("expand[]", "reservation_note"),
                    ],
                ):
                    rid = add("reservation", raw, "LIST_ENTITY", "/reservation", True)
                    if ("reservation_relations", rid) in cache:
                        continue
                    detail(
                        "reservation",
                        rid,
                        "/reservation/{reservation_id}",
                        "reservation_id",
                    )
                    for rel in client.collection(
                        "/reservation/{reservation_id}/invoice", {"reservation_id": rid}
                    ):
                        iid = api_id(rel.get("invoice_id", rel.get("id")))
                        detail("invoice", iid, "/invoice/{invoice_id}", "invoice_id")
                        invoice_items(iid)
                        edge(
                            "reservation",
                            rid,
                            "INVOICE",
                            "invoice",
                            iid,
                            rel,
                            "/reservation/{reservation_id}/invoice",
                        )
                    for rel in client.collection(
                        "/reservation/{reservation_id}/bill", {"reservation_id": rid}
                    ):
                        bid = api_id(rel.get("bill_id", rel.get("id")))
                        bill = detail("bill", bid, "/bill/{bill_id}", "bill_id")
                        require(
                            not bill.get("reservation_id")
                            or bill["reservation_id"] == rid,
                            "API_SCHEMA",
                            "Účet odkazuje na jinou rezervaci.",
                        )
                        bill["reservation_id"] = rid
                        edge(
                            "reservation",
                            rid,
                            "BILL",
                            "bill",
                            bid,
                            rel,
                            "/reservation/{reservation_id}/bill",
                        )
                        for item in client.collection(
                            "/bill/{bill_id}/bill-item", {"bill_id": bid}
                        ):
                            iid = api_id(item.get("bill_item_id", item.get("id")))
                            itemdata = detail(
                                "bill_item",
                                iid,
                                "/bill-item/{item_id}",
                                "item_id",
                                bill.get("currency"),
                            )
                            require(
                                not itemdata.get("bill_id")
                                or itemdata["bill_id"] == bid,
                                "API_SCHEMA",
                                "Položka patří jinému účtu.",
                            )
                            itemdata["bill_id"] = bid
                            edge(
                                "bill",
                                bid,
                                "ITEM",
                                "bill_item",
                                iid,
                                item,
                                "/bill/{bill_id}/bill-item",
                            )
                    for dep in client.collection(
                        "/reservation/{reservation_id}/security-deposit",
                        {"reservation_id": rid},
                    ):
                        did = add(
                            "security_deposit",
                            dep,
                            "LIST_ENTITY",
                            "/reservation/{reservation_id}/security-deposit",
                        )
                        deposit = entities[("security_deposit", did)]
                        require(
                            not deposit.get("reservation_id")
                            or deposit["reservation_id"] == rid,
                            "API_SCHEMA",
                            "Kauce patří jiné rezervaci.",
                        )
                        deposit["reservation_id"] = rid
                        edge(
                            "reservation",
                            rid,
                            "DEPOSIT",
                            "security_deposit",
                            did,
                            dep,
                            "/reservation/{reservation_id}/security-deposit",
                        )
                    cache[("reservation_relations", rid)] = True
                # Raw evidence is durable at every complete block; current pointer stays unchanged.
                with self.db.transaction() as c:
                    guard(c)
                    flush(c, a + "/" + b)
                    self.db.audit(
                        c,
                        "SYNC_BLOCK_COMPLETED",
                        after={"generation_id": gen, "start": a, "end": b},
                        operation=op,
                    )
                    c.execute(
                        "UPDATE operation SET heartbeat_at=?,progress_current=?,recovery_json=? WHERE id=?",
                        (
                            now(),
                            block,
                            canonical(
                                {
                                    "context_id": ctx,
                                    "credential_revision": st["credential_revision"],
                                    "generation_id": gen,
                                    "predecessor_id": st["published_generation_id"],
                                    "parser_contract": "BH-CONNECTOR-1",
                                    "scope": [start, end],
                                    "settings": settings,
                                    "evidence_class": client.evidence_class,
                                    "compatibility": compatibility,
                                    "completed_through": b,
                                    "blocks": block,
                                    "entities": [
                                        [list(k), v] for k, v in entities.items()
                                    ],
                                    "links": links,
                                    "snapshots": snapshots,
                                    "persisted": persisted,
                                    "edge_records": [
                                        [list(k), v] for k, v in edge_records.items()
                                    ],
                                    "currencies": currencies,
                                    "representations": [
                                        [list(k), v] for k, v in representations.items()
                                    ],
                                    "roots": [list(k) for k in roots],
                                    "cache": [[list(k), v] for k, v in cache.items()],
                                    "client_stats": client.stats,
                                }
                            ),
                            op,
                        ),
                    )
                cursor = stop + timedelta(days=1)
            client.check_cancel()
            for (kind, eid), payload in list(entities.items()):
                if kind == "invoice_item" and payload.get("bill_item_id"):
                    target = ("bill_item", payload["bill_item_id"])
                    require(
                        target in entities,
                        "API_SCHEMA",
                        "Položka dokladu odkazuje na nedoloženou položku účtu.",
                    )
                    edge(
                        kind,
                        eid,
                        "BILL_ITEM",
                        *target,
                        {"bill_item_id": payload["bill_item_id"]},
                        "/invoice/{invoice_id}",
                    )
            links = sorted(set(links))
            snapshot_ids = {}
            with self.db.transaction() as c:
                guard(c)

                def snapshot(kind, eid, projection, shape, template, payload):
                    return save_snapshot(
                        c, ctx, op, (kind, eid, projection, shape, template, payload)
                    )

                flush(c, "FULL_FINAL")
                previous = {}
                if st["published_generation_id"]:
                    previous = {
                        (r["resource_type"], r["external_id"]): dict(r)
                        for r in c.execute(
                            "SELECT h.*,s.content_hash FROM helper_current h JOIN helper_snapshot s ON s.id=h.snapshot_id WHERE h.context_id=? AND h.generation_id=?",
                            (ctx, st["published_generation_id"]),
                        )
                    }
                for (kind, eid), payload in sorted(entities.items()):
                    shapes = sorted(
                        {
                            (p, s)
                            for k, i, p, s in representations
                            if k == kind and i == eid
                        }
                    )
                    sid = snapshot(
                        kind,
                        eid,
                        "MERGED_ENTITY",
                        digest(shapes),
                        "LOCAL_MERGE",
                        payload,
                    )
                    snapshot_ids[(kind, eid)] = sid
                    prior = previous.get((kind, eid))
                    rev = (
                        prior["revision"]
                        + int(
                            prior["content_hash"] != digest(payload)
                            or not prior["active"]
                            or not prior["complete"]
                        )
                        if prior
                        else 1
                    )
                    c.execute(
                        "INSERT INTO helper_current VALUES(?,?,?,?,?,?,1,1,?,NULL,?)",
                        (
                            ctx,
                            gen,
                            kind,
                            eid,
                            sid,
                            rev,
                            int((kind, eid) in roots),
                            search_normalize(canonical(payload)),
                        ),
                    )
                    if kind == "reservation":
                        channel = payload.get("reservation_source") or {}
                        ref = extract_references(
                            payload.get("reservation_note", []),
                            channel.get("name") if isinstance(channel, dict) else None,
                        )
                        for origin in ref["origins"] or [{}]:
                            c.execute(
                                "INSERT INTO helper_reference VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                                (
                                    uid(),
                                    ctx,
                                    gen,
                                    eid,
                                    sid,
                                    origin.get("candidate"),
                                    origin.get("label"),
                                    origin.get("start_offset"),
                                    origin.get("end_offset"),
                                    REFERENCE_VERSION,
                                    ref["status"],
                                ),
                            )
                for key, prior in previous.items():
                    if key not in entities:
                        c.execute(
                            "INSERT INTO helper_current VALUES(?,?,?,?,?,?,0,?,0,?,?)",
                            (
                                ctx,
                                gen,
                                *key,
                                prior["snapshot_id"],
                                prior["revision"] + int(prior["active"]),
                                prior["complete"],
                                "NOT_OBSERVED_IN_FULL_SYNC",
                                prior["local_search_text"],
                            ),
                        )
                for ft, fi, rel, tt, ti in links:
                    require(
                        (ft, fi) in entities and (tt, ti) in entities,
                        "API_SCHEMA",
                        "Graf má neúplnou hranu.",
                    )
                    c.execute(
                        "INSERT INTO helper_link VALUES(?,?,?,?,?,?,?,?,1,1,?)",
                        (
                            uid(),
                            ctx,
                            gen,
                            ft,
                            fi,
                            rel,
                            tt,
                            ti,
                            save_snapshot(
                                c, ctx, op, edge_records[(ft, fi, rel, tt, ti)]
                            ),
                        ),
                    )
                if st["published_generation_id"]:
                    for old in c.execute(
                        "SELECT * FROM helper_link WHERE context_id=? AND generation_id=?",
                        (ctx, st["published_generation_id"]),
                    ).fetchall():
                        key = tuple(
                            old[k]
                            for k in (
                                "from_type",
                                "from_id",
                                "relation",
                                "to_type",
                                "to_id",
                            )
                        )
                        if key not in links:
                            c.execute(
                                "INSERT INTO helper_link VALUES(?,?,?,?,?,?,?,?,0,?,?)",
                                (
                                    uid(),
                                    ctx,
                                    gen,
                                    *key,
                                    old["complete"],
                                    old["snapshot_id"],
                                ),
                            )
                for kind in ("invoice", "reservation"):
                    c.execute(
                        "INSERT INTO sync_coverage VALUES(?,?,?,?,?,?,?,1)",
                        (ctx, gen, kind, start, end, op, now()),
                    )
                gh = graph_hash(c, ctx, gen)
                c.execute(
                    "UPDATE helper_generation SET state='SEALED',graph_hash=?,sealed_at=? WHERE id=?",
                    (gh, now(), gen),
                )
                guard(c)
                c.execute(
                    "UPDATE helper_generation SET state='PUBLISHED',published_at=?,evidence_epoch=? WHERE id=?",
                    (now(), st["evidence_epoch"] + 1, gen),
                )
                c.execute(
                    "UPDATE helper_state SET published_generation_id=?,status='READY',evidence_epoch=evidence_epoch+1,revision=revision+1,last_full_success_at=?,failure_code=NULL WHERE id=1",
                    (gen, now()),
                )
                self.db.invalidate_redo(c)
                self.db.audit(
                    c,
                    "HELPER_PUBLISHED",
                    after={
                        "context_id": ctx,
                        "generation_id": gen,
                        "entities": len(entities),
                        "links": len(links),
                    },
                    operation=op,
                )
            published = True
            stats = client.get(
                "/financial-stats", params=[("date_from", start), ("date_to", end)]
            )
            with self.db.transaction() as c:
                guard(c)
                payload = canonical(stats)
                c.execute(
                    "INSERT OR IGNORE INTO helper_snapshot VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        uid(),
                        ctx,
                        "financial_stats",
                        start + "/" + end,
                        "LIST_ENTITY",
                        request_shape("/financial-stats"),
                        "/financial-stats",
                        payload,
                        digest(stats),
                        now(),
                        op,
                    ),
                )
            self.db.finish_operation(op)
            return {
                "operation_id": op,
                "generation_id": gen,
                "entities": len(entities),
                "links": len(links),
                "status": "READY",
            }
        except Exception as error:
            e = (
                error
                if isinstance(error, AppError)
                else AppError(
                    "SYNC_FAILED",
                    "Synchronizace byla přerušena interní chybou; publikovaná data zůstala zachována.",
                )
            )
            client.fail(client.last_template, e.code)
            with self.db.transaction() as c:
                current = c.execute("SELECT context_id FROM helper_state").fetchone()[0]
                if current == ctx and not published:
                    c.execute(
                        "UPDATE helper_state SET status='STALE',failure_code=?,revision=revision+1 WHERE id=1",
                        (e.code,),
                    )
                    c.execute(
                        "UPDATE helper_generation SET state='ABORTED' WHERE id=?",
                        (gen,),
                    )
            self.db.finish_operation(op, e)
            raise e from None
        finally:
            if compatibility:
                with self.db.transaction() as c:
                    states = []
                    c.execute(
                        "DELETE FROM api_compatibility_endpoint WHERE run_id=?", (op,)
                    )
                    for template in TEMPLATES:
                        s = client.stats.get(
                            template,
                            {
                                "state": "UNEXERCISED"
                                if published
                                else "NOT_ATTEMPTED",
                                "response_count": 0,
                                "item_count": 0,
                                "status_codes": [],
                                "response_hashes": [],
                                "field_types": {},
                                "error_codes": [],
                            },
                        )
                        states.append(s["state"])
                        c.execute(
                            "INSERT INTO api_compatibility_endpoint VALUES(?,?,?,?,?,?,?,?,?)",
                            (
                                op,
                                template,
                                s["state"],
                                s["response_count"],
                                s["item_count"],
                                canonical(s["status_codes"]),
                                canonical(s["response_hashes"]),
                                canonical(s["field_types"]),
                                canonical(s["error_codes"]),
                            ),
                        )
                    status = (
                        "FAILED"
                        if "FAIL" in states or not published
                        else "PASSED"
                        if all(s == "PASS_NONEMPTY" for s in states)
                        else "PARTIAL"
                    )
                    c.execute(
                        "UPDATE api_compatibility_run SET status=?,helper_generation_id=?,finished_at=? WHERE id=?",
                        (status, gen if published else None, now(), op),
                    )

    def entities(self, include_inactive=False, context=None, generation=None):
        st = self.state()
        ctx = context or st["context_id"]
        gen = generation or st["published_generation_id"]
        with self.db.connect() as c:
            return [
                dict(r)
                for r in c.execute(
                    "SELECT h.*,s.payload_json,s.content_hash FROM helper_current h JOIN helper_snapshot s ON s.id=h.snapshot_id AND s.context_id=h.context_id WHERE h.context_id=? AND h.generation_id=?"
                    + ("" if include_inactive else " AND h.active=1"),
                    (ctx, gen),
                )
            ]
