"""End-to-end wall-thickness tests."""

from __future__ import annotations

import pytest
from build123d import Cone, Rectangle, Sphere

from augura import Severity, analyze, find_thin_walls, min_wall_thickness
from tests.fixtures import FLAT_PLATE, THIN_WALL_TUBE


def test_thin_wall_tube_is_flagged() -> None:
    tube = THIN_WALL_TUBE.build()

    assert min_wall_thickness(tube) == pytest.approx(0.3, abs=0.02)
    (finding,) = analyze(tube).thin_walls
    assert finding.severity is Severity.WARNING
    assert "0.30" in finding.message


def test_thick_part_is_not_flagged() -> None:
    assert analyze(FLAT_PLATE.build()).thin_walls == ()


def test_no_opposed_surface_abstains() -> None:
    # A bare 2-D face has no material ahead of its centre to measure against.
    face = Rectangle(10, 10)
    assert min_wall_thickness(face) is None
    assert find_thin_walls(face) == []


def test_degenerate_apex_does_not_crash() -> None:
    # Regression for #48: a ray probing wall thickness can graze a cone tip /
    # pyramid apex, where OCCT's normal-at-intersection is undefined (zero norm)
    # and used to throw. A watertight, printable solid must analyse, not crash.
    cone = Cone(bottom_radius=5, top_radius=0, height=10)
    assert min_wall_thickness(cone) is not None
    assert isinstance(analyze(cone).findings, tuple)
    # A sphere (no singular apex on a probed ray) was always fine — still is.
    assert isinstance(analyze(Sphere(5)).findings, tuple)


def test_wall_thickness_at_derives_direction_from_nearest_face() -> None:
    # 0.3 mm tube wall: a point on the outer surface, no direction given → augura
    # snaps to the face and probes inward along its normal.
    from build123d import Vector

    from augura import wall_thickness_at

    tube = THIN_WALL_TUBE.build()
    assert wall_thickness_at(tube, Vector(10, 0, 10)) == pytest.approx(0.3, abs=0.02)


def test_wall_thickness_at_interior_point_spans_both_sides() -> None:
    # A point *mid-wall* with an explicit direction must span the whole wall
    # (both sides), not just point→first-face.
    from build123d import Vector

    from augura import wall_thickness_at

    tube = THIN_WALL_TUBE.build()
    t = wall_thickness_at(tube, Vector(9.85, 0, 10), Vector(1, 0, 0))
    assert t == pytest.approx(0.3, abs=0.02)


def test_wall_thickness_at_plate_through_thickness() -> None:
    from build123d import Vector

    from augura import wall_thickness_at

    plate = FLAT_PLATE.build()  # Box(40, 40, 5), z ∈ [0, 5]
    assert wall_thickness_at(plate, Vector(0, 0, 2.5), Vector(0, 0, 1)) == pytest.approx(
        5.0, abs=0.02
    )


def test_wall_thickness_at_void_point_measures_first_segment() -> None:
    # From outside the part, the chord of the first solid segment the ray crosses.
    from build123d import Box, Vector

    from augura import wall_thickness_at

    cube = Box(20, 20, 20)  # x ∈ [-10, 10]
    assert wall_thickness_at(cube, Vector(-30, 0, 0), Vector(1, 0, 0)) == pytest.approx(
        20.0, abs=0.02
    )


def test_wall_thickness_at_abstains_when_ray_misses() -> None:
    from build123d import Box, Rectangle, Vector

    from augura import wall_thickness_at

    cube = Box(20, 20, 20)
    # a ray parallel to but clear of the cube hits nothing
    assert wall_thickness_at(cube, Vector(-30, 100, 0), Vector(1, 0, 0)) is None
    # a bare 2-D face has no material to measure
    assert wall_thickness_at(Rectangle(10, 10), Vector(0, 0, 0)) is None


def test_wall_thickness_at_zero_direction_abstains() -> None:
    from build123d import Box, Vector

    from augura import wall_thickness_at

    assert wall_thickness_at(Box(20, 20, 20), Vector(0, 0, 0), Vector(0, 0, 0)) is None


def test_wall_thickness_at_surface_point_with_explicit_direction() -> None:
    from build123d import Box, Vector

    from augura import wall_thickness_at

    cube = Box(20, 20, 20)  # x ∈ [-10, 10]; point on the -x face, probe inward
    assert wall_thickness_at(cube, Vector(-10, 0, 0), Vector(1, 0, 0)) == pytest.approx(
        20.0, abs=0.02
    )
