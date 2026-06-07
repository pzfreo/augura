"""End-to-end manifold/watertight tests.

Positive case from the SOLID_CUBE fixture; the negative case is built inline as
an open shell (no repo binary blob, no build123d-impossible non-manifold solid).
"""

from __future__ import annotations

from build123d import Box, Shell

from augura import Severity, analyze, find_manifold_issues, is_watertight
from tests.fixtures import SOLID_CUBE


def test_solid_cube_is_watertight() -> None:
    cube = SOLID_CUBE.build()
    assert is_watertight(cube) is True
    assert analyze(cube).manifold_issues == ()


def test_open_shell_is_flagged_not_watertight() -> None:
    open_shell = Shell(Box(20, 20, 20).faces()[:-1])  # one face removed -> open

    assert is_watertight(open_shell) is False
    issues = find_manifold_issues(open_shell)
    assert len(issues) == 1
    assert issues[0].severity is Severity.ERROR
