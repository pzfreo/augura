"""End-to-end minimum-feature / layer-height-bound tests."""

from __future__ import annotations

import pytest
from build123d import Box, Compound, Pos, Sphere

from augura import analyze, min_vertical_feature
from tests.fixtures import FLAT_PLATE, THIN_LAMINA_BLOCK


def test_thin_lamina_caps_layer_height() -> None:
    part = THIN_LAMINA_BLOCK.build()

    assert min_vertical_feature(part) == pytest.approx(0.2, abs=1e-3)
    (finding,) = analyze(part).min_feature
    assert "0.2" in finding.message and "layer height" in finding.message


def test_coplanar_faces_merge_to_one_level() -> None:
    # Two side-by-side boxes share top and bottom planes; the duplicate levels
    # merge, leaving a single 10 mm step (not a spurious sub-resolution feature).
    pair = Compound(children=[Box(10, 10, 10), Pos(20, 0, 0) * Box(10, 10, 10)])
    assert min_vertical_feature(pair) == pytest.approx(10.0)


def test_flat_plate_feature_above_threshold() -> None:
    plate = FLAT_PLATE.build()
    assert min_vertical_feature(plate) == pytest.approx(5.0)
    assert analyze(plate).min_feature == ()


def test_no_horizontal_faces_abstains() -> None:
    sphere = Sphere(radius=5)
    assert min_vertical_feature(sphere) is None
    assert analyze(sphere).min_feature == ()
