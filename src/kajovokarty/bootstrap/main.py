from pathlib import Path
import sys, json, hashlib, sqlite3
from PySide6.QtCore import QStandardPaths, QLockFile, QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMessageBox
from kajovokarty.infrastructure.database import Database
from kajovokarty.domain.core import AppError, require


def main():
    app = QApplication(sys.argv)
    app.setOrganizationName("Kajovo")
    app.setApplicationName("KajovoKarty")
    base = (
        Path(QStandardPaths.writableLocation(QStandardPaths.GenericDataLocation))
        / "KajovoKarty"
    )
    base.mkdir(parents=True, exist_ok=True)
    while True:
        result = run_workspace(app, base)
        if result != 23:
            return result


def run_workspace(app, base):
    from kajovokarty.ui.recovery import recovery_dialog

    pointer = base / "workspace.json"
    data = base / "data"
    try:
        if pointer.exists():
            data = Path(json.loads(pointer.read_text())["data_directory"])
            require(
                data.is_dir() and (data / "kajovokarty.sqlite").is_file(),
                "DIRECTORY_UNAVAILABLE",
                "Nakonfigurovaná datová složka není dostupná.",
            )
        require(
            not (data / ".moving").exists(),
            "DIRECTORY_BUSY",
            "Datový prostor se právě přesouvá.",
        )
    except (ValueError, KeyError, OSError, AppError) as e:
        message = (
            e.message
            if isinstance(e, AppError)
            else "Nelze načíst cestu k pracovnímu prostoru."
        )
        return 23 if recovery_dialog(None, data, pointer, message) else 1
    data.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(data / "application.lock"))
    lock.setStaleLockTime(0)
    name = (
        "KajovoKarty-" + hashlib.sha256(str(data.resolve()).encode()).hexdigest()[:24]
    )
    if not lock.tryLock(0):
        socket = QLocalSocket()
        socket.connectToServer(name)
        if socket.waitForConnected(1000):
            socket.write(b"activate")
            socket.flush()
            socket.waitForBytesWritten(500)
        else:
            QMessageBox.warning(
                None, "KájovoKarty", "Pracovní prostor je otevřen v jiné instanci."
            )
        return 0
    server = QLocalServer()
    QLocalServer.removeServer(name)
    server.listen(name)
    try:
        try:
            db = Database(data / "kajovokarty.sqlite")
            db.recover()
        except (AppError, sqlite3.DatabaseError, OSError) as e:
            message = (
                e.message
                if isinstance(e, AppError)
                else "Databázi nelze bezpečně otevřít."
            )
            return 23 if recovery_dialog(None, data, pointer, message) else 1
        db.workspace_pointer = pointer
        documents = Path(
            QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
        )
        db.default_directories = {
            "data.backup_directory": str(base / "backups"),
            "data.export_directory": str(documents / "KajovoKarty"),
            **{
                "imports.last_directory." + kind: str(documents)
                for kind in ("CASHBOOK_CARD", "BANK_CARD", "BOOKING")
            },
        }
        from kajovokarty.ui.main import MainWindow

        window = MainWindow(db)

        def activate():
            conn = server.nextPendingConnection()
            if conn:
                conn.disconnectFromServer()
                conn.deleteLater()
            window.showNormal()
            window.raise_()
            window.activateWindow()

        server.newConnection.connect(activate)
        window.show()

        def daily():
            from datetime import date, timedelta

            settings = window.settings.get()
            if not settings["backup.daily"]:
                return

            def execute(progress):
                folder = Path(settings["data.backup_directory"])
                folder.mkdir(parents=True, exist_ok=True)
                target = folder / ("auto-" + date.today().isoformat() + ".zip")
                if target.exists():
                    return str(target)
                result = window.backup.backup(target)
                limit = date.today() - timedelta(days=settings["backup.retention_days"])
                for p in folder.glob("auto-????-??-??.zip"):
                    try:
                        old = date.fromisoformat(p.stem[5:])
                    except ValueError:
                        continue
                    if old < limit and p != target:
                        p.unlink()
                return result

            window.run(execute, mutating=False)

        QTimer.singleShot(500, daily)
        result = app.exec()
        window.pool.waitForDone()
        window.hide()
        window.deleteLater()
        app.processEvents()
        return result
    finally:
        server.close()
        lock.unlock()
