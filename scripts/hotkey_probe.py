"""Manually verify the global shortcut on this Mac (no Vibe-Board window, no data access).

    python scripts/hotkey_probe.py --check ctrl+option+cmd+V   # can this combination be used?
    python scripts/hotkey_probe.py --listen                    # default ⌃⌥⌘V, 60 seconds
    python scripts/hotkey_probe.py --listen ctrl+shift+cmd+K --seconds 120

--listen registers the shortcut exactly the way Vibe-Board does and prints a line each time
it's pressed, so you can switch to Terminal, Safari, or VS Code and press it there. Quit
Vibe-Board first: two apps holding the same shortcut is allowed by macOS, and only one of
them receives each press. Nothing is typed, pasted, or recorded; no permission is needed.
"""

from __future__ import annotations

import argparse
import signal
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from clipflow.models.hotkey import DEFAULT_HOTKEY, Hotkey
from clipflow.platform.hotkey import HotkeyError, create_hotkey_backend
from clipflow.services.hotkey_manager import HotkeyManager


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", metavar="SHORTCUT")
    group.add_argument("--listen", metavar="SHORTCUT", nargs="?", const=DEFAULT_HOTKEY.to_text())
    parser.add_argument("--seconds", type=float, default=60)
    args = parser.parse_args()

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv[:1])
    try:
        hotkey = Hotkey.parse(args.check or args.listen)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2
    started = time.monotonic()
    manager = HotkeyManager(
        create_hotkey_backend(),
        lambda: print(
            f"[{time.monotonic() - started:6.1f}s] {hotkey.display()} pressed", flush=True
        ),
    )
    problem = manager.problem(hotkey)
    if args.check:
        verdict = problem or "can be used (other apps' shortcuts can't be checked)"
        print(f"{hotkey.display()}: {verdict}")
        return 1 if problem else 0
    try:
        manager.activate(hotkey)
    except HotkeyError as exc:
        print(f"Couldn't register {hotkey.display()}: {exc}", file=sys.stderr)
        return 1
    print(
        f"Listening for {hotkey.display()} for {args.seconds:.0f} s. Switch to another app "
        "and press it; each press prints a line. Ctrl+C stops.",
        flush=True,
    )
    signal.signal(signal.SIGINT, signal.SIG_DFL)  # Ctrl+C ends the probe (and its shortcut)
    QTimer.singleShot(int(args.seconds * 1000), app.quit)
    app.exec()
    manager.stop()
    print("Stopped; shortcut released.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
