"""Minimum vertical feature / layer-height bound.

The smallest vertical detail a part contains caps the usable layer height: you
need at least one layer to render it. This estimates that detail as the smallest
gap between distinct horizontal (normal +/-Z) face planes — the finest step the
print must resolve in Z.

This is a heuristic: it measures Z-resolution between horizontal faces, not thin
features in arbitrary directions (thin vertical walls are the wall-thickness
check's concern).
"""

from __future__ import annotations

from typing import Any

from build123d import Shape

from augura.report import Finding, Severity

# A face is horizontal when its normal is within this of +/-Z.
_PLANAR_TOL = 1e-6
# Below this smallest-feature size, flag the layer-height bound (tunable).
DEFAULT_MIN_FEATURE = 0.5


def min_vertical_feature(shape: Shape[Any]) -> float | None:
    """Return the smallest gap between horizontal face planes, or None.

    None when the shape has fewer than two distinct horizontal face levels (no
    measurable vertical step).
    """
    levels = []
    for face in shape.faces():
        normal = face.normal_at(face.center())
        if abs(abs(normal.Z) - 1.0) < _PLANAR_TOL:
            levels.append(face.center().Z)
    unique = sorted({round(z, 6) for z in levels})
    if len(unique) < 2:
        return None
    return min(b - a for a, b in zip(unique, unique[1:], strict=False))


def find_thin_features(
    shape: Shape[Any], *, min_feature: float = DEFAULT_MIN_FEATURE
) -> list[Finding]:
    """Return a finding when the smallest vertical feature caps the layer height."""
    feature = min_vertical_feature(shape)
    if feature is None or feature >= min_feature:
        return []
    return [
        Finding(
            kind="min_feature",
            severity=Severity.WARNING,
            message=(
                f"Smallest vertical feature {feature:.2f} mm caps the layer height "
                f"(use <= {feature:.2f} mm)"
            ),
        )
    ]
