"""End-to-end bed-fit tests, driven from the declared fixture expectations."""

from __future__ import annotations

from augura import Severity, analyze
from tests.fixtures import FLAT_PLATE, OVERSIZED_PLATE


def test_oversized_plate_overflows_a_256_build_volume() -> None:
    report = analyze(OVERSIZED_PLATE.build(), build_volume=(256, 256, 256))

    (finding,) = report.bed_fit
    assert finding.severity is Severity.ERROR
    # 350x350x5 overflows X and Y but not Z.
    assert "X" in finding.message and "Y" in finding.message


def test_flat_plate_fits_a_256_build_volume() -> None:
    report = analyze(FLAT_PLATE.build(), build_volume=(256, 256, 256))
    assert report.bed_fit == ()


def test_no_build_volume_skips_the_check() -> None:
    report = analyze(OVERSIZED_PLATE.build())
    assert report.bed_fit == ()
