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

from build123d import Face, Shape
from build123d.topology import topo_explore_connected_faces

from augura.footprint import BED_TOL
from augura.report import Finding, Severity

DEFAULT_SUPPORT_ANGLE = 45.0
"""Faces shallower than this many degrees from horizontal need support."""

DEFAULT_MAX_BRIDGE = 5.0
"""A flat (horizontal) downward ceiling whose narrowest span is at or below this
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


def _is_bridgeable(face: Any, shape: Shape[Any], z_plane: float, bed_tol: float) -> bool:
    """True if a flat ceiling is wall-bounded so its bridge lines have anchors.

    Every boundary edge of the ceiling must have a neighbour face that *descends*
    below the ceiling plane — a wall the bridge can start and end on. A pocket or
    slot ceiling is bounded on all sides; the underside of a floating or
    cantilevered mass has neighbours that only rise from its edges, so it is not
    bridgeable and still needs support.
    """
    for edge in face.edges():
        siblings = topo_explore_connected_faces(edge, shape)
        if not any(z_plane - bed_tol > Face(s).bounding_box().min.Z for s in siblings):
            return False
    return True


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
    bridges it in a few unsupported lines, so it needs no support — when both:
    its narrowest span (the smaller in-plane bounding-box extent) is at or below
    ``max_bridge``, *and* it is wall-bounded so the bridge lines have anchors (see
    :func:`_is_bridgeable`). The underside of a floating or cantilevered mass is
    never a bridge, however narrow, because it has no walls to bridge between.

    Pass ``faces`` to avoid re-iterating ``shape.faces()`` when the caller
    already holds the list.
    """
    z_min = shape.bounding_box().min.Z
    findings: list[Finding] = []

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
            fbb = face.bounding_box()
            span = min(fbb.size.X, fbb.size.Y)
            if span <= max_bridge and _is_bridgeable(face, shape, fbb.min.Z, bed_tol):
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
                f"Flat {area:.1f} mm2 ceiling at {beta:.1f} deg, {span:.1f} mm span needs support"
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
