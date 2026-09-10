import pytest
from kajovokarty.domain.columns import value_token, filter_rows, filter_options
from kajovokarty.application.work import WorkService
from kajovokarty.application.imports import ImportInput
from kajovokarty.domain.core import AppError


def test_typed_filter_values_empty_selection_and_blank_sort():
    rows = [
        {"id": "a", "amount": 1000, "value": None},
        {"id": "b", "amount": 200, "value": ""},
        {"id": "c", "amount": -100, "value": "001"},
        {"id": "d", "amount": 0, "value": "1"},
    ]
    assert [r["amount"] for r in filter_rows(rows, sort=[("amount", "asc")])] == [
        -100,
        0,
        200,
        1000,
    ]
    assert [r["id"] for r in filter_rows(rows, {"value": ["null"]})] == ["a", "b"]
    assert filter_rows(rows, {"value": []}) == []
    assert filter_rows(rows, {"value": [value_token("001")]}) == [rows[2]]
    assert [r["id"] for r in filter_rows(rows, sort=[("value", "desc")])][-2:] == [
        "a",
        "b",
    ]
    assert value_token(False) != value_token(0)


def test_facets_ignore_only_own_filter():
    rows = [{"x": "A", "y": 1}, {"x": "B", "y": 1}, {"x": "C", "y": 2}]
    options = filter_options(
        rows, "x", {"x": [value_token("A")], "y": [value_token(1)]}
    )
    assert {t for _, t in options} == {value_token("A"), value_token("B")}


def test_sql_filters_and_facets_cover_all_pages(importer, fixtures):
    preview = importer.preflight(
        [ImportInput("CASHBOOK_CARD", str(fixtures / "cashbook_year.xls"))]
    )
    importer.commit(preview.id)
    work = WorkService(importer.db)
    all_rows = work.query(page_size=0)["rows"]
    assert len(all_rows) == 1055
    target = all_rows[-1]
    filters = {
        "column_filters": {
            "primary_identifier": [value_token(target["primary_identifier"])]
        }
    }
    result = work.query(filters)
    assert target["id"] in result["ids"] and result["rows"]
    facets = work.query({**filters, "_facet": "primary_identifier"})["facets"]
    assert {t for _, t in facets} == {
        value_token(r["primary_identifier"]) for r in all_rows
    }
    assert work.query({"column_filters": {"primary_identifier": []}})["total"] == 0
    assert (
        work.query({"column_filters": {"kinds": [value_token(["CASHBOOK_CARD"])]}})[
            "total"
        ]
        == 1055
    )
    with pytest.raises(AppError):
        work.query({"column_filters": {"id); DROP TABLE work_object; --": []}})


@pytest.mark.parametrize(
    "field",
    [
        "resolved",
        "type",
        "kinds",
        "date",
        "primary_identifier",
        "description",
        "leaf_count",
        "amount",
        "currency",
        "difference",
        "reason",
        "note",
    ],
)
def test_every_work_column_has_sql_filter_and_facets(db, field):
    from test_acceptance_traces import seed

    seed(db, "CASHBOOK_CARD", "50.00")
    work = WorkService(db)
    row = work.query()["rows"][0]
    token = value_token(row[field])
    assert work.query({"column_filters": {field: [token]}})["ids"] == [row["id"]]
    assert token in {t for _, t in work.query({"_facet": field})["facets"]}


def test_report_filters_do_not_leak_between_view_schemas():
    from kajovokarty.ui.export_dialog import report_filters

    f = {"text": "ABC", "column_filters": {"sestava": [value_token("Terminál")]}}
    assert report_filters(f, 5, "terminal") == {"text": "ABC"}
    financial = {"column_filters": {"currency": [value_token("EUR")]}}
    assert report_filters(financial, 0, "unresolved") == financial
    imports = {"column_filters": {"original_name": []}}
    assert report_filters(imports, 2, "import_errors") == {
        "import_columns": {"original_name": []}
    }
    assert report_filters(financial, 0, "helpers") == {}
