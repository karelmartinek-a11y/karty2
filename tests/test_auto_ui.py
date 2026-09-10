import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import json
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QToolBar, QDialog, QPlainTextEdit
from kajovokarty.ui.main import MainWindow
from kajovokarty.application.imports import ImportService, ImportInput
from test_acceptance_traces import seed
from test_gui import spin


@pytest.mark.parametrize("cancel_after_one", [False, True])
def test_auto_only_button_ignores_filters_blocks_double_click_and_shows_result(
    db, fixtures, monkeypatch, cancel_after_one
):
    app = QApplication.instance() or QApplication([])
    for n in (1, 2):
        seed(db, "CASHBOOK_CARD", vs=str(n), minute=f"{n:02d}")
        seed(db, "BANK_CARD", vs=str(n), seq=str(n))
    window = MainWindow(db)
    calls = []
    original = window.matching.run

    def tracked(cancel, progress):
        calls.append(1)

        def pulse(message):
            progress(message)
            if cancel_after_one and "skupin 1" in message:
                cancel.set()

        return original(cancel, pulse)

    monkeypatch.setattr(window.matching, "run", tracked)
    window.show()
    spin(lambda: not window.jobs)
    importer = ImportService(db)
    preview = importer.preflight(
        [ImportInput("BOOKING", str(fixtures / "booking_a.csv"))]
    )
    window.run(lambda p: importer.commit(preview.id), window.after_mutation)
    spin(lambda: not window.jobs)
    window.set_column_filter("currency", [])
    spin(lambda: not window.jobs and window.model.rowCount() == 0)
    window.search.setText("nenalezitelná")
    window.refresh()
    spin(lambda: not window.jobs)
    assert calls == []
    action = window.registry.actions["auto"]
    button = next(
        b
        for bar in window.findChildren(QToolBar)
        if (b := bar.widgetForAction(action)) is not None
    )
    QTest.mouseClick(button, Qt.LeftButton)
    assert window.busy and not action.isEnabled()
    QTest.mouseClick(button, Qt.LeftButton)
    spin(lambda: not window.jobs)
    assert calls == [1]
    dialogs = [
        d
        for d in window.findChildren(QDialog)
        if d.objectName() == "automaticMatchingResult" and d.isVisible()
    ]
    assert len(dialogs) == 1
    with db.connect() as c:
        row = c.execute("SELECT * FROM operation WHERE type='AUTO_MATCH'").fetchone()
        result = json.loads(row["recovery_json"])
    assert result["analyzed_leaves"] == 25
    assert result["created_groups"] == (1 if cancel_after_one else 2)
    assert result["newly_resolved_leaves"] == (2 if cancel_after_one else 4)
    assert row["state"] == ("CANCELLED" if cancel_after_one else "COMPLETED")
    assert window.model.rowCount() == 0  # Active filters are not the matching scope.
    content = dialogs[0].findChild(QPlainTextEdit).toPlainText()
    assert "CZK" in content and "EUR" in content and "Běh:" in content
    if cancel_after_one:
        assert "přerušen" in content
    dialogs[0].close()
    window.search.clear()
    window.set_column_filter(None, None)
    spin(lambda: not window.jobs)
    assert calls == [1]
    window.close()
    app.processEvents()
