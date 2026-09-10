from __future__ import annotations
import json, re, unicodedata
from itertools import combinations
from kajovokarty.domain.core import canonical, digest, require
from kajovokarty.application.auto_run import AutoRun
from kajovokarty.domain.helpers import extract_references, reference_decision
from kajovokarty.domain.matching import (
    bank_edges,
    isolated,
    reversals,
    terminal_edges,
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
                    "SELECT f.*,w.revision FROM financial_source f JOIN work_object w ON w.source_id=f.id WHERE w.lifecycle='ACTIVE' AND f.signed_amount_minor!=0 AND NOT EXISTS(SELECT 1 FROM membership m WHERE m.child_id=w.id AND m.active=1) ORDER BY f.kind,f.source_identity"
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
                    "SELECT h.*,s.payload_json,s.content_hash FROM helper_current h JOIN helper_snapshot s ON s.id=h.snapshot_id AND s.context_id=h.context_id WHERE h.context_id=? AND h.generation_id=? ",
                    (ctx, gen),
                )
            }
            links = [
                dict(r)
                for r in c.execute(
                    "SELECT * FROM helper_link WHERE context_id=? AND generation_id=? ",
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
            return AutoRun(self.db, self.settings, cancel, progress).execute(self._run)

    def _run(self, run):
        cancel, pulse = run.cancel, run.pulse
        settings = run.settings
        run.stage("Načítání pomocných dokladů a rezervací")
        st, entities, links, overrides, coverage = self._helper()
        require(
            st["status"] != "REFRESHING",
            "STALE_STATE",
            "Nejprve dokončete načítání pomocných dat.",
        )
        if st["status"] == "READY":
            with self.db.connect() as c:
                valid = c.execute(
                    "SELECT 1 FROM helper_context h JOIN helper_generation g ON g.context_id=h.id WHERE h.id=? AND h.status='CURRENT' AND h.credential_revision=? AND g.id=? AND g.state='PUBLISHED' AND g.credential_revision=h.credential_revision",
                    (
                        st["context_id"],
                        st["credential_revision"],
                        st["published_generation_id"],
                    ),
                ).fetchone()
            require(
                valid,
                "STALE_STATE",
                "Publikovaný pomocný graf neodpovídá aktuálnímu připojení.",
            )
        run.stage("Načítání nespárovaných zdrojových položek")
        initial = self._free()
        run.inputs = {r["id"]: r["content_hash"] for r in initial}
        run.analyzed.update(r["currency"] for r in initial)
        run.inputs_loaded = True
        rounds = created = 0
        limits = run.limits
        suppressed = set()
        chain_reasons = {}

        def code_key(value):
            return unicodedata.normalize("NFKC", str(value or "")).casefold()

        invoice_index = {}
        invoice_links = {}
        chain_cache = {}
        run.stage("Indexace pomocných dokladů", len(entities), "dokladů a rezervací")
        for entity in run.track(entities.values()):
            pulse()
            if (
                entity["resource_type"] == "invoice"
                and entity["active"]
                and entity["complete"]
            ):
                key = code_key(entity["payload"].get("code"))
                if key:
                    invoice_index.setdefault(key, {})[entity["external_id"]] = entity
        run.stage("Indexace vazeb dokladů", len(links), "vazeb")
        for link in run.track(links):
            pulse()
            if (
                link["relation"] == "INVOICE"
                and link["from_type"] == "reservation"
                and link["to_type"] == "invoice"
            ):
                invoice_links.setdefault(link["to_id"], []).append(link)

        def chain(row):
            if row["id"] not in chain_cache:
                chain_cache[row["id"]] = resolve_chain(row)
            return chain_cache[row["id"]]

        def resolve_chain(row):
            def unknown(code):
                chain_reasons[row["id"]] = code
                run.unknown.add(row["id"])
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
                code_key(t)
                for t in re.findall(r"[\w/\-]+", p.get("label") or "", re.UNICODE)
            } | {
                code_key(p.get("invoice_code")),
                code_key(p.get("variable_symbol")),
                code_key(p.get("label")),
            }
            invoices = list(
                {
                    identity: entity
                    for token in tokens
                    for identity, entity in invoice_index.get(token, {}).items()
                }.values()
            )
            if len(invoices) != 1:
                return unknown(
                    "MULTIPLE_CANDIDATES" if invoices else "CASHBOOK_NO_DOCUMENT"
                )
            invoice = invoices[0]
            if invoice["payload"].get("currency") not in (None, row["currency"]):
                return unknown("CURRENCY_MISMATCH")
            rs = invoice_links.get(invoice["external_id"], [])
            if any(not l["active"] or not l["complete"] for l in rs):
                return unknown("HELPER_ENTITY_NOT_OBSERVED")
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
            if (
                not reservation
                or not reservation["active"]
                or not reservation["complete"]
            ):
                return unknown("HELPER_ENTITY_NOT_OBSERVED")
            rp = reservation["payload"]
            if rp.get("currency") not in (None, row["currency"]):
                return unknown("CURRENCY_MISMATCH")
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
            pulse()
            components = {}
            chains = {}
            unknown = set()
            allc = []
            blocked = set()
            run.stage("Booking — ověřování řetězců a sestavení kandidátů", len(rows))
            for r in run.track(rows):
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
            run.stage(
                "Booking — prohledávání kombinací částek",
                len(components),
                "skupin kandidátů",
            )
            for key, items in run.track(sorted(components.items())):
                if {r["kind"] for r in items} != {"CASHBOOK_CARD", "BOOKING"}:
                    continue  # Absence of one side proves B impossible without a search.
                run.search_progress(0)
                found, limit, states = zero_combinations(
                    items,
                    settings["matching.max_combination"],
                    settings["matching.max_component_items"],
                    settings["matching.max_search_states"],
                    pulse=pulse,
                    search_progress=run.search_progress,
                )
                if limit:
                    limits.add(key)
                    blocked.update(r["id"] for r in items)
                else:
                    allc.extend(found)
            return allc, chains, unknown, blocked

        def commit(rule, candidates, rows, proofs=None, legacy_proofs=None):
            nonlocal created
            lookup = {r["id"]: r for r in rows}
            count = 0
            matches = isolated(candidates)
            names = {
                "A": "Bankovní storna",
                "B": "Booking a pokladna",
                "C_TERMINAL": "TerminĂˇl a pokladna podle dne a ÄŤĂˇstky",
                "C_STRONG": "Banka se shodným VS",
                "C_WEAK": "Banka podle částky a dokladů",
                "D": "Protizápisy Bookingu",
            }
            run.stage(
                names[rule] + " — kontrola důkazů a zápis shod",
                len(matches),
                "kandidátních skupin",
            )
            for ids in matches:
                pulse()
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
                    proofs[r["id"]][2]
                    for r in chosen
                    if proofs and r["id"] in proofs and proofs[r["id"]][2]
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
                # 0.3.0 used UUID order for proof arrays. Honor its existing
                # suppressions while writing canonical source-order fingerprints.
                old_proofs = legacy_proofs or proofs
                old_proof = [
                    old_proofs[i][2]
                    for i in sorted(ids)
                    if old_proofs and i in old_proofs and old_proofs[i][2]
                ]
                old_hash = digest(
                    [content_only(p) for p in old_proof]
                    if old_proof
                    else [r["payload"] for r in chosen]
                )
                old_finger = digest(
                    {
                        "rule_id": rule,
                        "leaves": [
                            [r["kind"], r["source_identity"], r["content_hash"]]
                            for r in chosen
                        ],
                        "evidence_hash": old_hash,
                    }
                )
                with self.db.connect() as c:
                    supp = c.execute(
                        "SELECT 1 FROM auto_suppression WHERE fingerprint IN (?,?) AND active=1",
                        (finger, old_finger),
                    ).fetchone()
                if supp:
                    suppressed.update(ids)
                    run.step_done += 1
                    run.emit_progress()
                    continue
                evidence = {
                    "rule_id": rule,
                    "auto_run_id": run.op,
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
                    auto_context=run,
                )
                run.step_done += 1
                run.record(rule, chosen)
                count += 1
                created += 1
            run.emit_progress(True)
            return count

        while True:
            rounds += 1
            run.rounds = rounds
            pulse()
            count = 0
            require(
                not (cancel and cancel.is_set()),
                "CANCELLED",
                "Párování bylo zrušeno.",
            )
            rows = self._free()
            bank = [r for r in rows if r["kind"] == "BANK_CARD"]
            run.stage("Bankovní storna — prověřování transakcí", len(bank))
            ac = reversals(bank, pulse, track=run.track)
            count += commit("A", ac, rows)
            rows = self._free()
            cash = [r for r in rows if r["kind"] == "CASHBOOK_CARD"]
            bank = [r for r in rows if r["kind"] == "BANK_CARD"]
            run.stage(
                "TerminĂˇl â€” hledĂˇnĂ­ shod podle dne, mÄ›ny a ÄŤĂˇstky",
                len(cash),
                "pokladnĂ­ch poloĹľek",
            )
            terminal = terminal_edges(cash, bank, pulse=pulse, track=run.track)
            count += commit("C_TERMINAL", terminal, rows)
            rows = self._free()
            bc, chains, unknown, blocked = candidates_b(rows)
            count += commit("B", bc, rows, chains)
            rows = self._free()
            cash = [r for r in rows if r["kind"] == "CASHBOOK_CARD"]
            bank = [r for r in rows if r["kind"] == "BANK_CARD"]
            run.stage(
                "Banka — hledání přesné shody VS a částky",
                len(cash),
                "pokladních položek",
            )
            strong = bank_edges(
                cash,
                bank,
                settings["matching.bank_window_days"],
                pulse=pulse,
                track=run.track,
            )
            count += commit("C_STRONG", strong, rows)
            rows = self._free()
            cash = [r for r in rows if r["kind"] == "CASHBOOK_CARD"]
            bank = [r for r in rows if r["kind"] == "BANK_CARD"]
            run.stage(
                "Banka — hledání přesné shody VS a částky",
                len(cash),
                "pokladních položek",
            )
            strong = bank_edges(
                cash,
                bank,
                settings["matching.bank_window_days"],
                pulse=pulse,
                track=run.track,
            )
            incident = set().union(*strong) if strong else set()
            run.stage(
                "Banka — ověření pomocných dokladů", len(cash), "pokladních položek"
            )
            chains = {r["id"]: chain(r) for r in run.track(cash)}
            weak_cash = [r for r in cash if r["id"] not in incident]
            run.stage(
                "Banka — hledání shod podle částky a dokladů",
                len(weak_cash),
                "pokladních položek",
            )
            weak = bank_edges(
                weak_cash,
                [r for r in bank if r["id"] not in incident],
                settings["matching.bank_window_days"],
                False,
                lambda r: chains[r["id"]][0] == "OTHER",
                pulse=pulse,
                track=run.track,
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
                run.stage(
                    "Booking — prověřování protizápisů",
                    sum(len(g) * (len(g) - 1) // 2 for g in by_reference.values()),
                    "dvojic",
                )
                for a, b in run.track(
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
                            [
                                chains[x["id"]][2]
                                for x in rows
                                if x["kind"] == "CASHBOOK_CARD"
                                and x["currency"] == r["currency"]
                                and chains[x["id"]][2]
                            ],
                            key=canonical,
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
            legacy_dproof = {
                i: (
                    kind,
                    ref,
                    {
                        **proof,
                        "cash_chains": sorted(
                            [v[2] for v in chains.values() if v[2]], key=canonical
                        ),
                    },
                )
                for i, (kind, ref, proof) in dproof.items()
            }
            count += commit("D", d, rows, dproof, legacy_dproof)
            if not count:
                break
        run.stage("Ukládání důvodů zbývajících nespárovaných položek", len(rows))
        with self.db.transaction() as c:
            run.validate(c)
            domain_revision = c.execute("SELECT revision FROM domain_clock").fetchone()[
                0
            ]
            settings_revision = c.execute(
                "SELECT coalesce(sum(revision),0) FROM setting"
            ).fetchone()[0]
            from collections import Counter

            degree = Counter(
                i for candidate in [*ac, *bc, *strong, *weak, *d] for i in candidate
            )
            for row in rows:
                run.check_cancel()
                i = row["id"]
                code = (
                    chain_reasons.get(i)
                    or {
                        "BOOKING": "BOOKING_NO_COUNTERPART",
                        "BANK_CARD": "BANK_NO_COUNTERPART",
                        "CASHBOOK_CARD": "CASHBOOK_NO_COUNTERPART",
                    }[row["kind"]]
                )
                if row["kind"] == "BOOKING" and (
                    st["status"] != "READY" or row["currency"] in unknown
                ):
                    code = (
                        "HELPER_DATA_NOT_SYNCED"
                        if st["status"] != "READY"
                        else "HELPER_CHAIN_UNVERIFIED"
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
                        if any(b["payload"]["booking_reference"] == ref for b in book)
                        else "BOOKING_REFERENCE_NOT_FOUND"
                    )
                c.execute(
                    "INSERT OR REPLACE INTO work_reason VALUES(?,?,?,?,?)",
                    (i, code, domain_revision, st["revision"], settings_revision),
                )
                run.step_done += 1
                run.emit_progress()
        run.emit_progress(True)
