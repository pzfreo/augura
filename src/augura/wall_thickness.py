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


def _as_vector(value: Any) -> Vector:
    """Coerce a point/direction to a ``Vector``, rejecting non-(x, y, z) input."""
    if isinstance(value, Vector):
        return value
    seq = tuple(value)
    if len(seq) != 3 or not all(
        isinstance(c, (int, float)) and not isinstance(c, bool) for c in seq
    ):
        raise TypeError(f"expected an (x, y, z) triple of numbers, got {value!r}")
    return Vector(*seq)


def _dedup_sorted(values: Any) -> list[float]:
    """Sorted values with near-duplicates merged: a ray crossing a shared edge is
    reported once per adjacent face, so raw hit distances contain duplicates."""
    out: list[float] = []
    for t in sorted(values):
        if not out or t - out[-1] > _RAY_TOL:
            out.append(t)
    return out


def _line_crossings(shape: Shape[Any], origin: Vector, ray: Vector) -> list[float]:
    """Signed distances (along +``ray``) of every boundary crossing on the whole
    line through ``origin``. Both half-rays are cast and merged so the result never
    depends on whether ``find_intersection_points`` returns the ray or the line."""
    ts: list[float] = []
    for sign in (1.0, -1.0):
        try:
            hits = shape.find_intersection_points(Axis(origin, ray * sign))
        except Exception:
            continue
        ts.extend((hp - origin).dot(ray) for hp, _ in hits)
    return _dedup_sorted(ts)


def _interval_distance(x: float, segment: tuple[float, float]) -> float:
    a, b = segment
    return a - x if x < a else (x - b if x > b else 0.0)


def wall_thickness_at(shape: Shape[Any], point: Any, direction: Any) -> float | None:
    """Local wall thickness along a line through ``point``, or ``None``.

    Measures the length of the solid segment of the line ``point + t*direction``
    that the point lies in or on. **Sign-invariant** — the answer does not depend
    on which way ``direction`` points — and correct wherever the point sits in the
    wall: on a surface, mid-wall, or at an interior junction (it spans the single
    contiguous solid segment containing the point, not point→first-face). If the
    point is in a void, the nearest solid segment along the line is measured.

    Same measured, BREP-exact ray query as :func:`min_wall_thickness`, but at a
    caller-chosen location. Returns ``None`` when the line meets no solid (a miss,
    or an open 2-D face). A near-tangent/grazing ray returns the true (small)
    chord it cuts — which is not a wall; pick a direction that crosses it.

    Assumes a valid (watertight) solid; classification on a non-manifold shell is
    unreliable. ``point``/``direction`` are absolute in the part's own frame.
    """
    origin = _as_vector(point)
    ray = _as_vector(direction)
    if ray.length < _RAY_TOL:
        return None
    ray = ray.normalized()

    crossings = _line_crossings(shape, origin, ray)
    if len(crossings) < 2:
        return None

    # Solid segments = consecutive crossings whose midpoint is inside the solid.
    solids: list[tuple[float, float]] = []
    for a, b in zip(crossings, crossings[1:], strict=False):
        try:
            inside = bool(shape.is_inside(origin + ray * ((a + b) / 2.0)))
        except Exception:
            inside = False
        if inside:
            solids.append((a, b))
    if not solids:
        return None

    # The segment the point lies in/on (t = 0), else the nearest solid segment.
    containing = [s for s in solids if s[0] - _RAY_TOL <= 0.0 <= s[1] + _RAY_TOL]
    a, b = containing[0] if containing else min(solids, key=lambda s: _interval_distance(0.0, s))
    return b - a


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
