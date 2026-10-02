from __future__ import annotations

import sqlite3
from pathlib import Path

from clipflow.repositories.database import MIGRATIONS


class FakeClipboard:
    """Records writes. Also exposes read-style methods that only count calls, so a test can
    prove the app never reads the clipboard even through duck typing."""

    def __init__(self) -> None:
        self.writes: list[str] = []
        self.read_calls = 0
        self.fail_writes = False

    def write_text(self, text: str) -> None:
        if self.fail_writes:
            raise OSError("simulated clipboard failure")
        self.writes.append(text)

    def _record_read(self, *_args: object) -> None:
        self.read_calls += 1

    read_text = text = mimeData = change_count = changeCount = types = _record_read
    stringForType_ = dataForType_ = pasteboardItems = _record_read


# Obviously fake legacy content (never real clipboard data).
LEGACY_ROWS = [
    ("legacy-entry-alpha  \n\twith whitespace", 0),
    ("legacy-entry-bravo 🙂 ស្វាគមន៍", 1),
]


def make_legacy_v1_db(path: Path) -> None:
    """Create a database exactly as the superseded clipboard-history build left it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, isolation_level=None)
    conn.execute("BEGIN")
    MIGRATIONS[1](conn)
    conn.execute("PRAGMA user_version = 1")
    for i, (content, pinned) in enumerate(LEGACY_ROWS):
        stamp = f"2026-09-0{i + 1}T08:00:00.000000+00:00"
        conn.execute(
            "INSERT INTO clipboard_entries (content, content_hash, is_pinned, created_at,"
            " last_copied_at, byte_size) VALUES (?, ?, ?, ?, ?, ?)",
            (content, f"hash-{i}", pinned, stamp, stamp, len(content.encode())),
        )
    # Preferences that would have re-enabled recording in the old build.
    conn.executemany(
        "INSERT INTO app_settings (key, value) VALUES (?, ?)",
        [("recording_consent", "true"), ("recording_paused", "false")],
    )
    conn.execute("COMMIT")
    conn.close()


def dump_legacy(path: Path) -> tuple[list[tuple], list[tuple]]:
    conn = sqlite3.connect(path)
    try:
        entries = conn.execute("SELECT * FROM clipboard_entries ORDER BY id").fetchall()
        settings = conn.execute("SELECT * FROM app_settings ORDER BY key").fetchall()
    finally:
        conn.close()
    return entries, settings


class FakeHotkeyBackend:
    """Stands in for the OS shortcut service. ``system_taken`` mimics macOS's own shortcuts;
    ``refuse`` mimics combos the OS rejects at registration time."""

    def __init__(self, *, system_taken=None, refuse=()) -> None:
        self.system_taken = dict(system_taken or {})
        self.refuse = set(refuse)
        self.registered: dict = {}
        self.history: list[tuple[str, object]] = []

    def system_conflict(self, hotkey):
        return self.system_taken.get(hotkey)

    def register(self, hotkey, callback):
        from clipflow.platform.hotkey import HotkeyError

        if hotkey in self.refuse or hotkey in self.registered:
            raise HotkeyError(f"{hotkey.display()} is already registered.")
        self.registered[hotkey] = callback
        self.history.append(("register", hotkey))
        backend = self

        class _Registration:
            def unregister(self) -> None:
                if backend.registered.pop(hotkey, None) is not None:
                    backend.history.append(("unregister", hotkey))

        return _Registration()

    def press(self, hotkey) -> None:
        """What the OS does when the registered combination is pressed."""
        self.registered[hotkey]()
