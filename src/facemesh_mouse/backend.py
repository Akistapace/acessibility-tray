"""Headless backend: wires Engine to the stdio IPC protocol (see
modules/ipc_protocol.py). BackendServer.handle_command is pure command
dispatch, testable against a real Engine with no camera or real stdio
involved -- the push loops and camera/stdin wiring live in main() (see
the design spec's Testing section: that half is manual-verified, not
unit tested, the same way it always has been for this project's
camera-dependent code paths).
"""
from __future__ import annotations

import base64
import ctypes
import sys
import threading
from typing import Callable

from .modules import click_log
from .modules import config as config_mod
from .modules.config import AppConfig
from .modules.engine import Engine
from .modules import ipc_protocol as proto
from .modules.gestures import trigger_progress
from .modules import preview as preview_mod
from . import virtual_keyboard
from . import voice_typing

CONFIG_PATH = "config.json"
STATUS_POLL_INTERVAL_S = 0.2
FRAME_INTERVAL_S = 1 / 30


def _status_snapshot(engine: Engine) -> dict:
    mouse_controller = engine.mouse_controller
    return {
        "control_enabled": engine.control_enabled.is_set(),
        "paused": engine.paused.is_set(),
        "no_face": engine.no_face.is_set(),
        "yielded": mouse_controller.yielded if mouse_controller is not None else False,
    }


def _encode_frame(
    frame, metrics, config: AppConfig, seq: int, highlighted_gesture: str | None = None
) -> dict:
    jpeg_bytes = preview_mod.render_preview_jpeg(frame, metrics, highlighted_gesture)
    jpeg_b64 = base64.b64encode(jpeg_bytes).decode("ascii")
    gesture_progress = {
        name: (
            trigger_progress(name, metrics, gesture_cfg.threshold)
            if metrics is not None
            else 0.0
        )
        for name, gesture_cfg in config.gestures.items()
    }
    return proto.frame_message(jpeg_b64, gesture_progress, seq)


class BackendServer:
    def __init__(
        self,
        engine: Engine,
        config: AppConfig,
        config_path: str = CONFIG_PATH,
        send: Callable[[dict], None] = lambda message: None,
    ) -> None:
        self._engine = engine
        self.config = config
        self._config_path = config_path
        self._send = send
        self.preview_enabled = False
        self.highlighted_gesture: str | None = None

    def handle_command(self, command: dict) -> None:
        handler = getattr(self, f"_cmd_{command.get('type')}", None)
        if handler is None:
            return
        try:
            handler(command)
        except Exception as exc:  # noqa: BLE001 - one bad command must never kill the backend
            print(
                f"facemesh-mouse: command {command.get('type')!r} failed ({exc!r})",
                file=sys.stderr,
            )

    def _cmd_set_preview(self, command: dict) -> None:
        self.preview_enabled = bool(command.get("enabled", False))

    def _cmd_highlight_gesture(self, command: dict) -> None:
        gesture = command.get("gesture")
        self.highlighted_gesture = gesture if gesture in config_mod.GESTURE_NAMES else None

    def _cmd_start(self, _command: dict) -> None:
        self._engine.control_enabled.set()

    def _cmd_stop(self, _command: dict) -> None:
        self._engine.control_enabled.clear()

    def _cmd_pause(self, _command: dict) -> None:
        self._engine.paused.set()

    def _cmd_resume(self, _command: dict) -> None:
        self._engine.paused.clear()

    def _cmd_update_config(self, command: dict) -> None:
        self.config = config_mod.config_from_dict(command.get("config", {}))
        self._engine.update_config(self.config)
        self._sync_click_logging(self.config)

    def _cmd_save_config(self, command: dict) -> None:
        on_disk = config_mod.load_config(self._config_path)
        on_disk_dict = config_mod.config_to_dict(on_disk)
        payload = command.get("config", {})
        merged = {**on_disk_dict, **payload}
        if "calibration" in payload:
            merged["calibration"] = {**on_disk_dict["calibration"], **payload["calibration"]}
        if "action_buttons" in payload:
            merged["action_buttons"] = {**on_disk_dict["action_buttons"], **payload["action_buttons"]}
        saved = config_mod.config_from_dict(merged)
        config_mod.save_config(self._config_path, saved)
        # Windows other than the one that saved (e.g. the buttons window,
        # which only ever asks for config once on load) have no other way
        # to learn a change like the keyboard-button toggle short of an
        # app restart.
        self._send(proto.config_message(config_mod.config_to_dict(saved)))

    def _cmd_open_keyboard(self, command: dict) -> None:
        x, y = command.get("x", 0), command.get("y", 0)
        opened = virtual_keyboard.open_virtual_keyboard()
        self._send(proto.keyboard_result_message(opened, x, y))

    def _cmd_open_voice_typing(self, _command: dict) -> None:
        voice_typing.toggle_voice_typing()

    def _cmd_get_config(self, _command: dict) -> None:
        self._send(proto.config_message(config_mod.config_to_dict(self.config)))

    def _sync_click_logging(self, config: AppConfig) -> None:
        try:
            if config.calibration.click_logging_enabled:
                click_log.enable()
            else:
                click_log.disable()
        except OSError as exc:
            print(f"facemesh-mouse: click log setup failed ({exc!r})", file=sys.stderr)


def _redirect_prints_to_stderr() -> None:
    """stdout is reserved for protocol lines -- every diagnostic print in
    this process, including ones raised deep in virtual_keyboard.py or
    voice_typing.py, must land on stderr or it corrupts the line-
    delimited JSON stream Electron is parsing."""
    sys.stdout = sys.stderr


def _primary_screen_size() -> tuple[int, int]:
    return (
        ctypes.windll.user32.GetSystemMetrics(0),
        ctypes.windll.user32.GetSystemMetrics(1),
    )


def _status_loop(engine: Engine, send: Callable[[dict], None], stop: threading.Event) -> None:
    last = None
    while not stop.is_set():
        current = _status_snapshot(engine)
        if current != last:
            send(proto.status_message(**current))
            last = current
        stop.wait(STATUS_POLL_INTERVAL_S)


def _frame_loop(
    engine: Engine, server: "BackendServer", send: Callable[[dict], None], stop: threading.Event
) -> None:
    seq = 0
    while not stop.is_set():
        if server.preview_enabled:
            try:
                frame, metrics = engine.state.snapshot()
                if frame is not None:
                    send(_encode_frame(frame, metrics, server.config, seq, server.highlighted_gesture))
                    seq += 1
            except Exception as exc:  # noqa: BLE001 - one bad frame must never kill the push loop
                print(f"facemesh-mouse: frame push failed ({exc!r})", file=sys.stderr)
        stop.wait(FRAME_INTERVAL_S)


def main() -> None:
    real_stdout = sys.stdout
    _redirect_prints_to_stderr()
    config = config_mod.load_config(CONFIG_PATH)

    def send(message: dict) -> None:
        proto.write_message(real_stdout, message)

    def on_action(gesture_name: str, action: str, position: tuple[int, int]) -> None:
        click_log.record(gesture_name, action, position)
        send(proto.action_message(gesture_name, action, position[0], position[1]))

    engine = Engine(config, on_action=on_action)
    server = BackendServer(engine, config, config_path=CONFIG_PATH, send=send)
    server._sync_click_logging(config)

    if not engine.open_camera():
        send(proto.error_message("camera"))
        return

    engine.start(_primary_screen_size())

    stop = threading.Event()
    threading.Thread(target=_status_loop, args=(engine, send, stop), daemon=True).start()
    threading.Thread(target=_frame_loop, args=(engine, server, send, stop), daemon=True).start()

    try:
        for command in proto.read_messages(sys.stdin):
            server.handle_command(command)
    finally:
        stop.set()
        engine.stop()


if __name__ == "__main__":
    main()
