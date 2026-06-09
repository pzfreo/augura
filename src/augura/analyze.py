"""Top-level analysis entry point.

``analyze`` is the public façade end-to-end tests drive. It composes the
individual geometry checks into a single :class:`~augura.report.Report`. Today it
runs overhang detection; new checks are added here as they are built.
"""

from __future__ import annotations

from typing import Any

from build123d import Shape

from augura.bed_fit import find_bed_fit
from augura.brim import find_brim_risk
from augura.footprint import BED_TOL
from augura.manifold import find_manifold_issues
from augura.mesh import analyze_mesh, is_mesh
from augura.min_feature import DEFAULT_MIN_FEATURE, find_thin_features
from augura.overhangs import DEFAULT_SUPPORT_ANGLE, find_overhangs
from augura.report import Report
from augura.tip_over import find_tip_over
from augura.wall_thickness import DEFAULT_MIN_PERIMETERS, DEFAULT_NOZZLE, find_thin_walls


def analyze(
    shape: Shape[Any],
    *,
    support_angle: float = DEFAULT_SUPPORT_ANGLE,
    build_volume: tuple[float, float, float] | None = None,
    nozzle: float = DEFAULT_NOZZLE,
    min_perimeters: int = DEFAULT_MIN_PERIMETERS,
    bed_tol: float = BED_TOL,
    min_feature: float = DEFAULT_MIN_FEATURE,
) -> Report:
    """Analyse a solid and return its printability report.

    Overhang, manifold, tip-over, brim, minimum-feature, and wall-thickness
    checks always run; the bed-fit check runs only when ``build_volume`` is
    supplied.

    Args:
        shape: The part to analyse, oriented for printing (+Z up, resting on
            the build plate at its minimum Z).
        support_angle: Faces shallower than this many degrees from horizontal
            are flagged as overhangs.
        build_volume: Optional usable build volume ``(x, y, z)`` in mm; when
            given, the part is checked against it for bed-fit.
        nozzle: Nozzle diameter (mm) for the wall-thickness check.
        min_perimeters: Walls thinner than ``min_perimeters * nozzle`` are flagged.
        bed_tol: Z-distance tolerance (mm) for identifying bed-contact faces.
            Increase for noisy STEP imports where the lowest face is not exactly
            at the part's bounding-box minimum.
        min_feature: Smallest vertical feature (mm) to flag as capping the layer
            height. Features at or above this threshold are not reported. Has no
            effect on mesh (STL) inputs — the mesh path has no thin-feature check.

    A tessellated mesh (trimesh) is accepted too and routed to the degraded,
    approximate mesh path; the exact BREP path is used for build123d shapes.
    """
    if is_mesh(shape):
        return analyze_mesh(shape, support_angle=support_angle, build_volume=build_volume, bed_tol=bed_tol)
    findings = find_overhangs(shape, support_angle=support_angle, bed_tol=bed_tol)
    findings += find_manifold_issues(shape)
    findings += find_tip_over(shape, bed_tol=bed_tol)
    findings += find_brim_risk(shape, bed_tol=bed_tol)
    findings += find_thin_features(shape, min_feature=min_feature)
    findings += find_thin_walls(shape, nozzle=nozzle, min_perimeters=min_perimeters)
    if build_volume is not None:
        findings += find_bed_fit(shape, build_volume)
    return Report(findings=tuple(findings))
