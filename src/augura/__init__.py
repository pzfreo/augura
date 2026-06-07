"""augura — BREP-exact 3D-printability analysis and print-advice.

Public surface. End-to-end tests are written against these names; grow the
package fixture-by-fixture behind this façade.
"""

from __future__ import annotations

from augura.analyze import analyze
from augura.overhangs import DEFAULT_SUPPORT_ANGLE, find_overhangs
from augura.report import Finding, Report, Severity

__all__ = [
    "DEFAULT_SUPPORT_ANGLE",
    "Finding",
    "Report",
    "Severity",
    "analyze",
    "find_overhangs",
]
