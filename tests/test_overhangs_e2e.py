"""End-to-end overhang tests, driven from the declared fixture expectations.

These exercise the public ``analyze()`` surface only — they describe the
behaviour augura promises, and the implementation exists to satisfy them.
"""

from __future__ import annotations

from typing import Any, cast

import pytest
from build123d import Box, Pos, Shape

from augura import Severity, analyze, orientation_scores
from tests.fixtures import CANTILEVER, FLAT_PLATE


def _flat_ceiling(span: float) -> Shape[Any]:
    """A block with a bottom-open pocket, leaving a wall-bounded flat ceiling whose
    narrowest in-plane span is ``span`` mm (the pocket is 30 mm in the other axis)."""
    block = Pos(0, 0, 10) * Box(span + 20, 40, 20)
    pocket = Pos(0, 0, 5) * Box(span, 30, 10)
    return cast(Shape[Any], block - pocket)


def _floating_strip() -> Shape[Any]:
    """A wall on the bed with a thin tongue jutting out partway up: the tongue's
    5 mm-wide underside floats unsupported (anchored at one end only)."""
    wall = Pos(0, 0, 15) * Box(5, 30, 30)
    tongue = Pos(15, 0, 20) * Box(25, 5, 5)
    return cast(Shape[Any], wall + tongue)


def test_cantilever_has_one_overhang() -> None:
    assert len(analyze(CANTILEVER.build()).overhangs) == 1


def test_flat_plate_has_no_overhangs() -> None:
    assert len(analyze(FLAT_PLATE.build()).overhangs) == 0


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


def test_narrow_wall_bounded_ceiling_is_a_bridge_not_an_overhang() -> None:
    # Issue #49: a narrow, wall-bounded flat ceiling (3 mm span, 30 mm long)
    # bridges in a few lines — it should be an informational bridge, not a warning.
    report = analyze(_flat_ceiling(3.0))
    assert report.overhangs == ()
    (bridge,) = report.bridges
    assert bridge.severity is Severity.INFO
    assert "bridge" in bridge.message


def test_floating_narrow_strip_still_needs_support() -> None:
    # Adjacency-aware: a 5 mm-wide cantilevered tongue has the same narrow span as
    # a bridgeable slot, but no walls to anchor bridge lines, so it is an overhang
    # not a bridge — proving the bridge check is anchoring-aware, not span-only.
    report = analyze(_floating_strip())
    assert report.bridges == ()
    overhangs = report.overhangs
    assert len(overhangs) == 1
    assert overhangs[0].severity is Severity.WARNING


def test_wide_flat_ceiling_still_needs_support() -> None:
    # A 20 mm span is well past the default 5 mm bridge limit: a real overhang.
    report = analyze(_flat_ceiling(20.0))
    assert report.bridges == ()
    (overhang,) = report.overhangs
    assert overhang.severity is Severity.WARNING
    # The message carries area and span so sizes are distinguishable (#49 opt. 3).
    assert "mm2" in overhang.message and "span" in overhang.message


def test_max_bridge_threshold_is_configurable() -> None:
    # A 3 mm span is a bridge by default but an overhang once the limit drops below it.
    assert analyze(_flat_ceiling(3.0), max_bridge=2.0).overhangs
    assert analyze(_flat_ceiling(3.0), max_bridge=2.0).bridges == ()


def test_cantilever_arm_underside_is_too_wide_to_bridge() -> None:
    # The arm underside spans 10 mm — past the 5 mm default, so it stays an overhang.
    report = analyze(CANTILEVER.build())
    assert len(report.overhangs) == 1
    assert report.bridges == ()


def test_bridges_do_not_count_as_orientation_support_area() -> None:
    # A bridgeable flat ceiling needs no support, so it must not inflate a pose's
    # ranked overhang area.
    scores = orientation_scores(_flat_ceiling(3.0), candidates=[(0, 0, 0)])
    assert scores[0].overhang_area == 0.0
