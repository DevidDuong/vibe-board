"""Real AppKit tests against a private, uniquely named pasteboard.

They never read or modify the user's general clipboard. Reading the private pasteboard back
here is test-only verification; ClipFlow itself has no read path.
"""

from __future__ import annotations

import sys

import pytest

pytestmark = [
    pytest.mark.macos,
    pytest.mark.skipif(sys.platform != "darwin", reason="requires macOS AppKit"),
]


@pytest.fixture
def private_pb():
    import AppKit

    pb = AppKit.NSPasteboard.pasteboardWithUniqueName()
    yield pb
    pb.releaseGlobally()


@pytest.mark.parametrize(
    "text",
    [
        'for f in *.log; do\n\tgzip "$f"\ndone\n',
        "echo 'សួស្តី 🚀'\r\n",
        "   spaced   ",
        "y" * 32 * 1024,
    ],
)
def test_writes_exact_text(private_pb, text):
    import AppKit

    from clipflow.platform.macos_clipboard import MacClipboardWriter

    MacClipboardWriter(private_pb).write_text(text)
    assert str(private_pb.stringForType_(AppKit.NSPasteboardTypeString)) == text


def test_copy_from_controller_reaches_pasteboard(qtbot, conn, private_pb):
    import AppKit

    from clipflow.app import ClipFlowController
    from clipflow.models.command import CommandDraft
    from clipflow.platform.macos_clipboard import MacClipboardWriter

    ctl = ClipFlowController(conn, MacClipboardWriter(private_pb), use_tray=False)
    qtbot.addWidget(ctl.window)
    saved = ctl.commands.create(CommandDraft("Multi", "a\n\tb\n"))
    ctl.copy_command(saved.id)
    assert str(private_pb.stringForType_(AppKit.NSPasteboardTypeString)) == "a\n\tb\n"
    ctl.shutdown()
