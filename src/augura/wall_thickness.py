"""Wall-thickness check (approximate, opposed-face / ray-sampling).

Estimates the minimum wall thickness by casting a ray from each face's centre
straight into the solid and measuring the distance to the opposite surface, then
flags walls thinner than ``min_perimeters * nozzle``.

Approximate by design: it samples a single point (the centre) per face, so it
represents reasonably uniform walls (like the tube fixture) well but can miss a
thin spot away from a face centre. A finer sample grid or a medial-axis method
would be more robust — see the tracking issue.
"""

from __future__ import annotations

from typing import Any

from build123d import Axis, Shape

from augura.report import Finding, Severity

DEFAULT_NOZZLE = 0.4
DEFAULT_MIN_PERIMETERS = 2
# Ignore the ray's own start point (distance ~0) when finding the far surface.
_RAY_TOL = 1e-6


def min_wall_thickness(shape: Shape[Any]) -> float | None:
    """Return the smallest face-centre-to-opposite-surface distance, or None.

    None when no face centre has a surface ahead of it (e.g. a bare 2-D face).
    """
    thinnest: float | None = None
    for face in shape.faces():
        point = face.center()
        inward = -face.normal_at(point)
        forward = []
        for hit_point, _normal in shape.find_intersection_points(Axis(point, inward)):
            distance = (hit_point - point).dot(inward)
            if distance > _RAY_TOL:
                forward.append(distance)
        if forward:
            nearest = min(forward)
            if thinnest is None or nearest < thinnest:
                thinnest = nearest
    return thinnest


def find_thin_walls(
    shape: Shape[Any],
    *,
    nozzle: float = DEFAULT_NOZZLE,
    min_perimeters: int = DEFAULT_MIN_PERIMETERS,
) -> list[Finding]:
    """Return a finding when a wall is thinner than ``min_perimeters * nozzle``."""
    thickness = min_wall_thickness(shape)
    threshold = nozzle * min_perimeters
    if thickness is None or thickness >= threshold:
        return []
    return [
        Finding(
            kind="thin_wall",
            severity=Severity.WARNING,
            message=(
                f"Wall as thin as {thickness:.2f} mm; below {min_perimeters} perimeters "
                f"at a {nozzle:.1f} mm nozzle ({threshold:.1f} mm)"
            ),
        )
    ]
