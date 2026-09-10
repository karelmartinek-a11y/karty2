"""Real worker-to-popup delivery, persisted counts, cancellation and error cleanup."""

import os
import threading
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from kajovokarty.ui.main import MainWindow
from test_acceptance_traces import seed
from test_gui import spin


@pytest.mark.parametrize("outcome", ["complete", "cancel", "error"])
def test_live_popup_reports_commits_and_closes_after_terminal_state(
    db, monkeypatch, outcome
):
    app = QApplication.instance() or QApplication([])
    for n in (1, 2):
        seed(db, "CASHBOOK_CARD", vs=str(n), minute=f"{n:02d}")
        seed(db, "BANK_CARD", vs=str(n), seq=str(n))
    window = MainWindow(db)
    window.show()
    spin(lambda: not window.jobs)
    original = window.matching.run
    release = threading.Event()
    snapshots = []
    paused = False

    def tracked(cancel, progress):
        def report(event):
            nonlocal paused
            progress(event)
            data = getattr(event, "snapshot", None)
            if data is not None:
                snapshots.append(data)
                if data["groups"] == 1 and not paused:
                    paused = True
                    assert release.wait(6), "UI did not release worker"
                    if outcome == "error":
                        raise RuntimeError("synthetic failure")

        return original(cancel, report)

    monkeypatch.setattr(window.matching, "run", tracked)
    try:
        window.start_auto()
        dialog = window.auto_progress
        assert dialog.isVisible() and dialog.bar.maximum() == 0
        spin(lambda: dialog.values["groups"].text() == "1")
        assert window.busy and dialog.isVisible()
        assert dialog.values["total"].text() == "4"
        assert dialog.values["resolved"].text() == "2"
        assert dialog.values["remaining"].text() == "2"
        assert "EUR: spárováno 2, zbývá 2" in dialog.currencies.text()
        assert "VS" in dialog.phase.text()
        assert "Dokončeno 1 z 2" in dialog.detail.text()
        assert dialog.bar.value() == 500
        with db.connect() as c:
            assert (
                c.execute("SELECT count(*) FROM reconciliation_group").fetchone()[0]
                == 1
            )
        if outcome == "complete" and os.environ.get("KAJOVO_PROGRESS_SCREENSHOT"):
            dialog.grab().save(os.environ["KAJOVO_PROGRESS_SCREENSHOT"])
        if outcome == "cancel":
            QTest.mouseClick(dialog.stop, Qt.LeftButton)
            assert window.cancel.is_set() and not dialog.stop.isEnabled()
            dialog.close()  # Closing during cancellation must not hide progress early.
            assert dialog.isVisible()
        release.set()
        spin(lambda: not window.jobs)
        assert not any(
            w.objectName() == "automaticMatchingProgress"
            for w in app.topLevelWidgets()
            if w.isVisible()
        )
        with db.connect() as c:
            state = c.execute(
                "SELECT state FROM operation WHERE type='AUTO_MATCH'"
            ).fetchone()[0]
        assert (
            state
            == {"complete": "COMPLETED", "cancel": "CANCELLED", "error": "FAILED"}[
                outcome
            ]
        )
        # All snapshots count only committed pairs and keep per-step bounds exact.
        assert any(s["groups"] == 0 for s in snapshots)
        for s in snapshots:
            assert s["resolved"] == 2 * s["groups"]
            assert s["remaining"] == s["total"] - s["resolved"]
            if s["step_total"] is not None:
                assert 0 <= s["step_done"] <= s["step_total"]
        if outcome == "complete":
            assert snapshots[-1]["groups"] == 2
    finally:
        release.set()
        spin(lambda: not window.jobs)
        for dialog in window.findChildren(type(window.auto_progress)):
            if dialog.isVisible():
                dialog.finish()
        window.close()
        app.processEvents()
