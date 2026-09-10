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
        QTest.qWait(10)
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
                and widget.windowTitle().startswith("Náhled importu")
            ):
                buttons = widget.findChild(QDialogButtonBox)
                QTest.mouseClick(buttons.button(QDialogButtonBox.Ok), Qt.LeftButton)

    timer = QTimer()
    timer.timeout.connect(accept_preview)
    timer.start(20)
    window.preflight([ImportInput("BOOKING", str(fixtures / "booking_a.csv"))])
    spin(lambda: window.model.rowCount() == 21 and not window.busy)
    timer.stop()
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


def test_settings_inline_validation_and_appearance(db):
    from PySide6.QtWidgets import QLineEdit, QLabel

    app = QApplication.instance() or QApplication([])
    window = MainWindow(db)
    window.show()
    spin(lambda: not window.jobs)
    stage = [0]

    def drive():
        dialog = next(
            (
                w
                for w in app.topLevelWidgets()
                if isinstance(w, QDialog)
                and w.isVisible()
                and w.windowTitle() == "Nastavení KájovoKarty"
            ),
            None,
        )
        if dialog is None:
            return
        edit = next(
            w
            for w in dialog.findChildren(QLineEdit)
            if w.accessibleName() == "Požadavků za sekundu"
        )
        buttons = dialog.findChild(QDialogButtonBox)
        if stage[0] == 0 and not window.busy:
            edit.setText("neplatné")
            stage[0] = 1
            buttons.button(QDialogButtonBox.Save).click()
        elif (
            stage[0] == 1
            and not window.busy
            and any("neplatná" in w.text() for w in dialog.findChildren(QLabel))
        ):
            assert db.path.exists()
            edit.setText("0.8")
            stage[0] = 2
            buttons.button(QDialogButtonBox.Save).click()

    timer = QTimer()
    timer.timeout.connect(drive)
    timer.start(20)
    window.settings_dialog()
    timer.stop()
    spin(lambda: not window.jobs)
    assert stage[0] == 2 and window.settings.get()["sync.requests_per_second"] == "0.8"
    window.view_timer.stop()
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
