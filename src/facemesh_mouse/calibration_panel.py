"""The "Movimento" tab: cursor-tuning sliders.

Four-point calibration is gone -- the cursor now moves relatively, driven by
averaged optical-flow movement (see `point_tracker.py` and
`mouse_controller.py`), so there is nothing left to record. This tab just
tunes how that movement turns into cursor speed.
"""
from __future__ import annotations

import customtkinter as ctk

from .config import AppConfig
from .tracker import FaceMetrics

# field name -> (label, from_, to, description). Order here is the order the
# sliders are drawn in.
SLIDER_SPECS: dict[str, tuple[str, float, float, str]] = {
    "sensitivity_x": (
        "Sensibilidade horizontal",
        0.005,
        0.10,
        "Quanto o cursor anda para cada movimento horizontal da cabeça.",
    ),
    "sensitivity_y": (
        "Sensibilidade vertical",
        0.005,
        0.10,
        "Quanto o cursor anda para cada movimento vertical da cabeça. Costuma "
        "precisar ser maior que a horizontal, porque a cabeça se move menos "
        "na vertical.",
    ),
    "acceleration": (
        "Aceleração",
        0.0,
        1.0,
        "Deixa o cursor mais lento em movimentos pequenos e mais rápido em "
        "movimentos grandes. É o que permite mirar com precisão sem perder "
        "velocidade.",
    ),
    "motion_threshold_px": (
        "Limiar de movimento",
        0.0,
        10.0,
        "Ignora movimentos menores que isso, em pixels. Ajuda o cursor a "
        "parar completamente.",
    ),
}

# Per-field live-value formatting for the label next to each slider.
_VALUE_FORMATS = {
    "sensitivity_x": lambda value: f"{value:.3f}",
    "sensitivity_y": lambda value: f"{value:.3f}",
    "acceleration": lambda value: f"{value:.2f}",
    "motion_threshold_px": lambda value: f"{value:.1f} px",
    "dwell_time_s": lambda value: f"{value:.1f} s",
}

# Range for the dwell-click time slider, matching CALIBRATION_RANGES in
# config.py (kept separate, like the other sliders above, since the GUI
# owns its own widget ranges).
_DWELL_TIME_RANGE = (0.3, 5.0)


class CalibrationPanel:
    def __init__(self, parent, config: AppConfig) -> None:
        self._config = config
        self.sliders: dict[str, ctk.CTkSlider] = {}
        self._value_labels: dict[str, ctk.CTkLabel] = {}
        self.dwell_switch: ctk.CTkSwitch | None = None

        self.frame = ctk.CTkFrame(parent, fg_color="transparent")
        self._build()

    # -- widgets -------------------------------------------------------
    def _build(self) -> None:
        self.frame.grid_columnconfigure(0, weight=1)
        row = 0
        for field, (label, low, high, description) in SLIDER_SPECS.items():
            row = self._build_row(row, field, label, low, high, description)
        self._build_dwell_row(row)

    def _build_row(
        self, row: int, field: str, label: str, low: float, high: float, description: str
    ) -> int:
        ctk.CTkLabel(
            self.frame, text=label, anchor="w", font=("Segoe UI", 13, "bold")
        ).grid(row=row, column=0, sticky="ew", pady=(10, 2))
        row += 1

        holder = ctk.CTkFrame(self.frame, fg_color="transparent")
        holder.grid(row=row, column=0, sticky="w")
        row += 1

        value = getattr(self._config.calibration, field)
        value_label = ctk.CTkLabel(holder, text=_VALUE_FORMATS[field](value), width=60)

        def on_change(new_value, field=field, value_label=value_label) -> None:
            value_label.configure(text=_VALUE_FORMATS[field](float(new_value)))

        # Bounded width rather than letting the slider stretch to fill the
        # tab -- unbounded sliders were what pushed the window content past
        # the screen width.
        slider = ctk.CTkSlider(holder, from_=low, to=high, width=220, command=on_change)
        slider.set(value)
        slider.grid(row=0, column=0, sticky="w")
        value_label.grid(row=0, column=1, padx=(8, 0), sticky="w")

        self.sliders[field] = slider
        self._value_labels[field] = value_label

        ctk.CTkLabel(
            self.frame,
            text=description,
            justify="left",
            wraplength=380,
            anchor="w",
            text_color="gray70",
        ).grid(row=row, column=0, sticky="ew", pady=(0, 4))
        row += 1

        return row

    def _build_dwell_row(self, row: int) -> int:
        self.dwell_switch = ctk.CTkSwitch(
            self.frame, text="Clique por permanência (dwell click)"
        )
        if self._config.calibration.dwell_click_enabled:
            self.dwell_switch.select()
        else:
            self.dwell_switch.deselect()
        self.dwell_switch.grid(row=row, column=0, sticky="w", pady=(14, 2))
        row += 1

        ctk.CTkLabel(
            self.frame,
            text="Clica sozinho quando o cursor fica parado em cima de um "
            "elemento, sem precisar de nenhum gesto.",
            justify="left",
            wraplength=380,
            anchor="w",
            text_color="gray70",
        ).grid(row=row, column=0, sticky="ew", pady=(0, 4))
        row += 1

        return self._build_row(
            row,
            "dwell_time_s",
            "Tempo até clicar",
            _DWELL_TIME_RANGE[0],
            _DWELL_TIME_RANGE[1],
            "Quanto tempo o cursor precisa ficar parado antes do clique automático.",
        )

    # -- config sync ------------------------------------------------------
    def apply_to_config(self) -> None:
        cal = self._config.calibration
        cal.sensitivity_x = round(self.sliders["sensitivity_x"].get(), 4)
        cal.sensitivity_y = round(self.sliders["sensitivity_y"].get(), 4)
        cal.acceleration = round(self.sliders["acceleration"].get(), 2)
        cal.motion_threshold_px = round(self.sliders["motion_threshold_px"].get(), 1)
        cal.dwell_time_s = round(self.sliders["dwell_time_s"].get(), 1)
        cal.dwell_click_enabled = bool(self.dwell_switch.get())

    # -- per-frame ------------------------------------------------------
    def update(self, metrics: FaceMetrics) -> None:
        # No-op: this tab has no live readouts any more (the old capture
        # flow was the only thing that consumed per-frame metrics here).
        # Kept so the shell can call it every frame the same way it calls
        # GesturePanel.update without special-casing this tab.
        pass
