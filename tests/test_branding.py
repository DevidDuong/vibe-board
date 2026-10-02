"""The app is shown as "Vibe-Board" (formerly ClipFlow) while its storage keeps the old
folder names, so libraries created before the rename are still found."""

from __future__ import annotations

import ast
from pathlib import Path

from clipflow import APP_NAME
from clipflow.app import ClipFlowController
from clipflow.config import DATA_DIR_ENV, STORAGE_NAME, default_paths
from clipflow.ui.command_editor import SECRET_NOTE
from clipflow.ui.settings_dialog import privacy_text
from fakes import FakeClipboard

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "clipflow"


def test_display_name():
    assert APP_NAME == "Vibe-Board"


def test_existing_library_and_logs_are_still_found(monkeypatch):
    monkeypatch.delenv(DATA_DIR_ENV, raising=False)
    paths = default_paths()
    assert paths.data_dir == Path.home() / "Library" / "Application Support" / "ClipFlow"
    assert paths.log_dir == Path.home() / "Library" / "Logs" / "ClipFlow"
    assert STORAGE_NAME == "ClipFlow" != APP_NAME  # renaming the app must not move the data


def test_window_title_and_visible_text_use_display_name(qtbot, conn):
    ctl = ClipFlowController(conn, FakeClipboard(), use_tray=False)
    qtbot.addWidget(ctl.window)
    assert ctl.window.windowTitle() == APP_NAME
    assert APP_NAME in ctl.window.accessibleName()
    assert APP_NAME in SECRET_NOTE
    assert privacy_text(Path("/tmp/x.sqlite3")).startswith(f"{APP_NAME} never reads")
    ctl.shutdown()


def _docstring_nodes(tree: ast.AST) -> set[int]:
    nodes = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                nodes.add(id(body[0].value))
    return nodes


def test_old_name_is_not_hardcoded_in_any_user_visible_string():
    offenders = []
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstrings = _docstring_nodes(tree)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and "ClipFlow" in node.value
                and id(node) not in docstrings
            ):
                offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}: {node.value!r}")
    # The only allowed literal is the storage folder name.
    assert offenders == [f"src/clipflow/config.py:{_storage_line()}: 'ClipFlow'"]


def _storage_line() -> int:
    for number, line in enumerate((SRC / "config.py").read_text().splitlines(), start=1):
        if line.startswith("STORAGE_NAME ="):
            return number
    raise AssertionError("STORAGE_NAME not found")


def test_bundle_is_named_after_display_name():
    spec = (ROOT / "packaging" / "ClipFlow.spec").read_text()
    assert "from clipflow import APP_NAME" in spec
    assert 'name=f"{APP_NAME}.app"' in spec
    assert '"CFBundleName": APP_NAME' in spec and '"CFBundleDisplayName": APP_NAME' in spec
