"""Small AppKit helpers for app activation."""

from __future__ import annotations

import sys


def activate_app() -> None:
    """Bring ClipFlow to the foreground so the popup's search field receives keystrokes.

    Only called in response to a user action (menu-bar click or reopen request).
    """
    if sys.platform != "darwin":
        return
    import AppKit

    app = AppKit.NSApplication.sharedApplication()
    app.unhide_(None)  # in case the palette was dismissed with hide_app()
    if hasattr(app, "activate"):  # macOS 14+
        app.activate()
    else:
        app.activateIgnoringOtherApps_(True)


def hide_app() -> None:
    """Hand focus back to the previously active app after the palette is dismissed.

    Equivalent to ⌘H. Re-launching ClipFlow (Spotlight, Finder, Dock) then reactivates it.
    """
    if sys.platform != "darwin":
        return
    import AppKit

    AppKit.NSApplication.sharedApplication().hide_(None)
