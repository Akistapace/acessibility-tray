import { mainRelay } from "./relay";
import { moveKeyboardWindow, endKeyboardDrag, hideKeyboardWindow } from "../windows/keyboardWindow";
import { typeText, pressBackspace, pressEnter } from "../services/keyboard.service";

export function registerKeyboardIpc(): void {
  mainRelay.on("keyboard:type", (message: { text: string }) => {
    void typeText(message.text);
  });
  mainRelay.on("keyboard:backspace", () => {
    void pressBackspace();
  });
  mainRelay.on("keyboard:enter", () => {
    void pressEnter();
  });
  mainRelay.on("keyboard:drag-move", (message: { dx: number; dy: number }) => {
    moveKeyboardWindow(message.dx, message.dy);
  });
  mainRelay.on("keyboard:drag-end", () => {
    endKeyboardDrag();
  });
  mainRelay.on("keyboard:close", () => {
    hideKeyboardWindow();
  });
}
