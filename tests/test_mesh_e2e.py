"""End-to-end mesh-fallback tests.

Meshes are generated in-test by tessellating build123d solids (no binary blobs).
"""

from __future__ import annotations

from typing import Any

import pytest
from build123d import Box, Pos

from augura import analyze

trimesh = pytest.importorskip("trimesh")


def _mesh(shape: Any, tolerance: float = 0.1) -> Any:
    verts, faces = shape.tessellate(tolerance)
    return trimesh.Trimesh(vertices=[(v.X, v.Y, v.Z) for v in verts], faces=faces)


def test_analyze_accepts_a_watertight_mesh() -> None:
    report = analyze(_mesh(Box(20, 20, 10)))
    # Closed box mesh: watertight and no overhangs.
    assert report.manifold_issues == ()
    assert report.overhangs == ()


def test_non_watertight_mesh_is_flagged() -> None:
    verts, faces = Box(20, 20, 10).tessellate(0.1)
    open_mesh = trimesh.Trimesh(vertices=[(v.X, v.Y, v.Z) for v in verts], faces=faces[:-1])

    (finding,) = analyze(open_mesh).manifold_issues
    assert "approximate" in finding.message


def test_mesh_overhang_is_reported_and_marked_approximate() -> None:
    cantilever = Pos(0, 0, 30) * Box(20, 10, 60) + Pos(25, 0, 55) * Box(30, 10, 10)

    overhangs = analyze(_mesh(cantilever)).overhangs
    assert overhangs
    assert all("approximate" in f.message for f in overhangs)
