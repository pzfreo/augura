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

from augura.footprint import bed_contact_faces
from augura.overhangs import DEFAULT_SUPPORT_ANGLE, find_overhangs

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
    """A candidate orientation and the metrics used to rank it."""

    rotation: Rotation3
    overhang_area: float
    z_height: float = 0.0
    bed_contact_area: float = 0.0


def orientation_scores(
    shape: Shape[Any],
    *,
    support_angle: float = DEFAULT_SUPPORT_ANGLE,
    candidates: list[Rotation3] | None = None,
) -> list[OrientationScore]:
    """Rank candidate orientations best-first.

    Primary key: total unsupported overhang area (lower is better).
    Tie-breakers: shorter Z-height, then greater bed-contact area.

    Each candidate is an ``(X, Y, Z)`` Euler rotation in degrees; the rotated
    part is dropped onto the bed (min Z → 0) before evaluation.
    """
    rotations = _AXIS_ORIENTATIONS if candidates is None else candidates
    scores: list[OrientationScore] = []
    for rotation in rotations:
        oriented = Rotation(*rotation) * shape
        oriented = Pos(0, 0, -oriented.bounding_box().min.Z) * oriented
        area = float(
            sum((f.area or 0.0) for f in find_overhangs(oriented, support_angle=support_angle))
        )
        bb = oriented.bounding_box()
        z_height = float(bb.max.Z)
        contact = float(sum(f.area for f in bed_contact_faces(oriented)))
        scores.append(OrientationScore(
            rotation=rotation,
            overhang_area=area,
            z_height=z_height,
            bed_contact_area=contact,
        ))
    return sorted(scores, key=lambda s: (s.overhang_area, s.z_height, -s.bed_contact_area))
