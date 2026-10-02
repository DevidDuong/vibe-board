"""NSPasteboard writer (PyObjC). Deliberately has no read methods."""

from __future__ import annotations

from collections.abc import Callable

import AppKit


class MacClipboardWriter:
    def __init__(self, pasteboard: AppKit.NSPasteboard | None = None) -> None:
        # Tests pass a uniquely named private pasteboard so they never touch the user's clipboard.
        self._pb = pasteboard if pasteboard is not None else AppKit.NSPasteboard.generalPasteboard()

    def write_text(self, text: str) -> None:
        self._pb.clearContents()
        if not self._pb.setString_forType_(text, AppKit.NSPasteboardTypeString):
            raise OSError("NSPasteboard rejected the string write")


def private_pasteboard_writer() -> tuple[MacClipboardWriter, Callable[[], None]]:
    """A writer bound to a new, uniquely named pasteboard (never the user's clipboard), plus
    a function that releases it. Used by the packaged-app self-test."""
    pasteboard = AppKit.NSPasteboard.pasteboardWithUniqueName()
    return MacClipboardWriter(pasteboard), pasteboard.releaseGlobally
