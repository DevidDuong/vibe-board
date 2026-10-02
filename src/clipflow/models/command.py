from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class CommandDraft:
    """User-entered fields for creating or editing a command. ``command`` is kept verbatim."""

    title: str
    command: str
    description: str = ""
    category: str = ""


@dataclass(frozen=True, slots=True)
class Command:
    """A saved command. Its ``command`` text is data only and is never executed by ClipFlow."""

    id: int
    title: str
    command: str
    description: str
    category: str
    is_pinned: bool
    created_at: datetime
    updated_at: datetime

    def to_draft(self) -> CommandDraft:
        return CommandDraft(
            title=self.title,
            command=self.command,
            description=self.description,
            category=self.category,
        )
