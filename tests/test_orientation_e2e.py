"""End-to-end orientation-search tests, driven from the angle_bracket fixture."""

from __future__ import annotations

from augura import orientation_scores
from tests.fixtures import ANGLE_BRACKET


def test_flat_pose_minimises_overhang() -> None:
    scores = orientation_scores(ANGLE_BRACKET.build())

    # The best (first) pose needs no support...
    assert scores[0].overhang_area == 0.0
    # ...and the as-modelled flat pose (0, 0, 0) is among those support-free best.
    assert any(s.rotation == (0, 0, 0) and s.overhang_area == 0.0 for s in scores)
    # Orientation matters: at least one stand-on-end pose needs support.
    assert max(s.overhang_area for s in scores) > 0.0
    # Returned ranked best-first.
    assert scores == sorted(scores, key=lambda s: s.overhang_area)


def test_candidates_override_is_respected() -> None:
    scores = orientation_scores(ANGLE_BRACKET.build(), candidates=[(0, 0, 0)])
    assert len(scores) == 1
    assert scores[0].overhang_area == 0.0
