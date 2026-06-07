"""Reusable, parametric part fixtures with declared printability expectations.

Each fixture builds an *exact* build123d solid in code — no binary blobs, so the
geometry is reproducible and diffable — and declares which planned capability it
exercises and what augura should conclude about it. End-to-end tests drive the
codebase from these expectations: to implement a capability, make its fixture's
declared ``expects`` outcome pass.

Capabilities still to be built each have a tracking issue; the ``capability``
slug below matches the issue. Until a capability exists, its fixtures are still
exercised by ``test_fixtures_build`` (they must build to a valid solid) — only
the capability-specific assertion waits for the implementation.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

from build123d import Axis, Box, Cylinder, Pos, Shape, chamfer


@dataclass(frozen=True)
class PartFixture:
    """A named part builder plus the printability outcome augura should report.

    ``expects`` is deliberately free-form prose, not a typed schema: each
    capability's exact return shape is designed when that capability is built,
    not pre-frozen here.
    """

    name: str
    build: Callable[[], Shape[Any]]
    capability: str
    expects: str
    notes: str = ""


# --------------------------------------------------------------------------- #
# overhang detection  (implemented)
# --------------------------------------------------------------------------- #
def _cantilever_bracket() -> Shape[Any]:
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


def _flat_plate() -> Shape[Any]:
    """A simple plate resting flat on the bed — nothing needs support."""
    return Pos(0, 0, 2.5) * Box(40, 40, 5)


# --------------------------------------------------------------------------- #
# orientation search
# --------------------------------------------------------------------------- #
def _angle_bracket() -> Shape[Any]:
    """An L of two thick plates: one flat on the bed, one standing vertical.

    Orientation-sensitive: as modelled the upright leg's geometry differs in
    support cost from a pose that lays both legs in-plane.
    """
    base = Pos(0, 0, 2.5) * Box(60, 30, 5)
    leg = Pos(-27.5, 0, 25) * Box(5, 30, 40)
    return cast(Shape[Any], base + leg)


# --------------------------------------------------------------------------- #
# bed-fit
# --------------------------------------------------------------------------- #
def _oversized_plate() -> Shape[Any]:
    """A 350 mm plate — larger than a typical 256 mm bed in X and Y."""
    return Pos(0, 0, 2.5) * Box(350, 350, 5)


# --------------------------------------------------------------------------- #
# tip-over / stability
# --------------------------------------------------------------------------- #
def _tipping_mast() -> Shape[Any]:
    """A small foot with a tall mast cantilevered far to one side.

    The combined centre of mass projects well outside the foot's footprint, so
    the part is statically unstable and will topple without support/bracing.
    """
    foot = Pos(0, 0, 2) * Box(20, 20, 4)
    mast = Pos(40, 0, 54) * Box(10, 10, 100)
    return cast(Shape[Any], foot + mast)


# --------------------------------------------------------------------------- #
# minimum feature / layer-height bound
# --------------------------------------------------------------------------- #
def _thin_lamina_block() -> Shape[Any]:
    """A solid block topped by a deliberately thin 0.2 mm horizontal slab.

    The 0.2 mm vertical extent is the smallest feature and bounds the usable
    layer height.
    """
    base = Pos(0, 0, 5) * Box(40, 40, 10)
    lamina = Pos(0, 0, 10.1) * Box(20, 20, 0.2)
    return cast(Shape[Any], base + lamina)


# --------------------------------------------------------------------------- #
# wall thickness
# --------------------------------------------------------------------------- #
def _thin_wall_tube() -> Shape[Any]:
    """A tube with a 0.3 mm wall — thinner than two 0.4 mm nozzle widths."""
    outer = Cylinder(radius=10, height=20)
    inner = Cylinder(radius=9.7, height=20)
    return outer - inner


# --------------------------------------------------------------------------- #
# manifold / watertight
# --------------------------------------------------------------------------- #
def _solid_cube() -> Shape[Any]:
    """A trivially watertight solid (positive case).

    A non-manifold negative case cannot be built as a build123d BREP solid — it
    requires the STL/mesh fallback path (see the manifold tracking issue).
    """
    return Box(20, 20, 20)


# --------------------------------------------------------------------------- #
# brim / raft risk
# --------------------------------------------------------------------------- #
def _tall_thin_pin() -> Shape[Any]:
    """A tall, slender pin: tiny bed-contact footprint relative to its height."""
    return Cylinder(radius=3, height=80)


# --------------------------------------------------------------------------- #
# strength under a declared load
# --------------------------------------------------------------------------- #
def _rect_beam() -> Shape[Any]:
    """A rectangular beam (80 x 20 x 10) for orientation-vs-strength comparison.

    Under a vertical (Z) tip load when cantilevered along X, section modulus and
    layer-line alignment both depend on which cross-section dimension is vertical
    and on the print orientation.
    """
    return Box(80, 20, 10)


CANTILEVER = PartFixture(
    name="cantilever_bracket",
    build=_cantilever_bracket,
    capability="overhang",
    expects="exactly 1 overhang (~250 mm2 arm underside); chamfer is borderline-45 deg "
    "(not flagged); column bottom is bed-contact (not flagged)",
)
FLAT_PLATE = PartFixture(
    name="flat_plate",
    build=_flat_plate,
    capability="overhang",
    expects="0 overhangs; the bottom face is bed-contact, not an overhang",
)
ANGLE_BRACKET = PartFixture(
    name="angle_bracket",
    build=_angle_bracket,
    capability="orientation_search",
    expects="orientation search ranks a both-legs-flat pose above the as-modelled upright "
    "pose by total unsupported overhang area",
)
OVERSIZED_PLATE = PartFixture(
    name="oversized_plate",
    build=_oversized_plate,
    capability="bed_fit",
    expects="fails bed-fit for a 256 x 256 x 256 mm build volume (exceeds X and Y)",
)
TIPPING_MAST = PartFixture(
    name="tipping_mast",
    build=_tipping_mast,
    capability="tip_over",
    expects="unstable: centre of mass projects outside the bed-contact footprint",
)
THIN_LAMINA_BLOCK = PartFixture(
    name="thin_lamina_block",
    build=_thin_lamina_block,
    capability="min_feature",
    expects="smallest vertical feature ~0.2 mm bounds the maximum usable layer height",
)
THIN_WALL_TUBE = PartFixture(
    name="thin_wall_tube",
    build=_thin_wall_tube,
    capability="wall_thickness",
    expects="0.3 mm wall flagged as too thin for a 0.4 mm nozzle (< 2 perimeters)",
)
SOLID_CUBE = PartFixture(
    name="solid_cube",
    build=_solid_cube,
    capability="manifold",
    expects="reported watertight/manifold (positive case)",
)
TALL_THIN_PIN = PartFixture(
    name="tall_thin_pin",
    build=_tall_thin_pin,
    capability="brim_raft",
    expects="small contact footprint + high aspect ratio -> recommend a brim",
)
RECT_BEAM = PartFixture(
    name="rect_beam",
    build=_rect_beam,
    capability="strength",
    expects="under a Z tip load, the higher-section-modulus orientation scores stronger; "
    "a flat print places weak layer-adhesion planes across the tensile face",
)

ALL: list[PartFixture] = [
    CANTILEVER,
    FLAT_PLATE,
    ANGLE_BRACKET,
    OVERSIZED_PLATE,
    TIPPING_MAST,
    THIN_LAMINA_BLOCK,
    THIN_WALL_TUBE,
    SOLID_CUBE,
    TALL_THIN_PIN,
    RECT_BEAM,
]
