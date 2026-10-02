"""Single-instance coordination over a per-user local socket."""

from __future__ import annotations

import hashlib
import logging
import os

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

logger = logging.getLogger(__name__)

_ACTIVATE = b"activate"


def instance_key(data_dir: str) -> str:
    # Per user and per data directory, so a dev checkout with CLIPFLOW_DATA_DIR can run alongside.
    digest = hashlib.sha256(data_dir.encode()).hexdigest()[:12]
    return f"clipflow-{os.getuid()}-{digest}"


class SingleInstance(QObject):
    """First instance listens; later launches ask it to show its popup and then exit."""

    activation_requested = Signal()

    def __init__(self, key: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._key = key
        self._server: QLocalServer | None = None

    def acquire(self) -> bool:
        """Return True if this process is the primary instance."""
        probe = QLocalSocket()
        probe.connectToServer(self._key)
        if probe.waitForConnected(300):
            probe.write(_ACTIVATE)
            probe.flush()
            probe.waitForBytesWritten(300)
            probe.disconnectFromServer()
            if probe.state() != QLocalSocket.LocalSocketState.UnconnectedState:
                probe.waitForDisconnected(300)
            return False
        QLocalServer.removeServer(self._key)  # stale socket left by a crash
        server = QLocalServer(self)
        server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        if not server.listen(self._key):
            logger.warning("Single-instance server unavailable; continuing without it")
            return True
        server.newConnection.connect(self._on_connection)
        self._server = server
        return True

    def release(self) -> None:
        if self._server is not None:
            self._server.close()
            self._server = None

    def _on_connection(self) -> None:
        if self._server is None:
            return
        while (socket := self._server.nextPendingConnection()) is not None:
            # The message is tiny and the sender waits for it to be written; read it directly
            # rather than keeping per-socket callbacks alive.
            ready = socket.bytesAvailable() > 0 or socket.waitForReadyRead(300)
            if ready and bytes(socket.readAll().data()).startswith(_ACTIVATE):
                self.activation_requested.emit()
            socket.abort()
            socket.deleteLater()
