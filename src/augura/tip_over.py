"""Tip-over / stability check.

A part is statically stable iff its centre of mass projects straight down into
the convex hull of its bed-contact footprint (the support-polygon criterion).
If the projected COM falls outside that hull, the part topples.
"""

from __future__ import annotations

from typing import Any

from build123d import CenterOf, Shape

from augura.footprint import BED_TOL, bed_contact_faces
from augura.report import Finding, Severity

Point = tuple[float, float]

# Cross-product slack so a COM exactly on the hull boundary counts as stable.
_HULL_TOL = 1e-9


def _convex_hull(points: list[Point]) -> list[Point]:
    """Counter-clockwise convex hull via Andrew's monotone chain."""
    pts = sorted(set(points))
    if len(pts) < 3:
        return pts

    def cross(o: Point, a: Point, b: Point) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[Point] = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: list[Point] = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def _inside_hull(point: Point, hull: list[Point]) -> bool:
    """Whether ``point`` lies within the counter-clockwise ``hull`` (inclusive)."""
    x, y = point
    n = len(hull)
    for i in range(n):
        ax, ay = hull[i]
        bx, by = hull[(i + 1) % n]
        # CCW hull: interior points are left of every directed edge (cross >= 0).
        if (bx - ax) * (y - ay) - (by - ay) * (x - ax) < -_HULL_TOL:
            return False
    return True


def find_tip_over(shape: Shape[Any], *, bed_tol: float = BED_TOL) -> list[Finding]:
    """Return a finding if the part's COM falls outside its support polygon.

    Only flat faces lying in the bed plane contribute to the support polygon;
    parts that rest on tilted faces, edges, or points abstain (no finding).
    """
    points: list[Point] = [
        (vertex.X, vertex.Y) for face in bed_contact_faces(shape, bed_tol=bed_tol) for vertex in face.vertices()
    ]
    hull = _convex_hull(points)
    if len(hull) < 3:
        return []  # no usable support polygon (e.g. line or point contact)
    com = shape.center(CenterOf.MASS)
    if _inside_hull((com.X, com.Y), hull):
        return []
    return [
        Finding(
            kind="tip_over",
            severity=Severity.ERROR,
            message=(
                f"Centre of mass ({com.X:.1f}, {com.Y:.1f}) projects outside the "
                "bed-contact footprint; the part will topple"
            ),
        )
    ]
