"""Application wiring: storage, preferences, theme, command palette window, and menu-bar icon.

ClipFlow has no background work. After startup it only reacts to user actions: there is no
clipboard monitor, no polling timer, and no recording mode. The only clipboard operation is
writing a saved command when the user explicitly asks to copy it.
"""

from __future__ import annotations

import contextlib
import logging
import os
import signal
import sqlite3
import sys
import traceback
from collections.abc import Callable
from pathlib import Path
from types import TracebackType

from PySide6.QtCore import QObject, QSize, QSocketNotifier, Qt, QTimer
from PySide6.QtGui import QCursor, QGuiApplication, QScreen
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon, QWidget

from clipflow import APP_NAME, __version__
from clipflow.config import default_paths, setup_logging
from clipflow.models.command import Command, CommandDraft
from clipflow.models.preferences import UiPreferences
from clipflow.models.window_state import WindowState
from clipflow.platform.clipboard import ClipboardWriter
from clipflow.platform.hotkey import GlobalHotkeyBackend, HotkeyError, create_hotkey_backend
from clipflow.platform.macos_app import activate_app, hide_app
from clipflow.repositories.command_repository import CommandRepository
from clipflow.repositories.database import StorageError, open_database
from clipflow.repositories.preferences_repository import PreferencesRepository
from clipflow.repositories.window_state_repository import WindowStateRepository
from clipflow.services.command_service import CommandService
from clipflow.services.hotkey_manager import HotkeyManager
from clipflow.single_instance import SingleInstance, instance_key
from clipflow.ui.command_editor import CommandEditorDialog
from clipflow.ui.icons import app_icon, clipboard_icon
from clipflow.ui.palette_window import DEFAULT_SIZE, PaletteWindow
from clipflow.ui.placement import place_window
from clipflow.ui.settings_dialog import SettingsDialog, SettingsSaveError
from clipflow.ui.theme import ThemeManager

logger = logging.getLogger("clipflow.app")

HIDE_AFTER_COPY_DELAY_MS = 900  # long enough to see the "Copied" confirmation


class ClipFlowController(QObject):
    def __init__(
        self,
        conn: sqlite3.Connection,
        clipboard: ClipboardWriter,
        *,
        use_tray: bool = True,
        hotkey_backend: GlobalHotkeyBackend | None = None,
        parent: QObject | None = None,
    ) -> None:
        """``hotkey_backend`` None disables the global shortcut (tests, unsupported OS)."""
        super().__init__(parent)
        self._clipboard = clipboard
        self._database = Path(conn.execute("PRAGMA database_list").fetchone()[2] or ":memory:")
        self.commands = CommandService(CommandRepository(conn))
        self._preferences_repo = PreferencesRepository(conn)
        self._window_state_repo = WindowStateRepository(conn)
        self._window_state = self._load_window_state()
        self._window_shown = False
        self._hotkey_backend = hotkey_backend
        self.hotkeys = HotkeyManager(
            hotkey_backend or _NoHotkeys(),
            # Leave the OS event handler right away; act from the Qt event loop.
            lambda: QTimer.singleShot(0, self.on_global_hotkey),
        )
        self._hotkey_problem: str | None = None
        self._hotkey_problem_dismissed = False
        self.window = PaletteWindow()
        self.theme = ThemeManager(QApplication.instance())
        self.theme.theme_changed.connect(self.window.set_theme)
        self.editor: CommandEditorDialog | None = None
        self.settings_dialog: SettingsDialog | None = None
        self.tray = self._create_tray() if use_tray else None
        try:
            self.preferences = self._preferences_repo.load()
        except StorageError as exc:
            self.preferences = UiPreferences()
            self.window.show_error(str(exc))
        self._apply_preferences(self.preferences)

        self.window.new_requested.connect(lambda: self.open_editor())
        self.window.edit_requested.connect(self.open_editor)
        self.window.delete_requested.connect(self.delete_command)
        self.window.pin_requested.connect(self.set_pinned)
        self.window.copy_requested.connect(self.copy_command)
        self.window.filters_changed.connect(self.refresh)
        self.window.settings_requested.connect(lambda: self.open_settings())
        self.window.close_requested.connect(self._on_close_requested)
        self.window.error_dismissed.connect(self._on_error_dismissed)
        # Launching ClipFlow again (Spotlight, Finder, Dock) only reactivates the running app;
        # show the palette when that happens so a relaunch is never a silent no-op.
        QApplication.instance().applicationStateChanged.connect(self._on_app_state_changed)
        self.window.quit_requested.connect(self.quit)
        # Keep the window on a usable display when monitors change while it's open.
        gui = QGuiApplication.instance()
        gui.screenAdded.connect(self._on_screen_added)
        gui.screenRemoved.connect(self._on_screens_changed)
        for screen in gui.screens():
            screen.availableGeometryChanged.connect(self._on_screens_changed)

    # -- lifecycle --------------------------------------------------------------------

    def start(self) -> None:
        self.window.set_loading()
        QTimer.singleShot(0, self._initial_load)  # one-shot initial load, not a polling timer

    def _initial_load(self) -> None:
        self._start_hotkey()
        self.refresh()
        with contextlib.suppress(StorageError):  # already shown in the window by refresh()
            logger.info("Library loaded (%d commands)", self.commands.count())

    def shutdown(self) -> None:
        self.hotkeys.stop()
        self._disconnect_app_signals()
        if self.window.isVisible():
            self._remember_window()
        if self.tray is not None:
            self.tray.hide()
        self.window.hide()
        logger.info("%s shut down", APP_NAME)

    def quit(self) -> None:
        QApplication.instance().quit()

    # -- window -----------------------------------------------------------------------

    def show_window(self, reason: str = "user") -> None:
        logger.info("Window shown (%s)", reason)
        if not self.window.isVisible() or not self._on_active_screen():
            self._place_window()
        self._window_shown = True
        self.window.show()
        self.window.raise_()
        if QGuiApplication.platformName() == "cocoa":
            activate_app()
        self.window.activateWindow()
        self.window.focus_search()

    def toggle_window(self) -> None:
        if self.window.isVisible() and self.window.isActiveWindow():
            self.hide_window()
        else:
            self.show_window("menu bar")

    def hide_window(self) -> None:
        """Dismiss the palette and give focus back to the app the user came from."""
        if self.window.isVisible():
            self._remember_window()
        self.window.hide()
        if QGuiApplication.platformName() == "cocoa" and not any(
            w.isVisible() for w in QApplication.topLevelWidgets()
        ):
            hide_app()

    def refresh(self) -> None:
        try:
            self.window.set_filter_options(
                self.commands.categories(),
                has_uncategorized=bool(self.commands.list_commands(category="")),
            )
            selected = self.window.current_filter()
            commands = self.commands.list_commands(
                query=self.window.query(),
                category=selected.category if selected.kind == "category" else None,
                pinned_only=selected.kind == "pinned",
            )
            total = self.commands.count()
        except StorageError as exc:
            self.window.show_error(str(exc))
            self.window.show_load_error("Your commands are still on disk. Try again shortly.")
            return
        self.window.show_error(self._standing_notice())
        self.window.set_commands(commands, total=total)

    # -- user actions -----------------------------------------------------------------

    def open_editor(self, command_id: int | None = None) -> CommandEditorDialog | None:
        """Open the add/edit dialog (window-modal, non-blocking). Saving happens only there."""
        if self.editor is not None and self.editor.isVisible():
            self.editor.raise_()
            return self.editor
        initial: Command | None = None
        try:
            if command_id is not None:
                initial = self.commands.get(command_id)
                if initial is None:
                    self.refresh()
                    return None
            categories = self.commands.categories()
        except StorageError as exc:
            self.window.show_error(str(exc))
            return None
        if not self.window.isVisible():
            self.show_window()

        def save(draft: CommandDraft, acknowledge: bool) -> Command:
            if initial is None:
                return self.commands.create(draft, acknowledge_warnings=acknowledge)
            return self.commands.update(initial.id, draft, acknowledge_warnings=acknowledge)

        dialog = CommandEditorDialog(
            save_handler=save,
            categories=categories,
            initial=initial,
            theme=self.theme.theme,
            parent=self.window,
        )
        dialog.saved.connect(self._on_saved)
        dialog.finished.connect(lambda _result: setattr(self, "editor", None))
        self.editor = dialog
        dialog.open()
        return dialog

    def copy_command(self, command_id: int) -> None:
        """Explicit user action: put the saved text on the clipboard. Never runs or pastes it."""
        try:
            command = self.commands.get(command_id)
        except StorageError as exc:
            self.window.show_error(str(exc))
            return
        if command is None:
            self.refresh()
            return
        try:
            self._clipboard.write_text(command.command)
        except Exception as exc:  # OS boundary: report, never crash
            logger.warning("Clipboard write failed (%s)", type(exc).__name__)
            self.window.show_error("Couldn't copy to the clipboard. Please try again.")
            return
        logger.info("Command %d copied to clipboard", command_id)
        self.window.show_error(None)
        self.window.show_toast(f"Copied “{command.title}” — paste it where you need it")
        if self.preferences.hide_after_copy:
            QTimer.singleShot(HIDE_AFTER_COPY_DELAY_MS, self._hide_after_copy)

    def open_settings(self) -> SettingsDialog:
        if self.settings_dialog is not None and self.settings_dialog.isVisible():
            self.settings_dialog.raise_()
            return self.settings_dialog
        if not self.window.isVisible():
            self.show_window()
        dialog = SettingsDialog(
            self.preferences,
            database=self._database,
            unified_title_bar_supported=QGuiApplication.platformName() == "cocoa",
            save_handler=self.apply_settings,
            hotkey_checker=self.hotkeys.problem,
            hotkey_supported=self._hotkey_backend is not None,
            parent=self.window,
        )
        dialog.finished.connect(lambda _result: setattr(self, "settings_dialog", None))
        self.settings_dialog = dialog
        dialog.open()
        return dialog

    def apply_settings(self, preferences: UiPreferences) -> None:
        """Commit new settings, all or nothing. Raises ``SettingsSaveError``.

        The new global shortcut is registered first; if that fails nothing is saved and the
        previous shortcut stays active. If saving fails, the previous shortcut is restored.
        """
        new = preferences.validated()
        previous = self.hotkeys.active
        if self._hotkey_backend is not None:
            try:
                self.hotkeys.activate(new.global_hotkey())
            except HotkeyError as exc:
                keep = f" {previous.display()} still works." if previous else ""
                raise SettingsSaveError(f"{exc}{keep}") from exc
        try:
            self._preferences_repo.save(new)
        except StorageError as exc:
            if self._hotkey_backend is not None:
                with contextlib.suppress(HotkeyError):
                    self.hotkeys.activate(previous)
            raise SettingsSaveError(f"{exc}. Nothing was changed.") from exc
        self.preferences = new
        self._set_hotkey_problem(None)
        self._apply_preferences(new)

    def save_preferences(self, preferences: UiPreferences) -> None:
        """Programmatic save; problems are shown in the window instead of raised."""
        try:
            self.apply_settings(preferences)
        except SettingsSaveError as exc:
            self.window.show_error(str(exc))

    def on_global_hotkey(self) -> None:
        """Global shortcut: show + focus search when hidden or behind; hide when in front."""
        logger.info("Global shortcut pressed")
        dialog = self.settings_dialog
        modal = QApplication.activeModalWidget()
        if dialog is not None and dialog.isVisible():
            self._bring_to_front(dialog)  # changing settings (maybe the shortcut itself)
        elif modal is not None:
            self._bring_to_front(modal)  # e.g. an editor with unsaved text: never hide it
        elif self.window.isVisible() and self.window.isActiveWindow():
            self.hide_window()
        else:
            self.show_window("global shortcut")

    def set_pinned(self, command_id: int, pinned: bool) -> None:
        self._run_storage_action(lambda: self.commands.set_pinned(command_id, pinned))

    def delete_command(self, command_id: int) -> None:
        self._run_storage_action(lambda: self.commands.delete(command_id))
        self.window.show_toast("Command deleted")

    # -- internals --------------------------------------------------------------------

    def _on_saved(self, command: Command) -> None:
        self.refresh()
        self.window.select_command(command.id)
        self.window.show_toast(f"Saved “{command.title}”")

    # -- global shortcut --------------------------------------------------------------

    def _start_hotkey(self) -> None:
        if self._hotkey_backend is None:
            return
        target = self.preferences.global_hotkey()
        if target is None:
            logger.info("Global shortcut is turned off")
            return
        try:
            self.hotkeys.activate(target)
        except HotkeyError as exc:
            logger.warning("Global shortcut %s unavailable", target.display())
            self._set_hotkey_problem(
                f"The global shortcut {target.display()} isn't active: {exc} "
                "Choose another in Settings."
            )

    def _set_hotkey_problem(self, problem: str | None) -> None:
        self._hotkey_problem = problem
        self._hotkey_problem_dismissed = False
        self.window.show_error(self._standing_notice())

    def _standing_notice(self) -> str | None:
        return None if self._hotkey_problem_dismissed else self._hotkey_problem

    def _on_error_dismissed(self) -> None:
        if self._hotkey_problem:
            self._hotkey_problem_dismissed = True

    def _bring_to_front(self, widget: QWidget) -> None:
        if QGuiApplication.platformName() == "cocoa":
            activate_app()
        widget.raise_()
        widget.activateWindow()

    # -- window placement -------------------------------------------------------------

    def _active_screen(self) -> QScreen | None:
        """The display the user is working on: the one under the mouse pointer."""
        return QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()

    def _on_active_screen(self) -> bool:
        screen = self._active_screen()
        return screen is None or screen.geometry().contains(self.window.frameGeometry().center())

    def _place_window(self) -> None:
        screen = self._active_screen()
        if screen is None:
            return
        placement = place_window(
            saved=self._window_state,
            available=screen.availableGeometry(),
            frame=self.window.frame_margins(),
            default_size=QSize(*DEFAULT_SIZE),
            minimum=self.window.minimumSize(),
        )
        self.window.apply_placement(placement)
        logger.debug("Window placed (remembered position: %s)", placement.remembered)

    def keep_window_on_screen(self) -> None:
        """After a display change, pull a visible window fully back onto a usable display."""
        if not self.window.isVisible():
            return
        frame = self.window.frameGeometry()
        screen = QGuiApplication.screenAt(frame.center()) or self._active_screen()
        if screen is None or screen.availableGeometry().contains(frame):
            return
        placement = place_window(
            saved=self.window.window_state(),
            available=screen.availableGeometry(),
            frame=self.window.frame_margins(),
            default_size=QSize(*DEFAULT_SIZE),
            minimum=self.window.minimumSize(),
        )
        self.window.apply_placement(placement)
        logger.info("Window moved back onto a display")

    def _disconnect_app_signals(self) -> None:
        """App-wide signals outlive this controller; detach so nothing calls into it later."""
        gui = QGuiApplication.instance()
        connections = [
            (gui.applicationStateChanged, self._on_app_state_changed),
            (gui.screenAdded, self._on_screen_added),
            (gui.screenRemoved, self._on_screens_changed),
            *((s.availableGeometryChanged, self._on_screens_changed) for s in gui.screens()),
        ]
        for source, slot in connections:
            with contextlib.suppress(RuntimeError, TypeError):
                source.disconnect(slot)

    def _on_screen_added(self, screen: QScreen) -> None:
        screen.availableGeometryChanged.connect(self._on_screens_changed)
        self._on_screens_changed()

    def _on_screens_changed(self, *_args: object) -> None:
        if self.window.isVisible():
            QTimer.singleShot(0, self.keep_window_on_screen)  # one-shot, after Qt settles

    def _load_window_state(self) -> WindowState | None:
        try:
            return self._window_state_repo.load()
        except StorageError:
            return None

    def _remember_window(self) -> None:
        if not self._window_shown:
            return
        self._window_state = self.window.window_state()
        try:
            self._window_state_repo.save(self._window_state)
        except StorageError:
            logger.warning("Could not save the window position")

    def _apply_preferences(self, preferences: UiPreferences) -> None:
        self.theme.set_mode(preferences.theme)
        self.window.set_preview_lines(preferences.preview_lines)
        self.window.set_unified_title_bar(preferences.unified_title_bar)

    def _hide_after_copy(self) -> None:
        if self.window.isVisible() and QApplication.activeModalWidget() is None:
            self.hide_window()

    def _on_app_state_changed(self, state: Qt.ApplicationState) -> None:
        if state == Qt.ApplicationState.ApplicationActive and not self.window.isVisible():
            self.show_window("reactivated")

    def _run_storage_action(self, action: Callable[[], object]) -> None:
        try:
            action()
        except StorageError as exc:
            self.window.show_error(str(exc))
        self.refresh()

    def _on_close_requested(self) -> None:
        if self.tray is None:
            self.quit()  # no menu-bar icon to come back through
        else:
            self.hide_window()

    def _create_tray(self) -> QSystemTrayIcon | None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            logger.warning("System tray unavailable; the window is the only entry point")
            return None
        tray = QSystemTrayIcon(clipboard_icon(), self)
        tray.setToolTip(f"{APP_NAME} — Command Library")
        # No setContextMenu(): on macOS that would replace left-click activation with the menu.
        # Left click toggles the window; right/ctrl-click opens this menu manually.
        self._tray_menu = QMenu()
        self._tray_menu.addAction("Open Command Library", self.show_window)
        self._tray_menu.addAction("New Command…", lambda: self.open_editor())
        self._tray_menu.addSeparator()
        self._tray_menu.addAction(f"Quit {APP_NAME}", self.quit)
        tray.activated.connect(self._on_tray_activated)
        tray.show()
        logger.info("Menu bar icon shown (visible=%s)", tray.isVisible())
        return tray

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Context:
            self._tray_menu.popup(QCursor.pos())
        elif reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.toggle_window()


def _log_unhandled(
    exc_type: type[BaseException], exc: BaseException, tb: TracebackType | None
) -> None:
    if issubclass(exc_type, KeyboardInterrupt):
        app = QApplication.instance()
        if app is not None:
            app.quit()
        return
    # Log the type and stack only; exception messages could contain command text.
    stack = "".join(traceback.format_tb(tb))
    logger.critical("Unhandled %s\n%s", exc_type.__name__, stack)


def _install_quit_signals(app: QApplication) -> None:
    """Quit gracefully on SIGTERM (Activity Monitor "Quit", ``kill``) and SIGINT (Ctrl+C).

    Python runs signal handlers only when the interpreter regains control, which may not
    happen while Qt waits for events. ``set_wakeup_fd`` writes to a pipe that Qt watches,
    waking the event loop — no polling timer needed.
    """
    read_fd, write_fd = os.pipe()
    os.set_blocking(write_fd, False)
    os.set_blocking(read_fd, False)
    signal.set_wakeup_fd(write_fd)
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: None)  # the wakeup fd does the work
    notifier = QSocketNotifier(read_fd, QSocketNotifier.Type.Read, app)

    def on_signal() -> None:
        try:
            os.read(read_fd, 64)
        except BlockingIOError:
            return
        logger.info("Quit signal received")
        app.quit()

    notifier.activated.connect(on_signal)


class _NoHotkeys:
    """Backend used when the global shortcut is disabled (tests, unsupported platforms)."""

    def system_conflict(self, hotkey: object) -> str | None:
        return None

    def register(self, hotkey: object, callback: object) -> object:
        raise HotkeyError("Global shortcuts aren't available.")


def _create_clipboard_writer() -> ClipboardWriter:
    from clipflow.platform.macos_clipboard import MacClipboardWriter

    return MacClipboardWriter()


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv)
    if "--self-test" in argv:
        from clipflow.selftest import run_self_test

        return run_self_test(argv)

    paths = default_paths()
    setup_logging(paths)
    sys.excepthook = _log_unhandled
    logger.info("Starting %s %s", APP_NAME, __version__)

    QApplication.setApplicationName(APP_NAME)
    QApplication.setApplicationVersion(__version__)
    app = QApplication(argv)
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(app_icon())  # the packaged .app uses its .icns; this covers source runs
    _install_quit_signals(app)  # the notifier is owned by app (Qt parent)

    if sys.platform != "darwin":
        QMessageBox.critical(None, APP_NAME, f"{APP_NAME} currently supports macOS only.")
        return 1

    instance = SingleInstance(instance_key(str(paths.data_dir)))
    if not instance.acquire():
        logger.info("Another instance is running; asked it to show its window")
        return 0

    try:
        conn = open_database(paths.database)
    except StorageError as exc:
        logger.error("Database unavailable: %s", exc)
        QMessageBox.critical(
            None,
            APP_NAME,
            f"{APP_NAME} couldn't open its database:\n{paths.database}\n\n{exc}\n\n"
            "Check that the folder exists, is writable, and the disk isn't full.",
        )
        return 1

    controller = ClipFlowController(
        conn, _create_clipboard_writer(), hotkey_backend=create_hotkey_backend()
    )
    instance.activation_requested.connect(lambda: controller.show_window("second launch"))
    app.aboutToQuit.connect(controller.shutdown)
    app.aboutToQuit.connect(instance.release)
    app.aboutToQuit.connect(conn.close)
    controller.start()
    controller.show_window("launch")
    exit_code = app.exec()
    logger.info("%s exited (%d)", APP_NAME, exit_code)
    return exit_code
