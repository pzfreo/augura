"""Mesh (STL) fallback input path.

The analytic BREP path is primary; when only a tessellated mesh is available
(e.g. an STL from a non-build123d source) augura runs a degraded, explicitly
*approximate* version of the checks via trimesh (a core dependency).

This fallback covers: overhang, manifold, tip-over, brim-risk, and (when a
build volume is supplied) bed-fit. The exact BREP path is still preferred;
mesh results are clearly marked with ``[mesh, approximate]``.
"""

from __future__ import annotations

import math
from typing import Any

from augura.brim import DEFAULT_MAX_ASPECT, DEFAULT_MIN_FOOTPRINT_AREA
from augura.overhangs import DEFAULT_SUPPORT_ANGLE
from augura.report import Finding, Report, Severity
from augura.tip_over import _convex_hull, _inside_hull

_DOWNWARD_TOL = 1e-6
_BED_TOL = 1e-3
_FIT_TOL = 1e-6
_ANGLE_TOL = 1e-3
_BED_NORMAL_TOL = 0.99
# Every mesh-path finding carries this marker — results are approximate.
_MESH_NOTE = "[mesh, approximate] "


def is_mesh(obj: Any) -> bool:
    """Whether ``obj`` is a trimesh mesh (duck-typed, no hard trimesh import)."""
    return type(obj).__module__.split(".")[0] == "trimesh"


def find_overhangs_mesh(
    mesh: Any, *, support_angle: float = DEFAULT_SUPPORT_ANGLE, bed_tol: float = _BED_TOL
) -> list[Finding]:
    """Approximate total overhang area from a mesh's downward triangles."""
    z_min = float(mesh.bounds[0][2])
    total = 0.0
    for index, normal in enumerate(mesh.face_normals):
        nz = float(normal[2])
        if nz >= -_DOWNWARD_TOL:
            continue
        tri_min_z = float(mesh.triangles[index][:, 2].min())
        if abs(tri_min_z - z_min) < bed_tol and nz < -_BED_NORMAL_TOL:
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


def find_bed_fit_mesh(mesh: Any, build_volume: tuple[float, float, float]) -> list[Finding]:
    """Flag if the mesh bounding-box extents overflow the build volume."""
    extents = mesh.bounds[1] - mesh.bounds[0]  # numpy [dx, dy, dz]
    over = [
        axis
        for axis, extent, limit in zip("XYZ", extents, build_volume, strict=True)
        if float(extent) > limit + _FIT_TOL
    ]
    if not over:
        return []
    dx, dy, dz = float(extents[0]), float(extents[1]), float(extents[2])
    msg = (
        f"{_MESH_NOTE}Part {dx:.1f}x{dy:.1f}x{dz:.1f} mm exceeds the "
        f"{build_volume[0]:.0f}x{build_volume[1]:.0f}x{build_volume[2]:.0f} mm "
        f"build volume on {', '.join(over)}"
    )
    return [Finding(kind="bed_fit", severity=Severity.ERROR, message=msg)]


def _bed_contact_tri_indices(mesh: Any, bed_tol: float = _BED_TOL) -> list[int]:
    """Indices of triangles whose vertices all lie within bed_tol of the mesh's lowest Z."""
    z_min = float(mesh.bounds[0][2])
    return [
        i
        for i, tri in enumerate(mesh.triangles)
        if all(abs(float(v[2]) - z_min) < bed_tol for v in tri)
    ]


def find_tip_over_mesh(
    mesh: Any, *, bed_indices: list[int] | None = None, bed_tol: float = _BED_TOL
) -> list[Finding]:
    """Flag instability: COM projects outside the XY convex hull of bed vertices."""
    _bed = bed_indices if bed_indices is not None else _bed_contact_tri_indices(mesh, bed_tol)
    points: list[tuple[float, float]] = [
        (float(v[0]), float(v[1])) for i in _bed for v in mesh.triangles[i]
    ]
    hull = _convex_hull(points)
    if len(hull) < 3:
        return []
    com = mesh.center_mass
    cx, cy = float(com[0]), float(com[1])
    if _inside_hull((cx, cy), hull):
        return []
    return [
        Finding(
            kind="tip_over",
            severity=Severity.ERROR,
            message=(
                f"{_MESH_NOTE}Centre of mass ({cx:.1f}, {cy:.1f}) projects outside "
                "the bed-contact footprint; the part will topple"
            ),
        )
    ]


def find_brim_risk_mesh(
    mesh: Any,
    *,
    min_footprint_area: float = DEFAULT_MIN_FOOTPRINT_AREA,
    max_aspect: float = DEFAULT_MAX_ASPECT,
    bed_indices: list[int] | None = None,
    bed_tol: float = _BED_TOL,
) -> list[Finding]:
    """Recommend a brim when the mesh footprint is small or aspect ratio is high."""
    _bed = bed_indices if bed_indices is not None else _bed_contact_tri_indices(mesh, bed_tol)
    height = float(mesh.bounds[1][2]) - float(mesh.bounds[0][2])
    footprint = sum(float(mesh.area_faces[i]) for i in _bed)
    if footprint <= 0.0:
        return []
    aspect = height / math.sqrt(footprint)
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
            message=f"{_MESH_NOTE}Recommend a brim: " + " and ".join(reasons),
        )
    ]


def analyze_mesh(
    mesh: Any,
    *,
    support_angle: float = DEFAULT_SUPPORT_ANGLE,
    build_volume: tuple[float, float, float] | None = None,
    bed_tol: float = _BED_TOL,
) -> Report:
    """Degraded, approximate analysis of a tessellated mesh."""
    if mesh.bounds is None:  # empty / degenerate mesh: nothing to analyse
        return Report()
    bed = _bed_contact_tri_indices(mesh, bed_tol)
    findings = find_overhangs_mesh(mesh, support_angle=support_angle, bed_tol=bed_tol)
    findings += find_manifold_issues_mesh(mesh)
    findings += find_tip_over_mesh(mesh, bed_indices=bed, bed_tol=bed_tol)
    findings += find_brim_risk_mesh(mesh, bed_indices=bed, bed_tol=bed_tol)
    if build_volume is not None:
        findings += find_bed_fit_mesh(mesh, build_volume)
    return Report(findings=tuple(findings))
