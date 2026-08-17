import { cpSync, existsSync } from "node:fs";

if (existsSync("src/ui")) {
  cpSync("src/ui", "dist/ui", {
    recursive: true,
    filter: (source) => !source.endsWith(".ts"),
  });
}

if (existsSync("assets")) {
  cpSync("assets", "dist/assets", { recursive: true });
}
