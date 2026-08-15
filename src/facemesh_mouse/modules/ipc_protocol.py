"""Newline-delimited JSON protocol shared with the Electron frontend's
`protocol.ts`. One JSON object per line; the Python backend's stdout
carries protocol only (see backend.py's stdout redirect)."""
from __future__ import annotations

import json
from typing import Iterator, TextIO


def encode_message(message: dict) -> str:
    return json.dumps(message, separators=(",", ":")) + "\n"


def write_message(stream: TextIO, message: dict) -> None:
    stream.write(encode_message(message))
    stream.flush()


def read_messages(stream: TextIO) -> Iterator[dict]:
    """Yields one dict per well-formed line. A malformed line is skipped,
    never raised -- a single bad command must never kill the backend."""
    for line in stream:
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def frame_message(jpeg_b64: str, gesture_progress: dict, seq: int) -> dict:
    return {
        "type": "frame",
        "jpeg_b64": jpeg_b64,
        "gesture_progress": gesture_progress,
        "seq": seq,
    }


def status_message(control_enabled: bool, paused: bool, no_face: bool, yielded: bool) -> dict:
    return {
        "type": "status",
        "control_enabled": control_enabled,
        "paused": paused,
        "no_face": no_face,
        "yielded": yielded,
    }


def action_message(gesture: str, action: str, x: int, y: int) -> dict:
    return {"type": "action", "gesture": gesture, "action": action, "x": x, "y": y}


def keyboard_result_message(opened: bool, x: int, y: int) -> dict:
    return {"type": "keyboard_result", "opened": opened, "x": x, "y": y}


def error_message(message: str) -> dict:
    return {"type": "error", "message": message}
