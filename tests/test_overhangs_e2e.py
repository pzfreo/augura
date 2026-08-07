"""End-to-end overhang tests, driven from the declared fixture expectations.

These exercise the public ``analyze()`` surface only — they describe the
behaviour augura promises, and the implementation exists to satisfy them.
"""

from __future__ import annotations

from typing import Any, cast

import pytest
from build123d import (
    Axis,
    Box,
    Circle,
    Cylinder,
    Edge,
    Ellipse,
    Face,
    Plane,
    Pos,
    Rot,
    Shape,
    Shell,
    Solid,
    Vector,
    Wire,
    extrude,
)

from augura import Severity, analyze, find_overhangs, orientation_scores
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


def _windowed_wall(window_width: float, wall_thickness: float = 2.0) -> Shape[Any]:
    """A thin upright wall with a rectangular window cut clean through it. The
    ceiling face is ``window_width x wall_thickness``, but the wall thickness is a
    through-direction with open air on both sides, so it anchors nothing."""
    wall = Pos(0, 0, 6) * Box(40, wall_thickness, 12)
    window = Pos(0, 0, 6) * Box(window_width, wall_thickness + 4, 6)
    return cast(Shape[Any], wall - window)


def test_through_window_span_is_the_window_width_not_the_wall_thickness() -> None:
    # Issue #55: the ceiling of a 20 mm window through a 2 mm wall is 20x2 mm, so
    # the narrowest bounding-box side is the 2 mm wall thickness — but there is
    # open air on both faces of the wall at that height, so nothing anchors a
    # 2 mm bridge. The only anchors are the window ends, 20 mm apart.
    report = analyze(_windowed_wall(20.0))
    assert report.bridges == ()
    (overhang,) = report.overhangs
    assert "20.0 mm span" in overhang.message


def test_through_window_narrow_enough_to_bridge_reports_the_true_span() -> None:
    # The same geometry small enough to bridge must quote the window width (3 mm),
    # not the wall thickness (2 mm) — the span is what makes the verdict credible.
    (bridge,) = analyze(_windowed_wall(3.0)).bridges
    assert bridge.severity is Severity.INFO
    assert "3.0 mm span" in bridge.message


def test_bridge_span_does_not_depend_on_rotation_about_the_print_axis() -> None:
    # Spinning a part about Z changes nothing a printer cares about, so the span
    # must not move. A bounding-box dimension does move: it read 2.0 mm upright
    # and 15.6 mm at 45 deg for this part.
    part = _windowed_wall(20.0)
    upright = analyze(part).overhangs[0]
    for angle in (30.0, 45.0, 90.0):
        (turned,) = analyze(cast(Shape[Any], Rot(0, 0, angle) * part)).overhangs
        assert turned.message == upright.message


def test_slot_open_at_one_end_has_no_bridge_anchors() -> None:
    # A through-window pushed to the wall's end is anchored on one side only, so
    # every bridge line has one end in mid-air however short it is.
    wall = Pos(0, 0, 6) * Box(40, 2, 12)
    slot = Pos(15, 0, 6) * Box(14, 6, 6)
    report = analyze(cast(Shape[Any], wall - slot))
    assert report.bridges == ()
    (overhang,) = report.overhangs
    assert "no bridge direction" in overhang.message


def test_blind_hole_ceiling_spans_its_diameter() -> None:
    # An all-curved anchored boundary: the flat ceiling of a blind drilled hole is
    # a disc bounded by one circular edge, with no straight edge to measure across.
    block = Pos(0, 0, 10) * Box(30, 30, 20)
    hole = Pos(0, 0, 5) * Cylinder(radius=1.5, height=10)
    (bridge,) = analyze(cast(Shape[Any], block - hole)).bridges
    assert "3.0 mm span" in bridge.message


def test_round_flange_underside_has_no_bridge_direction() -> None:
    # A mushroom cap: the underside is an annulus anchored on the stem but free
    # around its whole outer circle. Bridge lines would have to stay parallel to
    # that circle, which no straight line can do, so it needs support.
    stem = Pos(0, 0, 5) * Cylinder(radius=2, height=10)
    cap = Pos(0, 0, 11) * Cylinder(radius=6, height=2)
    report = analyze(cast(Shape[Any], stem + cap))
    assert report.bridges == ()
    assert any("Flat" in o.message for o in report.overhangs)


def test_span_ignores_how_a_straight_edge_is_stored() -> None:
    # A BREP edge can be a spline whose points happen to be collinear, which
    # imported STEP is full of. Judging curvature by curve type would call this
    # window unbridgeable; the span is 3 mm either way.
    half_width, half_depth = 1.5, 5.0
    outline = [
        Edge.make_spline(
            [(-half_width, -half_depth, 0), (0, -half_depth, 0), (half_width, -half_depth, 0)]
        ),
        Edge.make_line((half_width, -half_depth, 0), (half_width, half_depth, 0)),
        Edge.make_spline(
            [(half_width, half_depth, 0), (0, half_depth, 0), (-half_width, half_depth, 0)]
        ),
        Edge.make_line((-half_width, half_depth, 0), (-half_width, -half_depth, 0)),
    ]
    window = Pos(0, 0, 3) * Solid.extrude(Face(Wire(outline)), (0, 0, 6))
    (bridge,) = analyze(cast(Shape[Any], Pos(0, 0, 6) * Box(40, 10, 12) - window)).bridges
    assert "3.0 mm span" in bridge.message


def _elliptical_pocket(angle: float) -> Shape[Any]:
    """A blind pocket with a 20x4 mm elliptical ceiling, turned in plan."""
    block = Pos(0, 0, 10) * Box(40, 40, 20)
    pocket = Pos(0, 0, 5) * Rot(0, 0, angle) * extrude(Ellipse(10, 2), 10)
    return cast(Shape[Any], block - pocket)


def test_all_curved_ceiling_span_survives_rotation() -> None:
    # A ceiling bounded only by curves has no straight edge to measure across, and
    # falling back to the bounding box would read 4 mm upright and 14.4 mm at
    # 45 deg. The pocket is 4 mm across whichever way the part is turned.
    for angle in (0.0, 30.0, 45.0, 90.0):
        (bridge,) = analyze(_elliptical_pocket(angle)).bridges
        assert "4.0 mm span" in bridge.message


def test_ceiling_with_an_inner_wire_spans_to_the_island_not_across_it() -> None:
    # A thin annular cavity around a central column of material. The column
    # anchors the inside of the ceiling, so bridge lines cross the 2.8 mm gap —
    # they never span the 20 mm outer diameter.
    block = Pos(0, 0, 10) * Box(40, 40, 20)
    cavity = Pos(0, 0, 5) * (extrude(Circle(10), 10) - extrude(Circle(9.9), 10))
    (bridge,) = analyze(cast(Shape[Any], block - cavity)).bridges
    assert bridge.severity is Severity.INFO


def test_non_convex_ceiling_is_measured_across_an_arm_not_end_to_end() -> None:
    # An L-shaped cavity with 3 mm arms. Its extent is 20 mm each way and 16.3 mm
    # diagonally, but no single bridge line ever crosses more than one arm, so the
    # best direction is the diagonal at about 4.2 mm.
    block = Pos(0, 0, 5) * Box(30, 30, 10)
    arms = Pos(0, -8.5, 4) * Box(20, 3, 8) + Pos(-8.5, 0, 4) * Box(3, 20, 8)
    (bridge,) = analyze(cast(Shape[Any], block - arms)).bridges
    assert "4.2 mm span" in bridge.message


def test_ceiling_supported_only_in_patches_still_needs_support() -> None:
    # A roof carried on scattered tabs. Sampling its edges at a few points would
    # find material at each and call the whole 20x4 mm underside a 4 mm bridge,
    # but most bridge lines have nothing to land on.
    roof = Pos(0, 0, 5.5) * Box(20, 4, 1)
    part = roof
    for x in (-5.0, 0.0, 5.0):
        part = part + Pos(x, -2.5, 2.75) * Box(0.8, 1, 5.5)
        part = part + Pos(x, 2.5, 2.75) * Box(0.8, 1, 5.5)
    for y in (-1.0, 0.0, 1.0):
        part = part + Pos(-10.5, y, 2.75) * Box(1, 0.8, 5.5)
        part = part + Pos(10.5, y, 2.75) * Box(1, 0.8, 5.5)
    report = analyze(cast(Shape[Any], part))
    assert report.bridges == ()
    assert any("no bridge direction" in o.message for o in report.overhangs)


def test_tilted_ceiling_probes_for_anchors_at_its_own_height() -> None:
    # A ceiling may lean up to _FLAT_TOL and still count as flat. Probing every
    # anchor at one height taken from the face's lowest corner would sit well
    # below the ceiling at its high end, where open air reads as solid material.
    # The +y wall here stops short over half the length, so it cannot bridge.
    block = Pos(0, 0, 20) * Box(120, 40, 40)
    void = Rot(0, -0.9, 0) * (Pos(0, 0, 10) * Box(140, 4, 20))
    missing_wall = Pos(30, 5, 22.25) * Box(60, 6, 5.5)
    report = analyze(cast(Shape[Any], block - void - missing_wall))
    assert report.bridges == ()


def test_filleted_roof_junction_still_anchors_a_bridge() -> None:
    # Where a fillet meets the ceiling the wall is horizontal, falling away as
    # sqrt(2*R*depth). A probe that drops too far before reaching out misses it
    # and reads every anchored edge as open air, which would switch bridging off
    # for most real parts — rounded pocket roofs are everywhere.
    # .solid() first: filleting a Box subclass tries to rebuild it on build123d 0.10.
    void = (Pos(0, 0, 5) * Box(20, 6, 10)).solid()
    void = void.fillet(1.0, void.edges().filter_by(Plane.XY).group_by(Axis.Z)[-1])
    (bridge,) = analyze(cast(Shape[Any], Pos(0, 0, 10) * Box(40, 40, 20) - void)).bridges
    assert bridge.severity is Severity.INFO


def test_roof_whose_supports_converge_is_not_a_bridge() -> None:
    # The two unsupported sides of this roof converge by 14 degrees, leaving a
    # corner no straight line reaches with both ends held. Judging a direction by
    # which way the boundary points admits it; judging by where the lines land
    # does not. Reported as bridgeable it would be an unsafe answer — the print
    # fails rather than merely wasting support material.
    corners = [(-2, -2, 5), (2, -2, 5), (2, 2, 5), (-2, 1, 5)]
    roof = Solid.extrude(Face(Wire.make_polygon(corners, close=True)), Vector(0, 0, 1))
    part = roof + Pos(-2.25, -0.5, 2.5) * Box(0.52, 3, 5) + Pos(2.25, 0, 2.5) * Box(0.52, 4, 5)
    report = analyze(cast(Shape[Any], part))
    assert report.bridges == ()
    assert any("no bridge direction" in o.message for o in report.overhangs)


def test_span_does_not_depend_on_the_threshold_it_is_compared_against() -> None:
    # max_bridge decides the verdict, never the geometry. A ceiling settled by the
    # cheap area/reach bound says so rather than passing that bound off as a
    # measured span, which would move with the caller's threshold.
    block = Pos(0, 0, 5) * Box(30, 30, 10)
    arms = Pos(0, -8.5, 4) * Box(20, 3, 8) + Pos(-8.5, 0, 4) * Box(3, 20, 8)
    part = cast(Shape[Any], block - arms)
    assert "4.2 mm span" in analyze(part).bridges[0].message
    (measured,) = analyze(part, max_bridge=4.0).overhangs
    assert "4.2 mm span" in measured.message
    (bounded,) = analyze(part, max_bridge=3.0).overhangs
    assert "at least" in bounded.message


def test_ceiling_far_too_large_to_bridge_is_settled_without_probing() -> None:
    # A ceiling holding a chord of at least area/reach cannot bridge whichever way
    # lines run, so the verdict is reached before any anchor probe or chord sweep.
    # Without that shortcut a lid carrying a grid of bosses — every boss an inner
    # wire — takes the sweep quadratic in the number of bosses.
    lid = Pos(0, 0, 10) * Box(100, 100, 20) - Pos(0, 0, 4) * Box(90, 90, 8)
    part = lid
    for i in range(8):
        for j in range(8):
            part = part + Pos(-40 + i * 80 / 7, -40 + j * 80 / 7, 4) * Cylinder(
                radius=1.5, height=8
            )
    report = analyze(cast(Shape[Any], part))
    assert report.bridges == ()
    assert any("Flat" in o.message and "needs support" in o.message for o in report.overhangs)


def test_shape_with_no_solid_does_not_claim_a_bridge_verdict() -> None:
    # Anchors are found by classifying points against solids. A surface-only STEP
    # has none, so every probe would come back empty and every ceiling would be
    # declared unbridgeable — a confident answer built on no evidence.
    solid = (Pos(0, 0, 10) * Box(30, 40, 20) - Pos(0, 0, 5) * Box(3, 30, 10)).solid()
    (from_solid,) = [f for f in find_overhangs(solid) if "Flat" in f.message]
    (from_shell,) = [f for f in find_overhangs(Shell(solid.faces())) if "Flat" in f.message]
    assert "bridges" in from_solid.message
    assert "bridge" not in from_shell.message and "needs support" in from_shell.message


def test_bridges_do_not_count_as_orientation_support_area() -> None:
    # A bridgeable flat ceiling needs no support, so it must not inflate a pose's
    # ranked overhang area.
    scores = orientation_scores(_flat_ceiling(3.0), candidates=[(0, 0, 0)])
    assert scores[0].overhang_area == 0.0
