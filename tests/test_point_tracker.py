import cv2
import numpy as np
import pytest

from facemesh_mouse.point_tracker import (
    MIN_DISTANCE_TO_ADD,
    PointTracker,
    mean_movement,
    prune_points,
    should_add_point,
)


def _pts(*pairs):
    return np.array(pairs, dtype=np.float32).reshape(-1, 2)


def test_prune_drops_points_optical_flow_lost():
    cur = _pts((10, 10), (20, 20))
    prev = _pts((9, 10), (19, 20))
    status = np.array([1, 0], dtype=np.uint8)

    kept_cur, kept_prev = prune_points(cur, prev, status, nose=(15, 15), head_size=100)

    assert len(kept_cur) == 1
    assert kept_cur[0].tolist() == [10, 10]
    assert kept_prev[0].tolist() == [9, 10]


def test_prune_deduplicates_points_sharing_a_grid_cell():
    # (10,10) and (12,12) both fall in grid cell (2,2) at a 5px grid
    cur = _pts((10, 10), (12, 12), (40, 40))
    prev = _pts((10, 10), (12, 12), (40, 40))
    status = np.array([1, 1, 1], dtype=np.uint8)

    kept_cur, _ = prune_points(cur, prev, status, nose=(20, 20), head_size=100)

    assert len(kept_cur) == 2


def test_prune_culls_points_beyond_the_head_ellipse():
    nose = (100.0, 100.0)
    cur = _pts((110, 100), (400, 100))  # one near, one far away
    prev = cur.copy()
    status = np.array([1, 1], dtype=np.uint8)

    kept_cur, _ = prune_points(cur, prev, status, nose=nose, head_size=60)

    assert len(kept_cur) == 1
    assert kept_cur[0].tolist() == [110, 100]


def test_region_cull_is_stretched_horizontally():
    """The cull ellipse is 1.4x wider than tall, so the same distance
    survives vertically but not horizontally."""
    nose = (100.0, 100.0)
    head_size = 60.0
    offset = 50.0  # 50 * 1.4 = 70 > 60 horizontally, but 50 < 60 vertically

    horizontal = prune_points(
        _pts((100 + offset, 100)), _pts((100 + offset, 100)),
        np.array([1], dtype=np.uint8), nose, head_size,
    )[0]
    vertical = prune_points(
        _pts((100, 100 + offset)), _pts((100, 100 + offset)),
        np.array([1], dtype=np.uint8), nose, head_size,
    )[0]

    assert len(horizontal) == 0
    assert len(vertical) == 1


def test_should_add_point_rejects_a_candidate_near_an_existing_one():
    existing = _pts((100, 100))
    too_close = (100 + MIN_DISTANCE_TO_ADD - 1, 100 + MIN_DISTANCE_TO_ADD - 1)

    assert not should_add_point(too_close, existing)


def test_should_add_point_accepts_a_candidate_clear_on_both_axes():
    existing = _pts((100, 100))
    far = (100 + MIN_DISTANCE_TO_ADD + 1, 100 + MIN_DISTANCE_TO_ADD + 1)

    assert should_add_point(far, existing)


def test_should_add_point_accepts_anything_when_there_are_no_points():
    assert should_add_point((5, 5), _pts())


def test_mean_movement_averages_every_point():
    cur = _pts((10, 10), (20, 30))
    prev = _pts((8, 9), (18, 26))

    dx, dy = mean_movement(cur, prev)

    assert dx == pytest.approx(2.0)
    assert dy == pytest.approx(2.5)


def test_mean_movement_is_zero_without_points():
    assert mean_movement(_pts(), _pts()) == (0.0, 0.0)


def _textured_frame(seed=0):
    rng = np.random.default_rng(seed)
    frame = rng.integers(0, 255, (240, 320), dtype=np.uint8)
    return cv2.GaussianBlur(frame, (5, 5), 0)


def test_tracker_recovers_a_known_translation_through_real_optical_flow():
    """Pins the cv2.calcOpticalFlowPyrLK call's argument order and return
    shapes against a synthetic frame shifted by a known amount."""
    first = _textured_frame()
    shift_x, shift_y = 6, -3
    second = cv2.warpAffine(
        first, np.float32([[1, 0, shift_x], [0, 1, shift_y]]), (320, 240)
    )

    tracker = PointTracker()
    nose = (160.0, 120.0)
    candidates = [(150.0, 110.0), (170.0, 130.0), (160.0, 100.0)]

    tracker.update(first, nose, head_size=120.0, candidates=candidates)
    assert tracker.point_count == 3
    assert tracker.get_movement() == (0.0, 0.0)  # nothing to compare against yet

    tracker.update(second, nose, head_size=120.0, candidates=candidates)
    dx, dy = tracker.get_movement()

    assert dx == pytest.approx(shift_x, abs=1.0)
    assert dy == pytest.approx(shift_y, abs=1.0)


def test_reset_drops_every_point_and_zeroes_movement():
    tracker = PointTracker()
    tracker.update(_textured_frame(), (160.0, 120.0), 120.0, [(150.0, 110.0)])
    assert tracker.point_count == 1

    tracker.reset()

    assert tracker.point_count == 0
    assert tracker.get_movement() == (0.0, 0.0)


def test_candidates_are_not_re_added_once_tracked():
    tracker = PointTracker()
    frame = _textured_frame()
    candidates = [(150.0, 110.0), (170.0, 130.0)]

    tracker.update(frame, (160.0, 120.0), 120.0, candidates)
    tracker.update(frame, (160.0, 120.0), 120.0, candidates)

    assert tracker.point_count == 2
