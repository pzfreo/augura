"""Command-line interface for augura.

Usage::

    augura analyze <file>        # printability report
    augura orientations <file>   # rank print orientations by support need

``<file>`` is a STEP (``.step`` / ``.stp``) part — analysed on the exact BREP
path — or an STL (``.stl``) — loaded as a mesh and analysed on the degraded,
approximate path. Output is human text by default, or Markdown (``--format md``)
or JSON (``--format json``).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from augura.analyze import analyze
from augura.footprint import BED_TOL
from augura.mesh import is_mesh
from augura.min_feature import DEFAULT_MIN_FEATURE
from augura.orientation import OrientationScore, orientation_scores
from augura.overhangs import DEFAULT_SUPPORT_ANGLE
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


def _render_report(report: Report, source: str, fmt: str) -> str:
    if fmt == "json":
        return json.dumps({"source": source, **report.to_dict()}, indent=2)
    if fmt == "md":
        lines = [f"# augura report - `{source}`", ""]
        if not report.findings:
            return "\n".join([*lines, "No printability issues found."]) + "\n"
        lines += ["| Severity | Check | Detail |", "| --- | --- | --- |"]
        lines += [
            f"| {f.severity.value} | {f.kind} | {_md_cell(f.message)} |" for f in report.findings
        ]
        return "\n".join([*lines, ""]) + "\n"
    # text
    if not report.findings:
        return f"augura - {source}\n  No printability issues found."
    lines = [f"augura - {source}"]
    lines += [f"  [{f.severity.value.upper()}] {f.kind}: {f.message}" for f in report.findings]
    errors = sum(1 for f in report.findings if f.severity is Severity.ERROR)
    warnings = sum(1 for f in report.findings if f.severity is Severity.WARNING)
    lines.append(f"  {len(report.findings)} finding(s): {errors} error, {warnings} warning")
    return "\n".join(lines)


def _render_orientations(scores: list[OrientationScore], source: str, fmt: str) -> str:
    if fmt == "json":
        payload = {
            "source": source,
            "orientations": [
                {
                    "rotation": list(s.rotation),
                    "overhang_area": s.overhang_area,
                    "z_height_mm": s.z_height,
                    "bed_contact_mm2": s.bed_contact_area,
                }
                for s in scores
            ],
        }
        return json.dumps(payload, indent=2)
    if fmt == "md":
        lines = [
            f"# augura orientations - `{source}`",
            "",
            "| Rank | Rotation (deg) | Overhang (mm2) | Z-height (mm) | Bed contact (mm2) |",
            "| --- | --- | --- | --- | --- |",
        ]
        lines += [
            f"| {i} | {s.rotation} | {s.overhang_area:.1f} | {s.z_height:.1f} | {s.bed_contact_area:.0f} |"
            for i, s in enumerate(scores, 1)
        ]
        return "\n".join([*lines, ""]) + "\n"
    # text
    lines = [f"augura orientations - {source} (best first)"]
    lines += [
        f"  {i}. rotation {s.rotation} -> {s.overhang_area:.1f} mm2 overhang, "
        f"{s.z_height:.1f} mm tall, {s.bed_contact_area:.0f} mm2 contact"
        for i, s in enumerate(scores, 1)
    ]
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="augura", description="Pre-slice printability analysis.")
    sub = parser.add_subparsers(dest="command", required=True)

    an = sub.add_parser("analyze", help="report a part's printability issues")
    an.add_argument("file", type=Path, help="STEP (.step/.stp) or STL (.stl) file")
    an.add_argument("--format", choices=["text", "md", "json"], default="text")
    an.add_argument("--support-angle", type=float, default=DEFAULT_SUPPORT_ANGLE)
    an.add_argument("--nozzle", type=float, default=DEFAULT_NOZZLE)
    an.add_argument("--min-perimeters", type=int, default=DEFAULT_MIN_PERIMETERS)
    an.add_argument("--build-volume", nargs=3, type=float, metavar=("X", "Y", "Z"), default=None)
    an.add_argument(
        "--bed-tol", type=float, default=BED_TOL, metavar="MM",
        help="Z tolerance (mm) for identifying bed-contact faces (default: %(default)s)",
    )
    an.add_argument(
        "--min-feature", type=float, default=DEFAULT_MIN_FEATURE, metavar="MM",
        help="minimum vertical feature size (mm) to flag (default: %(default)s)",
    )
    an.add_argument("--exit-code", action="store_true", help="exit 1 if any ERROR-severity finding")

    orient = sub.add_parser("orientations", help="rank print orientations by support need")
    orient.add_argument("file", type=Path, help="STEP (.step/.stp) file")
    orient.add_argument("--format", choices=["text", "md", "json"], default="text")
    orient.add_argument("--support-angle", type=float, default=DEFAULT_SUPPORT_ANGLE)
    return parser


def _run_analyze(shape: Any, args: argparse.Namespace) -> int:
    build_volume = (
        (args.build_volume[0], args.build_volume[1], args.build_volume[2])
        if args.build_volume
        else None
    )
    report = analyze(
        shape,
        support_angle=args.support_angle,
        build_volume=build_volume,
        nozzle=args.nozzle,
        min_perimeters=args.min_perimeters,
        bed_tol=args.bed_tol,
        min_feature=args.min_feature,
    )
    print(_render_report(report, args.file.name, args.format))
    if args.exit_code and any(f.severity is Severity.ERROR for f in report.findings):
        return 1
    return 0


def _run_orientations(shape: Any, args: argparse.Namespace) -> int:
    if is_mesh(shape):
        print("augura: orientation search needs a STEP/BREP input, not a mesh", file=sys.stderr)
        return 2
    scores = orientation_scores(shape, support_angle=args.support_angle)
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
