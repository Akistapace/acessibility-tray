"""Launcher used both for `python run.py` (dev) and as the PyInstaller
entry point for the headless backend Electron spawns."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from facemesh_mouse.backend import main  # noqa: E402

if __name__ == "__main__":
    main()
