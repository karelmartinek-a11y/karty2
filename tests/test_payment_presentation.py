import pytest
from kajovokarty.domain.columns import display_value, filter_options, filter_rows
from kajovokarty.domain.errors import explain
from kajovokarty.application.work import WorkService
from test_acceptance_traces import seed


@pytest.mark.parametrize("month,name", enumerate(
    ("ledna", "února", "března", "dubna", "května", "června", "července", "srpna",
     "září", "října", "listopadu", "prosince"), 1))
def test_czech_dates(month, name):
    assert display_value("date", f"2026-{month:02d}-07") == f"07. {name} 2026"


def test_dates_keep_filter_tokens_and_chronological_order():
    rows = [{"date": "2026-01-01"}, {"date": "2024-02-29"}, {"date": "2025-12-31"}]
    assert display_value("date", None) == ""
    assert display_value("date", "invalid") == "invalid"
    assert display_value("date", "2024-02-29") == "29. února 2024"
    assert [r["date"] for r in filter_rows(rows, sort=[("date", "asc")])] == ["2024-02-29", "2025-12-31", "2026-01-01"]
    assert filter_options(rows, "date")[0] == ("29. února 2024", '"2024-02-29"')


def test_unmatched_source_has_informational_reason(db):
    seed(db, "BOOKING")
    row = WorkService(db).query()["rows"][0]
    assert row["reason"] == "NOT_YET_MATCHED"
    for code in (row["reason"], "Dosud nepárováno"):
        assert display_value("reason", code) == "Dosud nepárováno"
        assert explain(code).severity == "INFO"
    assert explain("INTERNAL_ERROR").severity == "ERROR"
    assert WorkService(db).query({"reason": ["Dosud nepárováno"]})["total"] == 1


def test_payment_ui_restores_old_layout_and_switches_sources(db):
    from PySide6.QtWidgets import QApplication
    from kajovokarty.ui.main import MainWindow
    from kajovokarty.ui.models import HIDDEN_PAYMENT_COLUMNS
    from test_gui import spin
    seed(db, "BOOKING")
    seed(db, "BANK_CARD")
    seed(db, "CASHBOOK_CARD")
    app = QApplication.instance() or QApplication([])
    window = MainWindow(db)
    errors = []
    window.show_error = lambda error: errors.append(error.code)
    spin(lambda: not window.jobs)
    # Simulate a saved pre-upgrade layout in which every column is visible.
    for index in range(window.model.columnCount()):
        window.table.setColumnHidden(index, False)
    state = bytes(window.table.horizontalHeader().saveState().toBase64()).decode()
    window.catalog.save_view("columns:0", state)
    window.displayed_layout = None
    window.column_states[0] = {"reason": ['"anything"'], "note": ['"missing"'], "leaf_count": ['999']}
    window.sort_order = [("leaf_count", "desc")]
    window.advanced = {"kind": ["BOOKING"]}
    window.refresh()
    spin(lambda: not window.jobs)
    assert window.model.rowCount() == 1
    assert dict(window.model.columns)["primary_identifier"] == "Booking.com ID"
    assert dict(window.model.columns)["leaf_count"] == "Počet plateb"
    assert not window.column_states[0]
    assert window.sort_order == [("date", "asc")]
    for index, (key, _) in enumerate(window.model.columns):
        assert window.table.isColumnHidden(index) == (key in HIDDEN_PAYMENT_COLUMNS)
    assert not errors
    # Mixed sources restore the neutral heading. Other screens retain columns.
    window.advanced = {}
    window.refresh()
    spin(lambda: not window.jobs)
    assert window.model.rowCount() == 3
    assert dict(window.model.columns)["primary_identifier"] == "Identifikátor"
    for source_index in range(window.source.count()):
        window.source.setCurrentIndex(source_index)
        spin(lambda: not window.jobs)
        expected = "Booking.com ID" if window.filters().get("kind") == ["BOOKING"] else "Identifikátor"
        assert dict(window.model.columns)["primary_identifier"] == expected
    for scope in (1, 4, 0):
        window.nav.setCurrentRow(scope)
        spin(lambda: not window.jobs)
        for index, (key, _) in enumerate(window.model.columns):
            if key in HIDDEN_PAYMENT_COLUMNS:
                assert window.table.isColumnHidden(index)
    window.nav.setCurrentRow(2)
    spin(lambda: not window.jobs)
    assert all(not window.table.isColumnHidden(i) for i in range(window.model.columnCount()))
    window.close()
    reopened = MainWindow(db)
    spin(lambda: not reopened.jobs)
    for index, (key, _) in enumerate(reopened.model.columns):
        if key in HIDDEN_PAYMENT_COLUMNS:
            assert reopened.table.isColumnHidden(index)
    reopened.close()
    app.processEvents()


def test_group_identifier_is_not_a_booking_reference():
    from PySide6.QtCore import Qt
    from kajovokarty.ui.models import TableModel, payment_columns
    model = TableModel([{"type": "GROUP", "primary_identifier": "G123"}], payment_columns(True))
    index = [k for k, _ in model.columns].index("primary_identifier")
    assert model.data(model.index(0, index), Qt.DisplayRole) == ""


@pytest.mark.parametrize('kind,short', [('BANK_CARD', 'T'), ('CASHBOOK_CARD', 'P'), ('BOOKING', 'B')])
def test_compact_display_preserves_raw_values_and_tooltips(kind, short):
    from PySide6.QtCore import Qt
    from kajovokarty.ui.models import TableModel
    model = TableModel([{'kinds': [kind], 'date': '2026-05-23'}],
                       [('kinds', 'Zdroj'), ('date', 'Datum')])
    assert model.data(model.index(0, 0)) == short
    assert model.data(model.index(0, 0), Qt.UserRole) == [kind]
    assert model.data(model.index(0, 0), Qt.ToolTipRole) == display_value('kinds', [kind])
    assert model.data(model.index(0, 1)) == '23.05.2026'
    assert model.data(model.index(0, 1), Qt.UserRole) == '2026-05-23'
