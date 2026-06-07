"""Brim / raft risk heuristic (Tier 2).

Flags parts likely to lift or peel during printing: a small bed-contact
footprint and/or a high height-to-footprint aspect ratio. Thresholds are
parameters with conservative defaults — absolute adhesion depends on material
and bed, which are out of scope (they live in estampo's profiles).
"""

from __future__ import annotations

import math
from typing import Any

from build123d import Shape

from augura.report import Finding, Severity

# A face lies on the bed when it sits within this many mm of the lowest point.
_BED_TOL = 1e-3
# Defaults: below this contact area, or above this height/sqrt(area) ratio, a
# brim is advised. Tunable per material/bed by the caller.
DEFAULT_MIN_FOOTPRINT_AREA = 50.0
DEFAULT_MAX_ASPECT = 6.0


def _footprint_area(shape: Shape[Any], z_min: float) -> float:
    """Total area of planar faces lying in the bed plane (the contact footprint)."""
    area = 0.0
    for face in shape.faces():
        box = face.bounding_box()
        if abs(box.min.Z - z_min) < _BED_TOL and abs(box.max.Z - z_min) < _BED_TOL:
            area += face.area
    return area


def find_brim_risk(
    shape: Shape[Any],
    *,
    min_footprint_area: float = DEFAULT_MIN_FOOTPRINT_AREA,
    max_aspect: float = DEFAULT_MAX_ASPECT,
) -> list[Finding]:
    """Return a brim recommendation if the part risks lifting off the bed.

    Uses the total planar bed-contact area (its spatial spread is the tip-over
    check's concern) and a height/sqrt(area) slenderness proxy. Abstains when
    there is no planar footprint to measure (e.g. line contact).
    """
    bbox = shape.bounding_box()
    footprint = _footprint_area(shape, bbox.min.Z)
    if footprint <= 0.0:
        return []  # no flat bed contact to assess

    aspect = (bbox.max.Z - bbox.min.Z) / math.sqrt(footprint)
    reasons = []
    if footprint < min_footprint_area:
        reasons.append(f"small bed-contact footprint ({footprint:.0f} mm2)")
    if aspect > max_aspect:
        reasons.append(f"high aspect ratio ({aspect:.1f})")
    if not reasons:
        return []
    return [
        Finding(
            kind="brim",
            severity=Severity.WARNING,
            message="Recommend a brim: " + " and ".join(reasons),
        )
    ]
