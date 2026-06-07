# augura

**Will it print? Ask before you print.**

augura analyses a 3D solid and produces a deterministic, explainable
*printability report* — where a part needs support, how to orient it, whether it
will fit, lift, or tip, where it is weakest — **before** it is sliced. It reads
the exact boundary representation (OpenCASCADE, via
[build123d](https://github.com/gumyr/build123d)) rather than a tessellated mesh,
so its geometry is analytic, not approximate.

> *augura* — Spanish/Italian, "it foretells".

## Status

**Pre-alpha / specification.** See [`SPEC.md`](SPEC.md) for the mission, detailed
aims, and non-aims.

## Where it fits

```
build123d-mcp  →  augura        →  estampo            →  bambox        →  printer
(design)          (will it print?)  (reproducible slice)  (Bambu package)
```

augura is loosely coupled — it depends on none of its siblings and is usable on
its own. Other tools wrap it; it wraps nothing.

## License

Apache-2.0.
