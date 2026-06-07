"""Reusable, parametric part fixtures with declared printability expectations.

Each fixture builds an *exact* build123d solid in code — no binary blobs, so the
geometry is reproducible and diffable — and declares what augura should conclude
about it. End-to-end tests drive the codebase from these expectations: to add a
behaviour, add a fixture whose expectation fails, then implement until it passes.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from build123d import Axis, Box, Part, Pos, chamfer


@dataclass(frozen=True)
class PartFixture:
    """A named part builder plus the printability outcome augura should report."""

    name: str
    build: Callable[[], Part]
    expected_overhangs: int
    notes: str = ""


def _cantilever_bracket() -> Part:
    """A column on the bed with a horizontal arm cantilevered off the top.

    The arm's underside is a flat (0 deg) overhang; one bottom-outer edge is
    chamfered at exactly 45 deg (borderline — should NOT be flagged); the column
    bottom rests on the bed (bed contact — should NOT be flagged).
    """
    col = Pos(0, 0, 30) * Box(20, 10, 60)
    arm = Pos(25, 0, 55) * Box(30, 10, 10)
    part = col + arm
    edge = (
        part.edges()
        .filter_by(Axis.Y)
        .filter_by_position(Axis.Z, 49.9, 50.1)
        .filter_by_position(Axis.X, 39.9, 40.1)
    )
    return chamfer(edge, length=5)


def _flat_plate() -> Part:
    """A simple plate resting flat on the bed — nothing needs support."""
    return Pos(0, 0, 2.5) * Box(40, 40, 5)


CANTILEVER = PartFixture(
    name="cantilever_bracket",
    build=_cantilever_bracket,
    expected_overhangs=1,
    notes="arm underside (~250 mm2) is the only overhang; chamfer is borderline-45 deg; "
    "column bottom is bed-contact",
)

FLAT_PLATE = PartFixture(
    name="flat_plate",
    build=_flat_plate,
    expected_overhangs=0,
    notes="rests flat on the bed; its bottom face is bed-contact, not an overhang",
)

ALL: list[PartFixture] = [CANTILEVER, FLAT_PLATE]
