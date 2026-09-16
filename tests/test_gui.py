import os, time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox
from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtCore import QItemSelectionModel
from kajovokarty.ui.main import MainWindow
from kajovokarty.application.imports import ImportInput


def spin(predicate, seconds=8):
    deadline = time.monotonic() + seconds
    while not predicate() and time.monotonic() < deadline:
        QApplication.processEvents()
        # Let Python workers acquire the GIL between GUI event batches.
        # QTest.qWait can starve them, especially on Windows.
        time.sleep(0.01)
    assert predicate()


def test_actual_widgets_import_select_group(db, fixtures):
    app = QApplication.instance() or QApplication([])
    window = MainWindow(db)
    errors = []
    window.show_error = lambda e: errors.append(e.as_dict())
    window.show()
    spin(lambda: not window.jobs)
    assert not errors, errors
    assert window.model.rowCount() == 0 and window.title.text() == "Nevyřízené"

    def accept_preview():
        for widget in app.topLevelWidgets():
            if (
                isinstance(widget, QDialog)
                and widget.isVisible()
                and widget.objectName() == "bookingImportQueue"
            ):
                buttons = widget.findChild(QDialogButtonBox)
                QTest.mouseClick(buttons.button(QDialogButtonBox.Ok), Qt.LeftButton)

    timer = QTimer()
    timer.timeout.connect(accept_preview)
    timer.start(20)
    window.preflight([ImportInput("BOOKING", str(fixtures / "booking_a.csv"))])
    spin(lambda: window.model.rowCount() == 21 and not window.busy)
    timer.stop()
    for dialog in window.findChildren(QDialog):
        if dialog.objectName() == "importProgressDialog":
            dialog.close()
    selection = window.table.selectionModel()
    selection.select(
        window.model.index(0, 0), QItemSelectionModel.Select | QItemSelectionModel.Rows
    )
    selection.select(
        window.model.index(1, 0), QItemSelectionModel.Select | QItemSelectionModel.Rows
    )
    window.registry.actions["select"].trigger()
    spin(lambda: len(window.selection) == 2 and not window.busy)

    def accept_group():
        for widget in app.topLevelWidgets():
            if (
                isinstance(widget, QDialog)
                and widget.isVisible()
                and widget.windowTitle() == "Náhled finanční skupiny"
            ):
                widget.accept()

    timer.timeout.disconnect()
    timer.timeout.connect(accept_group)
    timer.start(20)
    window.registry.actions["group"].trigger()
    spin(lambda: window.model.rowCount() == 20 and not window.busy)
    timer.stop()
    assert any(r["type"] == "GROUP" for r in window.model.rows)
    window.search.setText("nenalezitelná-fráze")
    spin(lambda: window.model.rowCount() == 0)
    window.search.clear()
    spin(lambda: window.model.rowCount() == 20)
    window.registry.actions["undo"].trigger()
    spin(lambda: window.model.rowCount() == 21 and not window.busy)
    window.view_timer.stop()
    spin(lambda: not window.jobs)
    window.close()
    app.processEvents()
    assert not errors, errors


def test_settings_without_api_and_persisted_import_folder(db, tmp_path):
    from PySide6.QtWidgets import QLineEdit, QDialogButtonBox
    app = QApplication.instance() or QApplication([])
    window = MainWindow(db)
    window.show()
    spin(lambda: not window.jobs)
    errors = []

    def drive():
        dialog = app.activeModalWidget()
        if dialog is None:
            return
        try:
            edits = {w.accessibleName(): w for w in dialog.findChildren(QLineEdit)}
            assert not any("Token" in n or "Proxy" in n or "Požadavků" in n for n in edits)
            edits["Poslední složka Účtů"].setText(str(tmp_path))
            dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Save).click()
        except Exception as error:
            errors.append(error)
            dialog.reject()

    QTimer.singleShot(50, drive)
    window.settings_dialog()
    spin(lambda: not window.jobs)
    assert not errors
    assert window.settings.get()["imports.last_directory.ACCOUNTS"] == str(tmp_path)
    window.close()
    app.processEvents()


def test_table_ctrl_a_and_text_undo_do_not_mutate(db, fixtures):
    app = QApplication.instance() or QApplication([])
    from kajovokarty.application.imports import ImportService

    service = ImportService(db)
    service.commit(
        service.preflight(
            [ImportInput("CASHBOOK_CARD", str(fixtures / "cashbook_year.xls"))]
        ).id
    )
    window = MainWindow(db)
    window.show()
    spin(lambda: not window.jobs)
    window.table.setFocus()
    QTest.keyClick(window.table, Qt.Key_A, Qt.ControlModifier)
    assert len(window.selected_ids()) == 1055 and window.model.rowCount() == 500
    window.search.setFocus()
    QTest.keyClicks(window.search, "zkouska")
    QTest.keyClick(window.search, Qt.Key_Z, Qt.ControlModifier)
    spin(lambda: not window.jobs)
    assert not window.work.history()
    window.view_timer.stop()
    window.close()
    app.processEvents()
