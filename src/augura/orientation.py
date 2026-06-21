"""Orientation search.

Scores a set of candidate print orientations by the total unsupported overhang
area each would require, reusing the overhang check per candidate. Returns the
full ranked frontier (best first) rather than a single "best" pose, so the
caller can weigh support cost against other concerns.

Tie-breaking (same overhang area): prefer shorter Z-height first (faster print),
then more bed-contact area (better adhesion).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from build123d import Pos, Rotation, Shape

from augura.bed_fit import overflowing_axes
from augura.cadquery_adapter import as_build123d, is_cadquery
from augura.footprint import BED_TOL, bed_contact_faces
from augura.overhangs import DEFAULT_MAX_BRIDGE, DEFAULT_SUPPORT_ANGLE, find_overhangs

Rotation3 = tuple[float, float, float]

_AXIS_ORIENTATIONS: list[Rotation3] = [
    (0, 0, 0),
    (180, 0, 0),
    (90, 0, 0),
    (-90, 0, 0),
    (0, 90, 0),
    (0, -90, 0),
]


@dataclass(frozen=True)
class OrientationScore:
    """A candidate orientation and the metrics used to rank it.

    ``fits_build_volume`` is ``None`` unless :func:`orientation_scores` was
    given a ``build_volume`` to check against.
    """

    rotation: Rotation3
    overhang_area: float
    z_height: float = 0.0
    bed_contact_area: float = 0.0
    fits_build_volume: bool | None = None


def _pose(shape: Shape[Any], rotation: Rotation3) -> tuple[Shape[Any], Any]:
    """Rotate a build123d shape then drop it onto the bed; also returns the
    pre-drop bounding box (extents are translation-invariant, so it describes
    the posed part too)."""
    oriented = Rotation(*rotation) * shape
    bb = oriented.bounding_box()
    dropped: Shape[Any] = Pos(0, 0, -bb.min.Z) * oriented
    return dropped, bb


def apply_orientation(shape: Shape[Any], rotation: Rotation3) -> Shape[Any]:
    """Pose *shape* exactly as :func:`orientation_scores` evaluated it.

    *rotation* is an ``(X, Y, Z)`` Euler rotation in degrees (build123d
    ``Rotation`` convention: intrinsic rotations about X, then Y, then Z). The
    rotated part is dropped onto the bed (min Z → 0).
    """
    if is_cadquery(shape):
        shape = as_build123d(shape)
    return _pose(shape, rotation)[0]


def orientation_scores(
    shape: Shape[Any],
    *,
    support_angle: float = DEFAULT_SUPPORT_ANGLE,
    candidates: list[Rotation3] | None = None,
    bed_tol: float = BED_TOL,
    build_volume: tuple[float, float, float] | None = None,
    max_bridge: float = DEFAULT_MAX_BRIDGE,
) -> list[OrientationScore]:
    """Rank candidate orientations best-first.

    Primary key: total unsupported overhang area (lower is better).
    Tie-breakers: shorter Z-height, then greater bed-contact area.
    When *build_volume* is given, poses whose bounding box fits it rank before
    poses that don't (so a feasible pose always beats an infeasible one); if
    nothing fits, the ranking is unchanged. Each score's ``fits_build_volume``
    records the per-pose result.

    Each candidate is an ``(X, Y, Z)`` Euler rotation in degrees (build123d
    ``Rotation`` convention; see :func:`apply_orientation`); the rotated part
    is dropped onto the bed (min Z → 0) before evaluation.
    """
    if is_cadquery(shape):
        shape = as_build123d(shape)
    rotations = _AXIS_ORIENTATIONS if candidates is None else candidates
    scores: list[OrientationScore] = []
    for rotation in rotations:
        oriented, bb = _pose(shape, rotation)
        size = bb.size
        fits: bool | None = None
        if build_volume is not None:
            fits = not overflowing_axes((size.X, size.Y, size.Z), build_volume)
        faces = list(oriented.faces())
        area = float(
            sum(
                (f.area or 0.0)
                for f in find_overhangs(
                    oriented,
                    support_angle=support_angle,
                    faces=faces,
                    bed_tol=bed_tol,
                    max_bridge=max_bridge,
                )
                if f.kind == "overhang"
            )
        )
        contact = float(
            sum(f.area for f in bed_contact_faces(oriented, faces=faces, bed_tol=bed_tol))
        )
        scores.append(
            OrientationScore(
                rotation=rotation,
                overhang_area=area,
                z_height=float(size.Z),
                bed_contact_area=contact,
                fits_build_volume=fits,
            )
        )
    return sorted(
        scores,
        key=lambda s: (
            s.fits_build_volume is False,
            s.overhang_area,
            s.z_height,
            -s.bed_contact_area,
        ),
    )
