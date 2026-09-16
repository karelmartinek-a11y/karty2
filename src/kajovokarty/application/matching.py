from __future__ import annotations
import json
from kajovokarty.domain.core import digest, require
from kajovokarty.application.auto_run import AutoRun
from kajovokarty.domain.matching import (
    isolated,
    reversals,
)
from kajovokarty.application.work import WorkService
from kajovokarty.domain.matching_windows import business_days, match_date, within, compatible, sum_candidates, cash_reversals


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
        window = settings['matching.business_window_days']
        # Suppress the same leaves across rules and inside larger groups too.
        banned_sets = []
        with self.db.connect() as c:
            active_bans = {r[0] for r in c.execute('SELECT fingerprint FROM auto_suppression WHERE active=1')}
            for group in c.execute('SELECT object_id,evidence_json FROM reconciliation_group'):
                if json.loads(group['evidence_json']).get('fingerprint') not in active_bans:
                    continue
                leaves = c.execute('''WITH RECURSIVE descendants(id) AS (
                    SELECT child_id FROM membership WHERE parent_id=?
                    UNION SELECT m.child_id FROM membership m JOIN descendants d ON m.parent_id=d.id
                ) SELECT d.id FROM descendants d JOIN work_object w ON w.id=d.id WHERE w.type='SOURCE' ''', (group['object_id'],))
                ids = frozenset(r[0] for r in leaves)
                if ids:
                    banned_sets.append(ids)

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
                        if within([r, b], window):
                            candidates.append(frozenset((r["id"], b["id"])))
            return candidates, chains, set(), set()

        def candidates_b_date(rows):
            """Fallback Booking match using checkout date, amount and currency.

            A confirmed Accounts reference remains the stronger source of truth;
            those cashbook rows are intentionally excluded from this fallback.
            """
            index, candidates = {}, []
            run.stage("Booking — shoda data odjezdu, měny a částky", len(rows))
            for r in rows:
                if r["kind"] == "BOOKING":
                    departure = r["payload"].get("departure")
                    if departure:
                        index.setdefault(
                            (departure[:10], r["currency"], r["signed_amount_minor"]),
                            [],
                        ).append(r)
            for r in run.track(rows):
                if r["kind"] != "CASHBOOK_CARD":
                    continue
                if references.get(r["payload"].get("variable_symbol")):
                    continue
                for b in index.get(
                    (r["local_date"], r["currency"], r["signed_amount_minor"]),
                    [],
                ):
                    candidates.append(frozenset((r["id"], b["id"])))
            return candidates

        def commit(rule, candidates, rows, proofs=None, legacy_proofs=None):
            nonlocal created
            lookup = {r["id"]: r for r in rows}
            count = 0
            matches = isolated(candidates)
            accepted = set(matches)
            for candidate in candidates:
                self.db.log.event("AUTO_CANDIDATE", operation_id=run.op, rule_id=rule,
                                  source_ids=sorted(candidate), state="ISOLATED" if candidate in accepted else "AMBIGUOUS")
            names = {
                "A": "Bankovní storna",
                "A_CASH": "Storna pokladny do dvou kalendářních dnů",
                "B_SUM": "Booking a pokladna podle součtu",
                "C_SUM": "Terminál a pokladna podle součtu",
                "B": "Booking a pokladna",
                "B_DATE": "Booking a pokladna podle data odjezdu a částky",
                "C_TERMINAL": "Terminál a pokladna podle částky a pracovních dnů",
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
                if supp or any(ban <= ids for ban in banned_sets):
                    self.db.log.event("AUTO_SUPPRESSED", operation_id=run.op, rule_id=rule, source_ids=sorted(ids))
                    suppressed.update(ids)
                    run.step_done += 1
                    run.emit_progress()
                    continue
                evidence = {
                    "rule_id": rule,
                    "matching_contract": "KK-MATCH-3",
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
                dates = {r['id']: match_date(r) for r in chosen}
                evidence['matching_dates'] = dates
                evidence['business_window_days'] = window
                if rule == 'A_CASH':
                    evidence['calendar_window_days'] = 2
                if all(dates.values()):
                    evidence['business_day_span'] = business_days(min(dates.values()), max(dates.values()))
                evidence['source_totals_minor'] = {
                    kind: sum(r['signed_amount_minor'] for r in chosen if r['kind'] == kind)
                    for kind in {r['kind'] for r in chosen}
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
            cash_stornos = cash_reversals([r for r in rows if r['kind'] == 'CASHBOOK_CARD'], pulse)
            count += commit('A_CASH', cash_stornos, rows)
            rows = self._free()
            bank = [r for r in rows if r["kind"] == "BANK_CARD"]
            run.stage("Bankovní storna — prověřování transakcí", len(bank))
            ac = reversals(bank, pulse, track=run.track)
            count += commit("A", ac, rows)
            rows = self._free()
            bc, chains, unknown, blocked = candidates_b(rows)
            count += commit("B", bc, rows, chains)
            extra_candidates, sum_ambiguous, sum_blocked = [], set(), set()
            for phase_window in dict.fromkeys((0, window)):
                for kind, pair_rule, sum_rule in (('BOOKING', 'B_DATE', 'B_SUM'), ('BANK_CARD', 'C_TERMINAL', 'C_SUM')):
                    def eligible(snapshot):
                        return [r for r in snapshot if r['kind'] == kind or (
                            r['kind'] == 'CASHBOOK_CARD' and (kind != 'BOOKING'
                            or not references.get(r['payload'].get('variable_symbol'))))]

                    rows = self._free()
                    available = eligible(rows)
                    cash = [r for r in available if r['kind'] == 'CASHBOOK_CARD']
                    other = [r for r in available if r['kind'] == kind]
                    pairs = []
                    run.stage('Hledání kandidátů podle částky a pracovních dnů', len(cash), 'pokladních položek')
                    for a in run.track(cash):
                        for index, b in enumerate(other):
                            if index % 1024 == 0:
                                pulse()
                            if (a['currency'] == b['currency']
                                    and a['signed_amount_minor'] == b['signed_amount_minor']
                                    and within([a, b], phase_window) and compatible(a, b)):
                                pairs.append(frozenset((a['id'], b['id'])))
                    extra_candidates.extend(pairs)
                    count += commit(pair_rule, pairs, rows)
                    rows = self._free()
                    run.stage('Hledání vyrovnaných součtových skupin')
                    sums, ambiguous, limited = sum_candidates(
                        eligible(rows), phase_window,
                        settings['matching.max_combination'], settings['matching.max_component_items'],
                        settings['matching.max_search_states'], pulse, run.search_progress)
                    sum_ambiguous.update(ambiguous)
                    sum_blocked.update(limited)
                    if limited:
                        run.limits.add((kind, phase_window, tuple(sorted(limited))))
                    count += commit(sum_rule, sums, rows)
            # Recompute reasons from the actual remaining snapshot on the final round.
            rows = self._free()
            bc, chains, unknown, blocked = candidates_b(rows)
            blocked.update(sum_blocked)
            bdate = candidates_b_date(rows)
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

            free_ids = {r['id'] for r in rows}
            remaining_candidates = {ids for ids in [*ac, *cash_stornos, *bc, *bdate, *extra_candidates] if ids <= free_ids}
            degree = Counter(i for candidate in remaining_candidates for i in candidate)
            ambiguous_ids = {i for candidate in remaining_candidates
                             if any(degree[j] > 1 for j in candidate) for i in candidate}
            ambiguous_ids.update(sum_ambiguous)
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
                elif i in ambiguous_ids:
                    code = "MULTIPLE_CANDIDATES"
                elif (
                    row["kind"] == "CASHBOOK_CARD"
                    and chains.get(i, (None,))[0] == "BOOKING"
                ):
                    ref = chains[i][1]
                    related = [b for b in book if b["payload"]["booking_reference"] == ref]
                    code = ("BOOKING_REFERENCE_NOT_FOUND" if not related else
                            "CURRENCY_MISMATCH" if not any(b["currency"] == row["currency"] for b in related)
                            else "AMOUNT_MISMATCH" if not any(
                                b['currency'] == row['currency']
                                and b['signed_amount_minor'] == row['signed_amount_minor'] for b in related)
                            else "MATCH_DATE_OUTSIDE_WINDOW")
                self.db.log.event("AUTO_UNMATCHED", operation_id=run.op, source_id=i, error_code=code)
                c.execute(
                    "INSERT OR REPLACE INTO work_reason VALUES(?,?,?,?,?)",
                    (i, code, domain_revision, st["revision"], settings_revision),
                )
                run.step_done += 1
                run.emit_progress()
        run.emit_progress(True)
