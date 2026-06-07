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
from augura.manifold import find_manifold_issues
from augura.min_feature import find_thin_features
from augura.overhangs import DEFAULT_SUPPORT_ANGLE, find_overhangs
from augura.report import Report
from augura.tip_over import find_tip_over


def analyze(
    shape: Shape[Any],
    *,
    support_angle: float = DEFAULT_SUPPORT_ANGLE,
    build_volume: tuple[float, float, float] | None = None,
) -> Report:
    """Analyse a solid and return its printability report.

    Overhang, manifold, tip-over, brim, and minimum-feature checks always run;
    the bed-fit check runs only when ``build_volume`` is supplied.

    Args:
        shape: The part to analyse, oriented for printing (+Z up, resting on
            the build plate at its minimum Z).
        support_angle: Faces shallower than this many degrees from horizontal
            are flagged as overhangs.
        build_volume: Optional usable build volume ``(x, y, z)`` in mm; when
            given, the part is checked against it for bed-fit.
    """
    findings = find_overhangs(shape, support_angle=support_angle)
    findings += find_manifold_issues(shape)
    findings += find_tip_over(shape)
    findings += find_brim_risk(shape)
    findings += find_thin_features(shape)
    if build_volume is not None:
        findings += find_bed_fit(shape, build_volume)
    return Report(findings=tuple(findings))
