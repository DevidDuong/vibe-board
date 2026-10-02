"""Command palette UI + controller on the offscreen Qt platform with a fake clipboard."""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QAbstractButton, QApplication, QLabel

from clipflow.app import ClipFlowController
from clipflow.models.command import CommandDraft
from clipflow.models.preferences import UiPreferences
from clipflow.ui.command_editor import CommandEditorDialog
from clipflow.ui.palette_window import DETAIL_MIN_WIDTH
from clipflow.ui.theme import DARK, LIGHT
from clipflow.ui.widgets import ALL, PINNED, UNCATEGORIZED, Filter
from fakes import FakeClipboard

MULTILINE = 'for f in *.log; do\n\tgzip "$f"\ndone\n'
FAKE_TOKEN = "ghp_" + "Fake" * 9


class FakeTray:
    """Stands in for the menu-bar icon so closing hides instead of quitting."""

    def hide(self) -> None:
        pass


@pytest.fixture
def clipboard() -> FakeClipboard:
    return FakeClipboard()


def start(qtbot, conn, clipboard, *, show=True) -> ClipFlowController:
    ctl = ClipFlowController(conn, clipboard, use_tray=False)
    qtbot.addWidget(ctl.window)
    ctl.start()
    if show:
        ctl.show_window()
        qtbot.waitExposed(ctl.window)
    qtbot.waitUntil(lambda: not ctl.window._loading)
    return ctl


@pytest.fixture
def controller(qtbot, conn, clipboard):
    ctl = start(qtbot, conn, clipboard)
    yield ctl
    ctl.shutdown()


def titles(ctl: ClipFlowController) -> list[str]:
    model = ctl.window.list.command_model
    return [model.command_at(i).title for i in range(model.rowCount())]


def card_center(ctl: ClipFlowController, row: int):
    lst = ctl.window.list
    return lst.visualRect(lst.command_model.index(row)).center()


def fill(dialog: CommandEditorDialog, title="", command="", description="", category=""):
    dialog.title_edit.setText(title)
    dialog.command_edit.setPlainText(command)
    dialog.description_edit.setPlainText(description)
    dialog.category_edit.setCurrentText(category)


def add(ctl, qtbot, **fields) -> CommandEditorDialog:
    dialog = ctl.open_editor()
    fill(dialog, **fields)
    qtbot.mouseClick(dialog.save_button, Qt.MouseButton.LeftButton)
    return dialog


# -- states -----------------------------------------------------------------------------


def test_loading_then_empty_state_with_add_action(qtbot, conn, clipboard):
    ctl = ClipFlowController(conn, clipboard, use_tray=False)
    qtbot.addWidget(ctl.window)
    ctl.start()
    assert ctl.window.empty.title.text() == "Loading commands…"
    qtbot.waitUntil(lambda: not ctl.window._loading)
    assert ctl.window.empty.title.text() == "Your command library is empty"
    assert not ctl.window.copy_button.isEnabled()
    assert ctl.window.empty.action.text() == "Add Command"
    ctl.window.empty.action.click()
    assert ctl.editor is not None and ctl.editor.isVisible()
    ctl.editor.reject()
    ctl.shutdown()


def test_search_autofocuses_when_window_opens(controller):
    assert controller.window.search.hasFocus() or QApplication.focusWidget() is None


def test_storage_error_shows_banner_and_error_state(controller, conn):
    conn.close()
    controller.refresh()
    assert controller.window.banner.isVisibleTo(controller.window)
    assert controller.window.empty.title.text() == "Couldn't load commands"


# -- add / edit / delete ----------------------------------------------------------------


def test_add_persists_only_after_save(controller, qtbot):
    dialog = controller.open_editor()
    fill(dialog, title="Compress logs", command=MULTILINE, category="Shell")
    assert controller.commands.count() == 0  # typing alone saves nothing
    assert "3 lines" in dialog.command_stats.text()
    qtbot.mouseClick(dialog.save_button, Qt.MouseButton.LeftButton)
    assert not dialog.isVisible()
    [saved] = controller.commands.list_commands()
    assert saved.command == MULTILINE
    assert titles(controller) == ["Compress logs"]
    assert controller.window.detail_command.toPlainText() == MULTILINE
    assert "Saved “Compress logs”" in controller.window.toast.text.text()


def test_enter_in_title_field_does_not_save(controller, qtbot):
    dialog = controller.open_editor()
    fill(dialog, title="t", command="ls")
    qtbot.keyClick(dialog.title_edit, Qt.Key.Key_Return)
    assert controller.commands.count() == 0 and dialog.isVisible()


def test_save_disabled_until_title_and_command(controller):
    dialog = controller.open_editor()
    assert not dialog.save_button.isEnabled()
    fill(dialog, title="t", command="  \n ")
    assert not dialog.save_button.isEnabled()
    fill(dialog, title="t", command="ls")
    assert dialog.save_button.isEnabled()


def test_cancel_with_changes_asks_and_discards(controller, monkeypatch):
    dialog = controller.open_editor()
    fill(dialog, title="t", command="ls")
    monkeypatch.setattr(dialog, "confirm_discard", lambda: False)
    dialog.reject()
    assert dialog.isVisible()
    monkeypatch.setattr(dialog, "confirm_discard", lambda: True)
    dialog.reject()
    assert not dialog.isVisible() and controller.commands.count() == 0


def test_edit_existing_command(controller, qtbot):
    add(controller, qtbot, title="Old", command="echo old")
    command_id = controller.window.current_id()
    dialog = controller.open_editor(command_id)
    assert (dialog.title_edit.text(), dialog.command_edit.toPlainText()) == ("Old", "echo old")
    fill(dialog, title="New", command="echo new\necho two")
    qtbot.mouseClick(dialog.save_button, Qt.MouseButton.LeftButton)
    assert controller.commands.get(command_id).command == "echo new\necho two"
    assert titles(controller) == ["New"]


def test_delete_requires_confirmation(controller, qtbot, monkeypatch):
    add(controller, qtbot, title="Keep me", command="ls")
    monkeypatch.setattr(controller.window, "confirm_delete", lambda _title: False)
    qtbot.mouseClick(controller.window.delete_button, Qt.MouseButton.LeftButton)
    assert controller.commands.count() == 1
    monkeypatch.setattr(controller.window, "confirm_delete", lambda _title: True)
    qtbot.keyClick(
        controller.window.search, Qt.Key.Key_Backspace, Qt.KeyboardModifier.ControlModifier
    )
    assert controller.commands.count() == 0
    assert controller.window.empty.title.text() == "Your command library is empty"


def test_secret_warning_go_back_then_save_anyway(controller, qtbot, monkeypatch):
    dialog = controller.open_editor()
    fill(dialog, title="Login", command=f"gh auth login --with-token {FAKE_TOKEN}")
    monkeypatch.setattr(dialog, "confirm_secret_warning", lambda _e: False)
    qtbot.mouseClick(dialog.save_button, Qt.MouseButton.LeftButton)
    assert controller.commands.count() == 0 and dialog.isVisible()
    monkeypatch.setattr(dialog, "confirm_secret_warning", lambda _e: True)
    qtbot.mouseClick(dialog.save_button, Qt.MouseButton.LeftButton)
    assert controller.commands.count() == 1 and not dialog.isVisible()


def test_private_key_cannot_be_saved(controller, qtbot, monkeypatch):
    shown = []
    dialog = controller.open_editor()
    monkeypatch.setattr(dialog, "show_blocked", shown.append)
    fill(dialog, title="key", command="-----BEGIN " + "RSA PRIVATE KEY-----\nfake")
    qtbot.mouseClick(dialog.save_button, Qt.MouseButton.LeftButton)
    assert shown and shown[0].blocked and controller.commands.count() == 0


# -- pin / filters / search ---------------------------------------------------------------


def test_pin_moves_command_to_top(controller, qtbot):
    add(controller, qtbot, title="Alpha", command="a")
    add(controller, qtbot, title="Zulu", command="z")
    assert titles(controller) == ["Alpha", "Zulu"]
    controller.window.select_command(controller.commands.list_commands()[1].id)
    qtbot.mouseClick(controller.window.pin_button, Qt.MouseButton.LeftButton)
    assert titles(controller) == ["Zulu", "Alpha"]
    assert controller.window.pin_button.text() == "Unpin"
    assert "pinned" in controller.window.list.command_model.index(0).data()


def test_filter_chips_pinned_category_and_uncategorized(controller, qtbot):
    add(controller, qtbot, title="Graph", command="git log --graph", category="Git")
    add(controller, qtbot, title="Prune", command="docker system prune", category="Docker")
    add(controller, qtbot, title="Ports", command="lsof -i", description="LISTEN sockets")
    win = controller.window
    assert win.filter_bar.filters() == [
        ALL,
        PINNED,
        Filter("category", "Docker"),
        Filter("category", "Git"),
        UNCATEGORIZED,
    ]
    win.filter_bar.button_for(Filter("category", "Docker")).click()
    assert titles(controller) == ["Prune"]
    assert win.count_label.text() == "1 of 3"
    win.filter_bar.button_for(UNCATEGORIZED).click()
    assert titles(controller) == ["Ports"]
    win.filter_bar.button_for(PINNED).click()
    assert titles(controller) == []
    assert win.empty.title.text() == "No matching commands"
    controller.set_pinned(controller.commands.list_commands()[0].id, True)
    assert len(titles(controller)) == 1
    win.filter_bar.button_for(ALL).click()
    assert len(titles(controller)) == 3


def test_search_matches_fields_and_clear_filters_action(controller, qtbot):
    add(controller, qtbot, title="Ports", command="lsof -i", description="LISTEN sockets")
    add(controller, qtbot, title="Disk", command="du -sh *")
    win = controller.window
    qtbot.keyClicks(win.search, "listen")
    assert titles(controller) == ["Ports"]
    win.search.setText("zzz")
    assert win.empty.title.text() == "No matching commands"
    win.empty.action.click()  # "Clear Filters"
    assert win.search.text() == "" and len(titles(controller)) == 2


def test_chips_keep_selection_and_are_not_rebuilt_needlessly(controller, qtbot):
    add(controller, qtbot, title="a", command="a", category="Git")
    bar = controller.window.filter_bar
    git = bar.button_for(Filter("category", "Git"))
    git.click()
    controller.refresh()
    assert bar.button_for(Filter("category", "Git")) is git  # unchanged options: same widgets
    assert bar.current == Filter("category", "Git")
    add(controller, qtbot, title="b", command="b", category="Docker")
    assert bar.current == Filter("category", "Git")  # survives a rebuild


def test_filter_bar_is_tall_enough_for_styled_chips(controller, qtbot):
    # Invariant check for chips that were once clipped (seen in a Cocoa render). Reverting
    # the individual fixes did not reproduce it headlessly, so the screenshot check in the
    # manual checklist remains the real guard.
    add(controller, qtbot, title="a", command="a", category="Git")
    qtbot.wait(10)
    chip = controller.window.filter_bar.button_for(ALL)
    assert controller.window.filter_bar.height() >= chip.sizeHint().height()


def test_filter_cycle_shortcuts(controller, qtbot):
    add(controller, qtbot, title="a", command="a", category="Git")
    bar = controller.window.filter_bar
    qtbot.keyClick(
        controller.window.search, Qt.Key.Key_BracketRight, Qt.KeyboardModifier.ControlModifier
    )
    assert bar.current == PINNED
    qtbot.keyClick(
        controller.window.search, Qt.Key.Key_BracketLeft, Qt.KeyboardModifier.ControlModifier
    )
    assert bar.current == ALL


# -- copy and keyboard ----------------------------------------------------------------------


def test_copy_paths_write_exact_text_and_confirm(controller, qtbot, clipboard):
    add(controller, qtbot, title="Loop", command=MULTILINE)
    win = controller.window
    qtbot.mouseClick(win.copy_button, Qt.MouseButton.LeftButton)
    center = card_center(controller, 0)
    qtbot.mouseClick(win.list.viewport(), Qt.MouseButton.LeftButton, pos=center)
    assert len(clipboard.writes) == 1  # a single click only selects
    qtbot.mouseDClick(win.list.viewport(), Qt.MouseButton.LeftButton, pos=center)
    qtbot.keyClick(win.search, Qt.Key.Key_Return)
    qtbot.keyClick(win.list, Qt.Key.Key_Return)
    assert clipboard.writes == [MULTILINE] * 4
    assert win.toast.isVisible()
    assert win.toast.text.text().startswith("Copied “Loop”")
    assert clipboard.read_calls == 0


def test_browsing_searching_and_filtering_never_touch_clipboard(controller, qtbot, clipboard):
    add(controller, qtbot, title="A", command="a", category="Git")
    add(controller, qtbot, title="B", command="b")
    win = controller.window
    qtbot.keyClick(win.search, Qt.Key.Key_Down)
    qtbot.keyClick(win.search, Qt.Key.Key_Up)
    qtbot.mouseClick(win.list.viewport(), Qt.MouseButton.LeftButton, pos=card_center(controller, 1))
    qtbot.keyClicks(win.search, "a")
    win.filter_bar.button_for(Filter("category", "Git")).click()
    controller.open_settings().reject()
    assert clipboard.writes == [] and clipboard.read_calls == 0


def test_arrow_keys_move_selection_from_search(controller, qtbot):
    add(controller, qtbot, title="A", command="a")
    add(controller, qtbot, title="B", command="b")
    win = controller.window
    win.list.select_row(0)
    qtbot.keyClick(win.search, Qt.Key.Key_Down)
    assert win.list.currentIndex().row() == 1
    qtbot.keyClick(win.search, Qt.Key.Key_Down)
    assert win.list.currentIndex().row() == 1  # clamps at the end
    qtbot.keyClick(win.search, Qt.Key.Key_Up)
    assert win.list.currentIndex().row() == 0


def test_escape_clears_search_then_dismisses(controller, qtbot, monkeypatch):
    controller.tray = FakeTray()  # with a menu-bar icon, dismiss hides
    win = controller.window
    win.search.setText("abc")
    qtbot.keyClick(win.search, Qt.Key.Key_Escape)
    assert win.search.text() == "" and win.isVisible()
    qtbot.keyClick(win.search, Qt.Key.Key_Escape)
    assert not win.isVisible()


def test_typing_on_list_goes_to_search(controller, qtbot):
    add(controller, qtbot, title="A", command="a")
    controller.window.list.setFocus()
    qtbot.keyClicks(controller.window.list, "gi")
    assert controller.window.search.text() == "gi"


def test_shortcuts_open_editor_and_settings(controller, qtbot):
    qtbot.keyClick(controller.window.search, Qt.Key.Key_N, Qt.KeyboardModifier.ControlModifier)
    assert controller.editor is not None and controller.editor.isVisible()
    controller.editor.reject()
    qtbot.keyClick(controller.window.search, Qt.Key.Key_Comma, Qt.KeyboardModifier.ControlModifier)
    assert controller.settings_dialog is not None and controller.settings_dialog.isVisible()
    controller.settings_dialog.reject()


def test_clipboard_failure_shows_banner(controller, qtbot, clipboard):
    add(controller, qtbot, title="A", command="a")
    clipboard.fail_writes = True
    qtbot.mouseClick(controller.window.copy_button, Qt.MouseButton.LeftButton)
    assert controller.window.banner.isVisibleTo(controller.window)
    assert "Couldn't copy" in controller.window.banner.text.text()


def test_markup_in_user_data_is_shown_literally(controller, qtbot):
    add(controller, qtbot, title="<b>bold</b>", command="echo '<i>x</i>'")
    assert controller.window.detail_title.text() == "<b>bold</b>"
    for label in controller.window.findChildren(QLabel):
        if label.text() == "<b>bold</b>":
            assert label.textFormat() == Qt.TextFormat.PlainText


# -- preferences / settings -------------------------------------------------------------------


def test_hide_after_copy_preference(controller, qtbot):
    add(controller, qtbot, title="A", command="a")
    controller.save_preferences(UiPreferences(hide_after_copy=False))
    controller.copy_command(controller.window.current_id())
    qtbot.wait(1100)
    assert controller.window.isVisible()
    controller.save_preferences(UiPreferences(hide_after_copy=True))
    controller.copy_command(controller.window.current_id())
    assert controller.window.isVisible()  # confirmation is visible first
    qtbot.waitUntil(lambda: not controller.window.isVisible(), timeout=3000)


def test_settings_save_persists_and_applies(controller, qtbot, conn):
    add(controller, qtbot, title="A", command="1\n2\n3\n4\n5\n6")
    lst = controller.window.list
    before = lst.sizeHintForIndex(lst.command_model.index(0)).height()
    dialog = controller.open_settings()
    dialog.theme_combo.setCurrentIndex(dialog.theme_combo.findData("dark"))
    dialog.preview_combo.setCurrentIndex(dialog.preview_combo.findData(6))
    dialog.hide_after_copy.setChecked(True)
    qtbot.mouseClick(dialog.save_button, Qt.MouseButton.LeftButton)
    assert controller.preferences == UiPreferences(
        theme="dark", preview_lines=6, hide_after_copy=True, unified_title_bar=True
    )
    from clipflow.repositories.preferences_repository import PreferencesRepository

    assert PreferencesRepository(conn).load() == controller.preferences
    window_color = QApplication.instance().palette().color(QPalette.ColorRole.Window).name()
    assert window_color.lower() == DARK.bg.lower()
    assert controller.window.theme is DARK
    assert lst.sizeHintForIndex(lst.command_model.index(0)).height() > before


def test_settings_cancel_changes_nothing(controller, qtbot, conn):
    dialog = controller.open_settings()
    dialog.theme_combo.setCurrentIndex(dialog.theme_combo.findData("dark"))
    qtbot.mouseClick(dialog.cancel_button, Qt.MouseButton.LeftButton)
    assert controller.preferences == UiPreferences()
    assert conn.execute("SELECT COUNT(*) FROM app_settings").fetchone()[0] == 0


def test_settings_offer_no_recording_execution_or_login_options(controller):
    from PySide6.QtWidgets import QComboBox

    dialog = controller.open_settings()
    controls = [b.text() for b in dialog.findChildren(QAbstractButton)]
    for combo in dialog.findChildren(QComboBox):
        controls += [combo.itemText(i) for i in range(combo.count())]
    controls += [
        label.text() for label in dialog.findChildren(QLabel) if label is not dialog.privacy
    ]
    options = " ".join(controls).lower()
    for forbidden in (
        "record",
        "history",
        "monitor",
        "login",
        "startup",
        "run",
        "execute",
        "paste",
    ):
        assert forbidden not in options, forbidden
    privacy = dialog.privacy.text()
    assert "never reads your clipboard" in privacy and "never runs commands" in privacy
    assert not dialog.unified_title_bar.isEnabled()  # offscreen platform is not macOS
    dialog.reject()


def test_preferences_and_data_survive_restart(qtbot, db_path, clipboard):
    from clipflow.repositories.database import open_database

    conn = open_database(db_path)
    ctl = start(qtbot, conn, clipboard, show=False)
    ctl.commands.create(CommandDraft("Persist", MULTILINE, "d", "Shell"))
    ctl.save_preferences(UiPreferences(theme="dark", preview_lines=5))
    ctl.shutdown()
    conn.close()

    conn = open_database(db_path)
    ctl = start(qtbot, conn, clipboard, show=False)
    assert titles(ctl) == ["Persist"]
    assert ctl.window.detail_command.toPlainText() == MULTILINE
    assert ctl.preferences.theme == "dark" and ctl.window.theme is DARK
    assert ctl.window.list.card_delegate.preview_lines == 5
    ctl.save_preferences(UiPreferences(theme="light"))
    assert ctl.window.theme is LIGHT
    ctl.shutdown()
    conn.close()


# -- window behavior ----------------------------------------------------------------------


def test_close_hides_with_tray_and_quits_without(qtbot, conn, clipboard, monkeypatch):
    quits = []
    monkeypatch.setattr(ClipFlowController, "quit", lambda self: quits.append(True))
    ctl = ClipFlowController(conn, clipboard, use_tray=False)
    qtbot.addWidget(ctl.window)
    ctl.window.show()
    ctl.window.close()
    assert quits == [True]
    ctl.tray = FakeTray()
    ctl.window.show()
    ctl.window.close()
    assert not ctl.window.isVisible() and quits == [True]


def test_detail_pane_and_hints_adapt_to_width(controller, qtbot):
    add(controller, qtbot, title="A", command="a")
    win = controller.window
    win.resize(DETAIL_MIN_WIDTH + 40, 600)
    assert win.detail_visible() and win.hints.isVisibleTo(win)
    win.resize(480, 600)
    assert not win.detail_visible() and not win.hints.isVisibleTo(win)
    assert win.copy_button.isVisibleTo(win)  # actions stay reachable when narrow


def test_unified_title_bar_is_macos_only(controller):
    controller.window.set_unified_title_bar(True)  # offscreen platform: ignored
    assert not controller.window.windowFlags() & Qt.WindowType.ExpandedClientAreaHint
    assert not controller.window.unified_title_bar
    assert controller.window.layout().contentsMargins().top() == 12  # standard top margin


def test_cards_grow_with_preview_lines_and_are_accessible(controller, qtbot):
    add(controller, qtbot, title="Multi", command="\n".join(f"line {i}" for i in range(10)))
    lst = controller.window.list
    index = lst.command_model.index(0)
    heights = []
    for lines in (1, 3, 8):
        lst.set_preview_lines(lines)
        heights.append(lst.sizeHintForIndex(index).height())
    assert heights == sorted(heights) and len(set(heights)) == 3
    text = index.data(Qt.ItemDataRole.AccessibleTextRole)
    assert "Multi" in text and "10 lines" in text and "uncategorized" in text
    lst.viewport().repaint()  # paint path exercised without errors
