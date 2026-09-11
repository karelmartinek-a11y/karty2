import copy
import json
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import httpx
import pytest
from PySide6.QtWidgets import QApplication
from kajovokarty.application.sync import SyncService
from kajovokarty.application.settings import SettingsService
from kajovokarty.application.refresh import RefreshService
from kajovokarty.domain.core import AppError
from kajovokarty.domain.helpers import invoice_rows, normalize_entity
from kajovokarty.infrastructure.betterhotel import BetterHotelClient, BASE
from kajovokarty.ui.sync_progress import SyncProgressDialog
from test_sync_period import mock_client


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


def test_duplicate_api_id_keeps_deposit_and_refresh(db, wire):
    invoice_fixture(wire)
    settings = SettingsService(db)
    sync = SyncService(db, settings)
    client = mock_client(wire, [])
    try:
        sync.full(client, scope=("2026-09-07", "2026-09-08"))
        def rows():
            return {r["external_id"]: json.loads(r["payload_json"])
                    for r in sync.entities() if r["resource_type"] == "invoice_item"}
        first = rows()
        assert len(first) == 4
        duplicated = [p for p in first.values() if p["source_item_id"] == "same-api-id"]
        assert len(duplicated) == 2
        assert next(p for p in duplicated if p["label"] == "Deposit")["signed_amount"] == "-1600.00"
        wire["/invoice/I1"]["data"]["items"].reverse()
        RefreshService(db, settings).refresh(client, "invoice", "I1", sync.state()["context_id"])
        assert rows() == first
        sync.full(client, scope=("2026-09-07", "2026-09-08"))
        assert rows() == first
    finally:
        client.close()


def test_identical_occurrences_and_parent_identity():
    item = {"id": "x", "total": 10}
    rows = list(invoice_rows("A", [item, item], {}, "EUR"))
    assert len({i for raw, i in rows}) == 2
    assert rows[0][1] != next(invoice_rows("B", [item], {}, "EUR"))[1]


def test_invoice_row_edge_accepts_equivalent_list_and_detail_encoding(db, wire):
    wire["/invoice"]["data"][0]["items"] = [{"id": "line", "label": None, "total": "10.000"}]
    wire["/invoice/I1"]["data"]["items"] = [{"id": "line", "label": "", "total": 10}]
    client = mock_client(wire, [])
    try:
        result = SyncService(db, SettingsService(db)).full(client, scope=("2026-09-07", "2026-09-08"))
        assert result["status"] == "READY"
    finally:
        client.close()


def test_financial_statistics_use_confirmed_api_parameter_names(db, wire):
    seen = []
    client = mock_client(wire, seen)
    try:
        SyncService(db, SettingsService(db)).full(client, scope=("2026-09-07", "2026-09-08"))
        assert next(params for path, params in seen if path == "/financial-stats") == {
            "from": "2026-09-07", "to": "2026-09-08"}
    finally:
        client.close()


def test_deposit_breakdown_is_not_treated_as_invoice_rows():
    raw = {"id": "D", "items": [{"method": "card", "amount": 100}],
           "deposit": [{"status": "held", "amount": 100}]}
    assert normalize_entity("security_deposit", raw, {}) == raw


def test_invoice_fetches_referenced_item_without_out_of_range_reservation(db, wire):
    wire["/reservation"]["data"] = []
    wire["/invoice"]["data"][0]["items"] = [{"id": "line", "bill_item_id": "outside", "total": 10}]
    wire["/bill-item/outside"] = {"data": {"id": "outside", "bill_id": "old-account", "amount": 10, "currency": "EUR"}}
    seen = []
    client = mock_client(wire, seen)
    sync = SyncService(db, SettingsService(db))
    try:
        sync.full(client, scope=("2026-09-07", "2026-09-08"))
    finally:
        client.close()
    assert any(p == "/bill-item/outside" for p, q in seen)
    assert not any(p.startswith("/reservation/") for p, q in seen)
    assert any(r["external_id"] == "outside" for r in sync.entities())


def test_true_invoice_conflict_is_recorded(db, wire):
    invoice_fixture(wire)
    wire["/invoice/I1"]["data"]["items"][0]["unit_price"] = 999
    client = mock_client(wire, [])
    try:
        with pytest.raises(AppError) as exc:
            SyncService(db, SettingsService(db)).full(client, scope=("2026-09-07", "2026-09-08"))
        assert exc.value.code == "API_SNAPSHOT_CONFLICT"
        evidence = db.path.parent / "diagnostics/conflicts" / (exc.value.details["diagnostic_id"] + ".json")
        payload = json.loads(evidence.read_text(encoding="utf-8"))
        assert "items" in payload["changed_fields"]
        assert payload["before_hash"] != payload["after_hash"]
        assert payload["entity_id"] == "I1"
    finally:
        client.close()


def test_legacy_currency_reference_and_sparse_note_are_resolved_by_detail(db, wire):
    invoice_fixture(wire)
    wire["/invoice"]["data"][0].update(currency="154", note=None, label=None)
    wire["/invoice/I1"]["data"].update(currency="EUR", note="Detail text", label="  ")
    client = mock_client(wire, [])
    sync = SyncService(db, SettingsService(db))
    try:
        sync.full(client, scope=("2026-09-07", "2026-09-08"))
    finally:
        client.close()
    invoice = next(r for r in sync.entities() if r["external_id"] == "I1")
    payload = json.loads(invoice["payload_json"])
    assert payload["currency"] == "EUR" and payload["currency_reference"] == "154"
    assert payload["note"] == "Detail text"
    assert all(json.loads(r["payload_json"])["currency"] == "EUR"
               for r in sync.entities() if r["resource_type"] == "invoice_item")


@pytest.mark.parametrize("list_currency,detail_currency,code", [
    ("EUR", "CZK", "API_SNAPSHOT_CONFLICT"),
    ("154", "154", "API_SCHEMA"),
])
def test_real_currency_conflict_or_unresolved_reference_stays_blocked(db, wire, list_currency, detail_currency, code):
    wire["/invoice"]["data"][0]["currency"] = list_currency
    wire["/invoice/I1"]["data"]["currency"] = detail_currency
    client = mock_client(wire, [])
    try:
        with pytest.raises(AppError) as exc:
            SyncService(db, SettingsService(db)).full(client, scope=("2026-09-07", "2026-09-08"))
        assert exc.value.code == code
    finally:
        client.close()


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


@pytest.mark.parametrize("server_total", [1, 3])
def test_inaccurate_server_total_becomes_unknown(server_total):
    calls = []
    def respond(request):
        more = not request.url.params.get("cursor")
        return httpx.Response(200, json={"data": [{"id": "a" if more else "b"}],
            "meta": {"total_count": server_total, "has_more": more, "cursor": "next"}})
    client = BetterHotelClient("a", "b", transport=httpx.MockTransport(respond), progress=calls.append)
    try:
        assert len(client.collection("/reservation")) == 2
    finally:
        client.close()
    events = [e for e in calls if isinstance(e, dict) and e.get("type") == "sync_progress"]
    assert events[-1]["total"] is None and events[-1]["completed"] == 2


def test_reservations_list_once_across_invoice_blocks(db, wire):
    seen = []
    client = mock_client(wire, seen)
    try:
        SyncService(db, SettingsService(db)).full(client, scope=("2026-09-01", "2026-09-11"))
    finally:
        client.close()
    assert sum(p == "/reservation" for p, q in seen) == 1
    assert sum(p == "/invoice" for p, q in seen) == 2


def test_resume_reservation_batch_restores_counts_and_skips_completed(db, wire):
    import threading
    cancel = threading.Event()
    wire["/reservation"]["data"] = []
    wire["/invoice"]["data"] = []
    for n in range(26):
        rid = f"R{n:03d}"
        raw = {"id": rid, "arrival": "2026-09-07", "departure": "2026-09-08"}
        wire["/reservation"]["data"].append(raw)
        wire[f"/reservation/{rid}"] = {"data": raw}
        for relation in ("invoice", "bill", "security-deposit"):
            wire[f"/reservation/{rid}/{relation}"] = {"data": []}
    def progress(event):
        if isinstance(event, dict) and event.get("phase") == "reservations" and event["completed"] == 25:
            cancel.set()
    sync = SyncService(db, SettingsService(db))
    client = mock_client(wire, [])
    client.cancel = cancel
    try:
        with pytest.raises(AppError) as exc:
            sync.full(client, scope=("2026-09-07", "2026-09-08"), progress=progress)
        assert exc.value.code == "CANCELLED"
    finally:
        client.close()
    with db.connect() as c:
        op, raw = c.execute("SELECT id,recovery_json FROM operation WHERE type='SYNC'").fetchone()
        checkpoint = json.loads(raw)
        assert checkpoint["phase"] == "RESERVATIONS"
    seen, events = [], []
    client = mock_client(wire, seen)
    try:
        sync.resume(client, op, events.append)
    finally:
        client.close()
    assert len(seen) == 4  # Three relation lists for the last reservation + statistics.
    counts = [e["completed"] for e in events if isinstance(e, dict) and e.get("phase") == "reservations"]
    assert counts[0] == 25 and counts[-1] == 26 and sorted(set(counts)) == [25, 26]
    assert sync.state()["status"] == "READY"
