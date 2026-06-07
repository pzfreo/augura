"""The printability report — augura's deterministic, explainable output.

A ``Report`` is a flat, serialisable bag of ``Finding`` objects. Each finding
carries a kind, a severity, a human-readable message, and (where meaningful) a
magnitude and a location, so every conclusion is explainable rather than an
opaque score.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Severity(StrEnum):
    """How much a finding should worry the maker."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class Finding:
    """A single, explainable observation about a part's printability."""

    kind: str
    severity: Severity
    message: str
    area: float | None = None
    location: tuple[float, float, float] | None = None


@dataclass(frozen=True)
class Report:
    """The result of analysing a part: an ordered collection of findings."""

    findings: tuple[Finding, ...] = ()

    def of_kind(self, kind: str) -> tuple[Finding, ...]:
        """Return every finding of the given ``kind``, preserving order."""
        return tuple(f for f in self.findings if f.kind == kind)

    @property
    def overhangs(self) -> tuple[Finding, ...]:
        """Findings flagging downward faces that will need support."""
        return self.of_kind("overhang")

    @property
    def bed_fit(self) -> tuple[Finding, ...]:
        """Findings flagging that the part overflows the build volume."""
        return self.of_kind("bed_fit")

    @property
    def manifold_issues(self) -> tuple[Finding, ...]:
        """Findings flagging that the shape is not watertight/manifold."""
        return self.of_kind("not_manifold")
