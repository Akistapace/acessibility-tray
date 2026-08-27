import koffi from "koffi";

const user32 = koffi.load("user32.dll");

const GetForegroundWindow = user32.func("void *GetForegroundWindow()");
const GetWindowTextLengthW = user32.func("int GetWindowTextLengthW(void *hWnd)");
const GetWindowTextW = user32.func("int GetWindowTextW(void *hWnd, _Out_ char16_t *lpString, int nMaxCount)");

export function foregroundWindowTitle(): string {
  try {
    const hwnd = GetForegroundWindow();
    const length = GetWindowTextLengthW(hwnd);
    const buf = Buffer.alloc((length + 1) * 2);
    GetWindowTextW(hwnd, buf, length + 1);
    return koffi.decode(buf, "char16_t", length) || "?";
  } catch {
    return "?";
  }
}
