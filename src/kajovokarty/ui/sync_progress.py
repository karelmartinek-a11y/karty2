"""Static, detailed progress dialog for BetterHotel synchronization."""
import re
import time
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QProgressBar, QPushButton

class SyncProgressDialog(QDialog):
    def __init__(self, parent, cancel):
        super().__init__(parent)
        self.setObjectName("betterHotelSyncProgress")
        self.setWindowTitle("Nactani BetterHotelu - prubeh")
        self.resize(650, 300)
        self.setModal(False)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.cancel_callback = cancel
        self.stopping = self.finished = False
        self.calls = self.items = 0
        self.started = time.monotonic()
        layout = QVBoxLayout(self)
        self.phase = QLabel("Pripravuji nacitani...")
        self.phase.setWordWrap(True)
        self.phase.setFixedHeight(44)
        layout.addWidget(self.phase)
        self.bar = QProgressBar()
        self.bar.setRange(0, 0)
        self.bar.setFixedHeight(22)
        layout.addWidget(self.bar)
        self.detail = QLabel("Cekam na prvni odpoved BetterHotelu...")
        self.detail.setWordWrap(True)
        self.detail.setFixedHeight(44)
        layout.addWidget(self.detail)
        self.total = QLabel("Celkem API volani: 0 | nactenych polozek: 0")
        self.total.setFixedHeight(26)
        layout.addWidget(self.total)
        self.elapsed = QLabel("Doba behu: 0:00")
        self.elapsed.setFixedHeight(26)
        layout.addWidget(self.elapsed)
        self.stop = QPushButton("Zrusit nacitani")
        self.stop.clicked.connect(self.request_cancel)
        layout.addWidget(self.stop)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(1000)

    def update_progress(self, event):
        message = str(event)
        if not self.stopping:
            self.phase.setText(message)
        self.detail.setText("Posledni udalost: " + message)
        if message.startswith("API") and "GET " in message:
            self.calls += 1
        match = re.search(r"HTTP \d+: (\d+) ", message)
        if match:
            self.items += int(match.group(1))
        self.total.setText(f"Celkem API volani: {self.calls} | nactenych polozek: {self.items}")
        self.tick()

    def tick(self):
        seconds = int(time.monotonic() - self.started)
        self.elapsed.setText(f"Doba behu: {seconds // 60}:{seconds % 60:02d}")

    def request_cancel(self):
        if self.stopping or self.finished:
            return
        self.stopping = True
        self.stop.setEnabled(False)
        self.phase.setText("Rusi se nacitani - cekam na bezpecne dokonceni kroku...")
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
