from PySide6.QtCore import QObject, QRunnable, Signal
from kajovokarty.domain.core import AppError


class Signals(QObject):
    result = Signal(object)
    error = Signal(object)
    progress = Signal(str)
    finished = Signal()


class Job(QRunnable):
    def __init__(self, fn):
        super().__init__()
        self.fn = fn
        self.signals = Signals()

    def run(self):
        try:
            self.signals.result.emit(self.fn(self.signals.progress.emit))
        except AppError as e:
            self.signals.error.emit(e)
        except Exception as e:
            # The GUI shows a safe error; exception text can contain source data.
            err = AppError(
                "INTERNAL_ERROR",
                "Operaci se nepodařilo dokončit. Databázová transakce byla vrácena.",
                {"exception_type": type(e).__name__},
            )
            self.signals.error.emit(err)
        finally:
            self.signals.finished.emit()
