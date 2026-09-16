"""Deliberately small allowlist: no URL/query, headers, payloads or personal paths."""

from pathlib import Path
from datetime import date, timedelta
import json
import logging
import threading
import traceback
import sys
from kajovokarty.domain.core import now


class TechnicalLog:
    _lock = threading.RLock()

    def __init__(self, folder, retention_days=30):
        self.folder = Path(folder)
        self.retention_days = retention_days
        self.last_cleanup = None
        self.failure = None

    def event(self, event, **fields):
        self.write({"event": event, "level": "DEBUG", **fields})

    def exception(self, event, error, **fields):
        # No exception text or frame locals: both can contain source data/tokens.
        stack = [{"file": Path(f.filename).name, "line": f.lineno, "function": f.name}
                 for f in traceback.extract_tb(error.__traceback__)]
        self.write({"event": event, "level": "ERROR", "exception_type": type(error).__name__,
                    "sqlite_error_name": getattr(error, "sqlite_errorname", None),
                    "os_error_number": getattr(error, "winerror", None) or getattr(error, "errno", None),
                    "error_code": getattr(error, "code", "INTERNAL_ERROR"), "stack": stack, **fields})

    def write(self, event):
        safe = {
            k: event[k]
            for k in (
                "endpoint_template",
                "http_status",
                "elapsed_ms",
                "correlation_id",
                "error_code",
                "diagnostic_id",
                "resource_type",
                "changed_fields",
                "event", "level", "operation_id", "file_id", "source_id", "row_start",
                "rule_id", "stage", "state", "disposition", "count", "counts", "source_ids",
                "transaction_id", "exception_type", "stack", "module", "thread", "kind",
                "sqlite_error_name", "os_error_number",
            )
            if k in event
        }
        safe["timestamp"] = now()
        safe.setdefault("level", "DEBUG")
        safe["thread"] = threading.current_thread().name
        try:
            with self._lock:
                self.folder.mkdir(parents=True, exist_ok=True)
                day = date.today()
                with (self.folder / (day.isoformat() + ".jsonl")).open("a", encoding="utf-8") as f:
                    f.write(json.dumps(safe, separators=(",", ":")) + "\n")
                if self.last_cleanup != day:
                    cutoff = day - timedelta(days=self.retention_days)
                    for path in self.folder.glob("????-??-??.jsonl"):
                        try:
                            stamp = date.fromisoformat(path.stem)
                        except ValueError:
                            continue
                        if stamp < cutoff:
                            path.unlink()
                    self.last_cleanup = day
                self.failure = None
        except OSError as error:
            # A diagnostic write must never turn a committed payment into a reported rollback.
            first_failure = self.failure is None
            self.failure = type(error).__name__
            if first_failure and sys.stderr:
                sys.stderr.write("KájovoKarty: podrobný provozní záznam nelze uložit.\n")


class SafeHandler(logging.Handler):
    def __init__(self, log):
        super().__init__(logging.DEBUG)
        self.log = log

    def emit(self, record):
        fields = {"module": record.name, "level": record.levelname}
        # Only explicitly structured fields, never arbitrary interpolated messages.
        fields.update(getattr(record, "safe_fields", {}))
        if record.exc_info:
            self.log.exception("UNHANDLED_EXCEPTION", record.exc_info[1], **fields)
        else:
            self.log.event(getattr(record, "event_code", "MODULE_EVENT"), **fields)


def configure(folder):
    log = TechnicalLog(folder)
    logger = logging.getLogger("kajovokarty")
    logger.setLevel(logging.DEBUG)
    for handler in list(logger.handlers):
        if isinstance(handler, SafeHandler):
            logger.removeHandler(handler)
            handler.close()
    logger.addHandler(SafeHandler(log))
    logger.propagate = False
    return log
