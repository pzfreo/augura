"""Bed-contact footprint geometry shared by the printability checks.

The bed-contact footprint is the set of flat faces a part rests on — planar
faces lying in its lowest Z plane. The tip-over check uses their convex hull;
the brim check uses their total area.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from build123d import Face, Shape

# A face lies on the bed when it sits within this many mm of the lowest point.
BED_TOL = 1e-3


def bed_contact_faces(
    shape: Shape[Any], *, faces: Iterable[Face] | None = None, bed_tol: float = BED_TOL
) -> list[Face]:
    """Return the planar faces lying in the part's bed plane (its lowest Z)."""
    z_min = shape.bounding_box().min.Z
    result: list[Face] = []
    for face in (faces if faces is not None else shape.faces()):
        box = face.bounding_box()
        if abs(box.min.Z - z_min) < bed_tol and abs(box.max.Z - z_min) < bed_tol:
            result.append(face)
    return result
