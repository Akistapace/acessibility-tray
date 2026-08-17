import { cpSync, existsSync } from "node:fs";

// HTML/CSS live alongside the renderer .ts sources and load the compiled
// .js next to them at runtime -- tsc only emits the .js, so the rest of
// the directory has to be copied into dist separately.
// src/renderer itself doesn't exist yet the first few times this script
// runs (renderer sources start in Task 11) -- skip it until it does,
// same as the assets/ guard below.
if (existsSync("src/renderer")) {
  cpSync("src/renderer", "dist/renderer", {
    recursive: true,
    filter: (source) => !source.endsWith(".ts"),
  });
}

// electron/assets (tray icons, added in the Tray task) doesn't exist yet
// the first few times this script runs -- skip it until it does.
if (existsSync("assets")) {
  cpSync("assets", "dist/assets", { recursive: true });
}
