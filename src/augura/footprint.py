"""Bed-contact footprint geometry shared by the printability checks.

The bed-contact footprint is the set of flat faces a part rests on — planar
faces lying in its lowest Z plane. The tip-over check uses their convex hull;
the brim check uses their total area.
"""

from __future__ import annotations

from typing import Any

from build123d import Face, Shape

# A face lies on the bed when it sits within this many mm of the lowest point.
BED_TOL = 1e-3


def bed_contact_faces(shape: Shape[Any]) -> list[Face]:
    """Return the planar faces lying in the part's bed plane (its lowest Z)."""
    z_min = shape.bounding_box().min.Z
    faces: list[Face] = []
    for face in shape.faces():
        box = face.bounding_box()
        if abs(box.min.Z - z_min) < BED_TOL and abs(box.max.Z - z_min) < BED_TOL:
            faces.append(face)
    return faces
