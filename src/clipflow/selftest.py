"""Packaged-app self-test: ``Vibe-Board.app/Contents/MacOS/Vibe-Board --self-test``.

Exercises the core flows inside whatever runtime launched it — most usefully the frozen
PyInstaller bundle — so a build can be checked without Accessibility permission or UI
scripting. Safety rules:

* Refuses to run unless ``CLIPFLOW_DATA_DIR`` points at a directory other than the real
  library location, so it can never read or modify the user's commands.
* Nothing is shown on screen (``WA_DontShowOnScreen``) and focus is never taken.
* Copies go to a private, uniquely named pasteboard, never the general clipboard, and the
  pasteboard is never read.
* Writes ``selftest/report.json`` and screenshots into the throwaway data directory.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable
from pathlib import Path

from clipflow import APP_NAME
from clipflow.config import DATA_DIR_ENV, STORAGE_NAME, default_paths, setup_logging

MULTILINE = 'for f in *.log; do\n\tgzip -9 "$f"\ndone\n'
FAKE_TOKEN = "ghp_" + "Selftest" * 5  # synthetic; must trigger the secret warning


def _real_data_dir() -> Path:
    return (Path.home() / "Library" / "Application Support" / STORAGE_NAME).resolve()


def _guard() -> Path | None:
    override = os.environ.get(DATA_DIR_ENV)
    if not override:
        return None
    data_dir = Path(override).expanduser().resolve()
    return None if data_dir == _real_data_dir() else data_dir


class _RecordingWriter:
    """Writes through the real AppKit adapter (private pasteboard) and remembers the text."""

    def __init__(self, inner: object) -> None:
        self._inner = inner
        self.writes: list[str] = []

    def write_text(self, text: str) -> None:
        self._inner.write_text(text)
        self.writes.append(text)


def run_self_test(argv: list[str]) -> int:
    data_dir = _guard()
    if data_dir is None:
        print(
            f"Refusing to run: set {DATA_DIR_ENV} to a throwaway directory "
            f"(never your real {APP_NAME} library).",
            file=sys.stderr,
        )
        return 2

    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFontDatabase, QGuiApplication
    from PySide6.QtWidgets import QApplication, QSystemTrayIcon

    from clipflow.app import ClipFlowController
    from clipflow.models.command import CommandDraft
    from clipflow.models.preferences import UiPreferences
    from clipflow.repositories.database import open_database

    paths = default_paths()
    setup_logging(paths)
    out = data_dir / "selftest"
    out.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication(argv)
    results: list[dict[str, object]] = []

    def check(name: str, condition: Callable[[], object]) -> None:
        try:
            ok = bool(condition())
            error = None
        except Exception as exc:  # report, keep going
            ok, error = False, type(exc).__name__
        results.append({"check": name, "ok": ok, **({"error": error} if error else {})})

    def settle() -> None:
        for _ in range(5):
            app.processEvents()

    release_pasteboard = None
    if sys.platform == "darwin":
        # Proves PyObjC/AppKit load in this runtime; writes go to a private pasteboard.
        from clipflow.platform.macos_clipboard import private_pasteboard_writer

        inner, release_pasteboard = private_pasteboard_writer()
        writer = _RecordingWriter(inner)
    else:
        writer = _RecordingWriter(type("Null", (), {"write_text": lambda self, t: None})())

    check("frozen bundle" if getattr(sys, "frozen", False) else "source run", lambda: True)
    check("Qt platform plugin loaded", lambda: QGuiApplication.platformName() != "")
    check("menu-bar (system tray) available", QSystemTrayIcon.isSystemTrayAvailable)
    check("system fonts available", lambda: len(QFontDatabase.families()) > 10)
    check(
        "fixed-pitch font resolves",
        lambda: QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont).family() != "",
    )

    conn = open_database(paths.database)
    ctl = ClipFlowController(conn, writer, use_tray=False)
    window = ctl.window
    window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    window.resize(820, 620)
    window.show()
    ctl.start()
    settle()
    check("Fusion style + theme stylesheet applied", lambda: bool(app.styleSheet()))
    check("empty state shown", lambda: "empty" in window.empty.title.text())

    # Add (only persists on Save)
    editor = ctl.open_editor()
    editor.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    editor.title_edit.setText("Compress logs")
    editor.command_edit.setPlainText(MULTILINE)
    editor.category_edit.setCurrentText("Shell")
    check("nothing saved before Save", lambda: ctl.commands.count() == 0)
    editor.save_button.click()
    settle()
    saved = ctl.commands.list_commands()
    check("add command", lambda: len(saved) == 1 and saved[0].command == MULTILINE)
    command_id = saved[0].id if saved else -1

    # Secret warning: Go Back keeps it unsaved
    editor = ctl.open_editor()
    editor.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    editor.title_edit.setText("Token")
    editor.command_edit.setPlainText(f"gh auth login --with-token {FAKE_TOKEN}")
    editor.confirm_secret_warning = lambda _error: False
    editor.save_button.click()
    check("secret warning blocks silent save", lambda: ctl.commands.count() == 1)
    editor.saved_command = object()  # skip the discard prompt
    editor.reject()

    # Edit, pin, search, filter
    editor = ctl.open_editor(command_id)
    editor.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    editor.command_edit.setPlainText(MULTILINE + "echo edited\n")
    editor.save_button.click()
    settle()
    check("edit command", lambda: ctl.commands.get(command_id).command.endswith("edited\n"))
    ctl.commands.create(CommandDraft("Disk usage", "du -sh * | sort -h", "", ""))
    ctl.set_pinned(command_id, True)
    check("pin command", lambda: ctl.commands.get(command_id).is_pinned)
    window.search.setText("SORT -H")
    settle()
    check("search", lambda: window.list.command_model.rowCount() == 1)
    window.search.clear()
    shell = next(f for f in window.filter_bar.filters() if f.category == "Shell")
    window.filter_bar.select(shell)
    settle()
    check("category filter", lambda: window.list.command_model.rowCount() == 1)
    window.filter_bar.select(window.filter_bar.filters()[0])
    settle()

    # Copy (private pasteboard only) and confirmation
    window.select_command(command_id)
    window.copy_button.click()
    settle()
    check("copy writes exact text", lambda: writer.writes[-1].endswith("echo edited\n"))
    check("copy confirmation visible", lambda: window.toast.isVisible())
    window.grab().save(str(out / "packaged-system-theme.png"))

    # Settings: persisted and applied
    dialog = ctl.open_settings()
    dialog.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    dialog.theme_combo.setCurrentIndex(dialog.theme_combo.findData("dark"))
    dialog.save_button.click()
    settle()
    check("settings saved", lambda: ctl.preferences.theme == "dark")
    check("dark theme applied", lambda: window.theme.is_dark)
    window.grab().save(str(out / "packaged-dark.png"))

    # Delete (with confirmation)
    other = next(c.id for c in ctl.commands.list_commands() if c.id != command_id)
    window.select_command(other)
    window.confirm_delete = lambda _title: True
    window.delete_button.click()
    settle()
    check("delete command", lambda: ctl.commands.get(other) is None)

    # Window placement: remembered when hidden, fully on-screen when reopened
    window.move(-50_000, -50_000)  # simulate a position on a display that no longer exists
    ctl.hide_window()
    window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    ctl.show_window("self-test")
    settle()
    screens = QGuiApplication.screens()
    check(
        "window placement recovers an off-screen position",
        lambda: any(s.availableGeometry().contains(window.frameGeometry()) for s in screens),
    )

    # Global shortcut backend (packaged Carbon adapter). Uses an obscure probe combination,
    # never the user's shortcut, and releases it immediately.
    if sys.platform == "darwin":
        from clipflow.models.hotkey import Hotkey
        from clipflow.platform.hotkey import create_hotkey_backend

        backend = create_hotkey_backend()
        probe = Hotkey.of("F19", "ctrl", "option", "shift", "cmd")

        def register_and_release() -> bool:
            registration = backend.register(probe, lambda: None)
            registration.unregister()
            return True

        check("global shortcut: Carbon registration works", register_and_release)
        check(
            "global shortcut: macOS shortcut conflicts detected",
            lambda: (
                backend.system_conflict(Hotkey.of("Space", "cmd")) is not None
                or backend.system_conflict(Hotkey.of("Space", "option", "cmd")) is not None
            ),
        )

    # Restart: data and preferences persist
    ctl.shutdown()
    conn.close()
    conn = open_database(paths.database)
    ctl = ClipFlowController(conn, writer, use_tray=False)
    ctl.refresh()
    check("data persists across restart", lambda: ctl.commands.get(command_id) is not None)
    check(
        "preferences persist across restart", lambda: ctl.preferences == UiPreferences(theme="dark")
    )
    check("window size remembered across restart", lambda: ctl._window_state is not None)
    check("database stored outside the app bundle", lambda: ".app/" not in str(paths.database))
    ctl.shutdown()
    conn.close()
    if release_pasteboard is not None:
        release_pasteboard()

    passed = all(r["ok"] for r in results)
    report = {
        "passed": passed,
        "frozen": bool(getattr(sys, "frozen", False)),
        "executable": sys.executable,
        "data_dir": str(data_dir),
        "results": results,
    }
    (out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    for r in results:
        print(
            f"{'PASS' if r['ok'] else 'FAIL'}  {r['check']}"
            + (f" ({r['error']})" if "error" in r else "")
        )
    passed_count = sum(bool(r["ok"]) for r in results)
    print(f"Self-test {'PASSED' if passed else 'FAILED'}: {passed_count}/{len(results)}")
    return 0 if passed else 1
