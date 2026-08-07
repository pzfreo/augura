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
  a floppy material. The span now comes from what actually supports the ceiling. Each
  stretch of its boundary is probed for material below; bridge lines must run parallel to
  every *unanchored* stretch or land in mid-air, so those stretches pick the direction,
  and the ceiling is measured along it. Anchored the whole way round, any direction works
  and the narrowest wins. Consequences: spans on through-features grow (some ceilings
  correctly stop being bridges), the answer no longer depends on how the part sits
  relative to the global axes (the same part read 2.0 mm upright and 15.6 mm at 45 deg),
  and a ceiling with no workable direction now says `no bridge direction - needs support`
  instead of quoting a span it cannot achieve.
- **The span is a chord, not an extent** (#55). What is measured is the longest line in
  the chosen direction that stays inside the ceiling, found by scanning the boundary. An
  L-shaped cavity with 3 mm arms used to be measured end to end at 20 mm; no bridge line
  crosses more than one arm, so it is 4.2 mm across the diagonal and bridges. A ceiling
  with an island of material in it (an inner wire) is now measured to the island rather
  than across it.
- **Anchor detection is local, and reads geometry rather than curve type** (#55). The old
  wall-bounded check asked whether a neighbouring face's *bounding box* reached below the
  ceiling plane — true for the outer skin of a wall a through-window is cut into even
  though nothing is under that edge. Boundaries are now walked at roughly 1 mm and probed
  for material just beyond and just below, per solid so touching solids in an unfused
  compound are not missed (the same `Compound.is_inside` trap `wall_thickness` sidesteps).
  Two things follow: a ceiling carried only on scattered pads is no longer mistaken for a
  bridge, and nothing keys off `GeomType`, so a spline that runs dead straight — which
  imported STEP is full of — behaves exactly like a line instead of being written off as
  uncurved. Ceilings bounded only by curves are handled directly rather than falling back
  to a bounding box, so a 20 x 4 mm elliptical pocket reads 4 mm at any rotation.
- **A direction is judged by where its lines land** (#55). Deciding it from which way the
  unanchored boundary points needed a tolerance, and no tolerance worked: tight enough to
  reject a roof whose sides converge into a corner no line reaches, and a window through a
  drafted wall was rejected too; loose enough to accept the window, and the roof came back
  as "bridges, no support needed" — an unsafe answer, since a wrong yes costs a failed print
  where a wrong no costs support material. Each candidate direction is now scanned and kept
  only if *every* line it produces is held at both ends, which needs no tolerance at all and
  removes the constant.
- **Anchor probing corrected against two false readings** (#55). Probes were dropped from one
  height taken from the face's lowest corner, but a ceiling may lean up to a degree and still
  count as flat — over a long ceiling that puts the probe well below the far end, where open
  air reads as solid. That produced a genuine *unsafe* verdict: a tilted ceiling with a
  missing wall reported as bridging. Each probe now drops from its own point. Probes also
  reached out before dropping far enough for a **filleted** roof junction, which is horizontal
  where it meets the ceiling and falls away as `sqrt(2*R*depth)`: any fillet over 0.05 mm read
  as open air and switched bridging off, which covers most real parts.
- **Bounded cost.** A ceiling whose area over its reach already exceeds `max_bridge` holds a
  line at least that long whichever way lines run, so it cannot bridge and is settled before
  any probe or scan. Without it a lid carrying a grid of bosses — each boss an inner wire —
  went quadratic: 144 bosses took 13.6 s, now under a second. Where that bound settles it, the
  message says "at least N mm span": the bound, not a measured line, so the number never moves
  with the caller's `max_bridge`.
- **A shape with no solid no longer claims a verdict.** Anchors are found by classifying points
  against solids, so surface-only input had every probe come back empty and every ceiling
  declared unbridgeable — a confident answer resting on no evidence. It now reports the ceiling
  without a bridge claim. A collapsed or self-crossing outline likewise returns "no direction"
  rather than a zero-length span, which read as "no support needed".
- Known limits, in the order they are likely to bite. **A window through a drafted, tapered or
  curved wall is reported as needing support.** Its unanchored sides are not quite parallel, so
  a line at the very edge of the ceiling does have one end unheld — a sliver in practice, but
  the model counts it, and it is the common case that over-warns. A ceiling with a **hole
  through it** treats the hole's rim as unanchored, when a bridge line should pass over it and
  land on the far side, so the annular step of a counterbore is reported as needing support
  (#58). Directions are tried every 5 degrees plus one across each stretch of boundary, and an
  untried direction can only make the span larger, never smaller (#59). Boundaries are walked
  at a millimetre up to a cap per edge, so a very long edge is sampled coarser and finer
  support gaps can be stepped over (#61). Tightly curved boundaries are measured on an
  inscribed polyline, normally under 2% low, but on a large curved boundary the polylines of a
  narrow slot can cross and the span is then unreliable in either direction (#60). Finally, an
  anchor is material that is *present*, not material that is itself supported (#62).


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
