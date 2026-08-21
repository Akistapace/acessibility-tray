import { mainRelay } from "./relay";
import { moveButtonsWindow, endButtonsDrag } from "../windows/buttonsWindow";

// These two channels are re-emitted by ipc/relay.ts's mainRelay rather than
// delivered on the shared "backend:send" channel directly -- a raw listener
// there would also see every engine-lifecycle command (start, update_config,
// ...) and would need to filter them back out itself.
export function registerButtonsIpc(): void {
  mainRelay.on("buttons:drag-move", (message: { dx: number; dy: number }) => {
    moveButtonsWindow(message.dx, message.dy);
  });
  mainRelay.on("buttons:drag-end", () => {
    endButtonsDrag();
  });
}
