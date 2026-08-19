import { app } from "electron";

// App-level runtime config, distinct from services/config.service.ts's
// user-facing calibration/gesture config persistence.
export const isPackaged = app.isPackaged;
export const resourcesPath = process.resourcesPath;
// The directory containing this package's package.json (apps/desktop in
// dev, the packaged app's resources root once packaged) -- used by
// backendCommand.ts to find the repo-root run.py in dev mode. See that
// module for why this replaced a __dirname-relative computation.
export const appPath = app.getAppPath();
export const CONFIG_PATH = "config.json";
