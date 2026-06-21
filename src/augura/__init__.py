"""augura — BREP-exact 3D-printability analysis and print-advice.

Public surface. End-to-end tests are written against these names; grow the
package fixture-by-fixture behind this façade.
"""

from __future__ import annotations

from augura.analyze import analyze
from augura.bed_fit import find_bed_fit
from augura.brim import find_brim_risk
from augura.cadquery_adapter import as_build123d, is_cadquery
from augura.estampo import to_estampo_toml
from augura.manifold import find_manifold_issues, is_watertight
from augura.mesh import analyze_mesh
from augura.min_feature import find_thin_features, min_vertical_feature
from augura.orientation import OrientationScore, apply_orientation, orientation_scores
from augura.overhangs import DEFAULT_MAX_BRIDGE, DEFAULT_SUPPORT_ANGLE, find_overhangs
from augura.report import Finding, Report, Severity
from augura.tip_over import find_tip_over
from augura.wall_thickness import find_thin_walls, min_wall_thickness

__all__ = [
    "DEFAULT_MAX_BRIDGE",
    "DEFAULT_SUPPORT_ANGLE",
    "Finding",
    "OrientationScore",
    "Report",
    "Severity",
    "analyze",
    "analyze_mesh",
    "apply_orientation",
    "as_build123d",
    "is_cadquery",
    "find_bed_fit",
    "find_brim_risk",
    "find_manifold_issues",
    "find_overhangs",
    "find_thin_features",
    "find_thin_walls",
    "find_tip_over",
    "is_watertight",
    "min_vertical_feature",
    "min_wall_thickness",
    "orientation_scores",
    "to_estampo_toml",
]
