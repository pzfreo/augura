# Changelog

All notable changes to augura are documented here. Versions follow PEP 440;
between releases `pyproject.toml` carries a `.devN` suffix.

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
