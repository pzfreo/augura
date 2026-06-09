"""CadQuery adapter tests.

The full e2e test (requires cadquery installed) is skipped when CadQuery is
absent. The mock-based tests cover adapter logic with a real TopoDS_Shape
extracted from build123d — no CadQuery install required.
"""

from __future__ import annotations

from typing import Any

import pytest
from build123d import Box
from build123d import Shape as B3dShape

from augura import analyze, as_build123d, is_cadquery
from augura.cadquery_adapter import as_build123d as _as_build123d


# ---------------------------------------------------------------------------
# Helpers: mock CadQuery objects backed by a real OCCT/TopoDS_Shape
# ---------------------------------------------------------------------------

def _make_mock_cq_shape(topo_ds: Any) -> Any:
    """A cadquery.Shape-like object wrapping a real TopoDS_Shape."""

    class _MockCQShape:
        def __init__(self, wrapped: Any) -> None:
            self.wrapped = wrapped

    _MockCQShape.__module__ = "cadquery.occ_impl.shapes"
    return _MockCQShape(topo_ds)


def _make_mock_cq_workplane(topo_ds: Any, *, count: int = 1) -> Any:
    """A cadquery.Workplane-like object with *count* val(s)."""

    mock_shape = _make_mock_cq_shape(topo_ds)

    class _MockCQWorkplane:
        def val(self) -> Any:
            return mock_shape

        def vals(self) -> list[Any]:
            return [mock_shape] * count

    _MockCQWorkplane.__module__ = "cadquery"
    return _MockCQWorkplane()


# Build a real TopoDS_Shape via build123d for use across tests
_B3D_BOX = Box(10, 10, 5)
_TOPO_DS = _B3D_BOX.wrapped


# ---------------------------------------------------------------------------
# is_cadquery duck-type detection
# ---------------------------------------------------------------------------

def test_is_cadquery_false_for_b3d_shape() -> None:
    assert not is_cadquery(Box(10, 10, 5))


def test_is_cadquery_false_for_builtins() -> None:
    assert not is_cadquery(42)
    assert not is_cadquery({"a": 1})
    assert not is_cadquery(None)


def test_is_cadquery_true_for_mock_cq_shape() -> None:
    assert is_cadquery(_make_mock_cq_shape(_TOPO_DS))


def test_is_cadquery_true_for_mock_cq_workplane() -> None:
    assert is_cadquery(_make_mock_cq_workplane(_TOPO_DS))


# ---------------------------------------------------------------------------
# as_build123d conversion
# ---------------------------------------------------------------------------

def test_as_build123d_from_cq_shape() -> None:
    mock = _make_mock_cq_shape(_TOPO_DS)
    result = as_build123d(mock)
    assert isinstance(result, B3dShape)


def test_as_build123d_preserves_geometry() -> None:
    mock = _make_mock_cq_shape(_TOPO_DS)
    result = as_build123d(mock)
    bb = result.bounding_box()
    assert bb.size.X == pytest.approx(10.0, abs=1e-3)
    assert bb.size.Y == pytest.approx(10.0, abs=1e-3)
    assert bb.size.Z == pytest.approx(5.0, abs=1e-3)


def test_as_build123d_from_workplane_single() -> None:
    wp = _make_mock_cq_workplane(_TOPO_DS, count=1)
    result = as_build123d(wp)
    assert isinstance(result, B3dShape)


def test_as_build123d_from_workplane_multiple_raises() -> None:
    wp = _make_mock_cq_workplane(_TOPO_DS, count=3)
    with pytest.raises(ValueError, match="3 solids"):
        as_build123d(wp)


def test_as_build123d_from_workplane_empty_raises() -> None:
    class _EmptyWP:
        def vals(self) -> list[Any]:
            return []

    _EmptyWP.__module__ = "cadquery"
    with pytest.raises(ValueError, match="empty"):
        _as_build123d(_EmptyWP())


def test_as_build123d_bad_type_raises() -> None:
    class _NotWrapped:
        pass

    _NotWrapped.__module__ = "cadquery.occ_impl.shapes"
    with pytest.raises(TypeError):
        _as_build123d(_NotWrapped())


# ---------------------------------------------------------------------------
# analyze() dispatch
# ---------------------------------------------------------------------------

def test_analyze_routes_cq_shape_through_brep() -> None:
    mock = _make_mock_cq_shape(_TOPO_DS)
    report = analyze(mock)
    # A plain 10×10×5 box: no overhangs, not manifold issue, no tip-over.
    assert report.overhangs == ()
    assert report.manifold_issues == ()


def test_analyze_cq_and_b3d_same_findings() -> None:
    """CadQuery adapter produces identical findings to the build123d path."""
    mock = _make_mock_cq_shape(_TOPO_DS)
    cq_report = analyze(mock)
    b3d_report = analyze(_B3D_BOX)
    assert cq_report.findings == b3d_report.findings


# ---------------------------------------------------------------------------
# Full e2e with real CadQuery (skipped if not installed)
# ---------------------------------------------------------------------------

def test_e2e_real_cadquery_box() -> None:  # pragma: no cover
    cq = pytest.importorskip("cadquery")
    from build123d import Box as B3dBox

    cq_box = cq.Workplane().box(10, 10, 5)
    b3d_box = B3dBox(10, 10, 5)

    cq_report = analyze(cq_box)
    b3d_report = analyze(b3d_box)

    # Same geometry → same printability findings.
    assert cq_report.findings == b3d_report.findings
