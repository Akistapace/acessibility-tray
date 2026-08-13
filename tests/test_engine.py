from unittest.mock import MagicMock, patch

from facemesh_mouse.modules.config import default_config
from facemesh_mouse.modules.engine import Engine
from facemesh_mouse.modules.tracker import FaceMetrics


def _metrics(nose_x=0.5, nose_y=0.5):
    return FaceMetrics(
        nose_x=nose_x,
        nose_y=nose_y,
        ear_a=0.3,
        ear_b=0.3,
        mouth_open_ratio=0.1,
        eyebrow_raise_a=0.05,
        eyebrow_raise_b=0.05,
        mouth_shift_ratio=0.0,
        landmarks=[],
    )


def _engine_with_fakes():
    engine = Engine(default_config())
    engine._mouse_controller = MagicMock()
    engine._gesture_engine = MagicMock()
    engine._gesture_engine.evaluate.return_value = []
    engine._point_tracker = MagicMock()
    engine._point_tracker.get_movement.return_value = (0.0, 0.0)
    return engine


def test_reanchors_on_first_active_frame():
    engine = _engine_with_fakes()
    engine.control_enabled.set()

    engine._drive_control(_metrics())

    engine._mouse_controller.reanchor.assert_called_once()
    engine._mouse_controller.move_cursor.assert_called_once()


def test_does_not_reanchor_on_subsequent_active_frames():
    engine = _engine_with_fakes()
    engine.control_enabled.set()

    engine._drive_control(_metrics())
    engine._drive_control(_metrics())

    assert engine._mouse_controller.reanchor.call_count == 1
    assert engine._mouse_controller.move_cursor.call_count == 2


def test_reanchors_on_resume_from_pause():
    engine = _engine_with_fakes()
    engine.control_enabled.set()

    engine._drive_control(_metrics())  # active frame 1 -> reanchor #1
    engine.paused.set()
    engine._drive_control(_metrics())  # paused, no-op
    engine.paused.clear()
    engine._drive_control(_metrics())  # resumed -> reanchor #2

    assert engine._mouse_controller.reanchor.call_count == 2


def test_reanchors_after_face_reacquired():
    engine = _engine_with_fakes()
    engine.control_enabled.set()

    engine._drive_control(_metrics())  # active -> reanchor #1
    engine._was_active = False  # simulates the no-face frame's reset
    engine._drive_control(_metrics())  # face reacquired -> reanchor #2

    assert engine._mouse_controller.reanchor.call_count == 2


def test_paused_frame_does_not_move_cursor_or_evaluate_gestures():
    engine = _engine_with_fakes()
    engine.control_enabled.set()
    engine.paused.set()

    engine._drive_control(_metrics())

    engine._mouse_controller.move_cursor.assert_not_called()
    engine._gesture_engine.evaluate.assert_not_called()


def test_mouse_controller_property_exposes_the_controller_after_start():
    engine = Engine(default_config())
    assert engine.mouse_controller is None

    engine._mouse_controller = MagicMock()
    assert engine.mouse_controller is engine._mouse_controller


@patch("facemesh_mouse.modules.engine.cv2.VideoCapture", side_effect=KeyboardInterrupt)
def test_open_camera_returns_false_when_user_interrupts_camera_start(mock_video_capture):
    engine = Engine(default_config())

    assert engine.open_camera() is False
