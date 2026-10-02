from __future__ import annotations

import logging

import pytest

from clipflow.models.command import CommandDraft
from clipflow.repositories.database import StorageError
from clipflow.services.command_service import (
    CommandNotFoundError,
    SecretPolicyError,
    ValidationError,
)

FAKE_TOKEN = "ghp_" + "Fake" * 9
FAKE_KEY = "-----BEGIN " + "EC PRIVATE KEY-----"


def test_nothing_persists_without_explicit_create(service):
    draft = CommandDraft("t", "echo hi")
    service.normalize(draft)
    service.validate(draft)
    service.scan(draft)
    assert service.count() == 0
    service.create(draft)
    assert service.count() == 1


def test_metadata_trimmed_command_preserved_exactly(service):
    text = "  for i in 1 2; do\n\techo $i\n  done  \n"
    cmd = service.create(CommandDraft("  Loop  ", text, "  notes \n", "  Shell "))
    assert (cmd.title, cmd.description, cmd.category) == ("Loop", "notes", "Shell")
    assert cmd.command == text


def test_category_reuses_existing_spelling(service):
    service.create(CommandDraft("a", "x", category="Git"))
    second = service.create(CommandDraft("b", "y", category="git"))
    assert second.category == "Git"
    assert service.categories() == ["Git"]


@pytest.mark.parametrize(
    ("draft", "field"),
    [
        (CommandDraft("", "ls"), "title"),
        (CommandDraft("   ", "ls"), "title"),
        (CommandDraft("t", ""), "command"),
        (CommandDraft("t", " \n\t "), "command"),
        (CommandDraft("x" * 121, "ls"), "title"),
        (CommandDraft("t", "x" * (32 * 1024 + 1)), "command"),
        (CommandDraft("t", "ls", description="d" * 2001), "description"),
        (CommandDraft("t", "ls", category="c" * 51), "category"),
        (CommandDraft("t", "bad \ud800 surrogate"), "command"),
    ],
)
def test_validation(service, draft, field):
    with pytest.raises(ValidationError) as info:
        service.create(draft)
    assert field in info.value.problems
    assert service.count() == 0


def test_update_and_missing(service, clock):
    cmd = service.create(CommandDraft("t", "a"))
    clock.advance(minutes=1)
    updated = service.update(cmd.id, CommandDraft("t2", "b\nc"))
    assert updated.command == "b\nc" and updated.updated_at > cmd.updated_at
    service.delete(cmd.id)
    with pytest.raises(CommandNotFoundError):
        service.update(cmd.id, CommandDraft("t3", "d"))


def test_pin_and_delete(service):
    cmd = service.create(CommandDraft("t", "a"))
    assert service.set_pinned(cmd.id, True)
    assert service.get(cmd.id).is_pinned
    assert service.delete(cmd.id)
    assert service.get(cmd.id) is None


def test_secret_warning_requires_acknowledgement(service):
    draft = CommandDraft("Login", f"gh auth login --with-token {FAKE_TOKEN}")
    with pytest.raises(SecretPolicyError) as info:
        service.create(draft)
    assert not info.value.blocked
    assert FAKE_TOKEN not in str(info.value)
    assert service.count() == 0
    assert service.create(draft, acknowledge_warnings=True).command == draft.command


@pytest.mark.parametrize("field", ["title", "command", "description", "category"])
def test_private_key_is_rejected_in_any_field(service, field):
    values = {"title": "t", "command": "echo", "description": "", "category": ""}
    values[field] = FAKE_KEY
    with pytest.raises(SecretPolicyError) as info:
        service.create(CommandDraft(**values), acknowledge_warnings=True)
    assert info.value.blocked
    assert service.count() == 0


def test_secret_policy_applies_to_updates(service):
    cmd = service.create(CommandDraft("t", "echo ok"))
    with pytest.raises(SecretPolicyError):
        service.update(cmd.id, CommandDraft("t", f"export TOKEN={FAKE_TOKEN}"))
    assert service.get(cmd.id).command == "echo ok"


def test_storage_errors_are_translated_without_content(service, conn):
    conn.close()
    with pytest.raises(StorageError) as info:
        service.create(CommandDraft("secret-title-zz", "secret-command-zz"))
    assert "secret-title-zz" not in str(info.value)
    assert "secret-command-zz" not in str(info.value)
    with pytest.raises(StorageError):
        service.list_commands()


def test_command_text_never_logged(service, caplog):
    with caplog.at_level(logging.DEBUG, logger="clipflow"):
        cmd = service.create(CommandDraft("title-marker-q", "command-marker-q", "desc-marker-q"))
        service.update(cmd.id, CommandDraft("title-marker-r", "command-marker-r"))
        service.list_commands(query="search-marker-q")
        with pytest.raises(SecretPolicyError):
            service.create(CommandDraft("x", f"T={FAKE_TOKEN}"))
        service.delete(cmd.id)
    for marker in ("marker-q", "marker-r", FAKE_TOKEN):
        assert marker not in caplog.text
