import os

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


def test_real_drop_route_pair_detach_and_undo(db):
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
    pos = window.table.visualRect(window.model.index(target_index, 0)).center()
    event = QDropEvent(QPointF(pos), Qt.MoveAction, mime, Qt.LeftButton, Qt.NoModifier)
    window.table.dropEvent(event)
    spin(lambda: not window.jobs and window.pair_panel.current is not None)
    gid = window.pair_panel.current["id"]
    assert event.isAccepted() and window.pair_panel.current["resolved"]
    assert window.pair_panel.model.rowCount() == 2
    member = next(r for r in window.pair_panel.model.rows if r["id"] == bank)
    mime = window.pair_panel.table.mime_for_rows([member])
    event = QDropEvent(
        QPointF(10, 10), Qt.MoveAction, mime, Qt.LeftButton, Qt.NoModifier
    )
    window.pair_panel.free_area.dropEvent(event)
    spin(lambda: not window.jobs and window.model.rowCount() == 2)
    assert not errors
    window.registry.actions["undo"].trigger()
    spin(lambda: not window.jobs and window.model.rowCount() == 0)
    assert set(window.work.evidence(gid)["children"]) == {cash, bank}
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


def test_all_main_views_expose_sort_and_filter_on_every_column(db, fixtures, wire):
    from kajovokarty.application.imports import ImportService, ImportInput
    from kajovokarty.application.sync import SyncService
    from kajovokarty.application.settings import SettingsService
    from test_api import client

    _app = QApplication.instance() or QApplication([])
    importer = ImportService(db)
    importer.commit(
        importer.preflight([ImportInput("BOOKING", str(fixtures / "booking_a.csv"))]).id
    )
    sync = SyncService(db, SettingsService(db))
    http = client(wire)
    try:
        sync.full(http, scope=("2026-09-07", "2026-09-08"))
    finally:
        http.close()
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
        columns = list(window.model.columns)
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
