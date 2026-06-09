"""Wall-thickness check (approximate, opposed-face / ray-sampling).

Estimates the minimum wall thickness by casting rays from sample points on each
face straight into the solid and measuring the distance to the opposite surface,
then flags walls thinner than ``min_perimeters * nozzle``.

Sampling strategy: every face is probed at its centre. For large faces (area
exceeding ``GRID_AREA_THRESHOLD``) an additional interior grid is added using
the face's UV parameterisation via OCC BRepAdaptor_Surface, so thin spots away
from the centre are not silently missed.

Vertices are intentionally excluded from sampling: they are topological boundary
points shared with adjacent faces, and rays from them can intersect those
adjacent faces at non-trivial distances, producing false thin-wall readings.

Approximate by design: curved or very large faces may still have unsampled
regions. A medial-axis method would be fully exhaustive.
"""

from __future__ import annotations

import math
from typing import Any

from build123d import Axis, Shape, Vector

from augura.report import Finding, Severity

DEFAULT_NOZZLE = 0.4
DEFAULT_MIN_PERIMETERS = 2
_RAY_TOL = 1e-6
GRID_AREA_THRESHOLD = 100.0  # mm² — faces larger than this get an interior grid
_GRID_N = 3  # interior grid is (_GRID_N × _GRID_N) points


def _face_sample_pairs(face: Any) -> list[tuple[Any, Any]]:
    """Return (point, inward_normal) pairs to probe for wall thickness.

    Always includes the face centre. For large faces (area exceeding
    ``GRID_AREA_THRESHOLD``) adds a UV-space interior grid so thin spots
    away from the centre are not silently missed.

    Vertices are excluded: they are boundary points shared with adjacent faces
    and rays from them can hit those faces at real distances, producing false
    thin-wall readings.
    """
    center = face.center()
    inward = -face.normal_at(center)
    pairs: list[tuple[Any, Any]] = [(center, inward)]

    if face.area > GRID_AREA_THRESHOLD:
        try:
            from OCP.BRepAdaptor import BRepAdaptor_Surface  # type: ignore[import]
            from OCP.gp import gp_Pnt  # type: ignore[import]

            adaptor = BRepAdaptor_Surface(face.wrapped)
            u0, u1 = adaptor.FirstUParameter(), adaptor.LastUParameter()
            v0, v1 = adaptor.FirstVParameter(), adaptor.LastVParameter()
            if all(math.isfinite(x) for x in (u0, u1, v0, v1)):
                for i in range(1, _GRID_N + 1):
                    for j in range(1, _GRID_N + 1):
                        u = u0 + (u1 - u0) * i / (_GRID_N + 1)
                        v = v0 + (v1 - v0) * j / (_GRID_N + 1)
                        pt = gp_Pnt()
                        adaptor.D0(u, v, pt)
                        gp = Vector(pt.X(), pt.Y(), pt.Z())
                        try:
                            gn = -face.normal_at(gp)
                        except Exception:
                            gn = inward
                        pairs.append((gp, gn))
        except Exception:  # ImportError or OCC Standard_Failure / RuntimeError
            pass  # fall back to centre-only for this face

    return pairs


def min_wall_thickness(shape: Shape[Any]) -> float | None:
    """Return the smallest sampled wall thickness, or None.

    None when no sample point on any face has an opposite surface ahead of it
    (e.g. a bare 2-D face with no solid behind it).
    """
    thinnest: float | None = None
    for face in shape.faces():
        for point, inward in _face_sample_pairs(face):
            forward = []
            for hit_point, _ in shape.find_intersection_points(Axis(point, inward)):
                d = (hit_point - point).dot(inward)
                if d > _RAY_TOL:
                    forward.append(d)
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
