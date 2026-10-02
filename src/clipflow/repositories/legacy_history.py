"""Legacy clipboard history left over from the superseded clipboard-recording design.

The running app never calls this module: legacy entries are neither shown nor imported.
It exists only for ``scripts/legacy_history.py``, which lets the user review (summary or
export) or securely delete that data on request.
"""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path

LEGACY_TABLE = "clipboard_entries"


@dataclass(frozen=True, slots=True)
class LegacySummary:
    entry_count: int
    pinned_count: int
    oldest: str | None
    newest: str | None


def has_legacy_table(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (LEGACY_TABLE,)
    ).fetchone()
    return row is not None


def summarize(conn: sqlite3.Connection) -> LegacySummary | None:
    """Counts and date range only; never reads entry contents."""
    if not has_legacy_table(conn):
        return None
    row = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(is_pinned), 0), MIN(created_at), MAX(last_copied_at)"
        " FROM clipboard_entries"
    ).fetchone()
    return LegacySummary(entry_count=row[0], pinned_count=row[1], oldest=row[2], newest=row[3])


def export_entries(conn: sqlite3.Connection, destination: Path) -> int:
    """Write all legacy entries to a new user-only (0600) JSON file. Refuses to overwrite."""
    if not has_legacy_table(conn):
        return 0
    rows = conn.execute(
        "SELECT id, content, is_pinned, created_at, last_copied_at, copy_count"
        " FROM clipboard_entries ORDER BY last_copied_at DESC, id DESC"
    ).fetchall()
    payload = [
        {
            "id": row[0],
            "content": row[1],
            "is_pinned": bool(row[2]),
            "created_at": row[3],
            "last_copied_at": row[4],
            "copy_count": row[5],
        }
        for row in rows
    ]
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    return len(payload)


def delete_all(conn: sqlite3.Connection) -> int:
    """Delete every legacy entry and scrub freed pages. Only called on explicit user request."""
    if not has_legacy_table(conn):
        return 0
    conn.execute("PRAGMA secure_delete = ON")  # overwrite deleted content with zeros
    removed = conn.execute("DELETE FROM clipboard_entries").rowcount
    conn.execute("VACUUM")
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    return removed
