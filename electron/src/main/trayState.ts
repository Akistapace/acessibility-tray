export interface TrayStatus {
  control_enabled: boolean;
  paused: boolean;
  no_face: boolean;
  yielded: boolean;
}

export type TrayIconState = "running" | "paused" | "no_face" | "yielded";

export function computeTrayState(status: TrayStatus): { icon: TrayIconState; title: string } {
  if (status.paused) {
    return { icon: "paused", title: "FaceMesh Mouse -- Pausado" };
  }
  if (status.yielded) {
    return { icon: "yielded", title: "FaceMesh Mouse -- Controle pelo mouse físico" };
  }
  if (status.no_face) {
    return { icon: "no_face", title: "FaceMesh Mouse -- Rosto não detectado" };
  }
  return { icon: "running", title: "FaceMesh Mouse" };
}
