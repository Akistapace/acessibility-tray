import numpy as np
import cv2

from facemesh_mouse.modules import preview
from facemesh_mouse.modules.tracker import FaceMetrics


def _fake_metrics() -> FaceMetrics:
    landmarks = [(0.5, 0.5)] * 468
    landmarks[33] = (0.3, 0.5)
    landmarks[263] = (0.7, 0.5)
    return FaceMetrics(
        nose_x=0.5, nose_y=0.5, ear_a=0.3, ear_b=0.3, mouth_open_ratio=0.1,
        eyebrow_raise_a=0.1, eyebrow_raise_b=0.1, mouth_shift_ratio=0.0,
        landmarks=landmarks,
    )


def test_render_preview_jpeg_without_metrics_returns_a_decodable_jpeg():
    frame = np.zeros((240, 320, 3), dtype=np.uint8)

    jpeg_bytes = preview.render_preview_jpeg(frame, None)

    decoded = cv2.imdecode(np.frombuffer(jpeg_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert decoded is not None
    assert decoded.shape[:2] == (preview.PREVIEW_SIZE[1], preview.PREVIEW_SIZE[0])


def test_render_preview_jpeg_with_metrics_returns_a_decodable_jpeg():
    frame = np.zeros((240, 320, 3), dtype=np.uint8)

    jpeg_bytes_without = preview.render_preview_jpeg(frame, None)
    jpeg_bytes_with = preview.render_preview_jpeg(frame, _fake_metrics())

    decoded_without = cv2.imdecode(np.frombuffer(jpeg_bytes_without, dtype=np.uint8), cv2.IMREAD_COLOR)
    decoded_with = cv2.imdecode(np.frombuffer(jpeg_bytes_with, dtype=np.uint8), cv2.IMREAD_COLOR)

    assert decoded_with is not None
    assert decoded_with.shape[:2] == (preview.PREVIEW_SIZE[1], preview.PREVIEW_SIZE[0])
    assert not np.array_equal(decoded_with, decoded_without)


def _decode(jpeg_bytes: bytes):
    return cv2.imdecode(np.frombuffer(jpeg_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)


def test_highlighted_gesture_draws_a_green_zone_over_the_baseline():
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    metrics = _fake_metrics()

    baseline = _decode(preview.render_preview_jpeg(frame, metrics))
    highlighted = _decode(preview.render_preview_jpeg(frame, metrics, "blink_a"))

    assert not np.array_equal(baseline, highlighted)
    # BGR: some pixel must have turned unambiguously green (no red/blue) --
    # proof the highlight was actually drawn, not just JPEG noise.
    assert np.any((highlighted[:, :, 1] > 100) & (highlighted[:, :, 2] < 50) & (highlighted[:, :, 0] < 50))


def test_unknown_gesture_name_draws_no_highlight():
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    metrics = _fake_metrics()

    baseline = preview.render_preview_jpeg(frame, metrics)
    unknown = preview.render_preview_jpeg(frame, metrics, "not_a_real_gesture")

    assert baseline == unknown


def test_no_highlighted_gesture_matches_the_baseline():
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    metrics = _fake_metrics()

    baseline = preview.render_preview_jpeg(frame, metrics)
    explicit_none = preview.render_preview_jpeg(frame, metrics, None)

    assert baseline == explicit_none


def test_highlighted_gesture_without_a_face_does_not_crash():
    frame = np.zeros((240, 320, 3), dtype=np.uint8)

    jpeg_bytes = preview.render_preview_jpeg(frame, None, "blink_a")  # must not raise

    assert _decode(jpeg_bytes) is not None
