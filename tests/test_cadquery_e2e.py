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

from augura import analyze, as_build123d, is_cadquery, orientation_scores
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


def _make_mock_cq_workplane(*topo_ds: Any) -> Any:
    """A cadquery.Workplane-like object stacking the given TopoDS shape(s)."""

    mock_shapes = [_make_mock_cq_shape(t) for t in topo_ds]

    class _MockCQWorkplane:
        def val(self) -> Any:
            return mock_shapes[0]

        def vals(self) -> list[Any]:
            return list(mock_shapes)

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
    assert pytest.approx(10.0, abs=1e-3) == bb.size.X
    assert pytest.approx(10.0, abs=1e-3) == bb.size.Y
    assert pytest.approx(5.0, abs=1e-3) == bb.size.Z


def test_as_build123d_from_workplane_single() -> None:
    wp = _make_mock_cq_workplane(_TOPO_DS)
    result = as_build123d(wp)
    assert isinstance(result, B3dShape)


def test_as_build123d_from_workplane_multiple_combines() -> None:
    """A multi-solid Workplane stack (e.g. print-in-place) becomes one compound."""
    wp = _make_mock_cq_workplane(Box(10, 10, 5).wrapped, Box(8, 8, 4).wrapped, Box(6, 6, 3).wrapped)
    result = as_build123d(wp)
    assert isinstance(result, B3dShape)
    assert len(result.solids()) == 3


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


def test_as_build123d_shell_raises() -> None:
    """Non-solid topology (a shell) is rejected, not silently analysed."""
    shell_topo = _B3D_BOX.shells()[0].wrapped
    mock = _make_mock_cq_shape(shell_topo)
    with pytest.raises(TypeError, match="not a solid"):
        as_build123d(mock)


def test_as_build123d_face_raises() -> None:
    face_topo = _B3D_BOX.faces()[0].wrapped
    mock = _make_mock_cq_shape(face_topo)
    with pytest.raises(TypeError, match="not a solid"):
        as_build123d(mock)


def test_as_build123d_non_topology_wrapped_raises() -> None:
    """cq.Vector/cq.Location have .wrapped holding non-topology — clear error."""

    class _FakeGpVec:
        pass

    mock = _make_mock_cq_shape(_FakeGpVec())
    with pytest.raises(TypeError, match="not OCCT topology"):
        as_build123d(mock)


def test_as_build123d_none_wrapped_raises() -> None:
    mock = _make_mock_cq_shape(None)
    with pytest.raises(TypeError, match="not OCCT topology"):
        as_build123d(mock)


def test_analyze_assembly_like_raises_clearly() -> None:
    """An Assembly-like object (no .wrapped, no .vals) gets a clear TypeError
    from the adapter rather than an AttributeError deep in the pipeline."""

    class _MockAssembly:
        pass

    _MockAssembly.__module__ = "cadquery.assembly"
    assert is_cadquery(_MockAssembly())
    with pytest.raises(TypeError, match="Assembly, flatten"):
        analyze(_MockAssembly())


def test_as_build123d_solid_with_stray_face_raises() -> None:
    """A compound mixing one solid with a free face is rejected, not analysed."""
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Compound

    builder = BRep_Builder()
    compound = TopoDS_Compound()
    builder.MakeCompound(compound)
    builder.Add(compound, Box(5, 5, 5).wrapped)
    builder.Add(compound, _B3D_BOX.faces()[0].wrapped)

    mock = _make_mock_cq_shape(compound)
    with pytest.raises(TypeError, match="stray non-solid geometry"):
        as_build123d(mock)


def test_as_build123d_multi_solid_compound_accepted() -> None:
    """A multi-body compound (e.g. print-in-place hinge) is analysed as one part,
    matching the native build123d path."""
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Compound

    builder = BRep_Builder()
    compound = TopoDS_Compound()
    builder.MakeCompound(compound)
    builder.Add(compound, Box(5, 5, 5).wrapped)
    builder.Add(compound, Box(3, 3, 3).wrapped)

    mock = _make_mock_cq_shape(compound)
    result = as_build123d(mock)
    assert len(result.solids()) == 2


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
    """CadQuery adapter produces identical findings to the build123d path.

    The mock wraps an independently constructed box (a distinct TopoDS object
    with the same dimensions) so the two paths genuinely diverge — a
    regression in the adapter would not corrupt both sides identically.
    """
    independent_box = Box(10, 10, 5)
    assert independent_box.wrapped is not _TOPO_DS
    mock = _make_mock_cq_shape(independent_box.wrapped)
    cq_report = analyze(mock)
    b3d_report = analyze(_B3D_BOX)
    assert cq_report.findings == b3d_report.findings


def test_orientation_scores_accepts_cq_shape() -> None:
    """orientation_scores converts CadQuery input like analyze does."""
    mock = _make_mock_cq_shape(_TOPO_DS)
    cq_scores = orientation_scores(mock)
    b3d_scores = orientation_scores(_B3D_BOX)
    assert [s.rotation for s in cq_scores] == [s.rotation for s in b3d_scores]


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
