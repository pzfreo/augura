"""Mesh (STL) fallback input path.

The analytic BREP path is primary; when only a tessellated mesh is available
(e.g. an STL from a non-build123d source) augura runs a degraded, explicitly
*approximate* version of the checks via trimesh (a core dependency).

Today this fallback covers the per-triangle overhang estimate and the
watertight/manifold check (which finally unlocks the non-manifold negative case
the exact BREP path cannot represent). Other checks remain BREP-only for now.
"""

from __future__ import annotations

import math
from typing import Any

from augura.overhangs import DEFAULT_SUPPORT_ANGLE
from augura.report import Finding, Report, Severity

_DOWNWARD_TOL = 1e-6
_BED_TOL = 1e-3
_ANGLE_TOL = 1e-3
_BED_NORMAL_TOL = 0.99
# Every mesh-path finding carries this marker — results are approximate.
_MESH_NOTE = "[mesh, approximate] "


def is_mesh(obj: Any) -> bool:
    """Whether ``obj`` is a trimesh mesh (duck-typed, no hard trimesh import)."""
    return type(obj).__module__.split(".")[0] == "trimesh"


def find_overhangs_mesh(
    mesh: Any, *, support_angle: float = DEFAULT_SUPPORT_ANGLE
) -> list[Finding]:
    """Approximate total overhang area from a mesh's downward triangles."""
    z_min = float(mesh.bounds[0][2])
    total = 0.0
    for index, normal in enumerate(mesh.face_normals):
        nz = float(normal[2])
        if nz >= -_DOWNWARD_TOL:
            continue
        tri_min_z = float(mesh.triangles[index][:, 2].min())
        if abs(tri_min_z - z_min) < _BED_TOL and nz < -_BED_NORMAL_TOL:
            continue  # bed contact
        beta = math.degrees(math.acos(min(1.0, -nz)))
        if beta < support_angle - _ANGLE_TOL:
            total += float(mesh.area_faces[index])
    if total <= 0.0:
        return []
    return [
        Finding(
            kind="overhang",
            severity=Severity.WARNING,
            message=f"{_MESH_NOTE}~{total:.0f} mm2 of downward faces need support",
            area=total,
        )
    ]


def find_manifold_issues_mesh(mesh: Any) -> list[Finding]:
    """Flag a mesh that is not watertight (the non-manifold negative case)."""
    if mesh.is_watertight:
        return []
    return [
        Finding(
            kind="not_manifold",
            severity=Severity.ERROR,
            message=f"{_MESH_NOTE}mesh is not watertight (open or non-manifold)",
        )
    ]


def analyze_mesh(mesh: Any, *, support_angle: float = DEFAULT_SUPPORT_ANGLE) -> Report:
    """Degraded, approximate analysis of a tessellated mesh."""
    if mesh.bounds is None:  # empty / degenerate mesh: nothing to analyse
        return Report()
    findings = find_overhangs_mesh(mesh, support_angle=support_angle)
    findings += find_manifold_issues_mesh(mesh)
    return Report(findings=tuple(findings))
