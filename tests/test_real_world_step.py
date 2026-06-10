"""Regression smoke tests against real-world STEP files.

The parametric fixtures in ``tests/fixtures`` are clean, single-body solids we
built ourselves. These tests run the full STEP -> analyze pipeline on
production CAD instead: the Framework Expansion Card printable parts, which
are multi-body assemblies written by a commercial CAD package (see
``tests/data/real_world/ATTRIBUTION.md`` for source and licence).

Assertions are at the finding-kind level — exact counts and areas would be
brittle against tolerance tuning. The point is: real files load, analyse
without crashing, and the expected capabilities fire.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from build123d import import_step

from augura import analyze

DATA = Path(__file__).parent / "data" / "real_world"

REAL_WORLD = [
    ("framework_expansion_card_selftapping.stp", 4),
    ("framework_expansion_card_threadedinsert.stp", 6),
    ("cubotino_baseplate_r_leg.stp", 1),
    ("cubotino_cover.stp", 1),
]


@pytest.mark.parametrize(("filename", "n_solids"), REAL_WORLD)
def test_real_world_step_analyses(filename: str, n_solids: int) -> None:
    shape = import_step(DATA / filename)
    assert len(shape.solids()) == n_solids

    report = analyze(shape)

    kinds = {f.kind for f in report.findings}
    # As-imported (CAD orientation) these parts have unsupported faces.
    assert "overhang" in kinds
    # All four parts are valid closed solids; degenerated edges (cone apexes,
    # sphere poles) must not be reported as non-manifold.
    assert "not_manifold" not in kinds
    # Every finding must be explainable: it carries a human-readable message.
    for finding in report.findings:
        assert finding.message
