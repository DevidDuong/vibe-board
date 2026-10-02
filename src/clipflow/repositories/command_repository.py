"""Parameterized SQL for the ``commands`` table. No business rules live here."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from clipflow.models.command import Command, CommandDraft

_COLUMNS = "id, title, command, description, category, is_pinned, created_at, updated_at"


def to_db_time(value: datetime) -> str:
    # Fixed-width UTC ISO 8601 so lexical order equals chronological order.
    return value.astimezone(UTC).isoformat(timespec="microseconds")


def _row_to_command(row: sqlite3.Row) -> Command:
    return Command(
        id=row["id"],
        title=row["title"],
        command=row["command"],
        description=row["description"],
        category=row["category"],
        is_pinned=bool(row["is_pinned"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


class CommandRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def create(self, draft: CommandDraft, now: datetime) -> int:
        stamp = to_db_time(now)
        cursor = self.conn.execute(
            "INSERT INTO commands (title, command, description, category, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (draft.title, draft.command, draft.description, draft.category, stamp, stamp),
        )
        return int(cursor.lastrowid)

    def update(self, command_id: int, draft: CommandDraft, now: datetime) -> bool:
        cursor = self.conn.execute(
            "UPDATE commands SET title = ?, command = ?, description = ?, category = ?,"
            " updated_at = ? WHERE id = ?",
            (
                draft.title,
                draft.command,
                draft.description,
                draft.category,
                to_db_time(now),
                command_id,
            ),
        )
        return cursor.rowcount == 1

    def get(self, command_id: int) -> Command | None:
        row = self.conn.execute(
            f"SELECT {_COLUMNS} FROM commands WHERE id = ?", (command_id,)
        ).fetchone()
        return None if row is None else _row_to_command(row)

    def delete(self, command_id: int) -> bool:
        return self.conn.execute("DELETE FROM commands WHERE id = ?", (command_id,)).rowcount == 1

    def set_pinned(self, command_id: int, pinned: bool) -> bool:
        cursor = self.conn.execute(
            "UPDATE commands SET is_pinned = ? WHERE id = ?", (int(pinned), command_id)
        )
        return cursor.rowcount == 1

    def list(
        self, *, query: str = "", category: str | None = None, pinned_only: bool = False
    ) -> list[Command]:
        """Pinned first, then by title. ``query`` matches title, command, or description
        case-insensitively (Unicode casefold); ``category`` is an exact match when given."""
        clauses: list[str] = []
        params: dict[str, object] = {}
        if pinned_only:
            clauses.append("is_pinned = 1")
        if query:
            clauses.append(
                "(cf_contains(title, :needle) OR cf_contains(command, :needle)"
                " OR cf_contains(description, :needle))"
            )
            params["needle"] = query.casefold()
        if category is not None:
            clauses.append("category = :category")
            params["category"] = category
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.conn.execute(
            f"SELECT {_COLUMNS} FROM commands {where} "
            "ORDER BY is_pinned DESC, title COLLATE NOCASE, id",
            params,
        ).fetchall()
        return [_row_to_command(row) for row in rows]

    def categories(self) -> list[str]:
        rows = self.conn.execute(
            "SELECT DISTINCT category FROM commands WHERE category != '' "
            "ORDER BY category COLLATE NOCASE"
        ).fetchall()
        return [row["category"] for row in rows]

    def count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM commands").fetchone()[0])
