import { contextBridge, ipcRenderer, IpcRendererEvent } from "electron";

contextBridge.exposeInMainWorld("backend", {
  send: (message: Record<string, unknown>) => ipcRenderer.send("backend:send", message),
  on: (channel: string, callback: (message: unknown) => void) => {
    const listener = (_event: IpcRendererEvent, message: unknown) => callback(message);
    ipcRenderer.on(`backend:${channel}`, listener);
    return () => ipcRenderer.removeListener(`backend:${channel}`, listener);
  },
});
