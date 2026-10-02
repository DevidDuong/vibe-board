"""Packaged-app support: self-test guard and run, lifecycle (reactivation, graceful quit
signals), and the bundle verifier's forbidden-file scan."""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import signal
import sys
from pathlib import Path

import pytest
from PySide6.QtCore import QObject, Qt

from clipflow import app as app_module
from clipflow.app import ClipFlowController
from clipflow.config import DATA_DIR_ENV
from clipflow.selftest import run_self_test
from fakes import FakeClipboard

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def restore_logging():
    logger = logging.getLogger("clipflow")
    state = (list(logger.handlers), logger.level, logger.propagate)
    yield
    for handler in logger.handlers:
        handler.close()
    logger.handlers[:], logger.level, logger.propagate = state[0], state[1], state[2]


# -- self-test ---------------------------------------------------------------------------


def test_self_test_refuses_without_throwaway_data_dir(monkeypatch, capsys):
    monkeypatch.delenv(DATA_DIR_ENV, raising=False)
    assert run_self_test(["ClipFlow", "--self-test"]) == 2
    real = Path.home() / "Library" / "Application Support" / "ClipFlow"
    monkeypatch.setenv(DATA_DIR_ENV, str(real))
    assert run_self_test(["ClipFlow", "--self-test"]) == 2
    assert "Refusing to run" in capsys.readouterr().err


def test_self_test_runs_core_flows(qapp, tmp_path, monkeypatch, restore_logging):
    monkeypatch.setenv(DATA_DIR_ENV, str(tmp_path / "selftest-data"))
    run_self_test(["ClipFlow", "--self-test"])
    report = json.loads((tmp_path / "selftest-data" / "selftest" / "report.json").read_text())
    failed = [r["check"] for r in report["results"] if not r["ok"]]
    # The offscreen test platform has no menu bar; everything else must pass.
    assert failed in ([], ["menu-bar (system tray) available"])
    assert len(report["results"]) >= 20
    assert (tmp_path / "selftest-data" / "selftest" / "packaged-dark.png").exists()


def test_main_dispatches_self_test(monkeypatch):
    called = []
    monkeypatch.setattr("clipflow.selftest.run_self_test", lambda argv: called.append(argv) or 7)
    assert app_module.main(["ClipFlow", "--self-test"]) == 7
    assert called


# -- lifecycle ---------------------------------------------------------------------------


@pytest.fixture
def controller(qtbot, conn):
    ctl = ClipFlowController(conn, FakeClipboard(), use_tray=False)
    qtbot.addWidget(ctl.window)
    ctl.start()
    yield ctl
    ctl.shutdown()


def test_reactivation_shows_hidden_window(controller):
    controller.window.hide()
    controller._on_app_state_changed(Qt.ApplicationState.ApplicationInactive)
    assert not controller.window.isVisible()
    controller._on_app_state_changed(Qt.ApplicationState.ApplicationActive)
    assert controller.window.isVisible()


def test_hide_window_hides_palette(controller):
    controller.show_window()
    controller.hide_window()  # hide_app() is a no-op off Cocoa
    assert not controller.window.isVisible()


class _StubApp(QObject):
    def __init__(self) -> None:
        super().__init__()
        self.quits = 0

    def quit(self) -> None:
        self.quits += 1


@pytest.mark.parametrize("signum", [signal.SIGTERM, signal.SIGINT])
def test_quit_signals_quit_gracefully(qtbot, signum):
    previous = {s: signal.getsignal(s) for s in (signal.SIGTERM, signal.SIGINT)}
    stub = _StubApp()
    try:
        app_module._install_quit_signals(stub)
        os.kill(os.getpid(), signum)
        qtbot.waitUntil(lambda: stub.quits == 1, timeout=2000)
    finally:
        signal.set_wakeup_fd(-1)
        for s, handler in previous.items():
            signal.signal(s, handler)


# -- bundle verifier -----------------------------------------------------------------------


def _load_verifier():
    spec = importlib.util.spec_from_file_location(
        "verify_bundle", ROOT / "packaging" / "verify_bundle.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["verify_bundle"] = module
    spec.loader.exec_module(module)
    return module


def test_verifier_flags_user_data_logs_secrets_and_tests(tmp_path):
    verifier = _load_verifier()
    bundle = tmp_path / "ClipFlow.app" / "Contents"
    resources = bundle / "Resources"
    resources.mkdir(parents=True)
    for name in ("clipflow.sqlite3", "clipflow.sqlite3-wal", "clipflow.log", ".env", "id_rsa"):
        (resources / name).write_text("x")
    (resources / "tests").mkdir()
    (resources / "ok.py").write_text("x")
    (resources / "libqcocoa.dylib").write_text("x")
    hits = {p.name for p in verifier.forbidden_files(tmp_path / "ClipFlow.app")}
    assert hits == {
        "clipflow.sqlite3",
        "clipflow.sqlite3-wal",
        "clipflow.log",
        ".env",
        "id_rsa",
        "tests",
    }


def test_spec_and_verifier_agree_on_bundle_identity():
    spec_text = (ROOT / "packaging" / "ClipFlow.spec").read_text()
    verifier = _load_verifier()
    assert f'BUNDLE_ID = "{verifier.EXPECTED_BUNDLE_ID}"' in spec_text
    assert 'target_arch="arm64"' in spec_text
    assert "datas=[]" in spec_text  # no data files bundled
    assert "LSUIElement" in spec_text and "SMLoginItem" not in spec_text
