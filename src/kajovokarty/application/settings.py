import json
from contextlib import nullcontext
from pathlib import Path
from decimal import Decimal, InvalidOperation
from kajovokarty.domain.core import AppError, canonical, now, parse_date, require, uid

DEFAULTS = {
    "sync.start_date": "",
    "sync.block_days": 7,
    "sync.timeout_seconds": 30,
    "sync.retry_count": 3,
    "sync.requests_per_second": "2.0",
    "matching.bank_window_days": 7,
    "matching.max_combination": 6,
    "matching.max_component_items": 40,
    "matching.max_search_states": 100000,
    "matching.warning_age_days": 30,
    "imports.max_megabytes": 100,
    "backup.daily": True,
    "backup.retention_days": 30,
    "diagnostics.log_retention_days": 30,
    "ui.row_density": "normal",
    "ui.text_scale": 100,
    "ui.high_contrast": False,
    "ui.reduce_motion": True,
    "network.proxy_url": "",
    "data.directory": "",
    "data.backup_directory": "",
    "data.export_directory": "",
    "imports.last_directory.CASHBOOK_CARD": "",
    "imports.last_directory.BANK_CARD": "",
    "imports.last_directory.BOOKING": "",
}
RANGES = {
    "sync.block_days": (1, 31),
    "sync.timeout_seconds": (5, 120),
    "sync.retry_count": (0, 5),
    "matching.bank_window_days": (0, 30),
    "matching.max_combination": (2, 10),
    "matching.max_component_items": (2, 100),
    "matching.max_search_states": (1000, 1000000),
    "matching.warning_age_days": (1, 3650),
    "imports.max_megabytes": (1, 2048),
    "backup.retention_days": (1, 3650),
    "diagnostics.log_retention_days": (1, 3650),
    "ui.text_scale": (80, 160),
}


class SettingsService:
    def __init__(self, db, protector=None):
        self.db = db
        self.protector = protector

    def get(self):
        defaults = {**DEFAULTS, **getattr(self.db, "default_directories", {})}
        defaults["data.directory"] = str(self.db.path.parent)
        defaults["data.backup_directory"] = defaults["data.backup_directory"] or str(
            self.db.path.parent.parent / "backups"
        )
        defaults["data.export_directory"] = defaults["data.export_directory"] or str(
            Path.home() / "Documents" / "KajovoKarty"
        )
        with self.db.connect() as c:
            return {
                **defaults,
                **{
                    r["key"]: json.loads(r["value_json"])
                    for r in c.execute("SELECT * FROM setting")
                },
            }

    def save(self, values, _connection=None):
        from urllib.parse import urlparse

        require(
            set(values) <= set(DEFAULTS), "SETTING_INVALID", "Neznámá volba nastavení."
        )
        errors = {}
        for key, value in values.items():
            if key.startswith("data.") or key.startswith("imports.last_directory."):
                if not isinstance(value, str):
                    errors[key] = "Vyžadována cesta ke složce."
                elif value:
                    path = Path(value).expanduser()
                    if not path.is_absolute() or (path.exists() and not path.is_dir()):
                        errors[key] = "Zadejte úplnou cestu ke složce."
                    elif (
                        key == "data.directory"
                        and path.resolve() != self.db.path.parent.resolve()
                    ):
                        errors[key] = "Použijte tlačítko Přesunout pracovní prostor."
            elif key in RANGES:
                low, high = RANGES[key]
                if type(value) is not int or not low <= value <= high:
                    errors[key] = f"Celé číslo {low} až {high}."
            elif isinstance(DEFAULTS[key], bool) and type(value) is not bool:
                errors[key] = "Vyžadován přepínač."
            elif key == "sync.start_date" and value:
                try:
                    parse_date(value)
                except AppError:
                    errors[key] = "Datum YYYY-MM-DD."
            elif key == "network.proxy_url" and value:
                p = urlparse(value)
                if (
                    p.scheme not in ("http", "https")
                    or not p.hostname
                    or p.username
                    or p.password
                ):
                    errors[key] = "HTTP/HTTPS proxy bez hesla v URL."
            elif key == "sync.requests_per_second":
                try:
                    require(
                        Decimal(".2") <= Decimal(str(value)) <= Decimal("2"),
                        "SETTING_INVALID",
                        "Rozsah 0,2–2.",
                    )
                except (AppError, InvalidOperation):
                    errors[key] = "Rozsah 0,2–2."
            elif key == "ui.row_density" and value not in (
                "compact",
                "normal",
                "comfortable",
            ):
                errors[key] = "Neplatná hustota řádků."
        require(
            not errors, "SETTING_INVALID", "Nastavení obsahuje neplatná pole.", errors
        )
        with (
            nullcontext(_connection)
            if _connection is not None
            else self.db.transaction() as c
        ):
            old = self.get()
            if all(old[k] == v for k, v in values.items()):
                return
            for k, v in values.items():
                if k == "data.directory":
                    continue
                c.execute(
                    "INSERT INTO setting VALUES(?,?,1) ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,revision=setting.revision+1",
                    (k, canonical(v)),
                )
            self.db.invalidate_redo(c)
            self.db.audit(c, "SETTINGS_CHANGED", after=values)

    def tokens(self):
        with self.db.connect() as c:
            rows = {
                r["key"]: r["encrypted_blob"] for r in c.execute("SELECT * FROM secret")
            }
        if "betterhotel" not in rows:
            return ("", "")
        from kajovokarty.infrastructure.secrets import unprotect

        return tuple(
            json.loads(
                (
                    self.protector.decrypt(rows["betterhotel"])
                    if self.protector
                    else unprotect(rows["betterhotel"])
                ).decode()
            )
        )

    def save_tokens(self, access, client, _connection=None):
        access = access.strip()
        client = client.strip()
        require(
            not any(x in access + client for x in ("\r", "\n")),
            "API_AUTH",
            "Token nesmí obsahovat konec řádku.",
        )
        from kajovokarty.infrastructure.secrets import protect

        with self.db.gate:
            try:
                previous = self.tokens()
            except AppError as e:
                if e.code not in ("DPAPI_FAILED", "DPAPI_UNAVAILABLE"):
                    raise
                previous = None
            if (access, client) == previous:
                return
            encrypted = (
                (
                    self.protector.encrypt(canonical([access, client]).encode())
                    if self.protector
                    else protect(canonical([access, client]).encode())
                )
                if access or client
                else None
            )
            with (
                nullcontext(_connection)
                if _connection is not None
                else self.db.transaction() as c
            ):
                old = c.execute("SELECT * FROM helper_state").fetchone()
                ctx = uid()
                revision = old["credential_revision"] + 1
                c.execute(
                    "UPDATE helper_context SET status='RETIRED',retired_at=? WHERE status='CURRENT'",
                    (now(),),
                )
                c.execute(
                    "INSERT INTO helper_context VALUES(?,'CURRENT',?,?,NULL)",
                    (ctx, revision, now()),
                )
                c.execute(
                    "UPDATE helper_state SET context_id=?,credential_revision=?,published_generation_id=NULL,status='UNAVAILABLE',previous_status=NULL,evidence_epoch=0,revision=revision+1,operation_id=NULL,planned_scope_json='{}',last_full_success_at=NULL,failure_code=NULL WHERE id=1",
                    (ctx, revision),
                )
                c.execute("DELETE FROM secret WHERE key='betterhotel'")
                if encrypted:
                    c.execute(
                        "INSERT INTO secret VALUES('betterhotel',?,'DPAPI_USER',?)",
                        (encrypted, now()),
                    )
                self.db.invalidate_redo(c)
                self.db.audit(
                    c,
                    "TOKENS_REPLACED" if encrypted else "TOKENS_REMOVED",
                    after={"old_context_id": old["context_id"], "new_context_id": ctx},
                )

    def proxy_auth(self):
        with self.db.connect() as c:
            row = c.execute(
                "SELECT encrypted_blob FROM secret WHERE key='proxy'"
            ).fetchone()
        if not row:
            return None
        from kajovokarty.infrastructure.secrets import unprotect

        raw = self.protector.decrypt(row[0]) if self.protector else unprotect(row[0])
        return tuple(json.loads(raw.decode()))

    def save_proxy(self, username, password, _connection=None):
        from kajovokarty.infrastructure.secrets import protect

        raw = canonical([username.strip(), password]).encode()
        encrypted = (
            (self.protector.encrypt(raw) if self.protector else protect(raw))
            if username or password
            else None
        )
        with (
            nullcontext(_connection)
            if _connection is not None
            else self.db.transaction() as c
        ):
            c.execute("DELETE FROM secret WHERE key='proxy'")
            if encrypted:
                c.execute(
                    "INSERT INTO secret VALUES('proxy',?,'DPAPI_USER',?)",
                    (encrypted, now()),
                )
            self.db.audit(
                c, "PROXY_CREDENTIALS_CHANGED", after={"present": bool(encrypted)}
            )

    def save_all(self, values, tokens=None, proxy=None):
        with self.db.transaction() as c:
            self.save(values, _connection=c)
            if tokens is not None:
                self.save_tokens(*tokens, _connection=c)
            if proxy is not None:
                self.save_proxy(*proxy, _connection=c)

    def reset(self):
        self.save({k: v for k, v in DEFAULTS.items() if k != "data.directory"})
