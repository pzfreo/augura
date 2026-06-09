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

from build123d import Shape

from augura.report import Finding, Severity

DEFAULT_SUPPORT_ANGLE = 45.0
"""Faces shallower than this many degrees from horizontal need support."""

# A face counts as resting on the bed when its lowest point sits at the part's
# minimum Z *and* it faces almost straight down.
_BED_Z_TOL = 1e-3
_BED_NORMAL_TOL = 0.99
# Normals with a Z-component above this are upward or vertical: no overhang.
_DOWNWARD_TOL = 1e-6
# Float slack so a face at exactly the threshold angle is treated as borderline
# (not flagged) rather than tipping on rounding noise.
_ANGLE_TOL = 1e-3


def find_overhangs(
    shape: Shape[Any],
    *,
    support_angle: float = DEFAULT_SUPPORT_ANGLE,
    faces: Iterable[Any] | None = None,
    bed_tol: float = _BED_Z_TOL,
) -> list[Finding]:
    """Return one ``Finding`` per face that will need support to print.

    Assumes the part is oriented for printing with +Z up and resting at its own
    minimum Z (the build plate). Bed-contact faces are excluded.

    Pass ``faces`` to avoid re-iterating ``shape.faces()`` when the caller
    already holds the list.
    """
    z_min = shape.bounding_box().min.Z
    findings: list[Finding] = []

    for face in (faces if faces is not None else shape.faces()):
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
        if beta < support_angle - _ANGLE_TOL:
            center = face.center()
            findings.append(
                Finding(
                    kind="overhang",
                    severity=Severity.WARNING,
                    message=f"Downward face at {beta:.1f} deg from horizontal needs support",
                    area=face.area,
                    location=(center.X, center.Y, center.Z),
                )
            )

    return findings
