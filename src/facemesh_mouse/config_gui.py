"""Tkinter config window: webcam preview + calibration wizard + gesture
mapping form. Reads the engine's SharedState for preview only -- it never
touches the camera directly (see engine.py)."""
from __future__ import annotations

import copy
import tkinter as tk
from tkinter import ttk
from typing import Callable

import cv2
from PIL import Image, ImageDraw, ImageTk

from . import config as config_mod
from .config import AppConfig
from .engine import Engine

_GESTURE_LABELS = {
    "blink_left": "Piscar olho A",
    "blink_right": "Piscar olho B",
    "blink_both": "Piscar os dois",
    "mouth_open": "Boca aberta",
    "eyebrow_raised": "Sobrancelha levantada",
}

_ACTION_LABELS = {
    "none": "(nenhuma)",
    "left_click": "Clique esquerdo",
    "right_click": "Clique direito",
    "double_click": "Duplo clique",
    "scroll_up": "Scroll cima",
    "scroll_down": "Scroll baixo",
}
_ACTION_BY_LABEL = {v: k for k, v in _ACTION_LABELS.items()}

_CAPTURE_META = {
    "up": {
        "axis": "y",
        "extreme": "min",
        "label": "Cima",
        "guide": "Mova a cabeça o máximo para cima e clique em Parar quando terminar.",
    },
    "down": {
        "axis": "y",
        "extreme": "max",
        "label": "Baixo",
        "guide": "Mova a cabeça o máximo para baixo e clique em Parar quando terminar.",
    },
    "left": {
        "axis": "x",
        "extreme": "min",
        "label": "Esquerda",
        "guide": "Mova a cabeça o máximo para a esquerda e clique em Parar quando terminar.",
    },
    "right": {
        "axis": "x",
        "extreme": "max",
        "label": "Direita",
        "guide": "Mova a cabeça o máximo para a direita e clique em Parar quando terminar.",
    },
}

_METRIC_TO_GESTURE = {
    "ear_a": "blink_left",
    "ear_b": "blink_right",
    "mouth_open_ratio": "mouth_open",
    "eyebrow_raise_ratio": "eyebrow_raised",
}
_METRIC_BAR_LABELS = {
    "ear_a": "Olho A",
    "ear_b": "Olho B",
    "mouth_open_ratio": "Boca aberta",
    "eyebrow_raise_ratio": "Sobrancelha levantada",
}


class ConfigWindow:
    def __init__(
        self,
        root: tk.Tk,
        engine: Engine,
        config: AppConfig,
        config_path: str,
        on_start: Callable[[AppConfig], None],
    ) -> None:
        self._root = root
        self._engine = engine
        self._config = copy.deepcopy(config)
        self._config_path = config_path
        self._on_start = on_start
        self._tk_image = None
        self._after_id = None

        self._recording_direction: str | None = None
        self._recording_extreme: float | None = None
        self._capture_buttons: dict[str, ttk.Button] = {}

        root.title("FaceMesh Mouse - Configuracao")
        root.protocol("WM_DELETE_WINDOW", self._start_and_hide)

        self._build_widgets()
        self._tick()

    # -- widgets ----------------------------------------------------
    def _build_widgets(self) -> None:
        main = ttk.Frame(self._root, padding=10)
        main.grid(row=0, column=0, sticky="nsew")

        self._canvas = tk.Label(main)
        self._canvas.grid(row=0, column=0, rowspan=30, padx=(0, 10), sticky="n")

        row = 0
        row = self._build_step1_calibration(main, row)
        row = self._build_step2_gestures(main, row)
        row = self._build_step3_start(main, row)

    def _section_header(self, main: ttk.Frame, row: int, text: str) -> int:
        ttk.Label(main, text=text, font=("Segoe UI", 10, "bold")).grid(
            row=row, column=1, sticky="w", pady=(10, 2)
        )
        return row + 1

    def _help_text(self, main: ttk.Frame, row: int, text: str) -> int:
        ttk.Label(main, text=text, justify="left", wraplength=320).grid(
            row=row, column=1, sticky="w", pady=(0, 4)
        )
        return row + 1

    # -- step 1: calibration ------------------------------------------
    def _build_step1_calibration(self, main: ttk.Frame, row: int) -> int:
        row = self._section_header(main, row, "1. Calibrar movimento")
        row = self._help_text(
            main,
            row,
            "Grave os 4 extremos do movimento da cabeça: aperte Gravar, mova "
            "a cabeça até o limite desejado e aperte Parar. Ajuste as barras "
            "abaixo se o cursor estiver muito sensível ou tremendo.",
        )

        cal_frame = ttk.Frame(main)
        cal_frame.grid(row=row, column=1, sticky="w")
        for col, direction in enumerate(["up", "down", "left", "right"]):
            btn = ttk.Button(
                cal_frame,
                text=f"▶ Gravar {_CAPTURE_META[direction]['label']}",
                command=lambda d=direction: self._toggle_capture(d),
            )
            btn.grid(row=col // 2, column=col % 2, padx=2, pady=2, sticky="w")
            self._capture_buttons[direction] = btn
        row += 1

        self._capture_guide = tk.StringVar(value="")
        ttk.Label(main, textvariable=self._capture_guide, justify="left", wraplength=320).grid(
            row=row, column=1, sticky="w"
        )
        row += 1

        self._capture_live = tk.StringVar(value="")
        ttk.Label(main, textvariable=self._capture_live).grid(row=row, column=1, sticky="w")
        row += 1

        self._cal_status = tk.StringVar(value=self._calibration_status_text())
        ttk.Label(main, textvariable=self._cal_status, justify="left").grid(
            row=row, column=1, sticky="w", pady=(0, 8)
        )
        row += 1

        self._deadzone_var = tk.DoubleVar(value=self._config.calibration.deadzone_px)
        ttk.Label(main, text="Zona morta (ignora tremores pequenos):").grid(
            row=row, column=1, sticky="w"
        )
        row += 1
        deadzone_row = ttk.Frame(main)
        deadzone_row.grid(row=row, column=1, sticky="w")
        ttk.Scale(
            deadzone_row,
            from_=0,
            to=15,
            orient="horizontal",
            length=180,
            variable=self._deadzone_var,
            command=self._on_deadzone_change,
        ).grid(row=0, column=0)
        self._deadzone_label = ttk.Label(deadzone_row, text=self._deadzone_text())
        self._deadzone_label.grid(row=0, column=1, padx=(6, 0))
        row += 1

        self._sensitivity_var = tk.DoubleVar(value=self._config.calibration.sensitivity)
        ttk.Label(main, text="Sensibilidade (velocidade do cursor):").grid(
            row=row, column=1, sticky="w", pady=(6, 0)
        )
        row += 1
        sensitivity_row = ttk.Frame(main)
        sensitivity_row.grid(row=row, column=1, sticky="w")
        ttk.Scale(
            sensitivity_row,
            from_=0.3,
            to=3.0,
            orient="horizontal",
            length=180,
            variable=self._sensitivity_var,
            command=self._on_sensitivity_change,
        ).grid(row=0, column=0)
        self._sensitivity_label = ttk.Label(sensitivity_row, text=self._sensitivity_text())
        self._sensitivity_label.grid(row=0, column=1, padx=(6, 0))
        row += 1

        return row

    def _calibration_status_text(self) -> str:
        cal = self._config.calibration
        return (
            f"x: [{cal.x_min:.2f}, {cal.x_max:.2f}]  "
            f"y: [{cal.y_min:.2f}, {cal.y_max:.2f}]"
        )

    def _deadzone_text(self) -> str:
        return f"{self._config.calibration.deadzone_px:.0f}px"

    def _sensitivity_text(self) -> str:
        return f"{self._config.calibration.sensitivity:.1f}x"

    def _on_deadzone_change(self, _value=None) -> None:
        self._config.calibration.deadzone_px = round(self._deadzone_var.get(), 1)
        self._deadzone_label.configure(text=self._deadzone_text())

    def _on_sensitivity_change(self, _value=None) -> None:
        self._config.calibration.sensitivity = round(self._sensitivity_var.get(), 2)
        self._sensitivity_label.configure(text=self._sensitivity_text())

    # -- calibration capture (play/pause) ------------------------------
    def _toggle_capture(self, direction: str) -> None:
        if self._recording_direction == direction:
            self._stop_capture()
        else:
            self._start_capture(direction)

    def _start_capture(self, direction: str) -> None:
        _frame, metrics = self._engine.state.snapshot()
        if metrics is None:
            return
        meta = _CAPTURE_META[direction]
        seed = metrics.nose_y if meta["axis"] == "y" else metrics.nose_x
        self._recording_direction = direction
        self._recording_extreme = seed
        for d, btn in self._capture_buttons.items():
            if d == direction:
                btn.configure(text="⏸ Parar")
            else:
                btn.configure(state="disabled")
        self._capture_guide.set(meta["guide"])
        self._update_live_extreme_label()

    def _stop_capture(self) -> None:
        if self._recording_direction is None:
            return
        direction = self._recording_direction
        cal = self._config.calibration
        if direction == "up":
            cal.y_min = self._recording_extreme
        elif direction == "down":
            cal.y_max = self._recording_extreme
        elif direction == "left":
            cal.x_min = self._recording_extreme
        elif direction == "right":
            cal.x_max = self._recording_extreme

        self._recording_direction = None
        self._recording_extreme = None
        for d, btn in self._capture_buttons.items():
            btn.configure(state="normal", text=f"▶ Gravar {_CAPTURE_META[d]['label']}")
        self._capture_guide.set("")
        self._capture_live.set("")
        self._cal_status.set(self._calibration_status_text())

    def _update_live_extreme_label(self) -> None:
        if self._recording_direction is None:
            return
        self._capture_live.set(f"Extremo atual: {self._recording_extreme:.3f}")

    # -- step 2: gesture mapping ---------------------------------------
    def _build_step2_gestures(self, main: ttk.Frame, row: int) -> int:
        row = self._section_header(main, row, "2. Mapear gestos")
        row = self._help_text(
            main,
            row,
            "Pisque cada olho e observe qual barra reage abaixo antes de "
            "mapear (rótulo 'A'/'B' é só interno). Escolha o que cada gesto "
            "faz; '(nenhuma)' desativa o gesto.",
        )

        self._metric_bar_vars: dict[str, tk.DoubleVar] = {}
        for key in ["ear_a", "ear_b", "mouth_open_ratio", "eyebrow_raise_ratio"]:
            bar_row = ttk.Frame(main)
            bar_row.grid(row=row, column=1, sticky="w", pady=1)
            ttk.Label(bar_row, text=_METRIC_BAR_LABELS[key], width=18).grid(row=0, column=0)
            var = tk.DoubleVar(value=0.0)
            self._metric_bar_vars[key] = var
            ttk.Progressbar(
                bar_row,
                orient="horizontal",
                length=150,
                mode="determinate",
                maximum=100,
                variable=var,
            ).grid(row=0, column=1)
            row += 1

        self._action_vars: dict[str, tk.StringVar] = {}
        for gesture_name in config_mod.GESTURE_NAMES:
            gframe = ttk.Frame(main)
            gframe.grid(row=row, column=1, sticky="w", pady=2)
            ttk.Label(gframe, text=_GESTURE_LABELS[gesture_name], width=22).grid(row=0, column=0)
            current_action = self._config.gestures[gesture_name].action
            var = tk.StringVar(value=_ACTION_LABELS[current_action])
            self._action_vars[gesture_name] = var
            combo = ttk.Combobox(
                gframe,
                textvariable=var,
                values=list(_ACTION_LABELS.values()),
                state="readonly",
                width=18,
            )
            combo.grid(row=0, column=1)
            row += 1

        return row

    # -- step 3: start ---------------------------------------------------
    def _build_step3_start(self, main: ttk.Frame, row: int) -> int:
        row = self._section_header(main, row, "3. Iniciar")
        row = self._help_text(
            main,
            row,
            "Ao iniciar, esta janela some e o cursor passa a seguir a "
            "cabeça. Ctrl+Alt+P pausa/retoma a qualquer momento -- use pra "
            "'levantar o mouse': o cursor congela, reposicione a cabeça numa "
            "posição confortável e retome; o controle continua exatamente de "
            "onde parou, sem pular. Ctrl+Alt+O reabre esta janela.",
        )

        ttk.Button(
            main, text="▶ Iniciar controle do mouse", command=self._start_and_hide
        ).grid(row=row, column=1, sticky="e", pady=(6, 0))
        row += 1
        return row

    # -- live preview loop ---------------------------------------------
    def _tick(self) -> None:
        frame, metrics = self._engine.state.snapshot()
        if frame is not None:
            display = frame.copy()
            if metrics is not None:
                self._draw_overlay(display, metrics)
                self._update_metric_bars(metrics)
                if self._recording_direction is not None:
                    self._track_capture_extreme(metrics)
            rgb = cv2.cvtColor(display, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(rgb)
            self._tk_image = ImageTk.PhotoImage(image=img)
            self._canvas.configure(image=self._tk_image)

        self._after_id = self._root.after(33, self._tick)

    def _update_metric_bars(self, metrics) -> None:
        values = {
            "ear_a": metrics.ear_a,
            "ear_b": metrics.ear_b,
            "mouth_open_ratio": metrics.mouth_open_ratio,
            "eyebrow_raise_ratio": metrics.eyebrow_raise_ratio,
        }
        for key, value in values.items():
            gesture_name = _METRIC_TO_GESTURE[key]
            threshold = self._config.gestures[gesture_name].threshold or 1e-6
            pct = max(0.0, min(100.0, (value / threshold) * 100.0))
            self._metric_bar_vars[key].set(pct)

    def _track_capture_extreme(self, metrics) -> None:
        meta = _CAPTURE_META[self._recording_direction]
        live_value = metrics.nose_y if meta["axis"] == "y" else metrics.nose_x
        if meta["extreme"] == "min":
            self._recording_extreme = min(self._recording_extreme, live_value)
        else:
            self._recording_extreme = max(self._recording_extreme, live_value)
        self._update_live_extreme_label()

    def _draw_overlay(self, frame, metrics) -> None:
        h, w = frame.shape[:2]
        cx, cy = int(metrics.nose_x * w), int(metrics.nose_y * h)
        cv2.circle(frame, (cx, cy), 5, (0, 0, 255), -1)

    # -- lifecycle ----------------------------------------------------
    def _start_and_hide(self) -> None:
        for gesture_name, var in self._action_vars.items():
            self._config.gestures[gesture_name].action = _ACTION_BY_LABEL[var.get()]
        config_mod.save_config(self._config_path, self._config)
        self._on_start(self._config)
        self._root.withdraw()

    def show(self) -> None:
        self._root.deiconify()
        self._root.lift()
