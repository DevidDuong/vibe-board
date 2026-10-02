"""UI preferences stored as JSON values under explicit ``ui.*`` keys in ``app_settings``.

Only the keys listed in ``KEYS`` are ever read or written. Legacy rows in the same table
(the superseded ``recording_*`` preferences) are never selected, so they stay inert.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import asdict, fields

from clipflow.models.preferences import UiPreferences
from clipflow.repositories.database import storage_errors, transaction

logger = logging.getLogger(__name__)

KEYS: dict[str, str] = {field.name: f"ui.{field.name}" for field in fields(UiPreferences)}


class PreferencesRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def load(self) -> UiPreferences:
        defaults = UiPreferences()
        placeholders = ", ".join("?" for _ in KEYS)
        with storage_errors("load preferences"):
            rows = self.conn.execute(
                f"SELECT key, value FROM app_settings WHERE key IN ({placeholders})",
                tuple(KEYS.values()),
            ).fetchall()
        stored = {row[0]: row[1] for row in rows}
        values: dict[str, object] = {}
        for name, key in KEYS.items():
            if key not in stored:
                continue
            default = getattr(defaults, name)
            try:
                value = json.loads(stored[key])
            except json.JSONDecodeError:
                logger.warning("Ignoring unreadable preference %s", key)
                continue
            # Exact type match: bool is an int subclass, and "1" must never become True.
            if type(value) is not type(default):
                logger.warning("Ignoring preference %s with unexpected type", key)
                continue
            values[name] = value
        return UiPreferences(**values).validated()

    def save(self, preferences: UiPreferences) -> None:
        preferences = preferences.validated()
        with storage_errors("save preferences"), transaction(self.conn):
            self.conn.executemany(
                "INSERT INTO app_settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                [(KEYS[name], json.dumps(value)) for name, value in asdict(preferences).items()],
            )
