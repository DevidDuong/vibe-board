"""Window placement: pure geometry rules, the remembered-geometry store, and the controller
(open on the active display, remember size/position, recover from bad or stale positions)."""

from __future__ import annotations

import json

import pytest
from PySide6.QtCore import QMargins, QPoint, QRect, QSize
from PySide6.QtGui import QGuiApplication

from clipflow.app import ClipFlowController
from clipflow.models.window_state import WindowState
from clipflow.repositories.window_state_repository import KEY, WindowStateRepository
from clipflow.ui.palette_window import DEFAULT_SIZE, MINIMUM_SIZE
from clipflow.ui.placement import SCREEN_MARGIN, default_position, outer_size, place_window
from fakes import FakeClipboard

RETINA = QRect(0, 25, 1512, 957)  # built-in display below a 25 pt menu bar
EXTERNAL_RIGHT = QRect(1512, 0, 2560, 1415)
EXTERNAL_LEFT = QRect(-1920, 0, 1920, 1055)
NO_FRAME = QMargins()
TITLE_BAR = QMargins(0, 28, 0, 0)
DEFAULT = QSize(*DEFAULT_SIZE)
MINIMUM = QSize(*MINIMUM_SIZE)


def place(saved, available, frame=NO_FRAME):
    return place_window(
        saved=saved, available=available, frame=frame, default_size=DEFAULT, minimum=MINIMUM
    )


def outer(placement, frame=NO_FRAME):
    return QRect(placement.position, outer_size(placement.size, frame))


# -- pure rules ------------------------------------------------------------------------------


def test_first_open_is_centred_in_upper_part_of_active_display():
    placement = place(None, RETINA)
    rect = outer(placement)
    assert placement.size == DEFAULT and not placement.remembered
    assert abs(rect.center().x() - RETINA.center().x()) <= 1
    assert RETINA.top() < rect.top() < RETINA.top() + RETINA.height() // 3
    assert RETINA.contains(rect)


def test_valid_remembered_position_and_size_are_reused():
    saved = WindowState(300, 200, 700, 520)
    placement = place(saved, RETINA)
    assert placement.remembered
    assert (placement.position, placement.size) == (QPoint(300, 200), QSize(700, 520))


@pytest.mark.parametrize(
    "saved",
    [
        WindowState(5000, 300, 700, 520),  # on a monitor that's gone
        WindowState(-3000, 100, 700, 520),
        WindowState(1300, 200, 700, 520),  # partly off the right edge
        WindowState(300, 900, 700, 520),  # partly below the display
        WindowState(300, 0, 700, 520),  # under the menu bar
    ],
)
def test_invalid_or_partly_offscreen_position_falls_back_to_active_display(saved):
    placement = place(saved, RETINA)
    assert not placement.remembered
    assert placement.size == QSize(700, 520)  # size is still remembered
    assert RETINA.contains(outer(placement))
    expected = default_position(outer_size(QSize(700, 520), NO_FRAME), RETINA)
    assert placement.position == expected


def test_disconnected_external_monitor_position_is_not_reused():
    # Saved while on the external display to the right; that display is now unplugged.
    saved = WindowState(2000, 300, 780, 600)
    assert place(saved, EXTERNAL_RIGHT).remembered  # still valid while it's connected
    placement = place(saved, RETINA)
    assert not placement.remembered and RETINA.contains(outer(placement))


def test_displays_left_of_primary_with_negative_coordinates():
    saved = WindowState(-1500, 100, 780, 600)
    assert place(saved, EXTERNAL_LEFT).remembered
    assert EXTERNAL_LEFT.contains(outer(place(None, EXTERNAL_LEFT)))


def test_lower_resolution_shrinks_remembered_size_but_keeps_minimum():
    small = QRect(0, 25, 1024, 615)
    placement = place(WindowState(10, 30, 1400, 900), small)
    assert placement.size.width() <= small.width() - 2 * SCREEN_MARGIN
    assert placement.size.height() <= small.height() - 2 * SCREEN_MARGIN
    assert placement.size.width() >= MINIMUM.width() and placement.size.height() >= MINIMUM.height()
    assert not placement.remembered and small.contains(outer(placement))


def test_standard_title_bar_frame_is_kept_on_screen():
    placement = place(WindowState(300, 400, 780, 560), RETINA, TITLE_BAR)
    rect = outer(placement, TITLE_BAR)
    assert RETINA.contains(rect)
    # The same client size without a frame would have fitted; with the title bar it must not
    # overflow the bottom.
    assert rect.bottom() <= RETINA.bottom()


@pytest.mark.parametrize("x", range(-4000, 6000, 997))
@pytest.mark.parametrize("y", range(-2000, 3000, 811))
def test_result_is_always_fully_visible(x, y):
    for display in (RETINA, EXTERNAL_RIGHT, EXTERNAL_LEFT):
        placement = place(WindowState(x, y, 780, 600), display, TITLE_BAR)
        assert display.contains(outer(placement, TITLE_BAR))


# -- remembered-geometry store -----------------------------------------------------------------


def test_window_state_round_trip_and_bad_values(conn):
    repo = WindowStateRepository(conn)
    assert repo.load() is None
    repo.save(WindowState(10, 20, 700, 500))
    assert repo.load() == WindowState(10, 20, 700, 500)
    for bad in (
        '"nope"',
        "{bad json",
        json.dumps({"x": 1}),
        json.dumps({"x": 1, "y": 2, "width": 0, "height": 10}),
        json.dumps({"x": 1.5, "y": 2, "width": 10, "height": 10}),
    ):
        conn.execute("UPDATE app_settings SET value = ? WHERE key = ?", (bad, KEY))
        assert repo.load() is None


def test_window_state_touches_only_its_own_key(conn):
    conn.execute("INSERT INTO app_settings (key, value) VALUES ('recording_consent', 'true')")
    WindowStateRepository(conn).save(WindowState(1, 2, 500, 400))
    rows = dict(conn.execute("SELECT key, value FROM app_settings"))
    assert rows["recording_consent"] == "true" and set(rows) == {"recording_consent", KEY}


# -- controller ------------------------------------------------------------------------------


def start(qtbot, conn):
    ctl = ClipFlowController(conn, FakeClipboard(), use_tray=False)
    qtbot.addWidget(ctl.window)
    ctl.start()
    qtbot.waitUntil(lambda: not ctl.window._loading)
    return ctl


def screen_rect() -> QRect:
    return QGuiApplication.primaryScreen().availableGeometry()


def frame_rect(ctl) -> QRect:
    return ctl.window.frameGeometry()


def test_opens_fully_visible_on_active_display_and_keeps_search_focus(qtbot, conn):
    ctl = start(qtbot, conn)
    ctl.show_window()
    qtbot.waitExposed(ctl.window)
    assert screen_rect().contains(frame_rect(ctl))
    assert ctl.window.focusWidget() is ctl.window.search
    ctl.shutdown()


def test_size_and_position_are_remembered_across_restart(qtbot, conn):
    ctl = start(qtbot, conn)
    ctl.show_window()
    ctl.window.resize(600, 500)
    ctl.window.move(40, 60)
    ctl.hide_window()
    assert WindowStateRepository(conn).load() == WindowState(40, 60, 600, 500)
    ctl.shutdown()

    ctl = start(qtbot, conn)
    ctl.show_window()
    assert (ctl.window.x(), ctl.window.y(), ctl.window.width(), ctl.window.height()) == (
        40,
        60,
        600,
        500,
    )
    ctl.shutdown()


def test_invalid_stored_position_is_recovered(qtbot, conn):
    WindowStateRepository(conn).save(WindowState(99_000, -50_000, 600, 450))
    ctl = start(qtbot, conn)
    ctl.show_window()
    assert screen_rect().contains(frame_rect(ctl))
    assert ctl.window.size() == QSize(600, 450)
    ctl.shutdown()


def test_window_pushed_offscreen_by_display_change_is_brought_back(qtbot, conn):
    ctl = start(qtbot, conn)
    ctl.show_window()
    ctl.window.move(screen_rect().right() - 100, screen_rect().bottom() - 50)  # mostly off
    assert not screen_rect().contains(frame_rect(ctl))
    ctl.keep_window_on_screen()
    assert screen_rect().contains(frame_rect(ctl))
    ctl._on_screens_changed()  # the signal path schedules the same check
    qtbot.wait(10)
    assert screen_rect().contains(frame_rect(ctl))
    ctl.shutdown()


def test_minimum_size_and_breakpoints_preserved(qtbot, conn):
    WindowStateRepository(conn).save(WindowState(10, 10, 100, 100))  # below minimum
    ctl = start(qtbot, conn)
    ctl.show_window()
    assert ctl.window.width() >= MINIMUM.width() and ctl.window.height() >= MINIMUM.height()
    ctl.shutdown()
