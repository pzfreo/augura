"""End-to-end tip-over / stability tests, driven from the fixtures."""

from __future__ import annotations

from build123d import Cylinder, Pos, Rotation

from augura import Severity, analyze
from tests.fixtures import FLAT_PLATE, SOLID_CUBE, TIPPING_MAST


def test_tipping_mast_is_unstable() -> None:
    report = analyze(TIPPING_MAST.build())

    (finding,) = report.tip_over
    assert finding.severity is Severity.ERROR


def test_flat_plate_is_stable() -> None:
    assert analyze(FLAT_PLATE.build()).tip_over == ()


def test_solid_cube_is_stable() -> None:
    assert analyze(SOLID_CUBE.build()).tip_over == ()


def test_line_contact_is_not_assessed() -> None:
    # A cylinder on its side touches the bed along a line, so there is no planar
    # support polygon to test against — the check abstains rather than guess.
    cyl = Rotation(0, 90, 0) * Cylinder(radius=5, height=20)
    cyl = Pos(0, 0, -cyl.bounding_box().min.Z) * cyl
    assert analyze(cyl).tip_over == ()
