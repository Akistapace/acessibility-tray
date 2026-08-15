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
