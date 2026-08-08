import ctypes

import pytest

from facemesh_mouse import click_feedback


def test_show_pulse_creates_a_click_through_topmost_window(container):
    window = click_feedback.show_pulse(container, 100, 100)

    assert window is not None
    hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
    styles = ctypes.windll.user32.GetWindowLongW(hwnd, click_feedback.GWL_EXSTYLE)

    assert styles & click_feedback.WS_EX_TRANSPARENT
    assert styles & click_feedback.WS_EX_LAYERED

    window.destroy()


def test_show_pulse_positions_the_window_around_the_given_point(container):
    window = click_feedback.show_pulse(container, 500, 300)

    assert window is not None
    size = window.winfo_width()
    assert window.winfo_x() == pytest.approx(500 - size // 2, abs=2)
    assert window.winfo_y() == pytest.approx(300 - size // 2, abs=2)

    window.destroy()


def test_show_pulse_survives_a_broken_render(monkeypatch, container):
    """A missing pulse must never crash tracking -- verify the guard by
    forcing the internal implementation to raise."""

    def _boom(*_args, **_kwargs):
        raise RuntimeError("simulated overlay failure")

    monkeypatch.setattr(click_feedback, "_show_pulse", _boom)

    result = click_feedback.show_pulse(container, 0, 0)

    assert result is None
