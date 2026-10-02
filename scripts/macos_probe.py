"""Menu-bar feasibility probe (macOS only). Independent of the clipflow package.

    python scripts/macos_probe.py --check     # print environment report, then exit
    python scripts/macos_probe.py             # run the interactive probe

Adds a menu-bar icon and prints every activation reason Qt reports, so left/right-click
behavior can be verified on this Mac. Left-click toggles a small window; right-click shows a
menu with Quit. The probe never touches the clipboard and starts no timers.
"""

from __future__ import annotations

import argparse
import platform
import signal
import sys
import time

if sys.platform != "darwin":
    sys.exit("This probe requires macOS.")

import AppKit
import objc
import PySide6
from PySide6.QtCore import Qt, QTimer, qVersion
from PySide6.QtGui import QColor, QCursor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QLabel, QMenu, QSystemTrayIcon, QVBoxLayout, QWidget


def environment_report(app: QApplication) -> list[str]:
    return [
        f"macOS {platform.mac_ver()[0]} ({platform.machine()})",
        f"Python {platform.python_version()} at {sys.executable}",
        f"PySide6 {PySide6.__version__} / Qt {qVersion()} / platform '{app.platformName()}'",
        f"PyObjC {objc.__version__}",
        f"System tray available: {QSystemTrayIcon.isSystemTrayAvailable()}",
    ]


def probe_icon() -> QIcon:
    pixmap = QPixmap(36, 36)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor("black"))
    painter.drawEllipse(8, 8, 20, 20)
    painter.end()
    pixmap.setDevicePixelRatio(2)
    icon = QIcon(pixmap)
    icon.setIsMask(True)
    return icon


class Probe:
    def __init__(self, app: QApplication) -> None:
        self.app = app
        self.clicks = 0
        self.window = QWidget(None, Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self.window.setWindowTitle("Vibe-Board menu-bar probe")
        self.label = QLabel("Left-click the dot icon to toggle this window.")
        layout = QVBoxLayout(self.window)
        layout.addWidget(self.label)
        self.window.resize(360, 100)

        self.tray = QSystemTrayIcon(probe_icon())
        self.tray.setToolTip("Vibe-Board probe")
        self.menu = QMenu()
        self.menu.addAction("Quit probe", app.quit)
        self.tray.activated.connect(self.on_activated)
        self.tray.show()

    def on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        self.clicks += 1
        print(time.strftime("%H:%M:%S"), f"tray activated: {reason.name}", flush=True)
        self.label.setText(f"Activations: {self.clicks}, last: {reason.name}")
        if reason == QSystemTrayIcon.ActivationReason.Context:
            self.menu.popup(QCursor.pos())
        elif reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.window.isVisible():
                self.window.hide()
                return
            geo = self.tray.geometry()
            if geo.isValid():
                self.window.move(geo.center().x() - 180, geo.bottom() + 8)
            self.window.show()
            self.window.raise_()
            AppKit.NSApplication.sharedApplication().activate()
            self.window.activateWindow()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="print environment and exit")
    parser.add_argument("--auto-quit", type=float, default=0, help="quit after N seconds")
    args = parser.parse_args()

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    for line in environment_report(app):
        print(line)
    if args.check:
        return 0

    Probe(app)
    print("Probe running. Left-click and right-click the dot icon in the menu bar.")
    print("Right-click → Quit probe, or press Ctrl+C here, to stop.")
    if args.auto_quit:
        QTimer.singleShot(int(args.auto_quit * 1000), app.quit)
    signal.signal(signal.SIGINT, signal.SIG_DFL)  # Ctrl+C terminates immediately
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
