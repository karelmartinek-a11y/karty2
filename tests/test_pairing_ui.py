import os
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt, QPoint, QPointF
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import QApplication, QLineEdit, QListWidget, QPushButton
from PySide6.QtTest import QTest
from kajovokarty.ui.main import MainWindow
from kajovokarty.ui.work_table import WorkTable
from kajovokarty.ui.models import TableModel
from kajovokarty.ui.evidence_tree import EvidenceTree, EvidenceItem, RAW_ROLE
from kajovokarty.domain.columns import value_token
from test_acceptance_traces import seed
from test_gui import spin


def finish(window):
    window.panel_timer.stop()
    window.view_timer.stop()
    spin(lambda: not window.jobs)
    window.close()
    QApplication.processEvents()


def test_actual_header_filter_menu_and_empty_selection(db):
    _app = QApplication.instance() or QApplication([])
    seed(db, "CASHBOOK_CARD", "50.00")
    seed(db, "BANK_CARD", "50.00")
    window = MainWindow(db)
    window.show()
    errors = []
    window.show_error = lambda e: errors.append(e)
    spin(lambda: not window.jobs)
    controller = window.table.column_controller
    field = next(
        i for i, (key, label) in enumerate(window.model.columns) if key == "kinds"
    )
    header = controller.header
    # The visible arrow is a real input path, not just a direct service call.
    x = header.sectionViewportPosition(field) + header.sectionSize(field) - 10
    QTest.mouseClick(
        header.viewport(), Qt.LeftButton, pos=QPoint(x, header.height() // 2)
    )
    spin(
        lambda: controller.menu is not None
        and controller.menu.findChild(QPushButton, "applyColumnFilter").isEnabled()
    )
    menu = controller.menu
    search = menu.findChild(QLineEdit, "columnFilterSearch")
    QTest.keyClicks(search, "Booking")
    values = menu.findChild(QListWidget, "columnFilterValues")
    assert all(values.item(i).isHidden() for i in range(values.count()))
    search.clear()
    for i in range(values.count()):
        values.item(i).setCheckState(Qt.Unchecked)
    QTest.mouseClick(menu.findChild(QPushButton, "applyColumnFilter"), Qt.LeftButton)
    spin(lambda: not window.jobs and window.model.rowCount() == 0)
    assert window.column_states[0]["kinds"] == []
    window.refresh()
    spin(lambda: not window.jobs)
    assert window.model.rowCount() == 0
    controller.change(None, None)
    spin(lambda: not window.jobs and window.model.rowCount() == 2)
    assert not errors
    finish(window)


def test_real_drop_route_adds_to_draft_and_save_undo(db):
    _app = QApplication.instance() or QApplication([])
    cash = seed(db, "CASHBOOK_CARD", "50.00")
    bank = seed(db, "BANK_CARD", "50.00")
    window = MainWindow(db)
    window.resize(1700, 900)
    window.show()
    errors = []
    window.show_error = lambda e: errors.append(e)
    spin(lambda: not window.jobs)
    target_index = next(i for i, r in enumerate(window.model.rows) if r["id"] == cash)
    source = next(r for r in window.model.rows if r["id"] == bank)
    mime = window.table.mime_for_rows([source])
    visible_column = next(i for i in range(window.model.columnCount()) if not window.table.isColumnHidden(i))
    pos = window.table.visualRect(window.model.index(target_index, visible_column)).center()
    event = QDropEvent(QPointF(pos), Qt.MoveAction, mime, Qt.LeftButton, Qt.NoModifier)
    window.table.dropEvent(event)
    spin(lambda: not window.jobs and window.pair_panel.current is not None)
    assert event.isAccepted() and not window.pair_panel.current["resolved"]
    assert window.pair_panel.model.rowCount() == 2
    for row in window.pair_panel.model.rows:
        original = next(r for r in window.model.rows if r['id'] == row['id'])
        for key in ('kinds', 'date', 'amount', 'currency', 'primary_identifier', 'description'):
            assert row[key] == original[key]
    assert all(window.pair_panel.model.data(window.pair_panel.model.index(0, c))
               for c in range(5))
    assert window.pair_panel.save.isEnabled()
    # Dropping an existing draft row back into the panel must not remove it.
    panel_mime = window.pair_panel.table.mime_for_rows([window.pair_panel.model.rows[0]])
    panel_event = QDropEvent(QPointF(5, 5), Qt.MoveAction, panel_mime, Qt.LeftButton, Qt.NoModifier)
    window.pair_panel.table.dropEvent(panel_event)
    spin(lambda: not window.jobs)
    assert panel_event.isAccepted()
    assert window.pair_panel.model.rowCount() == 2
    window.pair_panel.save.click()
    spin(lambda: not window.jobs and window.work.query({"status": "resolved"}, page_size=0)["total"] == 1)
    gid = window.work.query({"status": "resolved"}, page_size=0)["rows"][0]["id"]
    assert not errors
    window.registry.actions["undo"].trigger()
    spin(lambda: not window.jobs and window.work.query({"status": "resolved"}, page_size=0)["total"] == 0)
    assert set(window.work.evidence(gid)["children"]) == {cash, bank}
    finish(window)


def test_saved_group_is_removed_from_current_and_candidate_views(db):
    _app = QApplication.instance() or QApplication([])
    cash = seed(db, "CASHBOOK_CARD", "50.00")
    bank = seed(db, "BANK_CARD", "50.00")
    window = MainWindow(db)
    window.show()
    spin(lambda: not window.jobs)

    rows = [
        r for r in window.work.query({"status": "unresolved"}, page_size=0)["rows"]
        if r["id"] in {cash, bank}
    ]
    assert window.pair_panel.add_rows(rows)
    window.pair_panel.save.click()
    spin(lambda: not window.jobs and window.work.query({"status": "resolved"}, page_size=0)["total"] == 1)

    assert {r["id"] for r in window.model.rows}.isdisjoint({cash, bank})
    assert window.candidate_rows is None
    assert window.pair_panel.candidate_model.rowCount() == 0

    window.nav.setCurrentRow(4)
    spin(lambda: not window.jobs)
    assert {r["id"] for r in window.model.rows}.isdisjoint({cash, bank})
    finish(window)


@pytest.mark.parametrize('kind', ['BANK_CARD', 'CASHBOOK_CARD', 'BOOKING'])
def test_candidate_source_filter_and_column_order(db, kind):
    _app = QApplication.instance() or QApplication([])
    ids = {k: seed(db, k) for k in ('BANK_CARD', 'CASHBOOK_CARD', 'BOOKING')}
    # A second row of the anchor's source proves this is a reversible filter.
    seed(db, kind, amount='51.00', seq='second', minute='01')
    window = MainWindow(db)
    window.show()
    spin(lambda: not window.jobs)
    anchor = next(r for r in window.model.rows if r['id'] == ids[kind])
    window.pair_panel.add_rows([anchor])
    window.pair_panel.candidates.click()
    spin(lambda: not window.jobs)
    panel = window.pair_panel
    expected = {value_token([k]) for k in ids if k != kind}
    assert set(panel.candidate_model.column_filters['kinds']) == expected
    assert set(window.column_states[4]['kinds']) == expected
    assert {r['id'] for r in window.model.rows} == {r['id'] for r in panel.candidate_model.rows}
    assert all(kind not in r['kinds'] for r in panel.candidate_model.rows)
    columns = ['kinds', 'date', 'amount', 'currency', 'primary_identifier', 'description']
    for table in (panel.table, panel.candidate_table):
        header = table.horizontalHeader()
        assert [table.model().columns[header.logicalIndex(i)][0] for i in range(header.count())] == columns
    panel.candidate_table.column_controller.change('kinds', None)
    spin(lambda: not window.jobs)
    assert any(kind in r['kinds'] for r in panel.candidate_model.rows)
    panel.candidates.click()
    spin(lambda: not window.jobs)
    assert set(panel.candidate_model.column_filters['kinds']) == expected
    panel.clear_draft()
    finish(window)


def test_empty_candidate_result_keeps_filter_accessible(db):
    _app = QApplication.instance() or QApplication([])
    seed(db, 'BANK_CARD')
    window = MainWindow(db)
    window.show()
    spin(lambda: not window.jobs)
    window.pair_dock.show()
    window.pair_panel.add_rows(window.model.rows)
    window.find_panel_candidates()
    spin(lambda: not window.jobs)
    assert window.pair_panel.candidate_model.rowCount() == 0
    assert window.pair_panel.candidate_table.isVisible()
    assert window.model.rowCount() == 0
    window.pair_panel.clear_draft()
    finish(window)


def test_obsolete_candidate_responses_are_ignored(db, monkeypatch):
    _app = QApplication.instance() or QApplication([])
    seed(db, 'BANK_CARD')
    seed(db, 'CASHBOOK_CARD')
    window = MainWindow(db)
    window.show()
    spin(lambda: not window.jobs)
    rows = list(window.model.rows)
    window.pair_panel.add_rows([rows[0]])
    pending = []
    original_run = window.run
    monkeypatch.setattr(window, 'run', lambda fn, done=None, *args, **kwargs: pending.append(done))
    window.find_panel_candidates()
    window.find_panel_candidates()
    pending[0]([rows[1]])
    assert window.candidate_context is None
    window.pair_panel.clear_draft()
    window.pair_panel.add_rows([rows[1]])
    pending[1]([rows[0]])
    assert window.candidate_context is None
    assert window.pair_panel.candidate_model.rowCount() == 0
    monkeypatch.setattr(window, 'run', original_run)
    window.pair_panel.clear_draft()
    finish(window)


def test_local_table_every_column_and_tree_context():
    _app = QApplication.instance() or QApplication([])
    model = TableModel(
        [
            {"id": "a", "amount": 200},
            {"id": "b", "amount": 1000},
            {"id": "c", "amount": -100},
        ],
        [("id", "ID"), ("amount", "Částka")],
    )
    table = WorkTable()
    table.setModel(model)
    table.selectRow(0)
    table.column_controller.apply_sort([("amount", "asc")])
    assert model.rows[table.selectionModel().selectedRows()[0].row()]["id"] == "a"
    assert [r["id"] for r in model.rows] == ["c", "a", "b"]
    model.set_column_filter("id", [value_token("b")])
    model.replace(model.source_rows)
    assert [r["id"] for r in model.rows] == ["b"]
    tree = EvidenceTree()
    tree.setHeaderLabels(["List", "Zdroj", "Částka", "Měna"])
    root = EvidenceItem(["G", "Skupina", "", "EUR"])
    tree.addTopLevelItem(root)
    for col, val in enumerate(["G", "GROUP", None, "EUR"]):
        root.setData(col, RAW_ROLE, val)
    for name, amount in [("A", 1000), ("B", 200)]:
        item = EvidenceItem([name, "BANK_CARD", str(amount), "EUR"])
        root.addChild(item)
        for col, val in enumerate([name, "BANK_CARD", amount, "EUR"]):
            item.setData(col, RAW_ROLE, val)
    tree.enable_filters()
    tree.set_sort([("amount", "asc")])
    assert root.child(0).text(0) == "B"
    tree.set_column_filter("identity", [value_token("A")])
    assert not root.isHidden()
    assert next(
        root.child(i) for i in range(2) if root.child(i).text(0) == "B"
    ).isHidden()
    assert not next(
        root.child(i) for i in range(2) if root.child(i).text(0) == "A"
    ).isHidden()
    tree.close()
    table.close()


def test_foreign_or_malformed_drag_is_rejected():
    _app = QApplication.instance() or QApplication([])
    table = WorkTable()
    table.workspace = "one"
    row = {
        "id": "id",
        "revision": 1,
        "type": "SOURCE",
        "lifecycle": "ACTIVE",
        "currency": "EUR",
    }
    mime = table.mime_for_rows([row])
    assert WorkTable.decode(mime, "two") is None
    mime.setData(WorkTable.MIME, b'{"rows":null}')
    assert WorkTable.decode(mime, "one") is None


def test_all_main_views_expose_sort_and_filter_on_visible_columns(db, fixtures, wire):
    from kajovokarty.application.imports import ImportService, ImportInput

    _app = QApplication.instance() or QApplication([])
    importer = ImportService(db)
    importer.commit(
        importer.preflight([ImportInput("BOOKING", str(fixtures / "booking_a.csv"))]).id
    )
    from test_accounts import import_sample
    import_sample(db)
    window = MainWindow(db)
    window.show()
    errors = []
    window.show_error = lambda e: errors.append(e)
    a = seed(db, "CASHBOOK_CARD", "50.00")
    b = seed(db, "BANK_CARD", "50.00")
    window.pairing.move([b], {b: 1}, target=a, target_revision=1)
    for scope in range(8):
        window.nav.setCurrentRow(scope)
        window.refresh()
        spin(lambda: not window.jobs)
        assert window.model.rows, scope
        row = dict(window.model.rows[0])
        columns = [column for i, column in enumerate(window.model.columns)
                   if not window.table.isColumnHidden(i)]
        for field, _ in columns:
            window.set_column_filter(None, None)
            spin(lambda: not window.jobs)
            window.set_column_filter(field, [value_token(row.get(field))])
            spin(lambda: not window.jobs)
            assert window.model.rows, (scope, field)
            assert all(
                value_token(r.get(field)) == value_token(row.get(field))
                for r in window.model.rows
            ), (scope, field)
            window.set_column_sort([(field, "asc")])
            spin(lambda: not window.jobs)
        window.set_column_filter(None, None)
        spin(lambda: not window.jobs)
    assert not errors
    finish(window)
