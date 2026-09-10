"""Lifecycle, immutable run inputs and truthful partial results for automatic matching."""

import sqlite3
import time
from collections import Counter
from kajovokarty.domain.core import AppError, canonical, now, require
from kajovokarty.application.work import WorkService


class AutoProgress(str):
    """A backward-compatible message carrying an immutable progress snapshot."""

    def __new__(cls, message, snapshot):
        value = super().__new__(cls, message)
        value.snapshot = snapshot
        return value


class AutoRun:
    def __init__(self, db, settings, cancel=None, progress=None):
        self.db, self.settings_service = db, settings
        self.cancel, self.progress = cancel, progress
        self.rounds = self.created = self.resolved = 0
        self.analyzed = Counter()
        self.created_by_currency = Counter()
        self.resolved_by_currency = Counter()
        self.rules = Counter()
        self.limits = set()
        self.unknown = set()
        self.last_pulse = 0.0
        self.inputs = {}
        self.inputs_loaded = False
        self.guard = None
        self.stage_label = "Příprava nastavení a podkladů"
        self.step_total = None
        self.step_done = 0
        self.unit = "položek"
        self.last_event = 0.0
        self.search_states = None

    @staticmethod
    def signature(c):
        helper = dict(c.execute("SELECT * FROM helper_state").fetchone())
        context = c.execute(
            "SELECT id,status,credential_revision FROM helper_context WHERE id=?",
            (helper["context_id"],),
        ).fetchone()
        generation = c.execute(
            "SELECT id,context_id,credential_revision,state,graph_hash FROM helper_generation WHERE id=?",
            (helper["published_generation_id"],),
        ).fetchone()
        return {
            "context": tuple(context) if context else None,
            "generation": tuple(generation) if generation else None,
            "domain": c.execute(
                "SELECT revision FROM domain_clock WHERE id=1"
            ).fetchone()[0],
            "helper": helper,
            "settings": [
                tuple(r)
                for r in c.execute(
                    "SELECT key,value_json,revision FROM setting WHERE key LIKE 'matching.%' ORDER BY key"
                )
            ],
            "suppression": [
                tuple(r)
                for r in c.execute(
                    "SELECT fingerprint,active,revision FROM auto_suppression ORDER BY fingerprint"
                )
            ],
        }

    def check_cancel(self):
        require(
            not (self.cancel and self.cancel.is_set()),
            "CANCELLED",
            "Párování bylo zrušeno; již dokončené skupiny zůstávají zachovány.",
        )

    def emit_progress(self, force=False):
        current = time.monotonic()
        if not self.progress or (not force and current - self.last_event < 0.2):
            return
        total = sum(self.analyzed.values())
        self.progress(
            AutoProgress(
                f"Automatické párování: kolo {self.rounds}, skupin {self.created}; {self.stage_label}",
                {
                    "stage": self.stage_label,
                    "step_total": self.step_total,
                    "step_done": self.step_done,
                    "unit": self.unit,
                    "total": total,
                    "inputs_loaded": self.inputs_loaded,
                    "resolved": self.resolved,
                    "remaining": total - self.resolved,
                    "groups": self.created,
                    "round": self.rounds,
                    "search_states": self.search_states,
                    "limits": len(self.limits),
                    "currencies": {
                        cur: {
                            "resolved": self.resolved_by_currency[cur],
                            "remaining": self.analyzed[cur]
                            - self.resolved_by_currency[cur],
                        }
                        for cur in ("CZK", "EUR")
                    },
                },
            )
        )
        self.last_event = current

    def stage(self, label, total=None, unit="položek"):
        self.stage_label, self.step_total, self.unit = label, total, unit
        self.step_done = 0
        self.search_states = None
        self.check_cancel()
        self.emit_progress(True)

    def search_progress(self, states):
        self.search_states = states
        self.emit_progress()

    def track(self, items):
        for item in items:
            self.pulse()
            yield item
            self.step_done += 1
            self.emit_progress()
        self.emit_progress(True)

    def pulse(self):
        self.check_cancel()
        current = time.monotonic()
        if current - self.last_pulse >= 1:
            with self.db.transaction() as c:
                c.execute(
                    "UPDATE operation SET heartbeat_at=?,progress_current=?,progress_total=? WHERE id=?",
                    (now(), self.resolved, sum(self.analyzed.values()), self.op),
                )
            self.last_pulse = current
            self.check_cancel()
        self.emit_progress()

    def validate(self, c, ids=()):
        self.check_cancel()
        require(
            self.guard == self.signature(c),
            "STALE_STATE",
            "Data, důkazy nebo pravidla se během párování změnila. Spusťte nový běh.",
        )
        for identity in ids:
            row = c.execute(
                "SELECT content_hash FROM financial_source WHERE id=?", (identity,)
            ).fetchone()
            require(
                row and row[0] == self.inputs.get(identity),
                "STALE_STATE",
                "Zdrojový důkaz již neodpovídá snímku běhu.",
            )

    def accept_commit(self, c):
        # Called inside the financial transaction, after all its domain writes.
        # No concurrent write can be silently accepted between COMMIT and a read.
        self.guard["domain"] = c.execute(
            "SELECT revision FROM domain_clock WHERE id=1"
        ).fetchone()[0]

    def record(self, rule, rows):
        self.created += 1
        self.resolved += len(rows)
        currency = rows[0]["currency"]
        self.created_by_currency[currency] += 1
        self.resolved_by_currency[currency] += len(rows)
        self.rules[rule] += 1
        self.emit_progress(True)

    def summary(self, fixed_point):
        kpi = WorkService(self.db).query({"status": "unresolved"}, page_size=1)["kpi"]
        free = Counter()
        reasons = {cur: Counter() for cur in ("CZK", "EUR")}
        with self.db.connect() as c:
            for row in c.execute(
                "SELECT f.currency,r.code FROM financial_source f JOIN work_object w ON w.source_id=f.id LEFT JOIN work_reason r ON r.object_id=w.id WHERE w.lifecycle='ACTIVE' AND f.signed_amount_minor!=0 AND NOT EXISTS(SELECT 1 FROM membership m WHERE m.child_id=w.id AND m.active=1)"
            ):
                free[row["currency"]] += 1
                reasons[row["currency"]][
                    row["code"]
                    if fixed_point and row["code"]
                    else "RUN_NOT_COMPLETED"
                    if not fixed_point
                    else "NOT_MATCHED"
                ] += 1
        return {
            "operation_id": self.op,
            "rounds": self.rounds,
            "created_groups": self.created,
            "newly_resolved_leaves": self.resolved,
            "analyzed_leaves": sum(self.analyzed.values()),
            "reached_fixed_point": fixed_point,
            "limited_components": len(self.limits),
            "invalid_helper_leaves": len(self.unknown),
            "groups_by_rule": dict(self.rules),
            "by_currency": {
                cur: {
                    "analyzed_leaves": self.analyzed[cur],
                    "newly_resolved_leaves": self.resolved_by_currency[cur],
                    "created_groups": self.created_by_currency[cur],
                    "remaining_unresolved_roots": kpi[cur]["roots"],
                    "remaining_free_leaves": free[cur],
                    "reasons": dict(reasons[cur]),
                }
                for cur in ("CZK", "EUR")
            },
        }

    def finish(self, result, error=None):
        state = (
            "COMPLETED"
            if error is None
            else "CANCELLED"
            if error.code == "CANCELLED"
            else "FAILED"
        )
        with self.db.transaction() as c:
            if error is None:
                self.validate(c)
            c.execute(
                "UPDATE operation SET state=?,finished_at=?,heartbeat_at=?,progress_current=?,progress_total=?,safe_error_json=?,recovery_json=? WHERE id=?",
                (
                    state,
                    now(),
                    now(),
                    self.resolved,
                    sum(self.analyzed.values()),
                    canonical(error.as_dict()) if error else None,
                    canonical(result),
                    self.op,
                ),
            )
            self.db.audit(
                c,
                "AUTO_FINISHED" if error is None else "AUTO_" + state,
                after=result,
                operation=self.op,
            )
            self.db.audit(c, "OPERATION_" + state, operation=self.op)

    def execute(self, algorithm):
        self.check_cancel()
        self.op = self.db.start_operation("AUTO_MATCH")
        try:
            self.emit_progress(True)
            self.settings = self.settings_service.get()
            with self.db.connect() as c:
                self.guard = self.signature(c)
            algorithm(self)
            with self.db.transaction() as c:
                self.validate(c)
            self.stage("Kontrola výsledků a uložení souhrnu")
            result = self.summary(True)
            self.finish(result)
            return result
        except Exception as cause:
            error = (
                cause
                if isinstance(cause, AppError)
                else AppError(
                    "INTERNAL_ERROR",
                    "Automatické párování bylo přerušeno chybou. Dokončené skupiny zůstávají zachovány.",
                    {"exception_type": type(cause).__name__},
                )
            )
            error.operation_id = self.op
            try:
                result = self.summary(False)
                error.details = {**error.details, "auto_result": result}
                self.finish(result, error)
            except (sqlite3.Error, AppError):
                # Disk/database failure may prevent recording the terminal state.
                # Startup recovery will mark RUNNING as INTERRUPTED; never claim success.
                error.details = {**error.details, "completion_recorded": False}
            raise error from cause
