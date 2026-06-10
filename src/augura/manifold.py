"""Manifold / watertight check.

Reports whether a shape is a closed, manifold solid (every shell of every
solid closed). For exact BREP solids this is watertight-by-construction, so
it earns its keep mainly on imported geometry (STEP from other CAD packages,
see also the mesh fallback), which can be open or non-manifold.

build123d's ``Shape.is_manifold`` is not used: it counts degenerated edges
(zero-length edges at cone apexes and sphere poles) as non-manifold, so
``Sphere(1).is_manifold`` is ``False`` — flagging plain ``Sphere``/``Cone``
solids, and most imported real-world parts, as unprintable (no upstream
build123d issue as of 2026-06). Instead each shell is checked with OCCT's
own ``BRepCheck_Shell`` closed-status, which is orientation-aware and
handles degenerated and seam edges correctly.

Only solids are analysable: a shape with no solids (surface-only STEP, bare
faces or wires) gets its own finding rather than "non-manifold", since the
rest of the pipeline (mass properties, tip-over) requires a solid body.
"""

from __future__ import annotations

from typing import Any

from build123d import Shape
from OCP.BRepCheck import BRepCheck_Shell, BRepCheck_Status

from augura.report import Finding, Severity


def _solid_is_watertight(solid: Shape[Any]) -> bool:
    shells = solid.shells()
    if not shells:
        return False
    return all(
        BRepCheck_Shell(shell.wrapped).Closed(True) == BRepCheck_Status.BRepCheck_NoError
        for shell in shells
    )


def is_watertight(shape: Shape[Any]) -> bool:
    """Return whether the shape is a closed, manifold (watertight) solid.

    Solids only: a shape containing no solids returns ``False``. For a
    multi-body compound, every solid must be watertight.
    """
    solids = shape.solids()
    if not solids:
        return False
    return all(_solid_is_watertight(solid) for solid in solids)


def find_manifold_issues(shape: Shape[Any]) -> list[Finding]:
    """Return a finding if the shape is not a closed, manifold solid."""
    if not shape.solids():
        return [
            Finding(
                kind="not_manifold",
                severity=Severity.ERROR,
                message=(
                    "Shape contains no solid body (surface or wire geometry"
                    " only) and cannot be analysed for printing"
                ),
            )
        ]
    if is_watertight(shape):
        return []
    return [
        Finding(
            kind="not_manifold",
            severity=Severity.ERROR,
            message="Shape is not watertight (open or non-manifold) and cannot be printed",
        )
    ]
