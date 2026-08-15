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
from .action_buttons import ActionButtons
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
    "3. Iniciar -- a janela some e o cursor passa a seguir a cabeça, já com "
    "os ajustes atuais. Reabrir a janela depois não interrompe o controle; "
    "use o botão Parar para isso de propósito.\n\n"
    "4. Salvar configurações -- grava os ajustes atuais no arquivo, pra "
    "abrirem assim da próxima vez. Iniciar/Parar e fechar esta janela não "
    "salvam sozinhos -- só esse botão salva.\n\n"
    "Atalhos\n\n"
    "Ctrl+Alt+P pausa e retoma (o ícone da bandeja também tem essa opção). "
    "Use como quem levanta o mouse da mesa: o cursor congela, você "
    "reposiciona a cabeça numa posição confortável, e ao retomar o controle "
    "continua exatamente de onde parou, sem pular. Pausado por qualquer um "
    "desses dois jeitos, o botão grande nesta janela muda pra \"Retomar "
    "controle do mouse\" -- clicar nele também retoma.\n\n"
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
        action_buttons: ActionButtons | None = None,
    ) -> None:
        self._root = root
        self._engine = engine
        # A private copy: the panels mutate self._config live as sliders and
        # captures change, and it must not be the same object Engine /
        # GestureEngine / MouseController are using mid-frame. `_start_and_hide`
        # hands this copy to `on_start`, which calls `engine.update_config`,
        # so edits still reach the engine -- but only on an explicit save.
        self._config = copy.deepcopy(config)
        # Not part of the deep copy: no panel in this window reads or edits
        # the action buttons' position, so there's nothing to buffer --
        # `_apply_panel_edits` reads it fresh from here, so a drag that
        # happened after this window was built is never lost.
        self._live_config = config
        self._config_path = config_path
        self._on_start = on_start
        # None when the floating buttons failed to construct in main.py --
        # the reset button becomes a no-op rather than crashing the window.
        self._action_buttons = action_buttons
        self._tk_image = None
        self._after_id = None

        root.title("FaceMesh Mouse")
        root.protocol("WM_DELETE_WINDOW", self._save_and_hide)

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

        self._status_label = ctk.CTkLabel(left, text="", font=("Segoe UI", 12, "bold"))
        self._status_label.pack(padx=10, pady=(0, 4))

        self._toggle_button = ctk.CTkButton(
            left,
            text="",
            height=44,
            font=("Segoe UI", 14, "bold"),
            command=self._on_toggle,
        )
        self._toggle_button.pack(fill="x", padx=10, pady=(0, 10))
        # Captured before the first _update_toggle() call so "Iniciar" can
        # restore the theme's default blue instead of hardcoding it.
        self._start_fg_color = self._toggle_button.cget("fg_color")
        self._start_hover_color = self._toggle_button.cget("hover_color")
        self._update_toggle()

        self._save_button = ctk.CTkButton(
            left,
            text="Salvar configurações",
            height=36,
            fg_color="transparent",
            border_width=1,
            command=self._on_save,
        )
        self._save_button.pack(fill="x", padx=10, pady=(0, 10))

        ctk.CTkButton(
            left,
            text="Redefinir posição do teclado/microfone",
            height=32,
            fg_color="transparent",
            border_width=1,
            text_color="gray70",
            command=self._on_reset_position,
        ).pack(fill="x", padx=10, pady=(0, 10))

        ctk.CTkLabel(
            left,
            text=(
                "Iniciar aplica os ajustes ao controle, mas só fica salvo pra "
                "próxima vez que você clicar em Salvar. Fechar esta janela não "
                "muda o controle nem salva."
            ),
            text_color="gray70",
            justify="left",
            wraplength=220,
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
            self._update_toggle()

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
    def _apply_panel_edits(self) -> None:
        """Pulls pending slider/dropdown edits from the panels into
        self._config, and syncs the floating buttons' drag positions from
        `_live_config` -- but never touches disk. Shared by both the
        explicit Salvar action and Iniciar, which must apply edits to the
        running engine even when the user never clicks Salvar."""
        self._calibration.apply_to_config()
        self._gestures.apply_to_config()
        self._config.action_buttons.x = self._live_config.action_buttons.x
        self._config.action_buttons.y = self._live_config.action_buttons.y

    def _save_config(self) -> None:
        """Explicit save, only ever called from the Salvar button -- Iniciar/
        Parar/closing the window must not silently write to disk on their
        own; see _apply_panel_edits for the in-memory-only counterpart."""
        self._apply_panel_edits()
        config_mod.save_config(self._config_path, self._config)

    def _start_and_hide(self) -> None:
        self._apply_panel_edits()
        self._on_start(self._config)
        self._root.withdraw()

    def _resume_and_hide(self) -> None:
        """Un-pauses (e.g. paused earlier from the tray icon or Ctrl+Alt+P)
        and hides -- same "apply pending edits, go back to head control"
        shape as _start_and_hide, since control was never actually stopped."""
        self._apply_panel_edits()
        self._on_start(self._config)
        self._engine.paused.clear()
        self._root.withdraw()

    def _stop(self) -> None:
        self._engine.control_enabled.clear()
        self._update_toggle()

    def _save_and_hide(self) -> None:
        """WM_DELETE_WINDOW handler: just hides, leaving control_enabled
        exactly as it was -- closing the window must not second-guess an
        explicit Iniciar/Parar choice, nor silently persist or discard
        whatever is pending in the panels (use Salvar for that)."""
        self._root.withdraw()

    def _on_save(self) -> None:
        self._save_config()
        self._flash_save_button()

    def _on_reset_position(self) -> None:
        """Moves the floating keyboard/mic buttons back to their default
        corner immediately, and persists it -- a no-op if the buttons
        failed to construct in main.py (self._action_buttons is None)."""
        if self._action_buttons is not None:
            self._action_buttons.reset_position()

    def _flash_save_button(self) -> None:
        """Brief text swap so clicking Salvar has visible confirmation --
        there's no other feedback for a save that doesn't also start/stop
        control."""
        self._save_button.configure(text="Salvo")
        self._root.after(1200, lambda: self._save_button.configure(text="Salvar configurações"))

    def _on_toggle(self) -> None:
        if not self._engine.control_enabled.is_set():
            self._start_and_hide()
        elif self._engine.paused.is_set():
            self._resume_and_hide()
        else:
            self._stop()

    def _update_toggle(self) -> None:
        """Reflects three states, not two: stopped, paused (e.g. from the
        tray icon or Ctrl+Alt+P -- yielded to a physical mouse but still
        "on"), and actively tracking. Without the paused state here, this
        window would show "Parar controle do mouse" while paused, which
        both lies about what's currently happening and -- if clicked --
        would stop control outright instead of the lighter resume the user
        actually wants."""
        if not self._engine.control_enabled.is_set():
            self._status_label.configure(text="Controle parado")
            self._toggle_button.configure(
                text="Iniciar controle do mouse",
                fg_color=self._start_fg_color,
                hover_color=self._start_hover_color,
            )
        elif self._engine.paused.is_set():
            self._status_label.configure(text="Controle pausado")
            self._toggle_button.configure(
                text="Retomar controle do mouse",
                fg_color="#d68910",
                hover_color="#b7790d",
            )
        else:
            self._status_label.configure(text="Controle ativo")
            self._toggle_button.configure(
                text="Parar controle do mouse",
                fg_color="#c0392b",
                hover_color="#992d22",
            )

    def show(self) -> None:
        self._update_toggle()
        self._root.deiconify()
        self._root.lift()
