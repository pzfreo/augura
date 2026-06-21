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
