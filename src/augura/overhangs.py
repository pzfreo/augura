"""BREP-exact overhang detection.

Classifies every downward-facing face of a solid by its angle from horizontal,
reading exact OpenCASCADE face normals (not tessellated approximations). A face
whose normal points within ``support_angle`` of straight-down is a printability
overhang — *unless* it is resting on the build plate, in which case it is a
bed-contact face and needs no support.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any

from build123d import Shape, Vector
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.gp import gp_Pnt
from OCP.TopAbs import TopAbs_State

from augura.footprint import BED_TOL
from augura.report import Finding, Severity

DEFAULT_SUPPORT_ANGLE = 45.0
"""Faces shallower than this many degrees from horizontal need support."""

DEFAULT_MAX_BRIDGE = 5.0
"""A flat (horizontal) downward ceiling whose bridge span is at or below this
many mm bridges in a few unsupported lines, so it is reported as an informational
``bridge`` rather than a ``overhang`` that needs support."""

# A face counts as resting on the bed when its lowest point sits at the part's
# minimum Z *and* it faces almost straight down.
_BED_NORMAL_TOL = 0.99
# Normals with a Z-component above this are upward or vertical: no overhang.
_DOWNWARD_TOL = 1e-6
# Float slack so a face at exactly the threshold angle is treated as borderline
# (not flagged) rather than tipping on rounding noise.
_ANGLE_TOL = 1e-3
# A downward face within this many degrees of horizontal is a flat ceiling — a
# bridge candidate. Steeper overhangs sag across a gap, so they are never bridged.
_FLAT_TOL = 1.0
# Boundary sampling step, in mm. Straight edges are cut up too, not just curved
# ones, so a gap in the material under an otherwise straight edge is not stepped
# over. The floor keeps a tight curve's polyline hugging it, since an inscribed
# chord falls inside the true boundary and would shorten spans if left coarse;
# the cap stops a long edge from dominating the chord scan, which is quadratic.
_SAMPLE_STEP = 1.0
_MIN_SAMPLES = 24
_MAX_SAMPLES = 64
# A point further than this off the line between its neighbours is a real corner.
_FLATNESS_TOL = 1e-6
# How far to step sideways off a ceiling edge when probing for anchor material.
# Far below any printable wall, far above BREP tolerance.
_PROBE_OUT = 1e-2
# How far to step below the ceiling when probing. Far shallower than
# ``_PROBE_OUT`` because the wall a bridge lands on rarely drops away squarely: a
# filleted roof junction is horizontal where it meets the ceiling and falls away
# as sqrt(2*R*depth), so material is only found within ``_PROBE_OUT**2 / (2*R)``
# of the ceiling. At these values a roof fillet up to 5 mm still reads as an
# anchor, which covers anything a pocket is likely to carry.
_PROBE_DOWN = 1e-5
# Point-classification tolerance, matching ``Shape.is_inside``'s default.
_INSIDE_TOL = 1e-6
# A probe point this far from the ceiling face has stepped off it. A step that
# stays on the face measures 0; one that leaves it measures ``_PROBE_OUT``.
_OUTSIDE_TOL = _PROBE_OUT / 2
# Bridge directions are tried every this many degrees on top of the ones the
# boundary itself suggests: the best direction over a non-convex ceiling need be
# neither along an edge nor across one.
_DIRECTION_STEP_DEG = 5.0
# A direction and its reverse are the same bridge direction, so directions live
# on a half turn rather than a full one.
_HALF_TURN_DEG = 180.0
# Decimal places two directions must agree to before they count as the same one.
# Finer than the fan step by orders of magnitude, so it only ever folds together
# directions that arrived from different sources.
_DIRECTION_DIGITS = 6
# Where to place a scan line inside the gap between two boundary vertices, as a
# fraction of that gap. Any point strictly inside gives the same crossings; this
# sits hard against the ends, where the longest run is.
_SCAN_INSET = 1e-9
# Sine of the widest angle between a bridge line and an unanchored stretch that
# could still leave only a sliver unheld. Purely a cost filter — anything it lets
# through is measured properly by the scan, which is what decides.
_GRAZING = 0.3
# How wide a band of unheld ceiling, in mm, still counts as a sliver rather than a
# corner needing support. Whether such a band actually prints depends on extrusion
# width, which is process context this module does not have and must not invent
# (SPEC.md), so the value is set to over-warn rather than to sit midway: a window
# through a curved wall leaves 0.12 mm and is reported as needing support, where a
# roof whose supports stop short leaves 0.98 mm. Deriving it from a declared nozzle
# would let the curved case through honestly.
_SLIVER_BAND = 0.1
# Ceilings this detailed get described more coarsely for the chord scan, which is
# quadratic in boundary segments and runs once per direction. A lid carrying a
# grid of bosses is one face with a hundred-odd inner wires and would otherwise
# take minutes. Anchor probing is unaffected — only how finely the outline is
# drawn, and a coarser outline can only shorten a chord it measures.
_SCAN_SEGMENTS = 200
# Fewest points an edge keeps however tight the budget: a closed one still has to
# come out as a polygon.
_MIN_POLYGON = 3
# Rough ceiling on scan work, in segment-crossing tests. Directions are dropped to
# stay under it. The span is a minimum over the directions tried, so trying fewer
# can only report a longer span, never a shorter one.
_SCAN_WORK = 2_000_000
# How far, relative to its own length, a boundary segment may stray across a scan
# line and still count as running alongside it. A line running beside a segment
# never lands on it, so such a segment terminates nothing. The bound is float
# noise rather than a modelling choice: a direction read off the boundary is
# parallel to that boundary only to within rounding.
_ALONGSIDE_EPS = 1e-9


def _classifiers(shape: Shape[Any]) -> list[BRepClass3d_SolidClassifier]:
    """One point classifier per solid, built once and reused for every probe.

    ``Shape.is_inside`` rebuilds its classifier on every call, which on a part with
    many faces costs far more than the query itself. One per *solid* rather than one
    for the whole shape because a compound classifier misses points inside all but
    the first solid when they touch — the same trap `wall_thickness` sidesteps.
    """
    return [BRepClass3d_SolidClassifier(solid.wrapped) for solid in shape.solids()]


def _has_material(
    classifiers: list[BRepClass3d_SolidClassifier], x: float, y: float, z: float
) -> bool:
    """True if the point is inside any of the part's solids."""
    point = gp_Pnt(x, y, z)
    for classifier in classifiers:
        classifier.Perform(point, _INSIDE_TOL)
        if classifier.State() == TopAbs_State.TopAbs_IN:
            return True
    return False


def _step_count(edge: Any) -> int:
    """How many pieces of ``_SAMPLE_STEP`` this edge covers.

    Uncapped, unlike the geometric sampling: the cap is there to keep the chord
    scan affordable, and applying it here would stretch the probe spacing on a
    long edge until a gap in the material under it could pass between probes.
    """
    return max(1, math.ceil(float(edge.length) / _SAMPLE_STEP))


def _sample_count(edge: Any) -> int:
    """How finely to describe this edge geometrically — never below the floor that
    keeps a tight curve's polyline hugging it."""
    return max(_MIN_SAMPLES, _step_count(edge))


def _outward_sign(edge: Any, face: Any) -> float:
    """Which perpendicular of the edge tangent points out of the ceiling.

    Probing the wrong way would find whatever fills the space *under* the ceiling.
    The step that leaves the face is the outward one: it lands clear of the face
    rather than on it. Handedness holds along a boundary edge, so one test settles
    the whole edge.
    """
    point = edge.position_at(0.5)
    tangent = edge.tangent_at(0.5)
    probe = Vector(point.X + tangent.Y * _PROBE_OUT, point.Y - tangent.X * _PROBE_OUT, point.Z)
    return -1.0 if face.distance_to(probe) < _OUTSIDE_TOL else 1.0


def _boundary(
    face: Any, classifiers: list[BRepClass3d_SolidClassifier]
) -> list[tuple[float, float, float, float, bool]]:
    """The ceiling's boundary as 2D segments, each flagged with what is under it.

    Every edge — straight or curved — is walked at a fixed step, so nothing here
    depends on how a curve happens to be represented: a spline running dead
    straight yields collinear segments and behaves exactly like a line, which
    matters because imported STEP geometry is full of them.

    Each segment is probed just beyond itself and just below the ceiling for the
    material a bridge line could land on. Probes drop from their own point on the
    curve rather than from a chord across it, or from one height for the whole
    face: an inscribed chord sits inside a tight curve by more than the probe
    reaches, and a ceiling may lean up to ``_FLAT_TOL``, which over a long face
    puts a shared height below the far end where open air reads as solid.
    """
    boundary: list[tuple[float, float, float, float, bool]] = []
    edges = face.edges()
    allowance = max(_MIN_POLYGON, _SCAN_SEGMENTS // max(1, len(edges)))
    for edge in edges:
        count = min(_sample_count(edge), allowance)
        sign = _outward_sign(edge, face)
        # Describing the curve and checking what holds it up want different
        # resolutions. Every probe costs a solid classification, so they follow
        # the step; the polyline is only positions, so it can afford to be finer.
        probes = _step_count(edge)
        anchored = [
            _probe(edge, (index + 0.5) / probes, sign, classifiers) for index in range(probes)
        ]
        points = [edge.position_at(index / count) for index in range(count + 1)]
        run: list[tuple[float, float, float, float, bool]] = []
        for index, (start, end) in enumerate(zip(points, points[1:], strict=False)):
            if start.X == end.X and start.Y == end.Y:
                continue
            held = anchored[min(int((index + 0.5) / count * probes), probes - 1)]
            run.append((start.X, start.Y, end.X, end.Y, held))
        boundary.extend(_merge_runs(run))
    return boundary


def _probe(
    edge: Any, position: float, sign: float, classifiers: list[BRepClass3d_SolidClassifier]
) -> bool:
    """True if there is material just beyond the boundary here to land a bridge on."""
    point = edge.position_at(position)
    tangent = edge.tangent_at(position)
    return _has_material(
        classifiers,
        point.X + tangent.Y * sign * _PROBE_OUT,
        point.Y - tangent.X * sign * _PROBE_OUT,
        point.Z - _PROBE_DOWN,
    )


def _merge_runs(
    segments: list[tuple[float, float, float, float, bool]],
) -> list[tuple[float, float, float, float, bool]]:
    """Join consecutive segments that run straight on and agree about their anchor.

    Sampling is set by the tightest curve a boundary might hold and by how finely
    the material under it has to be checked, which leaves a plain straight edge
    carrying two dozen identical pieces. The chord scan is quadratic in them.
    Merging works off the geometry, so a spline that happens to run straight thins
    out exactly like a line, and it stops wherever the anchor state changes so a
    ceiling supported along only part of an edge keeps that detail.
    """
    merged: list[tuple[float, float, float, float, bool]] = []
    for segment in segments:
        if merged:
            x0, y0, _, _, anchored = merged[-1]
            if anchored == segment[4] and _off_line((x0, y0), segment[2:4], segment[0:2]) <= (
                _FLATNESS_TOL
            ):
                merged[-1] = (x0, y0, segment[2], segment[3], anchored)
                continue
        merged.append(segment)
    return merged


def _off_line(
    start: tuple[float, float], end: tuple[float, float], point: tuple[float, float]
) -> float:
    """Perpendicular distance from ``point`` to the line through ``start``/``end``."""
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = math.hypot(dx, dy)
    if length == 0:
        return math.hypot(point[0] - start[0], point[1] - start[1])
    return abs(dx * (start[1] - point[1]) - dy * (start[0] - point[0])) / length


def _bridge_run(
    boundary: list[tuple[float, float, float, float, bool]], dx: float, dy: float
) -> float | None:
    """Longest bridge line in this direction, or ``None`` if one would fall.

    Bridge lines all run one way over a ceiling and each has to land on material
    at both ends, so the direction only works if *every* line it produces does.
    Testing where the lines actually land is what settles it — asking instead
    which way the unanchored boundary points cannot tell a harmless fan from a
    roof whose sides converge into a corner no line reaches with both ends held.

    Working in a frame where the direction is +u, a scan line's crossings pair up
    into the runs of ceiling it covers, and run lengths vary linearly between one
    boundary vertex and the next — so the longest run always turns up at a scan
    line grazing a vertex, and it is enough to look there.
    """
    turned = [
        (x0 * dx + y0 * dy, -x0 * dy + y0 * dx, x1 * dx + y1 * dy, -x1 * dy + y1 * dx, anchored)
        for x0, y0, x1, y1, anchored in boundary
    ]
    levels = sorted({v for _, v, _, _, _ in turned} | {v for _, _, _, v, _ in turned})
    longest = 0.0
    loose = 0.0
    for lower, upper in zip(levels, levels[1:], strict=False):
        gap = upper - lower
        unheld = False
        for scan in (lower + gap * _SCAN_INSET, upper - gap * _SCAN_INSET):
            crossings = sorted(
                (u0 + (scan - v0) / (v1 - v0) * (u1 - u0), anchored)
                for u0, v0, u1, v1, anchored in turned
                if (v0 > scan) != (v1 > scan)
                and abs(v1 - v0) > _ALONGSIDE_EPS * math.hypot(u1 - u0, v1 - v0)
            )
            for entry, leave in zip(crossings[::2], crossings[1::2], strict=False):
                if entry[1] and leave[1]:
                    longest = max(longest, leave[0] - entry[0])
                else:
                    unheld = True
        if unheld:
            # Accumulated, not maxed: a curved boundary is cut into many short
            # pieces, and a wedge that clears the tolerance in every single piece
            # still leaves the whole wedge unheld.
            loose += gap
    # Unanchored boundary that merely grazes the direction leaves a sliver of
    # ceiling unheld — a window through a tapered or curved wall does this and
    # bridges in practice. A roof whose supports genuinely stop short leaves a
    # band orders of magnitude wider, which is what ``_SLIVER_BAND`` separates.
    return None if loose > _SLIVER_BAND else (longest or None)


def _directions(
    boundary: list[tuple[float, float, float, float, bool]],
) -> list[tuple[float, float]]:
    """Bridge directions worth trying over a ceiling.

    The candidates are the ones across each stretch of boundary — where a convex
    ceiling is always narrowest — plus a regular fan, because a non-convex one
    need not be narrowest across any of its edges.
    """
    seen: dict[tuple[float, float], tuple[float, float]] = {}
    fan = [
        (math.cos(math.radians(angle)), math.sin(math.radians(angle)))
        for angle in _degrees_around_a_half_turn()
    ]
    for x0, y0, x1, y1, _ in boundary:
        length = math.hypot(x1 - x0, y1 - y0)
        fan.append(((y1 - y0) / length, (x0 - x1) / length))
    for dx, dy in fan:
        # A direction and its reverse are one bridge direction, so fold onto a
        # half turn before rounding to a key.
        if dy < 0 or (dy == 0 and dx < 0):
            dx, dy = -dx, -dy
        seen.setdefault((round(dx, _DIRECTION_DIGITS), round(dy, _DIRECTION_DIGITS)), (dx, dy))
    return list(seen.values())


def _degrees_around_a_half_turn() -> list[float]:
    steps = math.ceil(_HALF_TURN_DEG / _DIRECTION_STEP_DEG)
    return [index * _DIRECTION_STEP_DEG for index in range(steps)]


def _bridge_span(face: Any, classifiers: list[BRepClass3d_SolidClassifier]) -> float | None:
    """The unsupported distance a bridge over this flat ceiling has to cross.

    Returns ``None`` when no direction works, so the ceiling needs support however
    small it is — the underside of a floating or cantilevered mass, a slot open at
    one end, or a roof whose supports leave a corner no straight line can reach.

    The slicer lays every bridge line over a ceiling in one direction, and each
    line has to land on material at both ends. So a direction is only usable if
    every line it produces is held at both ends, and the span is the longest line
    in the best such direction.

    Deliberately not a bounding-box dimension. A rectangular window through a thin
    wall has the wall thickness as its narrower side, but there is open air on both
    faces of the wall, so that side anchors nothing and the real span is the window
    width (issue #55). A bounding box also makes the answer depend on how the part
    happens to sit relative to the global axes, which it must not.
    """
    boundary = _boundary(face, classifiers)
    if len(boundary) < 3:
        return None
    candidates = _candidate_directions(boundary)
    affordable = max(1, _SCAN_WORK // max(1, len(boundary) ** 2))
    runs = [_bridge_run(boundary, *d) for d in candidates[:affordable]]
    usable = [run for run in runs if run is not None]
    return min(usable) if usable else None


def _candidate_directions(
    boundary: list[tuple[float, float, float, float, bool]],
) -> list[tuple[float, float]]:
    """Directions a bridge could conceivably run, before checking where lines land.

    A line that crosses a stretch of boundary with nothing under it ends in
    mid-air, and any stretch not running alongside the line gets crossed. So the
    unanchored stretches, if there are any, leave exactly one direction to try —
    and if they do not all run the same way, none at all. That is a necessary
    condition rather than a sufficient one, which is why :func:`_bridge_run` still
    checks each line: a roof whose sides converge passes this and still fails
    there. It is worth doing first only because it is cheap, and it keeps the
    scan, quadratic in boundary segments, off ceilings that cannot use it.
    """
    free = [segment for segment in boundary if not segment[4]]
    directions = _directions(boundary)
    if not free:
        return directions
    # Lines must run near enough alongside every unanchored stretch that what they
    # leave unheld stays a sliver. How much is left is for the scan to measure;
    # this only spares it the directions that obviously cannot work.
    headings = [_unit(segment) for segment in free]
    return [
        direction
        for direction in directions
        if all(
            abs(direction[0] * heading[1] - direction[1] * heading[0]) <= _GRAZING
            for heading in headings
        )
    ] + [
        h for h in headings[:1] if all(abs(h[0] * o[1] - h[1] * o[0]) <= _GRAZING for o in headings)
    ]


def _unit(segment: tuple[float, float, float, float, bool]) -> tuple[float, float]:
    x0, y0, x1, y1, _ = segment
    length = math.hypot(x1 - x0, y1 - y0)
    return (x1 - x0) / length, (y1 - y0) / length


def find_overhangs(
    shape: Shape[Any],
    *,
    support_angle: float = DEFAULT_SUPPORT_ANGLE,
    faces: Iterable[Any] | None = None,
    bed_tol: float = BED_TOL,
    max_bridge: float = DEFAULT_MAX_BRIDGE,
) -> list[Finding]:
    """Return one ``Finding`` per downward face that affects printability.

    Assumes the part is oriented for printing with +Z up and resting at its own
    minimum Z (the build plate). Bed-contact faces are excluded.

    Most findings are ``overhang`` (``WARNING``) faces that need support. A flat
    (horizontal) ceiling is instead reported as a ``bridge`` (``INFO``) — FDM
    bridges it in a few unsupported lines, so it needs no support — when its
    bridge span is at or below ``max_bridge``. The span is the unsupported
    distance the bridge actually has to cross, derived from which stretches of
    the ceiling's boundary have material below them to land on (see
    :func:`_bridge_span`). The underside of a floating or cantilevered mass is
    never a bridge, however narrow, because it has no walls to bridge between.

    Pass ``faces`` to avoid re-iterating ``shape.faces()`` when the caller
    already holds the list.
    """
    z_min = shape.bounding_box().min.Z
    findings: list[Finding] = []
    classifiers = _classifiers(shape)

    for face in faces if faces is not None else shape.faces():
        normal = face.normal_at(face.center())
        nz = normal.Z

        # Upward or vertical faces never need support.
        if nz >= -_DOWNWARD_TOL:
            continue

        # A downward face flush with the build plate is bed contact, not overhang.
        box = face.bounding_box()
        on_bed = abs(box.min.Z - z_min) < bed_tol and nz < -_BED_NORMAL_TOL
        if on_bed:
            continue

        # Angle of the downward normal from straight-down == overhang angle from
        # horizontal. 0deg is a flat ceiling (worst case); 90deg is vertical.
        beta = math.degrees(math.acos(min(1.0, -nz)))
        if beta >= support_angle - _ANGLE_TOL:
            continue

        center = face.center()
        area = face.area
        location = (center.X, center.Y, center.Z)

        # A flat, wall-bounded ceiling short enough to bridge needs no support —
        # report it as an informational bridge, not an overhang warning.
        if beta < _FLAT_TOL and classifiers:
            span = _bridge_span(face, classifiers)
            if span is not None and span <= max_bridge:
                findings.append(
                    Finding(
                        kind="bridge",
                        severity=Severity.INFO,
                        message=f"Flat {area:.1f} mm2 ceiling, {span:.1f} mm span"
                        " - bridges, no support needed",
                        area=area,
                        location=location,
                    )
                )
                continue
            flat = f"Flat {area:.1f} mm2 ceiling at {beta:.1f} deg,"
            message = (
                f"{flat} no bridge direction - needs support"
                if span is None
                else f"{flat} {span:.1f} mm span needs support"
            )
        elif beta < _FLAT_TOL:
            # No solid to probe against, so whether it bridges cannot be told
            # apart from a ceiling that genuinely has nothing under it.
            message = f"Flat {area:.1f} mm2 ceiling at {beta:.1f} deg needs support"
        else:
            message = (
                f"Downward face at {beta:.1f} deg from horizontal ({area:.1f} mm2) needs support"
            )

        findings.append(
            Finding(
                kind="overhang",
                severity=Severity.WARNING,
                message=message,
                area=area,
                location=location,
            )
        )

    return findings
