"""Orientation search.

Scores a set of candidate print orientations by the total unsupported overhang
area each would require, reusing the overhang check per candidate. Returns the
full ranked frontier (best first) rather than a single "best" pose, so the
caller can weigh support cost against other concerns.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from build123d import Pos, Rotation, Shape

from augura.overhangs import DEFAULT_SUPPORT_ANGLE, find_overhangs

Rotation3 = tuple[float, float, float]

# Default candidates: the six axis-aligned orientations (each principal axis
# pointing down in turn). Override via `candidates` for a finer search.
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
    """A candidate orientation and the overhang area it would need supported."""

    rotation: Rotation3
    overhang_area: float


def orientation_scores(
    shape: Shape[Any],
    *,
    support_angle: float = DEFAULT_SUPPORT_ANGLE,
    candidates: list[Rotation3] | None = None,
) -> list[OrientationScore]:
    """Rank candidate orientations by total unsupported overhang area (best first).

    Each candidate is an ``(X, Y, Z)`` Euler rotation in degrees; the rotated
    part is dropped onto the bed before its overhangs are measured. Ties keep the
    candidate input order.
    """
    rotations = _AXIS_ORIENTATIONS if candidates is None else candidates
    scores: list[OrientationScore] = []
    for rotation in rotations:
        oriented = Rotation(*rotation) * shape
        oriented = Pos(0, 0, -oriented.bounding_box().min.Z) * oriented
        area = float(
            sum((f.area or 0.0) for f in find_overhangs(oriented, support_angle=support_angle))
        )
        scores.append(OrientationScore(rotation=rotation, overhang_area=area))
    return sorted(scores, key=lambda s: s.overhang_area)
