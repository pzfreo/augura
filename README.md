# augura

**Will it print? Ask before you print.**

[![PyPI](https://img.shields.io/pypi/v/augura)](https://pypi.org/project/augura/)
[![Python](https://img.shields.io/pypi/pyversions/augura)](https://pypi.org/project/augura/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![CI](https://github.com/pzfreo/augura/actions/workflows/ci.yml/badge.svg)](https://github.com/pzfreo/augura/actions/workflows/ci.yml)
[![coverage](https://img.shields.io/badge/coverage-100%25-brightgreen.svg)](https://github.com/pzfreo/augura/actions/workflows/ci.yml)
[![mypy: strict](https://img.shields.io/badge/mypy-strict-2a6db2.svg)](https://mypy-lang.org/)
[![ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

augura analyses a 3D part and tells you **how it will print — before you slice it.**
It reads the *exact* boundary representation (OpenCASCADE, via
[build123d](https://github.com/gumyr/build123d)) rather than a tessellated mesh,
so overhang angles, wall thicknesses, and the contact footprint are computed
analytically — not approximated. Point it at a STEP file and get a deterministic,
explainable printability report.

> *augura* — Spanish/Italian, "it foretells".

## Capabilities

| Check | What it flags |
|---|---|
| **overhangs** | downward faces shallower than the support angle (bed contact excluded) |
| **orientation search** | ranks candidate poses by unsupported overhang area |
| **manifold / watertight** | a part that isn't a closed solid |
| **tip-over** | centre of mass projecting outside the bed-contact footprint |
| **bed-fit** | a part too big for a declared build volume |
| **brim / raft** | small-footprint / high-aspect parts likely to lift |
| **minimum feature** | the smallest vertical step → your maximum layer height |
| **wall thickness** | walls thinner than `min_perimeters × nozzle` |

**Inputs:** STEP / build123d solids (exact) · STL meshes (degraded, approximate).

## Install

```bash
pip install augura      # or: uv pip install augura
```

STL support is built in — no extra needed.

## CLI

```bash
# Full printability report (human-readable)
augura analyze bracket.step

# Markdown (drop into a PR or wiki) or JSON (machine-readable)
augura analyze bracket.step --format md
augura analyze bracket.step --format json

# Tune to your printer / job
augura analyze bracket.step --nozzle 0.6 --min-perimeters 3
augura analyze bracket.step --build-volume 256 256 256 --support-angle 50

# Gate a build: exit non-zero if any ERROR-severity issue (great for CI / pre-slice)
augura analyze bracket.step --exit-code

# Rank print orientations by how much support each needs (STEP only)
augura orientations bracket.step --format json
```

`augura analyze` accepts `.step` / `.stp` (exact BREP path) or `.stl` (mesh path).

**Example — text:**

```
augura — bracket.step
  [WARNING] overhang: Downward face at 0.0 deg from horizontal needs support
  [WARNING] brim: Recommend a brim: small bed-contact footprint (28 mm2)
  2 finding(s): 0 error, 2 warning
```

**Example — JSON** (`--format json`):

```json
{
  "source": "bracket.step",
  "findings": [
    {"kind": "overhang", "severity": "warning",
     "message": "Downward face at 0.0 deg from horizontal needs support",
     "area": 250.0, "location": [25.0, 0.0, 50.0]}
  ]
}
```

| Flag | Meaning |
|---|---|
| `--format text\|md\|json` | output format (default `text`) |
| `--support-angle` | overhang threshold, degrees from horizontal (default 45) |
| `--nozzle` / `--min-perimeters` | wall-thickness limit = `min_perimeters × nozzle` |
| `--build-volume X Y Z` | enable the bed-fit check against this volume (mm) |
| `--exit-code` | exit `1` if any ERROR finding (manifold / bed-fit / tip-over) |

## Python API

For build123d users, augura is a library too — one façade, `analyze()`, returning
a `Report`:

```python
import augura
from build123d import import_step

report = augura.analyze(import_step("bracket.step"))

for f in report.findings:
    print(f.severity, f.kind, f.message)

report.overhangs        # tuple[Finding, ...] — just the overhang findings
report.bed_fit          # likewise per check: .manifold_issues, .tip_over,
                        # .brim, .min_feature, .thin_walls
report.to_dict()        # JSON-serialisable view
```

Pass any build123d `Shape` you already have in memory — no file needed:

```python
from build123d import Box
report = augura.analyze(Box(40, 40, 5), build_volume=(256, 256, 256))
```

Individual checks and the orientation search are public too:

```python
augura.find_overhangs(shape, support_angle=45.0)
augura.find_thin_walls(shape, nozzle=0.4, min_perimeters=2)
augura.orientation_scores(shape)        # ranked list[OrientationScore], best first
augura.is_watertight(shape)             # bool
```

Top-level surface: `analyze`, `analyze_mesh`, `Report`, `Finding`, `Severity`,
`OrientationScore`, `find_overhangs`, `find_bed_fit`, `find_manifold_issues`,
`find_tip_over`, `find_brim_risk`, `find_thin_features`, `find_thin_walls`,
`min_vertical_feature`, `min_wall_thickness`, `is_watertight`,
`orientation_scores`, `DEFAULT_SUPPORT_ANGLE`.

## Where it fits

```
build123d-mcp  →  augura          →  estampo            →  bambox        →  printer
(design)          (will it print?)   (reproducible slice)  (Bambu package)
```

augura is loosely coupled — it depends on none of its siblings and is usable on
its own. Other tools wrap it; it wraps nothing.

## Status

**Pre-alpha.** The public API is still evolving; `0.1.x` may introduce breaking
changes. See [`SPEC.md`](SPEC.md) for the mission, detailed aims, and non-aims,
and [`CHANGELOG.md`](CHANGELOG.md) for releases.

## License

Apache-2.0.
