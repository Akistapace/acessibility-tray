import { cpSync, existsSync } from "node:fs";

if (existsSync("src/renderer")) {
  cpSync("src/renderer", "dist/renderer", {
    recursive: true,
    filter: (source) => !source.endsWith(".ts"),
  });
}

if (existsSync("assets")) {
  cpSync("assets", "dist/assets", { recursive: true });
}
