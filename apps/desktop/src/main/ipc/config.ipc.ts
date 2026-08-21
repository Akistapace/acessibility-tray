import { mainRelay } from "./relay";
import { resetButtonsPosition } from "../windows/buttonsWindow";

export function registerConfigIpc(): void {
  mainRelay.on("config:reset-position", () => {
    resetButtonsPosition();
  });
}
