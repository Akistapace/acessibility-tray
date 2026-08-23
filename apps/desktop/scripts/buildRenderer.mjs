import { existsSync, readdirSync } from "node:fs";
import * as esbuild from "esbuild";

function hasTypeScriptFiles(dir) {
  if (!existsSync(dir)) return false;
  for (const entry of readdirSync(dir, { withFileTypes: true, recursive: true })) {
    if (entry.isFile() && entry.name.endsWith(".ts")) return true;
  }
  return false;
}

const RENDERER_ENTRIES = ["buttons", "config", "keyboard", "overlay", "tracking"];

if (hasTypeScriptFiles("src/renderer")) {
  const entryPoints = RENDERER_ENTRIES.filter((name) => existsSync(`src/renderer/${name}/index.ts`)).map(
    (name) => `src/renderer/${name}/index.ts`,
  );

  await esbuild.build({
    entryPoints,
    outbase: "src/renderer",
    outdir: "dist/renderer",
    bundle: true,
    format: "iife",
    platform: "browser",
    target: "es2022",
    // @techstark/opencv-js ships a single Emscripten UMD bundle for both Node
    // and the browser, gated at runtime by an ENVIRONMENT_IS_NODE check. Its
    // dead Node-only branch does `require("fs")`/`require("crypto")`, which
    // esbuild would otherwise fail to resolve when bundling for the browser.
    // Marking them external leaves those calls un-bundled; they're never
    // reached at runtime here since the renderer always resolves ENVIRONMENT_IS_NODE
    // false.
    external: ["fs", "crypto"],
  });
} else {
  console.log("No renderer TypeScript files yet -- skipping renderer bundle.");
}
