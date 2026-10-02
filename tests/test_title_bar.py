"""Title-bar regression tests.

Root cause of the old ~30 pt blank band: with the blended title bar Qt already insets the
content by the title bar (window safe area), and the palette added its *own* spacer of the
same height on top. The palette must therefore never add a title-bar spacer itself.

The structural checks run everywhere. The real-window measurement shows windows on screen,
so it only runs when CLIPFLOW_GUI_TESTS=1 (see tests/manual_macos_checklist.md).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from PySide6.QtCore import Qt

from clipflow.app import ClipFlowController
from clipflow.ui.theme import SPACE_2, SPACE_3
from fakes import FakeClipboard

ROOT = Path(__file__).resolve().parent.parent


def test_no_title_bar_spacer_and_qt_safe_area_respected(qtbot, conn):
    ctl = ClipFlowController(conn, FakeClipboard(), use_tray=False)
    qtbot.addWidget(ctl.window)
    window = ctl.window
    assert window.testAttribute(Qt.WidgetAttribute.WA_ContentsMarginsRespectsSafeArea)
    assert window.layout().itemAt(0).widget() is window.header  # nothing above the header
    assert not hasattr(window, "title_strip")
    assert window.layout().contentsMargins().top() == SPACE_3  # standard mode
    ctl.shutdown()


@pytest.mark.macos
@pytest.mark.skipif(
    sys.platform != "darwin" or os.environ.get("CLIPFLOW_GUI_TESTS") != "1",
    reason="shows real windows; set CLIPFLOW_GUI_TESTS=1 to run",
)
def test_real_window_header_sits_just_below_the_title_bar():
    env = {k: v for k, v in os.environ.items() if k != "QT_QPA_PLATFORM"}
    run = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "window_probe.py"), "--json"],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
        check=False,
    )
    results = [json.loads(line) for line in run.stdout.splitlines() if line.startswith("{")]
    assert run.returncode == 0 and results, run.stderr[-2000:]
    for r in results:
        if r["mode"] == "blended":
            assert r["title_bar_inset"] > 0  # content really extends under the title bar
            assert r["gap_below_title_bar"] == SPACE_2, r
        else:
            assert r["title_bar_inset"] == 0 and r["header_y"] == SPACE_3, r
