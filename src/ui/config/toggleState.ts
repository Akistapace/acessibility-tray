export interface ToggleStatus {
  control_enabled: boolean;
  paused: boolean;
}

export interface ToggleState {
  statusText: string;
  buttonText: string;
  nextCommand: "start" | "resume" | "stop";
}

export function computeToggleState(status: ToggleStatus): ToggleState {
  if (!status.control_enabled) {
    return {
      statusText: "Controle parado",
      buttonText: "Iniciar controle do mouse",
      nextCommand: "start",
    };
  }
  if (status.paused) {
    return {
      statusText: "Controle pausado",
      buttonText: "Retomar controle do mouse",
      nextCommand: "resume",
    };
  }
  return {
    statusText: "Controle ativo",
    buttonText: "Parar controle do mouse",
    nextCommand: "stop",
  };
}
