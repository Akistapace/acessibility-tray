import pytest

from facemesh_mouse.modules import click_log


@pytest.fixture(autouse=True)
def _reset_logger():
    """The module-level logger is process-global state shared by every
    test in this file -- reset it before and after each test so tests
    can't see each other's handlers."""
    click_log.disable()
    yield
    click_log.disable()


def test_record_without_enable_writes_nothing(tmp_path):
    path = tmp_path / "clicks.log"

    click_log.record("blink_a", "left_click", (0, 0))

    assert not path.exists()


def test_record_writes_one_parseable_line(tmp_path):
    path = tmp_path / "clicks.log"
    click_log.enable(path)

    click_log.record("blink_a", "left_click", (842, 511), window_title_fn=lambda: "Notepad")

    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert "blink_a" in lines[0]
    assert "left_click" in lines[0]
    assert "(842, 511)" in lines[0]
    assert '"Notepad"' in lines[0]


def test_enable_twice_does_not_duplicate_handlers(tmp_path):
    path = tmp_path / "clicks.log"
    click_log.enable(path)
    click_log.enable(path)

    click_log.record("blink_a", "left_click", (0, 0), window_title_fn=lambda: "X")

    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1  # would be 2 if the handler got attached twice


def test_disable_stops_further_writes(tmp_path):
    path = tmp_path / "clicks.log"
    click_log.enable(path)
    click_log.record("blink_a", "left_click", (0, 0), window_title_fn=lambda: "X")
    click_log.disable()

    click_log.record("blink_a", "left_click", (0, 0), window_title_fn=lambda: "X")

    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1  # the record() after disable() must not append


def test_rotation_creates_a_backup_past_max_bytes(tmp_path):
    path = tmp_path / "clicks.log"
    click_log.enable(path, max_bytes=500, backup_count=2)

    for i in range(50):
        click_log.record("blink_a", "left_click", (i, i), window_title_fn=lambda: "x" * 40)

    assert (tmp_path / "clicks.log.1").exists()


def test_foreground_window_title_does_not_raise():
    title = click_log._foreground_window_title()

    assert isinstance(title, str)
    assert title != ""
