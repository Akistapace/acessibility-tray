"""Headless backend: wires Engine to the stdio IPC protocol (see
modules/ipc_protocol.py). BackendServer.handle_command is pure command
dispatch, testable against a real Engine with no camera or real stdio
involved -- the push loops and camera/stdin wiring live in main() (see
the design spec's Testing section: that half is manual-verified, not
unit tested, the same way it always has been for this project's
camera-dependent code paths).
"""
from __future__ import annotations

import sys
from typing import Callable

from .modules import click_log
from .modules import config as config_mod
from .modules.config import AppConfig
from .modules.engine import Engine
from .modules import ipc_protocol as proto
from . import virtual_keyboard
from . import voice_typing

CONFIG_PATH = "config.json"


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

    def handle_command(self, command: dict) -> None:
        handler = getattr(self, f"_cmd_{command.get('type')}", None)
        if handler is None:
            return
        handler(command)

    def _cmd_set_preview(self, command: dict) -> None:
        self.preview_enabled = bool(command.get("enabled", False))

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
        config = config_mod.config_from_dict(command.get("config", {}))
        config_mod.save_config(self._config_path, config)

    def _cmd_open_keyboard(self, command: dict) -> None:
        x, y = command.get("x", 0), command.get("y", 0)
        opened = virtual_keyboard.open_virtual_keyboard()
        self._send(proto.keyboard_result_message(opened, x, y))

    def _cmd_open_voice_typing(self, _command: dict) -> None:
        voice_typing.toggle_voice_typing()

    def _sync_click_logging(self, config: AppConfig) -> None:
        try:
            if config.calibration.click_logging_enabled:
                click_log.enable()
            else:
                click_log.disable()
        except OSError as exc:
            print(f"facemesh-mouse: click log setup failed ({exc!r})", file=sys.stderr)
