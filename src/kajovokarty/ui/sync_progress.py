"""Static, human-readable progress dialog for BetterHotel synchronization."""
import re
import time
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QProgressBar, QPushButton


class SyncProgressDialog(QDialog):
    LABELS = {
        "/currency": "číselník měn", "/invoice": "seznam faktur",
        "/reservation": "seznam rezervací", "/bill": "účty",
        "/bill-item": "položky účtů", "/invoice-item": "položky faktur",
        "/security-deposit": "kauce",
    }
    DETAILS = {
        "invoice": "fakturu", "reservation": "rezervaci", "bill": "účet",
        "bill-item": "položku účtu", "invoice-item": "položku faktury",
        "security-deposit": "kauci",
    }

    def __init__(self, parent, cancel):
        super().__init__(parent)
        self.setObjectName("betterHotelSyncProgress")
        self.setWindowTitle("Načítání BetterHotelu — průběh")
        self.resize(700, 300)
        self.setModal(False)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.cancel_callback = cancel
        self.stopping = self.finished = False
        self.calls = self.items = 0
        self.expected = None
        self.unit = ""
        self.current_phase = "preparing"
        self.started = time.monotonic()
        layout = QVBoxLayout(self)
        self.phase = QLabel("Připravuji načítání…")
        self.phase.setWordWrap(True); self.phase.setFixedHeight(44); layout.addWidget(self.phase)
        self.bar = QProgressBar(); self.bar.setRange(0, 0); self.bar.setFixedHeight(22); layout.addWidget(self.bar)
        self.detail = QLabel("Čekám na první data z BetterHotelu…")
        self.detail.setWordWrap(True); self.detail.setFixedHeight(44); layout.addWidget(self.detail)
        self.total = QLabel("Zpracováno 0 z celkového počtu, který se zjišťuje…")
        self.total.setFixedHeight(26); layout.addWidget(self.total)
        self.elapsed = QLabel("Doba běhu: 0:00"); self.elapsed.setFixedHeight(26); layout.addWidget(self.elapsed)
        self.eta = QLabel("Odhad dokončení: zjišťuji rozsah…")
        self.eta.setFixedHeight(26); layout.addWidget(self.eta)
        self.stop = QPushButton("Zrušit načítání"); self.stop.clicked.connect(self.request_cancel); layout.addWidget(self.stop)
        self.timer = QTimer(self); self.timer.timeout.connect(self.tick); self.timer.start(1000)

    def update_progress(self, event):
        if isinstance(event, dict):
            if event.get("type") == "api_call":
                self.calls = event["calls"]
            elif event.get("type") == "sync_progress":
                self.current_phase = event["phase"]
                self.items = event["completed"]
                self.expected = event.get("total")
                self.unit = event.get("unit", "")
                if not self.stopping:
                    self.phase.setText(event["message"])
                if self.expected is None:
                    self.bar.setRange(0, 0)
                else:
                    self.bar.setRange(0, max(1, self.expected))
                    self.bar.setValue(self.items)
            self.render_counts()
        else:
            self.detail.setText(self.human_message(str(event)))
        self.tick()

    def render_counts(self):
        known = self.expected is not None
        count = f"{self.items} z {self.expected}" if known else str(self.items)
        self.total.setText(f"{count} {self.unit} | API: {self.calls}")
        self.eta.setText(self.phase_hint())

    def phase_hint(self):
        if self.current_phase == "completed":
            return "Načítání úspěšně dokončeno."
        if self.expected is None:
            return "Celkový rozsah této fáze není znám; čas dokončení nelze spolehlivě odhadnout."
        return "Průběh aktuální fáze. Následující kroky mají vlastní počty."

    def phase_message(self, message):
        if message.startswith("API → GET "): return "Načítám data z BetterHotelu"
        if message.startswith("API ←"): return "Zpracovávám přijatá data"
        if message.startswith("API stránka") or message.startswith("API rozsah"): return "Zpracovávám přijatá data"
        if message.startswith("Načítám stránku"): return "Načítám další část seznamu"
        if message.startswith("Zpracováno"): return "Zpracovávám data"
        if message.startswith("Dokončeno"): return "Dokončuji datový blok"
        return message

    def human_message(self, message):
        if message.startswith("API stránka "):
            m = re.search(r"API stránka ([^:]+): (.+)", message)
            if m: return f"{self.LABELS.get(m.group(1), 'seznam dat')}: záznamy {m.group(2)}"
        if message.startswith("API rozsah "):
            m = re.search(r"API rozsah ([^:]+): (\d+) záznamů", message)
            if m: return f"{self.LABELS.get(m.group(1), 'seznam dat')}: celkem {m.group(2)} záznamů"
        if message.startswith("API → GET "):
            path = message.split("GET ", 1)[1].split("?", 1)[0].split("/api/", 1)[-1]
            parts = path.split("/")
            if len(parts) >= 5 and parts[3] in self.DETAILS: return f"Načítám {self.DETAILS[parts[3]]} č. {parts[4]}"
            endpoint = "/" + parts[3] if len(parts) > 3 else ""
            return f"Načítám {self.LABELS.get(endpoint, 'data')}"
        if message.startswith("API ← HTTP"):
            m = re.search(r"HTTP (\d+): (\d+) položek", message)
            return f"Odpověď přijata: {m.group(2)} záznamů (HTTP {m.group(1)})" if m else "Odpověď přijata"
        if message.startswith("API !"): return "Síťová chyba — opakuji načtení"
        return message.replace("položek", "záznamů")

    def tick(self):
        seconds = int(time.monotonic() - self.started)
        self.elapsed.setText(f"Doba běhu: {seconds // 60}:{seconds % 60:02d}")

    def request_cancel(self):
        if self.stopping or self.finished: return
        self.stopping = True; self.stop.setEnabled(False)
        self.phase.setText("Ruším načítání — čekám na bezpečné dokončení kroku…")
        self.cancel_callback()

    def reject(self): self.request_cancel()

    def closeEvent(self, event):
        if not self.finished: self.request_cancel(); event.ignore()
        else: event.accept()

    def finish(self):
        self.finished = True; self.timer.stop(); self.close()
