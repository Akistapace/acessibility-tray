"""Launcher used both for `python run.py` and as the PyInstaller entry point."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from facemesh_mouse.main import main  # noqa: E402

if __name__ == "__main__":
    main()
