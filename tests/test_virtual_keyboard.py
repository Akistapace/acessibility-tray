import ctypes
from unittest.mock import MagicMock

import pytest

from facemesh_mouse import virtual_keyboard

# Captured before any test below monkeypatches the module attribute of the
# same name, so tests targeting it directly still exercise the real code.
_real_prefer_floating_layout = virtual_keyboard._prefer_floating_layout


@pytest.fixture(autouse=True)
def _no_real_registry_writes(monkeypatch):
    """open_virtual_keyboard() writes a Windows preference to the real
    registry on every call; none of the COM-focused tests below should
    touch actual machine state as a side effect."""
    monkeypatch.setattr(virtual_keyboard, "_prefer_floating_layout", MagicMock())


@pytest.fixture(autouse=True)
def _touch_keyboard_appears_immediately(monkeypatch):
    """Stubs the post-Toggle visibility poll to succeed on the first check,
    so most tests don't depend on/wait for a real touch keyboard and don't
    pay for the poll's sleep. The one test covering "Windows silently
    declined to show it" overrides this to report not-visible."""
    monkeypatch.setattr(virtual_keyboard, "_touch_keyboard_visible", MagicMock(return_value=True))


def _stub_out_com_object(monkeypatch, address: int = 0xDEAD) -> None:
    """Makes CoCreateInstance report success and hand back a fake, non-null
    object pointer, without touching real COM/memory."""

    def fake_cocreateinstance(_rclsid, _outer, _clsctx, _riid, ppv):
        ctypes.cast(ppv, ctypes.POINTER(ctypes.c_void_p))[0] = ctypes.c_void_p(address)
        return 0  # S_OK

    monkeypatch.setattr(virtual_keyboard.ctypes.windll.ole32, "CoCreateInstance", fake_cocreateinstance)


def test_open_virtual_keyboard_toggles_the_touch_keyboard_via_com(monkeypatch):
    monkeypatch.setattr(virtual_keyboard.ctypes.windll.ole32, "CoInitializeEx", lambda *_a: 0)
    uninit_mock = MagicMock()
    monkeypatch.setattr(virtual_keyboard.ctypes.windll.ole32, "CoUninitialize", uninit_mock)
    _stub_out_com_object(monkeypatch)

    toggle_mock = MagicMock()
    release_mock = MagicMock()

    def fake_vtable_method(_obj, slot, _restype, *_argtypes):
        if slot == virtual_keyboard._TOGGLE_VTABLE_SLOT:
            return toggle_mock
        if slot == virtual_keyboard._RELEASE_VTABLE_SLOT:
            return release_mock
        raise AssertionError(f"unexpected vtable slot {slot}")

    monkeypatch.setattr(virtual_keyboard, "_vtable_method", fake_vtable_method)

    result = virtual_keyboard.open_virtual_keyboard()

    toggle_mock.assert_called_once()
    release_mock.assert_called_once()  # the COM reference is always released
    uninit_mock.assert_called_once()  # and the apartment always torn down
    assert result is True


def test_open_virtual_keyboard_returns_false_when_windows_declines_to_show_it(monkeypatch):
    """The touch keyboard requires a focused editable text control in the
    foreground app; without one, Toggle() still reports success but Windows
    never actually renders the keyboard. The caller (action_buttons.py)
    needs to tell this apart from a real open to show a warning instead of
    the normal click pulse."""
    monkeypatch.setattr(virtual_keyboard, "_touch_keyboard_visible", MagicMock(return_value=False))
    monkeypatch.setattr(virtual_keyboard.time, "sleep", MagicMock())
    monkeypatch.setattr(virtual_keyboard.ctypes.windll.ole32, "CoInitializeEx", lambda *_a: 0)
    monkeypatch.setattr(virtual_keyboard.ctypes.windll.ole32, "CoUninitialize", MagicMock())
    _stub_out_com_object(monkeypatch)
    monkeypatch.setattr(
        virtual_keyboard,
        "_vtable_method",
        lambda _obj, _slot, _restype, *_argtypes: MagicMock(),
    )

    assert virtual_keyboard.open_virtual_keyboard() is False


def test_open_virtual_keyboard_survives_a_cocreateinstance_failure(monkeypatch, capsys):
    monkeypatch.setattr(virtual_keyboard.ctypes.windll.ole32, "CoInitializeEx", lambda *_a: 0)
    monkeypatch.setattr(
        virtual_keyboard.ctypes.windll.ole32, "CoCreateInstance", lambda *_a: 0x80004005  # E_FAIL
    )
    uninit_mock = MagicMock()
    monkeypatch.setattr(virtual_keyboard.ctypes.windll.ole32, "CoUninitialize", uninit_mock)

    result = virtual_keyboard.open_virtual_keyboard()  # must not raise

    assert result is False
    assert "touch keyboard" in capsys.readouterr().out
    uninit_mock.assert_called_once()  # the apartment this call opened still gets torn down


def test_open_virtual_keyboard_survives_an_exception_before_com_object_creation(monkeypatch, capsys):
    """A missing/blocked touch keyboard must never crash the caller -- the
    tray thread or the Tk event loop, depending on which entry point calls
    it."""

    def _boom(*_args, **_kwargs):
        raise OSError("simulated COM initialization failure")

    monkeypatch.setattr(virtual_keyboard.ctypes.windll.ole32, "CoInitializeEx", _boom)

    result = virtual_keyboard.open_virtual_keyboard()  # must not raise

    assert result is False
    assert "touch keyboard" in capsys.readouterr().out


def test_open_virtual_keyboard_does_not_uninitialize_an_apartment_it_did_not_own(monkeypatch):
    """CoInitializeEx returning RPC_E_CHANGED_MODE means this thread already
    runs an incompatible COM apartment set up by someone else -- tearing
    that down here would break whatever set it up."""
    monkeypatch.setattr(
        virtual_keyboard.ctypes.windll.ole32, "CoInitializeEx", lambda *_a: 0x80010106
    )
    uninit_mock = MagicMock()
    monkeypatch.setattr(virtual_keyboard.ctypes.windll.ole32, "CoUninitialize", uninit_mock)
    monkeypatch.setattr(
        virtual_keyboard.ctypes.windll.ole32, "CoCreateInstance", lambda *_a: 0x80004005
    )

    virtual_keyboard.open_virtual_keyboard()

    uninit_mock.assert_not_called()


def test_open_virtual_keyboard_prefers_the_floating_layout(monkeypatch):
    prefer_mock = MagicMock()
    monkeypatch.setattr(virtual_keyboard, "_prefer_floating_layout", prefer_mock)
    monkeypatch.setattr(virtual_keyboard.ctypes.windll.ole32, "CoInitializeEx", lambda *_a: 0)
    monkeypatch.setattr(
        virtual_keyboard.ctypes.windll.ole32, "CoCreateInstance", lambda *_a: 0x80004005
    )

    virtual_keyboard.open_virtual_keyboard()

    prefer_mock.assert_called_once()


def test_prefer_floating_layout_sets_the_docked_state_registry_value(monkeypatch):
    set_value_mock = MagicMock()
    monkeypatch.setattr(virtual_keyboard.winreg, "SetValueEx", set_value_mock)
    monkeypatch.setattr(virtual_keyboard.winreg, "CreateKeyEx", MagicMock())

    _real_prefer_floating_layout()

    (_key, name, _reserved, _kind, value), _kwargs = set_value_mock.call_args
    assert name == virtual_keyboard._EDGE_TARGET_DOCKED_STATE
    assert value == virtual_keyboard._DOCKED_STATE_FLOATING


def test_prefer_floating_layout_survives_a_registry_failure(monkeypatch):
    monkeypatch.setattr(
        virtual_keyboard.winreg, "CreateKeyEx", MagicMock(side_effect=OSError("no access"))
    )

    _real_prefer_floating_layout()  # must not raise
