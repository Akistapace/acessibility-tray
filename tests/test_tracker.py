import math

import pytest

from facemesh_mouse.tracker import eye_midpoint, signed_lateral_offset


def test_signed_lateral_offset_is_zero_on_the_axis():
    assert signed_lateral_offset((0.5, 0.7), (0.5, 0.3), (0.5, 0.9)) == pytest.approx(0.0)


def test_signed_lateral_offset_is_symmetric_around_the_axis():
    axis_start, axis_end = (0.5, 0.3), (0.5, 0.9)
    higher_x = signed_lateral_offset((0.6, 0.7), axis_start, axis_end)
    lower_x = signed_lateral_offset((0.4, 0.7), axis_start, axis_end)

    assert higher_x > 0
    assert lower_x < 0
    assert higher_x == pytest.approx(-lower_x)


def test_signed_lateral_offset_magnitude_matches_perpendicular_distance():
    # point sits 0.1 to the right of a vertical axis
    offset = signed_lateral_offset((0.6, 0.7), (0.5, 0.3), (0.5, 0.9))
    assert offset == pytest.approx(0.1)


def test_signed_lateral_offset_survives_rotation():
    """Head yaw/roll rotates the whole face. Rotating the axis and the point
    together must not change the measured offset -- this is the property the
    lateral-mouth gesture depends on to not fire when the user turns their
    head to move the cursor."""
    axis_start = (0.5, 0.3)
    axis_end = (0.5, 0.9)
    point = (0.6, 0.7)
    before = signed_lateral_offset(point, axis_start, axis_end)

    def rotate(p, origin, angle):
        ox, oy = origin
        dx, dy = p[0] - ox, p[1] - oy
        return (
            ox + dx * math.cos(angle) - dy * math.sin(angle),
            oy + dx * math.sin(angle) + dy * math.cos(angle),
        )

    angle = math.radians(25)
    after = signed_lateral_offset(
        rotate(point, axis_start, angle),
        axis_start,
        rotate(axis_end, axis_start, angle),
    )

    assert after == pytest.approx(before)


def test_signed_lateral_offset_degenerate_axis_does_not_divide_by_zero():
    result = signed_lateral_offset((0.6, 0.7), (0.5, 0.5), (0.5, 0.5))
    assert math.isfinite(result)


def test_eye_midpoint_uses_the_center_between_the_eyes():
    pts = [(0.0, 0.0) for _ in range(500)]
    pts[33] = (0.2, 0.5)
    pts[263] = (0.8, 0.5)

    assert eye_midpoint(pts) == pytest.approx((0.5, 0.5))
