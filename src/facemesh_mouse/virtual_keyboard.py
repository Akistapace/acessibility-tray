"""Toggles Windows' touch keyboard.

The app doesn't build its own on-screen keyboard -- Windows already ships
one that's accessible from any focused app. This module only makes it
reachable through the same head-tracked cursor the rest of the app uses --
called from the floating keyboard button (see ui/action_buttons.py).

Uses the touch keyboard (the same one phones/tablets show for any text
field), not the legacy on-screen keyboard (osk.exe): on some Windows
builds osk.exe's manifest requires elevation, which throws up a UAC
consent prompt on the Secure Desktop -- a surface Windows deliberately
blocks all synthetic/injected input from reaching, by design, so no
gesture- or dwell-driven click can ever dismiss it. The touch keyboard runs
at the user's own privilege level and is built to be operated by any
pointing device, which matches this app's situation.
"""
from __future__ import annotations

import ctypes
import time
import winreg

# The documented COM interface Windows itself uses to show/hide the touch
# keyboard without going through its taskbar icon. ITipInvocation has one
# method beyond IUnknown's three (QueryInterface, AddRef, Release):
# Toggle(HWND) at vtable slot 3.
_CLSID_UI_HOST_NO_LAUNCH = "{4CE576FA-83DC-4F88-951C-9D0782B4E376}"
_IID_ITIP_INVOCATION = "{37c994e7-432b-4834-a2f7-dce1f13b834b}"
_TOGGLE_VTABLE_SLOT = 3
_RELEASE_VTABLE_SLOT = 2

# CLSCTX_INPROC_SERVER | CLSCTX_INPROC_HANDLER | CLSCTX_LOCAL_SERVER | CLSCTX_REMOTE_SERVER
_CLSCTX_ALL = 0x17

_COINIT_APARTMENTTHREADED = 0x2
_S_OK = 0
_S_FALSE = 1  # CoInitializeEx: this thread's COM apartment was already set up

# Docked (1) spans the full screen width; floating (0) is the small,
# freely-movable keyboard -- a per-user Windows preference, persisted in
# the registry once set, same place the touch keyboard itself saves it
# after a manual drag of its own dock/float toggle.
_TABLET_TIP_KEY = r"Software\Microsoft\TabletTip\1.7"
_EDGE_TARGET_DOCKED_STATE = "EdgeTargetDockedState"
_DOCKED_STATE_FLOATING = 0

# The touch keyboard's own top-level window class -- Windows silently
# declines to ever create/show it when the foreground app has no focused
# editable text control, no matter how many times Toggle() is called (it
# still returns S_OK). Polling this after Toggle() is the only way to tell
# "shown" from "silently refused" apart, since Toggle() itself can't say.
_TOUCH_KEYBOARD_WINDOW_CLASS = "IPTip_Main_Window"
_VISIBILITY_POLL_INTERVAL_S = 0.05
_VISIBILITY_POLL_ATTEMPTS = 8  # ~400ms -- enough for it to render if it's going to at all


def _touch_keyboard_visible() -> bool:
    hwnd = ctypes.windll.user32.FindWindowW(_TOUCH_KEYBOARD_WINDOW_CLASS, None)
    return bool(hwnd) and bool(ctypes.windll.user32.IsWindowVisible(hwnd))


def _prefer_floating_layout() -> None:
    """Best-effort: a docked keyboard is still fully usable, so a failure
    here (e.g. the key not existing yet on a fresh Windows profile) is not
    worth surfacing to the user."""
    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, _TABLET_TIP_KEY) as key:
            winreg.SetValueEx(key, _EDGE_TARGET_DOCKED_STATE, 0, winreg.REG_DWORD, _DOCKED_STATE_FLOATING)
    except OSError:
        pass


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]


def _guid(text: str) -> _GUID:
    guid = _GUID()
    ctypes.windll.ole32.CLSIDFromString(ctypes.c_wchar_p(text), ctypes.byref(guid))
    return guid


def _vtable_method(obj: ctypes.c_void_p, slot: int, restype, *argtypes):
    """Resolves a COM object's vtable[slot] to a callable -- the raw-ctypes
    equivalent of calling `obj->lpVtbl->Method(obj, ...)` in C. `obj` is
    always the first argument to the returned callable."""
    vtable_addr = ctypes.cast(obj, ctypes.POINTER(ctypes.c_void_p)).contents.value
    method_addr = ctypes.cast(
        vtable_addr + slot * ctypes.sizeof(ctypes.c_void_p), ctypes.POINTER(ctypes.c_void_p)
    ).contents.value
    return ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)(method_addr)


def open_virtual_keyboard() -> bool:
    """Shows the touch keyboard via ITipInvocation::Toggle, in its small
    floating layout rather than the full-width docked bar.

    Returns whether the keyboard actually became visible. Toggle() returns
    success even when Windows silently declines to show anything -- its
    most common cause is that the foreground app has no focused editable
    text control, which the touch keyboard requires and gives no error
    about. Callers use the return value to tell the user apart from a
    click that plainly did nothing (see ui/action_buttons.py's warning
    pulse).

    A failure here must never crash tracking, the tray, or the config
    window -- it's caught and printed, not raised."""
    _prefer_floating_layout()

    ole32 = ctypes.windll.ole32
    obj = ctypes.c_void_p()
    owns_apartment = False
    try:
        init_hr = ole32.CoInitializeEx(None, _COINIT_APARTMENTTHREADED)
        owns_apartment = init_hr in (_S_OK, _S_FALSE)

        clsid = _guid(_CLSID_UI_HOST_NO_LAUNCH)
        iid = _guid(_IID_ITIP_INVOCATION)
        hr = ole32.CoCreateInstance(
            ctypes.byref(clsid), None, _CLSCTX_ALL, ctypes.byref(iid), ctypes.byref(obj)
        )
        if hr != _S_OK or not obj.value:
            raise OSError(f"CoCreateInstance(UIHostNoLaunch) failed: hr={hr:#x}")

        toggle = _vtable_method(obj, _TOGGLE_VTABLE_SLOT, ctypes.c_long, ctypes.c_void_p)
        toggle(obj, None)
    except Exception as exc:  # noqa: BLE001 - a missing keyboard must never crash tracking
        print(f"facemesh-mouse: could not toggle the touch keyboard ({exc!r})")
        return False
    finally:
        if obj.value:
            release = _vtable_method(obj, _RELEASE_VTABLE_SLOT, ctypes.c_ulong)
            release(obj)
        if owns_apartment:
            ole32.CoUninitialize()

    for _ in range(_VISIBILITY_POLL_ATTEMPTS):
        if _touch_keyboard_visible():
            return True
        time.sleep(_VISIBILITY_POLL_INTERVAL_S)
    return False
