"""Bed-fit check: does the part fit a declared build volume?

Compares the part's axis-aligned bounding box (in its current, print-ready
orientation) against a build volume and flags any axis that overflows.
"""

from __future__ import annotations

from typing import Any

from build123d import Shape

from augura.report import Finding, Severity

# mm slack so an exact fit is not flagged on rounding noise.
FIT_TOL = 1e-6


def find_bed_fit(shape: Shape[Any], build_volume: tuple[float, float, float]) -> list[Finding]:
    """Return a single ``bed_fit`` finding if the part overflows the build volume.

    Compares the bounding-box *extent* per axis; the part's absolute position is
    irrelevant because the slicer places it on the plate. This answers "is the
    part too big for the volume?", not "is it currently sitting inside those
    coordinates?".

    Args:
        shape: the part, oriented as it will be printed.
        build_volume: usable build volume as ``(x, y, z)`` in mm.
    """
    size = shape.bounding_box().size
    extents = (size.X, size.Y, size.Z)
    over = [
        axis
        for axis, extent, limit in zip("XYZ", extents, build_volume, strict=True)
        if extent > limit + FIT_TOL
    ]
    if not over:
        return []
    msg = (
        f"Part {size.X:.1f}x{size.Y:.1f}x{size.Z:.1f} mm exceeds the "
        f"{build_volume[0]:.0f}x{build_volume[1]:.0f}x{build_volume[2]:.0f} mm "
        f"build volume on {', '.join(over)}"
    )
    return [Finding(kind="bed_fit", severity=Severity.ERROR, message=msg)]
