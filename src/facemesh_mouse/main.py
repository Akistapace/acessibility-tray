"""Entry point: wires engine, config GUI, tray icon, and hotkeys together."""
from __future__ import annotations

import sys
from pathlib import Path

import tkinter as tk
from tkinter import messagebox

from .modules import click_log
from .modules import config as config_mod
from .modules import single_instance
from .modules.engine import Engine
from .modules.hotkeys import HotkeyListener
from .ui import click_feedback
from .ui.action_buttons import ActionButtons
from .ui.config_gui import ConfigWindow, create_root
from .ui.tray import TrayIcon

CONFIG_PATH = "config.json"
ICON_PATH = "assets/icon.ico"


def _resource_path(relative: str) -> Path:
    """Resolves a bundled asset both when run from source and when frozen
    by PyInstaller, whose --onefile mode unpacks `datas` under `sys._MEIPASS`
    instead of the source tree."""
    base = getattr(sys, "_MEIPASS", None)
    if base is None:
        base = Path(__file__).resolve().parents[2]
    return Path(base) / relative


def _make_process_dpi_aware() -> None:
    """Must run before any Tk window is created.

    customtkinter itself calls SetProcessDpiAwareness when the first CTk
    window is built, but by then tkinter.Tk.__init__ has already run and
    cached the desktop size at the OLD (unaware) logical resolution. Every
    Win32 call made after the awareness flip -- including pynput's cursor
    positioning -- then operates in physical pixels, while the cached
    winfo_screenwidth/height stays at the stale logical value: on a scaled
    display the cursor can never reach the true right/bottom edge. Setting
    awareness here, first, makes Tk cache the real physical resolution so
    it and pynput agree.
    """
    if sys.platform.startswith("win"):
        import ctypes

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
        except OSError:
            pass


def _sync_click_logging(config) -> None:
    try:
        if config.calibration.click_logging_enabled:
            click_log.enable()
        else:
            click_log.disable()
    except OSError as exc:
        # A locked/read-only clicks.log must never block the app from
        # starting control -- logging is a convenience, not the feature.
        print(f"facemesh-mouse: click log setup failed ({exc!r})")


def main() -> None:
    _make_process_dpi_aware()
    _config_window_opener = None

    def _on_singleton_signal() -> None:
        if _config_window_opener is not None:
            _config_window_opener()

    singleton_socket = single_instance.acquire_or_signal(on_signal=_on_singleton_signal)
    if singleton_socket is None:
        sys.exit(0)

    app_config = config_mod.load_config(CONFIG_PATH)
    _sync_click_logging(app_config)

    def _on_action(gesture_name: str, action: str, position: tuple[int, int]) -> None:
        if action == "freeze_cursor":
            # Fired before MouseController flips `frozen` (see fire_action),
            # so its current value is the pre-toggle state -- "not frozen"
            # here means this call is about to engage the freeze.
            mouse_controller = engine.mouse_controller
            will_freeze = not (mouse_controller.frozen if mouse_controller else False)
            root.after(0, click_feedback.show_lock_pulse, root, position[0], position[1], will_freeze)
        else:
            root.after(0, click_feedback.show_pulse, root, position[0], position[1])
        click_log.record(gesture_name, action, position)

    engine = Engine(app_config, on_action=_on_action)

    if not engine.open_camera():
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "FaceMesh Mouse",
            "Não foi possível acessar a webcam. Verifique se ela está "
            "conectada e se a permissão de câmera do Windows está ativa.",
        )
        sys.exit(1)

    root = create_root()
    try:
        root.iconbitmap(str(_resource_path(ICON_PATH)))
    except Exception as exc:  # noqa: BLE001 - a missing icon must never block startup
        print(f"facemesh-mouse: window icon failed ({exc!r})")
    screen_size = (root.winfo_screenwidth(), root.winfo_screenheight())
    engine.start(screen_size)

    action_buttons = None
    try:
        action_buttons = ActionButtons(root, app_config, CONFIG_PATH, screen_size)
    except Exception as exc:  # noqa: BLE001 - missing buttons must never block startup
        print(f"facemesh-mouse: floating action buttons failed ({exc!r})")

    config_window = ConfigWindow(
        root,
        engine,
        app_config,
        CONFIG_PATH,
        on_start=_make_on_start(engine),
        action_buttons=action_buttons,
    )

    if Path(CONFIG_PATH).exists():
        engine.control_enabled.set()
        root.withdraw()

    def toggle_pause() -> bool:
        if engine.paused.is_set():
            engine.paused.clear()
        else:
            engine.paused.set()
        return engine.paused.is_set()

    def open_config() -> None:
        root.after(0, config_window.show)

    _config_window_opener = open_config

    def quit_app() -> None:
        engine.stop()
        hotkeys.stop()
        root.after(0, root.quit)

    tray = TrayIcon(
        on_toggle_pause=toggle_pause,
        on_open_config=open_config,
        on_quit=quit_app,
    )
    tray.run_in_thread()

    hotkeys = HotkeyListener(
        on_toggle_pause=tray.toggle_pause,
        on_open_config=open_config,
    )
    hotkeys.start()

    _poll_status(root, engine, tray)

    root.mainloop()


def _make_on_start(engine: Engine):
    def on_start(new_config) -> None:
        engine.update_config(new_config)
        _sync_click_logging(new_config)
        engine.control_enabled.set()

    return on_start


def _poll_status(root: tk.Tk, engine: Engine, tray: TrayIcon) -> None:
    tray.set_no_face(engine.no_face.is_set())
    mouse_controller = engine.mouse_controller
    tray.set_yielded(mouse_controller.yielded if mouse_controller is not None else False)
    root.after(500, _poll_status, root, engine, tray)


if __name__ == "__main__":
    main()
