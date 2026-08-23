import { mainRelay } from "./relay";
import { resetButtonsPosition } from "../windows/buttonsWindow";
import { resetKeyboardPosition } from "../windows/keyboardWindow";

export function registerConfigIpc(): void {
  mainRelay.on("config:reset-position", () => {
    resetButtonsPosition();
    resetKeyboardPosition();
  });
}
