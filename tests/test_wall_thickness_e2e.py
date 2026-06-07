"""End-to-end wall-thickness tests."""

from __future__ import annotations

import pytest
from build123d import Rectangle

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
