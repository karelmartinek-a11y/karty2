"""Synthetic local load probe. It is not the Windows reference acceptance test."""

from pathlib import Path
import csv, json, tempfile, time, platform
from kajovokarty.domain.core import uid, now
from kajovokarty.infrastructure.database import Database
from kajovokarty.application.imports import ImportService, ImportInput
from kajovokarty.application.work import WorkService
from kajovokarty.infrastructure.parsers import BOOK_HEADERS


def peak_rss():
    if platform.system() == "Windows":
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
                (name, ctypes.c_size_t)
                for name in (
                    "PeakWorkingSetSize",
                    "WorkingSetSize",
                    "QuotaPeakPagedPoolUsage",
                    "QuotaPagedPoolUsage",
                    "QuotaPeakNonPagedPoolUsage",
                    "QuotaNonPagedPoolUsage",
                    "PagefileUsage",
                    "PeakPagefileUsage",
                )
            ]

        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        ctypes.windll.psapi.GetProcessMemoryInfo(
            ctypes.windll.kernel32.GetCurrentProcess(),
            ctypes.byref(counters),
            counters.cb,
        )
        return counters.PeakWorkingSetSize // 1024
    import resource

    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss


def main():
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "booking.csv"
        with path.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(BOOK_HEADERS)
            for i in range(100000):
                w.writerow(
                    [
                        "Reservation",
                        str(1000000000 + i),
                        "2026-08-01",
                        "2026-08-02",
                        "Synthetic test",
                        "Booking.com",
                        "ok",
                        "EUR",
                        "Paid Online",
                        "50.00" if i % 2 == 0 else "-50.00",
                        "2026-08-27",
                        "LOAD-TEST",
                    ]
                )
        db = Database(Path(temp) / "db.sqlite")
        service = ImportService(db)
        start = time.perf_counter()
        preview = service.preflight([ImportInput("BOOKING", str(path))])
        result = service.commit(preview.id)
        import_seconds = time.perf_counter() - start
        work = WorkService(db)
        # Deterministic workload fixture: 19,999 pairs and one 1,000-leaf group.
        # Setup is one transaction; measurements below use production services.
        with db.transaction() as c:
            ids = [
                r[0]
                for r in c.execute(
                    "SELECT id FROM financial_source ORDER BY json_extract(canonical_json,'$.booking_reference')"
                )
            ]
            allgroups = []
            for index in range(20000):
                members = (
                    ids[index * 2 : index * 2 + 2]
                    if index < 19999
                    else ids[39998:40998]
                )
                gid, cmd = uid(), uid()
                allgroups.append(gid)
                c.execute(
                    "INSERT INTO command VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        cmd,
                        "CREATE_GROUP",
                        "MANUAL",
                        "{}",
                        "{}",
                        "{}",
                        "{}",
                        "{}",
                        "{}",
                        None,
                        "APPLIED",
                        now(),
                        index + 1,
                        1,
                    ),
                )
                c.execute(
                    "INSERT INTO work_object VALUES(?,'GROUP',NULL,'EUR','ACTIVE',1)",
                    (gid,),
                )
                c.execute(
                    "INSERT INTO reconciliation_group VALUES(?,'MANUAL','Synthetic benchmark',?,?, '{}')",
                    (gid, now(), now()),
                )
                c.executemany(
                    "INSERT INTO membership VALUES(?,?,?,1,?,NULL,?,NULL)",
                    [(uid(), gid, i, cmd, now()) for i in members],
                )
            large_group = allgroups[-1]
        query_samples = []
        selection_samples = []
        for index in range(20):
            start = time.perf_counter()
            q = work.query({"text": "Synthetic", "currency": ["EUR"]})
            query_samples.append(time.perf_counter() - start)
            start = time.perf_counter()
            work.select([q["rows"][index]["id"]])
            selection_samples.append(time.perf_counter() - start)
        start = time.perf_counter()
        evidence = work.evidence(large_group)
        detail_seconds = time.perf_counter() - start
        assert len(evidence["leaves"]) == 1000
        start = time.perf_counter()
        q = work.query()
        query_seconds = time.perf_counter() - start
        start = time.perf_counter()
        work.select([q["rows"][0]["id"]])
        selection_seconds = time.perf_counter() - start
        metrics = {
            "environment": platform.platform()
            + " CPython "
            + platform.python_version(),
            "financial_leaves": 100000,
            "groups": 20000,
            "query_samples_seconds": query_samples,
            "selection_samples_seconds": selection_samples,
            "filtered_first_page_p95_seconds": sorted(query_samples)[18],
            "selection_p95_seconds": sorted(selection_samples)[18],
            "group_1000_leaves_seconds": detail_seconds,
            "import_seconds": import_seconds,
            "first_page_seconds": query_seconds,
            "single_selection_seconds": selection_seconds,
            "peak_rss_kib": peak_rss(),
            "inserted": result["new"],
            "limitations": "Local environment; p95 over 20 samples. Windows reference hardware must be measured separately.",
        }
        (Path(__file__).parents[1] / "docs/load-probe.json").write_text(
            json.dumps(metrics, indent=2)
        )
        print(json.dumps(metrics))


if __name__ == "__main__":
    main()
