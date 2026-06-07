# augura

BREP-exact 3D-printability analysis and print-advice for build123d / FDM.
**Will it print? Ask before you print.**

See `SPEC.md` for the full mission, aims, and — importantly — the non-aims. This
file is the working guide for changes; `SPEC.md` is the source of truth for scope.

## What augura is (one paragraph)

Given a 3D solid, augura produces a deterministic, explainable *printability
report* — overhangs, recommended orientation, bed-fit, tip-over, thin walls,
weak cross-sections — before the part is sliced. It reads the exact OpenCASCADE
boundary representation (via build123d) so its geometry is analytic, not
approximate, and falls back to a mesh path only for STL-only input.

## Design principles (do not violate without discussion)

1. **Analytic-first, mesh-fallback.** Prefer exact BREP face/edge queries
   (`face.normal_at(...)`, exact areas, exact bounding boxes). Use a mesh
   (trimesh) path *only* when no BREP is available. Never silently downgrade a
   BREP input to mesh checks.
2. **Loose coupling.** augura imports neither `build123d-mcp` nor `estampo`. It
   must stay independently `pip install`-able. Integration is one-way: other
   tools wrap augura, not the reverse. The only estampo touch-point is an
   optional *data* adapter that emits an `estampo.toml` fragment — a pure
   transform, never a runtime import.
3. **Deterministic risk report, not a probability.** Same geometry in → same
   report out. Every finding carries a location and a magnitude and is
   explainable. No opaque scores, no randomness.
4. **Stay on the geometry side of the line.** augura owns what geometry implies
   (orientation, support need, bed-fit, stability, feature sizes, relative
   strength under a *declared* load). It does **not** own material/printer
   process settings (temperature, cooling, retraction, infill) — those are
   estampo's. If a feature needs material/load/printer data, take it as an
   explicit input or defer to estampo. Do not invent it.
5. **Expose trade-offs.** Orientation is a Pareto trade-off (support vs. strength
   vs. finish). Surface the frontier; don't hard-code a single "best".

If a proposed change blurs principle 2 or 4, stop and raise it — those are the
boundaries that keep the ecosystem loosely coupled.

## Development workflow

- **Python 3.11+.**
- **Tests:** `uv run pytest` — `uv` installs dependencies from `pyproject.toml`
  first. Target is 100% passing; no accepted pre-existing failures.
- **Dependencies:** `build123d` is the core (BREP path); `trimesh` is an optional
  extra for the STL fallback. Keep the core import-light.

## Branches, PRs, releases

- **Never commit directly to `main`.** Branch per change, push, open a PR with a
  clear description, then **stop** and wait for review. Creating a PR and merging
  it are separate, separately-consented steps. Never auto-merge.
- **Run the test suite before every push.**
- **Releasing:** cut releases with `gh release create vX.Y.Z --generate-notes`.
  The `Publish` workflow (`.github/workflows/publish.yml`) then builds, publishes
  to PyPI via Trusted Publishing, and auto-bumps `pyproject.toml` to the next
  `.dev0`. Pushes to `main` publish a `.devN` build to TestPyPI. **Never edit the
  version in `pyproject.toml` by hand and never push tags manually.** Make sure
  `CHANGELOG.md`'s top entry matches the version you're about to release (strip
  the `.dev0` suffix: `pyproject = 0.1.1.dev0` means you're cutting `v0.1.1`).

## Ecosystem

```
build123d-mcp  →  augura        →  estampo            →  bambox        →  printer
(design)          (will it print?)  (reproducible slice)  (Bambu package)
```

- build123d: https://github.com/gumyr/build123d
- build123d-mcp: https://github.com/pzfreo/build123d-mcp
- build123d-drafting-helpers: https://github.com/pzfreo/build123d-drafting-helpers
- estampo: https://github.com/estampo/estampo
