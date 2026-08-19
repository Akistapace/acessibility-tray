import { BackendProcess } from "../services/backendProcess";
import { wireBackendRelay } from "./relay";
import { registerConfigIpc } from "./config.ipc";
import { registerButtonsIpc } from "./buttons.ipc";

export function wireIpc(backend: BackendProcess): void {
  wireBackendRelay(backend);
  registerConfigIpc();
  registerButtonsIpc();
}
