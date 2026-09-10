"""Live automatic matching progress; closing requests safe cancellation."""

import time
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLabel,
    QProgressBar,
    QGridLayout,
    QPushButton,
    QPlainTextEdit,
)


class AutoProgressDialog(QDialog):
    def __init__(self, parent, cancel):
        super().__init__(parent)
        self.setObjectName("automaticMatchingProgress")
        self.setWindowTitle("Automatické párování — průběh")
        self.resize(700, 490)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.cancel_callback = cancel
        self.stopping = self.finished = False
        self.started = time.monotonic()
        self.last_stage = None
        layout = QVBoxLayout(self)
        self.phase = QLabel("Připravuji běh a čekám na přístup k databázi…")
        self.phase.setWordWrap(True)
        layout.addWidget(self.phase)
        self.bar = QProgressBar()
        self.bar.setRange(0, 0)
        layout.addWidget(self.bar)
        self.detail = QLabel("Počet dat zjišťuji…")
        self.detail.setWordWrap(True)
        layout.addWidget(self.detail)
        self.search = QLabel()
        self.search.setWordWrap(True)
        layout.addWidget(self.search)
        grid = QGridLayout()
        self.values = {}
        for i, (key, label) in enumerate(
            [
                ("total", "Položek na začátku běhu"),
                ("resolved", "Nově spárovaných položek"),
                ("remaining", "Dosud nespárovaných položek"),
                ("groups", "Uložených skupin"),
                ("round", "Aktuální kolo"),
            ]
        ):
            grid.addWidget(QLabel(label), i, 0)
            value = QLabel("—")
            value.setStyleSheet("font-weight: bold; font-size: 16px")
            grid.addWidget(value, i, 1)
            self.values[key] = value
        layout.addLayout(grid)
        self.currencies = QLabel("CZK: —     EUR: —")
        layout.addWidget(self.currencies)
        hint = QLabel(
            "Průběh platí pro aktuální krok. Nespárovaná položka může být již prověřená.\nDalší kolo ověří nové možnosti; nejednoznačné shody zůstanou nespárované."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.history = QPlainTextEdit()
        self.history.setReadOnly(True)
        self.history.setMaximumBlockCount(100)
        layout.addWidget(self.history)
        self.elapsed = QLabel()
        layout.addWidget(self.elapsed)
        self.stop = QPushButton("Zrušit párování")
        self.stop.clicked.connect(self.request_cancel)
        layout.addWidget(self.stop)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(1000)
        self.tick()

    def tick(self):
        seconds = int(time.monotonic() - self.started)
        self.elapsed.setText(f"Doba běhu: {seconds // 60}:{seconds % 60:02d}")

    def update_progress(self, event):
        data = getattr(event, "snapshot", None)
        if data is None:
            if not self.stopping:
                self.phase.setText(str(event))
            return
        if not self.stopping:
            self.phase.setText(data["stage"])
        total, done = data["step_total"], data["step_done"]
        if total is None:
            self.bar.setRange(0, 0)
            self.detail.setText("Zjišťuji rozsah aktuálního kroku…")
        else:
            self.bar.setRange(0, 1000)
            self.bar.setValue(1000 if total == 0 else int(1000 * done / total))
            self.detail.setText(
                f"Dokončeno {done:,} z {total:,} {data['unit']}; zbývá {total - done:,}."
            )
        self.search.setText(
            (
                f"Prohledaných stavů v aktuální skupině kandidátů: {data['search_states']:,}. "
                if data.get("search_states") is not None
                else ""
            )
            + f"Skupin kandidátů s dosaženým limitem: {data.get('limits', 0)}."
        )
        for key in self.values:
            self.values[key].setText(
                "—"
                if key in ("total", "remaining") and not data["inputs_loaded"]
                else str(data[key])
            )
        self.currencies.setText(
            "     |     ".join(
                f"{cur}: spárováno {v['resolved']}, zbývá {v['remaining']}"
                for cur, v in data["currencies"].items()
            )
        )
        if not data["inputs_loaded"]:
            self.currencies.setText("CZK: zjišťuji počet     |     EUR: zjišťuji počet")
        stage = (data["round"], data["stage"])
        if stage != self.last_stage:
            self.history.appendPlainText(f"Kolo {data['round']} · {data['stage']}")
            self.last_stage = stage

    def request_cancel(self):
        if self.stopping or self.finished:
            return
        self.stopping = True
        self.stop.setEnabled(False)
        self.phase.setText(
            "Ruším běh — čekám na bezpečné dokončení rozpracovaného kroku…"
        )
        self.cancel_callback()

    def reject(self):
        self.request_cancel()

    def closeEvent(self, event):
        if not self.finished:
            self.request_cancel()
            event.ignore()
        else:
            event.accept()

    def finish(self):
        self.finished = True
        self.timer.stop()
        self.close()
