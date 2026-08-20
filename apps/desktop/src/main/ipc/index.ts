import type { BackendServer } from "../services/backendServer";
import { wireBackendRelay } from "./relay";
import { registerConfigIpc } from "./config.ipc";
import { registerButtonsIpc } from "./buttons.ipc";

export function wireIpc(backend: BackendServer): void {
  wireBackendRelay(backend);
  registerConfigIpc();
  registerButtonsIpc();
}
