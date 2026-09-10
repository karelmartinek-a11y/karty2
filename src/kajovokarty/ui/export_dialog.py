from pathlib import Path
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QFormLayout,
    QComboBox,
    QLabel,
    QDialogButtonBox,
    QFileDialog,
    QInputDialog,
)
from kajovokarty.application.reports import REPORTS
from kajovokarty.infrastructure.export import export
from kajovokarty.domain.core import AppError


def export_dialog(window, report=None, ids=None):
    from kajovokarty.ui.main import REPORT_NAMES

    if report not in REPORTS:
        rows = window.selected_rows()
        report = rows[0].get("report_id") if len(rows) == 1 else None
        if report not in REPORTS:
            name, ok = QInputDialog.getItem(
                window,
                "Sestava",
                "Typ sestavy:",
                list(REPORT_NAMES),
                1 if window.scope == 1 else 0,
                False,
            )
            if not ok:
                return
            report = REPORT_NAMES[name]
    if report == "api_compatibility" and ids is None:

        def choose(rows):
            if not rows:
                window.show_error(
                    AppError(
                        "EXPORT_INVALID", "Dosud nebylo spuštěno ověření kompatibility."
                    )
                )
                return
            labels = [
                r["started_at"] + " · " + r["status"] + " · " + r["id"] for r in rows
            ]
            label, ok = QInputDialog.getItem(
                window, "Ověření BetterHotel", "Konkrétní běh:", labels, 0, False
            )
            if ok:
                export_dialog(window, report, [rows[labels.index(label)]["id"]])

        window.run(lambda p: window.catalog.rows("compatibility"), choose, False)
        return
    if report == "group_evidence" and ids is None:
        ids = window.selected_ids()
    d = QDialog(window)
    d.setWindowTitle("Export sestavy")
    layout = QVBoxLayout(d)
    form = QFormLayout()
    layout.addLayout(form)
    title = next(k for k, v in REPORT_NAMES.items() if v == report)
    layout.addWidget(QLabel(title))
    mode = QComboBox()
    mode.addItems(["Aktuální filtr", "Označené řádky", "Pracovní výběr (nevyřízené)"])
    if ids is not None:
        mode.setCurrentIndex(1)
        mode.setEnabled(False)
    form.addRow("Rozsah", mode)
    if report in ("unresolved", "resolved"):
        layout.addWidget(
            QLabel(
                "U označených pracovních objektů se stav určí z výběru.\nSmíšený výběr vytvoří dvě samostatné sestavy: Nevyřízené a Vyřízené.\nJejich názvy dostanou přípony _unresolved a _resolved."
            )
        )
    fmt = QComboBox()
    fmt.addItems(["CSV (ZIP)", "XLSX", "PDF"])
    form.addRow("Formát", fmt)
    info = QLabel(
        "Označené řádky a pracovní výběr se exportují i mimo aktuální filtr. Důkaz skupiny vždy zahrnuje všechny její listy."
    )
    info.setWordWrap(True)
    layout.addWidget(info)
    buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
    buttons.accepted.connect(d.accept)
    buttons.rejected.connect(d.reject)
    layout.addWidget(buttons)
    if not d.exec():
        return
    filters = window.filters()
    if report == "helpers":
        if window.helper_history:
            ctx, gen = window.helper_history
            filters["helper_graphs"] = [{"context_id": ctx, "generation_id": gen}]
            filters["include_history"] = True
        elif window.helper_inactive:
            filters["include_history"] = True
    if ids is None and mode.currentIndex() == 1:
        if report == "helpers":
            ids = [
                {
                    k: r[k]
                    for k in (
                        "context_id",
                        "generation_id",
                        "resource_type",
                        "external_id",
                    )
                }
                for r in window.selected_rows()
                if "resource_type" in r
            ]
        elif report == "import_errors":
            ids = list({r["run_id"] for r in window.selected_rows() if "run_id" in r})
        else:
            ids = window.selected_ids()
    if mode.currentIndex() == 2:
        report = "unresolved"
        ids = list(window.selection)
    if ids is not None and not ids:
        window.show_error(
            AppError("EXPORT_INVALID", "Nejsou označeny žádné řádky pro tento rozsah.")
        )
        return
    ext = {"CSV (ZIP)": "zip", "XLSX": "xlsx", "PDF": "pdf"}[fmt.currentText()]
    folder = Path(window.settings.get()["data.export_directory"])
    path, _ = QFileDialog.getSaveFileName(
        window,
        "Uložit sestavu",
        str(folder / (report + "." + ext)),
        "Sestava (*." + ext + ")",
    )
    if not path:
        return
    if not Path(path).suffix:
        path += "." + ext
    sort = list(window.sort_order)

    def execute(progress):
        plans = (
            window.reports.partition_work_selection(ids)
            if ids is not None and report in ("unresolved", "resolved")
            else {report: ids}
        )
        results = []
        for name, selected in plans.items():
            target = Path(path)
            if len(plans) > 1:
                target = target.with_name(target.stem + "_" + name + target.suffix)
            data = window.reports.build(name, selected, filters, sort)
            result = export(data, ext, target, cancel=window.cancel)
            results.append(result)
            try:
                with window.db.transaction() as c:
                    window.db.audit(
                        c,
                        "EXPORT_COMPLETED",
                        after={
                            "report_id": name,
                            "database_snapshot_id": next(
                                r["value_json"]
                                for r in data["metadata"]
                                if r["key"] == "database_snapshot_id"
                            ),
                        },
                    )
            except Exception:
                raise AppError(
                    "EXPORT_AUDIT_FAILED",
                    "Soubor byl vytvořen, ale audit exportu se nepodařilo uložit.",
                ) from None
        return results

    window.run(
        execute,
        lambda results: window.status.setText(
            "Uloženo: " + ", ".join(Path(r).name for r in results)
        ),
    )
