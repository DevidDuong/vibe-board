from __future__ import annotations

import json
import sqlite3
import stat
import sys
from pathlib import Path

import pytest

from clipflow.models.command import CommandDraft
from clipflow.repositories import legacy_history
from clipflow.repositories.command_repository import CommandRepository
from clipflow.repositories.database import open_database
from fakes import LEGACY_ROWS, make_legacy_v1_db

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def legacy_db(db_path):
    make_legacy_v1_db(db_path)
    return db_path


def test_summary_is_metadata_only(legacy_db):
    conn = sqlite3.connect(legacy_db)
    summary = legacy_history.summarize(conn)
    conn.close()
    assert summary.entry_count == 2 and summary.pinned_count == 1
    assert summary.oldest.startswith("2026-09-01") and summary.newest.startswith("2026-09-02")
    assert all(content not in repr(summary) for content, _ in LEGACY_ROWS)


def test_export_is_exact_private_and_never_overwrites(legacy_db, tmp_path):
    out = tmp_path / "export.json"
    conn = sqlite3.connect(legacy_db)
    assert legacy_history.export_entries(conn, out) == 2
    assert stat.S_IMODE(out.stat().st_mode) == 0o600
    exported = {item["content"] for item in json.loads(out.read_text(encoding="utf-8"))}
    assert exported == {content for content, _ in LEGACY_ROWS}
    with pytest.raises(FileExistsError):
        legacy_history.export_entries(conn, out)
    conn.close()


def test_delete_removes_only_legacy_rows_and_scrubs_bytes(legacy_db):
    conn = open_database(legacy_db)  # migrated to v2, as the app would
    CommandRepository(conn).create(
        CommandDraft("keep", "echo keep"), __import__("datetime").datetime.now()
    )
    assert legacy_history.delete_all(conn) == 2
    assert legacy_history.summarize(conn).entry_count == 0
    assert [c.title for c in CommandRepository(conn).list()] == ["keep"]
    conn.close()
    raw = b"".join(
        p.read_bytes() for p in legacy_db.parent.iterdir() if p.name.startswith(legacy_db.name)
    )
    assert b"legacy-entry-alpha" not in raw


def test_summary_without_legacy_table(tmp_path):
    conn = sqlite3.connect(tmp_path / "empty.sqlite3")
    assert legacy_history.summarize(conn) is None
    assert legacy_history.delete_all(conn) == 0
    conn.close()


def _run_script(monkeypatch, *args: str) -> int:
    sys.path.insert(0, str(SCRIPTS))
    try:
        import legacy_history as script  # scripts/legacy_history.py
    finally:
        sys.path.remove(str(SCRIPTS))
    return script.main(list(args))


def test_cli_summary_and_delete_never_print_contents(legacy_db, monkeypatch, capsys):
    assert _run_script(monkeypatch, "--db", str(legacy_db), "summary") == 0
    monkeypatch.setattr("builtins.input", lambda _prompt: "no")
    assert _run_script(monkeypatch, "--db", str(legacy_db), "delete") == 1
    out = capsys.readouterr().out
    assert "Legacy clipboard entries: 2 (1 pinned)" in out and "Cancelled." in out
    assert all(content not in out for content, _ in LEGACY_ROWS)
    assert _run_script(monkeypatch, "--db", str(legacy_db), "delete", "--yes") == 0
    assert "Deleted 2 entries" in capsys.readouterr().out
