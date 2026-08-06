"""Single-instance guard: binds a fixed localhost TCP port to detect (and
signal) an already-running instance. The bind is both the exclusivity
check and the IPC channel -- no separate mutex or lock file."""
from __future__ import annotations

import socket
import threading
from typing import Callable

HOST = "127.0.0.1"
PORT = 51737


def acquire_or_signal(
    on_signal: Callable[[], None],
    host: str = HOST,
    port: int = PORT,
) -> socket.socket | None:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.bind((host, port))
    except OSError:
        listener.close()
        _signal_existing_instance(host, port)
        return None

    listener.listen(1)
    thread = threading.Thread(target=_listen_loop, args=(listener, on_signal), daemon=True)
    thread.start()
    return listener


def _listen_loop(listener: socket.socket, on_signal: Callable[[], None]) -> None:
    while True:
        try:
            conn, _addr = listener.accept()
        except OSError:
            return
        conn.close()
        on_signal()


def _signal_existing_instance(host: str, port: int) -> None:
    try:
        with socket.create_connection((host, port), timeout=1.0):
            pass
    except OSError:
        pass
