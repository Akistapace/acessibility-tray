import io

from facemesh_mouse.modules import ipc_protocol as proto


def test_write_message_writes_one_json_line():
    stream = io.StringIO()
    proto.write_message(stream, {"type": "status", "paused": False})

    assert stream.getvalue() == '{"type":"status","paused":false}\n'


def test_read_messages_yields_each_line_as_a_dict():
    stream = io.StringIO('{"type":"start"}\n{"type":"stop"}\n')

    assert list(proto.read_messages(stream)) == [{"type": "start"}, {"type": "stop"}]


def test_read_messages_skips_blank_and_malformed_lines():
    stream = io.StringIO('{"type":"start"}\n\nnot json\n{"type":"stop"}\n')

    assert list(proto.read_messages(stream)) == [{"type": "start"}, {"type": "stop"}]


def test_frame_message_shape():
    msg = proto.frame_message("abc123", {"blink_a": 0.5}, seq=7)
    assert msg == {
        "type": "frame",
        "jpeg_b64": "abc123",
        "gesture_progress": {"blink_a": 0.5},
        "seq": 7,
    }


def test_status_message_shape():
    assert proto.status_message(True, False, True, False) == {
        "type": "status",
        "control_enabled": True,
        "paused": False,
        "no_face": True,
        "yielded": False,
    }


def test_action_message_shape():
    assert proto.action_message("blink_a", "left_click", 640, 480) == {
        "type": "action",
        "gesture": "blink_a",
        "action": "left_click",
        "x": 640,
        "y": 480,
    }


def test_keyboard_result_message_shape():
    assert proto.keyboard_result_message(False, 10, 20) == {
        "type": "keyboard_result",
        "opened": False,
        "x": 10,
        "y": 20,
    }


def test_error_message_shape():
    assert proto.error_message("camera") == {"type": "error", "message": "camera"}


def test_config_message_shape():
    assert proto.config_message({"calibration": {}}) == {
        "type": "config",
        "config": {"calibration": {}},
    }
