"""Deliberately small allowlist: no URL/query, headers, payloads or personal paths."""

from pathlib import Path
from datetime import date, timedelta
import json
from kajovokarty.domain.core import now


class TechnicalLog:
    def __init__(self, folder, retention_days=30):
        self.folder = Path(folder)
        self.retention_days = retention_days

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
            )
            if k in event
        }
        safe["timestamp"] = now()
        self.folder.mkdir(parents=True, exist_ok=True)
        day = date.today()
        with (self.folder / (day.isoformat() + ".jsonl")).open(
            "a", encoding="utf-8"
        ) as f:
            f.write(json.dumps(safe, separators=(",", ":")) + "\n")
        cutoff = day - timedelta(days=self.retention_days)
        for path in self.folder.glob("????-??-??.jsonl"):
            try:
                stamp = date.fromisoformat(path.stem)
            except ValueError:
                continue
            if stamp < cutoff:
                path.unlink()
