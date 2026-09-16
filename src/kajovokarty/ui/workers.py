from PySide6.QtCore import QObject, QRunnable, Signal
from kajovokarty.domain.core import AppError


class Signals(QObject):
    result = Signal(object)
    error = Signal(object)
    progress = Signal(object)
    finished = Signal()


class Job(QRunnable):
    def __init__(self, fn, log=None):
        super().__init__()
        self.fn = fn
        self.log = log
        self.signals = Signals()

    def run(self):
        if self.log:
            self.log.event("WORKER_BEGIN")
        try:
            self.signals.result.emit(self.fn(self.signals.progress.emit))
        except AppError as e:
            if self.log:
                self.log.exception("WORKER_FAILED", e)
            self.signals.error.emit(e)
        except Exception as e:
            if self.log:
                self.log.exception("WORKER_FAILED", e)
            # The GUI shows a safe error; exception text can contain source data.
            err = AppError(
                "INTERNAL_ERROR",
                "Operaci se nepodařilo dokončit. Výsledek dokončených kroků ověřte v historii.",
                {"exception_type": type(e).__name__},
            )
            self.signals.error.emit(err)
        finally:
            if self.log:
                self.log.event("WORKER_FINISHED")
            self.signals.finished.emit()
