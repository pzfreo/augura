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

from build123d import Compound, Shape


def is_cadquery(obj: Any) -> bool:
    """Return True if *obj* looks like a CadQuery object.

    Detects by module prefix (``cadquery.*``) and the presence of either
    ``.wrapped`` (``cadquery.Shape`` subclass) or ``.val()`` (``Workplane``).
    Does not import cadquery.
    """
    module = type(obj).__module__
    if not (module == "cadquery" or module.startswith("cadquery.")):
        return False
    return hasattr(obj, "wrapped") or (hasattr(obj, "val") and callable(obj.val))


def as_build123d(cq_obj: Any) -> Shape:
    """Wrap a CadQuery ``Solid`` / ``Shape`` / ``Workplane`` as a build123d Shape.

    The underlying ``TopoDS_Shape`` is shared — no geometry copy.

    Args:
        cq_obj: A ``cadquery.Workplane``, ``cadquery.Solid``, or any
            ``cadquery.Shape`` subclass.

    Returns:
        A build123d :class:`~build123d.Shape` (typically a ``Solid``) backed by
        the same OCCT kernel object.

    Raises:
        TypeError: If *cq_obj* is not a recognised CadQuery type.
        ValueError: If a ``Workplane`` contains more than one solid. Select a
            single result first (e.g. ``wp.val()``) before passing to
            ``as_build123d``.
    """
    # Workplane: unwrap to cadquery.Shape via .val() / .vals()
    if hasattr(cq_obj, "vals") and callable(cq_obj.vals):
        vals = cq_obj.vals()
        if len(vals) == 0:
            raise ValueError("CadQuery Workplane is empty — nothing to analyse")
        if len(vals) > 1:
            raise ValueError(
                f"CadQuery Workplane contains {len(vals)} solids; "
                "select one before calling as_build123d() (e.g. wp.val())"
            )
        cq_obj = vals[0]

    if not hasattr(cq_obj, "wrapped"):
        raise TypeError(
            f"Cannot convert {type(cq_obj).__qualname__!r} to a build123d Shape; "
            "expected a cadquery.Shape subclass or Workplane"
        )

    return Compound.cast(cq_obj.wrapped)
