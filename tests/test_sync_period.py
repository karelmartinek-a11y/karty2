"""User-controlled history and filtering when the server ignores date parameters."""

from datetime import date, timedelta
import json

import pytest

from kajovokarty.application.settings import SettingsService
from kajovokarty.domain.core import AppError
from kajovokarty.infrastructure.database import Database


@pytest.mark.parametrize("old", [None, "", "2026-02-03"])
def test_start_setting_initialized_and_preserved(db, old):
    with db.transaction() as c:
        c.execute("DELETE FROM setting WHERE key='sync.start_date'")
        if old is not None:
            c.execute("INSERT INTO setting VALUES('sync.start_date',?,1)", (json.dumps(old),))
    reopened = Database(db.path)
    assert SettingsService(reopened).get()["sync.start_date"] == (old or "2026-01-01")
    SettingsService(reopened).save({"sync.start_date": "2026-03-04"})
    assert SettingsService(Database(db.path)).get()["sync.start_date"] == "2026-03-04"


@pytest.mark.parametrize("value", ["", None, "bad", "2026-02-30", "20260101"])
def test_invalid_date_rejected(db, value):
    with pytest.raises(AppError, match="Nastavení"):
        SettingsService(db).save({"sync.start_date": value})


def test_future_date_rejected(db):
    with pytest.raises(AppError):
        SettingsService(db).save({"sync.start_date": (date.today() + timedelta(days=1)).isoformat()})
