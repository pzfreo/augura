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
# over. The floor keeps a tight curve's polyline hugging it: an inscribed chord
# falls inside the true boundary, which shortens spans if left coarse.
_SAMPLE_STEP = 1.0
_MAX_SAMPLES = 64
# Anchor probing and polyline fidelity want different things from the same walk.
# Probes cost a solid classification each, so they follow the step alone; the
# polyline is only positions, so a tight curve can afford a floor that keeps its
# chords hugging it. An inscribed chord falls inside the true boundary, which
# shortens spans if left coarse.
_MIN_PROBES = 3
_MIN_OUTLINE_SAMPLES = 24
# A point further than this off the line between its neighbours is a real corner.
_FLATNESS_TOL = 1e-6
# How far to step sideways off a ceiling edge when probing for anchor material.
# Far below any printable wall, far above BREP tolerance.
_PROBE_OUT = 1e-2
# How far to step below the ceiling plane when probing. Much smaller than
# ``_PROBE_OUT`` so a wall that slopes as it descends is still hit; probing short
# only ever loses an anchor, which errs toward warning the user.
_PROBE_DOWN = 1e-3
# Two directions whose 2D cross product is under this count as parallel.
_PARALLEL_TOL = 1e-6
# Point-classification tolerance, matching ``Shape.is_inside``'s default.
_INSIDE_TOL = 1e-6
# A probe point this far from the ceiling face has stepped off it. A step that
# stays on the face measures 0; one that leaves it measures ``_PROBE_OUT``.
_OUTSIDE_TOL = _PROBE_OUT / 2
# Bridge directions are tried every this many degrees on top of the ones the
# boundary itself suggests: the best direction over a non-convex ceiling need be
# neither along an edge nor across one.
_DIRECTION_STEP_DEG = 5.0
# Directions that survive to the chord sweep, cheapest-looking first. Sweeping
# fewer can only over-report the span, since the span is a minimum over them.
_MAX_DIRECTIONS = 12


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


def _outline(face: Any) -> list[tuple[float, float, float, float]]:
    """The ceiling's boundary as 2D segments ``(x0, y0, x1, y1)``.

    Every edge — straight or curved — is walked at a fixed step, so nothing here
    depends on how a curve happens to be represented. A spline that runs dead
    straight yields collinear segments and behaves exactly like a line, which
    matters because imported STEP geometry is full of them.
    """
    segments: list[tuple[float, float, float, float]] = []
    for edge in face.edges():
        count = _sample_count(edge, _MIN_OUTLINE_SAMPLES)
        points = _drop_collinear(
            [(p.X, p.Y) for p in (edge.position_at(i / count) for i in range(count + 1))]
        )
        for (x0, y0), (x1, y1) in zip(points, points[1:], strict=False):
            if x0 != x1 or y0 != y1:
                segments.append((x0, y0, x1, y1))
    return segments


def _sample_count(edge: Any, floor: int) -> int:
    return max(floor, min(_MAX_SAMPLES, math.ceil(float(edge.length) / _SAMPLE_STEP)))


def _off_line(
    start: tuple[float, float], end: tuple[float, float], point: tuple[float, float]
) -> float:
    """Perpendicular distance from ``point`` to the line through ``start``/``end``."""
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = math.hypot(dx, dy)
    if length == 0:
        return math.hypot(point[0] - start[0], point[1] - start[1])
    return abs(dx * (start[1] - point[1]) - dy * (start[0] - point[0])) / length


def _drop_collinear(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Thin a sampled edge back down to its corners.

    Sampling is set by the tightest curve a boundary might hold, which leaves a
    straight edge carrying two dozen redundant points. They cost nothing to probe
    for anchors but would multiply the chord sweep, which is quadratic in the
    number of segments. Works off the geometry, so a spline that happens to run
    straight thins out exactly like a line.
    """
    kept = [points[0]]
    for index in range(1, len(points) - 1):
        if _off_line(kept[-1], points[index + 1], points[index]) > _FLATNESS_TOL:
            kept.append(points[index])
    kept.append(points[-1])
    return kept


def _outward_sign(edge: Any, face: Any) -> float:
    """Which perpendicular of the edge tangent points out of the ceiling.

    Probing the wrong way would find whatever fills the space *under* the
    ceiling. The step that leaves the face is the outward one; handedness is
    constant along a valid boundary edge, so one test settles the whole edge.
    """
    point = edge.position_at(0.5)
    tangent = edge.tangent_at(0.5)
    probe = Vector(point.X + tangent.Y * _PROBE_OUT, point.Y - tangent.X * _PROBE_OUT, point.Z)
    return -1.0 if face.distance_to(probe) < _OUTSIDE_TOL else 1.0


def _bridge_heading(
    face: Any, z_plane: float, classifiers: list[BRepClass3d_SolidClassifier]
) -> tuple[bool, tuple[float, float] | None]:
    """Which way bridge lines have to run over this ceiling.

    Returns ``(False, None)`` when nothing works, ``(True, None)`` when the
    ceiling is anchored the whole way round so any direction does, and
    ``(True, heading)`` when the unanchored stretches pin it to one.

    Walks each edge at ``_SAMPLE_STEP``, probing from the point on the curve
    itself rather than from a chord across it — an inscribed chord sits inside a
    tight curve by more than the probe reaches, which would read as open air.
    A stretch with nothing to land on forces bridge lines parallel to it, so two
    such stretches at an angle to each other settle the answer immediately.
    """
    heading: tuple[float, float] | None = None
    for edge in face.edges():
        count = _sample_count(edge, _MIN_PROBES)
        sign = _outward_sign(edge, face)
        for index in range(count):
            position = (index + 0.5) / count
            point = edge.position_at(position)
            tangent = edge.tangent_at(position)
            out_x, out_y = tangent.Y * sign, -tangent.X * sign
            if _has_material(
                classifiers,
                point.X + out_x * _PROBE_OUT,
                point.Y + out_y * _PROBE_OUT,
                z_plane - _PROBE_DOWN,
            ):
                continue
            if heading is None:
                heading = (tangent.X, tangent.Y)
            elif abs(heading[0] * tangent.Y - heading[1] * tangent.X) > _PARALLEL_TOL:
                return False, None
    return True, heading


def _extent(segments: list[tuple[float, float, float, float]], dx: float, dy: float) -> float:
    """How far the ceiling reaches along a direction — an upper bound on its chords."""
    projections = [x * dx + y * dy for x0, y0, x1, y1 in segments for x, y in ((x0, y0), (x1, y1))]
    return max(projections) - min(projections)


def _longest_chord(
    segments: list[tuple[float, float, float, float]], dx: float, dy: float
) -> float:
    """The longest line in this direction that stays inside the ceiling.

    Not the same as the ceiling's extent once it stops being convex: an L-shaped
    cavity measures its full diagonal end to end, but no single bridge line ever
    spans more than the width of one arm. Working in a frame where the direction
    is +u, a scan line's crossings pair up into interior runs, and run lengths
    vary linearly between one boundary vertex and the next — so the longest run
    always turns up at a scan line grazing a vertex.
    """
    turned = [
        (x0 * dx + y0 * dy, -x0 * dy + y0 * dx, x1 * dx + y1 * dy, -x1 * dy + y1 * dx)
        for x0, y0, x1, y1 in segments
    ]
    levels = sorted({v for _, v, _, _ in turned} | {v for _, _, _, v in turned})
    longest = 0.0
    for lower, upper in zip(levels, levels[1:], strict=False):
        gap = upper - lower
        for scan in (lower + gap * 1e-9, upper - gap * 1e-9):
            crossings = sorted(
                u0 + (scan - v0) / (v1 - v0) * (u1 - u0)
                for u0, v0, u1, v1 in turned
                if (v0 > scan) != (v1 > scan)
            )
            for entry, leave in zip(crossings[::2], crossings[1::2], strict=False):
                longest = max(longest, leave - entry)
    return longest


def _directions(segments: list[tuple[float, float, float, float]]) -> list[tuple[float, float]]:
    """Bridge directions worth trying over a ceiling that is anchored all round.

    Every direction is viable there, and the narrowest wins. The candidates are
    the ones across each stretch of boundary — where a convex ceiling is always
    narrowest — plus a regular fan, because a non-convex one need not be.
    """
    seen: dict[tuple[float, float], tuple[float, float]] = {}
    fan = [
        (math.cos(math.radians(a)), math.sin(math.radians(a)))
        for a in _frange(0.0, 180.0, _DIRECTION_STEP_DEG)
    ]
    for x0, y0, x1, y1 in segments:
        length = math.hypot(x1 - x0, y1 - y0)
        fan.append(((y1 - y0) / length, (x0 - x1) / length))
    for dx, dy in fan:
        # A direction and its reverse are one bridge direction, so fold onto a
        # half-turn before rounding to a key.
        if dy < 0 or (dy == 0 and dx < 0):
            dx, dy = -dx, -dy
        seen.setdefault((round(dx, 6), round(dy, 6)), (dx, dy))
    return list(seen.values())


def _frange(start: float, stop: float, step: float) -> list[float]:
    return [start + step * i for i in range(math.ceil((stop - start) / step))]


def _bridge_span(
    face: Any, classifiers: list[BRepClass3d_SolidClassifier], z_plane: float
) -> float | None:
    """The unsupported distance a bridge over this flat ceiling has to cross.

    Returns ``None`` when no bridge direction works, so the ceiling needs support
    however small it is — the underside of a floating or cantilevered mass, or a
    slot open at one end.

    The slicer lays every bridge line over a ceiling in one direction, and each
    line has to land on material at both ends. So the stretches of boundary that
    carry no material below them — the *free* ones — decide the direction: bridge
    lines must run parallel to all of them, or a line ends in mid-air. Anchored
    all round, any direction works and the narrowest wins.

    Deliberately not a bounding-box dimension. A rectangular window through a thin
    wall has the wall thickness as its narrower side, but there is open air on both
    faces of the wall, so that side anchors nothing and the real span is the window
    width (issue #55). A bounding box also makes the answer depend on how the part
    happens to sit relative to the global axes, which it must not.
    """
    feasible, heading = _bridge_heading(face, z_plane, classifiers)
    if not feasible:
        return None

    segments = _outline(face)
    if len(segments) < 3:
        return None
    if heading is not None:
        return _longest_chord(segments, *heading)

    candidates = sorted(_directions(segments), key=lambda d: _extent(segments, *d))
    return min(_longest_chord(segments, *d) for d in candidates[:_MAX_DIRECTIONS])


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
        on_bed = abs(face.bounding_box().min.Z - z_min) < bed_tol and nz < -_BED_NORMAL_TOL
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
        if beta < _FLAT_TOL:
            span = _bridge_span(face, classifiers, face.bounding_box().min.Z)
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
