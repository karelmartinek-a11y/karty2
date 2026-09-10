from __future__ import annotations
import json, time, re
from itertools import combinations
from kajovokarty.domain.core import AppError, canonical, digest, header, require
from kajovokarty.domain.helpers import extract_references, reference_decision
from kajovokarty.domain.matching import (
    bank_edges,
    isolated,
    reversals,
    zero_combinations,
)
from kajovokarty.application.work import WorkService


class MatchingService:
    def __init__(self, db, settings):
        self.db = db
        self.settings = settings
        self.work = WorkService(db)

    def _free(self):
        with self.db.connect() as c:
            rows = [
                dict(r)
                for r in c.execute(
                    "SELECT f.*,w.revision FROM financial_source f JOIN work_object w ON w.source_id=f.id WHERE NOT EXISTS(SELECT 1 FROM membership m WHERE m.child_id=w.id AND m.active=1) ORDER BY f.kind,f.source_identity"
                )
            ]
            for r in rows:
                r["payload"] = json.loads(r["canonical_json"])
                r["contribution"] = r["signed_amount_minor"] * (
                    1 if r["kind"] == "CASHBOOK_CARD" else -1
                )
            return rows

    def _helper(self):
        with self.db.connect() as c:
            st = dict(c.execute("SELECT * FROM helper_state").fetchone())
            ctx = st["context_id"]
            gen = st["published_generation_id"]
            entities = {
                (r["resource_type"], r["external_id"]): {
                    **dict(r),
                    "payload": json.loads(r["payload_json"]),
                }
                for r in c.execute(
                    "SELECT h.*,s.payload_json,s.content_hash FROM helper_current h JOIN helper_snapshot s ON s.id=h.snapshot_id AND s.context_id=h.context_id WHERE h.context_id=? AND h.generation_id=? AND h.active=1 AND h.complete=1",
                    (ctx, gen),
                )
            }
            links = [
                dict(r)
                for r in c.execute(
                    "SELECT * FROM helper_link WHERE context_id=? AND generation_id=? AND active=1 AND complete=1",
                    (ctx, gen),
                )
            ]
            overrides = {
                r["reservation_id"]: dict(r)
                for r in c.execute(
                    "SELECT * FROM helper_override WHERE context_id=?", (ctx,)
                )
            }
            coverage = [
                dict(r)
                for r in c.execute(
                    "SELECT * FROM sync_coverage WHERE context_id=? AND generation_id=? AND complete=1",
                    (ctx, gen),
                )
            ]
            return st, entities, links, overrides, coverage

    def run(self, cancel=None, progress=None):
        with self.db.operation_gate(cancel, progress):
            return self._run(cancel, progress)

    def _run(self, cancel, progress):
        last_pulse = 0.0

        def pulse():
            nonlocal last_pulse
            require(
                not (cancel and cancel.is_set()), "CANCELLED", "Párování bylo zrušeno."
            )
            current = time.monotonic()
            if progress and current - last_pulse >= 1:
                progress("Prohledávám kandidáty automatického párování…")
                last_pulse = current

        pulse()
        op = self.db.start_operation("AUTO_MATCH")
        settings = self.settings.get()
        st, entities, links, overrides, coverage = self._helper()
        rounds = created = 0
        limits = set()
        suppressed = set()
        chain_reasons = {}
        require(
            st["status"] != "REFRESHING",
            "STALE_STATE",
            "Nejprve dokončete načítání pomocných dat.",
        )

        def chain(row):
            def unknown(code):
                chain_reasons[row["id"]] = code
                return ("UNKNOWN", None, None)

            if st["status"] != "READY":
                return unknown("HELPER_DATA_NOT_SYNCED")
            if not all(
                any(
                    c["resource_type"] == kind
                    and c["range_start"] <= row["local_date"] <= c["range_end"]
                    for c in coverage
                )
                for kind in ("invoice", "reservation")
            ):
                return unknown("HELPER_DATA_NOT_SYNCED")
            p = row["payload"]
            tokens = {
                header(t)
                for t in re.findall(r"[\w/\-]+", p.get("label") or "", re.UNICODE)
            } | {
                header(p.get("invoice_code")),
                header(p.get("variable_symbol")),
                header(p.get("label")),
            }
            invoices = [
                e
                for (k, i), e in entities.items()
                if k == "invoice"
                and header(e["payload"].get("code")) in tokens
                and e["payload"].get("code")
            ]
            if len(invoices) != 1:
                return unknown(
                    "MULTIPLE_CANDIDATES" if invoices else "CASHBOOK_NO_DOCUMENT"
                )
            invoice = invoices[0]
            if invoice["payload"].get("currency") not in (None, row["currency"]):
                return unknown("CURRENCY_MISMATCH")
            rs = [
                l
                for l in links
                if l["relation"] == "INVOICE"
                and l["to_id"] == invoice["external_id"]
                and l["from_type"] == "reservation"
            ]
            if not rs:
                return (
                    "OTHER",
                    None,
                    {
                        "context_id": st["context_id"],
                        "invoice": invoice["content_hash"],
                        "helper_provenance": {
                            "context_id": st["context_id"],
                            "generation_id": st["published_generation_id"],
                            "evidence_epoch": st["evidence_epoch"],
                            "entities": [
                                {
                                    "resource_type": "invoice",
                                    "external_id": invoice["external_id"],
                                    "snapshot_id": invoice["snapshot_id"],
                                    "content_hash": invoice["content_hash"],
                                }
                            ],
                            "links": [],
                            "reference_decision": None,
                        },
                    },
                )
            if len(rs) != 1:
                return unknown("DOCUMENT_NO_RESERVATION")
            reservation = entities.get(("reservation", rs[0]["from_id"]))
            if not reservation:
                return unknown("HELPER_ENTITY_NOT_OBSERVED")
            rp = reservation["payload"]
            channel = rp.get("reservation_source") or {}
            channel = channel.get("name") if isinstance(channel, dict) else None
            if not channel:
                return unknown("RESERVATION_NO_BOOKING_REFERENCE")
            ref = extract_references(rp.get("reservation_note"), channel)
            override = overrides.get(reservation["external_id"])
            decision = reference_decision(ref, override)
            proof = {
                "context_id": st["context_id"],
                "invoice": invoice["content_hash"],
                "reservation": reservation["content_hash"],
                "decision": decision,
                "helper_provenance": {
                    "context_id": st["context_id"],
                    "generation_id": st["published_generation_id"],
                    "evidence_epoch": st["evidence_epoch"],
                    "entities": [
                        {
                            "resource_type": e["resource_type"],
                            "external_id": e["external_id"],
                            "snapshot_id": e["snapshot_id"],
                            "content_hash": e["content_hash"],
                        }
                        for e in (invoice, reservation)
                    ],
                    "links": rs,
                    "reference_decision": {
                        **decision,
                        "override_command_id": override["command_id"]
                        if override and decision["resolution_status"] == "MANUAL_ACCEPT"
                        else None,
                    },
                },
            }
            if decision["resolution_status"] in ("MANUAL_ACCEPT", "AUTO_CONFIRMED"):
                return ("BOOKING", decision["effective_candidate"], proof)
            if ref["channel_name"] != "booking.com":
                return ("OTHER", None, proof)
            return unknown(
                {
                    "REJECTED": "BOOKING_REFERENCE_REJECTED",
                    "REVIEW_REQUIRED": "BOOKING_REFERENCE_REVIEW_REQUIRED",
                }.get(decision["resolution_status"], "RESERVATION_NO_BOOKING_REFERENCE")
            )

        def candidates_b(rows):
            components = {}
            chains = {}
            unknown = set()
            allc = []
            blocked = set()
            for r in rows:
                if r["kind"] == "CASHBOOK_CARD":
                    ch = chain(r)
                    chains[r["id"]] = ch
                    if ch[0] == "UNKNOWN":
                        unknown.add(r["currency"])
                    if ch[0] != "BOOKING":
                        continue
                    key = (ch[1], r["currency"])
                elif r["kind"] == "BOOKING":
                    key = (r["payload"]["booking_reference"], r["currency"])
                else:
                    continue
                components.setdefault(key, []).append(r)
            if st["status"] != "READY":
                return [], chains, unknown, blocked
            for key, items in sorted(components.items()):
                found, limit, states = zero_combinations(
                    items,
                    settings["matching.max_combination"],
                    settings["matching.max_component_items"],
                    settings["matching.max_search_states"],
                    pulse=pulse,
                )
                if limit:
                    limits.add(key)
                    blocked.update(r["id"] for r in items)
                else:
                    allc.extend(found)
            return allc, chains, unknown, blocked

        def commit(rule, candidates, rows, proofs=None):
            nonlocal created
            lookup = {r["id"]: r for r in rows}
            count = 0
            for ids in isolated(candidates):
                require(
                    not (cancel and cancel.is_set()),
                    "CANCELLED",
                    "Párování bylo zrušeno.",
                )
                chosen = sorted(
                    (lookup[i] for i in ids),
                    key=lambda r: (r["kind"], r["source_identity"]),
                )
                proof = [
                    proofs[i][2]
                    for i in sorted(ids)
                    if proofs and i in proofs and proofs[i][2]
                ]

                def content_only(value):
                    if isinstance(value, dict):
                        return {
                            k: content_only(v)
                            for k, v in value.items()
                            if k
                            not in (
                                "helper_provenance",
                                "generation_id",
                                "evidence_epoch",
                            )
                        }
                    if isinstance(value, list):
                        return [content_only(v) for v in value]
                    return value

                hashproof = [content_only(p) for p in proof]
                evidence_hash = digest(
                    hashproof if proof else [r["payload"] for r in chosen]
                )
                finger = digest(
                    {
                        "rule_id": rule,
                        "leaves": [
                            [r["kind"], r["source_identity"], r["content_hash"]]
                            for r in chosen
                        ],
                        "evidence_hash": evidence_hash,
                    }
                )
                with self.db.connect() as c:
                    supp = c.execute(
                        "SELECT active FROM auto_suppression WHERE fingerprint=?",
                        (finger,),
                    ).fetchone()
                if supp and supp[0]:
                    suppressed.update(ids)
                    continue
                evidence = {
                    "rule_id": rule,
                    "fingerprint": finger,
                    "evidence_hash": evidence_hash,
                    "helper_provenance": [
                        p["helper_provenance"]
                        for p in proof
                        if "helper_provenance" in p
                    ]
                    or None,
                }
                self.work.create_group(
                    [r["id"] for r in chosen],
                    {r["id"]: r["revision"] for r in chosen},
                    require_zero=True,
                    method="AUTO",
                    evidence=evidence,
                )
                count += 1
                created += 1
                if progress:
                    progress(f"Automatické párování: kolo {rounds}, skupin {created}")
            return count

        try:
            while True:
                rounds += 1
                count = 0
                require(
                    not (cancel and cancel.is_set()),
                    "CANCELLED",
                    "Párování bylo zrušeno.",
                )
                rows = self._free()
                count += commit(
                    "A",
                    reversals([r for r in rows if r["kind"] == "BANK_CARD"], pulse),
                    rows,
                )
                rows = self._free()
                bc, chains, unknown, blocked = candidates_b(rows)
                count += commit("B", bc, rows, chains)
                rows = self._free()
                cash = [r for r in rows if r["kind"] == "CASHBOOK_CARD"]
                bank = [r for r in rows if r["kind"] == "BANK_CARD"]
                strong = bank_edges(
                    cash, bank, settings["matching.bank_window_days"], pulse=pulse
                )
                count += commit("C_STRONG", strong, rows)
                rows = self._free()
                cash = [r for r in rows if r["kind"] == "CASHBOOK_CARD"]
                bank = [r for r in rows if r["kind"] == "BANK_CARD"]
                strong = bank_edges(
                    cash, bank, settings["matching.bank_window_days"], pulse=pulse
                )
                incident = set().union(*strong) if strong else set()
                chains = {r["id"]: chain(r) for r in cash}
                weak = bank_edges(
                    [r for r in cash if r["id"] not in incident],
                    [r for r in bank if r["id"] not in incident],
                    settings["matching.bank_window_days"],
                    False,
                    lambda r: chains[r["id"]][0] == "OTHER",
                    pulse=pulse,
                )
                count += commit("C_WEAK", weak, rows, chains)
                rows = self._free()
                bc, chains, unknown, blocked = candidates_b(rows)
                incident = (set().union(*bc) if bc else set()) | blocked
                book = [r for r in rows if r["kind"] == "BOOKING"]
                d = []
                if st["status"] == "READY":
                    by_reference = {}
                    for r in book:
                        by_reference.setdefault(
                            (r["currency"], r["payload"]["booking_reference"]), []
                        ).append(r)
                    for a, b in (
                        pair
                        for group in by_reference.values()
                        for pair in combinations(group, 2)
                    ):
                        pulse()
                        if (
                            a["currency"] in unknown
                            or a["id"] in incident
                            or b["id"] in incident
                        ):
                            continue
                        if (
                            a["currency"] == b["currency"]
                            and a["payload"]["booking_reference"]
                            == b["payload"]["booking_reference"]
                            and a["signed_amount_minor"] == -b["signed_amount_minor"]
                        ):
                            d.append(frozenset((a["id"], b["id"])))
                dproof = {
                    r["id"]: (
                        "ABSENCE",
                        None,
                        {
                            "context_id": st["context_id"],
                            "cash_chains": sorted(
                                [v[2] for v in chains.values() if v[2]], key=canonical
                            ),
                            "helper_provenance": {
                                "context_id": st["context_id"],
                                "generation_id": st["published_generation_id"],
                                "evidence_epoch": st["evidence_epoch"],
                                "entities": [],
                                "links": [],
                                "reference_decision": None,
                            },
                        },
                    )
                    for r in book
                }
                count += commit("D", d, rows, dproof)
                if not count:
                    break
            result = {
                "rounds": rounds,
                "created_groups": created,
                "reached_fixed_point": True,
                "limited_components": len(limits),
            }
            with self.db.transaction() as c:
                domain_revision = c.execute(
                    "SELECT revision FROM domain_clock"
                ).fetchone()[0]
                settings_revision = c.execute(
                    "SELECT coalesce(sum(revision),0) FROM setting"
                ).fetchone()[0]
                from collections import Counter

                degree = Counter(
                    i for candidate in [*bc, *strong, *weak, *d] for i in candidate
                )
                for row in rows:
                    i = row["id"]
                    code = (
                        chain_reasons.get(i)
                        or {
                            "BOOKING": "BOOKING_NO_COUNTERPART",
                            "BANK_CARD": "BANK_NO_COUNTERPART",
                            "CASHBOOK_CARD": "CASHBOOK_NO_COUNTERPART",
                        }[row["kind"]]
                    )
                    if i in suppressed:
                        code = "AUTO_SUPPRESSED"
                    elif i in blocked:
                        code = "AUTO_SEARCH_LIMIT"
                    elif degree[i] > 1:
                        code = "MULTIPLE_CANDIDATES"
                    elif (
                        row["kind"] == "CASHBOOK_CARD"
                        and chains.get(i, (None,))[0] == "BOOKING"
                    ):
                        ref = chains[i][1]
                        code = (
                            "AMOUNT_MISMATCH"
                            if any(
                                b["payload"]["booking_reference"] == ref for b in book
                            )
                            else "BOOKING_REFERENCE_NOT_FOUND"
                        )
                    c.execute(
                        "INSERT OR REPLACE INTO work_reason VALUES(?,?,?,?,?)",
                        (i, code, domain_revision, st["revision"], settings_revision),
                    )
                self.db.audit(c, "AUTO_FINISHED", after=result, operation=op)
            self.db.finish_operation(op)
            return result
        except AppError as e:
            self.db.finish_operation(op, e)
            raise
