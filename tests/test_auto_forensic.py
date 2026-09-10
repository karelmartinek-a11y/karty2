"""Regression cases for button-triggered automatic matching and safe completion."""

import json
import threading
import pytest
from kajovokarty.application.matching import MatchingService
from kajovokarty.application.settings import SettingsService
from kajovokarty.application.work import WorkService
from kajovokarty.domain.core import AppError
from test_acceptance_traces import seed


def service(db):
    return MatchingService(db, SettingsService(db))


def operations(db):
    with db.connect() as c:
        return [
            dict(r)
            for r in c.execute(
                "SELECT * FROM operation WHERE type='AUTO_MATCH' ORDER BY started_at"
            )
        ]


def test_preparation_error_finishes_operation(db, monkeypatch):
    match = service(db)
    monkeypatch.setattr(
        match,
        "_helper",
        lambda: (_ for _ in ()).throw(RuntimeError("private payload must not escape")),
    )
    with pytest.raises(AppError) as exc:
        match.run()
    assert exc.value.code == "INTERNAL_ERROR"
    assert "private payload" not in json.dumps(exc.value.as_dict())
    assert operations(db)[-1]["state"] == "FAILED"


def test_refreshing_helper_does_not_leave_running_operation(db):
    with db.transaction() as c:
        c.execute("UPDATE helper_state SET status='REFRESHING',revision=revision+1")
    with pytest.raises(AppError, match="Nejprve"):
        service(db).run()
    assert operations(db)[-1]["state"] == "FAILED"


def test_cancel_after_commit_keeps_group_and_reports_partial_result(db):
    for n in (1, 2):
        seed(db, "CASHBOOK_CARD", vs=str(n), minute=f"{n:02d}")
        seed(db, "BANK_CARD", vs=str(n), seq=str(n))
    cancel = threading.Event()

    def progress(message):
        if "skupin 1" in message:
            cancel.set()

    with pytest.raises(AppError) as exc:
        service(db).run(cancel, progress)
    assert exc.value.code == "CANCELLED"
    assert len(WorkService(db).query({"status": "resolved"})["rows"]) == 1
    op = operations(db)[-1]
    assert op["state"] == "CANCELLED"
    result = exc.value.details["auto_result"]
    assert result["created_groups"] == 1 and not result["reached_fixed_point"]
    assert result["newly_resolved_leaves"] == 2
    assert json.loads(op["recovery_json"]) == result
    assert service(db).run()["created_groups"] == 1
    assert service(db).run()["created_groups"] == 0


def sync_wire(db, wire):
    from kajovokarty.application.sync import SyncService
    from test_api import client

    http = client(wire)
    try:
        SyncService(db, SettingsService(db)).full(
            http, scope=("2026-09-07", "2026-09-08")
        )
    finally:
        http.close()


@pytest.mark.parametrize("mutation", ["helper", "settings", "ownership", "cancel"])
def test_last_moment_changes_are_rejected_inside_group_transaction(
    db, monkeypatch, mutation
):
    cash = seed(db, "CASHBOOK_CARD")
    seed(db, "BANK_CARD")
    match = service(db)
    original = match.work.create_group
    cancel = threading.Event()

    def altered(*args, **kwargs):
        if mutation == "cancel":
            cancel.set()
        else:
            with db.transaction() as c:
                if mutation == "helper":
                    c.execute("UPDATE helper_state SET revision=revision+1")
                elif mutation == "settings":
                    c.execute(
                        "INSERT INTO setting VALUES('matching.bank_window_days','1',1)"
                    )
                else:
                    c.execute(
                        "UPDATE work_object SET revision=revision+1 WHERE id=?", (cash,)
                    )
        return original(*args, **kwargs)

    monkeypatch.setattr(match.work, "create_group", altered)
    with pytest.raises(AppError) as exc:
        match.run(cancel)
    assert exc.value.code == ("CANCELLED" if mutation == "cancel" else "STALE_STATE")
    assert not WorkService(db).query({"status": "resolved"})["rows"]
    assert not exc.value.details["auto_result"]["reached_fixed_point"]
    assert operations(db)[-1]["state"] != "RUNNING"


def test_error_after_first_commit_preserves_only_completed_groups(db, monkeypatch):
    for n in (1, 2):
        seed(db, "CASHBOOK_CARD", vs=str(n), minute=f"{n:02d}")
        seed(db, "BANK_CARD", vs=str(n), seq=str(n))
    match = service(db)
    original = match.work.create_group
    calls = []

    def failing(*args, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("synthetic failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(match.work, "create_group", failing)
    with pytest.raises(AppError) as exc:
        match.run()
    assert exc.value.code == "INTERNAL_ERROR"
    assert exc.value.details["auto_result"]["created_groups"] == 1
    assert operations(db)[-1]["state"] == "FAILED"
    assert len(WorkService(db).query({"status": "resolved"})["rows"]) == 1
    assert service(db).run()["created_groups"] == 1


def test_removed_reservation_cannot_become_weak_bank_evidence(db, wire):
    import copy

    seed(db, "CASHBOOK_CARD")
    seed(db, "BANK_CARD", vs=None)
    sync_wire(db, wire)
    changed = copy.deepcopy(wire)
    changed["/reservation"] = {"data": []}
    sync_wire(db, changed)
    result = service(db).run()
    assert result["created_groups"] == 0
    assert result["invalid_helper_leaves"] == 1


@pytest.mark.parametrize(
    "damage",
    [
        "inactive_invoice",
        "incomplete_link",
        "reservation_currency",
        "invoice_code_spaces",
    ],
)
def test_unusable_helper_chain_never_commits_B(db, wire, monkeypatch, damage):
    seed(db, "CASHBOOK_CARD")
    seed(db, "BOOKING")
    sync_wire(db, wire)
    match = service(db)
    state, entities, links, overrides, coverage = match._helper()
    if damage == "inactive_invoice":
        entities[("invoice", "I1")]["active"] = 0
    elif damage == "incomplete_link":
        next(l for l in links if l["relation"] == "INVOICE" and l["to_id"] == "I1")[
            "complete"
        ] = 0
    elif damage == "reservation_currency":
        entities[("reservation", "R1")]["payload"]["currency"] = "CZK"
    else:
        entities[("invoice", "I1")]["payload"]["code"] = "FA2026  0001"
        original = match._free

        def free():
            rows = original()
            for row in rows:
                if row["kind"] == "CASHBOOK_CARD":
                    row["payload"].update(
                        label="FA2026 0001",
                        invoice_code="FA2026 0001",
                        variable_symbol=None,
                    )
            return rows

        monkeypatch.setattr(match, "_free", free)
    monkeypatch.setattr(
        match, "_helper", lambda: (state, entities, links, overrides, coverage)
    )
    assert match.run()["created_groups"] == 0


def test_booking_only_component_does_not_hit_cross_source_search_limit(db, wire):
    sync_wire(db, wire)
    for n in range(41):
        seed(db, "BOOKING", str(n + 1) + ".00", seq=str(n))
    seed(db, "BOOKING", "-1.00", seq="refund")
    result = service(db).run()
    assert result["created_groups"] == 1
    assert result["groups_by_rule"] == {"D": 1}
    assert result["limited_components"] == 0
    assert service(db).run()["created_groups"] == 0


def test_pre_cancelled_request_does_not_start_or_mutate(db):
    seed(db, "CASHBOOK_CARD")
    seed(db, "BANK_CARD")
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(AppError) as exc:
        service(db).run(cancel)
    assert exc.value.code == "CANCELLED"
    assert operations(db) == []
    assert not WorkService(db).history()


def test_manual_groups_are_not_auto_inputs(db):
    a = seed(db, "CASHBOOK_CARD", "20.00")
    b = seed(db, "CASHBOOK_CARD", "30.00", minute="01")
    seed(db, "BANK_CARD", "50.00")
    work = WorkService(db)
    group = work.create_group([a, b], {a: 1, b: 1})
    result = service(db).run()
    assert result["created_groups"] == 0 and result["analyzed_leaves"] == 1
    assert set(work.evidence(group["id"])["children"]) == {a, b}
    assert result["by_currency"]["EUR"]["remaining_unresolved_roots"] == 2


def test_per_currency_summary_matches_actual_full_database(db, importer, fixtures):
    from kajovokarty.application.imports import ImportInput

    importer.commit(
        importer.preflight(
            [ImportInput("CASHBOOK_CARD", str(fixtures / "cashbook_year.xls"))]
        ).id
    )
    result = service(db).run()
    assert result["analyzed_leaves"] == 1055 and result["created_groups"] == 0
    assert all(
        result["by_currency"][cur]["analyzed_leaves"] > 0 for cur in ("CZK", "EUR")
    )
    assert (
        sum(v["remaining_free_leaves"] for v in result["by_currency"].values()) == 1055
    )
    assert (
        sum(sum(v["reasons"].values()) for v in result["by_currency"].values()) == 1055
    )


def test_database_instances_share_financial_operation_gate(db):
    from kajovokarty.infrastructure.database import Database

    other = Database(db.path)
    entered = threading.Event()

    def attempt():
        with other.operation_gate():
            entered.set()

    with db.operation_gate():
        worker = threading.Thread(target=attempt)
        worker.start()
        assert not entered.wait(0.15)
    worker.join(2)
    assert entered.is_set() and not worker.is_alive()


@pytest.mark.parametrize(
    "cash_amounts,booking_amounts,expected",
    [
        (["50.00"], ["50.00"], 1),
        (["50.00"], ["25.00", "25.00"], 1),
        (["25.00", "25.00"], ["50.00"], 1),
        (["20.00", "30.00"], ["10.00", "40.00"], 1),
        (["100.00", "-50.00"], ["50.00"], 1),
        (["50.00", "50.00"], ["50.00"], 0),
        (["50.00"], ["49.99"], 0),
    ],
)
def test_B_exact_combinations_and_ambiguity(
    db, wire, cash_amounts, booking_amounts, expected
):
    from test_acceptance_traces import fixedpoint_wire

    for n, amount in enumerate(cash_amounts, 1):
        seed(db, "CASHBOOK_CARD", amount, vs=f"2026000{n}", minute=f"{n:02d}")
    for n, amount in enumerate(booking_amounts):
        seed(db, "BOOKING", amount, seq=str(n))
    sync_wire(db, fixedpoint_wire(wire))
    result = service(db).run()
    assert result["created_groups"] == expected
    assert all(
        row["difference"] == 0
        for row in WorkService(db).query({"status": "resolved"})["rows"]
    )
    assert service(db).run()["created_groups"] == 0


def test_search_limit_discards_whole_B_component_and_blocks_D(db, wire):
    for n in range(3):
        seed(db, "CASHBOOK_CARD", "50.00", minute=f"{n:02d}")
    seed(db, "BOOKING", "50.00")
    seed(db, "BOOKING", "-50.00", seq="refund")
    sync_wire(db, wire)
    SettingsService(db).save({"matching.max_component_items": 2})
    result = service(db).run()
    assert result["created_groups"] == 0 and result["limited_components"] == 1
    assert result["by_currency"]["EUR"]["reasons"]["AUTO_SEARCH_LIMIT"] == 5


def test_legacy_uuid_order_suppression_is_respected(db, wire, monkeypatch):
    from kajovokarty.domain.core import digest, now
    from kajovokarty.domain.helpers import extract_references, reference_decision
    from test_acceptance_traces import fixedpoint_wire

    # Deliberately reverse UUID and canonical source order to exercise compatibility.
    generated = iter(["z" * 32, "a" * 32, "b" * 32])
    monkeypatch.setattr("test_acceptance_traces.uid", lambda: next(generated))
    cash_a = seed(db, "CASHBOOK_CARD", "25.00")
    cash_b = seed(db, "CASHBOOK_CARD", "25.00", vs="20260002", minute="01")
    seed(db, "BOOKING", "50.00")
    sync_wire(db, fixedpoint_wire(wire))
    match = service(db)
    state, entities, _, _, _ = match._helper()
    reservation = entities[("reservation", "R1")]
    p = reservation["payload"]
    decision = reference_decision(
        extract_references(p["reservation_note"], p["reservation_source"]["name"])
    )
    proofs = {
        cash_a: {
            "context_id": state["context_id"],
            "invoice": entities[("invoice", "I1")]["content_hash"],
            "reservation": reservation["content_hash"],
            "decision": decision,
        },
        cash_b: {
            "context_id": state["context_id"],
            "invoice": entities[("invoice", "I2")]["content_hash"],
            "reservation": reservation["content_hash"],
            "decision": decision,
        },
    }
    sources = match._free()
    legacy = digest(
        {
            "rule_id": "B",
            "leaves": [
                [r["kind"], r["source_identity"], r["content_hash"]] for r in sources
            ],
            "evidence_hash": digest([proofs[i] for i in sorted(proofs)]),
        }
    )
    assert match.run()["created_groups"] == 1
    work = WorkService(db)
    group = work.query({"status": "resolved"})["rows"][0]
    evidence = work.evidence(group["id"])
    new = json.loads(evidence["group"]["evidence_json"])["fingerprint"]
    assert new != legacy
    command = work.dissolve(group["id"], group["revision"])
    with db.transaction() as c:
        c.execute(
            "UPDATE auto_suppression SET active=0,revision=revision+1 WHERE fingerprint=?",
            (new,),
        )
        c.execute(
            "INSERT INTO auto_suppression VALUES(?,?,1,1,?,?)",
            (legacy, command, now(), now()),
        )
    assert match.run()["created_groups"] == 0
