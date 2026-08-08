"""Optical-flow point tracking for cursor movement.

Ported from tracky-mouse (MIT, (c) Isaiah Odhner),
https://github.com/1j01/tracky-mouse -- its point-tracker class, pruning
rules, and constants, with OpenCV standing in for jsfeat.

Averaging the frame-to-frame movement of several tracked points cancels
noise that a single face landmark carries straight through to the cursor.
"""
from __future__ import annotations

import cv2
import numpy as np

# Points closer together than one grid cell are collapsed: points that have
# converged carry no extra information, and a cluster would weight one part
# of the face more than the rest.
PRUNING_GRID = 5.0

# A candidate is skipped if an existing point is already within this
# distance on either axis. Established points already carry motion history,
# so they are preferred over fresh ones.
MIN_DISTANCE_TO_ADD = PRUNING_GRID * 1.5

# The cull region is an ellipse wider than it is tall, matching a face.
REGION_X_STRETCH = 1.4

_LK_PARAMS = dict(
    winSize=(20, 20),
    maxLevel=3,
    criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01),
)


def _empty() -> np.ndarray:
    return np.empty((0, 2), dtype=np.float32)


def prune_points(points, prev_points, status, nose, head_size):
    """Drops points optical flow lost, collapses near-duplicates, and culls
    points that have drifted off the face -- in that order.

    Optical flow reports success for points that have visibly diverged, so
    the region cull rather than `status` is what keeps a runaway point from
    dragging the average. Returns the surviving (current, previous) arrays.
    """
    keep = np.asarray(status).reshape(-1) == 1
    points = np.asarray(points, dtype=np.float32).reshape(-1, 2)[keep]
    prev_points = np.asarray(prev_points, dtype=np.float32).reshape(-1, 2)[keep]

    seen_cells = {}
    for index, (x, y) in enumerate(points):
        seen_cells[(int(x // PRUNING_GRID), int(y // PRUNING_GRID))] = index
    if seen_cells:
        unique = sorted(seen_cells.values())
        points = points[unique]
        prev_points = prev_points[unique]

    if len(points):
        nose_x, nose_y = nose
        distances = np.hypot(
            (points[:, 0] - nose_x) * REGION_X_STRETCH, points[:, 1] - nose_y
        )
        inside = distances <= head_size
        points = points[inside]
        prev_points = prev_points[inside]

    return points, prev_points


def should_add_point(candidate, points) -> bool:
    """Whether a candidate is far enough from every tracked point to be
    worth adding, comparing each axis separately (the grid pruning makes
    Euclidean distance pointless here)."""
    points = np.asarray(points, dtype=np.float32).reshape(-1, 2)
    if not len(points):
        return True
    close_x = np.abs(points[:, 0] - candidate[0]) <= MIN_DISTANCE_TO_ADD
    close_y = np.abs(points[:, 1] - candidate[1]) <= MIN_DISTANCE_TO_ADD
    return not bool(np.any(close_x | close_y))


def mean_movement(points, prev_points) -> tuple[float, float]:
    """Average frame-to-frame movement across every tracked point, in
    camera pixels."""
    points = np.asarray(points, dtype=np.float32).reshape(-1, 2)
    prev_points = np.asarray(prev_points, dtype=np.float32).reshape(-1, 2)
    if not len(points):
        return 0.0, 0.0
    delta = points - prev_points
    return float(delta[:, 0].mean()), float(delta[:, 1].mean())


class PointTracker:
    """Tracks a small set of face points across frames via optical flow."""

    def __init__(self) -> None:
        self._prev_gray = None
        self._points = _empty()
        self._prev_points = _empty()

    @property
    def point_count(self) -> int:
        return len(self._points)

    def reset(self) -> None:
        """Drops every point and the previous frame, so the next update
        starts fresh. Used when control resumes or the face is lost."""
        self._prev_gray = None
        self._points = _empty()
        self._prev_points = _empty()

    def update(self, gray, nose, head_size, candidates) -> None:
        if self._prev_gray is not None and len(self._points):
            tracked, status, _err = cv2.calcOpticalFlowPyrLK(
                self._prev_gray, gray,
                self._points.reshape(-1, 1, 2), None,
                **_LK_PARAMS,
            )
            self._points, self._prev_points = prune_points(
                tracked.reshape(-1, 2), self._points, status, nose, head_size
            )
        else:
            self._prev_points = self._points.copy()

        for candidate in candidates:
            if should_add_point(candidate, self._points):
                self._points = np.vstack(
                    [self._points, np.array([candidate], dtype=np.float32)]
                )
                self._prev_points = np.vstack(
                    [self._prev_points, np.array([candidate], dtype=np.float32)]
                )

        self._prev_gray = gray

    def get_movement(self) -> tuple[float, float]:
        return mean_movement(self._points, self._prev_points)
