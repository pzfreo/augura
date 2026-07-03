"""End-to-end wall-thickness tests."""

from __future__ import annotations

import pytest
from build123d import Box, Compound, Cone, Cylinder, Pos, Rectangle, Sphere, Vector

from augura import Severity, analyze, find_thin_walls, min_wall_thickness, wall_thickness_at
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


# --------------------------------------------------------------------------- #
# wall_thickness_at — local wall thickness along a line through a point        #
# --------------------------------------------------------------------------- #


def test_wall_thickness_at_interior_point_spans_both_sides() -> None:
    # A mid-wall point spans the whole 0.3 mm tube wall, not point→first-face.
    tube = THIN_WALL_TUBE.build()
    assert wall_thickness_at(tube, Vector(9.85, 0, 10), Vector(1, 0, 0)) == pytest.approx(
        0.3, abs=0.02
    )


def test_wall_thickness_at_plate_through_thickness() -> None:
    plate = FLAT_PLATE.build()  # Box(40, 40, 5), z ∈ [0, 5]
    assert wall_thickness_at(plate, Vector(0, 0, 2.5), Vector(0, 0, 1)) == pytest.approx(
        5.0, abs=0.02
    )


def test_wall_thickness_at_is_sign_invariant_on_a_surface_point() -> None:
    # regression: an on-surface point gives the wall thickness for BOTH directions
    # (the old on_surface branch returned None for the outward one).
    plate = FLAT_PLATE.build()  # z ∈ [0, 5]
    assert wall_thickness_at(plate, Vector(0, 0, 5), Vector(0, 0, 1)) == pytest.approx(
        5.0, abs=0.02
    )
    assert wall_thickness_at(plate, Vector(0, 0, 5), Vector(0, 0, -1)) == pytest.approx(
        5.0, abs=0.02
    )


def test_wall_thickness_at_is_stable_across_the_surface_boundary() -> None:
    # regression: no sub-micron discontinuity flipping a valid 5.0 to None.
    plate = FLAT_PLATE.build()
    for z in (5 - 1e-6, 5 - 9e-7, 5.0, 5 + 9e-7):
        assert wall_thickness_at(plate, Vector(0, 0, z), Vector(0, 0, 1)) == pytest.approx(
            5.0, abs=0.02
        )


def test_wall_thickness_at_diagonal_through_edges_is_not_zero() -> None:
    # regression: duplicate hits where a ray crosses corner edges must not collapse
    # the chord to 0.0. Interior point so it lands in the (single) solid segment.
    cube = Box(20, 20, 20)  # x, y ∈ [-10, 10]
    assert wall_thickness_at(cube, Vector(0, 0, 0), Vector(1, 1, 0)) == pytest.approx(
        28.284, abs=0.05
    )


def test_wall_thickness_at_void_point_abstains() -> None:
    # a point in no wall must abstain (None), not report a distant/behind wall.
    cube = Box(20, 20, 20)  # x ∈ [-10, 10]
    assert wall_thickness_at(cube, Vector(-30, 0, 0), Vector(1, 0, 0)) is None


def test_wall_thickness_at_surface_point_explicit_direction() -> None:
    cube = Box(20, 20, 20)  # point on the -x face, probe inward
    assert wall_thickness_at(cube, Vector(-10, 0, 0), Vector(1, 0, 0)) == pytest.approx(
        20.0, abs=0.02
    )


def test_wall_thickness_at_zero_direction_abstains() -> None:
    assert wall_thickness_at(Box(20, 20, 20), Vector(0, 0, 0), Vector(0, 0, 0)) is None


def test_wall_thickness_at_abstains_when_line_meets_no_solid() -> None:
    cube = Box(20, 20, 20)
    assert wall_thickness_at(cube, Vector(-30, 100, 0), Vector(1, 0, 0)) is None  # misses
    assert wall_thickness_at(Rectangle(10, 10), Vector(0, 0, 0), Vector(0, 0, 1)) is None  # 2-D


def test_wall_thickness_at_rejects_malformed_point() -> None:
    cube = Box(20, 20, 20)
    for bad in ((1, 2), (1, 2, 3, 4), "xyz"):
        with pytest.raises((TypeError, ValueError)):
            wall_thickness_at(cube, bad, Vector(1, 0, 0))


def test_wall_thickness_at_coalesces_tangent_to_internal_bore() -> None:
    # regression: a ray tangent to an internal hole injects a crossing with solid
    # on both sides; the span must not be split (was 10.0, half the true wall).
    part = Box(20, 20, 10) - Cylinder(3, 12)  # hole r=3 along Z; wall along X ~20
    assert wall_thickness_at(part, Vector(0.5, 3, 0), Vector(1, 0, 0)) == pytest.approx(
        20.0, abs=0.05
    )


def test_wall_thickness_at_coalesces_unfused_compound() -> None:
    # regression: a coincident internal face in an unfused compound must not split
    # the wall (was 4.0, half the true 8 mm).
    comp = Compound([Pos(-2, 0, 0) * Box(4, 10, 10), Pos(2, 0, 0) * Box(4, 10, 10)])
    assert wall_thickness_at(comp, Vector(0, 0, 0), Vector(1, 0, 0)) == pytest.approx(8.0, abs=0.02)


def test_wall_thickness_at_accepts_numpy_int_and_float_points() -> None:
    np = pytest.importorskip("numpy")
    cube = Box(20, 20, 20)
    assert wall_thickness_at(cube, np.array([0, 0, 0]), Vector(1, 0, 0)) == pytest.approx(
        20.0, abs=0.02
    )
    assert wall_thickness_at(cube, np.array([0.0, 0.0, 0.0]), Vector(1, 0, 0)) == pytest.approx(
        20.0, abs=0.02
    )
