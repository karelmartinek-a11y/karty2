import json
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from kajovokarty.application.accounts import commit as commit_accounts
from kajovokarty.application.backup import BackupService
from kajovokarty.application.imports import ImportInput, ImportService
from kajovokarty.application.matching import MatchingService
from kajovokarty.application.settings import SettingsService
from kajovokarty.domain.core import AppError
from kajovokarty.infrastructure.parsers import Parsed, parse
from test_acceptance_traces import seed


SAMPLE = Path(__file__).parents[1] / "ucty.xls"


def import_sample(db):
    service = ImportService(db)
    preview = service.preflight([ImportInput("ACCOUNTS", str(SAMPLE))])
    assert preview.valid
    result = service.commit(preview.id)
    return preview, result


def add_references(db, rows):
    # Synthetic row sets exercise merge policy using an actual imported file's provenance.
    with db.connect() as c:
        origin = dict(c.execute("SELECT * FROM account_symbol LIMIT 1").fetchone())
    parsed = Parsed(origin["sheet"], [])
    parsed.accounts = [dict(variable_symbol=v, reservation=r, booking_reference=b, row=i+1) for i,(v,r,b) in enumerate(rows)]
    f = SimpleNamespace(parsed=parsed, request=SimpleNamespace(kind="ACCOUNTS"), file_id=origin["file_id"])
    with db.transaction() as c:
        return commit_accounts(c, [f], origin["import_run_id"])


def test_sample_only_identifiers_and_idempotence(db):
    preview, result = import_sample(db)
    parsed = preview.files[0].parsed
    assert len(parsed.accounts) == 14
    assert not parsed.sources and not parsed.occurrences
    assert all(set(row) == {"variable_symbol", "reservation", "booking_reference", "row"} for row in parsed.accounts)
    assert result["new"] > 0
    _, repeated = import_sample(db)
    assert repeated["new"] == 0
    assert repeated["known"] == 14
    with db.connect() as c:
        assert c.execute("SELECT count(*) FROM account_reservation").fetchone()[0] == 11
        assert c.execute("SELECT count(*) FROM financial_source").fetchone()[0] == 0


def test_first_booking_wins_additional_vs_and_conflicting_vs(db):
    import_sample(db)
    result = add_references(db, [("001", "R1", "1234567890"), ("002", "R1", "1234567890"),
                                ("003", "R1", "9999999999"), ("001", "R1", "1234567890"),
                                ("001", "R2", "8888888888")])
    assert result == dict(new=3, known=1, conflicts=1, incomplete=0)
    with db.connect() as c:
        assert c.execute("SELECT booking_reference FROM account_reservation WHERE reservation='R1'").fetchone()[0] == "1234567890"
        assert not c.execute("SELECT 1 FROM account_symbol WHERE variable_symbol='003'").fetchone()
        assert c.execute("SELECT count(*) FROM account_symbol WHERE variable_symbol='001'").fetchone()[0] == 2


@pytest.mark.parametrize("cash_amounts,book_amounts,expected", [
    (["50.00"], ["50.00"], 1),
    (["50.00"], ["50.01"], 0),
    (["20.00", "30.00"], ["50.00"], 0),
    (["50.00"], ["20.00", "30.00"], 0),
    (["50.00"], ["50.00", "50.00"], 0),
    (["50.00", "50.00"], ["50.00"], 0),
    (["-50.00"], ["-50.00"], 1),
])
def test_exact_individual_matches(db, cash_amounts, book_amounts, expected):
    import_sample(db)
    add_references(db, [("20260001", "R1", "1234567890")])
    for i, amount in enumerate(cash_amounts):
        seed(db, "CASHBOOK_CARD", amount=amount, minute=f"{i:02d}")
    for i, amount in enumerate(book_amounts):
        seed(db, "BOOKING", amount=amount, seq=str(i))
    matcher = MatchingService(db, SettingsService(db))
    result = matcher.run()
    assert result["created_groups"] == expected
    with db.connect() as c:
        groups = c.execute("SELECT evidence_json FROM reconciliation_group").fetchall()
        assert len(groups) == expected
        if expected:
            proof = json.loads(groups[0][0])["accounts_provenance"][0]
            assert proof["variable_symbol"] == "20260001"
            assert proof["reservation"] == "R1"
            assert proof["booking_reference"] == "1234567890"
    import_sample(db)
    add_references(db, [("20260001", "R1", "9999999999")])
    assert matcher.run()["created_groups"] == 0
    with db.connect() as c:
        assert c.execute("SELECT count(*) FROM reconciliation_group").fetchone()[0] == expected


def test_ambiguous_vs_is_manual(db):
    import_sample(db)
    add_references(db, [("20260001", "R1", "1234567890"), ("20260001", "R2", "1234567890")])
    seed(db, "CASHBOOK_CARD")
    seed(db, "BOOKING")
    assert MatchingService(db, SettingsService(db)).run()["created_groups"] == 0


def test_backup_preserves_references(db, tmp_path):
    import_sample(db)
    backup = BackupService(db)
    backup.backup(tmp_path / "accounts.zip")
    add_references(db, [("test", "test", "test")])
    backup.restore(tmp_path / "accounts.zip")
    with db.connect() as c:
        assert c.execute("SELECT count(*) FROM account_reservation").fetchone()[0] == 11
        assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_cancel_import_writes_no_references(db):
    importer = ImportService(db)
    preview = importer.preflight([ImportInput("ACCOUNTS", str(SAMPLE))])
    cancelled = threading.Event()
    cancelled.set()
    with pytest.raises(AppError, match="zrušen"):
        importer.commit(preview.id, cancel=cancelled)
    with db.connect() as c:
        assert c.execute("SELECT count(*) FROM account_symbol").fetchone()[0] == 0


def test_api_cannot_make_requests():
    from kajovokarty.infrastructure.betterhotel import BetterHotelClient
    with pytest.raises(AppError) as error:
        BetterHotelClient("unused", "unused")
    assert error.value.code == "API_REMOVED"


def test_different_currency_stays_manual_but_missing_reference_allows_date_match(db):
    import_sample(db)
    add_references(db, [("20260001", "R1", "1234567890")])
    seed(db, "CASHBOOK_CARD", currency="CZK")
    seed(db, "CASHBOOK_CARD", vs="999999999", minute="01")
    seed(db, "BOOKING")
    assert MatchingService(db, SettingsService(db)).run()['groups_by_rule'] == {'B_DATE': 1}


def test_accounts_report_and_proof_export(db, tmp_path):
    from kajovokarty.application.reports import ReportService
    from kajovokarty.infrastructure.export import export
    import_sample(db)
    add_references(db, [("20260001", "R1", "1234567890")])
    seed(db, "CASHBOOK_CARD")
    seed(db, "BOOKING")
    MatchingService(db, SettingsService(db)).run()
    with db.connect() as c:
        group = c.execute("SELECT object_id FROM reconciliation_group").fetchone()[0]
    report = ReportService(db).build("group_evidence", [group])
    assert report["group_summary"][0]["accounts_provenance"][0]["reservation"] == "R1"
    export(report, "zip", tmp_path / "proof.zip")
    report = ReportService(db).build("helpers")
    assert report["account_references"]
    export(report, "zip", tmp_path / "accounts.zip")


def test_migrate_v2_preserves_group_and_creates_backup(db):
    from kajovokarty.application.work import WorkService
    from kajovokarty.infrastructure.database import Database
    a = seed(db, "CASHBOOK_CARD")
    b = seed(db, "BOOKING")
    group = WorkService(db).create_group([a, b], {a: 1, b: 1})["id"]
    with db.connect() as c:
        c.execute("DROP TABLE account_symbol")
        c.execute("DROP TABLE account_reservation")
        c.execute("DELETE FROM schema_migration WHERE version=3")
        c.execute("PRAGMA user_version=2")
    upgraded = Database(db.path)
    assert WorkService(upgraded).evidence(group)["difference"] == 0
    assert list(db.path.parent.glob("before-migration-2-*.zip"))
    import_sample(upgraded)
    assert WorkService(upgraded).evidence(group)["difference"] == 0


@pytest.mark.parametrize("missing,duplicate", [(False, False), (True, False), (False, True)])
def test_headers_selected_columns_and_leading_zeros(monkeypatch, missing, duplicate):
    import xlrd
    from xlrd.sheet import Cell
    labels = ["Original ID", "Jiný sloupec", "Číslo rezervace", "Variabilní symbol"]
    if missing:
        labels[0] = "neznámý"
    if duplicate:
        labels[1] = "Original ID"
    values = [labels, [" 0012345678 ", 7, " 0009 ", 123.0], ["", 9, "10", 124.0]]
    class Sheet:
        name, visibility, nrows = "Test", 0, 3
        def row_values(self, ri): return values[ri]
        def row_len(self, ri): return len(values[ri])
        def cell(self, ri, col):
            value = values[ri][col]
            return Cell(xlrd.XL_CELL_ERROR if col == 1 else xlrd.XL_CELL_NUMBER if isinstance(value, float) else xlrd.XL_CELL_TEXT, value)
    class Book:
        def sheets(self): return [Sheet()]
        def release_resources(self): pass
    monkeypatch.setattr(xlrd, "open_workbook", lambda **kwargs: Book())
    if missing or duplicate:
        with pytest.raises(AppError) as exc:
            parse(bytes.fromhex("D0CF11E0A1B11AE1"), "test.xls", "ACCOUNTS")
        assert exc.value.code == "HEADER_INVALID"
    else:
        parsed = parse(bytes.fromhex("D0CF11E0A1B11AE1"), "test.xls", "ACCOUNTS")
        assert parsed.accounts == [dict(variable_symbol="123", reservation="0009", booking_reference="0012345678", row=2)]
        assert parsed.counters["incomplete"] == 1
