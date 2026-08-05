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

        root.title("FaceMesh Mouse - Configuracao")
        root.protocol("WM_DELETE_WINDOW", self._start_and_hide)

        self._build_widgets()
        self._tick()

    # -- widgets ----------------------------------------------------
    def _build_widgets(self) -> None:
        main = ttk.Frame(self._root, padding=10)
        main.grid(row=0, column=0, sticky="nsew")

        self._canvas = tk.Label(main)
        self._canvas.grid(row=0, column=0, rowspan=8, padx=(0, 10))

        ttk.Label(
            main,
            text="Pisque cada olho e observe qual indicador reage\n"
            "abaixo antes de mapear (label 'A'/'B' e' so' interno).",
            justify="left",
        ).grid(row=0, column=1, sticky="w")

        self._metric_labels: dict[str, tk.StringVar] = {}
        row = 1
        for key in ["ear_a", "ear_b", "mouth_open_ratio", "eyebrow_raise_ratio"]:
            var = tk.StringVar(value=f"{key}: --")
            self._metric_labels[key] = var
            ttk.Label(main, textvariable=var).grid(row=row, column=1, sticky="w")
            row += 1

        ttk.Separator(main, orient="horizontal").grid(
            row=row, column=1, sticky="ew", pady=8
        )
        row += 1

        ttk.Label(main, text="Calibracao (posicione a cabeca e capture):").grid(
            row=row, column=1, sticky="w"
        )
        row += 1
        cal_frame = ttk.Frame(main)
        cal_frame.grid(row=row, column=1, sticky="w")
        ttk.Button(cal_frame, text="Capturar Cima", command=lambda: self._capture("up")).grid(row=0, column=0, padx=2)
        ttk.Button(cal_frame, text="Capturar Baixo", command=lambda: self._capture("down")).grid(row=0, column=1, padx=2)
        ttk.Button(cal_frame, text="Capturar Esquerda", command=lambda: self._capture("left")).grid(row=1, column=0, padx=2, pady=2)
        ttk.Button(cal_frame, text="Capturar Direita", command=lambda: self._capture("right")).grid(row=1, column=1, padx=2, pady=2)
        row += 1

        self._cal_status = tk.StringVar(value=self._calibration_status_text())
        ttk.Label(main, textvariable=self._cal_status, justify="left").grid(
            row=row, column=1, sticky="w"
        )
        row += 1

        ttk.Separator(main, orient="horizontal").grid(
            row=row, column=1, sticky="ew", pady=8
        )
        row += 1

        ttk.Label(main, text="Mapeamento gesto -> acao:").grid(
            row=row, column=1, sticky="w"
        )
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

        ttk.Button(main, text="Iniciar tracking", command=self._start_and_hide).grid(
            row=row, column=1, sticky="e", pady=(10, 0)
        )

    def _calibration_status_text(self) -> str:
        cal = self._config.calibration
        return (
            f"x: [{cal.x_min:.2f}, {cal.x_max:.2f}]  "
            f"y: [{cal.y_min:.2f}, {cal.y_max:.2f}]"
        )

    # -- calibration --------------------------------------------------
    def _capture(self, direction: str) -> None:
        _frame, metrics = self._engine.state.snapshot()
        if metrics is None:
            return
        cal = self._config.calibration
        if direction == "up":
            cal.y_min = metrics.nose_y
        elif direction == "down":
            cal.y_max = metrics.nose_y
        elif direction == "left":
            cal.x_min = metrics.nose_x
        elif direction == "right":
            cal.x_max = metrics.nose_x
        self._cal_status.set(self._calibration_status_text())

    # -- live preview loop ---------------------------------------------
    def _tick(self) -> None:
        frame, metrics = self._engine.state.snapshot()
        if frame is not None:
            display = frame.copy()
            if metrics is not None:
                self._draw_overlay(display, metrics)
                self._metric_labels["ear_a"].set(f"ear_a: {metrics.ear_a:.3f}")
                self._metric_labels["ear_b"].set(f"ear_b: {metrics.ear_b:.3f}")
                self._metric_labels["mouth_open_ratio"].set(
                    f"mouth_open_ratio: {metrics.mouth_open_ratio:.3f}"
                )
                self._metric_labels["eyebrow_raise_ratio"].set(
                    f"eyebrow_raise_ratio: {metrics.eyebrow_raise_ratio:.3f}"
                )
            rgb = cv2.cvtColor(display, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(rgb)
            self._tk_image = ImageTk.PhotoImage(image=img)
            self._canvas.configure(image=self._tk_image)

        self._after_id = self._root.after(33, self._tick)

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
