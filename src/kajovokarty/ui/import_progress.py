"""One window from preparation through the acknowledged import result."""
import time
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QProgressBar, QPushButton, QPlainTextEdit, QInputDialog
from kajovokarty.application.import_batch import batch_text


class ImportProgressDialog(QDialog):
    def __init__(self, parent, cancel):
        super().__init__(parent)
        self.setObjectName("importProgressDialog")
        self.setWindowTitle("Import")
        self.setWindowModality(Qt.WindowModal)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.resize(820, 560)
        self.cancel = cancel
        self.completed = False
        self.stopping = False
        self.started = self.stage_started = time.monotonic()
        self.stage_key = None
        self.snapshot = {}
        layout = QVBoxLayout(self)
        self.phase = QLabel("Načítání – zjišťuji počet řádků…")
        self.phase.setWordWrap(True)
        layout.addWidget(self.phase)
        self.bar = QProgressBar()
        self.bar.setRange(0, 0)
        layout.addWidget(self.bar)
        self.counts = QLabel("Zjišťuji počet řádků…")
        self.counts.setWordWrap(True)
        layout.addWidget(self.counts)
        self.saved = QLabel("Skutečně uloženo: 0 plateb, 0 vazeb")
        layout.addWidget(self.saved)
        self.elapsed = QLabel()
        layout.addWidget(self.elapsed)
        self.details = QPlainTextEdit()
        self.details.setObjectName("importResultText")
        self.details.setReadOnly(True)
        self.details.hide()
        layout.addWidget(self.details)
        self.button = QPushButton("Zastavit import")
        self.button.setObjectName("importAction")
        self.button.clicked.connect(self.action)
        layout.addWidget(self.button)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(1000)
        self.tick()

    def update_progress(self, event):
        if self.completed:
            return
        if isinstance(event, dict) and "sheet_request" in event:
            try:
                if not self.cancel.is_set():
                    choice, ok = QInputDialog.getItem(self, "Výběr listu", event["name"], event["sheets"], 0, False)
                    event["answer"] = choice if ok else None
            finally:
                event["ready"].set()
            return
        data = getattr(event, "snapshot", None)
        if data is None:
            return
        self.snapshot = data
        key = (data["file_index"], data["stage"])
        if key != self.stage_key:
            self.stage_key = key
            self.stage_started = time.monotonic()
        if not self.stopping:
            self.phase.setText(f"Soubor {data['file_index']} z {data['file_total']}: {data['name']}\n{data['stage']}")
        total, current = data["total"], data["current"]
        if total is None:
            self.bar.setRange(0, 0)
            self.counts.setText("Zjišťuji počet řádků…" if data["stage"] in ("Načítání", "Kontrola") else "Dokončuji aktuální krok…")
        else:
            self.bar.setRange(0, 1000)
            self.bar.setValue(1000 if not total else min(1000, int(current * 1000 / total)))
            self.counts.setText("Soubor zpracován." if data["stage"] == "Soubor dokončen" else
                                f"Zpracováno {current} z {total} řádků tohoto kroku; zbývá {max(0, total-current)}.")
        self.saved.setText(f"Skutečně uloženo: {data['payments']} plateb, {data['accounts']} vazeb")
        self.tick()

    def tick(self):
        elapsed = int(time.monotonic() - self.started)
        text = f"Doba běhu: {elapsed // 60}:{elapsed % 60:02d}"
        d = self.snapshot
        seconds = time.monotonic() - self.stage_started
        if not self.completed and not self.stopping and d.get("total") and 0 < d.get("current", 0) < d["total"] and seconds >= 2:
            remaining = int(seconds * (d["total"] - d["current"]) / d["current"])
            text += f" · Odhad do konce aktuálního kroku: {remaining // 60}:{remaining % 60:02d}"
        self.elapsed.setText(text)

    def finish(self, reports, error=None):
        self.completed = True
        self.timer.stop()
        self.tick()
        failed = error is not None or any(r["state"] == "FAILED" for r in reports)
        stopped = any(r["state"] in ("CANCELLED", "NOT_STARTED") for r in reports)
        warnings = any(r["warnings"] for r in reports)
        title = "Import skončil s chybou" if failed else "Import zastaven" if stopped else "Import dokončen s upozorněním" if warnings else "Import dokončen"
        self.phase.setText(title)
        self.setWindowTitle(title)
        self.bar.setRange(0, 100)
        self.bar.setValue(100 if not failed and not stopped else 0)
        self.counts.setText(f"Úspěšné soubory: {sum(r['state'] == 'COMPLETED' for r in reports)} z {len(reports)}. "
                            f"S chybou: {sum(r['state'] == 'FAILED' for r in reports)}.")
        self.saved.setText(f"Skutečně uloženo: {sum(r['added'] for r in reports if r['kind'] != 'ACCOUNTS')} plateb, "
                           f"{sum(r['added'] for r in reports if r['kind'] == 'ACCOUNTS')} vazeb")
        self.details.setPlainText(batch_text(reports) + ("\n\n" + error.user_message if error else ""))
        self.details.show()
        self.button.setEnabled(True)
        self.button.setText("Hotovo")
        self.button.setFocus()
        self.show()
        self.raise_()
        self.activateWindow()

    def action(self):
        if self.completed:
            self.accept()
        elif not self.stopping:
            self.stopping = True
            self.cancel.set()
            self.phase.setText("Zastavuji – čekám na bezpečné dokončení kroku…")
            self.button.setEnabled(False)

    def reject(self):
        if self.completed:
            super().reject()
        else:
            self.action()

    def closeEvent(self, event):
        if self.completed:
            event.accept()
        else:
            self.action()
            event.ignore()
