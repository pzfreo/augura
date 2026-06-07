"""Manifold / watertight check.

Reports whether a shape is a closed, manifold solid (every edge shared by
exactly two faces). For exact BREP solids this is watertight-by-construction, so
it earns its keep mainly on imported mesh/STL geometry (see the mesh fallback),
which can be open or non-manifold.
"""

from __future__ import annotations

from typing import Any

from build123d import Shape

from augura.report import Finding, Severity


def is_watertight(shape: Shape[Any]) -> bool:
    """Return whether the shape is a closed, manifold (watertight) solid."""
    return bool(shape.is_manifold)


def find_manifold_issues(shape: Shape[Any]) -> list[Finding]:
    """Return a finding if the shape is not a closed, manifold solid."""
    if is_watertight(shape):
        return []
    return [
        Finding(
            kind="not_manifold",
            severity=Severity.ERROR,
            message="Shape is not watertight (open or non-manifold) and cannot be printed",
        )
    ]
