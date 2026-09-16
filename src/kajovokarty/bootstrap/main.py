from pathlib import Path
import sys, json, hashlib, sqlite3
from PySide6.QtCore import QStandardPaths, QLockFile, QTimer, QCoreApplication, QEvent, qInstallMessageHandler
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMessageBox
from kajovokarty.infrastructure.database import Database
from kajovokarty.domain.core import AppError, require


def main():
    if len(sys.argv) > 1 and sys.argv[1] == '--self-test-report':
        if len(sys.argv) != 3:
            return 2
        from kajovokarty.bootstrap.selftest import run
        return run(sys.argv[2])
    app = QApplication(sys.argv)
    app.setOrganizationName("Kajovo")
    app.setApplicationName("KajovoKarty")
    base = (
        Path(QStandardPaths.writableLocation(QStandardPaths.GenericDataLocation))
        / "KajovoKarty"
    )
    base.mkdir(parents=True, exist_ok=True)
    from kajovokarty.infrastructure.technical_log import configure
    log = configure(base / "logs")
    log.event("APPLICATION_START")
    def unhandled(kind, value, tb):
        log.exception("UNHANDLED_EXCEPTION", value)
        from kajovokarty.domain.errors import user_text
        QMessageBox.warning(None, "Operaci se nepodařilo dokončit", user_text("INTERNAL_ERROR"))
    sys.excepthook = unhandled
    qInstallMessageHandler(lambda kind, context, message: log.event("QT_MESSAGE", kind=str(kind)))
    while True:
        result = run_workspace(app, base)
        if result != 23:
            return result


def run_workspace(app, base):
    from kajovokarty.ui.recovery import recovery_dialog
    from kajovokarty.application.reset import ResetService, RESET_EXIT
    from kajovokarty.domain.errors import user_text

    pointer = base / "workspace.json"
    data = base / "data"
    try:
        if pointer.exists():
            data = Path(
                json.loads(pointer.read_text(encoding="utf-8"))["data_directory"]
            )
            require(
                data.is_dir() and ((data / "kajovokarty.sqlite").is_file()
                                   or (data / ".reset.json").is_file()),
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
            e.user_message
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
        if (data / ".reset.json").exists():
            try:
                reset = ResetService(data, base)
            except (AppError, OSError):
                QMessageBox.warning(None, "Reset není dokončen", user_text("RESET_FAILED"))
                return 1
            answer = QMessageBox.warning(
                None, "Dokončení resetu",
                "Předchozí reset nebyl dokončen. Před otevřením programu je potřeba "
                "dokončit potvrzené vymazání dat a záloh. Pokračovat?",
                QMessageBox.Yes | QMessageBox.Close, QMessageBox.Close,
            )
            if answer != QMessageBox.Yes:
                return 1
            if not finish_reset(reset):
                return 1
        try:
            db = Database(data / "kajovokarty.sqlite")
            db.recover()
        except (AppError, sqlite3.DatabaseError, OSError) as e:
            from kajovokarty.infrastructure.technical_log import TechnicalLog
            TechnicalLog(base / "logs").exception("DATABASE_START_FAILED", e)
            message = (
                e.user_message
                if isinstance(e, AppError)
                else user_text("DATABASE_ACCESS_DENIED")
                if isinstance(e, PermissionError) or getattr(e, "sqlite_errorcode", None) == sqlite3.SQLITE_CANTOPEN
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

            if getattr(window, "shutting_down", False):
                return
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
                window.backup.prune_daily(folder, limit, target)
                return result

            window.run(execute, mutating=False)

        daily_timer = QTimer(window)
        daily_timer.setSingleShot(True)
        daily_timer.timeout.connect(daily)
        daily_timer.start(500)
        result = app.exec()
        window.stop_background_activity()
        server.newConnection.disconnect(activate)
        window.pool.waitForDone()
        backup_directory = window.settings.get()["data.backup_directory"] if result == RESET_EXIT else None
        window.hide()
        window.deleteLater()
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        if result == RESET_EXIT:
            try:
                reset = ResetService(data, base)
                with db.gate:
                    reset.prepare(backup_directory)
            except (AppError, OSError, sqlite3.Error) as error:
                db.log.exception("RESET_PREPARATION_FAILED", error)
                QMessageBox.warning(None, "Reset nezačal", user_text("RESET_PREPARE_FAILED"))
                return 1
            return 23 if finish_reset(reset) else 1
        return result
    finally:
        server.close()
        lock.unlock()


def finish_reset(reset):
    """A failed deletion never opens normal UI or reports success."""
    from kajovokarty.domain.errors import user_text
    while True:
        try:
            reset.finish()
            return True
        except AppError:
            answer = QMessageBox.warning(
                None, "Reset není dokončen", user_text("RESET_FAILED"),
                QMessageBox.Retry | QMessageBox.Close, QMessageBox.Close,
            )
            if answer != QMessageBox.Retry:
                return False
