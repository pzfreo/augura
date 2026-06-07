"""End-to-end brim/raft tests, driven from the fixtures plus inline edge cases."""

from __future__ import annotations

from build123d import Box, Cylinder, Pos, Rotation

from augura import Severity, analyze
from tests.fixtures import FLAT_PLATE, TALL_THIN_PIN


def test_tall_thin_pin_recommends_brim() -> None:
    report = analyze(TALL_THIN_PIN.build())

    (finding,) = report.brim
    assert finding.severity is Severity.WARNING
    # Slender pin trips both the small-footprint and high-aspect criteria.
    assert "small" in finding.message and "aspect" in finding.message


def test_flat_plate_needs_no_brim() -> None:
    assert analyze(FLAT_PLATE.build()).brim == ()


def test_small_footprint_alone_recommends_brim() -> None:
    # Short but tiny footprint: small-footprint criterion only.
    short_pin = Pos(0, 0, 2.5) * Cylinder(radius=3, height=5)
    (finding,) = analyze(short_pin).brim
    assert "small" in finding.message
    assert "aspect" not in finding.message


def test_high_aspect_alone_recommends_brim() -> None:
    # Tall with an ample footprint: high-aspect criterion only.
    tower = Pos(0, 0, 100) * Box(30, 30, 200)
    (finding,) = analyze(tower).brim
    assert "aspect" in finding.message
    assert "small" not in finding.message


def test_line_contact_is_not_assessed() -> None:
    # A cylinder on its side has no planar footprint to measure.
    cyl = Rotation(0, 90, 0) * Cylinder(radius=5, height=20)
    cyl = Pos(0, 0, -cyl.bounding_box().min.Z) * cyl
    assert analyze(cyl).brim == ()
