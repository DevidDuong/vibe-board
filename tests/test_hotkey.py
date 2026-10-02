"""Global shortcut: model, preferences, manager (registration, conflicts, rollback),
recorder widget, Settings flow, and the show/hide behaviour of the controller."""

from __future__ import annotations

import json
import logging

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from clipflow.app import ClipFlowController
from clipflow.models.command import CommandDraft
from clipflow.models.hotkey import (
    DEFAULT_HOTKEY,
    KEY_NAMES,
    MAC_KEY_CODES,
    RESERVED,
    Hotkey,
    validation_problem,
)
from clipflow.models.preferences import UiPreferences
from clipflow.platform.hotkey import HotkeyError
from clipflow.repositories.preferences_repository import PreferencesRepository
from clipflow.services.hotkey_manager import HotkeyManager
from clipflow.ui.hotkey_edit import HotkeyEdit
from fakes import FakeClipboard, FakeHotkeyBackend

CUSTOM = Hotkey.of("K", "ctrl", "option", "cmd")
OTHER = Hotkey.of("J", "ctrl", "shift", "cmd")

# -- model ---------------------------------------------------------------------------------


def test_default_hotkey_is_ctrl_option_cmd_v_and_valid():
    assert DEFAULT_HOTKEY.display() == "⌃⌥⌘V"
    assert DEFAULT_HOTKEY.to_text() == "ctrl+option+cmd+V"
    assert Hotkey.of("V", "shift", "cmd") != DEFAULT_HOTKEY  # never ⌘⇧V
    assert validation_problem(DEFAULT_HOTKEY) is None


@pytest.mark.parametrize("text", ["ctrl+option+cmd+V", "shift+cmd+Space", "ctrl+cmd+F19"])
def test_parse_round_trip(text):
    assert Hotkey.parse(text).to_text() == text


def test_parse_normalises_order_and_case():
    assert Hotkey.parse("cmd+ctrl+v").to_text() == "ctrl+cmd+V"
    assert Hotkey.parse("option+cmd+space").display() == "⌥⌘Space"


@pytest.mark.parametrize(
    "text", ["", "V", "ctrl+", "ctrl+ctrl+V", "hyper+V", "ctrl+Tab", "ctrl+cmd+Enter"]
)
def test_parse_rejects_malformed(text):
    with pytest.raises(ValueError):
        Hotkey.parse(text)


@pytest.mark.parametrize(
    "hotkey",
    [
        Hotkey.of("C", "cmd"),  # would break ⌘C everywhere
        Hotkey.of("C", "ctrl"),  # Terminal interrupt
        Hotkey.of("Space", "option"),  # option-only
        Hotkey.of("V", "option", "shift"),  # option+shift only
        Hotkey.of("V", "shift"),
    ],
)
def test_validation_requires_cmd_or_ctrl_plus_another_modifier(hotkey):
    assert "⌘ or ⌃ plus at least one more modifier" in validation_problem(hotkey)


def test_reserved_shortcuts_are_refused_with_reason():
    assert "Paste and Match Style" in validation_problem(Hotkey.of("V", "shift", "cmd"))
    assert "screenshot" in validation_problem(Hotkey.of("4", "shift", "cmd"))
    assert all(validation_problem(h) for h in RESERVED)


def test_every_supported_key_has_a_mac_key_code():
    assert set(KEY_NAMES) == set(MAC_KEY_CODES)
    assert len(set(MAC_KEY_CODES.values())) == len(MAC_KEY_CODES)


# -- preferences -----------------------------------------------------------------------------


def test_hotkey_preference_persists(conn):
    repo = PreferencesRepository(conn)
    assert repo.load().global_hotkey() == DEFAULT_HOTKEY
    repo.save(UiPreferences(hotkey=CUSTOM.to_text()))
    assert repo.load().global_hotkey() == CUSTOM
    repo.save(UiPreferences(hotkey_enabled=False, hotkey=CUSTOM.to_text()))
    loaded = repo.load()
    assert loaded.global_hotkey() is None and loaded.hotkey == CUSTOM.to_text()


def test_unreadable_stored_hotkey_falls_back_to_default(conn):
    conn.execute(
        "INSERT INTO app_settings (key, value) VALUES ('ui.hotkey', ?)", (json.dumps("cmd+??"),)
    )
    assert PreferencesRepository(conn).load().global_hotkey() == DEFAULT_HOTKEY


# -- manager -------------------------------------------------------------------------------


def make_manager(**backend_options):
    backend = FakeHotkeyBackend(**backend_options)
    pressed = []
    return HotkeyManager(backend, lambda: pressed.append(True)), backend, pressed


def test_valid_registration_path():
    manager, backend, pressed = make_manager()
    manager.activate(DEFAULT_HOTKEY)
    assert manager.active == DEFAULT_HOTKEY and DEFAULT_HOTKEY in backend.registered
    backend.press(DEFAULT_HOTKEY)
    assert pressed == [True]


def test_conflict_with_macos_shortcut_is_refused_before_registering():
    manager, backend, _ = make_manager(system_taken={CUSTOM: "used by macOS"})
    with pytest.raises(HotkeyError, match="used by macOS"):
        manager.activate(CUSTOM)
    assert backend.history == [] and manager.active is None


def test_registration_failure_keeps_previous_shortcut():
    manager, backend, _ = make_manager(refuse={CUSTOM})
    manager.activate(DEFAULT_HOTKEY)
    with pytest.raises(HotkeyError):
        manager.activate(CUSTOM)
    assert manager.active == DEFAULT_HOTKEY
    assert set(backend.registered) == {DEFAULT_HOTKEY}


def test_switching_registers_new_before_releasing_old():
    manager, backend, _ = make_manager()
    manager.activate(DEFAULT_HOTKEY)
    manager.activate(CUSTOM)
    assert backend.history == [
        ("register", DEFAULT_HOTKEY),
        ("register", CUSTOM),
        ("unregister", DEFAULT_HOTKEY),
    ]


def test_turning_off_and_invalid_input():
    manager, backend, _ = make_manager()
    manager.activate(DEFAULT_HOTKEY)
    manager.activate(None)
    assert manager.active is None and backend.registered == {}
    with pytest.raises(HotkeyError):
        manager.activate(Hotkey.of("C", "cmd"))
    assert manager.problem(DEFAULT_HOTKEY) is None


# -- recorder widget -------------------------------------------------------------------------


def test_recorder_captures_combination(qtbot):
    edit = HotkeyEdit(DEFAULT_HOTKEY)
    qtbot.addWidget(edit)
    recorded = []
    edit.recorded.connect(recorded.append)
    qtbot.mouseClick(edit, Qt.MouseButton.LeftButton)
    assert edit.recording and edit.text() == "Press shortcut…"
    # On macOS Qt reports ⌘ as Control and ⌃ as Meta.
    mods = (
        Qt.KeyboardModifier.ControlModifier
        | Qt.KeyboardModifier.MetaModifier
        | Qt.KeyboardModifier.ShiftModifier
    )
    qtbot.keyClick(edit, Qt.Key.Key_J, mods)
    assert recorded == [OTHER] and edit.text() == "⌃⇧⌘J" and not edit.recording


def test_recorder_escape_cancels_and_keeps_previous(qtbot):
    edit = HotkeyEdit(DEFAULT_HOTKEY)
    qtbot.addWidget(edit)
    edit.start_recording()
    qtbot.keyClick(edit, Qt.Key.Key_Escape)
    assert not edit.recording and edit.hotkey == DEFAULT_HOTKEY and edit.text() == "⌃⌥⌘V"


# -- controller + settings -----------------------------------------------------------------


@pytest.fixture
def backend():
    return FakeHotkeyBackend()


@pytest.fixture
def ctl(qtbot, conn, backend):
    controller = ClipFlowController(conn, FakeClipboard(), use_tray=False, hotkey_backend=backend)
    qtbot.addWidget(controller.window)
    controller.start()
    qtbot.waitUntil(lambda: not controller.window._loading)
    yield controller
    controller.shutdown()


def test_startup_registers_default(ctl, backend):
    assert ctl.hotkeys.active == DEFAULT_HOTKEY and DEFAULT_HOTKEY in backend.registered
    assert not ctl.window.banner.isVisibleTo(ctl.window)


def test_startup_conflict_shows_persistent_error(qtbot, conn, caplog):
    taken = FakeHotkeyBackend(refuse={DEFAULT_HOTKEY})
    with caplog.at_level(logging.WARNING, logger="clipflow"):
        ctl = ClipFlowController(conn, FakeClipboard(), use_tray=False, hotkey_backend=taken)
        qtbot.addWidget(ctl.window)
        ctl.start()
        qtbot.waitUntil(lambda: not ctl.window._loading)
    banner = ctl.window.banner
    assert banner.isVisibleTo(ctl.window)
    assert "⌃⌥⌘V isn't active" in banner.text.text() and "Settings" in banner.text.text()
    ctl.window.search.setText("x")  # refreshes must not silently clear the problem
    assert banner.isVisibleTo(ctl.window)
    banner._dismiss()
    ctl.window.search.setText("")
    assert not banner.isVisibleTo(ctl.window)  # dismissed stays dismissed
    assert "unavailable" in caplog.text
    ctl.shutdown()


def test_hotkey_toggles_window_and_focuses_search(ctl, backend, qtbot):
    ctl.hide_window()
    backend.press(DEFAULT_HOTKEY)
    qtbot.waitUntil(ctl.window.isVisible)
    qtbot.waitUntil(ctl.window.isActiveWindow)
    assert ctl.window.focusWidget() is ctl.window.search
    backend.press(DEFAULT_HOTKEY)
    qtbot.waitUntil(lambda: not ctl.window.isVisible())


def test_hotkey_never_hides_an_open_editor(ctl, backend, qtbot):
    ctl.show_window()
    editor = ctl.open_editor()
    editor.title_edit.setText("unsaved")
    backend.press(DEFAULT_HOTKEY)
    qtbot.wait(20)
    assert ctl.window.isVisible() and editor.isVisible()
    assert editor.title_edit.text() == "unsaved"
    editor.saved_command = object()
    editor.reject()


def test_hotkey_never_touches_clipboard_or_commands(qtbot, conn, backend):
    clipboard = FakeClipboard()
    ctl = ClipFlowController(conn, clipboard, use_tray=False, hotkey_backend=backend)
    qtbot.addWidget(ctl.window)
    ctl.start()
    qtbot.waitUntil(lambda: not ctl.window._loading)
    ctl.commands.create(CommandDraft("t", "echo hi"))
    for _ in range(4):
        backend.press(DEFAULT_HOTKEY)
        qtbot.wait(10)
    assert clipboard.writes == [] and clipboard.read_calls == 0
    assert ctl.commands.count() == 1
    ctl.shutdown()


def open_settings(ctl):
    dialog = ctl.open_settings()
    assert dialog.hotkey_edit.text() == ctl.hotkeys.active.display()
    return dialog


def test_settings_change_registers_new_and_persists(ctl, backend, conn, qtbot):
    dialog = open_settings(ctl)
    dialog.hotkey_edit.set_hotkey(CUSTOM)
    dialog._check_hotkey()
    assert "available" in dialog.hotkey_status.text()
    qtbot.mouseClick(dialog.save_button, Qt.MouseButton.LeftButton)
    assert not dialog.isVisible()
    assert ctl.hotkeys.active == CUSTOM and set(backend.registered) == {CUSTOM}
    assert PreferencesRepository(conn).load().global_hotkey() == CUSTOM


def test_settings_conflict_keeps_previous_and_saves_nothing(qtbot, conn):
    backend = FakeHotkeyBackend(system_taken={CUSTOM: "used by macOS"}, refuse={OTHER})
    ctl = ClipFlowController(conn, FakeClipboard(), use_tray=False, hotkey_backend=backend)
    qtbot.addWidget(ctl.window)
    ctl.start()
    qtbot.waitUntil(lambda: not ctl.window._loading)
    dialog = open_settings(ctl)
    dialog.hotkey_edit.set_hotkey(CUSTOM)
    dialog._check_hotkey()
    assert "used by macOS" in dialog.hotkey_status.text()  # detected before saving
    assert not dialog.attempt_save()
    assert dialog.isVisible() and "used by macOS" in dialog.save_error.text()
    dialog.hotkey_edit.set_hotkey(OTHER)  # passes checks, but the OS refuses it
    assert not dialog.attempt_save()
    assert "⌃⌥⌘V still works" in dialog.save_error.text()
    assert ctl.hotkeys.active == DEFAULT_HOTKEY and set(backend.registered) == {DEFAULT_HOTKEY}
    assert (
        conn.execute("SELECT COUNT(*) FROM app_settings WHERE key = 'ui.hotkey'").fetchone()[0] == 0
    )
    dialog.reject()
    ctl.shutdown()


def test_storage_failure_rolls_back_to_previous_shortcut(ctl, backend, conn, monkeypatch):
    from clipflow.repositories.database import StorageError

    def fail(_prefs):
        raise StorageError("Could not save preferences (OperationalError)")

    monkeypatch.setattr(ctl._preferences_repo, "save", fail)
    dialog = open_settings(ctl)
    dialog.hotkey_edit.set_hotkey(CUSTOM)
    assert not dialog.attempt_save()
    assert "Nothing was changed" in dialog.save_error.text()
    assert ctl.hotkeys.active == DEFAULT_HOTKEY and set(backend.registered) == {DEFAULT_HOTKEY}
    dialog.reject()


def test_reset_to_default_and_turning_off(ctl, backend, conn, qtbot):
    ctl.apply_settings(UiPreferences(hotkey=CUSTOM.to_text()))
    dialog = open_settings(ctl)
    qtbot.mouseClick(dialog.reset_hotkey_button, Qt.MouseButton.LeftButton)
    assert dialog.hotkey_edit.hotkey == DEFAULT_HOTKEY
    dialog.hotkey_enabled.setChecked(False)
    assert dialog.hotkey_status.text() == "The global shortcut is off."
    assert dialog.attempt_save()
    assert ctl.hotkeys.active is None and backend.registered == {}
    loaded = PreferencesRepository(conn).load()
    assert not loaded.hotkey_enabled and loaded.hotkey == DEFAULT_HOTKEY.to_text()


def test_hotkey_while_settings_open_does_not_hide(ctl, backend, qtbot):
    dialog = open_settings(ctl)
    backend.press(DEFAULT_HOTKEY)
    qtbot.wait(20)
    assert dialog.isVisible() and ctl.window.isVisible()
    dialog.reject()


def test_shutdown_releases_the_shortcut(qtbot, conn, backend):
    ctl = ClipFlowController(conn, FakeClipboard(), use_tray=False, hotkey_backend=backend)
    qtbot.addWidget(ctl.window)
    ctl.start()
    qtbot.waitUntil(lambda: ctl.hotkeys.active is not None)
    ctl.shutdown()
    assert backend.registered == {}
    assert QApplication.instance() is not None
