"""Render ClipFlow's UI states to PNG files for visual review.

    python scripts/render_ui_states.py [output_dir]      # default: ./ui-review (git-ignored)

Uses a throwaway database with sample commands and renders with ``WA_DontShowOnScreen`` +
``QWidget.grab()``: nothing appears on screen, no screen-recording permission is needed,
your real library and clipboard are never touched (copies go to a no-op writer).
Native window chrome (traffic lights, unified title bar) is not captured; check that live.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QWidget

from clipflow.app import ClipFlowController
from clipflow.models.command import CommandDraft
from clipflow.models.preferences import UiPreferences
from clipflow.repositories.database import open_database

SAMPLES = [
    ("Show listening ports", "lsof -iTCP -sTCP:LISTEN -n -P", "Which process owns it", "Network"),
    (
        "Compress old logs",
        'find . -name "*.log" -mtime +7 -print0 |\n  xargs -0 gzip -9\necho "done"\n'
        "# cleanup temp\nrm -f *.tmp",
        "Run from the log directory",
        "Shell",
    ),
    ("Pretty git graph", "git log --oneline --graph --decorate --all", "", "Git"),
    ("Rebuild containers", "docker compose down &&\n  docker compose up -d --build", "", "Docker"),
    ("Disk usage by folder", "du -sh * | sort -h", "", ""),
]


class _NoClipboard:
    def write_text(self, text: str) -> None:
        pass


class _PreviewHotkeys:
    """Lets the Settings screenshot show the shortcut section without registering anything."""

    def system_conflict(self, hotkey: object) -> None:
        return None

    def register(self, hotkey: object, callback: object) -> object:
        return type("Registration", (), {"unregister": lambda self: None})()


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "ui-review").resolve()
    out.mkdir(parents=True, exist_ok=True)
    app = QApplication(sys.argv[:1])
    scratch = Path(tempfile.mkdtemp(prefix="clipflow-ui-"))

    def settle() -> None:
        for _ in range(5):
            app.processEvents()

    def offscreen(widget: QWidget, size: tuple[int, int] | None = None) -> None:
        widget.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
        if size:
            widget.resize(*size)
        widget.show()
        settle()

    def shot(widget: QWidget, name: str) -> None:
        settle()
        widget.grab().save(str(out / f"{name}.png"))

    def controller(name: str, *, seed: bool) -> ClipFlowController:
        ctl = ClipFlowController(
            open_database(scratch / name),
            _NoClipboard(),
            use_tray=False,
            hotkey_backend=_PreviewHotkeys(),
        )
        if seed:
            for title, command, description, category in SAMPLES:
                saved = ctl.commands.create(CommandDraft(title, command, description, category))
                if title == "Compress old logs":
                    ctl.commands.set_pinned(saved.id, True)
        ctl.refresh()
        return ctl

    for mode in ("dark", "light"):
        ctl = controller(f"{mode}.sqlite3", seed=True)
        ctl.save_preferences(UiPreferences(theme=mode, unified_title_bar=False))
        offscreen(ctl.window, (820, 620))
        ctl.window.list.select_row(0)
        ctl.window.list.setFocus()
        shot(ctl.window, f"{mode}-wide")
        ctl.window.resize(480, 620)
        shot(ctl.window, f"{mode}-narrow")
        ctl.window.resize(820, 620)
        ctl.copy_command(ctl.window.current_id())
        shot(ctl.window, f"{mode}-copied")
        editor = ctl.open_editor(ctl.window.current_id())
        offscreen(editor)
        shot(editor, f"{mode}-editor")
        editor.saved_command = editor.saved_command or ctl.commands.get(ctl.window.current_id())
        editor.reject()
        settings = ctl.open_settings()
        offscreen(settings)
        shot(settings, f"{mode}-settings")
        settings.reject()
        ctl.window.search.setText("no such command")
        shot(ctl.window, f"{mode}-no-matches")

        empty = controller(f"{mode}-empty.sqlite3", seed=False)
        empty.save_preferences(UiPreferences(theme=mode, unified_title_bar=False))
        offscreen(empty.window, (820, 560))
        shot(empty.window, f"{mode}-empty")
        empty.window.show_error("Could not load commands (OperationalError)")
        shot(empty.window, f"{mode}-error")

    print(f"Wrote {len(list(out.glob('*.png')))} images to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
