export const GESTURE_NAMES = [
  "blink_a",
  "blink_b",
  "blink_both",
  "eyebrow_a",
  "eyebrow_b",
  "eyebrow_both",
  "mouth_open",
  "mouth_left",
  "mouth_right",
] as const;

export const GESTURE_LABELS: Record<string, string> = {
  blink_a: "Piscar olho esquerdo",
  blink_b: "Piscar olho direito",
  blink_both: "Piscar os dois olhos",
  eyebrow_a: "Sobrancelha esquerda",
  eyebrow_b: "Sobrancelha direita",
  eyebrow_both: "As duas sobrancelhas",
  mouth_open: "Boca aberta",
  mouth_left: "Boca fechada p/ esquerda",
  mouth_right: "Boca fechada p/ direita",
};

export const ACTION_LABELS: Record<string, string> = {
  none: "(nenhuma)",
  left_click: "Clique esquerdo",
  right_click: "Clique direito",
  double_click: "Duplo clique",
  scroll_up: "Scroll cima",
  scroll_down: "Scroll baixo",
  left_drag: "Clicar e arrastar (segurar)",
  freeze_cursor: "Congelar cursor (alternar)",
};
