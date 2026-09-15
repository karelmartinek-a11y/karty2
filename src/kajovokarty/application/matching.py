from __future__ import annotations
import json
from kajovokarty.domain.core import digest, require
from kajovokarty.application.auto_run import AutoRun
from kajovokarty.domain.matching import (
    bank_edges,
    isolated,
    reversals,
    terminal_edges,
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

    def run(self, cancel=None, progress=None):
        with self.db.operation_gate(cancel, progress):
            return AutoRun(self.db, self.settings, cancel, progress).execute(self._run)

    def _run(self, run):
        cancel, pulse = run.cancel, run.pulse
        settings = run.settings
        run.stage("Načítání vazeb z Účtů")
        with self.db.connect() as c:
            st = dict(c.execute("SELECT * FROM helper_state").fetchone())
            references = {}
            for r in c.execute("SELECT s.*,a.booking_reference FROM account_symbol s JOIN account_reservation a USING(reservation)"):
                references.setdefault(r["variable_symbol"], []).append(dict(r))
        run.stage("Načítání nespárovaných zdrojových položek")
        initial = self._free()
        run.inputs = {r["id"]: r["content_hash"] for r in initial}
        run.analyzed.update(r["currency"] for r in initial)
        run.inputs_loaded = True
        rounds = created = 0
        suppressed = set()
        chain_reasons = {}

        def chain(row):
            matches = references.get(row["payload"].get("variable_symbol"), [])
            if len(matches) != 1:
                run.unknown.add(row["id"])
                chain_reasons[row["id"]] = "MULTIPLE_CANDIDATES" if matches else "ACCOUNTS_REFERENCE_MISSING"
                return ("UNKNOWN", None, None)
            ref = matches[0]
            return ("BOOKING", ref["booking_reference"], {"accounts_provenance": ref})

        def candidates_b(rows):
            chains, index, candidates = {}, {}, []
            run.stage("Booking — přesná shoda VS, rezervace, měny a částky", len(rows))
            for r in rows:
                if r["kind"] == "BOOKING":
                    index.setdefault((r["payload"]["booking_reference"], r["currency"], r["signed_amount_minor"]), []).append(r)
            for r in run.track(rows):
                if r["kind"] != "CASHBOOK_CARD":
                    continue
                ch = chains[r["id"]] = chain(r)
                if ch[0] == "BOOKING":
                    for b in index.get((ch[1], r["currency"], r["signed_amount_minor"]), []):
                        candidates.append(frozenset((r["id"], b["id"])))
            return candidates, chains, set(), set()

        def commit(rule, candidates, rows, proofs=None, legacy_proofs=None):
            nonlocal created
            lookup = {r["id"]: r for r in rows}
            count = 0
            matches = isolated(candidates)
            names = {
                "A": "Bankovní storna",
                "B": "Booking a pokladna",
                "C_TERMINAL": "Terminál a pokladna podle dne a částky",
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
                fingerprints = {finger, old_finger}
                if rule in ("C_TERMINAL", "C_STRONG"):
                    # The same financial pair must not bypass a manual ban by
                    # falling through from the terminal rule to the VS rule.
                    fingerprints.add(digest({
                        "rule_id": "C_STRONG" if rule == "C_TERMINAL" else "C_TERMINAL",
                        "leaves": [[r["kind"], r["source_identity"], r["content_hash"]] for r in chosen],
                        "evidence_hash": evidence_hash,
                    }))
                with self.db.connect() as c:
                    supp = c.execute(
                        "SELECT 1 FROM auto_suppression WHERE fingerprint IN (" + ",".join("?" for _ in fingerprints) + ") AND active=1",
                        tuple(fingerprints),
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
                    "accounts_provenance": [p["accounts_provenance"] for p in proof if "accounts_provenance" in p] or None,
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
                "Terminál — hledání shod podle dne, měny a částky",
                len(cash),
                "pokladních položek",
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
            # Weak bank and Booking reversal rules relied on retired API evidence.
            weak, d = [], []
            bc, chains, unknown, blocked = candidates_b(rows)
            book = [r for r in rows if r["kind"] == "BOOKING"]
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
