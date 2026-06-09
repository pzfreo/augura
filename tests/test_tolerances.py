"""Tests that configurable tolerances thread through the API and take effect."""

from __future__ import annotations

from build123d import Box

from augura import analyze
from augura.footprint import BED_TOL, bed_contact_faces
from tests.fixtures import THIN_LAMINA_BLOCK


def test_bed_contact_faces_custom_tol_tight() -> None:
    # A very tight (but non-zero) tolerance still finds an exact build123d bottom face.
    box = Box(10, 10, 5)
    assert bed_contact_faces(box, bed_tol=1e-9) == bed_contact_faces(box)


def test_bed_contact_faces_custom_tol_large() -> None:
    # bed_tol larger than box height would catch all faces — sanity check it's
    # plumbed correctly by confirming the default and a large value are both valid.
    box = Box(10, 10, 5)
    default = bed_contact_faces(box)
    large = bed_contact_faces(box, bed_tol=100.0)
    assert len(large) >= len(default)


def test_analyze_bed_tol_takes_effect() -> None:
    # With bed_tol=0 the strict `<` comparison (abs(z - z_min) < 0) is never
    # satisfied, so the bottom face is NOT excluded as bed-contact and instead
    # appears as a downward-facing overhang.  This proves bed_tol is forwarded.
    box = Box(20, 20, 10)
    assert analyze(box).overhangs == ()          # default: bottom excluded as bed-contact
    assert analyze(box, bed_tol=0.0).overhangs  # zero tol: bottom becomes overhang


def test_analyze_min_feature_suppresses_finding() -> None:
    # THIN_LAMINA_BLOCK has a ~0.2 mm vertical feature, flagged at default 0.5 mm.
    part = THIN_LAMINA_BLOCK.build()
    assert analyze(part).min_feature  # finding present at default threshold
    # Setting threshold below 0.2 mm means 0.2 is not too small → no finding.
    assert analyze(part, min_feature=0.1).min_feature == ()


def test_analyze_min_feature_exposes_more_findings() -> None:
    # A part with a 5mm feature is safe at default 0.5; flagged at 10mm threshold.
    from tests.fixtures import FLAT_PLATE
    part = FLAT_PLATE.build()
    assert analyze(part).min_feature == ()
    assert analyze(part, min_feature=10.0).min_feature  # 5mm feature now too small
