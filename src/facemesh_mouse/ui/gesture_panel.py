"""The "Gestos" tab: one row per gesture, each showing how close that gesture
is to firing, which mouse action it triggers, and how long it must be held.

The live bars are driven by `gestures.trigger_progress`, the same function
the detector's threshold logic is written against, so a bar reflects both
which direction means "closer to firing" and whether the gesture is
currently reachable at all -- a gesture blocked by another gesture's
exclusion clause (e.g. blink_a while both eyes are closed) reads 0.0 instead
of a misleading full bar.
"""
from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass

import customtkinter as ctk

from ..modules import config as config_mod
from ..modules.config import AppConfig
from ..modules.gestures import trigger_progress
from ..modules.tracker import FaceMetrics

GESTURE_LABELS = {
    "blink_a": "Piscar olho A",
    "blink_b": "Piscar olho B",
    "blink_both": "Piscar os dois olhos",
    "eyebrow_a": "Sobrancelha A",
    "eyebrow_b": "Sobrancelha B",
    "eyebrow_both": "As duas sobrancelhas",
    "mouth_open": "Boca aberta",
    "mouth_left": "Boca fechada p/ esquerda",
    "mouth_right": "Boca fechada p/ direita",
}

ACTION_LABELS = {
    "none": "(nenhuma)",
    "left_click": "Clique esquerdo",
    "right_click": "Clique direito",
    "double_click": "Duplo clique",
    "scroll_up": "Scroll cima",
    "scroll_down": "Scroll baixo",
    "left_drag": "Clicar e arrastar (segurar)",
    "freeze_cursor": "Congelar cursor (segurar)",
}
ACTION_BY_LABEL = {label: action for action, label in ACTION_LABELS.items()}

# Actions where the interval slider means "repita a cada X ms enquanto
# segurar" instead of "espere X ms antes de aceitar o próximo disparo" --
# same field (cooldown_ms), different framing depending on the action.
_REPEATING_ACTIONS = {"scroll_up", "scroll_down"}

_HELP = (
    "A barra enche conforme você se aproxima de disparar o gesto. Os rótulos "
    "A e B dos olhos e das sobrancelhas são internos: faça o gesto e veja qual "
    "barra reage. O tempo de espera é quanto você precisa segurar a expressão "
    "para ela valer -- é o que impede piscadas naturais de virarem cliques. "
    "Em scroll, o intervalo abaixo também controla a repetição: segurando o "
    "gesto, o scroll continua rolando a cada intervalo em vez de precisar "
    "soltar e refazer. Em \"clicar e arrastar\", o botão fica pressionado "
    "enquanto o gesto for mantido e solta quando ele for desfeito. Em "
    "\"congelar cursor\", o mouse para 100% enquanto o gesto for mantido -- "
    "útil pra rolar ou selecionar com precisão sem o cursor balançar -- e "
    "volta a seguir a cabeça quando o gesto for desfeito."
)


def _cooldown_caption(action: str) -> str:
    if action in _REPEATING_ACTIONS:
        return "Repetição (enquanto o gesto ficar segurado):"
    return "Intervalo mínimo entre disparos:"


@dataclass
class GestureRow:
    bar: ctk.CTkProgressBar
    action_var: ctk.StringVar
    hold_var: ctk.IntVar
    cooldown_var: ctk.IntVar


class GesturePanel:
    def __init__(self, parent: tk.Misc, config: AppConfig) -> None:
        self._config = config
        self.rows: dict[str, GestureRow] = {}

        self.frame = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        self._build()

    def _build(self) -> None:
        self.frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self.frame,
            text=_HELP,
            justify="left",
            wraplength=380,
            anchor="w",
            text_color="gray70",
        ).grid(row=0, column=0, sticky="ew", pady=(4, 10))

        for index, name in enumerate(config_mod.GESTURE_NAMES, start=1):
            self.rows[name] = self._build_row(index, name)

    def _build_row(self, row: int, name: str) -> GestureRow:
        gesture_cfg = self._config.gestures[name]

        holder = ctk.CTkFrame(self.frame)
        holder.grid(row=row, column=0, sticky="ew", pady=4)
        holder.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            holder, text=GESTURE_LABELS[name], anchor="w", font=("Segoe UI", 13, "bold")
        ).grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 2))

        bar = ctk.CTkProgressBar(holder, height=10)
        bar.set(0.0)
        bar.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 8))

        controls = ctk.CTkFrame(holder, fg_color="transparent")
        controls.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 8))
        controls.grid_columnconfigure(1, weight=1)

        action_var = ctk.StringVar(value=ACTION_LABELS[gesture_cfg.action])

        cooldown_caption = ctk.CTkLabel(
            controls, text=_cooldown_caption(gesture_cfg.action), anchor="w", text_color="gray70"
        )

        def on_action_change(selected_label, caption=cooldown_caption) -> None:
            caption.configure(text=_cooldown_caption(ACTION_BY_LABEL[selected_label]))

        ctk.CTkOptionMenu(
            controls,
            variable=action_var,
            values=list(ACTION_LABELS.values()),
            width=150,
            command=on_action_change,
        ).grid(row=0, column=0, sticky="w")

        hold_var = ctk.IntVar(value=gesture_cfg.hold_ms)
        hold_label = ctk.CTkLabel(controls, text=f"{gesture_cfg.hold_ms} ms", width=64)

        def on_hold(value, label=hold_label, var=hold_var) -> None:
            var.set(int(float(value)))
            label.configure(text=f"{var.get()} ms")

        hold_slider = ctk.CTkSlider(
            controls, from_=0, to=1000, number_of_steps=20, command=on_hold
        )
        hold_slider.set(gesture_cfg.hold_ms)  # start at the saved value
        hold_slider.grid(row=0, column=1, sticky="ew", padx=8)
        hold_label.grid(row=0, column=2, sticky="e")

        cooldown_caption.grid(row=1, column=0, sticky="w", pady=(6, 0))

        cooldown_var = ctk.IntVar(value=gesture_cfg.cooldown_ms)
        cooldown_label = ctk.CTkLabel(controls, text=f"{gesture_cfg.cooldown_ms} ms", width=64)

        def on_cooldown(value, label=cooldown_label, var=cooldown_var) -> None:
            var.set(int(float(value)))
            label.configure(text=f"{var.get()} ms")

        cooldown_slider = ctk.CTkSlider(
            controls, from_=50, to=1500, number_of_steps=29, command=on_cooldown
        )
        cooldown_slider.set(gesture_cfg.cooldown_ms)  # start at the saved value
        cooldown_slider.grid(row=1, column=1, sticky="ew", padx=8, pady=(6, 0))
        cooldown_label.grid(row=1, column=2, sticky="e", pady=(6, 0))

        return GestureRow(bar=bar, action_var=action_var, hold_var=hold_var, cooldown_var=cooldown_var)

    def update(self, metrics: FaceMetrics) -> None:
        for name, row in self.rows.items():
            threshold = self._config.gestures[name].threshold
            row.bar.set(trigger_progress(name, metrics, threshold))

    def apply_to_config(self) -> None:
        for name, row in self.rows.items():
            gesture_cfg = self._config.gestures[name]
            gesture_cfg.action = ACTION_BY_LABEL[row.action_var.get()]
            gesture_cfg.hold_ms = int(row.hold_var.get())
            gesture_cfg.cooldown_ms = int(row.cooldown_var.get())
