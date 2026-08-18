import json

import pytest
from unittest.mock import MagicMock

from facemesh_mouse import cursor_theme


@pytest.fixture(autouse=True)
def _no_real_registry_or_broadcast(monkeypatch):
    """Every test below drives cursor_theme through a tmp_path cursor_dir
    and a mocked winreg/SystemParametersInfoW -- none should touch the
    real Windows registry, mirroring test_virtual_keyboard.py's rule."""
    monkeypatch.setattr(cursor_theme.winreg, "OpenKey", MagicMock(side_effect=FileNotFoundError))
    monkeypatch.setattr(cursor_theme.winreg, "QueryValueEx", MagicMock())
    monkeypatch.setattr(cursor_theme.winreg, "CreateKeyEx", MagicMock())
    monkeypatch.setattr(cursor_theme.winreg, "SetValueEx", MagicMock())
    monkeypatch.setattr(cursor_theme.winreg, "DeleteValue", MagicMock())
    monkeypatch.setattr(
        cursor_theme.ctypes.windll.user32, "SystemParametersInfoW", MagicMock()
    )


def test_apply_cursor_is_a_no_op_at_the_untouched_defaults(tmp_path):
    cursor_theme.apply_cursor(32, "default", "#000000", cursor_dir=tmp_path)

    cursor_theme.winreg.CreateKeyEx.assert_not_called()
    assert not (tmp_path / "arrow.cur").exists()


def test_apply_cursor_reverts_to_the_original_when_called_with_the_default_after_a_theme_was_applied(tmp_path):
    # Same as test_apply_cursor_stashes_the_original_registry_value_once:
    # undo the autouse fixture's default FileNotFoundError so the mocked
    # QueryValueEx return value is actually reached during the stash.
    cursor_theme.winreg.OpenKey.side_effect = None
    cursor_theme.winreg.QueryValueEx.return_value = ("C:\\some\\original.cur", 1)
    cursor_theme.apply_cursor(64, "black", "#000000", cursor_dir=tmp_path)  # apply a theme first

    cursor_theme.apply_cursor(32, "default", "#000000", cursor_dir=tmp_path)  # revert

    (_key, name, _reserved, _kind, value), _kwargs = cursor_theme.winreg.SetValueEx.call_args
    assert name == cursor_theme._ARROW_VALUE
    assert value == "C:\\some\\original.cur"
    assert not (tmp_path / "original_arrow.json").exists()


def test_apply_cursor_writes_a_cur_file_and_sets_the_registry(tmp_path):
    cursor_theme.apply_cursor(48, "white", "#000000", cursor_dir=tmp_path)

    assert (tmp_path / "arrow.cur").exists()
    (_key, name, _reserved, _kind, value), _kwargs = cursor_theme.winreg.SetValueEx.call_args
    assert name == cursor_theme._ARROW_VALUE
    assert value == str(tmp_path / "arrow.cur")
    cursor_theme.ctypes.windll.user32.SystemParametersInfoW.assert_called_once_with(
        cursor_theme._SPI_SETCURSORS, 0, None, cursor_theme._SPIF_SENDCHANGE
    )


def test_apply_cursor_stashes_the_original_registry_value_once(tmp_path):
    # The autouse fixture defaults OpenKey to raise FileNotFoundError (so
    # tests that don't care about the registry's prior state still exercise
    # the "no original value" branch cleanly); this test is specifically
    # about the branch where a real original value exists, so it must undo
    # that default to let the mocked QueryValueEx return value be reached.
    cursor_theme.winreg.OpenKey.side_effect = None
    cursor_theme.winreg.QueryValueEx.return_value = ("C:\\some\\original.cur", 1)

    cursor_theme.apply_cursor(32, "black", "#000000", cursor_dir=tmp_path)
    stash = json.loads((tmp_path / "original_arrow.json").read_text())
    assert stash == {"value": "C:\\some\\original.cur"}

    # A second apply must not re-stash over the real original with our own
    # previously-generated path.
    cursor_theme.winreg.QueryValueEx.return_value = ("should-not-be-stashed.cur", 1)
    cursor_theme.apply_cursor(64, "black", "#000000", cursor_dir=tmp_path)
    stash_again = json.loads((tmp_path / "original_arrow.json").read_text())
    assert stash_again == {"value": "C:\\some\\original.cur"}


def test_apply_cursor_stashes_none_when_no_original_value_exists(tmp_path):
    cursor_theme.winreg.OpenKey.side_effect = FileNotFoundError

    cursor_theme.apply_cursor(32, "black", "#000000", cursor_dir=tmp_path)

    stash = json.loads((tmp_path / "original_arrow.json").read_text())
    assert stash == {"value": None}


def test_restore_cursor_writes_back_the_stashed_value_and_deletes_the_stash(tmp_path):
    (tmp_path / "original_arrow.json").write_text(json.dumps({"value": "C:\\original.cur"}))

    cursor_theme.restore_cursor(cursor_dir=tmp_path)

    (_key, name, _reserved, _kind, value), _kwargs = cursor_theme.winreg.SetValueEx.call_args
    assert name == cursor_theme._ARROW_VALUE
    assert value == "C:\\original.cur"
    assert not (tmp_path / "original_arrow.json").exists()


def test_restore_cursor_deletes_the_value_when_original_was_absent(tmp_path):
    (tmp_path / "original_arrow.json").write_text(json.dumps({"value": None}))

    cursor_theme.restore_cursor(cursor_dir=tmp_path)

    cursor_theme.winreg.DeleteValue.assert_called_once()


def test_restore_cursor_is_a_no_op_when_nothing_was_ever_applied(tmp_path):
    cursor_theme.restore_cursor(cursor_dir=tmp_path)

    cursor_theme.winreg.SetValueEx.assert_not_called()
    cursor_theme.winreg.DeleteValue.assert_not_called()


def test_apply_cursor_survives_a_registry_failure(tmp_path, capsys):
    cursor_theme.winreg.CreateKeyEx.side_effect = OSError("access denied")

    cursor_theme.apply_cursor(48, "white", "#000000", cursor_dir=tmp_path)  # must not raise

    assert "cursor theme" in capsys.readouterr().err
