"""Live progress dialog for BetterHotel synchronization."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QProgressBar, QPlainTextEdit, QPushButton


class SyncProgressDialog(QDialog):
    def __init__(self, parent, cancel):
        super().__init__(parent)
        self.setObjectName("betterHotelSyncProgress")
        self.setWindowTitle("Načítání BetterHotelu — průběh")
        self.resize(650, 360)
        self.setModal(False)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.cancel_callback = cancel
        self.stopping = False
        self.finished = False

        layout = QVBoxLayout(self)
        self.phase = QLabel("Připravuji načítání…")
        self.phase.setWordWrap(True)
        layout.addWidget(self.phase)
        self.bar = QProgressBar()
        self.bar.setRange(0, 0)
        layout.addWidget(self.bar)
        self.detail = QLabel("Čekám na první odpověď BetterHotelu…")
        self.detail.setWordWrap(True)
        layout.addWidget(self.detail)
        self.history = QPlainTextEdit()
        self.history.setReadOnly(True)
        self.history.setMaximumBlockCount(200)
        layout.addWidget(self.history)
        self.stop = QPushButton("Zrušit načítání")
        self.stop.clicked.connect(self.request_cancel)
        layout.addWidget(self.stop)

    def update_progress(self, event):
        message = str(event)
        if not self.stopping:
            self.phase.setText(message)
        self.detail.setText("Probíhá komunikace s BetterHotelem…")
        if not self.history.toPlainText() or self.history.toPlainText().splitlines()[-1] != message:
            self.history.appendPlainText(message)

    def request_cancel(self):
        if self.stopping or self.finished:
            return
        self.stopping = True
        self.stop.setEnabled(False)
        self.phase.setText("Ruším načítání — čekám na bezpečné dokončení kroku…")
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
        self.close()
