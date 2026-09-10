import zipfile
import pytest, openpyxl
from kajovokarty.application.imports import ImportInput
from kajovokarty.application.reports import ReportService
from kajovokarty.infrastructure.export import export, columns
from kajovokarty.application.backup import BackupService
from kajovokarty.domain.core import AppError


def test_exports(importer, fixtures, tmp_path):
    p = importer.preflight([ImportInput("BANK_CARD", str(fixtures / "terminal.xlsx"))])
    importer.commit(p.id)
    data = ReportService(importer.db).build("terminal")
    for ext in ("zip", "xlsx", "pdf"):
        export(data, ext, tmp_path / ("terminal." + ext))
        assert (tmp_path / ("terminal." + ext)).stat().st_size > 0
    with zipfile.ZipFile(tmp_path / "terminal.zip") as z:
        assert z.namelist() == [name + ".csv" for name in data]
    book = openpyxl.load_workbook(tmp_path / "terminal.xlsx")
    sheet = book["bank_rows"]
    headers = [c.value for c in sheet[1]]
    col = headers.index("authorization_code") + 1
    assert any(
        sheet.cell(row, col).value == "001859" and sheet.cell(row, col).data_type == "s"
        for row in range(2, sheet.max_row + 1)
    )


def test_empty_schema(db, tmp_path):
    data = ReportService(db).build("booking")
    export(data, "xlsx", tmp_path / "empty.xlsx")
    book = openpyxl.load_workbook(tmp_path / "empty.xlsx")
    assert list(book.sheetnames) == list(data)
    for dataset in data:
        assert [c.value for c in book[dataset][1]] == [k for k, t in columns(dataset)]


def test_backup_restore(importer, fixtures, tmp_path):
    p = importer.preflight([ImportInput("BOOKING", str(fixtures / "booking_a.csv"))])
    importer.commit(p.id)
    b = BackupService(importer.db)
    b.backup(tmp_path / "backup.zip")
    p = importer.preflight([ImportInput("BOOKING", str(fixtures / "booking_b.csv"))])
    importer.commit(p.id)
    b.restore(tmp_path / "backup.zip")
    with importer.db.connect() as c:
        assert c.execute("SELECT count(*) FROM financial_source").fetchone()[0] == 21
        assert (
            c.execute("SELECT status FROM helper_state").fetchone()[0] == "UNAVAILABLE"
        )
        assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_bad_backup_preserves_db(db, tmp_path):
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"broken")
    with pytest.raises(AppError):
        BackupService(db).restore(bad)
    with db.connect() as c:
        assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
