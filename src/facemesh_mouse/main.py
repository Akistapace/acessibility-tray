"""Entry point: wires engine, config GUI, tray icon, and hotkeys together."""
from __future__ import annotations

import sys
from pathlib import Path

import tkinter as tk
from tkinter import messagebox

from . import config as config_mod
from . import single_instance
from .config_gui import ConfigWindow, create_root
from .engine import Engine
from .hotkeys import HotkeyListener
from .tray import TrayIcon

CONFIG_PATH = "config.json"


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

    root = create_root()
    screen_size = (root.winfo_screenwidth(), root.winfo_screenheight())
    engine.start(screen_size)

    config_window = ConfigWindow(
        root,
        engine,
        app_config,
        CONFIG_PATH,
        on_start=_make_on_start(engine),
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
