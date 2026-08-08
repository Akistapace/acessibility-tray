"""Shared fixtures for GUI-panel tests.

Every CustomTkinter-based test module shares ONE Tk root for the whole test
session via this fixture. Creating more than one Tk root in a process fails
intermittently under pytest's output capture once cv2/mediapipe are loaded.
Any test that needs a widget parent should depend on `container` -- never
construct a root of its own.
"""
import tkinter as tk

import pytest

ctk = pytest.importorskip("customtkinter")


@pytest.fixture(scope="session")
def root():
    from facemesh_mouse.config_gui import create_root

    try:
        window = create_root()
    except tk.TclError as exc:  # no display available
        pytest.skip(f"Tk unavailable: {exc}")
    window.withdraw()
    yield window
    window.destroy()


@pytest.fixture
def container(root):
    """A fresh parent widget per test, inside the one shared root."""
    frame = ctk.CTkFrame(root)
    yield frame
    frame.destroy()
