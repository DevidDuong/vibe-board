"""Review or delete clipboard history left by the superseded clipboard-recording version.

    python scripts/legacy_history.py summary              # counts and dates only
    python scripts/legacy_history.py export ~/Desktop/clipflow-legacy.json
    python scripts/legacy_history.py delete               # asks you to type DELETE

The Vibe-Board app (formerly ClipFlow) never shows, imports, or deletes this data by itself.
Nothing here prints clipboard contents to the terminal. ``export`` writes them to a new
file only you can read (mode 0600); delete that file when you're done. Respects
CLIPFLOW_DATA_DIR, or use --db.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from clipflow import APP_NAME
from clipflow.config import default_paths
from clipflow.repositories import legacy_history


def _connect_read_only(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", type=Path, default=default_paths().database)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("summary", help="show counts and date range (no contents)")
    export = sub.add_parser("export", help="write entries to a new 0600 JSON file")
    export.add_argument("destination", type=Path)
    delete = sub.add_parser("delete", help="permanently delete all legacy entries")
    delete.add_argument("--yes", action="store_true", help="skip the typed confirmation")
    args = parser.parse_args(argv)

    db: Path = args.db.expanduser()
    if not db.exists():
        print(f"No {APP_NAME} database at {db}; nothing to do.")
        return 0

    if args.action == "summary":
        with closing(_connect_read_only(db)) as conn:
            summary = legacy_history.summarize(conn)
        if summary is None or summary.entry_count == 0:
            print(f"No legacy clipboard history in {db}.")
        else:
            print(f"Database: {db}")
            print(
                f"Legacy clipboard entries: {summary.entry_count} ({summary.pinned_count} pinned)"
            )
            print(f"Oldest: {summary.oldest}   Newest: {summary.newest}  (UTC)")
        return 0

    if args.action == "export":
        destination: Path = args.destination.expanduser()
        if destination.exists():
            print(f"Refusing to overwrite {destination}.", file=sys.stderr)
            return 1
        with closing(_connect_read_only(db)) as conn:
            count = legacy_history.export_entries(conn, destination)
        print(f"Exported {count} entries to {destination} (readable only by you).")
        print("It contains whatever was on your clipboard; delete it when you're done.")
        return 0

    # delete
    with closing(_connect_read_only(db)) as conn:
        summary = legacy_history.summarize(conn)
    if summary is None or summary.entry_count == 0:
        print("No legacy clipboard history to delete.")
        return 0
    print(f"This permanently deletes {summary.entry_count} legacy clipboard entries from {db}.")
    print("Saved commands are not affected. Consider `export` first if you want a copy.")
    if not args.yes and input("Type DELETE to continue: ").strip() != "DELETE":
        print("Cancelled.")
        return 1
    conn = sqlite3.connect(db, isolation_level=None)
    try:
        removed = legacy_history.delete_all(conn)
    finally:
        conn.close()
    print(f"Deleted {removed} entries and scrubbed the freed space.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
