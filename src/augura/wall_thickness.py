"""Wall-thickness check (approximate, opposed-face / ray-sampling).

Estimates the minimum wall thickness by casting rays from sample points on each
face straight into the solid and measuring the distance to the opposite surface,
then flags walls thinner than ``min_perimeters * nozzle``.

Sampling strategy: every face is probed at its centre. For large faces (area
exceeding ``GRID_AREA_THRESHOLD``) an additional interior grid is added using
the face's UV parameterisation via ``face.position_at``, so thin spots away
from the centre are not silently missed.

Vertices are intentionally excluded from sampling: they are topological boundary
points shared with adjacent faces, and rays from them can intersect those
adjacent faces at non-trivial distances, producing false thin-wall readings.

Approximate by design: curved or very large faces may still have unsampled
regions. A medial-axis method would be fully exhaustive.
"""

from __future__ import annotations

from typing import Any

from build123d import Axis, Shape, Vector, Vertex

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
            for i in range(1, _GRID_N + 1):
                for j in range(1, _GRID_N + 1):
                    gp = face.position_at(i / (_GRID_N + 1), j / (_GRID_N + 1))
                    try:
                        gn = -face.normal_at(gp)
                    except Exception:
                        gn = inward
                    pairs.append((gp, gn))
        except Exception:
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
            try:
                hits = list(shape.find_intersection_points(Axis(point, inward)))
            except Exception:
                # A ray grazing a degenerate point (cone apex, pyramid tip) makes
                # OCCT's normal-at-intersection undefined (zero-norm) and throws.
                # Skip this ray; other samples still bound the wall thickness.
                continue
            forward = []
            for hit_point, _ in hits:
                d = (hit_point - point).dot(inward)
                if d > _RAY_TOL:
                    forward.append(d)
            if forward:
                nearest = min(forward)
                if thinnest is None or nearest < thinnest:
                    thinnest = nearest
    return thinnest


def _vertex(v: Vector) -> Vertex:
    return Vertex(v.X, v.Y, v.Z)


def _forward_hits(shape: Shape[Any], origin: Vector, direction: Vector) -> list[float]:
    """Sorted distances (> tol) from ``origin`` to boundary hits along ``direction``.

    Shares the grazing-degenerate-apex guard with :func:`min_wall_thickness`.
    """
    try:
        hits = list(shape.find_intersection_points(Axis(origin, direction)))
    except Exception:
        return []
    forward = [(hp - origin).dot(direction) for hp, _ in hits]
    return sorted(d for d in forward if d > _RAY_TOL)


def _closest_surface_point(face: Any, origin: Vector) -> Vector | None:
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape

    ext = BRepExtrema_DistShapeShape(_vertex(origin).wrapped, face.wrapped)
    if not ext.IsDone() or ext.NbSolution() < 1:
        return None
    p = ext.PointOnShape2(1)
    return Vector(p.X(), p.Y(), p.Z())


def _nearest_surface(shape: Shape[Any], origin: Vector) -> tuple[Vector, Vector] | None:
    """Return (closest surface point, inward normal) for the face nearest ``origin``."""
    v = _vertex(origin)
    best: Any = None
    best_d: float | None = None
    for face in shape.faces():
        try:
            d = face.distance_to(v)
        except Exception:
            continue
        if best_d is None or d < best_d:
            best_d, best = d, face
    if best is None:
        return None
    cp = _closest_surface_point(best, origin)
    if cp is None:
        return None
    try:
        return cp, -best.normal_at(cp)
    except Exception:
        return None


def wall_thickness_at(shape: Shape[Any], point: Any, direction: Any | None = None) -> float | None:
    """Local wall thickness at ``point``, or ``None`` if no opposite surface.

    Same measured, BREP-exact ray query as :func:`min_wall_thickness`, but at a
    caller-chosen location instead of face samples:

    - ``direction`` given: measures the solid **chord** along that line *through*
      ``point`` — correct even when ``point`` is mid-wall (it spans the segment
      containing the point, not merely point→first-face) or in a void ahead of a
      wall (the first entry→exit segment).
    - ``direction`` omitted: snaps ``point`` to the nearest face and measures
      inward along that face's normal — the robust opposed-face path, no reliance
      on where in the wall the caller placed the point.

    Returns ``None`` when the ray finds no opposite surface (misses, or an open
    2-D face with no material). Assumes a valid (watertight) solid, like every
    ray/inside query; classification on a non-manifold shell is unreliable.
    """
    origin = point if isinstance(point, Vector) else Vector(point)

    if direction is None:
        near = _nearest_surface(shape, origin)
        if near is None:
            return None
        origin, ray = near
        forward = _forward_hits(shape, origin, ray)
        return min(forward) if forward else None

    ray = direction if isinstance(direction, Vector) else Vector(direction)
    if ray.length < _RAY_TOL:
        return None
    ray = ray.normalized()
    forward = _forward_hits(shape, origin, ray)

    try:
        on_surface = shape.distance_to(_vertex(origin)) < _RAY_TOL
    except Exception:
        on_surface = False
    if on_surface:  # a surface point: nearest opposite face is the wall
        return min(forward) if forward else None

    try:
        inside = bool(shape.is_inside(origin))
    except Exception:
        inside = False
    if inside:  # interior point: span the wall on both sides
        back = _forward_hits(shape, origin, -ray)
        return (min(forward) + min(back)) if forward and back else None

    # void / outside: chord of the first solid segment the ray crosses
    return (forward[1] - forward[0]) if len(forward) >= 2 else None


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
