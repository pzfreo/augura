# Changelog

All notable changes to augura are documented here. Versions follow PEP 440;
between releases `pyproject.toml` carries a `.devN` suffix.

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
