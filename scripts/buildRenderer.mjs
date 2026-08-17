import { existsSync, readdirSync } from "node:fs";
import { execFileSync } from "node:child_process";

function hasTypeScriptFiles(dir) {
  if (!existsSync(dir)) return false;
  for (const entry of readdirSync(dir, { withFileTypes: true, recursive: true })) {
    if (entry.isFile() && entry.name.endsWith(".ts")) return true;
  }
  return false;
}

if (hasTypeScriptFiles("src/renderer")) {
  execFileSync(process.execPath, ["node_modules/typescript/bin/tsc", "-p", "tsconfig.renderer.json"], {
    stdio: "inherit",
  });
} else {
  console.log("No renderer TypeScript files yet -- skipping tsconfig.renderer.json build.");
}
