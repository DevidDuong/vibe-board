"""Write-only clipboard interface.

ClipFlow never reads the system clipboard. The only clipboard operation the app performs is
writing a saved command after the user explicitly asks to copy it.
"""

from __future__ import annotations

from typing import Protocol


class ClipboardWriter(Protocol):
    def write_text(self, text: str) -> None:
        """Replace the clipboard contents with ``text``. Raises ``OSError`` on failure."""
        ...
