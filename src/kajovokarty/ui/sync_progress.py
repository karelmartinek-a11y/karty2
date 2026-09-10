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
        self.calls = self.items = self.expected = 0
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
        self.total = QLabel("API záznamy: 0 | odhad celkem: zjišťuji")
        self.total.setFixedHeight(26)
        layout.addWidget(self.total)
        self.elapsed = QLabel("Doba behu: 0:00")
        self.elapsed.setFixedHeight(26)
        layout.addWidget(self.elapsed)
        self.eta = QLabel("Odhad dokončení: zjišťuji rozsah...")
        self.eta.setFixedHeight(26)
        layout.addWidget(self.eta)
        self.stop = QPushButton("Zrusit nacitani")
        self.stop.clicked.connect(self.request_cancel)
        layout.addWidget(self.stop)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(1000)

    def update_progress(self, event):
        message = str(event)
        if message.startswith("API") and "GET " in message:
            self.calls += 1
            self.phase.setText("Načítám data z BetterHotelu")
        elif message.startswith("API"):
            self.phase.setText("Zpracovávám přijatá data")
        elif message.startswith("Načítám stránku"):
            self.phase.setText("Načítám další část dat")
        elif message.startswith("Zpracováno"):
            self.phase.setText("Zpracovávám data")
        elif message.startswith("Dokončeno"):
            self.phase.setText("Dokončuji datový blok")
        elif not message.startswith("API rozsah") and not self.stopping:
            self.phase.setText(message)
        match = re.search(r"HTTP \d+: (\d+) ", message)
        if match:
            self.items += int(match.group(1))
        scope = re.search(r"API rozsah .*?: (\d+) záznamů", message)
        if scope:
            self.expected += int(scope.group(1))
        total = max(self.items, self.expected)
        if total:
            self.bar.setRange(0, 1000)
            self.bar.setValue(min(1000, int(1000 * self.items / total)))
        else:
            self.bar.setRange(0, 0)
        self.total.setText(
            f"Zpracováno {self.items} z {total if total else 'zjišťuji'} datových záznamů "
            f"| API volání: {self.calls}"
        )
        self.detail.setText(
            "Celkový počet se průběžně upřesňuje."
            if not total
            else f"Zbývá přibližně {max(0, total - self.items)} datových záznamů."
        )
        elapsed = max(time.monotonic() - self.started, 0.001)
        if total and self.items and self.items < total:
            remaining = total - self.items
            seconds = int(remaining * elapsed / self.items)
            finish = time.localtime(time.time() + seconds)
            self.eta.setText(
                f"Odhad dokončení: za {seconds // 60}:{seconds % 60:02d} "
                f"(přibližně {time.strftime('%H:%M', finish)})"
            )
        elif total and self.items >= total:
            self.eta.setText("Odhad dokončení: dokončování detailů a ukládání...")
        else:
            self.eta.setText("Odhad dokončení: zjišťuji rozsah API...")
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
