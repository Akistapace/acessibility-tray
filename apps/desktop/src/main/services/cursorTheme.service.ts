// Applies/restores the real Windows Arrow cursor via the same mechanism
// Windows' own Accessibility > Mouse pointer settings use: write a .cur
// file, point HKCU\Control Panel\Cursors\Arrow at it, and call
// SystemParametersInfoW(SPI_SETCURSORS) to reload it everywhere. Only the
// Arrow role is ever touched. A failure here must never affect tracking --
// same rule as win32.service.ts's touch-keyboard integration. Ported from
// cursor_theme.py -- see
// docs/superpowers/specs/2026-08-18-cursor-appearance-design.md.
//
// This file declares its own advapi32.dll/user32.dll koffi bindings rather
// than importing from win32.service.ts -- that file's scope is touch-keyboard
// specifically (one concern per service file). RegCreateKeyExW/RegSetValueExW
// are redeclared here with the exact same parameter-type spelling win32.
// service.ts uses, for consistency.
import koffi from "koffi";
import fs from "node:fs";
import path from "node:path";
import { buildCurBytesColor, buildCurBytesMista, VALID_CURSOR_MODES } from "./cursorImage";

const user32 = koffi.load("user32.dll");
const advapi32 = koffi.load("advapi32.dll");

const SystemParametersInfoW = user32.func(
  "bool SystemParametersInfoW(uint32 uiAction, uint32 uiParam, void *pvParam, uint32 fWinIni)"
);
const RegCreateKeyExW = advapi32.func(
  "long RegCreateKeyExW(void *hKey, const char16_t *lpSubKey, uint32 Reserved, void *lpClass, uint32 dwOptions, uint32 samDesired, void *lpSecurityAttributes, _Out_ void **phkResult, void *lpdwDisposition)"
);
const RegQueryValueExW = advapi32.func(
  "long RegQueryValueExW(void *hKey, const char16_t *lpValueName, void *lpReserved, _Out_ uint32 *lpType, _Out_ uint8_t *lpData, _Inout_ uint32 *lpcbData)"
);
const RegSetValueExW = advapi32.func(
  "long RegSetValueExW(void *hKey, const char16_t *lpValueName, uint32 Reserved, uint32 dwType, const uint8_t *lpData, uint32 cbData)"
);
const RegDeleteValueW = advapi32.func("long RegDeleteValueW(void *hKey, const char16_t *lpValueName)");
const RegCloseKey = advapi32.func("long RegCloseKey(void *hKey)");

const HKEY_CURRENT_USER = koffi.as(0x80000001, "void *");
const CURSORS_KEY = "Control Panel\\Cursors";
const ARROW_VALUE = "Arrow";
// Windows' own Ease of Access > Mouse pointer "Change pointer size" slider
// persists as this DWORD, and the shell scales EVERY loaded cursor to it at
// render time -- including a custom per-role override like ours. Writing a
// differently-sized .cur file to the Arrow value alone has no visible size
// effect until this is updated to match; Windows' own settings dialog
// always writes both together for the same reason.
const BASE_SIZE_VALUE = "CursorBaseSize";
const REG_SZ = 1;
const REG_DWORD = 4;
const KEY_READ = 0x20019;
const KEY_WRITE = 0x20006;
const SPI_SETCURSORS = 0x0057;
const SPIF_SENDCHANGE = 0x0002;

const CUR_FILENAME = "arrow.cur";
const STASH_FILENAME = "original_arrow.json";
const DEFAULT_SIZE_PX = 32;
const MODE_COLORS: Record<string, [number, number, number]> = {
  default: [0, 0, 0],
  white: [255, 255, 255],
  black: [0, 0, 0],
};

function defaultCursorDir(): string {
  return path.join(process.env.LOCALAPPDATA ?? ".", "FaceMeshMouse", "cursors");
}

function hexToRgb(hex: string): [number, number, number] {
  const h = hex.replace(/^#/, "");
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
}

function readArrowRegistryValue(): string | null {
  const phkResult = [null];
  const rc = RegCreateKeyExW(HKEY_CURRENT_USER, CURSORS_KEY, 0, null, 0, KEY_READ, null, phkResult, null);
  if (rc !== 0) return null;
  try {
    const cbData = [520]; // MAX_PATH * 2 bytes, generous
    const buf = Buffer.alloc(cbData[0]);
    const type = [0];
    const readRc = RegQueryValueExW(phkResult[0], ARROW_VALUE, null, type, buf, cbData);
    if (readRc !== 0) return null;
    return koffi.decode(buf, "char16_t", cbData[0] / 2 - 1) || null;
  } finally {
    RegCloseKey(phkResult[0]);
  }
}

function readCursorBaseSize(): number | null {
  const phkResult = [null];
  const rc = RegCreateKeyExW(HKEY_CURRENT_USER, CURSORS_KEY, 0, null, 0, KEY_READ, null, phkResult, null);
  if (rc !== 0) return null;
  try {
    const cbData = [4];
    const buf = Buffer.alloc(4);
    const type = [0];
    const readRc = RegQueryValueExW(phkResult[0], BASE_SIZE_VALUE, null, type, buf, cbData);
    if (readRc !== 0) return null;
    return buf.readUInt32LE(0);
  } finally {
    RegCloseKey(phkResult[0]);
  }
}

// ERROR_FILE_NOT_FOUND -- returned by RegDeleteValueW when the value is
// already gone. Matches the Python reference's explicit
// `except FileNotFoundError: pass`: deleting a value that doesn't exist is
// not a failure.
const ERROR_FILE_NOT_FOUND = 2;

function writeArrowRegistry(value: string | null): boolean {
  const phkResult = [null];
  const rc = RegCreateKeyExW(HKEY_CURRENT_USER, CURSORS_KEY, 0, null, 0, KEY_WRITE, null, phkResult, null);
  if (rc !== 0) return false;
  let ok = true;
  try {
    if (value === null) {
      const deleteRc = RegDeleteValueW(phkResult[0], ARROW_VALUE);
      ok = deleteRc === 0 || deleteRc === ERROR_FILE_NOT_FOUND;
    } else {
      const buf = Buffer.from(value + "\0", "utf16le");
      const setRc = RegSetValueExW(phkResult[0], ARROW_VALUE, 0, REG_SZ, buf, buf.length);
      ok = setRc === 0;
    }
  } finally {
    RegCloseKey(phkResult[0]);
  }
  return ok;
}

function writeCursorBaseSize(value: number | null): boolean {
  const phkResult = [null];
  const rc = RegCreateKeyExW(HKEY_CURRENT_USER, CURSORS_KEY, 0, null, 0, KEY_WRITE, null, phkResult, null);
  if (rc !== 0) return false;
  let ok = true;
  try {
    if (value === null) {
      const deleteRc = RegDeleteValueW(phkResult[0], BASE_SIZE_VALUE);
      ok = deleteRc === 0 || deleteRc === ERROR_FILE_NOT_FOUND;
    } else {
      const buf = Buffer.alloc(4);
      buf.writeUInt32LE(value, 0);
      const setRc = RegSetValueExW(phkResult[0], BASE_SIZE_VALUE, 0, REG_DWORD, buf, buf.length);
      ok = setRc === 0;
    }
  } finally {
    RegCloseKey(phkResult[0]);
  }
  return ok;
}

function broadcastCursorChange(): void {
  SystemParametersInfoW(SPI_SETCURSORS, 0, null, SPIF_SENDCHANGE);
}

function stashOriginalIfNeeded(cursorDir: string): void {
  const stashPath = path.join(cursorDir, STASH_FILENAME);
  if (fs.existsSync(stashPath)) return;
  const value = readArrowRegistryValue();
  const baseSize = readCursorBaseSize();
  fs.mkdirSync(cursorDir, { recursive: true });
  fs.writeFileSync(stashPath, JSON.stringify({ value, baseSize }), "utf-8");
}

export function applyCursor(sizePx: number, mode: string, customColor: string, cursorDir: string = defaultCursorDir()): void {
  if (sizePx === DEFAULT_SIZE_PX && mode === "default") {
    // Nothing was ever applied -> restoreCursor() is a pure no-op (no
    // registry read/write) because no stash file exists, so the
    // untouched-user guarantee is unchanged. Something WAS applied -> this
    // is an explicit revert to the Windows default, so put the original back.
    restoreCursor(cursorDir);
    return;
  }
  try {
    const effectiveMode = VALID_CURSOR_MODES.has(mode) ? mode : "default";
    const curBytes =
      effectiveMode === "mista"
        ? buildCurBytesMista(sizePx)
        : buildCurBytesColor(sizePx, effectiveMode === "custom" ? hexToRgb(customColor) : MODE_COLORS[effectiveMode]);

    stashOriginalIfNeeded(cursorDir);
    fs.mkdirSync(cursorDir, { recursive: true });
    const curPath = path.join(cursorDir, CUR_FILENAME);
    fs.writeFileSync(curPath, curBytes);
    const arrowOk = writeArrowRegistry(curPath);
    const baseSizeOk = writeCursorBaseSize(sizePx);
    if (arrowOk || baseSizeOk) broadcastCursorChange();
  } catch (exc) {
    console.error(`facemesh-mouse: cursor theme apply failed (${exc})`);
  }
}

export function restoreCursor(cursorDir: string = defaultCursorDir()): void {
  const stashPath = path.join(cursorDir, STASH_FILENAME);
  if (!fs.existsSync(stashPath)) return;
  try {
    const stash = JSON.parse(fs.readFileSync(stashPath, "utf-8"));
    const arrowOk = writeArrowRegistry(stash.value ?? null);
    const baseSizeOk = writeCursorBaseSize(stash.baseSize ?? null);
    if (arrowOk || baseSizeOk) broadcastCursorChange();
    if (arrowOk && baseSizeOk) {
      fs.unlinkSync(stashPath);
    } else {
      // Registry write-back failed -- leave the stash in place so a later
      // restore attempt can retry, instead of permanently losing the
      // user's original cursor (matches the Python reference: a raised
      // OSError there propagates past stash_path.unlink(), skipping it).
      console.error("facemesh-mouse: cursor theme restore failed (registry write-back failed, stash kept for retry)");
    }
  } catch (exc) {
    console.error(`facemesh-mouse: cursor theme restore failed (${exc})`);
  }
}
