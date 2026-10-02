"""Command library rules: validation, secret policy, and persistence on explicit save.

Commands are stored and returned as plain data. Nothing here (or anywhere in ClipFlow)
executes, parses, or shell-expands command text.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime

from clipflow import config
from clipflow.models.command import Command, CommandDraft
from clipflow.repositories.command_repository import CommandRepository
from clipflow.repositories.database import storage_errors, transaction
from clipflow.services.secret_scanner import SecretFinding, SecretScanner, Severity, scan_fields

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(UTC)


class ValidationError(Exception):
    def __init__(self, problems: dict[str, str]) -> None:
        super().__init__("; ".join(f"{field}: {msg}" for field, msg in problems.items()))
        self.problems = problems


class SecretPolicyError(Exception):
    """Raised before saving when the draft appears to contain a secret."""

    def __init__(self, findings: list[SecretFinding]) -> None:
        kinds = ", ".join(sorted({f"{f.kind} in {f.field}" for f in findings}))
        super().__init__(f"Possible secret detected: {kinds}")
        self.findings = findings

    @property
    def blocked(self) -> bool:
        return any(f.severity is Severity.BLOCK for f in self.findings)


class CommandNotFoundError(Exception):
    pass


FIELD_LABELS = {
    "title": "Title",
    "command": "Command",
    "description": "Description",
    "category": "Category",
}


class CommandService:
    def __init__(
        self,
        repo: CommandRepository,
        *,
        clock: Callable[[], datetime] = utc_now,
        scanner: SecretScanner = scan_fields,
    ) -> None:
        self._repo = repo
        self._clock = clock
        self._scanner = scanner

    # -- validation -------------------------------------------------------------------

    def normalize(self, draft: CommandDraft) -> CommandDraft:
        """Trim metadata fields. The command text itself is preserved byte for byte."""
        category = draft.category.strip()
        if category:
            # Reuse an existing category's spelling so "git" and "Git" don't split the filter.
            for existing in self.categories():
                if existing.casefold() == category.casefold():
                    category = existing
                    break
        return CommandDraft(
            title=draft.title.strip(),
            command=draft.command,
            description=draft.description.strip(),
            category=category,
        )

    @staticmethod
    def validate(draft: CommandDraft) -> dict[str, str]:
        problems: dict[str, str] = {}
        if not draft.title:
            problems["title"] = "Enter a title."
        elif len(draft.title) > config.MAX_TITLE_CHARS:
            problems["title"] = f"Use at most {config.MAX_TITLE_CHARS} characters."
        if not draft.command.strip():
            problems["command"] = "Enter the command text."
        else:
            try:
                size = len(draft.command.encode("utf-8"))
            except UnicodeEncodeError:
                problems["command"] = "The command contains characters that can't be stored."
            else:
                if size > config.MAX_COMMAND_BYTES:
                    problems["command"] = (
                        f"Commands are limited to {config.MAX_COMMAND_BYTES // 1024} KiB."
                    )
        if len(draft.description) > config.MAX_DESCRIPTION_CHARS:
            problems["description"] = f"Use at most {config.MAX_DESCRIPTION_CHARS} characters."
        if len(draft.category) > config.MAX_CATEGORY_CHARS:
            problems["category"] = f"Use at most {config.MAX_CATEGORY_CHARS} characters."
        return problems

    def scan(self, draft: CommandDraft) -> list[SecretFinding]:
        return self._scanner(
            {
                FIELD_LABELS["title"]: draft.title,
                FIELD_LABELS["command"]: draft.command,
                FIELD_LABELS["description"]: draft.description,
                FIELD_LABELS["category"]: draft.category,
            }
        )

    def _prepare(self, draft: CommandDraft, acknowledge_warnings: bool) -> CommandDraft:
        draft = self.normalize(draft)
        problems = self.validate(draft)
        if problems:
            raise ValidationError(problems)
        findings = self.scan(draft)
        blocked = [f for f in findings if f.severity is Severity.BLOCK]
        if blocked or (findings and not acknowledge_warnings):
            logger.info("Save refused by secret policy (%d findings)", len(findings))
            raise SecretPolicyError(blocked or findings)
        return draft

    # -- persistence (only via explicit save) -------------------------------------------

    def create(self, draft: CommandDraft, *, acknowledge_warnings: bool = False) -> Command:
        draft = self._prepare(draft, acknowledge_warnings)
        with storage_errors("save command"), transaction(self._repo.conn):
            command_id = self._repo.create(draft, self._clock())
        logger.info("Command %d created", command_id)
        return self.get_required(command_id)

    def update(
        self, command_id: int, draft: CommandDraft, *, acknowledge_warnings: bool = False
    ) -> Command:
        draft = self._prepare(draft, acknowledge_warnings)
        with storage_errors("save command"), transaction(self._repo.conn):
            if not self._repo.update(command_id, draft, self._clock()):
                raise CommandNotFoundError(command_id)
        logger.info("Command %d updated", command_id)
        return self.get_required(command_id)

    def delete(self, command_id: int) -> bool:
        with storage_errors("delete command"), transaction(self._repo.conn):
            deleted = self._repo.delete(command_id)
        logger.info("Command %d deleted=%s", command_id, deleted)
        return deleted

    def set_pinned(self, command_id: int, pinned: bool) -> bool:
        with storage_errors("update pin"), transaction(self._repo.conn):
            return self._repo.set_pinned(command_id, pinned)

    # -- queries ----------------------------------------------------------------------

    def get(self, command_id: int) -> Command | None:
        with storage_errors("load command"):
            return self._repo.get(command_id)

    def get_required(self, command_id: int) -> Command:
        command = self.get(command_id)
        if command is None:
            raise CommandNotFoundError(command_id)
        return command

    def list_commands(
        self, *, query: str = "", category: str | None = None, pinned_only: bool = False
    ) -> list[Command]:
        with storage_errors("load commands"):
            return self._repo.list(query=query, category=category, pinned_only=pinned_only)

    def categories(self) -> list[str]:
        with storage_errors("load categories"):
            return self._repo.categories()

    def count(self) -> int:
        with storage_errors("count commands"):
            return self._repo.count()
