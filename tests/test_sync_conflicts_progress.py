import copy
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from kajovokarty.domain.helpers import invoice_rows, normalize_entity
from kajovokarty.ui.sync_progress import SyncProgressDialog


def invoice_fixture(wire):
    items = [
        {"id": "same-api-id", "label": "Accommodation", "unit_price": 1100, "order": 0},
        {"id": "food", "label": "Food", "unit_price": 400, "order": 1},
        {"id": "fee", "label": "Fee", "unit_price": 100, "order": 2},
        {"id": "same-api-id", "label": "Deposit", "unit_price": -1600, "total": -1600, "order": 0},
    ]
    wire["/invoice/I1"]["data"]["items"] = copy.deepcopy(items)
    wire["/invoice"]["data"][0]["items"] = copy.deepcopy(items)
    return items


def test_identical_occurrences_and_parent_identity():
    item = {"id": "x", "total": 10}
    rows = list(invoice_rows("A", [item, item], {}, "EUR"))
    assert len({i for raw, i in rows}) == 2
    assert rows[0][1] != next(invoice_rows("B", [item], {}, "EUR"))[1]


def test_deposit_breakdown_is_not_treated_as_invoice_rows():
    raw = {"id": "D", "items": [{"method": "card", "amount": 100}],
           "deposit": [{"status": "held", "amount": 100}]}
    assert normalize_entity("security_deposit", raw, {}) == raw


def test_progress_does_not_add_details_to_reservations():
    app = QApplication.instance() or QApplication([])
    dialog = SyncProgressDialog(None, lambda: None)
    try:
        dialog.update_progress({"type": "sync_progress", "phase": "list:/reservation",
                                "completed": 15507, "total": 15507, "unit": "rezervací", "message": "Seznam"})
        for _ in range(20001):
            dialog.update_progress("API ← HTTP 200: 1 položek")
        assert dialog.items == dialog.expected == 15507
        dialog.update_progress({"type": "sync_progress", "phase": "reservations", "completed": 25,
                                "total": 100, "unit": "vybraných rezervací", "message": "Vazby"})
        assert dialog.bar.value() == 25 and dialog.bar.maximum() == 100
        dialog.update_progress({"type": "api_call", "calls": 20001})
        assert dialog.items == 25 and dialog.calls == 20001
        dialog.update_progress({"type": "sync_progress", "phase": "saving", "completed": 0,
                                "total": None, "unit": "", "message": "Ukládám"})
        assert dialog.bar.maximum() == 0
        assert "úspěšně" not in dialog.eta.text()
    finally:
        dialog.finish()
        app.processEvents()
