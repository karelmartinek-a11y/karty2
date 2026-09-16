"""Shared sequential imports: one atomic financial transaction per file."""
from pathlib import Path
import json
import time
from kajovokarty.application.imports import ImportService
from kajovokarty.application.import_messages import reason, counter_text
from kajovokarty.domain.core import AppError, canonical, uid
from kajovokarty.domain.import_progress import ImportProgress


def report_for(request, preview, state, outcome=None):
    parsed = preview.files[0].parsed if preview and preview.files else None
    counters = dict(parsed.counters) if parsed else {}
    diagnostics = list(preview.diagnostics) if preview else []
    diagnostics.extend({'severity': 'WARNING', 'code': code}
                       for code in (outcome or {}).get('warnings', []))
    accounts = request.kind == "ACCOUNTS"
    if accounts:
        counters = dict((outcome or {}).get("accounts") or counters)
        keys = ("new", "known", "conflicts", "incomplete")
        total = sum(counters.get(k, 0) for k in keys) if parsed else None
        skipped = {k: counters[k] for k in ("conflicts", "incomplete") if counters.get(k)}
    else:
        total = sum(counters.values()) if parsed else None
        skipped = {k: v for k, v in counters.items() if k not in ("NEW", "KNOWN", "ERROR") and v}
    added = (outcome or {}).get("new", 0)
    known = (outcome or {}).get("known", 0) if state == "COMPLETED" else (preview.existing_known if preview else 0)
    error_rows = len({(d.get("file_id"), d["row_start"]) for d in diagnostics
                      if d.get("severity") == "ERROR" and d.get("row_start") is not None})
    not_saved = None if total is None else max(0, total - added - known - sum(skipped.values()))
    return dict(kind=request.kind, name=Path(request.original_name or request.path or
                (preview.files[0].name if preview and preview.files else "Uložený soubor")).name,
                operation_id=preview.id if preview else None, state=state, added=added,
                already_saved=known, total=total, skipped=skipped, error_rows=error_rows,
                not_saved=not_saved, errors=[reason(d) for d in diagnostics if d.get("severity") == "ERROR"],
                warnings=[reason(d) for d in diagnostics if d.get("severity") == "WARNING"])


def file_text(report):
    state = {"COMPLETED": "Dokončeno", "FAILED": "Chyba – soubor nebyl uložen",
             "CANCELLED": "Zastaveno – soubor nebyl uložen", "NOT_STARTED": "Nezahájeno"}[report["state"]]
    unit = "vazby" if report["kind"] == "ACCOUNTS" else "platby"
    lines = [report["name"] + " — " + state,
             f"Nově uložené {unit}: {report['added']}. Již uložené: {report['already_saved']}.",
             f"Chybné řádky: {report['error_rows']}. Neuložené kvůli chybě nebo zastavení: " +
             (str(report['not_saved']) if report['not_saved'] is not None else "počet nezjištěn") + "."]
    if report["skipped"]:
        lines.append("Vynecháno: " + counter_text(report["skipped"]))
    if report["errors"]:
        lines.extend(["Chyby:", *report["errors"]])
    if report["warnings"]:
        lines.extend(["Upozornění:", *report["warnings"]])
    return "\n".join(lines)


def batch_text(reports):
    counts = {s: sum(r["state"] == s for r in reports) for s in ("COMPLETED", "FAILED", "CANCELLED", "NOT_STARTED")}
    lines = [f"Soubory dokončené: {counts['COMPLETED']} z {len(reports)}. S chybou: {counts['FAILED']}. "
             f"Zastavené: {counts['CANCELLED']}. Nezahájené: {counts['NOT_STARTED']}."]
    for accounts, label in ((False, "Platby"), (True, "Vazby Účtů")):
        items = [r for r in reports if (r["kind"] == "ACCOUNTS") == accounts]
        if items:
            lines.append(f"{label} – nově uloženo: {sum(r['added'] for r in items)}; již uložené: {sum(r['already_saved'] for r in items)}.")
    lines.append(f"Vynechané řádky: {sum(sum(r['skipped'].values()) for r in reports)}. Chybné řádky: {sum(r['error_rows'] for r in reports)}.")
    lines.append("Neuložené kvůli odmítnutí nebo zastavení: " + str(sum(r['not_saved'] or 0 for r in reports)) +
                 ("; u některých souborů počet nezjištěn." if any(r['not_saved'] is None for r in reports) else "."))
    return "\n".join(lines) + "\n\n" + "\n\n".join(file_text(r) for r in reports)


class ImportBatchService:
    def __init__(self, db):
        self.db = db
        self.importer = ImportService(db)

    def run(self, inputs, max_megabytes=100, cancel=None, progress=None, choose_sheet=None):
        reports = self.reports = []
        batch_id = uid()
        last_emit, last_stage = 0.0, None
        for index, original in enumerate(inputs, 1):
            request = original
            preview = None
            name = Path(request.original_name or request.path or "Uložený soubor").name

            def emit(event):
                nonlocal last_emit, last_stage
                data = dict(getattr(event, "snapshot", dict(stage=str(event), current=0, total=None)))
                stage = (index, data["stage"])
                now = time.monotonic()
                terminal = data["total"] is not None and data["current"] == data["total"]
                if stage != last_stage or terminal or now - last_emit >= 0.1:
                    if stage != last_stage or terminal:
                        self.db.log.event("IMPORT_PROGRESS", operation_id=preview.id if preview else None,
                                          state=data["stage"], counts={"file": index, "files": len(inputs),
                                          "processed": data["current"], "total": data["total"]})
                    last_emit, last_stage = now, stage
                    data.update(file_index=index, file_total=len(inputs), name=name,
                                added=sum(r["added"] for r in reports),
                                payments=sum(r["added"] for r in reports if r["kind"] != "ACCOUNTS"),
                                accounts=sum(r["added"] for r in reports if r["kind"] == "ACCOUNTS"))
                    if progress:
                        progress(ImportProgress(**data))

            if cancel and cancel.is_set():
                reports.append(report_for(request, None, "NOT_STARTED"))
                continue
            emit(ImportProgress("Načítání"))
            try:
                preview = self.importer.preflight([request], max_megabytes, cancel, emit, choose_sheet)
                cancelled = any(d["code"] == "CANCELLED" for d in preview.diagnostics)
                if cancelled:
                    if cancel:
                        cancel.set()
                    raise AppError("CANCELLED", "Import byl zastaven.")
                if cancel and cancel.is_set():
                    raise AppError("CANCELLED", "Import byl zastaven.")
                if not preview.valid:
                    report = report_for(request, preview, "FAILED")
                    self.importer.discard(preview.id)
                else:
                    outcome = self.importer.commit(preview.id, cancel=cancel, progress=emit)
                    report = report_for(request, preview, "COMPLETED", outcome)
            except Exception as error:
                if preview:
                    self.importer.discard(preview.id)
                self.db.log.exception("IMPORT_BATCH_FILE_FAILED", error, operation_id=preview.id if preview else None)
                report = report_for(request, preview, "CANCELLED" if getattr(error, "code", None) == "CANCELLED" else "FAILED")
                if not report["operation_id"]:
                    report["operation_id"] = getattr(error, "operation_id", None)
                report["errors"].append(reason({"code": getattr(error, "code", "INTERNAL_ERROR")}))
            reports.append(report)
            emit(ImportProgress("Soubor dokončen", 1, 1))
            self.db.log.event("IMPORT_FILE_RESULT", operation_id=report["operation_id"], kind=request.kind,
                              state=report["state"], counts={k: report[k] for k in ("added", "already_saved", "error_rows", "not_saved")})
            if report["operation_id"]:
                try:
                    with self.db.transaction() as c:
                        row = c.execute("SELECT row_counts_json FROM import_run WHERE id=?", (report["operation_id"],)).fetchone()
                        counts = json.loads(row[0])
                        counts.update(import_result=report, batch_id=batch_id)
                        c.execute("UPDATE import_run SET row_counts_json=? WHERE id=?", (canonical(counts), report["operation_id"]))
                except Exception as error:
                    self.db.log.exception("IMPORT_REPORT_FAILED", error, operation_id=report["operation_id"])
                    report["warnings"].append(reason({"code": "IMPORT_REPORT_FAILED"}))
        text = batch_text(reports)
        for report in reports:
            if not report["operation_id"]:
                continue
            try:
                with self.db.transaction() as c:
                    row = c.execute("SELECT row_counts_json FROM import_run WHERE id=?", (report["operation_id"],)).fetchone()
                    counts = json.loads(row[0])
                    counts.update(batch_summary=text)
                    c.execute("UPDATE import_run SET row_counts_json=? WHERE id=?", (canonical(counts), report["operation_id"]))
            except Exception as error:
                self.db.log.exception("IMPORT_REPORT_FAILED", error, operation_id=report["operation_id"])
                report["warnings"].append(reason({"code": "IMPORT_REPORT_FAILED"}))
        self.db.log.event("IMPORT_BATCH_RESULT", counts={"files": len(reports), "new": sum(r["added"] for r in reports),
            "known": sum(r["already_saved"] for r in reports), "failed": sum(r["state"] == "FAILED" for r in reports),
            "skipped": sum(sum(r["skipped"].values()) for r in reports),
            "error_rows": sum(r["error_rows"] for r in reports),
            "not_saved": sum(r["not_saved"] or 0 for r in reports),
            "unknown_files": sum(r["total"] is None for r in reports)})
        return reports
