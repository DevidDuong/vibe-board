"""Measure the palette's title-bar area on every connected display (real macOS windows).

    python scripts/window_probe.py                 # human-readable report
    python scripts/window_probe.py --json          # one JSON object per case (used by tests)
    python scripts/window_probe.py --shots DIR     # also save window screenshots

Shows the window briefly in blended and standard title-bar modes, dark and light themes, on
each display, using a throwaway database (never your library). For each case it reports the
title-bar height macOS uses, where the header starts, and the gap between them.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
os.environ["CLIPFLOW_DATA_DIR"] = tempfile.mkdtemp(prefix="vibe-window-probe-")

from PySide6.QtCore import QPoint, QTimer  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from clipflow.app import ClipFlowController  # noqa: E402
from clipflow.models.command import CommandDraft  # noqa: E402
from clipflow.models.preferences import UiPreferences  # noqa: E402
from clipflow.repositories.database import open_database  # noqa: E402

CASES = [(mode, theme) for mode in ("blended", "standard") for theme in ("dark", "light")]


class _NoClipboard:
    def write_text(self, text: str) -> None:
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--shots", type=Path)
    args = parser.parse_args()

    app = QApplication(sys.argv[:1])
    if app.platformName() != "cocoa":
        print("This probe needs the macOS (cocoa) platform.", file=sys.stderr)
        return 2
    conn = open_database(Path(os.environ["CLIPFLOW_DATA_DIR"]) / "probe.sqlite3")
    ctl = ClipFlowController(conn, _NoClipboard(), use_tray=False)
    ctl.commands.create(CommandDraft("Sample", "echo one\necho two", "demo", "Shell"))
    ctl.start()
    window = ctl.window
    queue = [(s, mode, theme) for s in QGuiApplication.screens() for mode, theme in CASES]
    results: list[dict] = []

    def run_next() -> None:
        if not queue:
            app.quit()
            return
        screen, mode, theme = queue.pop(0)
        window.hide()
        ctl.save_preferences(UiPreferences(theme=theme, unified_title_bar=mode == "blended"))
        area = screen.availableGeometry()
        window.move(area.left() + 40, area.top() + 40)
        window.show()
        window.raise_()
        QTimer.singleShot(900, lambda: measure(screen, mode, theme))

    def measure(screen, mode, theme) -> None:
        handle = window.windowHandle()
        header_y = window.header.mapTo(window, QPoint(0, 0)).y()
        safe_top = handle.safeAreaMargins().top()
        result = {
            "display": screen.name(),
            "scale": screen.devicePixelRatio(),
            "mode": mode,
            "theme": theme,
            "title_bar_inset": safe_top,
            "header_y": header_y,
            "gap_below_title_bar": header_y - safe_top,
        }
        results.append(result)
        if args.shots:
            args.shots.mkdir(parents=True, exist_ok=True)
            name = f"{screen.name()}-{mode}-{theme}".replace(" ", "_")
            window.grab().save(str(args.shots / f"{name}.png"))
        if args.json:
            print(json.dumps(result), flush=True)
        else:
            print(
                f"{result['display']:24} @{result['scale']:.0f}x {mode:8} {theme:5} "
                f"title bar {safe_top:2} pt, header at {header_y:2} pt, "
                f"gap {result['gap_below_title_bar']:2} pt",
                flush=True,
            )
        run_next()

    QTimer.singleShot(300, run_next)
    app.exec()
    ctl.shutdown()
    conn.close()
    return 0 if len(results) == len(CASES) * len(QGuiApplication.screens()) else 1


if __name__ == "__main__":
    sys.exit(main())
