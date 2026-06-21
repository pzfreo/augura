"""Command-line interface for augura.

Usage::

    augura analyze <file>        # printability report
    augura orientations <file>   # rank print orientations by support need

``<file>`` is a STEP (``.step`` / ``.stp``) part — analysed on the exact BREP
path — or an STL (``.stl``) — loaded as a mesh and analysed on the degraded,
approximate path. Output is human text by default, or Markdown (``--format md``),
JSON (``--format json``), or — for ``analyze`` — an estampo.toml fragment
(``--format estampo``).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from augura.analyze import analyze
from augura.estampo import format_rotation, to_estampo_toml
from augura.footprint import BED_TOL
from augura.mesh import is_mesh
from augura.min_feature import DEFAULT_MIN_FEATURE
from augura.orientation import (
    OrientationScore,
    Rotation3,
    apply_orientation,
    orientation_scores,
)
from augura.overhangs import DEFAULT_MAX_BRIDGE, DEFAULT_SUPPORT_ANGLE
from augura.report import Report, Severity
from augura.wall_thickness import DEFAULT_MIN_PERIMETERS, DEFAULT_NOZZLE

_STEP_SUFFIXES = {".step", ".stp"}
_STL_SUFFIXES = {".stl"}


def _load(path: Path) -> Any:
    """Load a CAD file: STEP -> exact build123d solid; STL -> trimesh mesh."""
    suffix = path.suffix.lower()
    if suffix in _STEP_SUFFIXES:
        from build123d import import_step

        return import_step(path)
    if suffix in _STL_SUFFIXES:
        import trimesh

        return trimesh.load(path, force="mesh")
    raise ValueError(f"unsupported file type '{path.suffix}' (use .step/.stp or .stl)")


def _md_cell(text: str) -> str:
    """Escape a string for a single Markdown table cell."""
    return text.replace("|", r"\|").replace("\n", " ")


def _render_report(report: Report, source: str, fmt: str, orient: Rotation3 | None = None) -> str:
    if fmt == "estampo":
        return to_estampo_toml(report, orient=orient, source=source)
    if fmt == "json":
        payload: dict[str, Any] = {"source": source}
        if orient is not None:
            payload["rotation"] = list(orient)
        payload.update(report.to_dict())
        return json.dumps(payload, indent=2)
    orient_note = f"analysed at rotation {format_rotation(orient)}" if orient is not None else None
    if fmt == "md":
        lines = [f"# augura report - `{source}`", ""]
        if orient_note:
            lines += [orient_note, ""]
        if not report.findings:
            return "\n".join([*lines, "No printability issues found."]) + "\n"
        lines += ["| Severity | Check | Detail |", "| --- | --- | --- |"]
        lines += [
            f"| {f.severity.value} | {f.kind} | {_md_cell(f.message)} |" for f in report.findings
        ]
        return "\n".join([*lines, ""]) + "\n"
    # text
    lines = [f"augura - {source}"]
    if orient_note:
        lines.append(f"  {orient_note}")
    if not report.findings:
        return "\n".join([*lines, "  No printability issues found."])
    lines += [f"  [{f.severity.value.upper()}] {f.kind}: {f.message}" for f in report.findings]
    errors = sum(1 for f in report.findings if f.severity is Severity.ERROR)
    warnings = sum(1 for f in report.findings if f.severity is Severity.WARNING)
    infos = sum(1 for f in report.findings if f.severity is Severity.INFO)
    lines.append(
        f"  {len(report.findings)} finding(s): {errors} error, {warnings} warning, {infos} info"
    )
    return "\n".join(lines)


def _fit_note(score: OrientationScore) -> str:
    return " (exceeds build volume)" if score.fits_build_volume is False else ""


def _render_orientations(scores: list[OrientationScore], source: str, fmt: str) -> str:
    if fmt == "json":
        entries = []
        for s in scores:
            entry: dict[str, Any] = {
                "rotation": list(s.rotation),
                "overhang_area": s.overhang_area,
                "z_height_mm": s.z_height,
                "bed_contact_mm2": s.bed_contact_area,
            }
            if s.fits_build_volume is not None:
                entry["fits_build_volume"] = s.fits_build_volume
            entries.append(entry)
        return json.dumps({"source": source, "orientations": entries}, indent=2)
    if fmt == "md":
        lines = [
            f"# augura orientations - `{source}`",
            "",
            "| Rank | Rotation (deg) | Overhang (mm2) | Z-height (mm) | Bed contact (mm2) |",
            "| --- | --- | --- | --- | --- |",
        ]
        lines += [
            f"| {i} | {s.rotation}{_fit_note(s)} | {s.overhang_area:.1f} | {s.z_height:.1f}"
            f" | {s.bed_contact_area:.0f} |"
            for i, s in enumerate(scores, 1)
        ]
        return "\n".join([*lines, ""]) + "\n"
    # text
    lines = [f"augura orientations - {source} (best first)"]
    lines += [
        f"  {i}. rotation {s.rotation}{_fit_note(s)} -> {s.overhang_area:.1f} mm2 overhang, "
        f"{s.z_height:.1f} mm tall, {s.bed_contact_area:.0f} mm2 contact"
        for i, s in enumerate(scores, 1)
    ]
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="augura", description="Pre-slice printability analysis.")
    sub = parser.add_subparsers(dest="command", required=True)

    an = sub.add_parser("analyze", help="report a part's printability issues")
    an.add_argument("file", type=Path, help="STEP (.step/.stp) or STL (.stl) file")
    an.add_argument("--format", choices=["text", "md", "json", "estampo"], default="text")
    an.add_argument("--support-angle", type=float, default=DEFAULT_SUPPORT_ANGLE)
    an.add_argument("--nozzle", type=float, default=DEFAULT_NOZZLE)
    an.add_argument("--min-perimeters", type=int, default=DEFAULT_MIN_PERIMETERS)
    an.add_argument(
        "--build-volume",
        nargs=3,
        type=float,
        metavar=("X", "Y", "Z"),
        default=None,
        help="enable the bed-fit check against this volume (mm);"
        " with --best-orientation, poses that fit it rank first",
    )
    an.add_argument(
        "--bed-tol",
        type=float,
        default=BED_TOL,
        metavar="MM",
        help="Z tolerance (mm) for identifying bed-contact faces (default: %(default)s)",
    )
    an.add_argument(
        "--min-feature",
        type=float,
        default=DEFAULT_MIN_FEATURE,
        metavar="MM",
        help="minimum vertical feature size (mm) to flag (default: %(default)s)",
    )
    an.add_argument(
        "--max-bridge",
        type=float,
        default=DEFAULT_MAX_BRIDGE,
        metavar="MM",
        help="flat ceilings with a span up to this (mm) are bridgeable info, not"
        " overhang warnings (default: %(default)s)",
    )
    an.add_argument("--exit-code", action="store_true", help="exit 1 if any ERROR-severity finding")
    pose = an.add_mutually_exclusive_group()
    pose.add_argument(
        "--best-orientation",
        action="store_true",
        help="rotate the part to its top-ranked print orientation before analysing"
        " (with --build-volume, poses that fit rank first); the rotation [X, Y, Z]"
        " is reported in the output (STEP input only)",
    )
    pose.add_argument(
        "--orient",
        nargs=3,
        type=float,
        metavar=("X", "Y", "Z"),
        default=None,
        help="analyse at this explicit (X, Y, Z) Euler rotation in degrees, e.g. a pose"
        " chosen from 'augura orientations' (STEP input only)",
    )

    orient = sub.add_parser("orientations", help="rank print orientations by support need")
    orient.add_argument("file", type=Path, help="STEP (.step/.stp) file")
    orient.add_argument("--format", choices=["text", "md", "json"], default="text")
    orient.add_argument("--support-angle", type=float, default=DEFAULT_SUPPORT_ANGLE)
    orient.add_argument(
        "--max-bridge",
        type=float,
        default=DEFAULT_MAX_BRIDGE,
        metavar="MM",
        help="flat ceilings with a span up to this (mm) don't count toward a pose's"
        " support need (default: %(default)s)",
    )
    orient.add_argument(
        "--build-volume",
        nargs=3,
        type=float,
        metavar=("X", "Y", "Z"),
        default=None,
        help="rank poses that fit this build volume (mm) first, and mark those that don't",
    )
    orient.add_argument(
        "--bed-tol",
        type=float,
        default=BED_TOL,
        metavar="MM",
        help="Z tolerance (mm) for identifying bed-contact faces (default: %(default)s)",
    )
    return parser


def _xyz(values: list[float]) -> tuple[float, float, float]:
    return (values[0], values[1], values[2])


def _run_analyze(shape: Any, args: argparse.Namespace) -> int:
    build_volume = _xyz(args.build_volume) if args.build_volume else None
    orient: Rotation3 | None = None
    if args.best_orientation or args.orient is not None:
        if is_mesh(shape):
            raise ValueError("--best-orientation/--orient need a STEP/BREP input, not a mesh")
        if args.orient is not None:
            orient = _xyz(args.orient)
        else:
            best = orientation_scores(
                shape,
                support_angle=args.support_angle,
                bed_tol=args.bed_tol,
                build_volume=build_volume,
                max_bridge=args.max_bridge,
            )[0]
            if best.fits_build_volume is False:
                print(
                    "augura: no candidate orientation fits the build volume;"
                    " using the unconstrained best",
                    file=sys.stderr,
                )
            orient = best.rotation
        # Analyse the part as it will actually print: rotated and dropped onto
        # the bed (the same pose orientation_scores evaluates), so the report
        # describes the part at the rotation it emits.
        shape = apply_orientation(shape, orient)
    report = analyze(
        shape,
        support_angle=args.support_angle,
        build_volume=build_volume,
        nozzle=args.nozzle,
        min_perimeters=args.min_perimeters,
        bed_tol=args.bed_tol,
        min_feature=args.min_feature,
        max_bridge=args.max_bridge,
    )
    print(_render_report(report, args.file.name, args.format, orient=orient))
    if args.exit_code and any(f.severity is Severity.ERROR for f in report.findings):
        return 1
    return 0


def _run_orientations(shape: Any, args: argparse.Namespace) -> int:
    if is_mesh(shape):
        raise ValueError("orientation search needs a STEP/BREP input, not a mesh")
    scores = orientation_scores(
        shape,
        support_angle=args.support_angle,
        bed_tol=args.bed_tol,
        build_volume=_xyz(args.build_volume) if args.build_volume else None,
        max_bridge=args.max_bridge,
    )
    print(_render_orientations(scores, args.file.name, args.format))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    args.file = args.file.expanduser()
    try:
        if not args.file.exists():
            raise FileNotFoundError(f"no such file: {args.file}")
        shape = _load(args.file)
        if is_mesh(shape) and shape.bounds is None:
            raise ValueError(f"no readable geometry in {args.file.name}")
        if args.command == "analyze":
            return _run_analyze(shape, args)
        return _run_orientations(shape, args)
    except Exception as exc:
        # CLI boundary: any failure reading or processing an input file becomes a
        # clean message + exit 2, never a traceback.
        print(f"augura: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
