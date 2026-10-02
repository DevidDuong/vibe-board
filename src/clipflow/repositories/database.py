"""SQLite connection setup and schema migrations (tracked with ``PRAGMA user_version``)."""

from __future__ import annotations

import logging
import os
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from clipflow import APP_NAME
from clipflow.config import ensure_private_dir

logger = logging.getLogger(__name__)

SIDECAR_SUFFIXES = ("-wal", "-shm", "-journal")


class StorageError(Exception):
    """A database problem the UI should surface. Messages never contain stored text."""


# v1 is the superseded clipboard-history schema. It is kept verbatim so existing databases
# stay valid; ``clipboard_entries`` is legacy data that the app no longer reads or writes
# (see repositories/legacy_history.py).
_SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS clipboard_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL DEFAULT 'text' CHECK (kind IN ('text')),
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    is_pinned INTEGER NOT NULL DEFAULT 0 CHECK (is_pinned IN (0,1)),
    source_bundle_id TEXT,
    created_at TEXT NOT NULL,
    last_copied_at TEXT NOT NULL,
    copy_count INTEGER NOT NULL DEFAULT 1,
    byte_size INTEGER NOT NULL,
    UNIQUE(kind, content_hash)
);
CREATE INDEX IF NOT EXISTS idx_clipboard_recent
    ON clipboard_entries(last_copied_at DESC);
CREATE INDEX IF NOT EXISTS idx_clipboard_pin_recent
    ON clipboard_entries(is_pinned DESC, last_copied_at DESC);
CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

# v2 adds the command library. Additive only: no existing table or row is touched.
_SCHEMA_V2 = """
CREATE TABLE IF NOT EXISTS commands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL CHECK (length(trim(title)) > 0),
    command TEXT NOT NULL CHECK (length(command) > 0),
    description TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '',
    is_pinned INTEGER NOT NULL DEFAULT 0 CHECK (is_pinned IN (0,1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_commands_pin_title
    ON commands(is_pinned DESC, title COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_commands_category
    ON commands(category);
"""


def _run_script(conn: sqlite3.Connection, script: str) -> None:
    # executescript() would COMMIT the surrounding transaction, so run statements one by one.
    for statement in script.split(";"):
        if statement.strip():
            conn.execute(statement)


# Each migration must be idempotent. Before adding a destructive one, back up the file first.
MIGRATIONS: dict[int, Callable[[sqlite3.Connection], None]] = {
    1: lambda conn: _run_script(conn, _SCHEMA_V1),
    2: lambda conn: _run_script(conn, _SCHEMA_V2),
}
SCHEMA_VERSION = max(MIGRATIONS)


def _casefold_contains(haystack: str | None, needle: str | None) -> int:
    if haystack is None or needle is None:
        return 0
    return int(needle in haystack.casefold())


def _restrict_files(path: Path) -> None:
    for candidate in (path, *(Path(f"{path}{suffix}") for suffix in SIDECAR_SUFFIXES)):
        if candidate.exists():
            os.chmod(candidate, 0o600)


def open_database(path: Path) -> sqlite3.Connection:
    """Open (creating if needed) the ClipFlow database and bring its schema up to date."""
    try:
        ensure_private_dir(path.parent)
        # Create the file 0600 before SQLite opens it: SQLite gives new -wal/-shm files the
        # main file's mode, so this keeps every database file user-only from the start.
        os.close(os.open(path, os.O_CREAT | os.O_RDWR, 0o600))
        _restrict_files(path)
        # Autocommit mode; writes use explicit transactions via ``transaction()``.
        conn = sqlite3.connect(path, isolation_level=None)
    except (OSError, sqlite3.Error) as exc:
        raise StorageError(f"Cannot open database ({type(exc).__name__})") from exc
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 3000")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.create_function("cf_contains", 2, _casefold_contains, deterministic=True)
        migrate(conn)
        _restrict_files(path)
    except (OSError, sqlite3.Error, StorageError) as exc:
        conn.close()
        if isinstance(exc, StorageError):
            raise
        raise StorageError(f"Cannot initialise database ({type(exc).__name__})") from exc
    return conn


def migrate(conn: sqlite3.Connection) -> None:
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    if current > SCHEMA_VERSION:
        raise StorageError(
            f"Database schema v{current} is newer than this {APP_NAME} build (v{SCHEMA_VERSION})"
        )
    for version in range(current + 1, SCHEMA_VERSION + 1):
        with transaction(conn):
            MIGRATIONS[version](conn)
            conn.execute(f"PRAGMA user_version = {int(version)}")
        logger.info("Migrated database schema to v%d", version)


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Run a write transaction; joins an already open transaction instead of nesting."""
    if conn.in_transaction:
        yield conn
        return
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


@contextmanager
def storage_errors(action: str) -> Iterator[None]:
    """Translate sqlite3 errors into ``StorageError`` without echoing values."""
    try:
        yield
    except sqlite3.Error as exc:
        # Log only the operation and exception type: sqlite messages can echo values.
        logger.error("Storage failure during %s (%s)", action, type(exc).__name__)
        raise StorageError(f"Could not {action} ({type(exc).__name__})") from exc
