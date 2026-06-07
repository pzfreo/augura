"""Top-level analysis entry point.

``analyze`` is the public façade end-to-end tests drive. It composes the
individual geometry checks into a single :class:`~augura.report.Report`. Today it
runs overhang detection; new checks are added here as they are built.
"""

from __future__ import annotations

from typing import Any

from build123d import Shape

from augura.overhangs import DEFAULT_SUPPORT_ANGLE, find_overhangs
from augura.report import Report


def analyze(shape: Shape[Any], *, support_angle: float = DEFAULT_SUPPORT_ANGLE) -> Report:
    """Analyse a solid and return its printability report.

    Args:
        shape: The part to analyse, oriented for printing (+Z up, resting on
            the build plate at its minimum Z).
        support_angle: Faces shallower than this many degrees from horizontal
            are flagged as overhangs.
    """
    findings = find_overhangs(shape, support_angle=support_angle)
    return Report(findings=tuple(findings))
