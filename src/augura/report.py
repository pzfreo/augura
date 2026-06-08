"""The printability report — augura's deterministic, explainable output.

A ``Report`` is a flat, serialisable bag of ``Finding`` objects. Each finding
carries a kind, a severity, a human-readable message, and (where meaningful) a
magnitude and a location, so every conclusion is explainable rather than an
opaque score.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


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

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable view of the report."""
        return {
            "findings": [
                {
                    "kind": f.kind,
                    "severity": f.severity.value,
                    "message": f.message,
                    "area": f.area,
                    "location": list(f.location) if f.location is not None else None,
                }
                for f in self.findings
            ]
        }

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

    @property
    def tip_over(self) -> tuple[Finding, ...]:
        """Findings flagging that the part is statically unstable (will topple)."""
        return self.of_kind("tip_over")

    @property
    def brim(self) -> tuple[Finding, ...]:
        """Findings recommending a brim/raft (lift/peel risk)."""
        return self.of_kind("brim")

    @property
    def min_feature(self) -> tuple[Finding, ...]:
        """Findings flagging a thin vertical feature that caps the layer height."""
        return self.of_kind("min_feature")

    @property
    def thin_walls(self) -> tuple[Finding, ...]:
        """Findings flagging walls too thin to print at the given nozzle."""
        return self.of_kind("thin_wall")
