import koffi from "koffi";

const user32 = koffi.load("user32.dll");
const ole32 = koffi.load("ole32.dll");
const advapi32 = koffi.load("advapi32.dll");

const FindWindowW = user32.func("void *FindWindowW(const char16_t *lpClassName, const char16_t *lpWindowName)");
const IsWindowVisible = user32.func("bool IsWindowVisible(void *hWnd)");
const GetForegroundWindow = user32.func("void *GetForegroundWindow()");
const GetWindowTextLengthW = user32.func("int GetWindowTextLengthW(void *hWnd)");
const GetWindowTextW = user32.func("int GetWindowTextW(void *hWnd, _Out_ char16_t *lpString, int nMaxCount)");

const CoInitializeEx = ole32.func("long CoInitializeEx(void *pvReserved, uint32 dwCoInit)");
const CoUninitialize = ole32.func("void CoUninitialize()");
const CLSIDFromString = ole32.func("long CLSIDFromString(const char16_t *lpsz, _Out_ uint8_t *pclsid)");
const CoCreateInstance = ole32.func(
  "long CoCreateInstance(const uint8_t *rclsid, void *pUnkOuter, uint32 dwClsContext, const uint8_t *riid, _Out_ void **ppv)"
);

const RegCreateKeyExW = advapi32.func(
  "long RegCreateKeyExW(void *hKey, const char16_t *lpSubKey, uint32 Reserved, void *lpClass, uint32 dwOptions, uint32 samDesired, void *lpSecurityAttributes, _Out_ void **phkResult, void *lpdwDisposition)"
);
const RegSetValueExW = advapi32.func(
  "long RegSetValueExW(void *hKey, const char16_t *lpValueName, uint32 Reserved, uint32 dwType, const uint8_t *lpData, uint32 cbData)"
);
const RegCloseKey = advapi32.func("long RegCloseKey(void *hKey)");

const CLSID_UI_HOST_NO_LAUNCH = "{4CE576FA-83DC-4F88-951C-9D0782B4E376}";
const IID_ITIP_INVOCATION = "{37c994e7-432b-4834-a2f7-dce1f13b834b}";
const CLSCTX_ALL = 0x17;
const COINIT_APARTMENTTHREADED = 0x2;
const S_OK = 0;
const S_FALSE = 1;

const HKEY_CURRENT_USER = koffi.as(0x80000001, "void *");
const TABLET_TIP_KEY = "Software\\Microsoft\\TabletTip\\1.7";
const EDGE_TARGET_DOCKED_STATE = "EdgeTargetDockedState";
const REG_DWORD = 4;
const DOCKED_STATE_FLOATING = 0;

const TOUCH_KEYBOARD_WINDOW_CLASS = "IPTip_Main_Window";
const VISIBILITY_POLL_INTERVAL_MS = 50;
const VISIBILITY_POLL_ATTEMPTS = 8;

function guidBuffer(text: string): Buffer {
  const buf = Buffer.alloc(16);
  const rc = CLSIDFromString(text, buf);
  if (rc !== S_OK) throw new Error(`CLSIDFromString(${text}) failed: hr=${rc}`);
  return buf;
}

function touchKeyboardVisible(): boolean {
  const hwnd = FindWindowW(TOUCH_KEYBOARD_WINDOW_CLASS, null);
  return Boolean(hwnd) && IsWindowVisible(hwnd);
}

function preferFloatingLayout(): void {
  const phkResult = [null];
  const rc = RegCreateKeyExW(HKEY_CURRENT_USER, TABLET_TIP_KEY, 0, null, 0, 0x20006 /* KEY_WRITE */, null, phkResult, null);
  if (rc !== S_OK) return; // best-effort, matches virtual_keyboard.py's silent failure
  const value = Buffer.alloc(4);
  value.writeUInt32LE(DOCKED_STATE_FLOATING, 0);
  RegSetValueExW(phkResult[0], EDGE_TARGET_DOCKED_STATE, 0, REG_DWORD, value, 4);
  RegCloseKey(phkResult[0]);
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function toggleTouchKeyboard(): Promise<boolean> {
  preferFloatingLayout();

  const initHr = CoInitializeEx(null, COINIT_APARTMENTTHREADED);
  const ownsApartment = initHr === S_OK || initHr === S_FALSE;

  try {
    const clsid = guidBuffer(CLSID_UI_HOST_NO_LAUNCH);
    const iid = guidBuffer(IID_ITIP_INVOCATION);
    const ppv = [null];
    const hr = CoCreateInstance(clsid, null, CLSCTX_ALL, iid, ppv);
    if (hr !== S_OK || !ppv[0]) {
      throw new Error(`CoCreateInstance(UIHostNoLaunch) failed: hr=${hr}`);
    }

    const obj = ppv[0] as unknown as Buffer;
    const vtable = koffi.decode(obj, "void **", 1)[0];
    const toggle = koffi.decode(vtable, koffi.pointer(koffi.proto("__stdcall", "long", ["void *", "void *"])), 4)[3];
    koffi.call(toggle, "long", ["void *", "void *"], [obj, null]);

    const release = koffi.decode(vtable, koffi.pointer(koffi.proto("__stdcall", "unsigned long", ["void *"])), 3)[2];
    koffi.call(release, "unsigned long", ["void *"], [obj]);
  } catch (exc) {
    console.error(`facemesh-mouse: could not toggle the touch keyboard (${exc})`);
    return false;
  } finally {
    if (ownsApartment) CoUninitialize();
  }

  for (let attempt = 0; attempt < VISIBILITY_POLL_ATTEMPTS; attempt++) {
    if (touchKeyboardVisible()) return true;
    await sleep(VISIBILITY_POLL_INTERVAL_MS);
  }
  return false;
}

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
