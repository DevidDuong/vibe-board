from __future__ import annotations

import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Headless Qt for unit tests; must be set before any Qt import.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest

from clipflow.repositories.command_repository import CommandRepository
from clipflow.repositories.database import open_database
from clipflow.services.command_service import CommandService


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: float) -> None:
        self.now += timedelta(**kwargs)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "data" / "clipflow.sqlite3"


@pytest.fixture
def conn(db_path: Path):
    connection = open_database(db_path)
    yield connection
    connection.close()


@pytest.fixture
def repo(conn) -> CommandRepository:
    return CommandRepository(conn)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def service(repo, clock) -> CommandService:
    return CommandService(repo, clock=clock)
