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
        self.calls = self.items = self.expected = 0
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
        message = str(event)
        human = self.human_message(message)
        if message.startswith("API → GET "): self.calls += 1
        match = re.search(r"HTTP \d+: (\d+) ", message)
        if match: self.items += int(match.group(1))
        scope = re.search(r"API rozsah .*?: (\d+) záznamů", message)
        if scope: self.expected += int(scope.group(1))
        if not self.stopping: self.phase.setText(self.phase_message(message))
        self.detail.setText(human)
        total = max(self.items, self.expected)
        if total:
            self.bar.setRange(0, 1000); self.bar.setValue(min(1000, int(1000 * self.items / total)))
        self.total.setText(f"Zpracováno {self.items} z {total if total else 'celkový počet se zjišťuje'} datových záznamů | API volání: {self.calls}")
        elapsed = max(time.monotonic() - self.started, 0.001)
        if total and self.items and self.items < total:
            seconds = int((total - self.items) * elapsed / self.items)
            self.eta.setText(f"Odhad dokončení: za {seconds // 60}:{seconds % 60:02d} (přibližně {time.strftime('%H:%M', time.localtime(time.time() + seconds))})")
        elif total and self.items >= total: self.eta.setText("Odhad dokončení: dokončování detailů a ukládání…")
        else: self.eta.setText("Odhad dokončení: zjišťuji celkový rozsah…")
        self.tick()

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
