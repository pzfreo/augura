"""End-to-end overhang tests, driven from the declared fixture expectations.

These exercise the public ``analyze()`` surface only — they describe the
behaviour augura promises, and the implementation exists to satisfy them.
"""

from __future__ import annotations

import pytest

from augura import analyze
from tests.fixtures import ALL, CANTILEVER, FLAT_PLATE, PartFixture


@pytest.mark.parametrize("fx", ALL, ids=lambda fx: fx.name)
def test_overhang_count_matches_expectation(fx: PartFixture) -> None:
    report = analyze(fx.build())
    assert len(report.overhangs) == fx.expected_overhangs, fx.notes


def test_cantilever_overhang_is_the_arm_underside() -> None:
    report = analyze(CANTILEVER.build())

    (overhang,) = report.overhangs
    # The arm underside is 30x10 minus the 5 mm chamfer strip -> ~250 mm2.
    assert overhang.area == pytest.approx(250.0, rel=0.05)
    # It is well above the bed (the column bottom, at z~0, must not be flagged).
    assert overhang.location is not None
    assert overhang.location[2] > 1.0


def test_flat_plate_has_no_findings() -> None:
    report = analyze(FLAT_PLATE.build())
    assert report.findings == ()


def test_support_angle_threshold_can_flag_the_chamfer() -> None:
    # The chamfer sits at exactly 45 deg, so the default threshold leaves it
    # borderline (unflagged). Raising the threshold past 45 deg must catch it.
    part = CANTILEVER.build()
    assert len(analyze(part, support_angle=45.0).overhangs) == 1
    assert len(analyze(part, support_angle=50.0).overhangs) == 2
