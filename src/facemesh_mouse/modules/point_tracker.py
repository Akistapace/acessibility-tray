"""Optical-flow point tracking for cursor movement.

Tracks several points on rigid parts of the face (nose bridge, nostrils,
temples, cheek edges -- deliberately not the mouth/eyebrows/eyelids, which
move during gestures) frame-to-frame with Lucas-Kanade optical flow, and
reports the average of their movement. Averaging multiple points cancels
noise that following a single face landmark carries straight through to
the cursor: any point that has drifted or lost tracking is pruned before
the average is taken, so an outlier can't drag the whole result off
course.

Distance thresholds scale with the tracked head's size in the frame rather
than using fixed pixel counts, so the same relative behavior holds whether
the user sits close to the camera or farther back.
"""
from __future__ import annotations

import cv2
import numpy as np

# Points closer together than this fraction of the head size are collapsed:
# points that have converged carry no extra information, and a cluster
# would weight one part of the face more heavily than the rest.
PRUNING_CELL_FRACTION = 0.02

# A candidate is skipped only when an existing point is already within this
# fraction of the head size on BOTH axes -- i.e. genuinely nearby. Rejecting
# on either axis alone would discard symmetric features, which share a
# coordinate (the two nostrils sit at the same height, the midline points
# share an x). Established points already carry motion history, so they're
# preferred over a fresh candidate sitting on top of one.
MIN_ADD_DISTANCE_FRACTION = 0.03

# Average adult face height/width ratio: the cull region is an ellipse this
# much taller than it is wide, so it fits an actual face shape rather than
# a circle.
FACE_ASPECT_RATIO = 1.3

_LK_PARAMS = dict(
    winSize=(21, 21),
    maxLevel=2,
    criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.03),
    # Rejects low-texture tracks that tend to wander; well below OpenCV's
    # own default of 1e-4.
    minEigThreshold=0.001,
)


def _empty() -> np.ndarray:
    return np.empty((0, 2), dtype=np.float32)


def prune_points(points, prev_points, status, nose, head_size):
    """Drops points optical flow lost, collapses near-duplicates, and culls
    points that have drifted off the face -- in that order.

    Optical flow can report success for a point that has visibly diverged,
    so the region cull, not `status`, is the real backstop against a
    runaway point dragging the average off course. Returns the surviving
    (current, previous) arrays.
    """
    keep = np.asarray(status).reshape(-1) == 1
    points = np.asarray(points, dtype=np.float32).reshape(-1, 2)[keep]
    prev_points = np.asarray(prev_points, dtype=np.float32).reshape(-1, 2)[keep]

    cell = max(head_size * PRUNING_CELL_FRACTION, 1.0)
    seen_cells = {}
    for index, (x, y) in enumerate(points):
        seen_cells[(int(x // cell), int(y // cell))] = index
    if seen_cells:
        unique = sorted(seen_cells.values())
        points = points[unique]
        prev_points = prev_points[unique]

    if len(points):
        nose_x, nose_y = nose
        distances = np.hypot(
            (points[:, 0] - nose_x) * FACE_ASPECT_RATIO, points[:, 1] - nose_y
        )
        inside = distances <= head_size
        points = points[inside]
        prev_points = prev_points[inside]

    return points, prev_points


def should_add_point(candidate, points, head_size) -> bool:
    """Whether a candidate is far enough from every tracked point, on BOTH
    axes, to be worth adding."""
    points = np.asarray(points, dtype=np.float32).reshape(-1, 2)
    if not len(points):
        return True
    min_distance = max(head_size * MIN_ADD_DISTANCE_FRACTION, 1.0)
    close_x = np.abs(points[:, 0] - candidate[0]) <= min_distance
    close_y = np.abs(points[:, 1] - candidate[1]) <= min_distance
    return not bool(np.any(close_x & close_y))


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
        self._movement = (0.0, 0.0)

    @property
    def point_count(self) -> int:
        return len(self._points)

    def reset(self) -> None:
        """Drops every point and the previous frame, so the next update
        starts fresh. Called when the face is lost or a camera read fails --
        either way the next frame has no valid reference to compare against."""
        self._prev_gray = None
        self._points = _empty()
        self._prev_points = _empty()
        self._movement = (0.0, 0.0)

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

        # Measured before seeding: a point added this frame has no movement
        # to report, and averaging its zero in would understate the frame by
        # 1/N -- which shows up as intermittent cursor-speed dips.
        self._movement = mean_movement(self._points, self._prev_points)

        for candidate in candidates:
            if should_add_point(candidate, self._points, head_size):
                self._points = np.vstack(
                    [self._points, np.array([candidate], dtype=np.float32)]
                )
                self._prev_points = np.vstack(
                    [self._prev_points, np.array([candidate], dtype=np.float32)]
                )

        self._prev_gray = gray

    def get_movement(self) -> tuple[float, float]:
        """The movement measured by the last `update`, in camera pixels."""
        return self._movement
