"""Remembered palette geometry, stored as JSON under the ``ui.window_geometry`` key.

Unlike preferences (written only on an explicit Save), this is UI state: it's written when
the palette hides and when the app quits, so the window reopens where the user left it.
Only this key is read or written; other ``app_settings`` rows are never touched.
"""

from __future__ import annotations

import json
import logging
import sqlite3

from clipflow.models.window_state import WindowState
from clipflow.repositories.database import storage_errors, transaction

logger = logging.getLogger(__name__)

KEY = "ui.window_geometry"
COORDINATE_LIMIT = 100_000
SIZE_LIMIT = 20_000


class WindowStateRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def load(self) -> WindowState | None:
        with storage_errors("load window position"):
            row = self.conn.execute(
                "SELECT value FROM app_settings WHERE key = ?", (KEY,)
            ).fetchone()
        if row is None:
            return None
        try:
            data = json.loads(row[0])
            values = {name: data[name] for name in ("x", "y", "width", "height")}
        except (json.JSONDecodeError, TypeError, KeyError):
            logger.warning("Ignoring unreadable window position")
            return None
        if not all(type(v) is int for v in values.values()) or not (
            all(abs(values[n]) <= COORDINATE_LIMIT for n in ("x", "y"))
            and all(1 <= values[n] <= SIZE_LIMIT for n in ("width", "height"))
        ):
            logger.warning("Ignoring out-of-range window position")
            return None
        return WindowState(**values)

    def save(self, state: WindowState) -> None:
        value = json.dumps(
            {"x": state.x, "y": state.y, "width": state.width, "height": state.height}
        )
        with storage_errors("save window position"), transaction(self.conn):
            self.conn.execute(
                "INSERT INTO app_settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (KEY, value),
            )
