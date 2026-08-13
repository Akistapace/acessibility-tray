"""Config window shell: live preview on the left, tabbed settings on the
right. Reads the engine's SharedState for preview only -- it never touches
the camera directly (see engine.py).

`ctk.CTk` subclasses `tk.Tk`, so the tray thread, the global hotkeys, the
single-instance listener, and the skip-wizard startup path keep using
`root.after` / `withdraw` / `deiconify` exactly as before.
"""
from __future__ import annotations

import copy
import tkinter as tk
from typing import Callable

import customtkinter as ctk
import cv2
from PIL import Image, ImageTk

from ..modules import config as config_mod
from ..modules.config import AppConfig
from ..modules.engine import Engine
from .calibration_panel import CalibrationPanel
from .gesture_panel import GesturePanel

PREVIEW_SIZE = (480, 360)

_HELP_TEXT = (
    "Como usar\n\n"
    "1. Movimento -- ajuste os sliders de sensibilidade, aceleração e limiar "
    "de movimento. O cursor anda de forma relativa, como um mouse de "
    "verdade. O interruptor de clique por permanência dispara um clique "
    "esquerdo sozinho quando o cursor fica parado sobre um elemento, sem "
    "precisar de gesto.\n\n"
    "2. Gestos -- veja qual barra reage a cada expressão e escolha o que ela "
    "faz. O tempo de cada gesto é quanto você precisa segurar a expressão: é o "
    "que impede piscadas naturais de virarem cliques. Deixe em 0 ms só se "
    "quiser disparo imediato.\n\n"
    "3. Iniciar -- a janela some e o cursor passa a seguir a cabeça.\n\n"
    "Atalhos\n\n"
    "Ctrl+Alt+P pausa e retoma. Use como quem levanta o mouse da mesa: o "
    "cursor congela, você reposiciona a cabeça numa posição confortável, e ao "
    "retomar o controle continua exatamente de onde parou, sem pular.\n\n"
    "Ctrl+Alt+O reabre esta janela. Clicar no ícone da bandeja também reabre; "
    "o botão direito no ícone mostra o menu completo.\n\n"
    "Abrir o app de novo enquanto ele já está rodando não cria uma segunda "
    "cópia: reabre esta janela."
)


def create_root() -> ctk.CTk:
    """Creates the single Tk root the whole app runs on."""
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    return ctk.CTk()


class ConfigWindow:
    def __init__(
        self,
        root: ctk.CTk,
        engine: Engine,
        config: AppConfig,
        config_path: str,
        on_start: Callable[[AppConfig], None],
    ) -> None:
        self._root = root
        self._engine = engine
        # A private copy: the panels mutate self._config live as sliders and
        # captures change, and it must not be the same object Engine /
        # GestureEngine / MouseController are using mid-frame. `_start_and_hide`
        # hands this copy to `on_start`, which calls `engine.update_config`,
        # so edits still reach the engine -- but only on an explicit save.
        self._config = copy.deepcopy(config)
        self._config_path = config_path
        self._on_start = on_start
        self._tk_image = None
        self._after_id = None

        root.title("FaceMesh Mouse")
        root.protocol("WM_DELETE_WINDOW", self._start_and_hide)

        self._build_widgets()
        self._tick()

    # -- widgets --------------------------------------------------------
    def _build_widgets(self) -> None:
        self._root.grid_columnconfigure(1, weight=1)
        self._root.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(self._root)
        left.grid(row=0, column=0, padx=12, pady=12, sticky="n")

        self._preview = tk.Label(left, background="#1f1f1f")
        self._preview.pack(padx=10, pady=10)

        ctk.CTkButton(
            left,
            text="Iniciar controle do mouse",
            height=44,
            font=("Segoe UI", 14, "bold"),
            command=self._start_and_hide,
        ).pack(fill="x", padx=10, pady=(0, 10))

        ctk.CTkLabel(
            left,
            text="A janela some e o controle segue em segundo plano.",
            text_color="gray70",
        ).pack(padx=10, pady=(0, 10))

        tabs = ctk.CTkTabview(self._root, width=430)
        tabs.grid(row=0, column=1, padx=(0, 12), pady=12, sticky="nsew")
        tabs.add("Movimento")
        tabs.add("Gestos")
        tabs.add("Ajuda")

        self._calibration = CalibrationPanel(tabs.tab("Movimento"), self._config)
        self._calibration.frame.pack(fill="both", expand=True)

        self._gestures = GesturePanel(tabs.tab("Gestos"), self._config)
        self._gestures.frame.pack(fill="both", expand=True)

        ctk.CTkLabel(
            tabs.tab("Ajuda"),
            text=_HELP_TEXT,
            justify="left",
            wraplength=390,
            anchor="nw",
        ).pack(fill="both", expand=True, padx=6, pady=6)

        # The preview image only arrives after the first camera frame, so
        # the window's natural requested size at build time (empty preview
        # label) underestimates the real need -- without an explicit size
        # the CustomTkinter default of 200x200 leaves buttons and sliders
        # off-screen. With the capture-button grid gone and the sliders
        # bounded to width=220, the content fits comfortably below these
        # values (previously 1120x720 / 1080x620, sized around content that
        # overflowed a 1536x864 screen).
        self._root.geometry("1060x680")
        self._root.minsize(1000, 620)

    # -- live preview loop ----------------------------------------------
    def _tick(self) -> None:
        # Skipped entirely while hidden: with the app now starting straight
        # into background tracking, "hidden" is the normal state for a whole
        # session, and this loop would otherwise decode and convert a frame
        # 30 times a second for a window nobody can see.
        if self._root.winfo_viewable():
            frame, metrics = self._engine.state.snapshot()
            if frame is not None:
                self._render_preview(frame, metrics)
            if metrics is not None:
                self._calibration.update(metrics)
                self._gestures.update(metrics)

        self._after_id = self._root.after(33, self._tick)

    def _render_preview(self, frame, metrics) -> None:
        display = cv2.resize(frame, PREVIEW_SIZE)
        if metrics is not None:
            height, width = display.shape[:2]
            center = (int(metrics.nose_x * width), int(metrics.nose_y * height))
            left_eye = (
                int(metrics.landmarks[33][0] * width),
                int(metrics.landmarks[33][1] * height),
            )
            right_eye = (
                int(metrics.landmarks[263][0] * width),
                int(metrics.landmarks[263][1] * height),
            )
            cv2.line(display, left_eye, right_eye, (0, 255, 255), 1)
            cv2.circle(display, left_eye, 2, (0, 255, 0), -1)
            cv2.circle(display, right_eye, 2, (0, 255, 0), -1)
            cv2.circle(display, center, 5, (0, 0, 255), -1)
        rgb = cv2.cvtColor(display, cv2.COLOR_BGR2RGB)
        self._tk_image = ImageTk.PhotoImage(image=Image.fromarray(rgb))
        self._preview.configure(image=self._tk_image)

    # -- lifecycle -------------------------------------------------------
    def _start_and_hide(self) -> None:
        self._calibration.apply_to_config()
        self._gestures.apply_to_config()
        config_mod.save_config(self._config_path, self._config)
        self._on_start(self._config)
        self._root.withdraw()

    def show(self) -> None:
        self._root.deiconify()
        self._root.lift()
