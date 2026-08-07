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

from build123d import Axis, GeomType, Shape, Vector
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
# Where along each boundary edge to probe for anchor material. Interior positions
# only: at a shared endpoint the neighbouring edge's material confuses the answer.
_EDGE_SAMPLES = (0.25, 0.5, 0.75)
# How far to step sideways off a ceiling edge when probing for anchor material.
# Far below any printable wall, far above BREP tolerance.
_PROBE_OUT = 1e-2
# How far to step below the ceiling plane when probing. Much smaller than
# ``_PROBE_OUT`` so a wall that slopes as it descends is still hit; probing short
# only ever loses an anchor, which errs toward warning the user.
_PROBE_DOWN = 1e-3
# Two edge directions whose 2D cross product is under this count as parallel.
_PARALLEL_TOL = 1e-6
# Point-classification tolerance, matching ``Shape.is_inside``'s default.
_INSIDE_TOL = 1e-6
# A probe point this far from the ceiling face has stepped off it. A step that
# stays on the face measures 0; one that leaves it measures ``_PROBE_OUT``.
_OUTSIDE_TOL = _PROBE_OUT / 2


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


def _is_anchored(
    edge: Any, face: Any, z_plane: float, classifiers: list[BRepClass3d_SolidClassifier]
) -> bool:
    """True if a ceiling boundary edge has material below it to land a bridge on.

    Probes just beyond the edge and just below the ceiling plane — a wall the
    bridge lines can start and end on. Probing the wrong way would find whatever
    fills the space *under* the ceiling instead, so each probe direction is
    checked against the face first.
    """
    z = z_plane - _PROBE_DOWN
    # Turning the unit tangent a quarter-turn about Z gives the in-plane normal,
    # but not which way is out of the ceiling. The step that leaves the face is
    # the outward one: it lands clear of the face rather than on it. The tangent
    # turns with the edge, so this handedness holds for the whole edge and is
    # worth establishing once — the containment test is the expensive part here.
    mid = edge.position_at(0.5)
    mid_tangent = edge.tangent_at(0.5)
    sign = 1.0
    probe = Vector(mid.X + mid_tangent.Y * _PROBE_OUT, mid.Y - mid_tangent.X * _PROBE_OUT, z_plane)
    if face.distance_to(probe) < _OUTSIDE_TOL:
        sign = -1.0

    for u in _EDGE_SAMPLES:
        point = edge.position_at(u)
        tangent = edge.tangent_at(u)
        step_x = tangent.Y * _PROBE_OUT * sign
        step_y = -tangent.X * _PROBE_OUT * sign
        if not _has_material(classifiers, point.X + step_x, point.Y + step_y, z):
            return False
    return True


def _extent(face: Any, direction: Vector) -> float:
    """Size of a flat ceiling measured along ``direction``, in the ceiling plane."""
    angle = math.degrees(math.atan2(direction.Y, direction.X))
    return float(face.rotate(Axis.Z, -angle).bounding_box().size.X)


def _bridge_span(
    face: Any, classifiers: list[BRepClass3d_SolidClassifier], z_plane: float
) -> float | None:
    """The unsupported distance a bridge over this flat ceiling has to cross.

    Returns ``None`` when no bridge direction works, so the ceiling needs support
    however small it is — the underside of a floating or cantilevered mass, or a
    slot open at one end.

    The slicer lays every bridge line over a ceiling in one direction, and each
    line has to land on material at both ends. So the boundary edges that carry
    no material below them — the *free* edges — decide the direction: bridge lines
    must run parallel to all of them, or a line ends in mid-air. With no free
    edges any direction works and the narrowest one wins, which for a convex
    ceiling is measured perpendicular to one of its edges.

    Deliberately not a bounding-box dimension. A rectangular window through a thin
    wall has the wall thickness as its narrower side, but there is open air on both
    faces of the wall, so that side anchors nothing and the real span is the window
    width (issue #55). A bounding box also makes the answer depend on how the part
    happens to sit relative to the global axes, which it must not.
    """
    free: list[Any] = []
    perpendiculars: list[Vector] = []
    for edge in face.edges():
        if edge.geom_type == GeomType.LINE:
            tangent = edge.tangent_at(0.5)
            perpendiculars.append(Vector(tangent.Y, -tangent.X, 0))
        if not _is_anchored(edge, face, z_plane, classifiers):
            free.append(edge)

    if not free:
        if not perpendiculars:
            # An all-curved anchored boundary: no edge to measure across, so fall
            # back to the bounding box (exact for the circular ceilings this hits).
            box = face.bounding_box()
            return float(min(box.size.X, box.size.Y))
        return min(_extent(face, d) for d in perpendiculars)

    # A curved free edge changes direction along its length, so no single bridge
    # direction can stay parallel to it.
    if any(edge.geom_type != GeomType.LINE for edge in free):
        return None
    heading = free[0].tangent_at(0.5)
    for edge in free[1:]:
        other = edge.tangent_at(0.5)
        if abs(heading.X * other.Y - heading.Y * other.X) > _PARALLEL_TOL:
            return None
    return _extent(face, heading)


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
    distance the bridge actually has to cross, derived from which of the ceiling's
    boundary edges have material below them to land on (see :func:`_bridge_span`).
    The underside of a floating or cantilevered mass is never a bridge, however
    narrow, because it has no walls to bridge between.

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
            message = (
                f"Flat {area:.1f} mm2 ceiling at {beta:.1f} deg, no bridge anchors - needs support"
                if span is None
                else f"Flat {area:.1f} mm2 ceiling at {beta:.1f} deg,"
                f" {span:.1f} mm span needs support"
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
