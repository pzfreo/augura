"""CadQuery input adapter — exact BREP path via shared OCCT kernel.

CadQuery and build123d both wrap the same OpenCASCADE (OCP) kernel, so a
CadQuery solid is backed by the same ``TopoDS_Shape`` type that build123d uses.
The adapter extracts that shape and hands it to the standard BREP pipeline
without any geometry copy.

No hard ``import cadquery`` — the duck-type detection works without CadQuery
being present, and the conversion only touches attributes that already exist on
the passed object.
"""

from __future__ import annotations

from typing import Any

from build123d import Compound, Shape, Solid
from OCP.TopoDS import TopoDS_Shape


def is_cadquery(obj: Any) -> bool:
    """Return True if *obj* comes from the cadquery package.

    Detects by module prefix (``cadquery.*``) alone — every CadQuery object is
    routed to :func:`as_build123d`, which raises a clear error for types it
    cannot convert (e.g. ``Assembly``). Does not import cadquery.
    """
    module = type(obj).__module__
    return module == "cadquery" or module.startswith("cadquery.")


def _topo(cq_obj: Any) -> TopoDS_Shape:
    """Extract the validated ``TopoDS_Shape`` from a CadQuery Shape-like object."""
    if not hasattr(cq_obj, "wrapped"):
        raise TypeError(
            f"Cannot convert {type(cq_obj).__qualname__!r} to a build123d Shape; "
            "expected a cadquery.Shape subclass or Workplane "
            "(for an Assembly, flatten it first, e.g. assembly.toCompound())"
        )
    # cq.Vector / cq.Location also have .wrapped, but it holds a gp_Vec /
    # TopLoc_Location rather than OCCT topology — reject before cast.
    if not isinstance(cq_obj.wrapped, TopoDS_Shape):
        raise TypeError(
            f"{type(cq_obj).__qualname__!r}.wrapped is not OCCT topology; "
            "expected a cadquery.Shape subclass wrapping a TopoDS_Shape"
        )
    return cq_obj.wrapped


def as_build123d(cq_obj: Any) -> Shape:
    """Wrap a CadQuery ``Solid`` / ``Shape`` / ``Workplane`` as a build123d Shape.

    The underlying ``TopoDS_Shape`` is shared — no geometry copy.

    Multi-body input (a multi-solid compound or a ``Workplane`` holding several
    solids, e.g. a print-in-place hinge) is accepted and combined into a single
    compound, matching how a multi-solid build123d compound is analysed.

    Args:
        cq_obj: A ``cadquery.Workplane``, ``cadquery.Solid``, or any
            ``cadquery.Shape`` subclass.

    Returns:
        A build123d :class:`~build123d.Shape` backed by the same OCCT kernel
        object(s).

    Raises:
        TypeError: If *cq_obj* is not a recognised CadQuery type, contains no
            solids, or mixes solids with free non-solid topology.
        ValueError: If a ``Workplane`` is empty.
    """
    # Workplane: unwrap to cadquery.Shape(s) via .vals()
    if hasattr(cq_obj, "vals") and callable(cq_obj.vals):
        vals = cq_obj.vals()
        if len(vals) == 0:
            raise ValueError("CadQuery Workplane is empty — nothing to analyse")
        if len(vals) == 1:
            result = Compound.cast(_topo(vals[0]))
        else:
            # Multiple stacked solids (e.g. print-in-place bodies): combine.
            result = Compound(children=[Compound.cast(_topo(v)) for v in vals])
    else:
        result = Compound.cast(_topo(cq_obj))

    # The downstream checks (overhangs, wall thickness, tip-over) only make
    # sense for solid bodies — reject faces/shells/wires up front.
    if isinstance(result, Compound):
        solids = result.solids()
        if len(solids) == 0:
            raise TypeError("CadQuery input contains no solids; augura analyses solid bodies")
        # A compound mixing solids with free faces/shells would silently
        # corrupt area-based findings — every face must belong to a solid.
        if len(result.faces()) != sum(len(s.faces()) for s in solids):
            raise TypeError(
                "CadQuery input mixes solids with stray non-solid geometry; pass the solids alone"
            )
    elif not isinstance(result, Solid):
        raise TypeError(
            f"CadQuery input is a {type(result).__name__}, not a solid; "
            "augura analyses solid bodies"
        )

    return result
