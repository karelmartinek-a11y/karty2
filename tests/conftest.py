from pathlib import Path
import pytest
from kajovokarty.infrastructure.database import Database
from kajovokarty.application.imports import ImportService


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "test.sqlite")


@pytest.fixture
def fixtures():
    return Path(__file__).parents[1] / "fixtures"


@pytest.fixture
def importer(db):
    return ImportService(db)


import json, re


@pytest.fixture
def wire():
    s = (Path(__file__).parents[1] / "docs/SSOT.md").read_text(encoding="utf-8")
    part = s.split("### A.4 Mock BetterHotel")[1]
    return json.loads(re.search(r"```json\n(.*?)\n```", part, re.S)[1])
