import ast
import json
from pathlib import Path
import threading

import pytest

from kajovokarty.application.imports import ImportInput, ImportService
from kajovokarty.application.matching import MatchingService
from kajovokarty.application.settings import SettingsService
from kajovokarty.application.work import WorkService
from kajovokarty.domain.core import AppError
from kajovokarty.domain.errors import CATALOG, user_text
from kajovokarty.infrastructure.technical_log import TechnicalLog
from test_acceptance_traces import seed
from test_accounts import import_sample, add_references


@pytest.mark.parametrize("booking_amount,expected,rule", [("50.00", 1, "B"), ("50.01", 1, "C_TERMINAL"), (None, 1, "C_TERMINAL")])
def test_booking_priority_and_terminal_fallback_for_referenced_cash(db, booking_amount, expected, rule):
    import_sample(db)
    add_references(db, [("20260001", "R1", "1234567890")])
    seed(db, "CASHBOOK_CARD")
    terminal = seed(db, "BANK_CARD")
    if booking_amount:
        seed(db, "BOOKING", amount=booking_amount)
    result = MatchingService(db, SettingsService(db)).run()
    assert result["created_groups"] == expected
    with db.connect() as c:
        terminal_membership = c.execute(
            "SELECT 1 FROM membership WHERE child_id=? AND active=1", (terminal,)
        ).fetchone()
        assert bool(terminal_membership) is (rule == "C_TERMINAL")
        if expected:
            assert result["groups_by_rule"] == {rule: 1}


def test_booking_fallback_matches_checkout_date_amount_and_currency(db):
    cash = seed(db, "CASHBOOK_CARD", amount="191.96", vs="20265378")
    booking = seed(
        db,
        "BOOKING",
        amount="191.96",
        seq="fallback",
        departure="2026-09-07",
    )

    result = MatchingService(db, SettingsService(db)).run()

    assert result["groups_by_rule"] == {"B_DATE": 1}
    with db.connect() as c:
        group = c.execute(
            "SELECT parent_id FROM membership WHERE child_id=? AND active=1",
            (cash,),
        ).fetchone()[0]
        members = {
            row[0]
            for row in c.execute(
                "SELECT child_id FROM membership WHERE parent_id=? AND active=1",
                (group,),
            )
        }
        assert {cash, booking} == members
        evidence = c.execute(
            "SELECT evidence_json FROM reconciliation_group WHERE object_id=?",
            (group,),
        ).fetchone()[0]
        assert json.loads(evidence)["rule_id"] == "B_DATE"


def test_booking_fallback_ambiguity_stays_manual(db):
    cash = seed(db, "CASHBOOK_CARD", amount="191.96", vs="20265378")
    seed(db, "BOOKING", amount="191.96", seq="fallback-a", departure="2026-09-07")
    seed(db, "BOOKING", amount="191.96", seq="fallback-b", departure="2026-09-07")

    assert MatchingService(db, SettingsService(db)).run()["created_groups"] == 0
    with db.connect() as c:
        assert c.execute(
            "SELECT code FROM work_reason WHERE object_id=?", (cash,)
        ).fetchone()[0] == "MULTIPLE_CANDIDATES"


@pytest.mark.parametrize("left,right", [(1, 2), (2, 1), (2, 2)])
def test_same_day_terminal_ambiguity_collapses_only_when_balanced(db, left, right):
    for i in range(left):
        seed(db, "CASHBOOK_CARD", minute=f"{i:02d}")
    for i in range(right):
        seed(db, "BANK_CARD", seq=str(i))
    result = MatchingService(db, SettingsService(db)).run()
    assert result["created_groups"] == (1 if left == right else 0)
    if left == right:
        assert result['groups_by_rule'] == {'C_SUM': 1}
    else:
        with db.connect() as c:
            assert {r[0] for r in c.execute("SELECT code FROM work_reason")} == {"MULTIPLE_CANDIDATES"}


def test_terminal_conflicting_symbols_not_matched(db):
    seed(db, "CASHBOOK_CARD")
    seed(db, "BANK_CARD", vs="999999")
    assert MatchingService(db, SettingsService(db)).run()["created_groups"] == 0


def test_group_matching_is_manual_at_service_boundary(db):
    ids = [seed(db, "CASHBOOK_CARD", amount="20.00"),
           seed(db, "CASHBOOK_CARD", amount="30.00", minute="01"),
           seed(db, "BANK_CARD")]
    work = WorkService(db)
    with pytest.raises(AppError) as error:
        work.create_group(ids, {i: 1 for i in ids}, method="AUTO", require_zero=True)
    assert error.value.code == "AUTO_GROUP_FORBIDDEN"
    assert work.create_group(ids, {i: 1 for i in ids}, require_zero=True)["difference"] == 0


def test_every_static_application_error_has_human_explanation():
    for path in (Path(__file__).parents[1] / "src").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            if node.func.id not in ("AppError", "require"):
                continue
            args = node.args[1:] if node.func.id == "require" else node.args
            if args and isinstance(args[0], ast.Constant) and isinstance(args[0].value, str):
                assert args[0].value in CATALOG, (path, args[0].value)
    assert "Booking" not in user_text("HEADER_INVALID")


def test_logging_concurrent_events_and_safe_trace(tmp_path):
    log = TechnicalLog(tmp_path / "logs")
    def write():
        for i in range(25):
            log.event("ROW", row_start=i, payload="DO_NOT_LOG", token="SECRET")
    threads = [threading.Thread(target=write) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    try:
        raise ValueError("SECRET_PERSON")
    except ValueError as error:
        log.exception("FAILED", error)
    text = next(log.folder.glob("*.jsonl")).read_text(encoding="utf-8")
    rows = [json.loads(line) for line in text.splitlines()]
    assert len(rows) == 101 and "SECRET" not in text and "DO_NOT_LOG" not in text
    assert rows[-1]["stack"] and rows[-1]["exception_type"] == "ValueError"
    assert {row["level"] for row in rows} == {"DEBUG", "ERROR"}


def test_import_commit_and_operation_state_are_atomic(db, fixtures, monkeypatch):
    service = ImportService(db)
    preview = service.preflight([ImportInput("BOOKING", str(fixtures / "booking_a.csv"))])
    original = db.audit
    def fail(c, event, *args, **kwargs):
        if event == "OPERATION_COMPLETED":
            raise OSError("failure before commit")
        return original(c, event, *args, **kwargs)
    monkeypatch.setattr(db, "audit", fail)
    with pytest.raises(AppError):
        service.commit(preview.id)
    with db.connect() as c:
        assert c.execute("SELECT count(*) FROM financial_source").fetchone()[0] == 0
        assert c.execute("SELECT state FROM operation WHERE id=?", (preview.id,)).fetchone()[0] == "FAILED"


def test_cancelled_commit_is_not_recorded_as_failure(db, fixtures):
    service = ImportService(db)
    preview = service.preflight([ImportInput("BOOKING", str(fixtures / "booking_a.csv"))])
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(AppError):
        service.commit(preview.id, cancel=cancel)
    with db.connect() as c:
        assert c.execute("SELECT state FROM operation WHERE id=?", (preview.id,)).fetchone()[0] == "CANCELLED"


@pytest.mark.parametrize("name", ["H &amp", "Jiná společnost &amp"])
def test_split_ampersand_is_not_hardcoded_to_one_company(monkeypatch, name):
    from kajovokarty.infrastructure import parsers
    cells = ["07.09.2026 12:00:00", "Příjem", None, "FA20260001", name,
             "Partner s.r.o.", 50.0, 0.0, "EUR", "Kartou", 20260001.0, "Test"]
    monkeypatch.setattr(parsers, "sheets", lambda *args: [("Worksheet", [
        (1, 1, parsers.CASH_HEADERS), (2, 2, cells)])])
    parsed = parsers.parse(b"test", "test.xls", "CASHBOOK_CARD")
    assert len(parsed.sources) == 1 and parsed.sources[0].amount == 5000
    assert parsed.occurrences[0]["repair_code"] == "SPLIT_CLIENT_ENTITY"
    assert not any(d["severity"] == "ERROR" for d in parsed.diagnostics)
    cells[4] = "Nejasný přesah"
    assert parsers.parse(b"test", "test.xls", "CASHBOOK_CARD").diagnostics[0]["code"] == "ROW_SHAPE_INVALID"


def test_repeat_import_records_known_occurrences(db, fixtures):
    service = ImportService(db)
    request = ImportInput("BOOKING", str(fixtures / "booking_a.csv"))
    first = service.preflight([request])
    service.commit(first.id)
    repeated = service.preflight([request])
    outcome = service.commit(repeated.id)
    assert outcome["new"] == 0
    with db.connect() as c:
        assert c.execute("SELECT count(*) FROM source_occurrence WHERE run_id=? AND disposition='NEW'", (repeated.id,)).fetchone()[0] == 0
        assert c.execute("SELECT count(*) FROM source_occurrence WHERE run_id=? AND disposition='KNOWN'", (repeated.id,)).fetchone()[0] == outcome["known"]


def test_unexpected_parser_failure_closes_operation(db, fixtures, monkeypatch):
    import kajovokarty.application.imports as module
    def crash(*args):
        raise ValueError("unsafe source text")
    monkeypatch.setattr(module, "parse", crash)
    service = ImportService(db)
    with pytest.raises(AppError) as error:
        service.preflight([ImportInput("BOOKING", str(fixtures / "booking_a.csv"))])
    assert "unsafe" not in error.value.user_message
    assert not service.previews
    with db.connect() as c:
        assert c.execute("SELECT state FROM operation").fetchone()[0] == "FAILED"
        assert c.execute("SELECT count(*) FROM financial_source").fetchone()[0] == 0


def test_history_summary_failure_does_not_hide_committed_booking(db, fixtures):
    from kajovokarty.application.booking_import import BookingImportService
    from kajovokarty.application.import_messages import batch_text
    with db.connect() as c:
        c.execute("""CREATE TRIGGER fail_summary BEFORE UPDATE ON import_run
            WHEN json_extract(NEW.row_counts_json,'$.booking_result') IS NOT NULL
            BEGIN SELECT RAISE(ABORT,'simulated history failure'); END""")
    reports = BookingImportService(db).run([ImportInput("BOOKING", str(fixtures / "booking_a.csv"))])
    assert reports[0]["state"] == "COMPLETED" and reports[0]["added"] == 21
    assert reports[0]["warnings"]
    assert "Soubor se nepodařilo" not in batch_text(reports)
    with db.connect() as c:
        assert c.execute("SELECT count(*) FROM financial_source").fetchone()[0] == 21
        assert c.execute("SELECT state FROM operation").fetchone()[0] == "COMPLETED"


def test_multiple_file_history_uses_per_file_counts(db, fixtures):
    from kajovokarty.application.catalog import CatalogService
    service = ImportService(db)
    preview = service.preflight([ImportInput("BOOKING", str(fixtures / name))
                                 for name in ("booking_a.csv", "booking_b.csv")])
    outcome = service.commit(preview.id)
    rows = CatalogService(db).rows("imports")
    with db.connect() as c:
        counts = [json.loads(r[0]) for r in c.execute("SELECT counters_json FROM import_file WHERE run_id=?", (preview.id,))]
    assert sum(r.get("NEW", 0) for r in counts) == outcome["new"]
    for row in rows:
        n = json.loads(row["counters_json"]).get("NEW", 0)
        assert f"načteno: {n}." in row["result_text"]
