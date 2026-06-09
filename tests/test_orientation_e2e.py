"""End-to-end orientation-search tests, driven from the angle_bracket fixture."""

from __future__ import annotations

import pytest
from build123d import Box

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


def test_tie_breaking_by_z_height_and_bed_contact() -> None:
    # Box(80, 20, 10): all six axis-aligned orientations have zero overhangs,
    # so ranking is decided entirely by tie-breakers.
    scores = orientation_scores(Box(80, 20, 10))

    assert all(s.overhang_area == 0.0 for s in scores), "symmetric box should have no overhangs"
    assert scores == sorted(scores, key=lambda s: (s.overhang_area, s.z_height, -s.bed_contact_area))

    # The flattest orientation (z_height=10) must rank above taller ones.
    assert scores[0].z_height == pytest.approx(10.0, abs=0.01)
    # All scores carry the new fields.
    assert all(s.z_height > 0.0 for s in scores)
    assert all(s.bed_contact_area > 0.0 for s in scores)
