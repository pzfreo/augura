# Changelog

All notable changes to augura are documented here. Versions follow PEP 440;
between releases `pyproject.toml` carries a `.devN` suffix.

## 0.1.8

- **Bridge span is the real unsupported distance, not a bounding-box side** (#55). The
  `bridge`/`overhang` span used to be the smaller in-plane extent of the ceiling face,
  which is only the bridging direction when the ceiling is anchored on that pair of
  sides. A rectangular window through a thin wall is the counter-example: the ceiling is
  `window_width x wall_thickness`, but the wall thickness has open air on both faces, so
  a 20 x 2 mm window reported "2.0 mm span - bridges, no support needed" when the bridge
  really has to cross 20 mm — the difference between a non-event and a real decision in
  a floppy material. The span is now derived from which of the ceiling's boundary edges
  have material below them to land on: bridge lines must run parallel to every
  *unanchored* edge, so those edges pick the direction and the ceiling is measured along
  it; with every edge anchored, any direction works and the narrowest wins. Three
  consequences: spans on through-features grow (some ceilings correctly stop being
  bridges), the answer no longer changes when the part is rotated about the print axis
  (the same part read 2.0 mm upright and 15.6 mm at 45 deg), and ceilings with no
  workable bridge direction now say `no bridge anchors - needs support` rather than
  quoting a span they cannot achieve.
- **Anchor detection is local rather than whole-face** (#55). The old wall-bounded check
  asked whether a neighbouring face's *bounding box* reached below the ceiling plane,
  which is true for the outer skin of a wall a through-window is cut into even though
  there is nothing under that edge, and false for a genuine anchor whose face is
  classified oddly. It now probes for material just beyond the edge and just below the
  plane, per solid so touching solids in an unfused compound are not missed (the same
  `Compound.is_inside` trap `wall_thickness` sidesteps). On the bundled Framework card
  fixture two pocket ceilings that were warned about as "1.3 mm span needs support" are
  now correctly `2.0 mm span - bridges`, measured across the axis that has anchors.
  Despite the extra queries `analyze()` got slightly faster on both real-world
  fixtures, since the classifier is now built once per part instead of per query.

## 0.1.7

- **Constrain away from the broken `cadquery-ocp-novtk 7.9.3.1.1` wheel** (#53). build123d
  0.11 pulls `cadquery-ocp-novtk>=7.9`, which resolves to 7.9.3.1.1 — a macOS wheel with no
  `OCP.GccEnt` module, so `import build123d` fails on a clean install. Added a `[tool.uv]`
  constraint (`!=7.9.3.1.1`; 7.9.3.1 is intact) that only bites when novtk is resolved, so
  the build123d 0.10 matrix is untouched. Remove when upstream yanks/fixes 7.9.3.1.1.

## 0.1.6

- **`wall_thickness_at(shape, point, direction)`**: local wall thickness at a
  caller-chosen location, exposing the same BREP-exact ray query that backs
  `min_wall_thickness` (via `find_intersection_points`). Measures the length of the
  solid segment of the line `point + t*direction` that the point lies in or on. The
  result is **sign-invariant** (independent of which way `direction` points) and
  correct wherever the point sits in the wall — on a surface, mid-wall, or at an
  interior junction; if the point is in a void, the nearest solid segment is used.
  Both half-rays are cast and crossings are de-duplicated, so shared-edge double
  hits can't collapse the chord to `0`; adjacent solid segments are coalesced so a
  ray tangent to an internal bore or a coincident face in an unfused compound
  doesn't split a genuine wall (each solid is classified individually, working
  around `Compound.is_inside` only testing the first solid). Returns `None` when the
  point lies in no solid (a void — abstain rather than report an unrelated wall) or
  the line meets no solid; a near-tangent ray returns the true small chord it cuts.
  Enables a targeted "is this rib/wall the thickness the drawing calls for" check in
  downstream tools, complementing the global `min_wall_thickness`.

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
