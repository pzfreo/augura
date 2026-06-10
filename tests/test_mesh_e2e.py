"""End-to-end mesh-fallback tests.

Meshes are generated in-test by tessellating build123d solids (no binary blobs).
"""

from __future__ import annotations

from typing import Any

import pytest
from build123d import Box, Pos

from augura import analyze
from tests.fixtures import TIPPING_MAST

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


def test_empty_mesh_yields_empty_report() -> None:
    # A failed/empty STL load (no faces) must not crash; it has nothing to report.
    assert analyze(trimesh.Trimesh()).findings == ()


def test_native_trimesh_box_has_no_overhangs() -> None:
    # A box from a non-build123d source (outward-wound normals): its bottom is
    # bed-contact, its top points up, its sides are vertical -> no overhangs.
    box = trimesh.creation.box(extents=(20, 20, 10))
    assert analyze(box).overhangs == ()


def test_sphere_mesh_flags_only_shallow_overhangs() -> None:
    # A sphere's lower hemisphere spans every angle: shallow downward faces are
    # flagged, steep (self-supporting) ones are not -- so an overhang is reported
    # but it does not cover the whole lower half.
    sphere = trimesh.creation.icosphere(radius=10)
    overhangs = analyze(sphere).overhangs
    assert overhangs
    assert all("approximate" in f.message for f in overhangs)


# --- bed-fit ----------------------------------------------------------------


def test_mesh_bed_fit_fits() -> None:
    report = analyze(_mesh(Box(20, 20, 10)), build_volume=(100, 100, 100))
    assert report.bed_fit == ()


def test_mesh_bed_fit_overflows() -> None:
    report = analyze(_mesh(Box(200, 20, 10)), build_volume=(100, 100, 100))
    (finding,) = report.bed_fit
    assert "approximate" in finding.message
    assert "X" in finding.message


# --- tip-over ---------------------------------------------------------------


def test_mesh_tip_over_stable_box() -> None:
    assert analyze(_mesh(Box(20, 20, 10))).tip_over == ()


def test_mesh_tip_over_unstable() -> None:
    (finding,) = analyze(_mesh(TIPPING_MAST.build())).tip_over
    assert "approximate" in finding.message
    assert "topple" in finding.message


# --- brim risk --------------------------------------------------------------


def test_mesh_brim_risk_wide_box_no_risk() -> None:
    assert analyze(_mesh(Box(100, 100, 5))).brim == ()


def test_mesh_brim_risk_small_footprint() -> None:
    # 5x5 mm base, 80 mm tall — tiny footprint + high aspect
    tall_pin = Pos(0, 0, 40) * Box(5, 5, 80)
    findings = analyze(_mesh(tall_pin)).brim
    assert findings
    assert all("approximate" in f.message for f in findings)
