"""Manifold / watertight check.

Reports whether a shape is a closed, manifold solid (every edge shared by
exactly two faces). For exact BREP solids this is watertight-by-construction, so
it earns its keep mainly on imported geometry (STEP from other CAD packages,
see also the mesh fallback), which can be open or non-manifold.

build123d's ``Shape.is_manifold`` is not used: it counts degenerated edges
(zero-length edges at cone apexes and sphere poles) as non-manifold, flagging
plain ``Sphere``/``Cone`` solids — and most imported real-world parts — as
unprintable. This check skips degenerated edges and counts face *uses*: the
ancestor map lists a face once per use of the edge, so a seam edge (one edge
bounding a closed face on both sides, e.g. a cylinder wall) naturally counts
as two.
"""

from __future__ import annotations

from typing import Any

from build123d import Shape
from OCP.BRep import BRep_Tool
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
from OCP.TopExp import TopExp
from OCP.TopoDS import TopoDS
from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape

from augura.report import Finding, Severity


def _solid_is_watertight(solid: Shape[Any]) -> bool:
    edge_faces = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(
        solid.wrapped, TopAbs_EDGE, TopAbs_FACE, edge_faces
    )
    for i in range(1, edge_faces.Extent() + 1):
        edge = TopoDS.Edge_s(edge_faces.FindKey(i))
        if BRep_Tool.Degenerated_s(edge):
            continue
        if edge_faces.FindFromIndex(i).Size() != 2:
            return False
    return True


def is_watertight(shape: Shape[Any]) -> bool:
    """Return whether the shape is a closed, manifold (watertight) solid.

    For a multi-body compound, every solid must be watertight.
    """
    solids = shape.solids()
    if not solids:
        return False
    return all(_solid_is_watertight(solid) for solid in solids)


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
