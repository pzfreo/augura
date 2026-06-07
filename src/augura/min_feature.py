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
# Face planes closer than this (mm) are treated as one level: sub-resolution
# numerical noise (boolean artefacts, parametric round-off) is not a real step.
_LEVEL_TOL = 1e-3
# Below this smallest-feature size, flag the layer-height bound (tunable).
DEFAULT_MIN_FEATURE = 0.5


def _distinct_levels(values: list[float]) -> list[float]:
    """Sorted Z-levels with planes within ``_LEVEL_TOL`` merged into one."""
    reps: list[float] = []
    for z in sorted(values):
        if not reps or z - reps[-1] > _LEVEL_TOL:
            reps.append(z)
    return reps


def min_vertical_feature(shape: Shape[Any]) -> float | None:
    """Return the smallest gap between horizontal face planes, or None.

    None when the shape has fewer than two distinct horizontal face levels (no
    measurable vertical step). Planes within ``_LEVEL_TOL`` mm are merged, so
    sub-resolution numerical noise is never reported as a feature.
    """
    levels = [
        face.center().Z
        for face in shape.faces()
        if abs(abs(face.normal_at(face.center()).Z) - 1.0) < _PLANAR_TOL
    ]
    reps = _distinct_levels(levels)
    if len(reps) < 2:
        return None
    return min(b - a for a, b in zip(reps, reps[1:], strict=False))


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
                f"Smallest vertical feature {feature:.3g} mm caps the layer height "
                f"(use <= {feature:.3g} mm)"
            ),
        )
    ]
