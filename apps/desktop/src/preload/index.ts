import { contextBridge, ipcRenderer, IpcRendererEvent } from "electron";

contextBridge.exposeInMainWorld("backend", {
  send: (message: Record<string, unknown>) => ipcRenderer.send("backend:send", message),
  on: (channel: string, callback: (message: unknown) => void) => {
    const listener = (_event: IpcRendererEvent, message: unknown) => callback(message);
    ipcRenderer.on(`backend:${channel}`, listener);
    return () => ipcRenderer.removeListener(`backend:${channel}`, listener);
  },
});

contextBridge.exposeInMainWorld("tracking", {
  sendFrame: (frame: Record<string, unknown>) => ipcRenderer.send("tracking:frame", frame),
  cameraError: () => ipcRenderer.send("tracking:camera-error"),
  onSetPreview: (callback: (enabled: boolean) => void) => {
    const listener = (_event: IpcRendererEvent, enabled: boolean) => callback(enabled);
    ipcRenderer.on("tracking:set-preview", listener);
    return () => ipcRenderer.removeListener("tracking:set-preview", listener);
  },
  onHighlightGesture: (callback: (gesture: string | null) => void) => {
    const listener = (_event: IpcRendererEvent, gesture: string | null) => callback(gesture);
    ipcRenderer.on("tracking:highlight-gesture", listener);
    return () => ipcRenderer.removeListener("tracking:highlight-gesture", listener);
  },
});
