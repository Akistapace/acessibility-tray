"""The "Movimento" tab: the four calibration capture toggles plus the
deadzone and sensitivity sliders.

The panel owns its recording state but never touches the camera -- the shell
feeds it one `FaceMetrics` per preview frame via `update`, and the running
extreme is seeded from the first frame after a capture starts.
"""
from __future__ import annotations

import customtkinter as ctk

from .config import AppConfig
from .tracker import FaceMetrics

CAPTURE_META = {
    "up": {
        "axis": "y",
        "extreme": "min",
        "label": "Cima",
        "guide": "Incline a cabeca o maximo para CIMA e clique em Parar.",
    },
    "down": {
        "axis": "y",
        "extreme": "max",
        "label": "Baixo",
        "guide": "Incline a cabeca o maximo para BAIXO e clique em Parar.",
    },
    "left": {
        "axis": "x",
        "extreme": "min",
        "label": "Esquerda",
        "guide": "Vire a cabeca o maximo para a ESQUERDA e clique em Parar.",
    },
    "right": {
        "axis": "x",
        "extreme": "max",
        "label": "Direita",
        "guide": "Vire a cabeca o maximo para a DIREITA e clique em Parar.",
    },
}

_HELP = (
    "Grave ate onde sua cabeca chega em cada direcao: clique em Gravar, mova "
    "a cabeca ate o limite confortavel e clique em Parar. O valor mais extremo "
    "durante a gravacao e o que fica salvo, entao nao precisa acertar o tempo "
    "do clique."
)


class CalibrationPanel:
    def __init__(self, parent, config: AppConfig) -> None:
        self._config = config
        self.recording_direction: str | None = None
        self.recording_extreme: float | None = None
        self.buttons: dict[str, ctk.CTkButton] = {}

        self.frame = ctk.CTkFrame(parent, fg_color="transparent")
        self._build()

    # -- widgets -------------------------------------------------------
    def _build(self) -> None:
        self.frame.grid_columnconfigure(0, weight=1)
        row = 0

        ctk.CTkLabel(
            self.frame,
            text=_HELP,
            justify="left",
            wraplength=380,
            anchor="w",
        ).grid(row=row, column=0, sticky="ew", pady=(4, 10))
        row += 1

        buttons = ctk.CTkFrame(self.frame, fg_color="transparent")
        buttons.grid(row=row, column=0, sticky="ew")
        buttons.grid_columnconfigure((0, 1), weight=1)
        for index, direction in enumerate(["up", "down", "left", "right"]):
            button = ctk.CTkButton(
                buttons,
                text=f"Gravar {CAPTURE_META[direction]['label']}",
                command=lambda d=direction: self.toggle_capture(d),
            )
            button.grid(row=index // 2, column=index % 2, padx=4, pady=4, sticky="ew")
            self.buttons[direction] = button
        row += 1

        self._guide_var = ctk.StringVar(value="")
        ctk.CTkLabel(
            self.frame,
            textvariable=self._guide_var,
            justify="left",
            wraplength=380,
            anchor="w",
            text_color="#4da3ff",
        ).grid(row=row, column=0, sticky="ew", pady=(10, 0))
        row += 1

        self._live_var = ctk.StringVar(value="")
        ctk.CTkLabel(self.frame, textvariable=self._live_var, anchor="w").grid(
            row=row, column=0, sticky="ew"
        )
        row += 1

        self._status_var = ctk.StringVar(value=self._status_text())
        ctk.CTkLabel(
            self.frame, textvariable=self._status_var, anchor="w", text_color="gray70"
        ).grid(row=row, column=0, sticky="ew", pady=(6, 12))
        row += 1

        self.deadzone_var = ctk.DoubleVar(value=self._config.calibration.deadzone_px)
        self._deadzone_label = self._slider_row(
            row,
            "Zona morta (ignora tremores pequenos)",
            self.deadzone_var,
            0,
            15,
            self._deadzone_text(),
            lambda _value=None: self.on_deadzone_change(),
        )
        row += 2

        self.sensitivity_var = ctk.DoubleVar(value=self._config.calibration.sensitivity)
        self._sensitivity_label = self._slider_row(
            row,
            "Sensibilidade (velocidade do cursor)",
            self.sensitivity_var,
            0.3,
            3.0,
            self._sensitivity_text(),
            lambda _value=None: self.on_sensitivity_change(),
        )

    def _slider_row(self, row, title, variable, low, high, value_text, command):
        ctk.CTkLabel(self.frame, text=title, anchor="w").grid(
            row=row, column=0, sticky="ew"
        )
        holder = ctk.CTkFrame(self.frame, fg_color="transparent")
        holder.grid(row=row + 1, column=0, sticky="ew", pady=(0, 10))
        holder.grid_columnconfigure(0, weight=1)
        ctk.CTkSlider(
            holder, from_=low, to=high, variable=variable, command=command
        ).grid(row=0, column=0, sticky="ew")
        value_label = ctk.CTkLabel(holder, text=value_text, width=60)
        value_label.grid(row=0, column=1, padx=(8, 0))
        return value_label

    # -- text helpers ---------------------------------------------------
    def _status_text(self) -> str:
        cal = self._config.calibration
        return (
            f"Faixa gravada -- x: [{cal.x_min:.2f}, {cal.x_max:.2f}]   "
            f"y: [{cal.y_min:.2f}, {cal.y_max:.2f}]"
        )

    def _deadzone_text(self) -> str:
        return f"{self._config.calibration.deadzone_px:.0f} px"

    def _sensitivity_text(self) -> str:
        return f"{self._config.calibration.sensitivity:.1f}x"

    # -- slider callbacks -----------------------------------------------
    def on_deadzone_change(self) -> None:
        self._config.calibration.deadzone_px = round(self.deadzone_var.get(), 1)
        self._deadzone_label.configure(text=self._deadzone_text())

    def on_sensitivity_change(self) -> None:
        self._config.calibration.sensitivity = round(self.sensitivity_var.get(), 2)
        self._sensitivity_label.configure(text=self._sensitivity_text())

    # -- capture --------------------------------------------------------
    def toggle_capture(self, direction: str) -> None:
        if self.recording_direction == direction:
            self.stop_capture()
        else:
            self.start_capture(direction)

    def start_capture(self, direction: str) -> None:
        self.recording_direction = direction
        self.recording_extreme = None  # seeded by the next update()
        for name, button in self.buttons.items():
            if name == direction:
                button.configure(text="Parar")
            else:
                button.configure(state="disabled")
        self._guide_var.set(CAPTURE_META[direction]["guide"])
        self._live_var.set("Aguardando o rosto aparecer...")

    def stop_capture(self) -> None:
        """Commits the recorded extreme into the calibration and resets."""
        direction = self.recording_direction
        if direction is None:
            return
        if self.recording_extreme is not None:
            cal = self._config.calibration
            if direction == "up":
                cal.y_min = self.recording_extreme
            elif direction == "down":
                cal.y_max = self.recording_extreme
            elif direction == "left":
                cal.x_min = self.recording_extreme
            elif direction == "right":
                cal.x_max = self.recording_extreme
        self._reset_capture()
        self._status_var.set(self._status_text())

    def cancel_capture(self) -> None:
        """Drops an in-progress recording WITHOUT writing it into the config.
        The user never confirmed it, so discarding is the safe default."""
        if self.recording_direction is None:
            return
        self._reset_capture()

    def _reset_capture(self) -> None:
        self.recording_direction = None
        self.recording_extreme = None
        for name, button in self.buttons.items():
            button.configure(
                state="normal", text=f"Gravar {CAPTURE_META[name]['label']}"
            )
        self._guide_var.set("")
        self._live_var.set("")

    # -- per-frame ------------------------------------------------------
    def update(self, metrics: FaceMetrics) -> None:
        if self.recording_direction is None:
            return
        meta = CAPTURE_META[self.recording_direction]
        value = metrics.nose_y if meta["axis"] == "y" else metrics.nose_x
        if self.recording_extreme is None:
            self.recording_extreme = value
        elif meta["extreme"] == "min":
            self.recording_extreme = min(self.recording_extreme, value)
        else:
            self.recording_extreme = max(self.recording_extreme, value)
        self._live_var.set(f"Extremo capturado: {self.recording_extreme:.3f}")
