# augura — Specification

> *augura* (Spanish/Italian, "it foretells") — ask before you print.

## Mission

**Tell a maker, before they slice, whether a part will print well — and how to
make it print better.** augura analyses a 3D solid and produces a deterministic,
explainable *printability report*: where it will need support, how it should be
oriented, whether it will lift or tip, where it is weakest, and what that implies
for slicer configuration. It answers the question every FDM print silently asks —
*will it print?* — before time and filament are spent finding out.

## The problem

Today the feedback loop for "is this printable?" runs through the slicer and,
ultimately, the printer. You model a part, slice it, eyeball the support preview,
print it, and discover the cantilever sagged or the part snapped along the layer
lines. The geometric facts that determine all of this — overhang angles, the
contact footprint, the thinnest wall, the weakest cross-section — are knowable
*from the model itself*, before any slicing happens. No widely-used Python library
exposes them as a coherent, pre-slice advisory.

## Core insight — analyse the BREP, not a mesh

augura's differentiator is that it reads the **exact boundary representation**
(OpenCASCADE solid, via build123d) rather than a tessellated mesh. Face normals
are *analytic*, not averaged over triangles, so:

- an overhang angle is exact (`-0.707` is exactly 45°, not "≈44.9° ± tessellation
  noise"),
- a downward face resting on the bed is distinguishable from a true overhang,
- the smallest real feature is the smallest real feature, not an artefact of mesh
  density.

Every prior tool in this space (trimesh, PySLM, Tweaker-3) is mesh-first and
therefore approximate. augura is analytic-first and **falls back** to a mesh path
(trimesh) only when the input is a plain STL with no BREP available.

## Where it fits

augura is one loosely-coupled piece of an open, Python-first 3D-design-to-print
ecosystem (all Apache-2.0):

```
build123d-mcp  →  augura        →  estampo            →  bambox        →  printer
(design in CAD)   (will it print?)  (reproducible slice)  (Bambu package)
```

- **build123d / build123d-mcp** — author the geometry.
- **augura** — *foresight*: pre-slice printability + advice (this project).
- **estampo** — ground-truth, reproducible slicing (Orca/Cura in pinned Docker,
  TOML-declared, CI-friendly).
- **bambox** — Bambu-specific packaging and printing.

augura informs estampo but does not depend on it. The boundary is deliberate:
**augura owns decisions derivable from geometry; estampo owns material and printer
process settings.**

## Principles

1. **Analytic-first, mesh-fallback.** BREP is the primary path; mesh is the
   degraded path for STL-only input.
2. **Loosely coupled / independently usable.** augura imports neither
   build123d-mcp nor estampo. It is `pip install augura` on its own. Other tools
   wrap *it*.
3. **A deterministic risk report, not a probability.** Same geometry in → same
   report out. Findings are explainable ("face #4, 250 mm², 0° overhang, no bed
   contact"), never an opaque score.
4. **Expose trade-offs; do not pretend there is one right answer.** Orientation
   is a Pareto trade-off (support cost vs. strength vs. surface finish). augura
   surfaces the frontier and lets the caller weight it.
5. **Stay on the geometry side of the line.** When a decision needs material
   properties, a load case, or a printer profile, augura either takes them as
   *explicit declared inputs* or hands the decision to estampo — it does not
   invent them.

## Aims

### Tier 1 — exact, geometry-only (no extra inputs required)

These need only the solid and the build platform.

- **Overhang detection** — classify every downward face by angle from horizontal;
  flag faces shallower than the support threshold, excluding bed-contact faces.
- **Orientation search** — score candidate orientations by total unsupported
  overhang area (and footprint/height) to recommend low-support orientations.
- **Bed-fit** — does the part fit the named build volume in the proposed
  orientation?
- **Tip-over / stability** — centre-of-mass projected against the contact
  footprint; flag parts that will topple or peel.
- **Minimum feature / layer-height bound** — the smallest vertical feature sets
  the maximum sensible layer height.
- **Wall thinness** — wall sections thinner than N nozzle widths (nozzle diameter
  declared).
- **Manifold / watertight check** — is the solid printable at all?

### Tier 2 — geometry + explicitly declared context

These require the caller to declare something (a load direction, a material
class, a nozzle size) — augura computes, it does not assume.

- **Brim / raft risk** — small or tall-narrow footprints, contact-area heuristics.
- **Strength under a declared load** — augura cannot output absolute strength in
  MPa (that needs material, infill, and a validated load), but given a **declared
  load direction** it computes comparative proxies:
  - alignment of the weak inter-layer plane (⊥ build-Z) with the principal stress,
  - section modulus / second moment of area at the critical cross-section,
  - stress-concentration locations (sharp re-entrant corners on the load path),
  - minimum load-bearing cross-section.
  The output is a *comparison between orientations*, not a safety certificate.

### Output

- A structured, serialisable **`Report`** (findings with locations, magnitudes,
  severities, and human-readable explanations).
- An **optional, one-way adapter** that emits an `estampo.toml` fragment
  (`orient`, `enable_support`, `brim_type`, slicer overrides) from a report. This
  is a pure data transform — augura never imports or calls estampo at runtime.

## Non-aims

augura is defined as much by what it refuses to do:

- **It is not a slicer.** It never generates G-code or toolpaths. Ground-truth
  slicing is estampo's job; augura is the pre-flight check.
- **It does not own process settings.** Temperature, cooling, retraction, flow,
  infill density, speed — these live in estampo's profiles, not here.
- **It is not a printer controller.** Sending jobs to hardware is bambox's job.
- **It does not predict absolute strength.** No MPa figures, no FEA pretence.
  Strength output is always a *relative* comparison under a *declared* load.
- **It does not pick a single "best" orientation.** It exposes the trade-off
  frontier; the caller (human or agent) chooses.
- **It is not mesh-first.** Mesh is a fallback for STL-only input, never the
  primary representation.
- **It ships no GUI.** It is a library. An MCP wrapper may come later as a
  *separate* concern; the core stays headless and importable.
- **It does not depend on its siblings.** No runtime import of build123d-mcp or
  estampo. Coupling is one-way and optional, via plain data.

## Status

**Pre-alpha / specification.** This document defines intent and scope before
implementation. The load-bearing technical assumption — that overhangs can be
classified exactly from build123d face normals, with bed-contact correctly
excluded — has been validated by hand; everything else is to be built against
this spec.

## License

Apache-2.0.
