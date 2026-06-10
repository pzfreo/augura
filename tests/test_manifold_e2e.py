"""End-to-end manifold/watertight tests.

Positive case from the SOLID_CUBE fixture; the negative cases are built inline
(open shell, and a deliberately malformed solid wrapping an open shell — the
kind of input a bad STEP import produces).
"""

from __future__ import annotations

from build123d import Box, Cone, Cylinder, Shell, Solid, Sphere
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeSolid
from OCP.TopoDS import TopoDS

from augura import Severity, analyze, find_manifold_issues, is_watertight
from tests.fixtures import SOLID_CUBE


def test_solid_cube_is_watertight() -> None:
    cube = SOLID_CUBE.build()
    assert is_watertight(cube) is True
    assert analyze(cube).manifold_issues == ()


def test_primitives_with_degenerated_or_seam_edges_are_watertight() -> None:
    """Sphere/cone (degenerated edges) and cylinder (seam edge) are valid
    closed solids — regression for build123d's is_manifold flagging them."""
    assert is_watertight(Sphere(10)) is True
    assert is_watertight(Cone(10, 0, 15)) is True
    assert is_watertight(Cylinder(5, 10)) is True


def test_shell_without_solid_gets_no_solid_finding() -> None:
    """Shells (even closed ones) carry no solid body: the pipeline needs mass
    properties, so they are unanalysable — and the finding must say that
    rather than claim the geometry is non-manifold."""
    for shell in (
        Shell(Box(20, 20, 20).faces()),  # closed
        Shell(Box(20, 20, 20).faces()[:-1]),  # one face removed -> open
    ):
        assert is_watertight(shell) is False
        issues = find_manifold_issues(shell)
        assert len(issues) == 1
        assert issues[0].severity is Severity.ERROR
        assert "no solid body" in issues[0].message


def test_open_solid_is_flagged_not_watertight() -> None:
    open_shell = Shell(Box(20, 20, 20).faces()[:-1])
    # OCCT happily builds a Solid around an open shell without validating
    # closure — exactly what a malformed STEP import yields.
    bad_solid = Solid(BRepBuilderAPI_MakeSolid(TopoDS.Shell_s(open_shell.wrapped)).Solid())

    assert is_watertight(bad_solid) is False
    issues = find_manifold_issues(bad_solid)
    assert len(issues) == 1
    assert issues[0].severity is Severity.ERROR
    assert "not watertight" in issues[0].message
