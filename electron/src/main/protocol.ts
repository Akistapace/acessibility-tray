// Newline-delimited JSON protocol shared with the Python backend's
// modules/ipc_protocol.py. One JSON object per line; a malformed line is
// dropped rather than thrown, matching the Python side's philosophy that
// one bad message must never kill the connection.

export interface FrameMessage {
  type: "frame";
  jpeg_b64: string;
  gesture_progress: Record<string, number>;
  seq: number;
}

export interface StatusMessage {
  type: "status";
  control_enabled: boolean;
  paused: boolean;
  no_face: boolean;
  yielded: boolean;
}

export interface ActionMessage {
  type: "action";
  gesture: string;
  action: string;
  x: number;
  y: number;
}

export interface KeyboardResultMessage {
  type: "keyboard_result";
  opened: boolean;
  x: number;
  y: number;
}

export interface ErrorMessage {
  type: "error";
  message: string;
}

export type BackendMessage =
  | FrameMessage
  | StatusMessage
  | ActionMessage
  | KeyboardResultMessage
  | ErrorMessage;

export function encodeMessage(message: Record<string, unknown>): string {
  return JSON.stringify(message) + "\n";
}

export function parseLines(
  chunk: string,
  leftover: string
): { messages: BackendMessage[]; leftover: string } {
  const combined = leftover + chunk;
  const lines = combined.split("\n");
  const newLeftover = lines.pop() ?? "";
  const messages: BackendMessage[] = [];
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    try {
      messages.push(JSON.parse(trimmed) as BackendMessage);
    } catch {
      continue;
    }
  }
  return { messages, leftover: newLeftover };
}
