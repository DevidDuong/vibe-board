from __future__ import annotations

import stat

import pytest

from clipflow.repositories.database import SCHEMA_VERSION, StorageError, open_database
from fakes import dump_legacy, make_legacy_v1_db


def _mode(path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_fresh_database_schema_and_user_only_permissions(conn, db_path):
    assert SCHEMA_VERSION == 2
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"commands", "clipboard_entries", "app_settings"} <= tables
    conn.execute(
        "INSERT INTO commands (title, command, created_at, updated_at) VALUES ('t','c','x','x')"
    )
    assert _mode(db_path.parent) == 0o700
    for suffix in ("", "-wal", "-shm"):
        sidecar = db_path.with_name(db_path.name + suffix)
        assert sidecar.exists() and _mode(sidecar) == 0o600, suffix


def test_existing_world_readable_sidecars_are_tightened(db_path):
    open_database(db_path).close()
    for suffix in ("-wal", "-shm"):
        sidecar = db_path.with_name(db_path.name + suffix)
        sidecar.touch()
        sidecar.chmod(0o644)
    open_database(db_path).close()
    for suffix in ("-wal", "-shm"):
        sidecar = db_path.with_name(db_path.name + suffix)
        if sidecar.exists():
            assert _mode(sidecar) == 0o600


def test_v1_to_v2_migration_preserves_legacy_history_and_settings(db_path):
    make_legacy_v1_db(db_path)
    before = dump_legacy(db_path)
    open_database(db_path).close()
    open_database(db_path).close()  # idempotent
    assert dump_legacy(db_path) == before
    conn = open_database(db_path)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM commands").fetchone()[0] == 0
    conn.close()


def test_newer_schema_is_refused_without_touching_data(db_path):
    conn = open_database(db_path)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    conn.close()
    with pytest.raises(StorageError):
        open_database(db_path)


def test_unwritable_location_raises_storage_error(tmp_path):
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o500)
    try:
        with pytest.raises(StorageError):
            open_database(locked / "sub" / "clipflow.sqlite3")
    finally:
        locked.chmod(0o700)
