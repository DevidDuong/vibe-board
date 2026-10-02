"""Filesystem locations, defaults, and privacy-safe logging setup."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Override for development/tests so a checkout never touches the real library.
DATA_DIR_ENV = "CLIPFLOW_DATA_DIR"
# Set to "1" to mirror the diagnostic log to stderr (still never contains command text).
DEBUG_ENV = "CLIPFLOW_DEBUG"

# Folder name for the library and logs. Deliberately still "ClipFlow" (the app's former
# name) so existing libraries are found after the rename. Never derive it from APP_NAME.
STORAGE_NAME = "ClipFlow"
DB_FILENAME = "clipflow.sqlite3"
LOG_FILENAME = "clipflow.log"

# Limits for saved commands (validated in services/command_service.py).
MAX_TITLE_CHARS = 120
MAX_CATEGORY_CHARS = 50
MAX_DESCRIPTION_CHARS = 2000
MAX_COMMAND_BYTES = 32 * 1024


@dataclass(frozen=True, slots=True)
class AppPaths:
    data_dir: Path
    log_dir: Path

    @property
    def database(self) -> Path:
        return self.data_dir / DB_FILENAME

    @property
    def log_file(self) -> Path:
        return self.log_dir / LOG_FILENAME


def default_paths() -> AppPaths:
    """Resolve storage locations.

    Data lives in ``~/Library/Application Support/ClipFlow`` and logs in
    ``~/Library/Logs/ClipFlow`` — never the working directory or the app bundle.
    """
    override = os.environ.get(DATA_DIR_ENV)
    if override:
        base = Path(override).expanduser().resolve()
        return AppPaths(data_dir=base, log_dir=base / "logs")
    home = Path.home()
    return AppPaths(
        data_dir=home / "Library" / "Application Support" / STORAGE_NAME,
        log_dir=home / "Library" / "Logs" / STORAGE_NAME,
    )


def ensure_private_dir(path: Path) -> None:
    """Create ``path`` if needed and restrict it to the current user (0700)."""
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, 0o700)


def setup_logging(paths: AppPaths) -> None:
    """Configure a rotating diagnostic log.

    Callers must never log command text, titles, descriptions, search text, or clipboard
    contents — only event kinds, ids, counts, and exception types.
    """
    ensure_private_dir(paths.log_dir)
    handler = RotatingFileHandler(
        paths.log_file, maxBytes=512 * 1024, backupCount=2, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger("clipflow")
    root.setLevel(logging.INFO)
    root.handlers.clear()
    root.addHandler(handler)
    if os.environ.get(DEBUG_ENV) == "1":
        root.setLevel(logging.DEBUG)
        root.addHandler(logging.StreamHandler())
    root.propagate = False
    os.chmod(paths.log_file, 0o600)
