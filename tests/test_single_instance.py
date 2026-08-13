import socket
import threading
import time

from facemesh_mouse.modules import single_instance


def _free_port() -> int:
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    return port


def test_acquire_returns_socket_and_invokes_callback_on_connect():
    port = _free_port()
    signaled = threading.Event()

    primary = single_instance.acquire_or_signal(on_signal=signaled.set, port=port)
    try:
        assert primary is not None

        with socket.create_connection(("127.0.0.1", port), timeout=1.0):
            pass

        assert signaled.wait(timeout=1.0)
    finally:
        primary.close()


def test_acquire_signals_existing_instance_and_returns_none_when_port_taken():
    port = _free_port()
    signaled = threading.Event()
    primary = single_instance.acquire_or_signal(on_signal=signaled.set, port=port)
    try:
        assert primary is not None

        result = single_instance.acquire_or_signal(on_signal=lambda: None, port=port)

        assert result is None
        assert signaled.wait(timeout=1.0)
    finally:
        primary.close()


def test_listener_keeps_accepting_after_first_signal():
    port = _free_port()
    call_count = {"n": 0}
    lock = threading.Lock()

    def on_signal() -> None:
        with lock:
            call_count["n"] += 1

    primary = single_instance.acquire_or_signal(on_signal=on_signal, port=port)
    try:
        assert primary is not None

        for _ in range(3):
            with socket.create_connection(("127.0.0.1", port), timeout=1.0):
                pass
            time.sleep(0.05)

        assert call_count["n"] == 3
    finally:
        primary.close()


def test_listener_survives_on_signal_exception():
    port = _free_port()
    call_count = {"n": 0}

    def flaky_on_signal() -> None:
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("simulated callback failure")

    primary = single_instance.acquire_or_signal(on_signal=flaky_on_signal, port=port)
    try:
        assert primary is not None

        # first connection triggers the raising callback
        with socket.create_connection(("127.0.0.1", port), timeout=1.0):
            pass
        time.sleep(0.05)
        assert call_count["n"] == 1

        # loop must still be alive to accept a second connection
        with socket.create_connection(("127.0.0.1", port), timeout=1.0):
            pass
        time.sleep(0.05)
        assert call_count["n"] == 2
    finally:
        primary.close()
