"""Security guarantees: no clipboard monitoring or reads, no command execution, no network,
no content in logs, and legacy history preserved but isolated."""

from __future__ import annotations

import ast
import importlib.util
import logging
import os
import re
import subprocess
from pathlib import Path

import pytest
from PySide6.QtCore import QProcess, Qt, QTimer

from clipflow.app import ClipFlowController
from clipflow.repositories.database import open_database
from fakes import LEGACY_ROWS, FakeClipboard, dump_legacy, make_legacy_v1_db

SRC = Path(__file__).resolve().parent.parent / "src" / "clipflow"
SOURCES = sorted(SRC.rglob("*.py"))


def _source_text() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in SOURCES)


# -- clipboard monitoring is gone --------------------------------------------------------


@pytest.mark.parametrize(
    "module",
    [
        "clipflow.services.clipboard_monitor",
        "clipflow.services.history_service",
        "clipflow.services.retention_service",
        "clipflow.ui.onboarding_dialog",
        "clipflow.repositories.settings_repository",
    ],
)
def test_recording_modules_no_longer_exist(module):
    assert importlib.util.find_spec(module) is None


@pytest.mark.parametrize(
    "token",
    [
        "changeCount",
        "stringForType",
        "dataForType",
        "propertyListForType",
        "readObjectsForClasses",
        "pasteboardItems",
        "availableTypeFromArray",
        "QClipboard",
        ".clipboard()",
        "mimeData",
        "recording_consent",
        "zsh_history",
    ],
)
def test_source_contains_no_clipboard_read_apis(token):
    assert token not in _source_text()


def test_clipboard_adapter_is_write_only():
    from clipflow.platform.macos_clipboard import MacClipboardWriter

    public = {name for name in dir(MacClipboardWriter) if not name.startswith("_")}
    assert public == {"write_text"}


# -- commands are data, never executed; no network ------------------------------------


FORBIDDEN_MODULES = {
    "subprocess",
    "pty",
    "multiprocessing",
    "shlex",
    "socket",
    "ssl",
    "urllib",
    "http",
    "ftplib",
    "smtplib",
    "requests",
    "webbrowser",
}
FORBIDDEN_OS_CALLS = {"system", "popen", "posix_spawn", "posix_spawnp", "fork", "forkpty"}


def test_no_execution_or_network_imports_or_calls():
    for path in SOURCES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
                if node.module == "PySide6.QtNetwork":
                    imported = {alias.name for alias in node.names}
                    assert imported <= {"QLocalServer", "QLocalSocket"}, path
                    assert path.name == "single_instance.py"
            else:
                names = []
            for name in names:
                assert name.split(".")[0] not in FORBIDDEN_MODULES, (path, name)
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                if node.value.id == "os":
                    attr = node.attr
                    assert attr not in FORBIDDEN_OS_CALLS, (path, attr)
                    assert not attr.startswith(("exec", "spawn")), (path, attr)
                assert node.attr not in {"start", "startDetached"} or node.value.id != "QProcess"
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in {"eval", "exec", "compile"}, path
    assert "QProcess" not in _source_text()


@pytest.fixture
def execution_traps(monkeypatch):
    calls: list[str] = []

    def trap(name):
        def _raise(*_args, **_kwargs):
            calls.append(name)
            raise AssertionError(f"{name} must never be called")

        return _raise

    monkeypatch.setattr(subprocess, "Popen", trap("subprocess.Popen"))
    for name in ("system", "popen", "execv", "execve", "execvp", "spawnv", "posix_spawn"):
        if hasattr(os, name):
            monkeypatch.setattr(os, name, trap(f"os.{name}"))
    monkeypatch.setattr(QProcess, "start", trap("QProcess.start"))
    monkeypatch.setattr(QProcess, "startDetached", trap("QProcess.startDetached"))
    return calls


def test_dangerous_commands_are_stored_and_copied_as_inert_text(
    qtbot, conn, tmp_path, execution_traps
):
    marker = tmp_path / "pwned"
    dangerous = f'touch {marker} && rm -rf "$HOME/does-not-exist" ; $(touch {marker})\n`id`'
    clipboard = FakeClipboard()
    ctl = ClipFlowController(conn, clipboard, use_tray=False)
    qtbot.addWidget(ctl.window)
    ctl.start()
    qtbot.waitUntil(lambda: not ctl.window._loading)

    dialog = ctl.open_editor()
    dialog.title_edit.setText("Dangerous")
    dialog.command_edit.setPlainText(dangerous)
    qtbot.mouseClick(dialog.save_button, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(ctl.window.copy_button, Qt.MouseButton.LeftButton)
    qtbot.keyClicks(ctl.window.search, "touch")
    edit = ctl.open_editor(ctl.window.current_id())
    edit.reject()
    ctl.shutdown()

    assert clipboard.writes == [dangerous]
    assert ctl.commands.list_commands()[0].command == dangerous
    assert not marker.exists()
    assert execution_traps == []


# -- lifecycle: never records, nothing polls, legacy preferences are inert ---------------


def _start(qtbot, db_path, clipboard):
    conn = open_database(db_path)
    ctl = ClipFlowController(conn, clipboard, use_tray=False)
    qtbot.addWidget(ctl.window)
    ctl.start()
    qtbot.waitUntil(lambda: not ctl.window._loading)
    return conn, ctl


def test_launch_and_restart_never_enable_recording_or_polling(qtbot, db_path):
    make_legacy_v1_db(db_path)  # includes recording_consent=true from the old build
    clipboard = FakeClipboard()
    for _ in range(2):  # launch, then restart
        conn, ctl = _start(qtbot, db_path, clipboard)
        ctl.show_window()
        qtbot.wait(1200)  # longer than the old 500 ms polling interval
        active = [
            t for owner in (ctl, ctl.window) for t in owner.findChildren(QTimer) if t.isActive()
        ]
        assert active == []
        assert not hasattr(ctl, "monitor")
        ctl.shutdown()
        conn.close()
    assert clipboard.read_calls == 0
    assert clipboard.writes == []


def test_legacy_history_preserved_and_never_displayed(qtbot, db_path):
    make_legacy_v1_db(db_path)
    before = dump_legacy(db_path)
    clipboard = FakeClipboard()
    conn, ctl = _start(qtbot, db_path, clipboard)
    assert ctl.commands.count() == 0
    assert "empty" in ctl.window.empty.title.text()
    model = ctl.window.list.command_model
    for content, _pinned in LEGACY_ROWS:
        qtbot.keyClicks(ctl.window.search, "legacy-entry")
        assert model.rowCount() == 0
        ctl.window.search.clear()
        assert all(content not in str(model.index(i).data()) for i in range(model.rowCount()))
    ctl.shutdown()
    conn.close()
    assert dump_legacy(db_path) == before


def test_command_contents_never_logged(qtbot, conn, caplog):
    with caplog.at_level(logging.DEBUG, logger="clipflow"):
        clipboard = FakeClipboard()
        ctl = ClipFlowController(conn, clipboard, use_tray=False)
        qtbot.addWidget(ctl.window)
        ctl.start()
        qtbot.waitUntil(lambda: not ctl.window._loading)
        dialog = ctl.open_editor()
        dialog.title_edit.setText("title-marker-k")
        dialog.command_edit.setPlainText("command-marker-k\nline2")
        qtbot.mouseClick(dialog.save_button, Qt.MouseButton.LeftButton)
        qtbot.mouseClick(ctl.window.copy_button, Qt.MouseButton.LeftButton)
        qtbot.keyClicks(ctl.window.search, "search-marker-k")
        ctl.shutdown()
    assert "copied to clipboard" in caplog.text
    assert "marker-k" not in caplog.text


# -- portability: macOS APIs stay behind platform adapters ------------------------------


def test_appkit_is_only_imported_by_macos_platform_modules():
    native = {"AppKit", "Foundation", "objc", "Quartz", "Cocoa"}
    for path in SOURCES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [(node.module or "").split(".")[0]]
            else:
                continue
            if native & set(names):
                assert path.parent.name == "platform" and path.name.startswith("macos_"), path


def test_shared_ui_and_services_do_not_import_macos_adapters_at_module_level():
    for folder in ("ui", "services", "models", "repositories"):
        for path in (SRC / folder).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in tree.body:  # module-level imports only
                if isinstance(node, ast.ImportFrom) and node.module:
                    assert "macos_clipboard" not in node.module, path


# -- global shortcut: registration only, never input simulation or monitoring -------------


@pytest.mark.parametrize(
    "token",
    [
        "CGEventPost",  # posting synthetic keyboard/mouse events
        "CGEventCreateKeyboardEvent",
        "CGEventTapCreate",  # event taps (Input Monitoring)
        "addGlobalMonitorForEvents",  # NSEvent global monitors (Accessibility)
        "addLocalMonitorForEvents",
        "AXUIElement",  # Accessibility API
        "AXIsProcessTrusted",
        "NSAppleScript",  # app/terminal automation
        "osascript",  # (also covers AppleScript "keystroke", which needs one of these)
        "IOHIDManager",  # raw keyboard access
        "CGRequestScreenCaptureAccess",  # Screen Recording
        "CGWindowListCreateImage",
    ],
)
def test_no_input_simulation_monitoring_or_automation_apis(token):
    assert token not in _source_text()


def test_hotkey_backend_only_registers_a_key_combination():
    source = (SRC / "platform" / "macos_hotkey.py").read_text()
    carbon_calls = set(re.findall(r"(?:lib|_carbon\(\))\.(\w+)\(", source))
    assert carbon_calls == {
        "CopySymbolicHotKeys",  # read macOS's own shortcut list (conflict check)
        "GetApplicationEventTarget",
        "InstallEventHandler",  # receive *our* hot-key events only
        "RegisterEventHotKey",
        "UnregisterEventHotKey",
        "GetEventParameter",
    }
