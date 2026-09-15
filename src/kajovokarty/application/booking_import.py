"""Commit Booking files independently, in the order selected by the user."""

from pathlib import Path
import json
from kajovokarty.application.import_messages import file_report, reason
from kajovokarty.application.imports import ImportService
from kajovokarty.domain.core import AppError, canonical, require


class BookingImportService:
    def __init__(self, db):
        self.db = db
        self.importer = ImportService(db)

    def run(self, inputs, max_megabytes=100, cancel=None, progress=None):
        require(inputs and all(r.kind == "BOOKING" for r in inputs), "FORMAT_INVALID", "Vyberte CSV soubory plateb z Bookingu.")
        reports = []
        for index, request in enumerate(inputs, 1):
            if cancel and cancel.is_set():
                reports.append(file_report(request, None, "NOT_STARTED"))
                continue
            name = Path(request.original_name or request.path or "Uložený soubor").name
            if progress:
                progress(f"Načítám soubor {index} z {len(inputs)}: {name}. Dosud přibylo {sum(r['added'] for r in reports)} plateb.")
            preview = None
            try:
                preview = self.importer.preflight([request], max_megabytes, cancel, progress)
                if not preview.valid:
                    report = file_report(request, preview, "CANCELLED" if cancel and cancel.is_set() else "FAILED")
                    self.importer.discard(preview.id)
                else:
                    outcome = self.importer.commit(preview.id, cancel=cancel)
                    report = file_report(request, preview, "COMPLETED", outcome)
            except AppError as error:
                if preview:
                    self.importer.discard(preview.id)
                report = file_report(request, preview, "CANCELLED" if error.code == "CANCELLED" else "FAILED")
                report["errors"] = [reason(error.as_dict())]
            reports.append(report)
            if preview:
                # Store the same readable report for later inspection in Importy.
                with self.db.transaction() as c:
                    counts = json.loads(c.execute("SELECT row_counts_json FROM import_run WHERE id=?", (preview.id,)).fetchone()[0])
                    counts["booking_result"] = report
                    c.execute("UPDATE import_run SET row_counts_json=? WHERE id=?", (canonical(counts), preview.id))
        return reports
