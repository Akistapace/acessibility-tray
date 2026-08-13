from pathlib import Path

from facemesh_mouse.main import ICON_PATH, _resource_path


def test_resource_path_resolves_to_the_repo_assets_dir_outside_pyinstaller():
    resolved = _resource_path(ICON_PATH)

    assert resolved == Path(__file__).resolve().parent.parent / ICON_PATH
    assert resolved.exists()


def test_resource_path_prefers_pyinstalls_meipass_when_frozen(monkeypatch):
    monkeypatch.setattr("sys._MEIPASS", "C:/fake/bundle", raising=False)

    resolved = _resource_path(ICON_PATH)

    assert resolved == Path("C:/fake/bundle") / ICON_PATH
