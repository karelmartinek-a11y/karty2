import pytest
from kajovokarty.application.imports import ImportInput
from kajovokarty.infrastructure.parsers import parse
from kajovokarty.domain.core import AppError


@pytest.mark.parametrize(
    "filename,kind,n,totals",
    [
        (
            "cashbook_year.xls",
            "CASHBOOK_CARD",
            1055,
            {"CZK": 125987613, "EUR": 14127070},
        ),
        ("cashbook_week.xls", "CASHBOOK_CARD", 9, {"CZK": 520000, "EUR": 108374}),
        ("terminal.xlsx", "BANK_CARD", 56, {"CZK": 21672903, "EUR": 125510}),
        ("booking_a.csv", "BOOKING", 21, {"CZK": 0, "EUR": 395564}),
        ("booking_b.csv", "BOOKING", 25, {"CZK": 0, "EUR": 451069}),
    ],
)
def test_real_fixtures(fixtures, filename, kind, n, totals):
    result = parse((fixtures / filename).read_bytes(), filename, kind)
    assert not [d for d in result.diagnostics if d["severity"] == "ERROR"]
    assert len(result.sources) == n
    assert {
        c: sum(s.amount for s in result.sources if s.currency == c)
        for c in ("CZK", "EUR")
    } == totals
    if filename == "cashbook_year.xls":
        assert [
            d["row_start"]
            for d in result.diagnostics
            if d["code"] == "SPLIT_CLIENT_ENTITY"
        ] == [1116, 1150]
        assert result.counters["CASH"] == 550 and result.counters["TRANSFER"] == 79
        assert any(d["code"] == "CASHBOOK_FOOTER_MISMATCH" for d in result.diagnostics)


@pytest.mark.parametrize(
    "order",
    [
        ["cashbook_year.xls", "cashbook_week.xls"],
        ["cashbook_week.xls", "cashbook_year.xls"],
    ],
)
def test_overlap(importer, fixtures, order):
    expected = [1055, 0] if order[0] == "cashbook_year.xls" else [9, 1046]
    for name, count in zip(order, expected):
        p = importer.preflight([ImportInput("CASHBOOK_CARD", str(fixtures / name))])
        assert p.valid
        assert importer.commit(p.id)["new"] == count
    with importer.db.connect() as c:
        assert c.execute("SELECT count(*) FROM financial_source").fetchone()[0] == 1055


@pytest.mark.parametrize("reverse", [False, True])
def test_overlap_set(importer, fixtures, reverse):
    names = ["cashbook_year.xls", "cashbook_week.xls"]
    names = names[::-1] if reverse else names
    p = importer.preflight(
        [ImportInput("CASHBOOK_CARD", str(fixtures / n)) for n in names]
    )
    assert p.new == 1055 and p.known == 9
    assert importer.commit(p.id)["new"] == 1055


def test_original_changed(importer, fixtures, tmp_path):
    pth = tmp_path / "booking.csv"
    pth.write_bytes((fixtures / "booking_a.csv").read_bytes())
    p = importer.preflight([ImportInput("BOOKING", str(pth))])
    pth.unlink()
    with pytest.raises(AppError, match="Autoritativní"):
        importer.commit(p.id)
    with importer.db.connect() as c:
        assert c.execute("SELECT count(*) FROM financial_source").fetchone()[0] == 0


def test_stored_snapshot(importer, fixtures, tmp_path):
    pth = tmp_path / "booking.csv"
    pth.write_bytes((fixtures / "booking_a.csv").read_bytes())
    p = importer.preflight([ImportInput("BOOKING", str(pth))])
    fid = p.files[0].file_id
    importer.commit(p.id)
    pth.unlink()
    p = importer.preflight([ImportInput("BOOKING", source_file_id=fid)])
    assert importer.commit(p.id)["new"] == 0


def test_atomic_failure(importer, fixtures, tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("wrong,header\n1,2")
    p = importer.preflight(
        [
            ImportInput("BOOKING", str(fixtures / "booking_a.csv")),
            ImportInput("BOOKING", str(bad)),
        ]
    )
    assert not p.valid
    with pytest.raises(AppError):
        importer.commit(p.id)
    with importer.db.connect() as c:
        assert c.execute("SELECT count(*) FROM financial_source").fetchone()[0] == 0


def test_hard_conflict(importer, fixtures, tmp_path):
    path = fixtures / "booking_a.csv"
    p = importer.preflight([ImportInput("BOOKING", str(path))])
    importer.commit(p.id)
    import csv, io

    rows = list(csv.reader(io.StringIO(path.read_text(encoding="utf-8-sig"))))
    rows[1][9] = "1.00"
    bad = tmp_path / "changed.csv"
    with bad.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)
    p = importer.preflight([ImportInput("BOOKING", str(bad))])
    assert not p.valid
    assert any(e["code"] == "SOURCE_CONFLICT" for e in p.diagnostics)
