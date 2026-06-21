# Changelog

All notable changes to augura are documented here. Versions follow PEP 440;
between releases `pyproject.toml` carries a `.devN` suffix.

## 0.1.4

- **Python 3.13 supported**: `requires-python` raised to `>=3.11,<3.14`. The
  build123d / cadquery-ocp stack installs on 3.13 (the 3.13 wheel pulls the
  `cadquery_vtk` fork in place of upstream `vtk`); augura's full suite passes
  there. CI still runs 3.11/3.12 because the committed `uv.lock` can't `uv sync`
  on 3.13 with build123d 0.10 — cadquery-ocp 7.8 ships divergent per-wheel deps
  that a universal lock can't represent — but a normal `pip install augura`
  resolves freshly and works on 3.13.
- **Bridge vs. overhang (#49)**: a flat (horizontal) downward ceiling that is
  *wall-bounded* and whose narrowest span is at or below `--max-bridge`
  (default 5 mm) is now reported as an informational `bridge` (FDM bridges it
  without support) instead of a blanket `overhang` warning. The check is
  adjacency-aware: the underside of a floating or cantilevered mass is never a
  bridge, however narrow, because it has no walls to anchor bridge lines to.
  Overhang messages now carry the face area (and, for flats, the span) so a wide
  flat ceiling reads differently from a hairline ridge. `bridge` findings are
  excluded from the support area used in orientation ranking; a `report.bridges`
  accessor and a `--max-bridge` flag (on `analyze` and `orientations`) are added.
- **Degenerate-apex crash fixed (#48)**: `analyze` aborted with
  `gp_Vec::Normalized() - vector has zero norm` on watertight solids with a
  point-singular face (cone tip, pyramid apex) — a wall-thickness probe ray
  grazing the apex hit an undefined normal. Such rays are now skipped; the part
  analyses normally.

## 0.1.3

- **estampo output on the CLI**: `augura analyze <part>.step --format estampo`
  emits the `estampo.toml` fragment (with source provenance in the header).
- **Orientation-aware analysis**: `--best-orientation` rotates the part to its
  top-ranked print pose before analysing (works with every output format; the
  rotation is reported — `orient = [X, Y, Z]` in estampo, `rotation` in JSON);
  `--orient X Y Z` analyses at an explicit pose instead. Both are STEP-only.
- **Build-volume-aware orientation ranking**: `orientation_scores` gained
  `build_volume=` — poses that fit rank before poses that don't, scores carry
  `fits_build_volume`, and `augura orientations --build-volume` marks misfits;
  `--best-orientation` warns when no candidate pose fits. All fit checks (BREP,
  mesh, ranking) now share one `overflowing_axes` predicate and tolerance.
- **`apply_orientation(shape, rotation)`** is public: poses a shape exactly as
  `orientation_scores` evaluated it (rotate, then drop onto the bed). The
  Euler convention (intrinsic X→Y→Z, build123d `Rotation`) is now documented.

## 0.1.2

- **CadQuery input**: `analyze` and `orientation_scores` accept CadQuery
  `Workplane`/`Shape` objects directly via the shared OCCT kernel
  (`as_build123d`, `is_cadquery`); multi-body (print-in-place) inputs are
  accepted as compounds.
- **estampo output adapter**: `to_estampo_toml(report)` emits an
  `estampo.toml` fragment (pure data transform — no estampo import).
- **Manifold check fixed**: degenerated edges (cone apexes, sphere poles) were
  counted as non-manifold, so plain `Sphere`/`Cone` solids — and most imported
  real-world STEP parts — were reported "not watertight" at ERROR severity.
  The check now uses OCCT's `BRepCheck_Shell` closed-status per shell, and a
  shape containing no solid body gets a distinct "no solid body" finding.
- **Real-world STEP regression fixtures**: Framework Expansion Card
  (multi-body) and CUBOTino cover, both CC-BY-4.0, exercised by the full
  import → analyze pipeline in CI.
- Tooling: ruff pinned and the codebase reformatted to it.

## 0.1.1

- **CLI** (`augura` command): `augura analyze <file>` and `augura orientations
  <file>` accept STEP (exact BREP) or STL (mesh) input, with `--format
  text|md|json`, `--exit-code` (non-zero on an ERROR finding), and tuning flags
  (`--support-angle`, `--nozzle`, `--min-perimeters`, `--build-volume`).
- **STL support is now first-class** — `trimesh` is a core dependency (no
  `augura[mesh]` extra needed).
- `analyze()` gained `nozzle` / `min_perimeters` parameters; `Report.to_dict()`
  added for JSON / programmatic use.

## 0.1.0

First public release — pre-alpha. BREP-exact, pre-slice printability analysis
for build123d / FDM, behind a single `analyze()` façade returning a `Report`.

Checks (all exact, run on a build123d solid):
- **overhangs** — downward faces shallower than the support angle, bed-contact excluded
- **manifold / watertight** — closed-solid check
- **tip-over / stability** — centre of mass vs. the convex hull of the bed footprint
- **bed-fit** — oriented bounding box vs. a declared build volume
- **brim / raft risk** — small-footprint / high-aspect heuristic
- **minimum feature / layer-height bound** — smallest vertical step the print must resolve
- **wall thickness** — opposed-face ray sampling vs. `min_perimeters × nozzle`
- **orientation search** — ranks candidate poses by unsupported overhang area (full frontier)

Input:
- build123d `Shape` (exact BREP path)
- tessellated mesh via the optional `augura[mesh]` extra (degraded, approximate path)

Status: the public API is still evolving; `0.1.x` may introduce breaking changes.
