import pytest
from test_acceptance_traces import seed
from kajovokarty.application.pairing import PairingService
from kajovokarty.application.work import WorkService
from kajovokarty.domain.core import AppError


def context(db):
    ids = [
        seed(db, "CASHBOOK_CARD", "50.00", vs="20260001"),
        seed(db, "BANK_CARD", "50.00", seq="1"),
        seed(db, "BANK_CARD", "10.00", seq="2"),
        seed(db, "BOOKING", "20.00", seq="3"),
    ]
    return ids, PairingService(db), WorkService(db)


def revisions(work, ids):
    with work.db.connect() as c:
        return {
            i: c.execute(
                "SELECT revision FROM work_object WHERE id=?", (i,)
            ).fetchone()[0]
            for i in ids
        }


def test_drop_create_edit_resolved_detach_collapse_and_undo(db):
    (cash, bank, extra, booking), pairing, work = context(db)
    first = pairing.move(
        [bank],
        revisions(work, [bank]),
        target=cash,
        target_revision=revisions(work, [cash])[cash],
    )
    gid = first["id"]
    assert first["difference"] == 0 and pairing.panel(gid)["object"]["resolved"]
    # Adding a new member explicitly reopens a settled group, and remains undoable.
    pairing.move(
        [extra],
        revisions(work, [extra]),
        target=gid,
        target_revision=revisions(work, [gid])[gid],
    )
    assert pairing.panel(gid)["object"]["difference"] == -1000
    panel = pairing.panel(gid)
    member = next(r for r in panel["rows"] if r["id"] == bank)
    command = pairing.move(
        [bank],
        {bank: member["revision"]},
        parent_revisions={bank: [gid, panel["object"]["revision"]]},
    )
    assert set(work.evidence(gid)["children"]) == {cash, extra}
    assert bank in work.query({"status": "all"}, page_size=0)["ids"]
    work.undo(command["command_id"])
    assert set(work.evidence(gid)["children"]) == {cash, bank, extra}
    work.undo(command["command_id"], True)
    panel = pairing.panel(gid)
    cash_row = next(r for r in panel["rows"] if r["id"] == cash)
    last = pairing.move(
        [cash],
        {cash: cash_row["revision"]},
        parent_revisions={cash: [gid, panel["object"]["revision"]]},
    )
    assert gid in last["dissolved"]
    assert {cash, bank, extra, booking} == set(
        work.query({"status": "all"}, page_size=0)["ids"]
    )
    work.undo(last["command_id"])
    assert set(work.evidence(gid)["children"]) == {cash, extra}


def test_transfer_member_is_one_command_and_keeps_financial_bytes(db):
    ids, pairing, work = context(db)
    a, b, c, d = ids
    left = pairing.move(
        [b], revisions(work, [b]), target=a, target_revision=revisions(work, [a])[a]
    )["id"]
    right = pairing.move(
        [d], revisions(work, [d]), target=c, target_revision=revisions(work, [c])[c]
    )["id"]
    with db.connect() as connection:
        before = [
            tuple(r)
            for r in connection.execute("SELECT * FROM financial_source ORDER BY id")
        ]
        count = connection.execute("SELECT count(*) FROM command").fetchone()[0]
    transfer = pairing.move(
        [b],
        revisions(work, [b]),
        target=right,
        target_revision=revisions(work, [right])[right],
        parent_revisions={b: [left, revisions(work, [left])[left]]},
    )
    assert set(work.evidence(right)["children"]) == {b, c, d}
    assert left in transfer["dissolved"]
    with db.connect() as connection:
        assert before == [
            tuple(r)
            for r in connection.execute("SELECT * FROM financial_source ORDER BY id")
        ]
        assert (
            connection.execute("SELECT count(*) FROM command").fetchone()[0]
            == count + 1
        )
    work.undo(transfer["command_id"])
    assert set(work.evidence(left)["children"]) == {a, b}
    assert set(work.evidence(right)["children"]) == {c, d}
    work.undo(transfer["command_id"], True)
    assert set(work.evidence(right)["children"]) == {b, c, d}


def test_stale_parent_and_self_drop_have_no_partial_effect(db):
    ids, pairing, work = context(db)
    a, b, c, d = ids
    gid = pairing.move(
        [b], revisions(work, [b]), target=a, target_revision=revisions(work, [a])[a]
    )["id"]
    before = work.evidence(gid)
    with pytest.raises(AppError, match="Členství"):
        pairing.move([b], revisions(work, [b]), parent_revisions={b: [gid, 0]})
    assert work.evidence(gid)["children"] == before["children"]
    with pytest.raises(AppError) as e:
        pairing.move(
            [gid],
            revisions(work, [gid]),
            target=gid,
            target_revision=revisions(work, [gid])[gid],
        )
    assert e.value.code == "CYCLE_DETECTED"


def test_group_to_unpair_zone_preserves_nested_group(db):
    ids, pairing, work = context(db)
    a, b, c, d = ids
    sub = work.create_group([b, c], revisions(work, [b, c]))["id"]
    root = work.create_group([a, sub, d], revisions(work, [a, sub, d]))["id"]
    result = pairing.move([root], revisions(work, [root]))
    assert set(work.query({"status": "all"}, page_size=0)["ids"]) == {a, sub, d}
    assert set(work.evidence(sub)["children"]) == {b, c}
    work.undo(result["command_id"])
    assert set(work.evidence(root)["children"]) == {a, sub, d}


def test_transaction_failure_rolls_back_transfer(db, monkeypatch):
    ids, pairing, work = context(db)
    a, b, c, d = ids
    before = work.query({"status": "all"}, page_size=0)["ids"]
    original = db.validate

    def reject(connection):
        original(connection)
        raise RuntimeError("injected boundary failure")

    monkeypatch.setattr(db, "validate", reject)
    with pytest.raises(RuntimeError):
        pairing.move(
            [b], revisions(work, [b]), target=a, target_revision=revisions(work, [a])[a]
        )
    assert work.query({"status": "all"}, page_size=0)["ids"] == before


def test_new_group_from_owned_members_updates_both_parents_atomically(db):
    ids, pairing, work = context(db)
    a, b, c, d = ids
    left = work.create_group([a, c], revisions(work, [a, c]))["id"]
    right = work.create_group([b, d], revisions(work, [b, d]))["id"]
    result = pairing.move(
        [b],
        revisions(work, [b]),
        target=a,
        target_revision=revisions(work, [a])[a],
        parent_revisions={
            a: [left, revisions(work, [left])[left]],
            b: [right, revisions(work, [right])[right]],
        },
    )
    assert set(work.evidence(result["id"])["children"]) == {a, b}
    assert set(result["dissolved"]) == {left, right}
    work.undo(result["command_id"])
    assert set(work.evidence(left)["children"]) == {a, c}
    assert set(work.evidence(right)["children"]) == {b, d}


def test_manual_change_archives_auto_evidence_and_undo_restores_it(db):
    import json

    ids, pairing, work = context(db)
    a, b, c, d = ids
    gid = work.create_group(
        [a, b],
        revisions(work, [a, b]),
        method="AUTO",
        evidence={"fingerprint": "test-auto-proof", "rule": "C"},
    )["id"]
    before = work.evidence(gid)["group"]
    result = pairing.move(
        [c],
        revisions(work, [c]),
        target=gid,
        target_revision=revisions(work, [gid])[gid],
    )
    current = work.evidence(gid)["group"]
    assert current["method"] == "MANUAL" and json.loads(current["evidence_json"]) == {}
    with db.connect() as connection:
        assert (
            connection.execute(
                "SELECT active FROM auto_suppression WHERE fingerprint='test-auto-proof'"
            ).fetchone()[0]
            == 1
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM group_history WHERE group_id=?", (gid,)
            ).fetchone()[0]
            == 1
        )
    work.undo(result["command_id"])
    restored = work.evidence(gid)["group"]
    assert (
        restored["method"] == before["method"]
        and restored["evidence_json"] == before["evidence_json"]
    )


def test_previous_auto_can_be_reenabled_without_pairing(db):
    ids, pairing, work = context(db)
    a, b, c, d = ids
    gid = work.create_group(
        [a, b],
        revisions(work, [a, b]),
        method="AUTO",
        evidence={"fingerprint": "prior-proof"},
    )["id"]
    pairing.move(
        [c],
        revisions(work, [c]),
        target=gid,
        target_revision=revisions(work, [gid])[gid],
    )
    assert pairing.panel(gid)["suppressed_auto"] == ["prior-proof"]
    children = work.evidence(gid)["children"]
    command = pairing.allow_previous_auto(gid)
    assert pairing.panel(gid)["suppressed_auto"] == []
    assert work.evidence(gid)["children"] == children
    work.undo(command)
    assert pairing.panel(gid)["suppressed_auto"] == ["prior-proof"]
