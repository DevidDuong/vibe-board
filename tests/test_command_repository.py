from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from clipflow.models.command import CommandDraft

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _add(repo, title, command="echo hi", description="", category="", now=NOW):
    return repo.create(CommandDraft(title, command, description, category), now)


def test_create_get_update_delete(repo):
    cid = _add(repo, "List files", "ls -la", "long listing", "Shell")
    cmd = repo.get(cid)
    assert (cmd.title, cmd.command, cmd.description, cmd.category) == (
        "List files",
        "ls -la",
        "long listing",
        "Shell",
    )
    assert cmd.created_at == cmd.updated_at == NOW and not cmd.is_pinned

    later = NOW + timedelta(minutes=5)
    assert repo.update(cid, CommandDraft("List all", "ls -lah", "", "Shell"), later)
    updated = repo.get(cid)
    assert updated.title == "List all" and updated.command == "ls -lah"
    assert updated.created_at == NOW and updated.updated_at == later

    assert repo.delete(cid)
    assert repo.get(cid) is None
    assert not repo.delete(cid)
    assert not repo.update(cid, CommandDraft("x", "y"), later)


@pytest.mark.parametrize(
    "text",
    [
        'for f in *.log; do\n\tgzip "$f"\ndone\n',
        "docker run --rm \\\n  -v \"$PWD\":/w \\\n  alpine sh -c 'ls /w'",
        "cat <<'EOF' > out.txt\n  indented $HOME stays literal\nEOF",
        "echo 'Khmer: សួស្តី · émoji 🚀'\r\n",
        "'; DROP TABLE commands; --",
        "   leading and trailing spaces   ",
    ],
)
def test_command_text_round_trips_exactly(repo, text):
    cid = _add(repo, "t", text)
    assert repo.get(cid).command == text


def test_search_title_command_description_case_insensitive(repo):
    _add(repo, "Docker cleanup", "docker system prune", "Frees disk space")
    _add(repo, "Git log", "git log --oneline --graph", "")
    _add(repo, "Ports", "lsof -iTCP -sTCP:LISTEN", "Show what is LISTENING on Straße")
    titles = lambda q: [c.title for c in repo.list(query=q)]  # noqa: E731
    assert titles("docker") == ["Docker cleanup"]  # title + command
    assert titles("ONELINE") == ["Git log"]  # command only
    assert titles("disk space") == ["Docker cleanup"]  # description only
    assert titles("STRASSE") == ["Ports"]  # Unicode casefold
    assert titles("%") == [] and titles("_") == []  # LIKE wildcards are literal
    assert titles("' OR 1=1 --") == []


def test_category_filter_and_categories(repo):
    _add(repo, "a", category="Git")
    _add(repo, "b", category="Docker")
    _add(repo, "c", category="")
    assert [c.title for c in repo.list(category="Git")] == ["a"]
    assert [c.title for c in repo.list(category="")] == ["c"]
    assert len(repo.list(category=None)) == 3
    assert repo.categories() == ["Docker", "Git"]


def test_pinned_first_then_title(repo):
    b = _add(repo, "beta")
    _add(repo, "Alpha")
    _add(repo, "gamma")
    assert repo.set_pinned(b, True)
    assert [c.title for c in repo.list()] == ["beta", "Alpha", "gamma"]
    assert repo.set_pinned(b, False)
    assert [c.title for c in repo.list()] == ["Alpha", "beta", "gamma"]


def test_schema_rejects_empty_title_or_command(repo, conn):
    import sqlite3

    with pytest.raises(sqlite3.IntegrityError):
        _add(repo, "   ", "x")
    with pytest.raises(sqlite3.IntegrityError):
        _add(repo, "t", "")
