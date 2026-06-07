"""augura — BREP-exact 3D-printability analysis and print-advice.

Public surface. End-to-end tests are written against these names; grow the
package fixture-by-fixture behind this façade.
"""

from __future__ import annotations

from augura.analyze import analyze
from augura.bed_fit import find_bed_fit
from augura.brim import find_brim_risk
from augura.manifold import find_manifold_issues, is_watertight
from augura.min_feature import find_thin_features, min_vertical_feature
from augura.orientation import OrientationScore, orientation_scores
from augura.overhangs import DEFAULT_SUPPORT_ANGLE, find_overhangs
from augura.report import Finding, Report, Severity
from augura.tip_over import find_tip_over

__all__ = [
    "DEFAULT_SUPPORT_ANGLE",
    "Finding",
    "OrientationScore",
    "Report",
    "Severity",
    "analyze",
    "find_bed_fit",
    "find_brim_risk",
    "find_manifold_issues",
    "find_overhangs",
    "find_thin_features",
    "find_tip_over",
    "is_watertight",
    "min_vertical_feature",
    "orientation_scores",
]
