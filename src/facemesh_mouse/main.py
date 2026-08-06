"""Entry point: wires engine, config GUI, tray icon, and hotkeys together."""
from __future__ import annotations

import sys
import tkinter as tk
from tkinter import messagebox

from . import config as config_mod
from . import single_instance
from .config_gui import ConfigWindow
from .engine import Engine
from .hotkeys import HotkeyListener
from .tray import TrayIcon

CONFIG_PATH = "config.json"


def main() -> None:
    _config_window_opener = None

    def _on_singleton_signal() -> None:
        if _config_window_opener is not None:
            _config_window_opener()

    singleton_socket = single_instance.acquire_or_signal(on_signal=_on_singleton_signal)
    if singleton_socket is None:
        sys.exit(0)

    app_config = config_mod.load_config(CONFIG_PATH)
    engine = Engine(app_config)

    if not engine.open_camera():
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "FaceMesh Mouse",
            "Nao foi possivel acessar a webcam. Verifique se ela esta "
            "conectada e se a permissao de camera do Windows esta ativa.",
        )
        sys.exit(1)

    root = tk.Tk()
    screen_size = (root.winfo_screenwidth(), root.winfo_screenheight())
    engine.start(screen_size)

    config_window = ConfigWindow(
        root,
        engine,
        app_config,
        CONFIG_PATH,
        on_start=_make_on_start(engine),
    )

    def toggle_pause() -> bool:
        if engine.paused.is_set():
            engine.paused.clear()
        else:
            engine.paused.set()
        return engine.paused.is_set()

    def open_config() -> None:
        engine.control_enabled.clear()
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

    _poll_no_face(root, engine, tray)

    root.mainloop()


def _make_on_start(engine: Engine):
    def on_start(new_config) -> None:
        engine.update_config(new_config)
        engine.control_enabled.set()

    return on_start


def _poll_no_face(root: tk.Tk, engine: Engine, tray: TrayIcon) -> None:
    tray.set_no_face(engine.no_face.is_set())
    root.after(500, _poll_no_face, root, engine, tray)


if __name__ == "__main__":
    main()
