# Peclet Examples

Worked, **runnable** examples for the [`peclet`](https://pypi.org/project/peclet/)
simulation suite — GPU-accelerated particle dynamics, CFD, and the spatial-indexing
primitives they build on. Built with [Quarto](https://quarto.org): each example is
executed to produce its figures and numbers, ships as a downloadable notebook, and
links back to the exact solver API it uses.

**Live site:** https://computational-chemical-engineering.github.io/peclet-examples *(published by CI)*

## Examples

| Example | Methods | Runs where |
|---|---|---|
| [Channel MMS](examples/channel-mms/) | finite differences · MMS · grid convergence | anywhere (pure NumPy) |
| [Poiseuille cut-cell IBM](examples/poiseuille-ibm/) | cut-cell IBM · SDF · projection | Colab/CPU via the `peclet` PyPI wheel (frozen for CI) |
| [Ring packed-bed permeability study](examples/ring-packed-bed/) | dem → flow · porous media · DOE · Kozeny–Carman | Colab/CPU via the `peclet` PyPI wheel (frozen for CI) |

…plus more in the [gallery](https://computational-chemical-engineering.github.io/peclet-examples) (Zick–Homsy, lid-driven cavity, vortex street, random packed bed, custom SDF particles, …).

## Build locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .                      # helpers + NumPy/Matplotlib
pip install jupyter nbclient nbformat

# Render everything (replays frozen solver outputs; re-executes pure-NumPy pages):
quarto render                          # -> _site/

# Re-execute a solver-backed page against a local source build of the suite:
PECLET_LOCAL_BUILD=/path/to/suite/flow/build_mpi OMP_NUM_THREADS=4 \
  quarto render examples/poiseuille-ibm/index.qmd --execute
#   ...or install the solver from PyPI and drop the env var:
#   pip install -e .[sim]
```

## How it's organised

```
src/peclet_examples/     installable helper package (imported by every example)
  mms.py                 pure-NumPy channel MMS
  channels.py            peclet.flow cut-cell Poiseuille driver
examples/<slug>/index.qmd  one worked example each
_freeze/                 committed execution outputs (so CI renders without a GPU)
_quarto.yml              site config (freeze: auto)
.github/workflows/       render + deploy to GitHub Pages
```

## Execution & publishing model

- **Lightweight examples** (pure NumPy) execute in CI and in the browser.
- **Solver-backed examples** are executed by the author on hardware with `peclet`
  installed; Quarto's `freeze` caches the outputs under `_freeze/`, which is
  committed. The Pages CI then **renders only** — no GPU, no compiled solver
  needed. Regenerate a page's freeze with `quarto render <page> --execute`.
- **GitHub Pages** is published by `.github/workflows/publish.yml` on push to `main`.
- **A stale freeze does not fail loudly.** If a page's source changes without its freeze,
  `freeze: auto` re-executes it at render time — and the bootstrap cell's
  `elif find_spec("peclet") is None` branch then *pip-installs peclet* and runs the page on CPU
  wheels. So the failure mode is a slow, silent CPU re-execution (wrong numbers for a
  GPU-authored page, or a job that runs to GitHub's 6-hour limit), not a clean red build. Before
  pushing a freeze refresh, render the WHOLE site on an interpreter with no peclet installed and
  check that **nothing executes** — that is the only test that distinguishes the two.

### Provenance of the current freezes (2026-09-14)

Every solver-backed page was re-executed on one RTX 5080 against **peclet 1.0.0** builds — local
CUDA builds of core, flow, dem, voro, pnm and coupling from the 1.0.0 tags, supplied through
`PECLET_LOCAL_BUILD` to an interpreter with no peclet installed.

`pip install peclet` now resolves to **1.0.1**, so a reader runs one patch release ahead of the
frozen numbers. That is deliberate and it moves nothing: the only 1.0.1 change with a numerical
mechanism is core's `cpu_budget.hpp`, which sizes the Kokkos host pool from a cgroup quota, and it
cannot act here on three counts — the render host has no quota, the render drivers pin
`OMP_NUM_THREADS=8` (an explicit setting makes `defaultHostThreads()` return 0 by design), and the
binaries were built from core v1.0.0, which does not contain the file. Everything else in 1.0.1 is
wheel platform matrices, Kokkos vendoring fallbacks and platform guards; the two other compute-path
edits are a `Kokkos::Threads` branch that a CUDA+OpenMP build never compiles and an `M_PI` ->
`constexpr` substitution with identical digits.

## Large files

Never committed to git (see `.gitignore`):

- **Videos → YouTube.** Pages embed an iframe; nothing is stored in-repo.
- **Datasets / fields (VTI/VTP/HDF5) → [Zenodo](https://zenodo.org)** (the suite
  already mints Zenodo DOIs) or GitHub Release assets, fetched on demand with
  [`pooch`](https://www.fatiando.org/pooch/) (checksummed).
- Git holds only text + the small frozen PNG figures.

## Contributing an example

Read the **[example style guide](STYLE_GUIDE.md)** — it defines the section
skeleton, the Colab bootstrap rule (reader-facing cells install `peclet` from
PyPI), and the freeze policy. Examples must run out-of-the-box on Colab.

Found something surprising while writing an example (a NaN, a divergence, a rough
API edge)? Log it in **[ISSUES.md](ISSUES.md)** — the gallery doubles as a test of
the packages and that backlog feeds fixes back into the suite.

## License

MIT — see [LICENSE](LICENSE).
